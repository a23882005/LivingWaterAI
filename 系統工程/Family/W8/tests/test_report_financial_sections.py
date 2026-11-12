"""Lossless display and binding checks, entirely invented financial outputs."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("financial_display_fixture", Path(__file__).parent / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


def inputs(c, **extra):
    return F.A.make_member_review_inputs(c["source"], c["request"], c["result"],
        source_id="SYNTHETIC_ALL_ASSET_PRODUCER", rules_sha="e" * 64, **extra)


def current(c, **extra):
    return F.D.build_w6_current_data(c["source"], **inputs(c, **extra))


def refresh_coverage(c):
    coverage = c["result"]["all_asset_coverage"]
    for bond in coverage["bonds"]:
        bond["result_digest"] = F.A.digest({k: v for k, v in bond.items() if k != "result_digest"})
    coverage["coverage_digest"] = F.A.digest({k: v for k, v in coverage.items() if k != "coverage_digest"})
    F.member_refresh(c)


class FinancialDisplayTests(unittest.TestCase):
    def test_eight_chapters_quote_known_values_and_preserve_raw_objects(self):
        c = F.member_financial_case();before = deepcopy(c)
        out = current(c)
        self.assertEqual(set(out["verified_sections"]), set(F.A.SECTION_NAMES))
        self.assertEqual(out["report_source_lineage"]["member_analysis"], c["result"])
        for section, fields in out["report_source_lineage"]["section_projection"]["quoted_fields"].items():
            data = {"request": c["request"], "result": c["result"]}
            for field in fields:
                value = data
                for part in field["pointer"].strip("/").split("/"):
                    if isinstance(value, list): value = value[int(part)]
                    elif part in value: value = value[part]
                    else: value = None;break
                if field["present"]: self.assertEqual(field["value"], value)
        text = str(out["verified_sections"])
        for value in ("12.345678901", "17.890123", "101.234567", "3.210987", "TECHNICAL_NEUTRAL"):
            self.assertIn(value, text)
        self.assertEqual(c, before)

    def test_all_asset_denominators_cash_bonds_and_funding_do_not_become_nav(self):
        c = F.member_financial_case();out = current(c)
        summary = out["asset_coverage_summary"]
        self.assertEqual(summary["denominators"], c["result"]["all_asset_coverage"]["denominators"])
        self.assertIs(summary["coverage_complete"], True)
        self.assertIs(summary["financial_completeness_asserted"], False)
        self.assertIsNone(out["current_total_twd"]);self.assertEqual(out["drift"], [])
        self.assertIsNone(out["approved_radar"])
        self.assertTrue(all(x["市值TWD"] is None for x in out["target"]))
        self.assertIn("SYN_SGOV", str(out["verified_sections"]["bond"]))
        self.assertIn("SYNTH_CASH", str(out["verified_sections"]["actions"]))

    def test_true_condition_is_not_promoted_to_a_selected_stage_or_amount(self):
        c = F.member_financial_case();out = current(c)
        self.assertEqual(c["result"]["positions"][0]["formal_conclusion"]["formal_stage"], "UNKNOWN")
        fields = out["report_source_lineage"]["section_projection"]["quoted_fields"]["valuation"]
        stage = next(x for x in fields if x["pointer"].endswith('/formal_stage'))
        condition = next(x for x in fields if x["pointer"].endswith('/eligible/2'))
        self.assertEqual(condition["value"], "TRUE");self.assertEqual(stage["value"], "UNKNOWN")
        self.assertTrue(all(x["proposed_amount"] is None for x in c["result"]["positions"]))

    def test_rehashed_foreign_coverage_account_routes_and_counts_are_rejected(self):
        for attack in ("client", "DB", "cutoff", "cash_owner", "account", "route", "count", "coverage", "financial_scope"):
            with self.subTest(attack=attack):
                c = F.member_financial_case();a = c["result"]["all_asset_coverage"]
                if attack == "client": a["client_id"] = "OTHER"
                elif attack == "DB": a["source_db_sha256"] = "b" * 64
                elif attack == "cutoff": a["evaluation_at"] = "2026-11-01T00:00:00Z"
                elif attack == "cash_owner": a["cash_accounts"][0]["owner_candidate"]["client_id"] = "OTHER"
                elif attack == "account": a["cash_accounts"][0]["account_key"] = "OTHER_ACCOUNT"
                elif attack == "route": a["bonds"][0]["route"] = "V82"
                elif attack == "count": a["denominators"]["cash_accounts"] = 0
                elif attack == "coverage": a["observed"] = []
                else: a["financial_completeness_asserted"] = True
                refresh_coverage(c)
                with self.assertRaisesRegex(ValueError, "W6_ALL_ASSET_"): current(c)

    def test_tampered_inner_digests_and_future_availability_are_rejected(self):
        for attack in ("coverage_digest", "bond_digest", "bond_time", "stock_time", "macro_time", "section_time"):
            with self.subTest(attack=attack):
                c = F.member_financial_case();a = c["result"]["all_asset_coverage"]
                if attack == "coverage_digest": a["coverage_digest"] = "0" * 64
                elif attack == "bond_digest": a["bonds"][0]["result_digest"] = "0" * 64
                elif attack == "bond_time": a["bonds"][0]["market"]["provider_verified_at"] = "2099-01-01T00:00:00Z";refresh_coverage(c)
                elif attack == "stock_time": c["result"]["positions"][0]["market"]["provider_verified_at"] = "2099-01-01T00:00:00Z"
                elif attack == "macro_time": c["request"]["macro_snapshot"]["payload"]["indicators"]["SYN_RATE"]["lastVerifiedAt"] = "2099-01-01T00:00:00Z"
                if attack == "bond_digest": a["coverage_digest"] = F.A.digest({k:v for k,v in a.items() if k != "coverage_digest"})
                F.member_refresh(c)
                if attack == "section_time":
                    envelope = deepcopy(F.case()["sections"]["market"])
                    envelope.update(run_id=c["request"]["run_id"], available_at="2099-01-01T00:00:00Z")
                    with self.assertRaisesRegex(ValueError, "W6_FUTURE_SECTION_AVAILABILITY"): current(c, sections={"market": envelope})
                else:
                    with self.assertRaises(ValueError): current(c)

    def test_explicit_verified_envelope_keeps_original_producer_values(self):
        c = F.member_financial_case();envelope = deepcopy(F.case()["sections"]["institutions"])
        envelope["run_id"] = c["request"]["run_id"]
        out = current(c, sections={"institutions": envelope})
        self.assertEqual(out["report_source_lineage"]["sections"]["institutions"], envelope)
        self.assertEqual(out["verified_sections"]["institutions"], envelope["payload"])
        self.assertNotIn("institutions", out["report_source_lineage"]["section_projection"]["generated_sections"])
        self.assertEqual(out["report_source_lineage"]["input_sections"]["institutions"], envelope)

    def test_projection_cannot_use_db_or_network_transport(self):
        from unittest.mock import patch
        c = F.member_financial_case()
        with patch("sqlite3.connect", side_effect=AssertionError("DB forbidden")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("HTTP forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            out = current(c)
        self.assertEqual(out["trade_authorization"], "NONE")


if __name__ == '__main__':
    unittest.main()
