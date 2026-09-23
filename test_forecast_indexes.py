"""Offline index fixtures; do not contact providers or decode/download GRIB."""
import json
import unittest
from datetime import date
from unittest.mock import Mock

import gfs_archive
import ifs_open
from download_region import parser


class ForecastIndexTests(unittest.TestCase):
    def test_gfs_subset_offsets_and_coupled_messages(self):
        a = parser().parse_args(['gfs-archive', '--variables', 'UGRD', 'VGRD'])
        index = ('1:0:d=2025010100:TMP:2 m above ground:anl:\n'
                 '2.1:100:d=2025010100:UGRD:10 m above ground:anl:\n'
                 '2.2:100:d=2025010100:VGRD:10 m above ground:anl:\n'
                 '3:200:d=2025010100:PRMSL:mean sea level:anl:\n')
        selected, ranges = gfs_archive.select_fields(index, a)
        self.assertEqual(len(selected), 2)
        self.assertEqual(ranges, [(100, 199)])
        a.variables = ['PRMSL']
        self.assertEqual(gfs_archive.select_fields(index, a)[1], [(200, None)])

    def test_ifs_parameters_and_lengths(self):
        a = parser().parse_args(['ifs-open', '--variables', '10u'])
        index = '\n'.join(json.dumps(r) for r in [
            dict(param='2t', levtype='sfc', _offset=0, _length=100),
            dict(param='10u', levtype='sfc', _offset=100, _length=150),
            dict(param='u', levtype='pl', levelist='850', _offset=250, _length=100)])
        self.assertEqual(ifs_open.select_fields(index, a)[1], [(100, 249)])
        a.group, a.variables, a.levels = 'pressure', ['u'], [850, 925]
        with self.assertRaisesRegex(ValueError, 'pressure levels absent'):
            ifs_open.select_fields(index, a)

    def test_ifs_stream_candidates_and_index_extension(self):
        urls = ifs_open.candidates(date(2025, 1, 1), 6, 24)
        self.assertEqual(len(urls), 2)
        self.assertIn('/scda/20250101060000-24h-scda-fc.grib2', urls[1])
        self.assertTrue(ifs_open.index_url(urls[1]).endswith('-fc.index'))

    def test_ifs_404_tries_other_stream(self):
        client = Mock()
        response404, response200 = Mock(), Mock()
        for response in (response404, response200):
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=None)
        response404.status_code = 404
        response200.status_code, response200.text = 200, 'index'
        client.get.side_effect = [response404, response200]
        url, text = gfs_archive.locate(client, ifs_open, date(2025, 1, 1), 6, 24)
        self.assertIn('/scda/', url)
        self.assertEqual(text, 'index')


if __name__ == '__main__':
    unittest.main()
