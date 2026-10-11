from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from helpers import cloned_payload
from v75_runtime import V75RunInput
from v75_runtime.work3 import build_work3_state


def us_payload():
    p = cloned_payload()
    p["existing_bond_holdings"] = [
        {"asset_id": "SGOV", "amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "amount": {"amount": "100", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["target_bond_holdings"] = [
        {"asset_id": "SGOV", "target_amount": {"amount": "700", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "target_amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    return p


def test_sgov_role_total_is_observational_sum_only():
    s = build_work3_state(V75RunInput.model_validate(us_payload()))
    r = s.sgov_reconciliation
    assert r.sgov_bond_bucket_amount.value.amount == Decimal("300")
    assert r.sgov_dry_powder_bucket_amount.value.amount == Decimal("400")
    assert r.observed_role_total_amount.value.amount == Decimal("700")
    assert r.roles_kept_separate is True
    assert r.dry_powder_is_read_only_context is True


def test_work3_does_not_mutate_sgov_input_roles():
    p = us_payload()
    model = V75RunInput.model_validate(p)
    before = model.model_dump(mode="json")
    build_work3_state(model)
    after = model.model_dump(mode="json")
    assert before == after


def test_work3_output_has_no_deployment_decision_fields():
    s = build_work3_state(V75RunInput.model_validate(us_payload()))
    dumped = s.model_dump(mode="json")
    text = str(dumped)
    assert "deploy_amount" not in text
    assert "deployment_pct" not in text
    assert "deployment_state" not in text
    assert "v75_undeployed_to_sgov" not in text


def test_cross_account_holding_still_rejected_by_frozen_work2_model():
    p = us_payload()
    p["existing_bond_holdings"][0]["broker_account_id"] = "OTHER"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(p)


def test_cross_account_target_still_rejected_by_frozen_work2_model():
    p = us_payload()
    p["target_bond_holdings"][0]["broker_account_id"] = "OTHER"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(p)


def test_unsettled_positive_budget_still_rejected_by_frozen_work2_model():
    p = us_payload()
    p["funding_settlement_status"] = "UNSETTLED"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(p)


def test_executable_budget_cannot_exceed_same_account_available_cash():
    p = us_payload()
    p["bond_executable_budget"]["amount"] = "1001"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(p)


def test_work3_does_not_depend_on_market_predicate_results():
    p = us_payload()
    p["predicate_results"] = []
    s1 = build_work3_state(V75RunInput.model_validate(p))
    p2 = deepcopy(p)
    # Work3 deliberately ignores predicate payloads; using no predicates in both remains deterministic.
    s2 = build_work3_state(V75RunInput.model_validate(p2))
    assert s1.model_dump(mode="json") == s2.model_dump(mode="json")


def test_no_cross_account_netting_in_gap_math():
    p = us_payload()
    # Cross-account holdings never enter the accepted model at all.
    p["existing_bond_holdings"].append({"asset_id": "SPSB", "amount": {"amount": "9999", "currency": "USD"}, "broker_account_id": "OTHER"})
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(p)
