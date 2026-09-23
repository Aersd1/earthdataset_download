"""Regional Aurora data acquisition. All dates/times are UTC; see README_zh.md."""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

LEVELS = [50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000]
SURFACE = ['2m_temperature', '10m_u_component_of_wind',
           '10m_v_component_of_wind', 'mean_sea_level_pressure']
ATMOS = ['temperature', 'u_component_of_wind', 'v_component_of_wind',
         'specific_humidity', 'geopotential']
STATIC = ['geopotential', 'land_sea_mask', 'soil_type']
WB = {
    'era5': 'era5/1959-2023_01_10-wb13-6h-1440x721_with_derived_variables.zarr',
    'hres': 'hres/2016-2022-0012-1440x721.zarr',
    'hres-t0': 'hres_t0/2016-2022-6h-1440x721.zarr',
    'ifs-ens': 'ifs_ens/2018-2022-1440x721.zarr',
    'ifs-ens-mean': 'ifs_ens/2018-2022-1440x721_mean.zarr',
}


def region(lat, lon, radius_km):
    """Spherical cap bounding box, N/W/S/E. Dateline crossing rejected explicitly."""
    if not all(math.isfinite(x) for x in [lat, lon, radius_km]):
        raise ValueError('Coordinates/radius must be finite.')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180 or radius_km < 0:
        raise ValueError('Use latitude [-90,90], longitude [-180,180], radius >= 0.')
    angle = radius_km / 6371.0088
    delta = math.degrees(angle)
    north, south = min(90, lat + delta), max(-90, lat - delta)
    if delta >= 180 or north == 90 or south == -90:
        return [north, -180.0, south, 180.0]
    dx = math.degrees(math.asin(min(1, math.sin(angle) / math.cos(math.radians(lat)))))
    if lon - dx < -180 or lon + dx > 180:
        raise ValueError('Bounding box crosses the dateline; split into two requests.')
    return [north, lon - dx, south, lon + dx]


def monthly(start, end):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end:
        raise ValueError('start must be <= end')
    while start <= end:
        last = min(end, date(start.year, start.month,
                             calendar.monthrange(start.year, start.month)[1]))
        yield start, last
        start = last + timedelta(days=1)


def point_area(lat, lon, step):
    region(lat, lon, 0)
    y, x = round(round(lat / step) * step, 8), round(round(lon / step) * step, 8)
    return [y, x, y, x]


