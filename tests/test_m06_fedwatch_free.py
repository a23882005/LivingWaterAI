"""m06 pure-function QA: date bounds, direction, probability, meeting boundary.
Research-only. Live acceptance still requires same-date CME evidence and multi-day runs.
"""
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("m06_probe",ROOT/"scripts/probe_m06_fedwatch_free.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TODAY=dt.date(2026,10,14)

def sample(date="2026-10-13", meeting="2027-10-27", probabilities=None):
    return {"target_source":"fred","trade_date":date,"current_target":"3.75%-4.00%",
      "meetings":[{"date":meeting,"probabilities":probabilities or
        {"3.75%-4.00%":50,"4.00%-4.25%":50}}]}

class M06BoundaryQA(unittest.TestCase):
    def test_positive_quarters_and_normalization(self):
        result=mod.calculate(sample(probabilities={"4.00%-4.25%":50.0,"4.25%-4.50%":49.9}),TODAY)
        self.assertAlmostEqual(result["m06_expected_rate_change_quarters"],1.4995,places=3)
        self.assertEqual(result["status"],"CANDIDATE_NEEDS_REVIEW")
    def test_negative_quarters(self):
        result=mod.calculate(sample(probabilities={"3.25%-3.50%":100}),TODAY)
        self.assertAlmostEqual(result["m06_expected_rate_change_quarters"],-2)
    def test_holiday_settlement_age_5_allowed(self):
        self.assertEqual(mod.calculate(sample(date="2026-10-09"),TODAY)["status"],"CANDIDATE_NEEDS_REVIEW")
    def test_stale_and_future_rejected(self):
        for date in ("2026-10-08","2026-10-15"):
            with self.subTest(date=date),self.assertRaises(ValueError):
                mod.calculate(sample(date=date),TODAY)
    def test_nearest_meeting_window(self):
        result=mod.calculate({"target_source":"fred","trade_date":"2026-10-13",
          "current_target":"3.75%-4.00%","meetings":[
          {"date":"2027-09-22","probabilities":{"3.75%-4.00%":100}},
          {"date":"2027-10-27","probabilities":{"4.00%-4.25%":100}}
          ]},TODAY)
        self.assertEqual(result["meeting_date"],"2027-10-27")
    def test_meeting_outside_45_days_rejected(self):
        with self.assertRaises(ValueError):
            mod.calculate(sample(meeting="2027-07-01"),TODAY)
    def test_invalid_probabilities_and_rate_interval(self):
        for p in ({"3.75%-4.00%":95},{"3.75%-4.00%":101},{"3.75%-4.50%":100}):
            with self.subTest(p=p),self.assertRaises(ValueError):
                mod.calculate(sample(probabilities=p),TODAY)
    def test_non_fred_target_rejected(self):
        a=sample();a["target_source"]="unspecified"
        with self.assertRaises(ValueError):mod.calculate(a,TODAY)

if __name__=="__main__":unittest.main()
