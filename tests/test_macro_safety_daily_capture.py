import csv
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

MODULE = Path(__file__).parents[1] / "scripts/capture_v703_daily_snapshot.py"
spec = importlib.util.spec_from_file_location("capture_v703_daily_snapshot", MODULE)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class DailyCaptureTests(unittest.TestCase):
    def feed(self):
        indicators = {f"m{i:02d}": {"value": i if i != 22 else None, "status": "OK",
                                     "dataDate": "2026-10-18", "source": f"https://example.com/{i}"}
                      for i in range(1, 29)}
        return {"schema": capture.EXPECTED_FEED_SCHEMA, "asOf": "2026-10-18T23:00:00Z",
                "batchDateTaipei": "2026-10-19", "verification": {
                    "ready": True, "valid": 26, "totalRequired": 26,
                    "independentIndicators": 25, "transportIndicators": 28,
                    "requiredScoringIndicators": 22, "requiredScoringIndicatorsValidated": 22},
                "indicators": indicators,
                "sourceSnapshot": {"macro18": "a", "macro8": "b", "wallstreet5": "c"},
                "monthlyReleaseCalendar": {"schema": "calendar"}}

    def browser_snapshot(self, feed):
        return {"verified": True, "canPublish": True,
                "sourceBatch": {"asOf": feed["asOf"], "sourceSnapshot": feed["sourceSnapshot"]},
                "latest": {"macroSafety": 73.25, "ruleVersion": "V70.3-test",
                           "calculatedAt": "2026-10-18T23:00:02Z", "syntheticInputs": False,
                           "status": "AUTO_ALLOCATION_CANDIDATE_PENDING_BACKTEST",
                           "dataValidation": {"allMacroValuesPresent": True,
                                              "allDatesAndSourcesValid": True}}}

    def test_verified_final_score_raw_na_and_source_data(self):
        feed = self.feed()
        record = capture.build_record(feed, self.browser_snapshot(feed), "2026-10-18T23:01:00Z",
                                      "commit123", "feedsha")
        self.assertEqual(record["observation_date"], "2026-10-19")
        self.assertEqual(record["health_score"], "73.25")
        self.assertEqual(record["score_status"], "FORMAL_VALID")
        self.assertEqual(record["neutral_imputed_items"], "")
        self.assertEqual(json.loads(record["raw_indicator_values_json"])["m22"], "NA")
        self.assertEqual(json.loads(record["indicator_provenance_json"])["m22"]["source"], "https://example.com/22")

    def test_gate_rejects_incomplete_or_mismatched_browser_capture(self):
        feed = self.feed()
        feed["verification"]["requiredScoringIndicatorsValidated"] = 21
        with self.assertRaises(capture.CaptureError):
            capture.build_record(feed, self.browser_snapshot(feed), "2026-10-18T23:01:00Z", "c", "h")
        feed = self.feed()
        snapshot = self.browser_snapshot(feed)
        snapshot["sourceBatch"]["asOf"] = "2026-10-17T23:00:00Z"
        with self.assertRaises(capture.CaptureError):
            capture.build_record(feed, snapshot, "2026-10-18T23:01:00Z", "c", "h")

    def test_formal_archive_rejects_demo_invalid_score_and_source_mismatch(self):
        import copy
        feed=self.feed()
        mutations=[('demo',lambda s:s['latest'].update(syntheticInputs=True)),
                   ('demo_status',lambda s:s['latest'].update(status='DEMO_SYNTHETIC')),
                   ('blocked',lambda s:s.update(canPublish=False)),
                   ('unverified',lambda s:s.update(verified=False)),
                   ('missing_values',lambda s:s['latest']['dataValidation'].update(allMacroValuesPresent=False)),
                   ('invalid_dates',lambda s:s['latest']['dataValidation'].update(allDatesAndSourcesValid=False)),
                   ('lineage',lambda s:s['sourceBatch'].update(sourceSnapshot={})),
                   ('nan',lambda s:s['latest'].update(macroSafety=float('nan'))),
                   ('overflow',lambda s:s['latest'].update(macroSafety=101))]
        for name,mutate in mutations:
            with self.subTest(case=name):
                snapshot=copy.deepcopy(self.browser_snapshot(feed));mutate(snapshot)
                with self.assertRaises(capture.CaptureError):
                    capture.build_record(feed,snapshot,'2026-10-18T23:01:00Z','c','h')
                print('ARCHIVE_CASE',name,'PASS',flush=True)

    def test_conflicting_record_preserves_existing_archive_bytes(self):
        record=capture.build_record(self.feed(),self.browser_snapshot(self.feed()),'2026-10-18T23:01:00Z','c','h')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'daily.csv';capture.append_idempotent(path,record);before=path.read_bytes()
            with self.assertRaises(capture.CaptureError):
                capture.append_idempotent(path,dict(record,health_score='1'))
            self.assertEqual(path.read_bytes(),before)

    def test_daily_archive_append_is_idempotent_and_keeps_old_rows(self):
        feed = self.feed()
        record = capture.build_record(feed, self.browser_snapshot(feed), "2026-10-18T23:01:00Z", "commit123", "feedsha")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "macro_safety_daily.csv"
            self.assertTrue(capture.append_idempotent(path, record))
            first = path.read_bytes()
            repeated = dict(record, run_timestamp_utc="2026-10-18T23:10:00Z")
            self.assertFalse(capture.append_idempotent(path, repeated))
            self.assertEqual(path.read_bytes(), first)
            newer_feed = dict(feed, asOf="2026-10-19T09:00:00Z", batchDateTaipei="2026-10-19")
            newer_snapshot = self.browser_snapshot(newer_feed)
            newer = capture.build_record(newer_feed, newer_snapshot, "2026-10-19T09:01:00Z", "commit123", "feedsha2")
            self.assertTrue(capture.append_idempotent(path, newer))
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["daily_record_id"], record["daily_record_id"])


if __name__ == "__main__":
    unittest.main()