def request_area(a, step):
    return point_area(a.lat, a.lon, step) if a.point else region(a.lat, a.lon, a.radius_km)


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def api_jobs(a):
    """Pure request construction; dry runs require neither credentials nor packages."""
    if a.source == 'era5':
        area = request_area(a, .25)
        groups = {'surface': SURFACE, 'pressure': ATMOS, 'static': STATIC}
        selected = list(groups) if a.group == 'all' else [a.group]
        for first, last in monthly(a.start, a.end):
            for group in selected:
                if group == 'static' and first.isoformat() != a.start:
                    continue
                req = dict(product_type=['reanalysis'], variable=a.variables or groups[group],
                           year=[str(first.year)], month=[f'{first.month:02}'],
                           day=[f'{d:02}' for d in range(first.day, last.day + 1)],
                           time=[f'{h:02}:00' for h in a.hours], area=area,
                           data_format='netcdf', download_format='unarchived')
                if group == 'pressure':
                    req['pressure_level'] = [str(x) for x in a.levels]
                if group == 'static':
                    req.update(day=[f'{first.day:02}'], time=['00:00'])
                ds = 'reanalysis-era5-' + ('pressure-levels' if group == 'pressure' else 'single-levels')
                yield ds, req, f'era5_{group}_{first}_{last}', '.nc'
    elif a.source.startswith('cams'):
        if a.group not in ('surface', 'pressure'):
            raise ValueError('CAMS: choose surface or pressure, one group per request.')
        if not a.variables:
            raise ValueError('CAMS requires --variables (names from the ADS catalogue).')
        eac4 = a.source == 'cams-eac4'
        ds = 'cams-global-reanalysis-eac4' if eac4 else 'cams-global-atmospheric-composition-forecasts'
        if not eac4 and date.fromisoformat(a.end) >= date(2023, 6, 27):
            raise ValueError('This CAMS preset targets the paper-era 0.4 degree grid before 2023-06-27.')
        for first, last in monthly(a.start, a.end):
            req = dict(date=f'{first}/{last}', time=[f'{h:02}:00' for h in a.hours],
                       area=request_area(a, .75 if eac4 else .4),
                       variable=a.variables, format='grib')
            if a.group == 'pressure':
                req['pressure_level'] = [str(x) for x in a.levels]
            if not eac4:
                req.update(type='analysis', leadtime_hour='0')
            yield ds, req, f'{a.source}_{a.group}_{first}_{last}', '.grib'
    elif a.source == 'hres-mars':
        if a.group not in ('surface', 'pressure'):
            raise ValueError('MARS: choose surface or pressure.')
        for first, last in monthly(a.start, a.end):
            req = {'class': 'od', 'stream': 'oper', 'expver': '1', 'type': 'an',
                   'date': f'{first}/to/{last}', 'time': '/'.join(f'{h:02}' for h in a.hours),
                   'step': '0', 'levtype': 'pl' if a.group == 'pressure' else 'sfc',
                   'param': '/'.join(a.variables or (['t', 'u', 'v', 'q', 'z']
                            if a.group == 'pressure' else ['2t', '10u', '10v', 'msl'])),
                   'grid': f'{a.grid}/{a.grid}',
                   'area': '/'.join(str(v) for v in request_area(a, a.grid))}
            if a.group == 'pressure':
                req['levelist'] = '/'.join(map(str, a.levels))
            yield 'mars', req, f'hres_analysis_{a.group}_{first}_{last}', '.grib'


def api_download(a):
    jobs = list(api_jobs(a))
    client = None
    for ds, req, label, suffix in jobs:
        record = {'dataset': ds, 'request': req,
                  'selection': dict(lat=a.lat, lon=a.lon, point=a.point, radius_km=a.radius_km)}
        target = a.out / f'{label}_{fingerprint(record)}{suffix}'
        print(json.dumps({'target': str(target), **record}, indent=2))
        if a.dry_run:
            continue
        if client is None:
            if a.source == 'hres-mars':
                import ecmwfapi
                client = ecmwfapi.ECMWFService('mars')
            else:
                import cdsapi
                service = 'CDS' if a.source == 'era5' else 'ADS'
                url = ('https://cds.climate.copernicus.eu/api' if service == 'CDS'
                       else 'https://ads.atmosphere.copernicus.eu/api')
                key = os.environ.get(service + '_API_KEY')
                if not key:
                    raise ValueError(f'Set {service}_API_KEY in your environment; see README_zh.md.')
                client = cdsapi.Client(url=url, key=key)
        a.out.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size:
            print('Already complete:', target)
            continue
        part = target.with_suffix(target.suffix + '.part')
        if ds == 'mars':
            client.execute(req, str(part))
        else:
            client.retrieve(ds, req, str(part))
        if not part.exists() or part.stat().st_size == 0:
            raise RuntimeError('Empty download; final file not written.')
        part.replace(target)
        target.with_suffix(target.suffix + '.request.json').write_text(
            json.dumps(record, indent=2), encoding='utf-8')
        print('Saved:', target)


