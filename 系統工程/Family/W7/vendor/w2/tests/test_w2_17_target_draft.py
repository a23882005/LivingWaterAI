import copy
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "c_configuration_core"))
from work17.target_draft import build_final_target_draft


FIXTURE = json.loads((ROOT / "fixtures/W2_17_TARGET_DRAFT_GOLDEN.json").read_text())


def build(**overrides):
    args = {k: copy.deepcopy(FIXTURE[k]) for k in ("c_work6_response", "funding_budgets", "planned_investments", "risk_by_instrument")}
    args.update({"expected_client_id": FIXTURE["expected_client_id"], "expected_run_id": FIXTURE["expected_run_id"]})
    args.update(overrides)
    return build_final_target_draft(**args)


class W2_17Tests(unittest.TestCase):
    def test_p01_known_bucket_budgets_and_risk_trace(self):
        out = build()
        self.assertEqual(out.status, "DRAFT")
        self.assertEqual(len(out.draft["target_lines"]), 2)
        self.assertEqual(sum(x["weight"]["value"] for x in out.draft["target_lines"]), 1.0)
        residuals = {x["funding_bucket_id"]: x["cash_residual"] for x in out.draft["cash_residual_by_funding_bucket"]}
        self.assertEqual(residuals, {"TW_LOCAL_A": 4000.0, "US_BROKER_A": 800.0})
        line = next(x for x in out.draft["target_lines"] if x["instrument_id"] == "ETF-A.TW")
        self.assertEqual(line["risk"]["max_drawdown"]["value"], -0.21)
        self.assertEqual(line["risk"]["drawdown_amount"]["value"], 12600.0)
        self.assertEqual(line["risk"]["recovery_period"]["value"], 28.0)
        self.assertEqual(out.draft["confirmation_status"], "PENDING")
        self.assertFalse(out.draft["is_trade_authorized"])
        self.assertEqual(len(out.draft["allocation_by_asset_type"]), 2)

    def test_n01_protected_cash_and_estimated_shares_fail_closed_unknown_risk_stays_null(self):
        budgets = copy.deepcopy(FIXTURE["funding_budgets"])
        budgets[0].update({"total_amount": 1000, "protected_amount": 800, "available_amount": 300})
        out = build(funding_budgets=budgets)
        self.assertEqual(out.status, "BLOCKED")
        self.assertIn("PROTECTED_LIVING_EXPENSES_USED", out.issue_codes)
        plans = copy.deepcopy(FIXTURE["planned_investments"])
        plans[0]["estimated_shares"] = 12
        out = build(planned_investments=plans)
        self.assertEqual(out.status, "BLOCKED")
        self.assertIn("ESTIMATED_SHARE_COUNT_NOT_ACCEPTED", out.issue_codes)
        risk = copy.deepcopy(FIXTURE["risk_by_instrument"])
        risk["ETF-A.TW"]["max_drawdown"] = {"value_state": "UNKNOWN", "value": 0}
        out = build(risk_by_instrument=risk)
        mdd = next(x for x in out.draft["target_lines"] if x["instrument_id"] == "ETF-A.TW")["risk"]["max_drawdown"]
        self.assertEqual(mdd["value_state"], "UNKNOWN")
        self.assertIsNone(mdd["value"])

    def test_b01_zero_small_cross_currency_duplicate_and_over_ten(self):
        budgets = copy.deepcopy(FIXTURE["funding_budgets"])
        budgets[0].update({"total_amount": 0, "protected_amount": 0, "available_amount": 0})
        plans = copy.deepcopy(FIXTURE["planned_investments"])
        plans[0]["amount"] = 0
        plans[1]["amount"] = 0.01
        out = build(funding_budgets=budgets, planned_investments=plans)
        self.assertEqual(out.status, "DRAFT")
        self.assertEqual(next(x for x in out.draft["cash_residual_by_funding_bucket"] if x["funding_bucket_id"] == "TW_LOCAL_A")["cash_residual"], 0.0)
        self.assertIn("MULTI_CURRENCY_SEPARATE_BUCKETS_NO_FX", out.issue_codes)
        plans = copy.deepcopy(FIXTURE["planned_investments"])
        plans.append(copy.deepcopy(plans[0]))
        out = build(planned_investments=plans)
        self.assertIn("DUPLICATE_IDENTICAL_COLLAPSED", out.issue_codes)
        self.assertEqual(next(x for x in out.draft["cash_residual_by_funding_bucket"] if x["funding_bucket_id"] == "TW_LOCAL_A")["allocated_amount"], 6000.0)
        response = copy.deepcopy(FIXTURE["c_work6_response"])
        ps = response["result"]["draft_allocation"]["snapshot"]["positions"]
        ps.append(copy.deepcopy(ps[0]))
        out = build(c_work6_response=response, planned_investments=[])
        self.assertEqual(len(out.draft["target_lines"]), 2)
        self.assertIn("DUPLICATE_TARGET_INSTRUMENT_COLLAPSED", out.issue_codes)
        response = copy.deepcopy(FIXTURE["c_work6_response"])
        snapshot = response["result"]["draft_allocation"]["snapshot"]
        snapshot["positions"] = []
        for i in range(11):
            p = copy.deepcopy(FIXTURE["c_work6_response"]["result"]["draft_allocation"]["snapshot"]["positions"][0])
            p["instrument_id"] = f"ETF-{i:02d}"
            p["weight"]["value"] = 1/11
            snapshot["positions"].append(p)
        out = build(c_work6_response=response, planned_investments=[])
        self.assertIn("TARGET_HOLDINGS_OVER_10_REVIEW", out.issue_codes)

    def test_wrong_client_or_confirmed_c_result_is_blocked(self):
        response = copy.deepcopy(FIXTURE["c_work6_response"])
        response["result"]["identity"]["client_id"] = "OTHER"
        self.assertEqual(build(c_work6_response=response).status, "BLOCKED")
        response = copy.deepcopy(FIXTURE["c_work6_response"])
        response["result"]["confirmation_status"] = "CONFIRMED"
        self.assertIn("TARGET_DRAFT_MUST_REMAIN_UNCONFIRMED", build(c_work6_response=response).issue_codes)

    def test_b01_reordered_inputs_have_identical_hash(self):
        first = build()
        budgets = copy.deepcopy(FIXTURE["funding_budgets"])[::-1]
        plans = copy.deepcopy(FIXTURE["planned_investments"])[::-1]
        response = copy.deepcopy(FIXTURE["c_work6_response"])
        response["result"]["draft_allocation"]["snapshot"]["positions"].reverse()
        second = build(funding_budgets=budgets, planned_investments=plans, c_work6_response=response)
        self.assertEqual(first.draft["draft_hash"], second.draft["draft_hash"])


if __name__ == "__main__":
    unittest.main()
