"""Public NOAA GFS 0.25-degree archive: indexed fields, then local spatial selection.

No AWS account is needed. --start/--end describe initialization dates, in UTC.
"""
from datetime import date, datetime, timedelta, timezone
import json
import re
import sys

from download_files import session

BASE = 'https://noaa-gfs-bdp-pds.s3.amazonaws.com'


def object_url(day, hour, lead):
    return (f'{BASE}/gfs.{day:%Y%m%d}/{hour:02}/atmos/'
            f'gfs.t{hour:02}z.pgrb2.0p25.f{lead:03}')


def candidates(day, hour, lead):
    return [object_url(day, hour, lead)]


def index_url(url):
    return url + '.idx'


def locate(client, provider, day, hour, lead, head=False):
    for url in provider.candidates(day, hour, lead):
        method = client.head if head else client.get
        with method(provider.index_url(url), timeout=45) as response:
            if response.status_code == 404:
                continue
            response.raise_for_status()
            text = None if head else response.text
        if head:
            with client.head(url, timeout=30) as response:
                if response.status_code == 404:
                    continue
                response.raise_for_status()
        return url, text
    return None


def validate(a):
    if not a.lead_hours:
        raise ValueError('GFS requires --lead-hours: 0 for initialization, e.g. 6 12 24 for forecasts.')
    if any(h not in (0, 6, 12, 18) for h in a.hours):
        raise ValueError('GFS initialization hours must be 0,6,12,18 UTC.')
    if any(h < 0 or h > 384 or (h > 120 and h % 3) for h in a.lead_hours):
        raise ValueError('GFS lead hours: 0..120 hourly, then 123..384 in 3-hour steps.')
    if a.group == 'static':
        raise ValueError('GFS archive supports surface, pressure or all.')


def latest_available(a, provider=None):
    provider = provider or sys.modules[__name__]
    provider.validate(a)
    today = datetime.now(timezone.utc).date()
    with session() as client:
        for offset in range(5):
            day = today - timedelta(days=offset)
            complete = True
            for hour in sorted(set(a.hours), reverse=True):
                for lead in sorted(set(a.lead_hours), reverse=True):
                    if not locate(client, provider, day, hour, lead, head=True):
                        complete = False
                    if not complete:
                        break
                if not complete:
                    break
            if complete:
                return day.isoformat()
    raise ValueError(f'No complete recent {a.source} day found for all selected cycles/lead hours; specify --end or retry.')


def select_fields(index, a):
    records = []
    for line in index.splitlines():
        cols = line.split(':')
        if len(cols) < 6 or not cols[1].isdigit():
            raise ValueError('Unrecognised GFS .idx record; refusing to guess byte offsets.')
        records.append(dict(offset=int(cols[1]), variable=cols[3], level=cols[4]))
    if not records or records[0]['offset'] != 0:
        raise ValueError('Empty or incomplete GFS index.')
    offsets = sorted({r['offset'] for r in records})
    ends = {start: offsets[i + 1] - 1 if i + 1 < len(offsets) else None
            for i, start in enumerate(offsets)}
    surface = {'2 m above ground', '10 m above ground', 'mean sea level'}
    levels = set()
    if a.group in ('surface', 'all'):
        levels |= surface
    if a.group in ('pressure', 'all'):
        levels |= {f'{lev} mb' for lev in a.levels}
    default = (['TMP', 'UGRD', 'VGRD', 'SPFH', 'HGT'] if a.group == 'pressure'
               else ['TMP', 'UGRD', 'VGRD', 'PRMSL', 'SPFH', 'HGT'] if a.group == 'all'
               else ['TMP', 'UGRD', 'VGRD', 'PRMSL'])
    variables = set(a.variables or default)
    selected = [r for r in records if r['variable'] in variables and r['level'] in levels]
    missing = variables - {r['variable'] for r in selected}
    if missing:
        raise ValueError(f'GFS fields not found at selected levels: {sorted(missing)}. Use GFS names such as UGRD, VGRD, TMP.')
    if not selected:
        raise ValueError('No matching GFS fields.')
    pressure_variables = {r['variable'] for r in selected if r['level'].endswith(' mb')}
    for variable in pressure_variables:
        actual = {int(r['level'].split()[0]) for r in selected
                  if r['variable'] == variable and r['level'].endswith(' mb')}
        if set(a.levels) - actual:
            raise ValueError(f'GFS {variable}: pressure levels absent: {sorted(set(a.levels) - actual)}.')
    # A multi-field GRIB message can have several inventory entries at one offset.
    # Fetch each complete message once. Coupled fields in one message are retained.
    ranges = [(start, ends[start]) for start in sorted({r['offset'] for r in selected})]
    return selected, ranges