def spatial_subset(ds, lat, lon, radius_km=50, point=False, mask_values=True):
    """Select rectilinear grid; nearest point or bounding box plus exact circle mask."""
    import numpy as np
    import xarray as xr
    region(lat, lon, 0 if point else radius_km)
    y = next((n for n in ['latitude', 'lat'] if n in ds.coords), None)
    x = next((n for n in ['longitude', 'lon'] if n in ds.coords), None)
    if y is None or x is None or ds[y].dims != (y,) or ds[x].dims != (x,):
        raise ValueError('Only one-dimensional latitude/longitude grids are supported.')
    ys, xs = ds[y].values, ds[x].values
    if not len(ys) or not len(xs):
        raise ValueError('Empty coordinate axis.')
    xnorm = (xs + 180) % 360 - 180
    if point:
        # Nearest rectilinear grid coordinate, cyclic longitude distance.
        iy = int(np.abs(ys - lat).argmin())
        ix = int(np.abs((xnorm - lon + 180) % 360 - 180).argmin())
        if lat < ys.min() - 1e-6 or lat > ys.max() + 1e-6:
            raise ValueError('Requested latitude outside available data.')
        out = ds.isel({y: [iy], x: [ix]})
    else:
        north, west, south, east = region(lat, lon, radius_km)
        iy = np.flatnonzero((ys >= south) & (ys <= north))
        ix = np.flatnonzero((xnorm >= west) & (xnorm <= east))
        if not len(iy) or not len(ix):
            raise ValueError('No grid centres in region; increase radius or use --point.')
        out = ds.isel({y: iy, x: ix})
    phi = np.deg2rad(out[y] - lat)
    lam = np.deg2rad((out[x] - lon + 180) % 360 - 180)
    h = np.sin(phi / 2)**2 + np.cos(np.deg2rad(lat)) * np.cos(np.deg2rad(out[y])) * np.sin(lam / 2)**2
    distance = 6371.0088 * 2 * np.arcsin(np.sqrt(h.clip(0, 1)))
    out = out.assign_coords(distance_km=distance)
    if not point:
        mask = distance <= radius_km + 1e-8
        if not bool(mask.any()):
            raise ValueError('No grid centres in circle; increase radius or use --point.')
        # Do not broadcast scalar or non-spatial variables to a new grid.
        if mask_values:
            out = xr.Dataset({n: v.where(mask) if y in v.dims and x in v.dims else v
                              for n, v in out.data_vars.items()}, coords=out.coords, attrs=out.attrs)
        out['within_radius'] = mask.astype('int8')
    out.attrs.update(requested_latitude=lat, requested_longitude=lon,
                     spatial_selection='nearest_grid' if point else 'circle',
                     requested_radius_km=0 if point else radius_km)
    return out


