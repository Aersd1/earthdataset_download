"""Inclusive UTC calendar ranges and public catalogue availability."""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def boundary(value, end=False):
    """Expand YYYY / YYYY-MM / YYYY-MM-DD without accepting ambiguous dates."""
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        raise ValueError(f'Invalid date {value!r}; use YYYY, YYYY-MM or YYYY-MM-DD.')
    parts = [int(x) for x in value.split('-')]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else (12 if end else 1)
    # Validate before calling monthrange (which accepts year zero).
    date(year, month, 1)
    day = parts[2] if len(parts) > 2 else (calendar.monthrange(year, month)[1] if end else 1)
    return date(year, month, day).isoformat()


def normalize_dates(a):
    if a.date:
        if a.start or a.end:
            raise ValueError('--date cannot be combined with --start/--end.')
        a.start, a.end = boundary(a.date), boundary(a.date, end=True)
    else:
        a.start = boundary(a.start) if a.start else None
        a.end = boundary(a.end, end=True) if a.end else None
    if a.source != 'subset' and not a.start:
        raise ValueError('Specify --date or --start; --end is optional.')
    if a.start and a.end and a.start > a.end:
        raise ValueError('start must be <= end')


def catalogue_bounds(url):
    try:
        with urlopen(url, timeout=45) as response:
            data = json.load(response)
        intervals = data['extent']['temporal']['interval']
        # Refuse open-ended metadata: do not substitute today's date.
        if len(intervals) != 1 or not all(intervals[0]):
            raise ValueError('No single closed availability interval in catalogue.')
        lo, hi = (boundary(value[:10]) for value in intervals[0])
        return lo, hi
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f'Cannot read latest availability from {url}. '
                         'Retry or supply an explicit --end; no date was guessed.') from exc


def cds_collections(a):
    if a.source == 'era5':
        names = []
        if a.group != 'pressure':
            names.append('reanalysis-era5-single-levels')
        if a.group in ('pressure', 'all'):
            names.append('reanalysis-era5-pressure-levels')
        return [('https://cds.climate.copernicus.eu', name) for name in names]
    name = ('cams-global-reanalysis-eac4' if a.source == 'cams-eac4'
            else 'cams-global-atmospheric-composition-forecasts')
    return [('https://ads.atmosphere.copernicus.eu', name)]


def latest_gfs(a):
    """Find a published day containing EVERY requested cycle and lead on NOMADS."""
    if not a.lead_hours or any(h not in (0, 6, 12, 18) for h in a.hours):
        raise ValueError('GFS requires --lead-hours and cycles 0,6,12,18 UTC.')
    today = datetime.now(timezone.utc).date()
    for offset in range(5):
        day = today - timedelta(days=offset)
        complete = True
        for hour in sorted(set(a.hours), reverse=True):
            for lead in sorted(set(a.lead_hours), reverse=True):
                url = (f'https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/'
                       f'gfs.{day:%Y%m%d}/{hour:02}/atmos/gfs.t{hour:02}z.pgrb2.0p25.f{lead:03}')
                try:
                    with urlopen(Request(url, method='HEAD'), timeout=30) as response:
                        if 'text/html' in response.headers.get('Content-Type', ''):
                            raise ValueError('NOMADS returned HTML instead of a GRIB file.')
                except HTTPError as exc:
                    if exc.code != 404:
                        raise ValueError('Cannot verify NOMADS availability; retry or specify --end.') from exc
                    complete = False
                    break
                except OSError as exc:
                    raise ValueError('Cannot verify NOMADS availability; retry or specify --end.') from exc
            if not complete:
                break
        if complete:
            return day.isoformat()
    raise ValueError('No complete recent GFS day found for the selected cycles/leads.')


def resolve_latest(a):
    """WB/local subsets resolve from their actual time coordinates after opening."""
    if a.end or a.source in ('wb', 'subset'):
        return
    if a.source == 'ifs-open':
        from ifs_open import latest_available
        a.end = latest_available(a)
    elif a.source == 'gfs-archive':
        from gfs_archive import latest_available
        a.end = latest_available(a)
    elif a.source == 'gfs':
        a.end = latest_gfs(a)
    elif a.source in ('era5', 'cams-eac4', 'cams-analysis'):
        bounds = []
        for host, dataset in cds_collections(a):
            url = f'{host}/api/catalogue/v1/collections/{dataset}'
            lo, hi = catalogue_bounds(url)
            print(f'Catalogue availability: {dataset}: {lo} .. {hi}\n  {url}')
            bounds.append((lo, hi))
        first, a.end = max(x[0] for x in bounds), min(x[1] for x in bounds)
        if a.start < first:
            raise ValueError(f'Start precedes catalogue coverage ({first}).')
    else:
        raise ValueError('MARS has no public latest-date catalogue for your account. '
                         'Specify --end after checking your archive permissions/availability.')
    if a.start > a.end:
        raise ValueError(f'Start {a.start} is later than latest available day {a.end}.')


def report_range(a):
    print(f'UTC inclusive range: {a.start or "first available"} .. {a.end or "latest in source"}')
