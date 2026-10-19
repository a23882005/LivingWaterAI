import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "scripts/monthly_research/build_bank_macro_monthly.py"
spec = importlib.util.spec_from_file_location("build_bank_macro_monthly", MODULE)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)


class BankMacroMonthlyTests(unittest.TestCase):
    def test_joins_each_bank_to_latest_known_forecast_and_preserves_na(self):
        banks = []
        for i, name in enumerate(bm.INSTITUTIONS):
            banks.extend([
                {"forecast_id": f"old-{i}", "institution": name,
                 "forecast_target_index": "S&P 500", "forecast_value": "5000",
                 "forecast_target_date": "2026-12-31", "evidence_date": "2026-01-05",
                 "publication_date": "", "forecast_horizon_days": "360",
                 "source_url": "https://example.com/old", "verification_status": "PIT_PENDING"},
                {"forecast_id": f"new-{i}", "institution": name,
                 "forecast_target_index": "S&P 500", "forecast_value": "6000",
                 "forecast_target_date": "2027-12-31", "evidence_date": "2026-10-06",
                 "publication_date": "2026-10-06", "forecast_horizon_days": "441",
                 "source_url": "https://example.com/new", "verification_status": "PIT_PENDING"},
            ])
        monthly = [{"snapshot_month": "2026-10", "snapshot_date": "2026-10-19",
                    "health_score": "56.934", "score_status": "FORMAL_VALID",
                    "previous_snapshot_date": "", "previous_health_score": "",
                    "sp500_start_date": "2026-10-16", "sp500_start_close": "5000",
                    "slope_points_per_month": "", "sp500_forward_3m_return_pct": "",
                    "return_status": "SOURCE_PENDING"}]
        rows = bm.build_rows(banks, monthly)
        self.assertEqual(len(rows), 5)
        self.assertEqual({r["institution"] for r in rows}, set(bm.INSTITUTIONS))
        self.assertTrue(all(r["forecast_id"].startswith("new-") for r in rows))
        self.assertTrue(all(r["macro_health_score"] == "56.934" for r in rows))
        self.assertTrue(all(r["forecast_implied_return_pct"] == "20" for r in rows))
        self.assertTrue(all(r["sp500_snapshot_date"] == "2026-10-16" for r in rows))
        self.assertTrue(all(r["forecast_publication_date"] != "NA" for r in rows))
        self.assertTrue(all(r["macro_slope_points_per_month"] == "NA" for r in rows))
        self.assertTrue(all(r["macro_return_status"] == "SOURCE_PENDING" for r in rows))

    def test_forecast_after_snapshot_is_not_used_and_empty_bank_is_na(self):
        banks = [{"forecast_id": "future", "institution": bm.INSTITUTIONS[0],
                  "forecast_target_index": "S&P 500", "forecast_value": "7000",
                  "forecast_target_date": "2027-12-31", "evidence_date": "2026-10-20",
                  "publication_date": "", "forecast_horizon_days": "400",
                  "source_url": "https://example.com", "verification_status": "PIT_PENDING"}]
        monthly = [{"snapshot_month": "2026-10", "snapshot_date": "2026-10-19",
                    "health_score": "56.934", "score_status": "FORMAL_VALID",
                    "previous_snapshot_date": "", "previous_health_score": "",
                    "sp500_start_date": "", "sp500_start_close": "",
                    "slope_points_per_month": "", "sp500_forward_3m_return_pct": "",
                    "return_status": "SOURCE_PENDING"}]
        rows = bm.build_rows(banks, monthly)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["forecast_id"], "NA")
        self.assertEqual(rows[0]["forecast_value"], "NA")
        self.assertEqual(rows[0]["forecast_implied_return_pct"], "NA")
        self.assertEqual(rows[0]["sp500_snapshot_close"], "NA")


    def test_implied_return_rejects_invalid_or_nonpositive_prices(self):
        self.assertEqual(bm._implied_return("8100", "7200"), "12.5")
        self.assertEqual(bm._implied_return("8100", ""), "NA")
        self.assertEqual(bm._implied_return("8100", "0"), "NA")


if __name__ == "__main__":
    unittest.main()
