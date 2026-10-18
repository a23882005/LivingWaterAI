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
CALENDAR = ROOT / "data/v703_official_monthly_release_calendar.json"
CORE = ROOT / "data/18_macro_verification.json"
MONTHLY_SIX = ("m04", "m05", "m15", "m18", "m19", "m20")


class OfficialMonthlyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.observed = json.loads(CORE.read_text(encoding="utf-8"))["items"]
        self.now = dt.datetime(2026, 10, 18, 8, 15, tzinfo=dt.timezone.utc)
        self.today = self.now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        self.calendar = builder._official_release_calendar(CALENDAR, self.today)

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

    def test_unverified_month_and_no_calendar_fail_closed(self):
        data = dict(self.observed["m04"], observation_date="2026-08-01")
        self.assertTrue(builder._validate("m04", data, self.today, self.calendar, self.now))
        self.assertTrue(builder._validate("m04", self.observed["m04"], self.today, {}, self.now))

    def test_calendar_rejects_untrusted_source_and_future_verification(self):
        data=json.loads(CALENDAR.read_text(encoding="utf-8"))
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
