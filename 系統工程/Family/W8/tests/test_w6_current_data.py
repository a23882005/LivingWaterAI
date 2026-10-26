"""W6 current report data regressions, synthetic-only, no family funds."""
import importlib.util
from pathlib import Path
import unittest
from copy import deepcopy
from decimal import Decimal

PATH=Path(__file__).resolve().parents[1]/"w6_current_data.py"
SPEC=importlib.util.spec_from_file_location("test_w8_w6_data",PATH)
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
CLIENT="fam_"+"a"*32
SHA="2"*64

def baseline():
    source={
        "schema_version":"Family.W8.FormalReportSource.v1",
        "client_id":CLIENT,"member_alias":"Joseph",
        "source_db_sha256":SHA,
        "actual_position_records":[
            {"account_key":"IB","instrument_key":"VT","ticker":"VT",
             "label":"全球股票","quantity":"2","as_of_utc":"2026-10-24T00:00:00Z"}],
        "current_cash_by_account_currency":[
            {"account_key":"IB","currency":"TWD","reported_cash_minor":10000,
             "data_state":"VERIFIED","as_of_utc":"2026-10-24T00:00:00Z"}],
        "current_confirmed_target_details":[
            {"target_key":"MAIN","version_no":2,"allocations":[
                {"instrument_key":"VT","ticker":"VT","label":"全球股票",
                 "weight_units":700000},
                {"instrument_key":"QQQ","ticker":"QQQ","label":"科技成長",
                 "weight_units":300000}]}],
        "trade_authorization":"NONE"
    }
    source["digest"]=M._sha(source)
    market={"client_id":CLIENT,"source_db_sha256":SHA,"run_id":"ok-01",
            "market_as_of":"2026-10-26T12:00:00Z","data_provenance":"SOURCE_BACKED",
            "verified":True,
            "position_values_twd":[
                {"account_key":"IB","instrument_key":"VT","source_reference":"quote-2026",
                 "data_provenance":"SOURCE_BACKED","market_value_twd":"2000"}],
            "included_cash_accounts":[
                {"account_key":"IB","currency":"TWD","included":True}],
            "fx_to_twd":{}}
    engine={"client_id":CLIENT,"source_db_sha256":SHA,"run_id":"ok-01",
            "evaluation_at":"2026-10-26T13:00:00Z",
            "data_provenance":"SOURCE_BACKED","status":"OK",
            "trade_authorization":"NONE"}
    return source,market,engine

class W6CurrentDataTests(unittest.TestCase):
    def test_allocations_and_full_drift(self):
        source,market,engine=baseline()
        out=M.build_w6_current_data(source,market,engine)
        self.assertEqual(out["current_total_twd"],"2100")
        self.assertEqual({x["標的"] for x in out["drift"]},
                         {"VT","QQQ","TWD_CASH"})
        self.assertEqual(sum(Decimal(x["權重"]) for x in out["actual"]),Decimal(1))
        self.assertEqual(sum(Decimal(x["權重"]) for x in out["target"]),Decimal(1))
        self.assertEqual(sum(Decimal(x["差異TWD"]) for x in out["drift"]),Decimal(0))
        self.assertIn("RENDER_AND_QA_REQUIRED",out["report_content_state"])

    def test_lilian_long_term_target_is_selected(self):
        source,market,engine=baseline()
        source["current_confirmed_target_details"][0]["target_key"]="LONG_TERM"
        source["digest"]=M._sha({k:v for k,v in source.items() if k!="digest"})
        report=M.build_w6_current_data(source,market,engine)
        self.assertEqual(report["target_key"],"LONG_TERM")
        self.assertEqual(report["target_version"],2)
        self.assertEqual(len(report["target"]),2)

    def test_multiple_distinct_confirmed_purposes_are_not_arbitrarily_chosen(self):
        source,market,engine=baseline()
        other=deepcopy(source["current_confirmed_target_details"][0])
        other["target_key"]="LONG_TERM"
        source["current_confirmed_target_details"].append(other)
        source["digest"]=M._sha({k:v for k,v in source.items() if k!="digest"})
        with self.assertRaisesRegex(ValueError,"W6_MULTIPLE_CONFIRMED_TARGETS_REQUIRE_KEY"):
            M.build_w6_current_data(source,market,engine)

    def test_verified_operator_can_choose_exact_target_key(self):
        source,market,engine=baseline()
        other=deepcopy(source["current_confirmed_target_details"][0])
        other["target_key"]="LONG_TERM"
        other["version_no"]=3
        source["current_confirmed_target_details"].append(other)
        source["digest"]=M._sha({k:v for k,v in source.items() if k!="digest"})
        market["confirmed_target_key"]="LONG_TERM"
        report=M.build_w6_current_data(source,market,engine)
        self.assertEqual((report["target_key"],report["target_version"]),("LONG_TERM",3))

    def test_bad_target_key_cannot_select_anything(self):
        source,market,engine=baseline()
        market["confirmed_target_key"]="NOT_CONFIRMED"
        with self.assertRaisesRegex(ValueError,"W6_FINAL_TARGET_NOT_CONFIRMED"):
            M.build_w6_current_data(source,market,engine)

    def test_other_client_engine_rejected(self):
        s,m,e=baseline();e["client_id"]="fam_"+"b"*32
        with self.assertRaisesRegex(PermissionError,"W6_SAME_CLIENT"):
            M.build_w6_current_data(s,m,e)

    def test_no_quote_coverage_rejected(self):
        s,m,e=baseline();m["position_values_twd"]=[]
        with self.assertRaisesRegex(ValueError,"W6_POSITION_VALUATION_COVERAGE"):
            M.build_w6_current_data(s,m,e)

    def test_unknown_cash_rejected(self):
        s,m,e=baseline();s["current_cash_by_account_currency"][0]["data_state"]="NEEDS_REVIEW"
        s["digest"]=M._sha({k:v for k,v in s.items() if k!="digest"})
        with self.assertRaisesRegex(ValueError,"W6_LATEST_CASH_NOT_VERIFIED"):
            M.build_w6_current_data(s,m,e)

    def test_fake_source_hash_rejected(self):
        s,m,e=baseline();s["digest"]="0"*64
        with self.assertRaisesRegex(ValueError,"W6_VERIFIED_REPORT_SOURCE_REQUIRED"):
            M.build_w6_current_data(s,m,e)

    def test_no_confirmed_target_rejected(self):
        s,m,e=baseline();s["current_confirmed_target_details"]=[]
        s["digest"]=M._sha({k:v for k,v in s.items() if k!="digest"})
        with self.assertRaisesRegex(ValueError,"W6_FINAL_TARGET_NOT_CONFIRMED"):
            M.build_w6_current_data(s,m,e)

    def test_future_market_rejected(self):
        s,m,e=baseline();m["market_as_of"]="2026-10-28T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"W6_FUTURE_MARKET"):
            M.build_w6_current_data(s,m,e)

    def test_quantity_zero_closed_not_in_current(self):
        s,m,e=baseline();s["actual_position_records"]=[]
        s["digest"]=M._sha({k:v for k,v in s.items() if k!="digest"})
        m["position_values_twd"]=[]
        out=M.build_w6_current_data(s,m,e)
        self.assertEqual({x["代碼"] for x in out["actual"]},{"TWD_CASH"})
        self.assertEqual(out["current_total_twd"],"100")

if __name__=="__main__":unittest.main()
