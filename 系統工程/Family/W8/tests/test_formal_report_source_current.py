"""W8 W6 report source regression on synthetic family records only."""
import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "formal_report_source.py"
SPEC = importlib.util.spec_from_file_location("w8_formal_source_current", FILE)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
CLIENT = "fam_" + "a"*32

def sample():
    return {
        "schema_version": "Family.W5.W1Snapshot.v1",
        "client_id": CLIENT,
        "source_sha256": "sha_fixture", "payload_digest": "fixture_payload",
        "identity": {"client_id": CLIENT, "family_alias": "Joseph"},
        "tables": {
            "portfolio_account": [{"client_id": CLIENT, "account_key": "IB"}],
            "portfolio_instrument": [{"client_id": CLIENT, "instrument_key": "VT",
                                      "ticker": "VT", "instrument_label": "全球股票"}],
            "portfolio_position": [{"client_id":CLIENT,"account_key":"IB","instrument_key":"VT",
                                    "as_of_utc":"2026-10-20T00:00:00Z",
                                    "quantity_decimal":"2","cost_state":"UNKNOWN"}],
            "cash_balance_snapshot": [
                {"client_id":CLIENT,"account_key":"IB","currency_code":"USD",
                 "cash_snapshot_id":"older","version":1,"as_of_utc":"2026-10-20T00:00:00Z",
                 "reported_cash_minor":200,"data_state":"VERIFIED"},
                {"client_id":CLIENT,"account_key":"IB","currency_code":"USD",
                 "cash_snapshot_id":"newest","version":2,"as_of_utc":"2026-10-22T00:00:00Z",
                 "reported_cash_minor":500,"data_state":"NEEDS_REVIEW"},
            ],
            "final_target_version":[
                {"client_id":CLIENT,"target_key":"MAIN","version_no":1,
                 "lifecycle_state":"CONFIRMED","completeness_state":"COMPLETE"},
                {"client_id":CLIENT,"target_key":"MAIN","version_no":2,
                 "lifecycle_state":"DRAFT","completeness_state":"COMPLETE"},
            ],
            "final_target_allocation":[
                {"client_id":CLIENT,"target_key":"MAIN","version_no":1,
                 "instrument_key":"VT","weight_units":1000000,"allocation_state":"ACCEPTED"},
                {"client_id":CLIENT,"target_key":"MAIN","version_no":2,
                 "instrument_key":"VT","weight_units":1000000,"allocation_state":"ACCEPTED"},
            ],
            "portfolio_snapshot_item":[],
        }
    }

class ReportSourceTests(unittest.TestCase):
    def test_one_latest_cash_per_account(self):
        result = MOD.build_report_source(sample(), account="JO", expected_client_id=CLIENT)
        self.assertEqual(len(result["current_cash_by_account_currency"]),1)
        self.assertEqual(result["current_cash_by_account_currency"][0]["reported_cash_minor"],500)
        self.assertEqual(result["current_cash_by_account_currency"][0]["data_state"],"NEEDS_REVIEW")
        self.assertEqual(len(result["cash_reports"]),2)

    def test_draft_never_replaces_approved_target(self):
        result = MOD.build_report_source(sample(), account="JO", expected_client_id=CLIENT)
        detail=result["current_confirmed_target_details"]
        self.assertEqual(len(detail),1)
        self.assertEqual(detail[0]["version_no"],1)
        self.assertEqual(detail[0]["allocations"][0]["weight_fraction"],"1")
        self.assertFalse(result["reporting_flags"]["w6_v16_renderer_data_complete"])

    def test_incomplete_newest_confirmed_does_not_revert_to_old_target(self):
        data=sample()
        old=data["tables"]["final_target_version"][0]
        newest=dict(old,version_no=3,lifecycle_state="CONFIRMED",
                    completeness_state="INCOMPLETE")
        data["tables"]["final_target_version"].append(newest)
        result=MOD.build_report_source(data,account="JO",expected_client_id=CLIENT)
        self.assertFalse(result["reporting_flags"]["confirmed_target_available"])
        self.assertEqual(result["current_confirmed_target_details"],[])

    def test_pending_rows_in_latest_confirmation_reject_current_target(self):
        data=sample()
        data["tables"]["final_target_allocation"].append({
            "client_id":CLIENT,"target_key":"MAIN","version_no":1,
            "instrument_key":"QQQ","weight_units":100000,
            "allocation_state":"PENDING"})
        result=MOD.build_report_source(data,account="JO",expected_client_id=CLIENT)
        self.assertFalse(result["reporting_flags"]["confirmed_target_available"])

    def test_other_family_rejected(self):
        with self.assertRaisesRegex(PermissionError,"REPORT_IDENTITY_MISMATCH"):
            MOD.build_report_source(sample(),account="AR",expected_client_id=CLIENT)

    def test_target_not_accepted_not_confirmed(self):
        data=sample()
        data["tables"]["final_target_allocation"][0]["allocation_state"]="PENDING"
        r=MOD.build_report_source(data,account="JO",expected_client_id=CLIENT)
        self.assertFalse(r["reporting_flags"]["confirmed_target_available"])

    def test_digest_responds_to_newer_cash(self):
        a=sample()
        b=sample()
        b["tables"]["cash_balance_snapshot"][1]["reported_cash_minor"]=600
        self.assertNotEqual(
            MOD.build_report_source(a,account="JO",expected_client_id=CLIENT)["digest"],
            MOD.build_report_source(b,account="JO",expected_client_id=CLIENT)["digest"])

if __name__=="__main__":
    unittest.main()
