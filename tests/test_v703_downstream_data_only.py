"""Current feed vetoes historical HTML scores; no browser or family DB needed."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
W8 = ROOT / '系統工程/Family/W8'
spec = importlib.util.spec_from_file_location('downstream_current_sources', W8 / 'on_demand_current_sources.py')
current = importlib.util.module_from_spec(spec)
spec.loader.exec_module(current)
spec = importlib.util.spec_from_file_location('downstream_reader', ROOT / '系統工程/總經V70/P70-5.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def data_only():
    return {'schema': 'V70.3/family-macro-feed-v3', 'asOf': '2026-11-11T00:00:00Z',
            'verification': {'ready': False, 'publicationReady': True},
            'publication': {'schema': 'V70.3/publication-state-v1', 'mode': 'DATA_ONLY',
                            'reason': 'CPI_YOY_BASE_PERIOD_MISSING', 'scoringAllowed': False,
                            'provisionalScoringAllowed':True,'calculationPolicy':'CPI_EXCLUDED_WITHIN_GROUP_MEAN',
                            'excludedIndicators':['m05']},
            'indicators': {'m05': {'value': None, 'status': 'OFFICIAL_UNAVAILABLE'}}}


class DownstreamDataOnly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / '系統工程/總經V70'
        self.folder.mkdir(parents=True)
        # An older HTML can contain apparently valid scores. It must never run.
        (self.folder / 'V70-3-27.html').write_text(
            '<script>window.v703Latest={macroSafety:99};throw Error("OLD_HTML_EXECUTED")</script>')

    def write_feed(self, feed):
        (self.folder / 'V70_macro_latest.json').write_text(json.dumps(feed))

    def test_family_reader_remains_strict(self):
        self.write_feed(data_only())
        with self.assertRaisesRegex(ValueError, 'MACRO_FEED_NOT_READY'):
            reader.read_macro(self.root)

    @unittest.skipUnless(shutil.which('node'), 'Node runtime required')
    def test_runtime_never_executes_old_html_for_non_scoring_feed(self):
        cases = [data_only(), data_only(), data_only(), data_only()]
        # Even inconsistent ready=true cannot override explicit scoring denial.
        cases[1]['verification']['ready'] = True
        cases[2]['verification']['ready'] = True
        cases[2]['publication'].pop('mode')
        # Other missing-data cases retain the strict block, not the CPI exception.
        cases[3].pop('publication')
        cases[3]['verification']['publicationReady'] = False
        for feed in cases:
            with self.subTest(feed=feed):
                self.write_feed(feed)
                out = current.run_original_v70(self.root, {'stock_percent': 80, 'bond_percent': 20},
                                               evaluation_at='2026-11-11T01:00:00Z')
                self.assertEqual(out['status'], 'V70_DATA_UNAVAILABLE')
                self.assertFalse(out['gates']['can_publish'])
                for field in ['tactical_percentages', 'macro_snapshot', 'original_latest', 'monetary_amounts']:
                    self.assertIsNone(out[field])
                self.assertEqual(out['local_reads'], [])

    def test_w5_projection_remains_strict(self):
        sys.path.insert(0, str(ROOT / '系統工程/Family/W5'))
        self.addCleanup(sys.path.pop, 0)
        from macro_source_bridge import project_macro
        from family_input import digest
        feed = data_only()
        with self.assertRaisesRegex(Exception, 'MACRO_NOT_READY'):
            project_macro({'payload': feed, 'digest': digest(feed)}, '2026-11-11T01:00:00Z')


if __name__ == '__main__':
    unittest.main()
