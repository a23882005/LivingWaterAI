"""V70.3 production audit invariants: 23 unique indicators, no proxy promotion."""
import json
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT = pathlib.Path(os.environ.get("V703_AUDIT_PATH", ROOT / "data" / "24_macro_verification.json"))
FEED = pathlib.Path(os.environ.get("V703_FEED_PATH", ROOT / "data" / "V70_macro_latest.json"))
SIX = {"m06", "m03_qqq", "m03_spy", "m03_vt", "m16", "s05"}

class ProductionAuditIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        cls.feed = json.loads(FEED.read_text(encoding="utf-8"))

    def test_exact_contract_and_duplicate(self):
        items = self.audit["items"]
        self.assertEqual(len(items), 24)
        self.assertEqual(len(set(items) - {"s03"}), 23)
        self.assertEqual(items["s03"]["value"], items["m07"]["value"])
        self.assertEqual(items["s03"]["observation_date"], items["m07"]["observation_date"])

    def test_no_missing_or_stale_is_exported_as_verified(self):
        audit = self.audit["items"]
        active = self.feed["indicators"]
        for key, item in audit.items():
            if item["status"] != "OK":
                self.assertNotIn(key, active, f"unverified {key} entered production feed")
        for key, item in active.items():
            self.assertEqual(audit[key]["status"], "OK")
            self.assertEqual(item["dataDate"], audit[key]["observation_date"])
            self.assertEqual(item["value"], audit[key]["value"])

    def test_independent_progress_derived_not_hardcoded(self):
        items = {k: v for k, v in self.audit["items"].items() if k != "s03"}
        actual = {status: sum(x["status"] == status for x in items.values())
                  for status in ("OK", "STALE", "MISSING")}
        self.assertEqual(self.audit["independent_indicators"]["summary"], actual)
        self.assertEqual(sum(actual.values()), 23)
        missing = {k for k,v in items.items() if v["status"]=="MISSING"}
        # Strictly check unresolved IDs only when this audit has six missing.
        # After real runner evidence fixes a gap, the test remains valid.
        if actual["MISSING"] == 6:
            self.assertEqual(missing, SIX)

    def test_each_verified_has_numeric_date_and_provenance(self):
        import datetime
        import math
        today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
        for key, item in self.audit["items"].items():
            if item["status"] != "OK":
                continue
            with self.subTest(key=key):
                v = item["value"]
                self.assertIsInstance(v, (int,float))
                self.assertNotIsInstance(v, bool)
                self.assertTrue(math.isfinite(v))
                date = datetime.date.fromisoformat(item["observation_date"])
                self.assertLessEqual(date, today)
                self.assertTrue(item["source_url"].startswith("https://"))
                self.assertTrue(item["method"])

if __name__ == "__main__":
    unittest.main()
