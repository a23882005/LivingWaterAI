# 最後修改日期時間（台灣）：2026/10/16 02:30｜版本：D009-v2｜檔案：test_d009_alert.py
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro18_alert import evaluate


class TestD009Alerts(unittest.TestCase):
    def test_first_failure_and_same_day_suppression(self):
        report = {"items": {"m02": {"status": "MISSING", "observation_date": None},
                            "m01": {"status": "OK", "observation_date": "2026-10-15"},
                            "s03": {"status": "OK", "observation_date": "2026-10-15"}}}
        state, alerts = evaluate(report, {}, "2026-10-16")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["indicator"], "m02")
        state2, alerts2 = evaluate(report, state, "2026-10-16")
        self.assertEqual(alerts2, [])
        self.assertEqual(state2["indicators"]["m02"]["consecutive_failures"], 2)

    def test_third_failure_and_recovery_reset(self):
        report = {"items": {"m09": {"status": "STALE", "observation_date": "2026-10-01"}}}
        prior = {"indicators": {"m09": {"consecutive_failures": 2, "last_alert_date": "2026-10-14"}}}
        state, alerts = evaluate(report, prior, "2026-10-16")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["count"], 3)
        report["items"]["m09"]["status"] = "OK"
        state2, alerts2 = evaluate(report, state, "2026-10-17")
        self.assertEqual(alerts2, [])
        self.assertEqual(state2["indicators"]["m09"]["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
