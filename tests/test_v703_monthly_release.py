# 最後修改日期：2026/11/07（台灣時間）｜檔案名稱：test_v703_monthly_release.py｜版本：固定歷史月資料與發布日測試樣本
"""V70-3-27 official monthly release-calendar gate acceptance tests (2026-10-18)."""
import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v703_daily_builder", ROOT / "scripts/build_daily_v703_site.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
SNAPSHOT = ROOT / "tests/fixtures/v703_20261022_snapshot.json"
MONTHLY_SIX = ("m04", "m05", "m15", "m18", "m19", "m20")


class OfficialMonthlyReleaseTests(unittest.TestCase):
    def test_missing_cpi_base_is_diagnosed_without_accepting_stale_value(self):
        from copy import deepcopy
        item = {"label": "Core CPI YoY", "status": "STALE", "value": 2.565841,
                "observation_date": "2026-09-01", "source_url": "https://fred.stlouisfed.org/series/CPILFESL",
                "method": "historical cache", "retrieval_error": "All FRED sources failed",
                "source_attempts": {"CPILFESL": [
                    {"result": "FAILED", "error": "FRED_CSV: ValueError: Insufficient CPILFESL history; missing 2025-10"}]}}
        before = deepcopy(item)
        diagnostics = builder._scoring_source_diagnostics({"m05": item}, set(builder.SCORING_IDS)-{"m05"})
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "CPI_YOY_BASE_PERIOD_MISSING")
        self.assertEqual(diagnostics[0]["missingBasePeriods"], ["2025-10"])
        self.assertEqual(item, before)
        now = dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc)
        self.assertIn("m05: status STALE", builder._validate("m05", item, now.date(), {}, now))

    def test_diagnostics_do_not_reuse_old_errors_for_valid_cpi_or_infer_outage(self):
        valid = {"m05": {"status": "OK", "error": "Insufficient CPILFESL history; missing 2025-10"}}
        self.assertEqual(builder._scoring_source_diagnostics(valid, set(builder.SCORING_IDS)), [])
        invalid = {"m05": {"status": "STALE", "error": "HTTP request timed out"}}
        result = builder._scoring_source_diagnostics(invalid, set(builder.SCORING_IDS)-{"m05"})
        self.assertEqual(result[0]["code"], "SCORING_INPUT_INVALID")
        self.assertNotIn("missingBasePeriods", result[0])

    def setUp(self):
        # The existing archived fixture contains September observations and the
        # corresponding official release calendar. Never read mutable production
        # inputs in this historical boundary test: October jobs are correctly fresh.
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.observed = {
            key: dict(snapshot["indicators"][key],
                      observation_date=snapshot["indicators"][key]["dataDate"],
                      source_url=snapshot["indicators"][key]["source"])
            for key in MONTHLY_SIX
        }
        self.now = dt.datetime(2026, 10, 18, 8, 15, tzinfo=dt.timezone.utc)
        self.today = self.now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        self.calendar_data = snapshot["monthlyReleaseCalendar"]
        self.calendar_data["checked_at_utc"] = "2026-10-18T08:00:00Z"
        self.fixture_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture_directory.cleanup)
        fixture_path = pathlib.Path(self.fixture_directory.name) / "calendar.json"
        fixture_path.write_text(json.dumps(self.calendar_data), encoding="utf-8")
        self.calendar = builder._official_release_calendar(fixture_path, self.today)

    def test_frozen_six_observations_and_calendar_are_september(self):
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                self.assertEqual(self.observed[key]["observation_date"], "2026-09-01")
                self.assertEqual(self.observed[key]["status"], "OK")
                self.assertEqual(self.calendar[key]["observation_month"], "2026-09")

    def test_new_october_observation_passes_at_september_expiry(self):
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                release = dt.datetime.fromisoformat(
                    self.calendar[key]["next_release_at_utc"].replace("Z", "+00:00"))
                current = dict(self.observed[key], observation_date="2026-10-01")
                self.assertEqual(builder._validate(
                    key, current, release.date(), self.calendar, release), [])

    def test_official_latest_september_observations_pass_after_day_46(self):
        self.assertEqual(set(self.calendar), set(MONTHLY_SIX))
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                self.assertEqual((self.today-dt.date(2026,9,1)).days, 47)
                self.assertEqual(builder._validate(key, self.observed[key],
                                                   self.today, self.calendar, self.now), [])

    def test_after_next_report_release_same_previous_month_must_fail(self):
        for key in MONTHLY_SIX:
            release = dt.datetime.fromisoformat(self.calendar[key]["next_release_at_utc"].replace("Z","+00:00"))
            with self.subTest(key=key):
                # One second before real release the existing latest report is still good.
                before = release-dt.timedelta(seconds=1)
                self.assertFalse(builder._validate(key, self.observed[key],
                                 before.date(), self.calendar, before))
                # At release timestamp a stale dataset must block deployment.
                errors = builder._validate(key, self.observed[key],
                                           release.date(), self.calendar, release)
                self.assertTrue(any("monthly data stale" in x for x in errors), errors)

    def test_66_day_latest_month_is_valid_until_official_november_release(self):
        # 2026/11/06: September is 66 calendar days old, but the official
        # October CPI and jobs reports have not yet been released at this time.
        # This regression guards the real 18/22 -> 22/22 V70 incident.
        now = dt.datetime(2026, 11, 6, 4, 0, tzinfo=dt.timezone.utc)
        day = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        self.assertEqual((day - dt.date(2026, 9, 1)).days, 66)
        for key in ("m05", "m18", "m19", "m20"):
            with self.subTest(key=key):
                item = dict(self.observed[key], status="OK", observation_date="2026-09-01")
                self.assertEqual(builder._validate(key, item, day, self.calendar, now), [])

    def test_unverified_month_and_no_calendar_fail_closed(self):
        data = dict(self.observed["m04"], observation_date="2026-08-01")
        self.assertTrue(builder._validate("m04", data, self.today, self.calendar, self.now))
        self.assertTrue(builder._validate("m04", self.observed["m04"], self.today, {}, self.now))

    def test_calendar_rejects_untrusted_source_and_future_verification(self):
        data=json.loads(json.dumps(self.calendar_data))
        data["items"]["m04"]["calendar_source_url"]="https://phishing.invalid/ism"
        with tempfile.TemporaryDirectory() as directory:
            p=pathlib.Path(directory)/"calendar.json"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"untrusted"):
                builder._official_release_calendar(p,self.today)
            data["items"]["m04"]["calendar_source_url"]="https://www.ismworld.org/calendar"
            data["checked_at_utc"]="2027-01-01T00:00:00Z"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"verification date"):
                builder._official_release_calendar(p,self.today)


if __name__ == "__main__":
    unittest.main()
