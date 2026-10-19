import csv
import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

MODULE = Path(__file__).parents[1] / "scripts/monthly_research/update_sp500_daily.py"
spec = importlib.util.spec_from_file_location("update_sp500_daily", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class UpdateSp500DailyTests(unittest.TestCase):
    def sample_fred(self):
        rows = ["observation_date,SP500"]
        for i in range(1100):
            d = date(2020, 1, 1).toordinal() + i
            rows.append(f"{date.fromordinal(d).isoformat()},{3000 + i / 10}")
        rows += ["2026-10-19,7000", "2026-10-20,7001", "2026-10-21,."]
        return ("\n".join(rows) + "\n").encode()

    def test_parse_fred_validates_schema_and_filters_after_as_of(self):
        values = mod.parse_fred_csv(self.sample_fred(), date(2026, 10, 19))
        self.assertEqual(values[-1], ("2026-10-19", "7000"))
        self.assertFalse(any(d > "2026-10-19" for d, _ in values))

    def test_update_merges_and_writes_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sp500.csv"
            result = mod.update(path, date(2026, 10, 19), lambda: self.sample_fred())
            self.assertEqual(result["status"], "FRESH")
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[-1]["date"], "2026-10-19")
            self.assertEqual(rows[-1]["series_id"], "FRED:SP500")
            self.assertIn("excludes dividends", result["measure"])

    def test_failed_fetch_keeps_valid_cache_and_marks_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sp500.csv"
            mod.update(path, date(2026, 10, 19), lambda: self.sample_fred())
            before = path.read_bytes()
            result = mod.update(path, date(2026, 10, 19), lambda: (_ for _ in ()).throw(OSError("offline")))
            self.assertEqual(result["status"], "CACHE_FALLBACK")
            self.assertIn("offline", result["fallback_reason"])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
