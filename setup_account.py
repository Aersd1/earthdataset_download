"""Configure CDS/ADS on the machine that will perform downloads."""
import argparse
import getpass
import os
from pathlib import Path
import sys

from accounts import SERVICES, account_notice, credentials


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('service', choices=['cds', 'ads', 'earthdata', 'mars'])
    p.add_argument('--check', action='store_true', help='Check local configuration only; no data request')
    p.add_argument('--open', action='store_true', help='Open account/help pages when a desktop is available')
    a = p.parse_args()
    datasets = (['reanalysis-era5-single-levels', 'reanalysis-era5-pressure-levels'] if a.service == 'cds'
                else ['cams-global-reanalysis-eac4', 'cams-global-atmospheric-composition-forecasts'] if a.service == 'ads' else [])
    try:
        account_notice(a.service, datasets, open_browser=a.open)
        if a.service not in SERVICES:
            return
        if a.check:
            found = credentials(a.service)
            if not found:
                p.exit(2, 'Token not configured. Run again without --check.\n')
            print(f'Local token configured in {found[2]}. This does not verify remote access or licence acceptance.')
            return
        if not sys.stdin.isatty():
            p.exit(2, 'Run interactively to enter the token privately, or set the documented API_KEY environment variable.\n')
        host, filename, _ = SERVICES[a.service]
        target = Path.home() / filename
        if target.exists():
            answer = input(f'Replace existing {target}? [y/N] ')
            if answer.lower() != 'y':
                return
        token = getpass.getpass('Paste Personal Access Token (hidden; never send it in chat): ').strip()
        if not token or any(c.isspace() for c in token) or token.startswith('<'):
            raise ValueError('Token is empty or contains whitespace/placeholder text.')
        # User-only permissions on Unix; stored outside this Git repository.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            if os.name != 'nt':
                os.fchmod(stream.fileno(), 0o600)
            stream.write(f'url: {host}/api\nkey: {token}\n')
        print(f'Saved to {target}. Token is not printed. Next: accept dataset terms, then try a one-day download.')
    except (ValueError, OSError) as exc:
        p.exit(2, f'Configuration failed: {exc}\n')


if __name__ == '__main__':
    main()