def download_ranges(client, url, ranges, target):
    part = target.with_suffix(target.suffix + '.part')
    with part.open('wb') as output:
        for start, end in ranges:
            interval = f'{start}-{end if end is not None else ""}'
            with client.get(url, headers={'Range': f'bytes={interval}', 'Accept-Encoding': 'identity'},
                            stream=True, timeout=(30, 180)) as response:
                response.raise_for_status()
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                if response.status_code != 206 or not match:
                    raise ValueError('Server did not honour HTTP Range; refusing a full global-file download.')
                actual_start, actual_end, total = map(int, match.groups())
                if actual_start != start or actual_end != (total - 1 if end is None else end):
                    raise ValueError('Unexpected Content-Range from GFS server.')
                size, magic = 0, b''
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    if len(magic) < 4:
                        magic = (magic + chunk)[:4]
                    output.write(chunk)
                    size += len(chunk)
                if size != actual_end - actual_start + 1 or magic != b'GRIB':
                    raise ValueError('Incomplete/invalid GRIB message; partial download retained.')
    part.replace(target)


def download(a, provider=None):
    provider = provider or sys.modules[__name__]
    if not a.dry_run:
        import cfgrib
    # Imported at call time to keep the CLI module independent at import time.
    from download_region import fingerprint, spatial_subset, save_netcdf
    provider.validate(a)
    first, last = date.fromisoformat(a.start), date.fromisoformat(a.end)
    with session() as client:
        day = first
        while day <= last:
            for hour in sorted(set(a.hours)):
                for lead in sorted(set(a.lead_hours)):
                    record = dict(source=a.source, date=str(day), hour=hour, lead=lead,
                                  group=a.group, variables=a.variables, levels=a.levels,
                                  lat=a.lat, lon=a.lon, point=a.point, radius_km=a.radius_km,
                                  csv=a.csv, keep_grib=a.keep_grib, format_version=1)
                    label = f'{a.source}_{day}_{hour:02}_f{lead:03}_{fingerprint(record)}'
                    receipt = a.out / (label + '.request.json')
                    if receipt.is_file() and not a.dry_run:
                        saved = json.loads(receipt.read_text(encoding='utf-8'))
                        outputs = saved.get('outputs', [])
                        if outputs and all((a.out / name).is_file() and (a.out / name).stat().st_size for name in outputs):
                            print('Already complete:', receipt)
                            continue
                    found = locate(client, provider, day, hour, lead)
                    if not found:
                        raise ValueError(f'{a.source} archive missing {day} {hour:02} UTC +{lead}h. '
                                         'No dates silently skipped. Check archive retention or selected lead hours.')
                    url, index = found
                    selected, ranges = provider.select_fields(index, a)
                    print(json.dumps(dict(url=url, selected_fields=selected, byte_ranges=ranges,
                                          warning='Selected GRIB messages cover global fields; spatial subset follows.'), indent=2))
                    if a.dry_run:
                        continue
                    a.out.mkdir(parents=True, exist_ok=True)
                    grib = a.out / (label + '.grib2')
                    download_ranges(client, url, ranges, grib)
                    # Decode each selected parameter/level separately to avoid mixing 2m/10m
                    # fields or analysis and forecast time coordinates in one hypercube.
                    parts = []
                    datasets = cfgrib.open_datasets(str(grib), backend_kwargs={'indexpath': '', 'errors': 'raise'})
                    try:
                        for part_number, dataset in enumerate(datasets, 1):
                            out = spatial_subset(dataset, a.lat, a.lon, a.radius_km, a.point)
                            out.attrs.update(source_url=url, forecast_reference_time=f'{day}T{hour:02}:00:00Z',
                                             forecast_lead_hours=lead, time_reference='UTC; selection dates are initialization dates')
                            target = a.out / f'{label}_part{part_number:02}.nc'
                            save_netcdf(out, target, a.csv)
                            parts.append(target.name)
                            if a.csv:
                                parts.append(target.with_suffix('.csv').name)
                    finally:
                        for dataset in datasets:
                            dataset.close()
                    if not parts:
                        raise ValueError('No decoded GFS fields; completion receipt not written.')
                    if a.keep_grib:
                        parts.append(grib.name)
                    else:
                        grib.unlink()
                    receipt_tmp = receipt.with_suffix('.json.part')
                    receipt_tmp.write_text(json.dumps(dict(record, url=url, selected_fields=selected, outputs=parts), indent=2), encoding='utf-8')
                    receipt_tmp.replace(receipt)
            day += timedelta(days=1)
