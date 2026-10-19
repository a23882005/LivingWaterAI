import csv
import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

MODULE = Path(__file__).parents[1] / "scripts/monthly_research/macro_safety_monthly.py"
spec = importlib.util.spec_from_file_location("macro_safety_monthly", MODULE)
msm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(msm)


class MonthlyResearchTests(unittest.TestCase):
    def daily(self):
        rows = []
        for day, score, imputed in [
            ("2026-01-05", "60", ""), ("2026-01-06", "61", ""),
            ("2026-02-05", "64", "m07"), ("2026-03-05", "58", ""),
        ]:
            rows.append({"observation_date": day, "run_timestamp_utc": day + "T12:00:00Z",
                         "v70_version": "V70-formal", "source_commit": "abc123",
                         "health_score": score, "score_status": "VALID",
                         "neutral_imputed_items": imputed, "raw_m07": "NA" if imputed else "7"})
        parsed = msm.read_daily_from_rows(rows)
        self.assertEqual(next(r for r in parsed if r["_date"] == "2026-02-05")["raw_m07"], "NA")
        return parsed

    def prices(self):
        return [(date(2026, 1, 5), 100.0), (date(2026, 2, 5), 110.0),
                (date(2026, 3, 5), 105.0), (date(2026, 4, 6), 120.0),
                (date(2026, 5, 5), 125.0), (date(2026, 6, 5), 130.0)]

    def test_real_months_slope_na_and_maturity(self):
        rows = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 4, 7), "2026-04-07T12:00:00Z")
        self.assertEqual([r["snapshot_month"] for r in rows], ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(rows[0]["health_score"], "60")  # later Jan record is after cutoff
        self.assertEqual(float(rows[1]["elapsed_months"]), 1.0)
        self.assertEqual(float(rows[1]["slope_points_per_month"]), 4.0)
        self.assertEqual(rows[1]["neutral_imputed_items"], "m07")
        self.assertEqual(rows[1]["return_status"], "PENDING")
        self.assertEqual(rows[1]["sp500_forward_3m_return_pct"], "")
        self.assertEqual(rows[0]["return_status"], "REALIZED")

    def test_quarterly_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "quarterly.csv"
            path.write_text("date,quarterly_score\n2020-01-01,50\n", encoding="utf-8")
            with self.assertRaisesRegex(msm.DataError, "Quarterly research files"):
                msm.read_daily(path)

    def test_csv_reader_preserves_literal_na(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "daily.csv"
            path.write_text(
                "observation_date,run_timestamp_utc,v70_version,source_commit,health_score,score_status,neutral_imputed_items,raw_m07\n"
                "2026-02-05,2026-02-05T12:00:00Z,V70,abc,64,VALID,m07,NA\n",
                encoding="utf-8")
            rows = msm.read_daily(path)
            self.assertEqual(rows[0]["raw_m07"], "NA")
            self.assertEqual(rows[0]["neutral_imputed_items"], "m07")

    def test_month_key_unique_and_atomic_rerun(self):
        rows = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 4, 7), "2026-04-07T12:00:00Z")
        self.assertEqual(len({row["snapshot_month"] for row in rows}), len(rows))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "monthly.csv"
            msm.write_atomic(path, rows)
            first = path.read_bytes()
            msm.write_atomic(path, rows)
            self.assertEqual(path.read_bytes(), first)
            with path.open(newline="", encoding="utf-8") as f:
                saved = list(csv.DictReader(f))
            self.assertEqual(len(saved), len(rows))

    def test_merge_preserves_timestamp_history_and_realized_return(self):
        original = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 4, 7),
                                     "2026-04-07T12:00:00Z")
        rerun = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 2, 6),
                                  "2026-04-08T12:00:00Z")
        merged = msm.merge_monthly(rerun, original)
        self.assertEqual(len(merged), 3)  # missing newer months remain preserved
        self.assertEqual(merged[0]["run_timestamp_utc"], original[0]["run_timestamp_utc"])
        self.assertEqual(merged[0]["sp500_forward_3m_return_pct"], "20")
        self.assertEqual(merged[0]["return_status"], "REALIZED")

    def test_delayed_retry_uses_actual_observation_date(self):
        rows = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 1, 6),
                                 "2026-01-06T12:00:00Z", retry_month="2026-01")
        self.assertEqual(rows[0]["snapshot_date"], "2026-01-06")
        self.assertEqual(rows[0]["health_score"], "61")

    def test_existing_delayed_snapshot_refreshes_same_day_only(self):
        original = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 1, 6),
                                     "2026-01-06T12:00:00Z", retry_month="2026-01")
        corrected_rows = [
            {"observation_date": "2026-01-06", "run_timestamp_utc": "2026-01-06T13:00:00Z",
             "v70_version": "V70-formal", "source_commit": "corrected",
             "health_score": "62", "score_status": "VALID", "neutral_imputed_items": ""},
            {"observation_date": "2026-01-07", "run_timestamp_utc": "2026-01-07T12:00:00Z",
             "v70_version": "V70-formal", "source_commit": "later",
             "health_score": "70", "score_status": "VALID", "neutral_imputed_items": ""},
        ]
        daily = msm.read_daily_from_rows(self.daily() + corrected_rows)
        refreshed = msm.build_monthly(
            daily, self.prices(), 5, date(2026, 1, 7), "2026-01-07T13:00:00Z",
            pinned_snapshot_dates={"2026-01": date(2026, 1, 6)})
        merged = msm.merge_monthly(refreshed, original)
        self.assertEqual(merged[0]["snapshot_date"], "2026-01-06")
        self.assertEqual(merged[0]["health_score"], "62")
        self.assertEqual(merged[0]["source_commit"], "corrected")

    def test_merge_refresh_keeps_corrected_delayed_snapshot(self):
        original = msm.build_monthly(self.daily(), [], 5, date(2026, 1, 6),
                                     "2026-01-06T12:00:00Z", retry_month="2026-01")
        corrected_rows = [
            {"observation_date": "2026-01-06", "run_timestamp_utc": "2026-01-06T13:00:00Z",
             "v70_version": "V70-formal", "source_commit": "corrected",
             "health_score": "62", "score_status": "VALID", "neutral_imputed_items": ""},
            {"observation_date": "2026-01-07", "run_timestamp_utc": "2026-01-07T12:00:00Z",
             "v70_version": "V70-formal", "source_commit": "later",
             "health_score": "70", "score_status": "VALID", "neutral_imputed_items": ""},
        ]
        daily = msm.read_daily_from_rows(self.daily() + corrected_rows)
        refreshed_snapshot = msm.build_monthly(
            daily, [], 5, date(2026, 1, 7), "2026-01-07T13:00:00Z",
            pinned_snapshot_dates={"2026-01": date(2026, 1, 6)})
        merged = msm.merge_and_refresh_monthly(
            refreshed_snapshot, original, self.prices(), date(2026, 4, 7))
        self.assertEqual(merged[0]["snapshot_date"], "2026-01-06")
        self.assertEqual(merged[0]["health_score"], "62")
        self.assertEqual(merged[0]["source_commit"], "corrected")
        self.assertEqual(merged[0]["return_status"], "REALIZED")
        self.assertEqual(merged[0]["sp500_forward_3m_return_pct"], "20")

    def test_existing_delayed_snapshot_keeps_date_and_matures_return(self):
        original = msm.build_monthly(self.daily(), self.prices(), 5, date(2026, 1, 6),
                                     "2026-01-06T12:00:00Z", retry_month="2026-01")
        self.assertEqual(original[0]["return_status"], "PENDING")
        refreshed = msm.refresh_existing_returns(original, self.prices(), date(2026, 4, 7))
        self.assertEqual(refreshed[0]["snapshot_date"], "2026-01-06")
        self.assertEqual(refreshed[0]["health_score"], "61")
        self.assertEqual(refreshed[0]["return_status"], "REALIZED")
        self.assertEqual(refreshed[0]["sp500_forward_3m_return_pct"], "20")

    def test_monthly_scores_and_slopes_collect_without_publishing_unlicensed_prices(self):
        rows = msm.build_monthly(self.daily(), [], 5, date(2026, 4, 7), "2026-04-07T12:00:00Z")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["slope_points_per_month"], "4")
        self.assertEqual(rows[1]["return_status"], "SOURCE_PENDING")
        self.assertEqual(rows[1]["sp500_start_close"], "")

    def test_calendar_month_elapsed_duration(self):
        self.assertEqual(msm._elapsed_calendar_months(date(2026, 1, 5), date(2026, 2, 5)), 1.0)
        self.assertEqual(msm._elapsed_calendar_months(date(2026, 1, 5), date(2026, 3, 5)), 2.0)
        self.assertAlmostEqual(msm._elapsed_calendar_months(date(2026, 1, 5), date(2026, 2, 6)),
                               1 + 1 / 28, places=8)


if __name__ == "__main__":
    unittest.main()
