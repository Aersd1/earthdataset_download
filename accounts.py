"""Credential discovery and actionable account notices; never print tokens."""
from __future__ import annotations

import os
from pathlib import Path
import webbrowser

SERVICES = {
    'cds': ('https://cds.climate.copernicus.eu', '.cdsapirc', 'CDS_API_KEY'),
    'ads': ('https://ads.atmosphere.copernicus.eu', '.adsapirc', 'ADS_API_KEY'),
}


def account_notice(service, datasets=(), open_browser=False):
    if service in SERVICES:
        host, filename, env = SERVICES[service]
        urls = [host + '/how-to-api'] + [host + '/datasets/' + ds + '?tab=download' for ds in datasets]
        print(f'[{service.upper()}] Register/login, copy your Personal Access Token, '
              'and accept each dataset licence at the bottom of its download form.')
        print(f'Configure on the download server: python setup_account.py {service}')
    elif service == 'earthdata':
        urls = ['https://urs.earthdata.nasa.gov/', 'https://urs.earthdata.nasa.gov/users/tokens']
        print('[NASA] Register/login and configure EARTHDATA_TOKEN on the download server.')
    else:
        urls = ['https://www.ecmwf.int/en/forecasts/access-forecasts/access-archive-datasets',
                'https://api.ecmwf.int/v1/key/']
        print('[MARS] An ECMWF account alone does not grant access to all historical archives.')
    for url in urls:
        print('  ' + url)
    if open_browser:
        # Avoid launching text browsers that can block a headless server.
        desktop = os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
        if desktop:
            for url in urls:
                try:
                    webbrowser.open(url, new=2)
                except webbrowser.Error:
                    pass
        else:
            print('No desktop browser detected. Open the links above on your own computer.')


def credentials(service):
    host, filename, env = SERVICES[service]
    key = os.environ.get(env)
    if key:
        return host + '/api', key, env
    # Respect standard CDS configuration, but keep ADS credentials separate.
    path = Path(os.environ.get('CDSAPI_RC', str(Path.home() / filename))) if service == 'cds' else Path.home() / filename
    if path.is_file():
        config = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if ':' in line and not line.lstrip().startswith('#'):
                name, value = line.split(':', 1)
                config[name.strip()] = value.strip().strip('"\'')
        if config.get('url', '').rstrip('/') != host + '/api':
            raise ValueError(f'{path} must use url: {host}/api (check CDS versus ADS).')
        if config.get('key') and not config['key'].startswith('<'):
            return host + '/api', config['key'], str(path)
    return None


def cds_client(service, datasets):
    found = credentials(service)
    if not found:
        account_notice(service, datasets, open_browser=True)
        raise ValueError(f'{service.upper()} token is not configured; see the links and setup command above.')
    import cdsapi
    url, key, origin = found
    print(f'{service.upper()} credentials found in {origin}; remote access/licence will be checked on submission.')
    return cdsapi.Client(url=url, key=key)


def explain_api_error(error, service, datasets):
    """Use status, not raw response text which might include authentication data."""
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    if status in (401, 403):
        print(f'HTTP {status}: check token, dataset licence acceptance, and account permissions.')
        account_notice(service, datasets, open_browser=True)
        return True
    return False
