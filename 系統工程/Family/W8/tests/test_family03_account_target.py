from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from family03_target import whole_account_weights, confirmed_request


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

    def test_confirmation_is_bound_to_member_and_reviewed_values(self):
        preview = {"每百萬單位":{"A":1000000}, "帳本摘要":"db1", "revision":"r1",
                   "allocations":[{"instrument_key":"A", "weight":"1"}]}
        core = {"identity":{"client_id":"mine"}, "loop_status":"FINAL_TARGET_CONFIRMED",
                "final_target_engine_result":{"formal_output_eligibility":{"eligible":True,"scope":"FULL"}},
                "route":{"decision":"C_ONLY"}, "work6_snapshot_id":"C-W6-test",
                "final_target":{"value_state":"KNOWN", "snapshot":{"confirmation_status":"CONFIRMED",
                    "positions":[{"ticker":"A","weight":{"value_state":"KNOWN","value":1}}]}}}
        request = dict(action="confirm_account", owner_confirmed=True, revision="r1",
                       source_sha256="db1", mentor_result=core)
        self.assertEqual(confirmed_request(preview,request,"mine")["record"]["allocations"],preview["allocations"])
        for field,value in [("owner_confirmed",False),("revision","older"),("source_sha256","other")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                confirmed_request(preview,{**request,field:value},"mine")
        with self.assertRaises(ValueError):
            confirmed_request(preview,request,"another member")
        with self.assertRaises(ValueError):
            confirmed_request({**preview,"每百萬單位":{"B":1000000}},request,"mine")
