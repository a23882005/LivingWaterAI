import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from qp_verified_window_producer import (
    OK, UNKNOWN, git_blob_sha, reconstruct_raw_rows, reconstruct_ib_snapshot, build_wealth,
    calculate_qp, produce_one,
)


def write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "Date": r["Date"], "Open": r["Close"], "High": r["Close"], "Low": r["Close"],
                "Close": r["Close"], "Adj Close": r["Close"], "Volume": 1000,
                "Dividends": r.get("Dividends", 0), "Stock Splits": r.get("Stock Splits", 0),
            })


class ProducerTests(unittest.TestCase):
    def _spec(self, path, start, end):
        data = path.read_bytes()
        return {
            "source_blob_sha": git_blob_sha(data),
            "verified_window_start": start,
            "verified_window_end": end,
            "bar_date_alignment_verified": True,
            "event_coverage_verified": True,
            "calendar_verified": True,
            "timestamp_evidence_verified": True,
            "expected_row_count": None,
            "event_count_verified": 0,
            "max_event_value_relative_error": 0,
            "event_value_relative_error_tolerance": 0.005,
            "verification_source": "unit-test",
        }

    def test_git_blob_sha_changes_with_content(self):
        self.assertNotEqual(git_blob_sha(b"a"), git_blob_sha(b"b"))

    def test_reconstruct_split_adjusted_cache_to_raw_old_share_basis(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            # Cache is back-adjusted for a future 10:1 split: pre-split close/dividend divided by 10.
            rows = [
                {"Date":"2024-06-07","Close":"120","Dividends":"0.004"},
                {"Date":"2024-06-10","Close":"12","Stock Splits":"10"},
                {"Date":"2024-06-11","Close":"12.1","Dividends":"0.01"},
            ]
            write_csv(p, rows)
            spec = self._spec(p, "2024-06-07", "2024-06-11")
            spec["event_count_verified"] = 3
            r = reconstruct_raw_rows(p, spec)
            self.assertEqual(r.status, OK)
            self.assertEqual(str(r.value[0].raw_close), "1200")
            self.assertEqual(str(r.value[0].raw_dividend_old_share), "0.040")
            self.assertEqual(str(r.value[1].raw_close), "12")
            self.assertEqual(str(r.value[1].split_ratio), "10")

    def test_ib_snapshot_reconstructs_split_back_adjusted_close_with_old_share_cash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ib.json"
            obj = {
                "contract":"V82_QP_IB_SNAPSHOT_v1",
                "price_basis":"SPLIT_BACK_ADJUSTED_CLOSE",
                "cash_dividend_basis":"OLD_SHARE_GROSS",
                "time":["2024-06-06T13:30:00Z","2024-06-07T13:30:00Z","2024-06-10T13:30:00Z"],
                "close":[11.6,12.0,12.1],
                "corp_actions":[
                    {"type":"CashDividends","date":"20240607","value":"4.0","currency":"USD"},
                    {"type":"Splits","date":"20240610","value":"10.0"},
                ],
            }
            p.write_text(json.dumps(obj), encoding="utf-8")
            spec = self._spec(p,"2024-06-06","2024-06-10")
            spec["event_count_verified"]=2
            r = reconstruct_ib_snapshot(p,spec)
            self.assertEqual(r.status,OK)
            self.assertEqual(r.value[0].raw_close, r.value[0].raw_close.__class__("116"))
            self.assertEqual(r.value[1].raw_close, r.value[1].raw_close.__class__("120"))
            self.assertEqual(str(r.value[1].raw_dividend_old_share),"4.0")
            self.assertEqual(str(r.value[2].raw_close),"12.1")
            self.assertEqual(str(r.value[2].split_ratio),"10.0")

    def test_ib_snapshot_supports_split_effective_date_override_after_suspension(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ib.json"
            obj = {
                "contract":"V82_QP_IB_SNAPSHOT_v1",
                "price_basis":"SPLIT_BACK_ADJUSTED_CLOSE",
                "cash_dividend_basis":"OLD_SHARE_GROSS",
                "time":["2025-06-10T01:00:00Z","2025-06-18T01:00:00Z"],
                "close":[47.1625,47.57],
                "corp_actions":[
                    {"type":"Splits","date":"20250611","value":"4.0"},
                ],
            }
            p.write_text(json.dumps(obj), encoding="utf-8")
            spec = self._spec(p,"2025-06-10","2025-06-18")
            spec["event_count_verified"]=1
            spec["corporate_action_effective_date_overrides"]={"Splits|2025-06-11":"2025-06-18"}
            r = reconstruct_ib_snapshot(p,spec)
            self.assertEqual(r.status,OK)
            self.assertEqual(str(r.value[0].raw_close),"188.65000")
            self.assertEqual(str(r.value[1].raw_close),"47.57")
            self.assertEqual(str(r.value[1].split_ratio),"4.0")
            self.assertEqual(r.evidence["corporate_action_effective_date_overrides"],
                             {"Splits|2025-06-11":"2025-06-18"})

    def test_source_blob_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            write_csv(p, [{"Date":"2024-01-02","Close":"100"},{"Date":"2024-01-03","Close":"101"}])
            s = self._spec(p, "2024-01-02", "2024-01-03")
            s["source_blob_sha"] = "0" * 40
            r = reconstruct_raw_rows(p, s)
            self.assertEqual(r.status, UNKNOWN)
            self.assertEqual(r.reason, "SOURCE_BLOB_SHA_MISMATCH")

    def test_unverified_gate_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            write_csv(p, [{"Date":"2024-01-02","Close":"100"},{"Date":"2024-01-03","Close":"101"}])
            s = self._spec(p, "2024-01-02", "2024-01-03")
            s["event_coverage_verified"] = False
            r = reconstruct_raw_rows(p, s)
            self.assertEqual(r.status, UNKNOWN)
            self.assertEqual(r.reason, "EVENT_COVERAGE_NOT_VERIFIED")

    def test_qp_deterministic_on_long_synthetic_window(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            d = date(2021, 11, 1)
            end = date(2026, 10, 30)
            v = 100.0
            rows=[]
            while d <= end:
                if d.weekday() < 5:
                    j=len(rows)
                    v *= 1.0004 if j % 13 < 7 else 0.9989
                    if j > 1050:
                        v *= 0.9988
                    rows.append({"Date":d.isoformat(),"Close":f"{v:.10f}"})
                d += timedelta(days=1)
            write_csv(p, rows)
            s = self._spec(p, rows[0]["Date"], rows[-1]["Date"])
            raw = reconstruct_raw_rows(p, s)
            self.assertEqual(raw.status, OK)
            wealth = build_wealth(raw.value)
            q = calculate_qp(raw.value, wealth)
            self.assertEqual(q.status, OK)
            self.assertGreaterEqual(float(q.value["qP"]), 0)
            self.assertLessEqual(float(q.value["qP"]), 100)
            self.assertGreaterEqual(q.value["reference_points"], 24)

    def test_expected_qp_regression_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/"x.csv"
            d=date(2021,11,1);end=date(2026,10,30);v=100.0;rows=[]
            while d<=end:
                if d.weekday()<5:
                    j=len(rows);v*=1.0002 if j%9<5 else 0.9991
                    rows.append({"Date":d.isoformat(),"Close":f"{v:.10f}"})
                d+=timedelta(days=1)
            write_csv(p,rows)
            s=self._spec(p,rows[0]["Date"],rows[-1]["Date"])
            s["source_path"]="x.csv"
            first=produce_one(root,s)
            self.assertEqual(first.status,OK)
            s["expected_qp"]="999"
            bad=produce_one(root,s)
            self.assertEqual(bad.status,UNKNOWN)
            self.assertEqual(bad.reason,"EXPECTED_QP_REGRESSION_MISMATCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