def save_netcdf(ds, target, csv=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix('.nc.part')
    # Source Zarr chunk/compressor encoding is not valid NetCDF encoding.
    ds = ds.drop_encoding()
    if csv:
        ds = ds.load()  # Avoid downloading the same remote chunks again for CSV.
    ds.to_netcdf(part, engine='netcdf4')
    part.replace(target)
    print('Saved:', target)
    if csv:
        ds.to_dataframe().reset_index().to_csv(target.with_suffix('.csv'), index=False)


def wb_request(a, first, last):
    groups = {'surface': SURFACE, 'pressure': ATMOS, 'all': SURFACE + ATMOS,
              'static': STATIC}
    return dict(url='https://storage.googleapis.com/weatherbench2/datasets/' + WB[a.dataset],
                start=str(first), end=str(last), variables=a.variables or groups[a.group],
                hours=a.hours, lat=a.lat, lon=a.lon, point=a.point,
                radius_km=0 if a.point else a.radius_km,
                levels=a.levels, lead_hours=a.lead_hours, members=a.members)


def wb_download(a):
    import numpy as np
    import xarray as xr
    # Public HTTPS exposes the same GCS objects without authentication or gRPC threads.
    for first, last in monthly(a.start, a.end):
        record = wb_request(a, first, last)
        url, variables = record['url'], record['variables']
        target = a.out / f'wb_{a.dataset}_{first}_{last}_{fingerprint(record)}.nc'
        if not a.dry_run and target.exists() and target.stat().st_size:
            print('Already complete:', target)
            if a.csv and not target.with_suffix('.csv').exists():
                with xr.open_dataset(target) as saved:
                    saved.to_dataframe().reset_index().to_csv(target.with_suffix('.csv'), index=False)
            continue
        # Open only coordinate metadata until writing the regional result.
        with xr.open_zarr(url, consolidated=True,
                          storage_options={'client_kwargs': {'trust_env': True}},
                          chunks=None, decode_timedelta=True) as source:
            missing = set(variables) - set(source.data_vars)
            if missing:
                raise ValueError(f'Unavailable variables: {missing}')
            lo, hi = source.time.values[[0, -1]].astype('datetime64[D]')
            if np.datetime64(first) < lo or np.datetime64(last) > hi:
                raise ValueError(f'Time outside store coverage {lo} to {hi}; use CDS/MARS for other dates.')
            ds = source[variables].sel(time=slice(str(first), str(last)))
            ds = ds.isel(time=np.flatnonzero(np.isin(ds.time.dt.hour.values, a.hours)))
            if not ds.sizes['time']:
                raise ValueError('No matching times.')
            if 'level' in ds.dims:
                ds = ds.sel(level=a.levels)
            if 'prediction_timedelta' in ds.dims:
                if not a.lead_hours:
                    raise ValueError('Forecast data requires --lead-hours, e.g. 0 6 12 24.')
                ds = ds.sel(prediction_timedelta=[np.timedelta64(h, 'h') for h in a.lead_hours])
            if 'number' in ds.dims:
                if not a.members:
                    raise ValueError('Ensemble data requires --members, e.g. 1 2 3.')
                ds = ds.sel(number=a.members)
            ds = spatial_subset(ds, a.lat, a.lon, a.radius_km, a.point, mask_values=not a.dry_run)
            ds.attrs.update(source_url=url, time_reference='UTC; forecast time is initialization time')
            print(json.dumps({'target': str(target), 'shape': dict(ds.sizes),
                              'output_MiB': round(ds.nbytes / 2**20, 3),
                              'warning': 'Remote chunks may contain entire global fields.'}, indent=2))
            if a.dry_run:
                continue
            save_netcdf(ds, target, a.csv)
            target.with_suffix('.request.json').write_text(json.dumps(record, indent=2), encoding='utf-8')


def subset_file(a):
    import xarray as xr
    kwargs = {'engine': a.engine} if a.engine else {}
    if a.engine == 'cfgrib':
        kwargs['backend_kwargs'] = {'indexpath': ''}
    with xr.open_dataset(a.input, **kwargs) as original:
        ds = original[a.variables] if a.variables else original
        time_name = next((n for n in ['time', 'valid_time'] if n in ds.dims), None)
        if time_name and a.start:
            ds = ds.sel({time_name: slice(a.start, a.end)})
            if ds.sizes[time_name] == 0:
                raise ValueError('Empty time selection.')
        out = spatial_subset(ds, a.lat, a.lon, a.radius_km, a.point, mask_values=not a.dry_run)
        print(out)
        if not a.dry_run:
            selection = dict(input=a.input, lat=a.lat, lon=a.lon, point=a.point,
                             radius_km=a.radius_km, start=a.start, end=a.end, variables=a.variables)
            save_netcdf(out, a.out / (Path(a.input).stem + '_subset_' + fingerprint(selection) + '.nc'), a.csv)


def gfs_download(a):
    from urllib.parse import urlencode
    from download_files import fetch
    first, last = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if last < first:
        raise ValueError('start must be <= end')
    if (date.today() - first).days > 10:
        raise ValueError('NOMADS is a rolling recent archive, not the 2015-2020 paper archive. See README.')
    if not a.lead_hours:
        raise ValueError('GFS requires --lead-hours (0 selects forecast initialization).')
    if a.point:
        raise ValueError('NOMADS needs an area. Use --radius-km 30, then subset --point.')
    north, west, south, east = request_area(a, .25)
    current = first
    while current <= last:
        for hour in a.hours:
            if hour not in [0, 6, 12, 18]:
                raise ValueError('GFS cycle must be 0,6,12,18 UTC.')
            for lead in a.lead_hours:
                req = dict(file=f'gfs.t{hour:02}z.pgrb2.0p25.f{lead:03}',
                           dir=f'/gfs.{current:%Y%m%d}/{hour:02}/atmos', subregion='',
                           leftlon=west, rightlon=east, toplat=north, bottomlat=south)
                for name in a.variables or ['UGRD', 'VGRD', 'TMP', 'PRMSL']:
                    req['var_' + name] = 'on'
                for lev in ['10_m_above_ground', '2_m_above_ground', 'mean_sea_level']:
                    req['lev_' + lev] = 'on'
                if a.group == 'pressure':
                    for lev in a.levels:
                        req[f'lev_{lev}_mb'] = 'on'
                url = 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?' + urlencode(req)
                target = a.out / f'gfs_{current}_{hour:02}_f{lead:03}_{fingerprint(req)}.grib2'
                print(url)
                if not a.dry_run:
                    fetch(url, target, expected_magic=b'GRIB')
                    import time
                    time.sleep(2)
        current += timedelta(days=1)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', choices=['era5', 'wb', 'cams-eac4', 'cams-analysis', 'hres-mars', 'gfs', 'subset'])
    p.add_argument('--lat', type=float, default=36.3)
    p.add_argument('--lon', type=float, default=120.33)
    space = p.add_mutually_exclusive_group()
    space.add_argument('--point', '--nearest', action='store_true', help='Select nearest grid point')
    space.add_argument('--radius-km', type=float, default=50, help='Default 50; APIs return enclosing rectangle')
    p.add_argument('--start', help='YYYY-MM-DD, inclusive UTC date')
    p.add_argument('--end', help='YYYY-MM-DD, inclusive UTC date')
    p.add_argument('--hours', nargs='+', type=int, default=[0, 6, 12, 18])
    p.add_argument('--group', choices=['surface', 'pressure', 'static', 'all'], default='surface')
    p.add_argument('--variables', nargs='+')
    p.add_argument('--levels', nargs='+', type=int, default=LEVELS)
    p.add_argument('--dataset', choices=list(WB), default='era5')
    p.add_argument('--lead-hours', nargs='+', type=int)
    p.add_argument('--members', nargs='+', type=int)
    p.add_argument('--grid', type=float, choices=[.1, .25], default=.1)
    p.add_argument('--input', help='Local NetCDF/GRIB or authenticated OPeNDAP URL')
    p.add_argument('--engine', choices=['netcdf4', 'cfgrib'])
    p.add_argument('--out', type=Path, default=Path(__file__).parent / 'downloads')
    p.add_argument('--csv', action='store_true', help='WB/subset also write CSV (small point data recommended)')
    p.add_argument('--dry-run', action='store_true')
    return p


def main():
    p = parser()
    a = p.parse_args()
    try:
        region(a.lat, a.lon, 0 if a.point else a.radius_km)
        if any(h < 0 or h > 23 for h in a.hours):
            raise ValueError('--hours must be 0..23')
        if a.lead_hours and any(h < 0 for h in a.lead_hours):
            raise ValueError('Lead times cannot be negative.')
        if a.source != 'subset' and (not a.start or not a.end):
            raise ValueError('--start and --end are required; no implicit multi-year downloads.')
        if a.start and a.end:
            list(monthly(a.start, a.end))
        if a.source == 'subset' and not a.input:
            raise ValueError('subset requires --input')
        if a.source == 'era5' and a.group == 'all' and a.variables:
            raise ValueError('--variables requires a single --group.')
        if a.csv and a.source not in ('wb', 'subset'):
            raise ValueError('--csv applies to wb/subset; download first, then use subset --csv.')
        {'wb': wb_download, 'subset': subset_file, 'gfs': gfs_download}.get(a.source, api_download)(a)
    except (ValueError, ImportError) as error:
        p.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
