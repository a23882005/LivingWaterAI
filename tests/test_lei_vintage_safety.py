"""Guard against promoting a cross-release-vintage LEI comparison as official YoY."""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "data" / "lei_cross_vintage_candidate_unverified.json"
AUDIT = ROOT / "data" / "24_macro_verification.json"

class LEIVintageSafety(unittest.TestCase):
    def test_mixed_release_vintages_are_diagnostic_only(self):
        item = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        self.assertEqual(item["indicator"], "m16")
        self.assertEqual(item["status"], "UNVERIFIED_MIXED_RELEASE_VINTAGES")
        self.assertNotEqual(item["latest"]["release_date"], item["year_earlier"]["release_date"])
        self.assertEqual(item["latest"]["observation_date"], "2026-08-01")
        self.assertEqual(item["year_earlier"]["observation_date"], "2025-08-01")
        expected = round((item["latest"]["index"]/item["year_earlier"]["index"]-1)*100, 2)
        self.assertAlmostEqual(item["illustrative_cross_vintage_yoy_percent"], expected)
        self.assertTrue(item["latest"]["source_url"].startswith("https://www.conference-board.org/"))
        self.assertTrue(item["year_earlier"]["source_url"].startswith("https://www.conference-board.org/"))
    def test_candidate_never_passes_v70_final_gate(self):
        candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        self.assertNotEqual(candidate["status"], "OK")
        # The diagnostic file is never an authorized verified override.
        overrides = json.loads((ROOT / "data" / "verified_overrides.json").read_text(encoding="utf-8"))
        self.assertNotIn("m16", overrides)

if __name__ == "__main__":
    unittest.main()
