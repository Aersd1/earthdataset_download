"""Download archive URL lists; discover CMIP6 files and public NOAA object keys.

Discovery writes JSONL manifests and never downloads bulk payloads. HTTPS whole-file
downloads cannot spatially subset GRIB/NetCDF. Use download_region.py subset afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from accounts import account_notice, explain_api_error


def session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s


def fetch(url, target, expected_magic=None, checksum=None, checksum_type=None, earthdata=False):
    import requests
    target = Path(target)
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('HTTPS URL required. Replace http with https only if the source supports it.')
    identity = dict(url=url, checksum=checksum, checksum_type=checksum_type)
    receipt = target.with_suffix(target.suffix + '.source.json')
    if target.exists():
        if receipt.exists() and json.loads(receipt.read_text()) == identity:
            print('Already complete:', target)
            return
        raise ValueError(f'Existing file has different/unknown source: {target}')
    headers = {}
    if earthdata:
        host = urllib.parse.urlparse(url).hostname or ''
        if not host.endswith(('.nasa.gov', '.eosdis.nasa.gov')):
            raise ValueError('Earthdata token may only be used with NASA endpoints.')
        token = os.environ.get('EARTHDATA_TOKEN')
        if not token:
            account_notice('earthdata', open_browser=True)
            raise ValueError('Set EARTHDATA_TOKEN; authorize NASA GES DISC in Earthdata first.')
        headers['Authorization'] = 'Bearer ' + token
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + '.part')
    digest = hashlib.new(checksum_type.lower().replace('-', '')) if checksum and checksum_type else None
    # Partial files restart on retry; this avoids corrupt concatenation when a server ignores Range.
    for attempt in range(3):
        try:
            if digest is not None:
                digest = hashlib.new(checksum_type.lower().replace('-', ''))
            with session() as s, s.get(url, headers=headers, stream=True, timeout=(30, 180)) as r:
                r.raise_for_status()
                if 'text/html' in r.headers.get('Content-Type', '').lower():
                    raise ValueError('Server returned an HTML login/error page instead of data.')
                size = 0
                first = True
                with part.open('wb') as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if not chunk:
                            continue
                        if first:
                            first = False
                            if expected_magic and not chunk.startswith(expected_magic):
                                raise ValueError('Response is not the expected data format.')
                            if chunk.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                                raise ValueError('HTML response rejected.')
                        f.write(chunk)
                        size += len(chunk)
                        if digest is not None:
                            digest.update(chunk)
                if not size:
                    raise ValueError('Empty response.')
                length = r.headers.get('Content-Length')
                if length and not r.headers.get('Content-Encoding') and size != int(length):
                    raise IOError(f'Incomplete response: expected {length}, got {size}')
            if digest is not None and digest.hexdigest().lower() != checksum.lower():
                raise ValueError('Checksum mismatch; .part retained for inspection.')
            part.replace(target)
            receipt.write_text(json.dumps(identity, indent=2), encoding='utf-8')
            print(f'Saved {size:,} bytes: {target}')
            return
        except (requests.RequestException, OSError) as exc:
            if earthdata and explain_api_error(exc, 'earthdata', []):
                raise ValueError('NASA access denied; see account instructions above.') from None
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def write_manifest(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')
    print(f'{len(rows)} files listed in {output}; inspect before downloading.')


def esgf(a):
    # Source models from Aurora v2, not arbitrary same-name climate projections.
    params = dict(project='CMIP6', activity_id='HighResMIP', experiment_id='hist-1950',
                  source_id=a.model, variable_id=','.join(a.variables), type='File',
                  latest='true', replica='false', format='application/solr+json', limit=200,
                  member_id=a.member, table_id=a.table)
    rows, seen, offset = [], set(), 0
    with session() as s:
        while True:
            params['offset'] = offset
            r = s.get(a.endpoint, params=params, timeout=90)
            r.raise_for_status()
            response = r.json()['response']
            docs = response['docs']
            if not docs:
                break
            for doc in docs:
                urls = [u.split('|')[0] for u in doc.get('url', []) if u.endswith('|HTTPServer')]
                if not urls:
                    continue
                url = urls[0]
                # ESGF file naming convention includes the time interval at the end.
                filename = doc.get('title', urllib.parse.urlparse(url).path.rsplit('/', 1)[-1])
                interval = filename.removesuffix('.nc').rsplit('_', 1)[-1].split('-')
                if len(interval) == 2 and all(v[:4].isdigit() for v in interval):
                    if int(interval[1][:4]) < a.start_year or int(interval[0][:4]) > a.end_year:
                        continue
                if url in seen:
                    continue
                seen.add(url)
                def scalar(key):
                    value = doc.get(key)
                    return value[0] if isinstance(value, list) and value else value
                rows.append(dict(url=url, filename=filename, size=doc.get('size'),
                                 checksum=scalar('checksum'), checksum_type=scalar('checksum_type'),
                                 dataset_id=doc.get('dataset_id'), model=a.model))
            offset += len(docs)
            if offset >= response['numFound']:
                break
    if not rows:
        raise ValueError('No files matched. Check node, member and table; no fallback to another experiment.')
    write_manifest(rows, a.out)


def noaa(a):
    endpoint = f'https://{a.bucket}.s3.amazonaws.com/'
    params = {'list-type': '2', 'prefix': a.prefix, 'max-keys': '1000'}
    ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    rows = []
    with session() as s:
        while True:
            r = s.get(endpoint, params=params, timeout=90)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall('s3:Contents', ns):
                key = item.findtext('s3:Key', namespaces=ns)
                if not key or key.endswith('/') or (a.contains and a.contains not in key):
                    continue
                # Hash prevents collisions between cycles, members and directory versions.
                rows.append(dict(url=endpoint + urllib.parse.quote(key, safe='/'),
                                 filename=hashlib.sha256(key.encode()).hexdigest()[:10] + '_' + key.rsplit('/', 1)[-1],
                                 key=key, size=int(item.findtext('s3:Size', namespaces=ns))))
            token = root.findtext('s3:NextContinuationToken', namespaces=ns)
            if not token:
                break
            params['continuation-token'] = token
    write_manifest(rows, a.out)


def download(a):
    lines = a.manifest.read_text(encoding='utf-8-sig').splitlines()
    rows = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        row = json.loads(line) if line.lstrip().startswith('{') else {'url': line.strip()}
        rows.append(row)
    for row in rows:
        url = row['url']
        name = row.get('filename') or (hashlib.sha256(url.encode()).hexdigest()[:10] + '_' +
               urllib.parse.unquote(urllib.parse.urlparse(url).path).rsplit('/', 1)[-1])
        if not name or any(c in name for c in '/\\:') or name in ('.', '..'):
            raise ValueError('Unsafe filename in manifest.')
        target = a.out / name
        if a.dry_run:
            print(json.dumps(dict(target=str(target), url=url, bytes=row.get('size'))))
        else:
            fetch(url, target, checksum=row.get('checksum'), checksum_type=row.get('checksum_type'),
                  earthdata=a.earthdata)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('esgf', help='Discover CMIP6 HighResMIP hist-1950 NetCDF files')
    e.add_argument('--endpoint', default='https://esgf-data.dkrz.de/esg-search/search')
    e.add_argument('--model', choices=['CMCC-CM2-VHR4', 'ECMWF-IFS-HR'], required=True)
    e.add_argument('--member', default='r1i1p1f1')
    e.add_argument('--table', default='6hrPlevPt')
    e.add_argument('--variables', nargs='+', default=['tas', 'uas', 'vas', 'psl'])
    e.add_argument('--start-year', type=int, default=1950)
    e.add_argument('--end-year', type=int, default=2014)
    e.add_argument('--out', type=Path, required=True)
    n = sub.add_parser('noaa', help='List actual NOAA archive keys (does not assume historical availability)')
    n.add_argument('--bucket', choices=['noaa-gfs-bdp-pds', 'noaa-gefs-retrospective'], required=True)
    n.add_argument('--prefix', required=True, help='E.g. GEFSv12/reforecast/2000/2000010100/c00/')
    n.add_argument('--contains', help='Keep keys containing this substring')
    n.add_argument('--out', type=Path, required=True)
    d = sub.add_parser('fetch', help='Download HTTPS URLs from JSONL or one-URL-per-line text')
    d.add_argument('--manifest', type=Path, required=True)
    d.add_argument('--out', type=Path, required=True)
    d.add_argument('--earthdata', action='store_true', help='NASA URLs only; use EARTHDATA_TOKEN')
    d.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    try:
        {'esgf': esgf, 'noaa': noaa, 'fetch': download}[a.command](a)
    except (ValueError, ImportError) as error:
        p.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
