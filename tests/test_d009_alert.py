# 最後修改日期時間（台灣）：2026/10/16 02:30｜版本：D009-v2｜檔案：test_d009_alert.py
import datetime as dt
import gzip
import sys
from unittest.mock import patch
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro18_alert import evaluate, fresh_cpi_gap_evidence, ROOT, CPI_GAP_END


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

    def test_sixth_failure_realerts_but_fifth_does_not(self):
        report = {"items": {"m09": {"status": "STALE", "observation_date": "2026-10-01"}}}
        previous = {"indicators": {"m09": {"consecutive_failures": 4, "last_alert_date": "2026-10-14"}}}
        state, alerts = evaluate(report, previous, "2026-10-16")
        self.assertEqual(alerts, [])
        state, alerts = evaluate(report, state, "2026-10-17")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["count"], 6)

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


    def test_verified_cpi_gap_is_not_a_failure_and_keeps_other_alerts(self):
        now = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)
        attempt = {"result": "FAILED", "http_status": 200,
                   "error": "FRED_CSV: ValueError: Insufficient CPILFESL history; missing 2025-10"}
        item = {"status": "STALE", "attempt_result": "FAILED",
                "source_attempts": {"CPILFESL": [attempt]}}
        report = {"items": {"m05": item, "m02": {"status": "MISSING"}}}
        archived_series = ROOT / "data/audit/cpi_unavailable_20261110_series.csv.gz"
        with patch("macro18_alert.requests.get") as get:
            get.return_value.content = gzip.decompress(archived_series.read_bytes())
            evidence = fresh_cpi_gap_evidence(report, now)
        self.assertIsNotNone(evidence)
        state, alerts = evaluate(report, {}, "2026-11-15", cpi_evidence=evidence, now=now)
        self.assertEqual([a["indicator"] for a in alerts], ["m02"])
        self.assertEqual(item["status"], "STALE")
        self.assertEqual(state["indicators"]["m05"]["alert_disposition"],
                         "OFFICIAL_CPI_BASE_PERIOD_UNAVAILABLE")
        for evidence_arg, clock in ((None, now), (evidence, now + dt.timedelta(hours=26)),
                                    (evidence, CPI_GAP_END)):
            _, alerts = evaluate(report, {}, "2026-11-15", cpi_evidence=evidence_arg, now=clock)
            self.assertIn("m05", [a["indicator"] for a in alerts])
        item["source_attempts"]["CPILFESL"].append(dict(attempt, http_status=429))
        _, alerts = evaluate(report, {}, "2026-11-15", cpi_evidence=evidence, now=now)
        self.assertIn("m05", [a["indicator"] for a in alerts])


if __name__ == "__main__":
    unittest.main()
