"""Incremental report contract tests. All identities and outputs are synthetic."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("report_contract_fixture", Path(__file__).parent / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class CanonicalReportTests(unittest.TestCase):
    def setUp(self):
        self.c = F.case()

    def test_current_union_target_and_canonical_values_are_lossless(self):
        frozen = deepcopy(self.c)
        out = F.current(self.c)
        rows = {r["標的"]: r for r in out["drift"]}
        self.assertEqual(set(rows), {"KEEP", "SELL", "BOTH", "NEW"})
        self.assertEqual({r["代碼"] for r in out["target"]}, {"KEEP", "BOTH", "NEW"})
        self.assertEqual({r["代碼"] for r in out["actual"]}, {"KEEP", "SELL", "BOTH"})
        for raw in self.c["c7"]["original_source"]["work6_result"]["drift_snapshot"]["items"]:
            row = rows[raw["ticker"]]
            self.assertEqual(row["canonical_item"], raw)
            self.assertEqual(Decimal(row["目標權重"]), Decimal(str(raw["final_target_weight"]["value"])))
            self.assertEqual(Decimal(row["差異百分點"]), -Decimal(str(raw["drift"]["value"])) * 100)
            self.assertEqual(Decimal(row["差異TWD"]), -Decimal(str(raw["drift"]["value"])) * 1000)
        self.assertTrue(rows["KEEP"]["protected"])
        self.assertEqual(rows["KEEP"]["client_facing_action"], "HOLD_PROTECTED")
        self.assertEqual(self.c, frozen)

    def test_c_target_not_db_weight_times_nav(self):
        c = self.c
        # A signed DB source-review projection is intentionally different;
        # C's effective protected Final Target is the rendering authority.
        c["source"]["current_confirmed_target_details"] = [{"target_key": "MAIN", "version_no": 7,
            "allocations": [{"instrument_key": "BOTH", "ticker": "BOTH", "weight_units": 1000000}]}]
        c["source"]["digest"] = F.A.digest({k: v for k, v in c["source"].items() if k != "digest"})
        c["target_context"] = None
        F.refresh(c)
        out = F.current(c)
        self.assertEqual({r["代碼"]: Decimal(r["市值TWD"]) for r in out["target"]},
                         {"KEEP": Decimal(400), "BOTH": Decimal(400), "NEW": Decimal(200)})

    def test_rehashed_scope_and_source_attacks_are_rejected(self):
        for key in ("client_id", "source_db_sha256", "source_digest", "run_id", "snapshot_payload_sha256"):
            with self.subTest(key=key):
                c = F.case(); b = c["engine"]["report_sources"]; b[key] = "WRONG"
                b["digest"] = F.A.digest({k: v for k, v in b.items() if k != "digest"})
                with self.assertRaisesRegex(ValueError, "W6_REPORT_SOURCE_BINDING"):
                    F.current(c)

    def test_wrong_owner_account_is_rejected_even_after_rehash(self):
        for owner_key in ("client_id", "account", "broker", "funding_domain"):
            with self.subTest(key=owner_key):
                c = F.case(); c["request"]["owner"][owner_key] = "WRONG"
                F.refresh(c)
                with self.assertRaises(ValueError):
                    F.current(c)

    def test_changed_work9_canonical_summary_and_digest_are_rejected(self):
        for attack in ("canonical", "summary", "source_bindings", "run", "owner"):
            with self.subTest(attack=attack):
                c = F.case(); u = c["result"]["native_result"]["unified_result"]
                if attack == "canonical": u["canonical_deployment_result"]["items"][0]["canonical_action"] = "BUY"
                elif attack == "summary": u["mentor_return"]["item_ids"] = []
                elif attack == "source_bindings": u["source_bindings"] = {}
                elif attack == "run": u["mentor_return"]["run_id"] = "WRONG"
                else: c["result"]["mentor"]["owner"]["account"] = "WRONG"
                F.refresh(c)
                with self.assertRaises(ValueError): F.current(c)

    def test_rehashed_c_denominator_and_unit_errors_are_rejected(self):
        for attack in ("currency", "amount", "drift_denominator", "percent", "unit", "universe", "protected"):
            with self.subTest(attack=attack):
                c = F.case(); w6 = c["c7"]["original_source"]["work6_result"]
                if attack == "currency": w6["final_target"]["snapshot"]["denominator"]["currency"] = "USD"
                elif attack == "amount": w6["final_target"]["snapshot"]["denominator"]["amount"] = 999
                elif attack == "drift_denominator": w6["drift_snapshot"]["denominator"]["amount"] = 999
                elif attack == "percent": w6["drift_snapshot"]["items"][0]["current_weight"]["value"] = 40
                elif attack == "unit": w6["drift_snapshot"]["items"][0]["current_weight"]["unit"] = "PERCENT"
                elif attack == "universe": w6["drift_snapshot"]["items"].pop()
                else: w6["drift_snapshot"]["items"][0]["client_facing_action"] = "SELL"
                c["c7"]["result"]["drift_snapshot"] = deepcopy(w6["drift_snapshot"])
                F.refresh(c)
                with self.assertRaises(ValueError): F.current(c)

    def test_same_client_wrong_c_run_or_digest_is_rejected(self):
        for attack in ("run", "digest", "snapshot", "final_id"):
            with self.subTest(attack=attack):
                c = F.case(); original = c["c7"]["original_source"]
                if attack == "run": original["work6_result"]["identity"]["run_id"] = "WRONG"
                elif attack == "snapshot": c["c7"]["result"]["parent_work6_snapshot_id"] = "WRONG"
                elif attack == "final_id": original["work6_result"]["final_target"]["snapshot"]["allocation_id"] = "WRONG"
                else: original["source_reference"] = "MODIFIED_WITHOUT_PRODUCER_DIGEST"
                if attack != "digest": F.refresh(c)
                else:
                    b = c["engine"]["report_sources"]; b["c7"]["original_source"] = original
                    b["digest"] = F.A.digest({k: v for k, v in b.items() if k != "digest"})
                with self.assertRaises(ValueError): F.current(c)

    def test_radar_order_labels_levels_and_raw_snapshot_preserved(self):
        out = F.current(self.c); radar = out["approved_radar"]
        raw = self.c["c7"]["original_source"]["work6_result"]["radar_snapshot"]
        self.assertEqual(radar["canonical_snapshot"], raw)
        self.assertEqual(radar["view_order"], [x["view_id"].lower() for x in raw["views"]])
        self.assertEqual([x["label_zh"] for x in radar["axes"]], [x[1] for x in F.AXES])
        self.assertEqual(radar["views"]["current_attack"]["levels"], [1, 2, 3, 4, 5, 6])
        html = F.R._radar_panels(radar)
        self.assertLess(html.index("目前攻擊"), html.index("目標攻擊"))
        import re
        self.assertIn("估值壓縮", re.sub("<[^>]+>", "", html))

    def test_radar_wrong_axis_order_rejected(self):
        c = self.c; radar = c["c7"]["original_source"]["work6_result"]["radar_snapshot"]
        radar["axes"].reverse(); c["c7"]["result"]["radar_snapshot"] = deepcopy(radar)
        F.refresh(c)
        with self.assertRaisesRegex(ValueError, "W6_C_RADAR_CONTRACT"): F.current(c)

    def test_unknown_radar_does_not_become_zero_or_old_score(self):
        c = self.c; radar = c["c7"]["original_source"]["work6_result"]["radar_snapshot"]
        radar["views"][0]["axes"][0]["score"].update(value_state="UNKNOWN", value=None)
        c["c7"]["result"]["radar_snapshot"] = deepcopy(radar); F.refresh(c)
        out = F.current(c)
        self.assertIsNone(out["approved_radar"]["views"]["current_attack"]["levels"][0])
        self.assertIn("UNKNOWN／待來源補齊", F.R._radar_panels(out["approved_radar"]))

    def test_eight_sections_keep_different_original_asof_and_scope(self):
        out = F.current(self.c)
        self.assertEqual(out["report_source_lineage"]["sections"], self.c["sections"])
        for name in F.A.SECTION_NAMES:
            self.assertEqual(out["verified_sections"][name], self.c["sections"][name]["payload"])
        blocks = F.R._build_blocks(out)
        for block in blocks[6:]:
            self.assertIn("資料日期：2026-10-01T00:00:00Z", "".join(block["parts"]))
        self.assertNotIn("Joseph", str(out))

    def test_hypothetical_and_historical_evidence_never_enters_actual(self):
        c = self.c
        c["source"]["actual_user_evidence"] = [{"evidence_tier": "ACCEPTED_HISTORICAL_W6", "entity": "OLD", "fields": {"market_value": "999999"}}]
        c["source"]["hypothetical_evidence_separate"] = [{"entity": "HYPOTHETICAL", "fields": {"market_value": "999999"}}]
        c["source"]["digest"] = F.A.digest({k: v for k, v in c["source"].items() if k != "digest"})
        F.refresh(c)
        out = F.current(c)
        self.assertEqual(out["current_total_twd"], "1000")
        self.assertEqual({x["代碼"] for x in out["actual"]}, {"KEEP", "SELL", "BOTH"})

    def test_wrong_current_account_and_tampered_snapshot_table_are_rejected(self):
        c = F.case(); c["market"]["position_values_twd"][0]["account_key"] = "OTHER_ACCOUNT"
        with self.assertRaisesRegex(ValueError, "W6_POSITION_VALUATION_COVERAGE"): F.current(c)
        c = F.case(); snap = c["request"]["client_snapshot"]["payload"]
        snap["tables"]["portfolio_position"][0]["quantity_decimal"] = "9999"
        c["request"]["client_snapshot"]["digest"] = F.A.digest(snap)
        F.refresh(c)
        with self.assertRaisesRegex(ValueError, "W6_REPORT_SNAPSHOT_TABLE_DIGEST"): F.current(c)

    def test_wrong_section_run_client_and_digest_rejected(self):
        for key in ("client_id", "run_id", "payload_sha256"):
            with self.subTest(key=key):
                c = F.case(); c["sections"]["bond"][key] = "WRONG"; F.refresh(c)
                if key == "payload_sha256":
                    b = c["engine"]["report_sources"]; b["sections"]["bond"][key] = "WRONG"
                    b["digest"] = F.A.digest({k: v for k, v in b.items() if k != "digest"})
                with self.assertRaises(ValueError): F.current(c)

    def test_full_scope_allows_declared_section_gaps_and_zero_new_funding(self):
        c = self.c; c["sections"] = {}; F.refresh(c)
        out = F.current(c)
        self.assertEqual(out["report_scope"], "CANONICAL_CALCULATION")
        self.assertEqual(len(F.R._build_blocks(out)), 14)
        self.assertEqual(out["verified_sections"]["bond"][0]["heading"], "資料狀態：UNKNOWN")
        self.assertTrue(all(x["canonical_action"] == "WAIT" for x in out["report_source_lineage"]["action"]["items"]))

    def test_actual_original_work9_and_mentor_output_shapes_are_consumed(self):
        import json
        c = self.c
        family = F.W8.parent
        repo = family.parents[1]
        raw_request = json.loads((family / "W5/tests/fixtures/work9_mentor_request.json").read_text())
        native = F.A._runtime("runtime_loader", "W5").load_c_module(repo, 9)
        unified = native.build_unified_deployment(raw_request)
        original_owner = unified["owner"]
        # Bind the synthetic report's DB/request to the actual public golden
        # account/run; retain all original Work9 values and source bindings.
        account = original_owner["account"]
        run = unified["run_id"]
        owner = {"client_id": F.CLIENT, **original_owner, "currency": unified["currency"]}
        snapshot = c["snapshot"]
        snapshot["tables"]["portfolio_account"][0]["account_key"] = account
        for row in snapshot["tables"]["portfolio_position"]: row["account_key"] = account
        snapshot["payload_digest"] = F.A.digest(snapshot["tables"])
        c["source"] = F.S.build_report_source(snapshot, account="AR", expected_client_id=F.CLIENT)
        c["request"].update(run_id=run, owner=deepcopy(owner))
        c["request"]["client_snapshot"] = {"payload": snapshot, "digest": F.A.digest(snapshot)}
        c["request"]["native_bundle"]["stock_request"]["work3_handoff"]["owner"] = deepcopy(original_owner)
        c["market"]["run_id"] = c["engine"]["run_id"] = run
        for row in c["market"]["position_values_twd"]: row["account_key"] = account
        c["target_context"].update(run_id=run, snapshot_payload_sha256=snapshot["payload_digest"])
        original = c["c7"]["original_source"]
        original["family_owner"] = deepcopy(owner)
        for ident in (original["canonical_input"]["identity"], original["work6_result"]["identity"], c["c7"]["result"]["identity"]):
            ident["run_id"] = run
        allocation_id = unified["source_bindings"]["final_target_allocation_id"]
        original["work6_result"]["final_target"]["snapshot"]["allocation_id"] = allocation_id
        target = c["request"]["confirmed_target"]
        target["payload"]["draft"]["allocation_id"] = allocation_id
        target["payload"]["draft"]["draft_hash"] = F.A.digest({k: v for k, v in target["payload"]["draft"].items() if k != "draft_hash"})
        target["target_hash"] = target["payload"]["target_hash"] = target["payload"]["draft"]["draft_hash"]
        c["target_context"]["expected_target_hash"] = target["target_hash"]
        for envelope in c["sections"].values(): envelope["run_id"] = run
        context = {"client_id": F.CLIENT, "run_id": run, "owner": original_owner, "currency": unified["currency"],
                   "analysis_permission": "ANALYZE_ONLY", "trade_authorization": "NONE", "runtime_mode": "REAL_DETERMINISTIC",
                   "data_provenance": "SYNTHETIC", "expected_result_digest": native._digest(unified)}
        mentor = F.A._runtime("mentor_bridge", "W5").explain_native(repo, raw_request, unified, trusted_context=context)
        c["result"].update(run_id=run, owner=deepcopy(owner), mentor=mentor)
        c["result"]["native_result"]["unified_result"] = unified
        F.refresh(c)
        out = F.current(c)
        self.assertEqual(out["report_source_lineage"]["action"]["items"], unified["canonical_deployment_result"]["items"])
        self.assertEqual(out["canonical_final_target_id"], allocation_id)

    def test_partial_review_does_not_require_work9_or_complete_sections(self):
        c = self.c; c["sections"] = {}; F.refresh(c, scope="SOURCE_REVIEW", result=False)
        out = F.current(c)
        self.assertEqual(out["report_scope"], "SOURCE_REVIEW")
        self.assertIsNone(out["report_source_lineage"]["action"])
        self.assertEqual(out["drift"][0]["client_facing_action"], "HOLD_PROTECTED")
        self.assertEqual(len(F.R._build_blocks(out)), 14)

    def test_source_review_without_c_does_not_claim_canonical_result(self):
        c = self.c; c["sections"] = {}; F.refresh(c, scope="SOURCE_REVIEW", result=False, c7=False)
        out = F.current(c)
        self.assertIsNone(out["approved_radar"])
        self.assertNotIn("canonical_lineage", out)
        self.assertIn("UNKNOWN", str(F.R._build_blocks(out)))

    def test_full_claim_requires_c_and_work9_but_review_retains_failure(self):
        c = self.c; F.refresh(c, result=False)
        with self.assertRaisesRegex(ValueError, "W6_CANONICAL_WORK9_REQUIRED"): F.current(c)
        c["result"] = {"schema_version": "Family.W5.result.v1", "status": "DATA_UNAVAILABLE",
            "request_id": c["request"]["request_id"], "run_id": c["request"]["run_id"],
            "canonical_result": None, "mentor": None, "production": "HOLD", "trade_action": "NO_TRADE"}
        c["engine"]["status"] = "DATA_UNAVAILABLE"
        F.refresh(c, scope="SOURCE_REVIEW", c7=False)
        out = F.current(c)
        self.assertEqual(out["report_source_lineage"]["action"]["status"], "DATA_UNAVAILABLE")

    def test_currency_conversion_is_named_and_reversible(self):
        c = self.c; original = c["c7"]["original_source"]
        for den in (original["work6_result"]["final_target"]["snapshot"]["denominator"],
                    original["work6_result"]["drift_snapshot"]["denominator"],
                    original["canonical_input"]["allocations"]["current_allocation"]["snapshot"]["denominator"]):
            den.update(amount=100, currency="USD")
        c["c7"]["result"]["drift_snapshot"] = deepcopy(original["work6_result"]["drift_snapshot"])
        c["market"]["fx_to_twd"]["USD"] = {"verified": True, "rate": "10", "source_reference": "SYNTHETIC_FX", "as_of": F.ASOF}
        F.refresh(c); out = F.current(c)
        self.assertEqual(out["canonical_lineage"]["fx_to_twd"], "10")
        self.assertEqual(Decimal(out["drift"][1]["差異TWD"]), Decimal(300))
        self.assertEqual(out["canonical_lineage"]["source"]["final"]["denominator"]["currency"], "USD")


class ExternalTargetTests(unittest.TestCase):
    def setUp(self): self.c = F.case()

    def build(self):
        return F.S.build_report_source(self.c["snapshot"], account="AR", expected_client_id=F.CLIENT,
            approved_target=self.c["request"]["confirmed_target"], target_context=self.c["target_context"])

    def refresh_snapshot(self):
        digest = F.A.digest(self.c["snapshot"]["tables"])
        self.c["snapshot"]["payload_digest"] = digest
        self.c["target_context"]["snapshot_payload_sha256"] = digest

    def test_empty_db_uses_original_approved_target_and_historical_confirmation(self):
        out = self.build(); detail = out["current_confirmed_target_details"][0]
        self.assertEqual(detail["version_no"], 7)
        self.assertEqual(detail["confirmed_at_utc"], "2026-09-01T00:00:00Z")
        self.assertEqual(out["external_target_receipt"]["payload"], self.c["request"]["confirmed_target"])

    def test_invalid_target_client_version_confirmation_and_source_rejected(self):
        for attack in ("client", "version", "confirmation", "source"):
            with self.subTest(attack=attack):
                self.c = F.case(); target = self.c["request"]["confirmed_target"]
                if attack == "client": target["payload"]["draft"]["identity"]["client_id"] = "WRONG"
                elif attack == "version": target["target_version"] = 8
                elif attack == "confirmation": target["payload"]["confirmation_evidence"] = {}
                else: self.c["target_context"]["source_db_sha256"] = "b" * 64
                with self.assertRaises(ValueError): self.build()

    def test_db_external_conflict_is_not_silently_selected(self):
        t = self.c["snapshot"]["tables"]
        t["final_target_version"] = [{"target_key": "MAIN", "version_no": 7,
            "lifecycle_state": "CONFIRMED", "completeness_state": "COMPLETE"}]
        t["final_target_allocation"] = [{"target_key": "MAIN", "version_no": 7, "instrument_key": "BOTH",
            "weight_units": 1000000, "allocation_state": "ACCEPTED"}]
        self.refresh_snapshot()
        with self.assertRaisesRegex(ValueError, "W6_DB_EXTERNAL_TARGET_CONFLICT"): self.build()

    def test_identical_db_and_external_target_keep_both_provenances(self):
        t = self.c["snapshot"]["tables"]
        t["final_target_version"] = [{"target_key": "MAIN", "version_no": 7,
            "lifecycle_state": "CONFIRMED", "completeness_state": "COMPLETE"}]
        t["final_target_allocation"] = [{"target_key": "MAIN", "version_no": 7, "instrument_key": x,
            "weight_units": w, "allocation_state": "ACCEPTED"} for x, w in (("KEEP", 400000), ("BOTH", 400000), ("NEW", 200000))]
        self.refresh_snapshot()
        out = self.build()
        self.assertEqual(len(out["current_confirmed_target_details"]), 1)
        self.assertIn("external_target_receipt", out["current_confirmed_target_details"][0])

    def test_newer_incomplete_db_confirmation_cannot_revert_to_external_old_version(self):
        self.c["snapshot"]["tables"]["final_target_version"] = [{"target_key": "MAIN", "version_no": 8,
            "lifecycle_state": "CONFIRMED", "completeness_state": "INCOMPLETE"}]
        self.refresh_snapshot()
        with self.assertRaisesRegex(ValueError, "W6_DB_EXTERNAL_TARGET_CONFLICT"): self.build()


if __name__ == "__main__": unittest.main()
