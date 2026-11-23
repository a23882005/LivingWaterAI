import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from qp_verified_window_producer import OK, produce_manifest

REPO_ROOT = HERE.parents[4]
MANIFEST = HERE / "v82_qp_verified_window_manifest_20261031.json"


class RealManifestReplayTests(unittest.TestCase):
    def test_all_manifest_symbols_replay_exactly(self):
        out = produce_manifest(REPO_ROOT, MANIFEST)
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]
        self.assertEqual(set(out["items"]), set(expected))
        bad = {k:v for k,v in out["items"].items() if v["status"] != OK}
        self.assertEqual(bad, {}, bad)
        for symbol, result in out["items"].items():
            self.assertAlmostEqual(float(result["value"]["qP"]), float(expected[symbol]["expected_qp"]), places=6)
            self.assertGreaterEqual(result["value"]["reference_points"], 24)
            self.assertEqual(result["value"]["max_consecutive_missing_periods"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
