import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import numpy as np
import xarray as xr

from accounts import credentials, cds_client, explain_api_error
from date_selection import boundary, normalize_dates, resolve_latest, catalogue_bounds, latest_gfs
from download_region import parser, api_jobs, api_download, subset_file


class DateTests(unittest.TestCase):
    def args(self, *items):
        a = parser().parse_args(list(items))
        normalize_dates(a)
        return a

    def test_calendar_precision_and_leap_year(self):
        for value, first, last in [('2025', '2025-01-01', '2025-12-31'),
                                   ('2024-02', '2024-02-01', '2024-02-29'),
                                   ('2025-02', '2025-02-01', '2025-02-28'),
                                   ('2025-03-04', '2025-03-04', '2025-03-04')]:
            self.assertEqual(boundary(value), first)
            self.assertEqual(boundary(value, end=True), last)

    def test_bad_dates_fail(self):
        for value in ['2025-2', '2025-02-29', '0000', '2025-13', '2025/01/01', '25', '2025-01-01x']:
            with self.assertRaises(ValueError):
                boundary(value)

    def test_whole_period_and_mixed_range(self):
        a = self.args('era5', '--date', '2024-02')
        jobs = list(api_jobs(a))
        self.assertEqual(jobs[0][1]['day'], [f'{day:02}' for day in range(1, 30)])
        a = self.args('era5', '--start', '2025', '--end', '2026-02')
        self.assertEqual((a.start, a.end), ('2025-01-01', '2026-02-28'))
        for items in [('era5', '--date', '2025', '--start', '2024'),
                      ('era5', '--start', '2026', '--end', '2025'), ('era5', '--end', '2025')]:
            with self.assertRaises(ValueError):
                self.args(*items)

    def test_latest_uses_common_surface_pressure_coverage(self):
        a = self.args('era5', '--start', '2025', '--group', 'all')
        with patch('date_selection.catalogue_bounds', side_effect=[('1940-01-01', '2026-09-17'),
                                                                  ('1940-01-01', '2026-09-16')]):
            resolve_latest(a)
        self.assertEqual(a.end, '2026-09-16')
        self.assertEqual(list(api_jobs(a))[-1][1]['day'][-1], '16')

    def test_explicit_end_offline_and_future_start_rejected(self):
        a = self.args('era5', '--date', '2025')
        with patch('date_selection.catalogue_bounds', side_effect=AssertionError('network')):
            resolve_latest(a)
        a = self.args('era5', '--start', '2027')
        with patch('date_selection.catalogue_bounds', return_value=('1940-01-01', '2026-09-17')):
            with self.assertRaisesRegex(ValueError, 'later than latest'):
                resolve_latest(a)

    def test_catalogue_failure_never_guesses_today(self):
        for data in [{}, {'extent': {'temporal': {'interval': [['1940-01-01', None]]}}}]:
            stream = io.BytesIO(json.dumps(data).encode())
            with patch('date_selection.urlopen', return_value=stream):
                with self.assertRaisesRegex(ValueError, 'no date was guessed'):
                    catalogue_bounds('https://example.com/catalogue')
        with patch('date_selection.urlopen', side_effect=TimeoutError):
            with self.assertRaises(ValueError):
                catalogue_bounds('https://example.com/catalogue')

    def test_gfs_latest_checks_every_requested_lead(self):
        a = self.args('gfs', '--start', '2026', '--hours', '0', '6', '--lead-hours', '0', '24')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.headers = {'Content-Type': 'application/octet-stream'}
        with patch('date_selection.urlopen', return_value=response) as opened:
            result = latest_gfs(a)
        self.assertRegex(result, r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual(opened.call_count, 4)

    def test_local_subset_end_only_and_partial_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.nc'
            xr.Dataset({'t': (('time', 'latitude', 'longitude'), np.ones((3, 1, 1)))},
                       coords={'time': np.array(['2025-02-01', '2025-02-28', '2025-03-01'], dtype='datetime64[D]'),
                               'latitude': [36.25], 'longitude': [120.25]}).to_netcdf(source)
            a = self.args('subset', '--input', str(source), '--end', '2025-02', '--point',
                          '--lat', '36.25', '--lon', '120.25', '--out', tmp)
            subset_file(a)
            with xr.open_dataset(next(Path(tmp).glob('*_subset_*.nc'))) as result:
                self.assertEqual(result.sizes['time'], 2)


class AccountTests(unittest.TestCase):
    def test_standard_config_and_separate_services(self):
        with tempfile.TemporaryDirectory() as tmp, patch('accounts.Path.home', return_value=Path(tmp)), patch.dict('os.environ', {}, clear=True):
            Path(tmp, '.cdsapirc').write_text('url: https://cds.climate.copernicus.eu/api\nkey: fake-test-token\n')
            self.assertEqual(credentials('cds')[1], 'fake-test-token')
            self.assertIsNone(credentials('ads'))
            with patch.dict('os.environ', {'CDS_API_KEY': 'env-test-token'}):
                self.assertEqual(credentials('cds')[1], 'env-test-token')
            Path(tmp, '.adsapirc').write_text('url: https://cds.climate.copernicus.eu/api\nkey: wrong-service\n')
            with self.assertRaisesRegex(ValueError, 'CDS versus ADS'):
                credentials('ads')

    def test_missing_credentials_and_denied_request_show_help_without_secret(self):
        with patch('accounts.credentials', return_value=None), patch('accounts.account_notice') as notice:
            with self.assertRaisesRegex(ValueError, 'not configured'):
                cds_client('cds', ['reanalysis-era5-single-levels'])
            self.assertTrue(notice.call_args.kwargs['open_browser'])
        error = Exception('SECRET-MUST-NOT-PRINT')
        error.response = Mock(status_code=403)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch('accounts.account_notice'):
            self.assertTrue(explain_api_error(error, 'cds', []))
        self.assertNotIn('SECRET', output.getvalue())

    def test_completed_api_files_need_no_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = parser().parse_args(['era5', '--start', '2025-01-01', '--end', '2025-01-01', '--out', tmp])
            class Client:
                def retrieve(self, ds, req, target):
                    Path(target).write_bytes(b'fake-test-file')
            with patch('download_region.cds_client', return_value=Client()):
                api_download(a)
            with patch('download_region.cds_client', side_effect=AssertionError('credentials queried')):
                api_download(a)


if __name__ == '__main__':
    unittest.main()
