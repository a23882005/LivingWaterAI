"""Synthetic account-scoped Menu04 receipts and earlier V75 references."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("holdings_html_fixture", HERE / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
W6 = F.load("holdings_on_demand_test", "on_demand_w6.py")


def seal(c):
    q, r = c["request"], c["result"]
    r["request_digest"] = F.A.digest(q)
    for row in r["analysis_result"]["positions"]:
        d = row["current_analysis"]
        d["delivery_digest"] = F.A.digest({k: v for k, v in d.items() if k != "delivery_digest"})
    wr = r["work9_request"]
    wr["request_digest"] = r["request_digest"]
    wr["positions"] = [{"instrument_id": x["instrument_id"], "native_component_delivery": deepcopy(x["current_analysis"])}
                       for x in r["analysis_result"]["positions"]]
    w9 = r["work9_result"]
    w9["source_request_digest"] = F.A.digest(wr)
    w9["request_digest"] = r["request_digest"]
    w9["result_digest"] = F.A.digest({k: v for k, v in w9.items() if k != "result_digest"})
    r["mentor"]["source_result_digest"] = F.A.digest(w9)
    for item in r["mentor"].get("items", []):
        item["source_result_digest"] = w9["result_digest"]
    rr = r["recommendation_report"]
    rr["digest"] = F.A.digest({k: v for k, v in rr.items() if k != "digest"})
    r["manifest_digest"] = F.A.digest(r["manifest"])
    r["report_digest"] = F.A.digest({k: v for k, v in r.items() if k not in ("report_digest", "source_sha256")})


def documents(raw, structural):
    return {name: {"source_id": "SYNTHETIC_REFERENCE_" + name,
                   "original_text": json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                   "sha256": sha256((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()}
            for name, value in (("raw", raw), ("structural", structural))}


def case():
    base = F.case()
    q = deepcopy(base["request"])
    q["analysis_permission"] = "ANALYZE_ONLY"
    q["run_id"] = "synthetic-account-holdings"
    common = {"client_id": F.CLIENT, "run_id": q["run_id"], "owner": deepcopy(q["owner"]),
              "source_db_sha256": base["source"]["source_db_sha256"]}
    holding = {"quantity": "4", "quantity_state": "KNOWN", "observed_at": F.ASOF}
    delivery = {"owner": deepcopy(q["owner"]), "symbol": "KEEP", "holding": deepcopy(holding)}
    row = {"instrument_id": "KEEP", "symbol": "KEEP", "owner": deepcopy(q["owner"]),
           "status": "ANALYSIS_PARTIAL", "holding": holding, "current_analysis": delivery,
           "market": {"observed_date": "2026-10-29", "observed_close": "7.125"}}
    wreq = {**deepcopy(common), "positions": []}
    work9 = {**deepcopy(common), "full_canonical_deployment_complete": False, "trade_action": "NO_TRADE",
             "items": [{"item_id": "KEEP", "asset_id": "KEEP", "native_component_delivery": delivery}]}
    mentor = {**deepcopy(common), "full_native_deployment_mentor": False, "broker_execution_allowed": False,
              "production": "HOLD", "trade_action": "NO_TRADE", "items": [{"item_id": "KEEP", "asset_id": "KEEP"}]}
    recommendation = {"client_id": F.CLIENT, "run_id": q["run_id"], "positions_returned": 1,
                      "full_native_deployment_complete": False, "trade_action": "NO_TRADE", "rows": [
                          {"instrument_id": "KEEP", "symbol": "KEEP", "quantity": "4",
                           "proposed_existing_asset_redeployment_amount": None, "proposed_new_external_buy_amount": "0",
                           "native_cash_trial_buy_amount": None, "new_external_currency": "TWD"}]}
    bond = {**deepcopy(common), "canonical_result": None, "full_native_canonical_complete": False,
            "trade_action": "NO_TRADE", "status": "ORIGINAL_SOURCE_WITH_GAPS", "requested_instruments": ["KEEP"],
            "targets": {"KEEP": {}, "NEW": {}}, "structural_state": {
                "run_id": q["run_id"], "broker_account_id": q["owner"]["account"], "currency": q["owner"]["currency"],
                "gap_calculations": [{"asset_id": "KEEP", "remaining_target_gap_amount": {
                    "status": "KNOWN", "value": {"amount": "12", "currency": "TWD"}},
                    "eligible_existing_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}}}]}}
    result = {"schema_version": "Family.W8.HoldingsAnalysisReport.v1", **common, "status": "ANALYSIS_PARTIAL",
              "snapshot_digest": F.A.digest(q["client_snapshot"]["payload"]), "source_data_provenance": "SOURCE_BACKED",
              "analysis_result": {"scope": "SELECTED_ACCOUNT__NOT_ALL_HOUSEHOLD", "positions": [row],
                                  "coverage": {"requested": 1, "returned": 1}},
              "deployment_status": {"full_native_canonical_complete": False}, "canonical_result": None,
              "trade_authorization": "NONE", "trade_action": "NO_TRADE", "work9_request": wreq,
              "work9_result": work9, "mentor": mentor, "recommendation_report": recommendation,
              "manifest": [], "native_bond_source": bond}
    c = {"source": base["source"], "request": q, "result": result}
    seal(c)
    raw = {"schema": "Synthetic.RawBondObservation.v1", "client_id": F.CLIENT,
           "run_id": "synthetic-earlier-reference", "evaluation_at": "2026-10-29T20:01:00Z",
           "source_pack_sha256": "d" * 64, "trade_authorization": "NONE", "has_formal_buying_permission": False,
           "bond_positions": {}}
    structural = {"schema_version": "Synthetic.StructuralReference.v1", "member_client_id": F.CLIENT,
                  "source_db_sha256": common["source_db_sha256"], "parent_raw_run_id": raw["run_id"],
                  "source_sha256": "d" * 64, "actual_evaluation_at": "2026-10-29T20:02:00Z",
                  "trade_authorization": "NONE", "formal_ledger_writable": False, "assets": {}}
    for symbol in ("KEEP", "NEW", "TW_A", "TW_B", "TW_C", "TW_D"):
        qty = "0" if symbol == "NEW" else "4"
        raw["bond_positions"][symbol] = {"symbol": symbol, "source_zip_sha256": "d" * 64,
            "last_close": "7.25", "last": "2026-10-29", "currency": "TWD", "rows": 30,
            "native_numeric": {"ma20": "7.5", "rsi14": "42"}, "native_td9": {"low": 0, "high": 2}}
        structural["assets"][symbol] = {"total_quantity": qty, "provider_close": "7.25", "valuation_currency": "TWD",
            "positions": [] if symbol == "NEW" else [{"account": "REFERENCE_ACCOUNT_A", "qty": "1"},
                                                      {"account": "REFERENCE_ACCOUNT_B", "qty": "3"}],
            "normal_increment_amount": None, "normal_increment_quantity": None,
            "full_v75_financial_permission": "UNKNOWN", "v75_pred009": {"state": "TECHNICAL_NEUTRAL"}}
    c["review_sources"] = documents(raw, structural)
    return c


def inputs(c):
    return F.A.make_holdings_review_inputs(c["source"], c["request"], c["result"],
        source_id="SYNTHETIC_NATIVE_HOLDINGS", rules_sha="e" * 64, review_sources=c.get("review_sources"))


def current(c=None):
    c = c or case()
    return F.D.build_w6_current_data(c["source"], **inputs(c))


class HoldingsReviewTest(unittest.TestCase):
    def test_original_result_and_earlier_six_references_remain_distinct(self):
        c = case(); before = deepcopy(c); out = current(c)
        self.assertEqual(c, before)
        self.assertEqual(out["report_source_lineage"]["holdings_analysis"], c["result"])
        self.assertEqual(len(out["report_source_lineage"]["holdings_review_documents"]["structural"]["assets"]), 6)
        self.assertIsNone(out["current_total_twd"])
        self.assertEqual(out["report_scope"], "SOURCE_REVIEW")
        cards = out["verified_sections"]
        text = " ".join(x["body"] for rows in cards.values() for x in rows)
        self.assertIn("UNKNOWN", text); self.assertIn("REFERENCE_ACCOUNT_A", text); self.assertIn("REFERENCE_ACCOUNT_B", text)
        fields = [f for rows in cards.values() for card in rows for f in card.get("quoted_fields", [])]
        self.assertTrue(any(f["pointer"].endswith("/total_quantity") and f["value"] == "0" for f in fields))
        self.assertTrue(any(f["pointer"].endswith("/normal_increment_amount") and f["value"] is None for f in fields))
        self.assertTrue(any(f["pointer"].endswith("/proposed_new_external_buy_amount") and f["value"] == "0" for f in fields))

    def test_original_report_without_supplement_does_not_invent_six_account_results(self):
        c = case(); c["review_sources"] = None
        out = current(c)
        self.assertEqual(out["report_source_lineage"]["holdings_review_documents"], {})
        self.assertEqual(out["report_source_lineage"]["holdings_analysis"], c["result"])

    def test_long_identifiers_are_wrapped_with_display_whitespace_only(self):
        c=case();long_scope="SYNTHETIC_SCOPE_"*20
        c["result"]["analysis_result"]["scope"]=long_scope;seal(c)
        out=current(c);cards=out["verified_sections"]["bond"]
        fact=next(f for card in cards for f in card.get("quoted_fields",[]) if f["pointer"]=="/result/analysis_result/scope")
        self.assertEqual(fact["value"],long_scope)
        self.assertTrue(any(long_scope in card["body"].replace(" ","") for card in cards))
        self.assertFalse(any(long_scope in card["body"] for card in cards))

    def test_operator_constructor_accepts_only_pinned_pair_and_keeps_original_options(self):
        c = case(); pair = {k: c[k] for k in ("request", "result")}
        options = {"source_id": "SYNTHETIC_RECEIVER", "rules_sha": "e" * 64,
                   "expected_request_digest": F.A.digest(c["request"]), "expected_result_digest": F.A.digest(c["result"]),
                   "holdings_review_sources": c["review_sources"]}
        producer = W6.MemberAnalysisReportProducer.from_menu04(pair, **options)
        self.assertEqual(producer(c["source"], {})["engine"]["report_sources"]["result"], c["result"])
        with self.assertRaisesRegex(ValueError, "W6_MENU04_RECEIPT_DIGEST_MISMATCH"):
            W6.MemberAnalysisReportProducer.from_menu04(pair, **{**options, "expected_result_digest": "f" * 64})
        producer.sections = {}
        with self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_SOURCE_OPTIONS_CONFLICT"):
            producer(c["source"], {})

    def test_rehashed_wrong_identity_account_DB_run_content_or_mentor_rejected(self):
        attacks = [lambda c: c["request"].update(client_id="OTHER"),
            lambda c: c["result"].update(source_db_sha256="f" * 64),
            lambda c: c["result"].update(run_id="OTHER"),
            lambda c: c["result"]["owner"].update(account="OTHER"),
            lambda c: c["result"]["analysis_result"]["positions"][0]["current_analysis"].update(symbol="OTHER"),
            lambda c: c["result"]["work9_result"]["items"][0].update(asset_id="OTHER"),
            lambda c: c["result"]["mentor"].update(owner={}),
            lambda c: c["result"]["mentor"].update(broker_execution_allowed=True),
            lambda c: c["result"]["recommendation_report"]["rows"][0].update(quantity="5"),
            lambda c: c["result"]["native_bond_source"]["structural_state"].update(run_id="OTHER")]
        for i, attack in enumerate(attacks):
            with self.subTest(attack=i):
                c = case(); attack(c); seal(c)
                with self.assertRaises(ValueError): current(c)

    def test_each_original_document_bytes_are_verified_including_whitespace(self):
        for kind in ("raw", "structural"):
            c = case(); c["review_sources"][kind]["original_text"] += "\n"
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_DOCUMENT_SHA"):
                current(c)

    def test_future_holdings_market_and_mismatched_mentor_items_rejected(self):
        for attack in (lambda c: c["result"]["analysis_result"]["positions"][0]["holding"].update(observed_at="2027-01-01T00:00:00Z"),
                       lambda c: c["result"]["analysis_result"]["positions"][0]["market"].update(observed_date="2027-01-01"),
                       lambda c: c["result"]["mentor"]["items"][0].update(asset_id="OTHER")):
            c=case();attack(c);seal(c)
            with self.subTest(attack=attack),self.assertRaises(ValueError):current(c)

    def test_each_document_identity_time_source_price_currency_and_zero_scope_checked(self):
        attacks = [("raw", lambda d: d.update(client_id="OTHER")),
            ("structural", lambda d: d.update(source_db_sha256="f" * 64)),
            ("structural", lambda d: d.update(parent_raw_run_id="OTHER")),
            ("structural", lambda d: d.update(actual_evaluation_at="2026-11-01T00:00:00Z")),
            ("raw", lambda d: d.update(has_formal_buying_permission=True)),
            ("raw", lambda d: d["bond_positions"]["KEEP"].update(last_close="8")),
            ("raw", lambda d: d["bond_positions"]["KEEP"].update(currency="USD")),
            ("structural", lambda d: d["assets"]["KEEP"].update(normal_increment_quantity="0")),
            ("structural", lambda d: d["assets"]["KEEP"]["positions"][1].update(account="REFERENCE_ACCOUNT_A")),
            ("structural", lambda d: d["assets"]["KEEP"].update(total_quantity="9"))]
        for i, (kind, attack) in enumerate(attacks):
            c = case(); docs = {k: json.loads(v["original_text"]) for k, v in c["review_sources"].items()}
            attack(docs[kind]); c["review_sources"] = documents(docs["raw"], docs["structural"])
            with self.subTest(attack=i), self.assertRaises(ValueError): current(c)

    def test_complete_analysis_does_not_promote_partial_deployment_to_canonical(self):
        c = case(); c["result"]["status"] = "ANALYSIS_COMPLETE"; seal(c)
        self.assertEqual(current(c)["report_scope"], "SOURCE_REVIEW")
        i = inputs(c); binding = i["engine"]["report_sources"]
        binding["scope"] = "CANONICAL_CALCULATION"
        binding["digest"] = F.A.digest({k: v for k, v in binding.items() if k != "digest"})
        with self.assertRaisesRegex(ValueError, "W6_HOLDINGS_REVIEW_SCOPE_ONLY"):
            F.D.build_w6_current_data(c["source"], **i)
        self.assertEqual(F.current()["report_scope"], "CANONICAL_CALCULATION")


if __name__ == "__main__":
    unittest.main()
