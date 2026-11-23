from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from family03_target import whole_account_weights, confirmed_request, account_preview


class AccountTargetTests(unittest.TestCase):
    def test_share_of_total_and_retained_positions(self):
        self.assertEqual(whole_account_weights(800000, {"A":65, "B":35},
                                               {"Bond":150000, "Cash":50000}),
                         {"A":520000, "B":280000, "Bond":150000, "Cash":50000})

    def test_partial_or_ambiguous_weights(self):
        for stocks, retained in [({"A":60}, {"Bond":200000}),
                                 ({"A":100}, {"A":200000}),
                                 ({"A":100}, {"Cash":100000})]:
            with self.subTest(stocks=stocks, retained=retained), self.assertRaises(ValueError):
                whole_account_weights(800000, stocks, retained)

    @patch("family03_target.bond_tickers", return_value={"BNDW"})
    def test_preview_follows_the_existing_ledger_and_keeps_cash_without_a_ticker(self, _bonds):
        instruments = [
            {"instrument_key": key, "ticker": ticker, "instrument_type": kind}
            for key, ticker, kind in [("A","A","STOCK"),("B","BNDW","ETF"),("C",None,"CASH")]
        ]
        for key in ("MAIN", "LONG_TERM"):
            with self.subTest(key=key):
                versions = [{"target_key":key, "version_no":v,
                             "lifecycle_state":"CONFIRMED", "completeness_state":"COMPLETE"} for v in (1,4)]
                lines = [{"target_key":key,"version_no":4,"instrument_key":i,"weight_units":w}
                         for i,w in [("A",850000),("B",100000),("C",50000)]]
                snapshot = {"source_sha256":"db","tables":{"final_target_version":versions,
                            "final_target_allocation":lines,"portfolio_instrument":instruments}}
                args = (snapshot, {"方案":"方案一"}, {"A":100}, {"主軸":{"A":{}}}, Path("test-pool.xlsx"), "rev")
                result = account_preview(*args)
                self.assertEqual((result["原全帳戶目標"],result["原全帳戶版本"]),(key,4))
                self.assertEqual(result["保留部位"],{"BNDW":100000,"C":50000})
                versions.append(dict(versions[-1], version_no=5, lifecycle_state="DRAFT"))
                with self.assertRaisesRegex(ValueError, "最新全帳戶"):
                    account_preview(*args)
                versions[-1] = dict(versions[0], target_key="LONG_TERM" if key=="MAIN" else "MAIN")
                with self.assertRaisesRegex(ValueError, "兩組"):
                    account_preview(*args)

    def test_confirmation_is_bound_to_member_and_reviewed_values(self):
        preview = {"原全帳戶目標":"LONG_TERM", "每百萬單位":{"A":1000000}, "帳本摘要":"db1", "revision":"r1",
                   "allocations":[{"instrument_key":"A", "weight":"1"}]}
        core = {"identity":{"client_id":"mine"}, "loop_status":"FINAL_TARGET_CONFIRMED",
                "final_target_engine_result":{"formal_output_eligibility":{"eligible":True,"scope":"FULL"}},
                "route":{"decision":"C_ONLY"}, "work6_snapshot_id":"C-W6-test",
                "final_target":{"value_state":"KNOWN", "snapshot":{"confirmation_status":"CONFIRMED",
                    "positions":[{"ticker":"A","weight":{"value_state":"KNOWN","value":1}}]}}}
        request = dict(action="confirm_account", owner_confirmed=True, revision="r1",
                       source_sha256="db1", mentor_result=core)
        self.assertEqual(confirmed_request(preview,request,"mine")["record"]["allocations"],preview["allocations"])
        self.assertEqual(confirmed_request(preview,request,"mine")["record"]["target_key"],"LONG_TERM")
        for field,value in [("owner_confirmed",False),("revision","older"),("source_sha256","other")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                confirmed_request(preview,{**request,field:value},"mine")
        with self.assertRaises(ValueError):
            confirmed_request(preview,request,"another member")
        with self.assertRaises(ValueError):
            confirmed_request({**preview,"每百萬單位":{"B":1000000}},request,"mine")
