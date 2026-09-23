import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date
import numpy as np
import xarray as xr
from download_region import monthly, point_area, region, spatial_subset, parser, api_jobs, wb_download, subset_file


class RegionalSelectionTests(unittest.TestCase):
    def fixture(self, descending=False):
        lat = np.arange(35, 37.51, .25)
        if descending:
            lat = lat[::-1]
        lon = np.arange(119, 121.51, .25)
        values = lat[:, None] * 1000 + lon[None, :]
        return xr.Dataset({'t': (('latitude', 'longitude'), values)},
                          coords={'latitude': lat, 'longitude': lon})

    def test_nearest_user_coordinate_both_latitude_orders(self):
        for descending in [True, False]:
            selected = spatial_subset(self.fixture(descending), 36.3, 120.33, point=True)
            self.assertEqual(float(selected.latitude.item()), 36.25)
            self.assertEqual(float(selected.longitude.item()), 120.25)
            self.assertEqual(selected.t.item(), 36370.25)
            self.assertTrue(8 < selected.distance_km.item() < 10)

    def test_radius_masks_rectangle_corners(self):
        selected = spatial_subset(self.fixture(), 36.3, 120.33, radius_km=50)
        outside = selected.distance_km > 50
        self.assertTrue(bool(outside.any()))
        self.assertTrue(bool(selected.t.where(outside).isnull().all()))
        self.assertTrue(bool(selected.t.where(~outside).notnull().any()))

    def test_cyclic_longitude_nearest(self):
        ds = xr.Dataset({'u': (('latitude', 'longitude'), [[1., 2., 3.]])},
                        coords={'latitude': [0.], 'longitude': [0., 180., 359.75]})
        out = spatial_subset(ds, 0., -.1, point=True)
        self.assertEqual(out.longitude.item(), 0.)

    def test_no_grid_in_small_circle(self):
        with self.assertRaisesRegex(ValueError, 'No grid'):
            spatial_subset(self.fixture(), 36.3, 120.33, radius_km=1)

    def test_leap_day_and_month_boundaries(self):
        self.assertEqual(list(monthly('2020-02-28', '2020-03-01')),
                         [(date(2020, 2, 28), date(2020, 2, 29)),
                          (date(2020, 3, 1), date(2020, 3, 1))])

    def test_invalid_regions(self):
        for args in [(91, 120, 50), (36, 181, 50), (36, 120, -1), (36, float('nan'), 50), (0, 179.9, 50)]:
            with self.assertRaises(ValueError):
                region(*args)

    def test_cds_nearest_and_three_variable_groups(self):
        a = parser().parse_args(['era5', '--start', '2020-02-28', '--end', '2020-03-01', '--point', '--group', 'all'])
        jobs = list(api_jobs(a))
        self.assertEqual(len(jobs), 5)
        self.assertEqual(jobs[0][1]['day'], ['28', '29'])
        for _, req, _, _ in jobs:
            self.assertEqual(req['area'], [36.25, 120.25, 36.25, 120.25])
        self.assertEqual(point_area(36.3, 120.33, .25), [36.25, 120.25, 36.25, 120.25])

    def test_cams_analysis_is_not_forecast(self):
        a = parser().parse_args(['cams-analysis', '--start', '2020-01-01', '--end', '2020-01-01',
                                '--variables', 'total_column_carbon_monoxide'])
        req = list(api_jobs(a))[0][1]
        self.assertEqual(req['type'], 'analysis')
        self.assertEqual(req['leadtime_hour'], '0')

    def test_different_hours_never_reuse_cached_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self.fixture().expand_dims(time=np.array(
                ['2020-01-01T00', '2020-01-01T06'], dtype='datetime64[h]'))
            for hour in [0, 6]:
                args = parser().parse_args(['wb', '--point', '--start', '2020-01-01',
                                            '--end', '2020-01-01', '--hours', str(hour),
                                            '--variables', 't', '--out', tmp, '--csv'])
                with patch('xarray.open_zarr', return_value=base.copy()):
                    wb_download(args)
            outputs = list(Path(tmp).glob('*.nc'))
            self.assertEqual(len(outputs), 2)
            actual_hours = set()
            for output in outputs:
                with xr.open_dataset(output) as ds:
                    actual_hours.add(int(ds.time.dt.hour.item()))
                self.assertTrue(output.with_suffix('.csv').is_file())
            self.assertEqual(actual_hours, {0, 6})
            # A completed rerun must not contact the source, including for CSV.
            with patch('xarray.open_zarr', side_effect=AssertionError('Unexpected network access')):
                wb_download(args)

    def test_subset_preserves_both_point_and_radius_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'original.nc'
            self.fixture().to_netcdf(original)
            out = Path(tmp) / 'out'
            for mode in [['--point'], ['--radius-km', '50']]:
                args = parser().parse_args(['subset', '--input', str(original), '--out', str(out), *mode])
                subset_file(args)
            results = list(out.glob('*.nc'))
            self.assertEqual(len(results), 2)
            selections = set()
            for result in results:
                with xr.open_dataset(result) as ds:
                    selections.add(ds.attrs['spatial_selection'])
            self.assertEqual(selections, {'circle', 'nearest_grid'})


if __name__ == '__main__':
    unittest.main()
