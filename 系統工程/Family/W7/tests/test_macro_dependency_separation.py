"""Verify immutable acceptance inputs separately from the changing live feed."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '系統工程/Family/W5'))
from verify_dependencies import verify

spec = importlib.util.spec_from_file_location('w7_macro_reader', ROOT / '系統工程/總經V70/P70-5.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
FEED = Path('系統工程/總經V70/V70_macro_latest.json')
FIXTURE = Path('系統工程/Family/W5/tests/fixtures/macro/V70_macro_W5_accepted.json')


class DependencySeparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        # Only the lock closure and live feed are needed; no family databases.
        home = ROOT / '系統工程/Family/W5'
        paths = {FEED}
        for filename in ('source_lock.json', 'dependency_lock.json'):
            lock = json.loads((home / filename).read_text())
            for row in lock['files'] if isinstance(lock, dict) else lock:
                paths.add(Path(row['path']))
        for path in paths:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)

    def test_current_tree_passes_original_115_checks(self):
        self.assertEqual(verify(self.root), 115)

    def test_daily_change_does_not_rewrite_acceptance_baseline(self):
        path = self.root / FEED
        feed = json.loads(path.read_text())
        feed['asOf'] = '2026-10-22T12:00:00Z'
        path.write_text(json.dumps(feed))
        self.assertEqual(verify(self.root), 115)
        self.assertEqual(reader.read_macro(self.root)['asOf'], feed['asOf'])

    def test_unready_live_feed_still_rejected_by_reader(self):
        path = self.root / FEED
        feed = json.loads(path.read_text())
        feed['verification']['ready'] = False
        path.write_text(json.dumps(feed))
        self.assertEqual(verify(self.root), 115)
        with self.assertRaisesRegex(ValueError, 'MACRO_FEED_NOT_READY'):
            reader.read_macro(self.root)

    def test_accepted_fixture_tampering_rejected(self):
        path = self.root / FIXTURE
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_HASH_MISMATCH'):
            verify(self.root)

    def test_code_tampering_rejected(self):
        lock = json.loads((ROOT / '系統工程/Family/W5/source_lock.json').read_text())
        path = self.root / lock['files'][0]['path']
        path.write_bytes(path.read_bytes() + b'\n# synthetic tamper\n')
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_HASH_MISMATCH'):
            verify(self.root)


if __name__ == '__main__':
    unittest.main()
