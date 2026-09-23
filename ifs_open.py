"""IFS deterministic open forecast subset from the public ECMWF AWS archive."""
import json
import sys

import gfs_archive

BASE = 'https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com'


def candidates(day, hour, lead):
    # Probe both published stream conventions at 06/18 UTC. This avoids guessing
    # which side of the 2026 transition an individual archived run uses.
    streams = ['oper', 'scda'] if hour in (6, 18) else ['oper']
    return [f'{BASE}/{day:%Y%m%d}/{hour:02}z/ifs/0p25/{stream}/'
            f'{day:%Y%m%d}{hour:02}0000-{lead}h-{stream}-fc.grib2' for stream in streams]


def index_url(url):
    return url.rsplit('.', 1)[0] + '.index'


def validate(a):
    if not a.lead_hours:
        raise ValueError('IFS requires --lead-hours, e.g. 0 6 12 24.')
    if any(h not in (0, 6, 12, 18) for h in a.hours):
        raise ValueError('IFS initialization hours must be 0,6,12,18 UTC.')
    if any(h < 0 or h > 360 or (h <= 144 and h % 3) or (h > 144 and h % 6) for h in a.lead_hours):
        raise ValueError('IFS lead hours: 0..144 in 3-hour steps, then 150..360 in 6-hour steps. '
                         'Older cycles and 06/18 UTC runs have shorter limits; absent files raise an error.')
    if a.group == 'static':
        raise ValueError('IFS open supports surface, pressure or all. Specify --variables for individual static fields.')


def select_fields(index, a):
    rows = [json.loads(line) for line in index.splitlines() if line.strip()]
    surface = ['2t', '10u', '10v', 'msl']
    pressure = ['t', 'u', 'v', 'q', 'gh']
    defaults = pressure if a.group == 'pressure' else surface + pressure if a.group == 'all' else surface
    variables = set(a.variables or defaults)
    selected = []
    for row in rows:
        if row.get('param') not in variables:
            continue
        levtype = row.get('levtype')
        if levtype == 'sfc' and a.group in ('surface', 'all'):
            selected.append(row)
        elif levtype == 'pl' and a.group in ('pressure', 'all') and str(row.get('levelist')) in {str(x) for x in a.levels}:
            selected.append(row)
    missing = variables - {r['param'] for r in selected}
    if missing:
        raise ValueError(f'IFS open parameters not found: {sorted(missing)}; consult the index/catalogue for this date.')
    for param in {r['param'] for r in selected if r.get('levtype') == 'pl'}:
        actual = {int(r['levelist']) for r in selected if r['param'] == param and r.get('levtype') == 'pl'}
        absent = set(a.levels) - actual
        if absent:
            raise ValueError(f'IFS {param}: requested pressure levels absent: {sorted(absent)}. '
                             'For older open data, try --levels 50 200 250 300 500 700 850 925 1000.')
    if not selected:
        raise ValueError('No matching IFS fields.')
    ranges = sorted({(int(r['_offset']), int(r['_offset']) + int(r['_length']) - 1) for r in selected})
    if any(start < 0 or end < start for start, end in ranges):
        raise ValueError('Invalid offsets in IFS index.')
    return selected, ranges


def latest_available(a):
    return gfs_archive.latest_available(a, sys.modules[__name__])


def download(a):
    return gfs_archive.download(a, sys.modules[__name__])
