import pytest
from pydantic import ValidationError

from helpers import cloned_payload
from v75_runtime.models import PerAssetDeploymentInput, V75RunInput
from v75_runtime.validation import validate_v75_run_input


def test_legacy_alias_normalizes_once():
    raw = {
        "asset_id": "SGOV",
        "remaining_target_gap": {"amount": "10", "currency": "USD"},
        "existing_position_amount": {"amount": "0", "currency": "USD"},
        "currency": "USD",
    }
    model = PerAssetDeploymentInput.model_validate(raw)
    dumped = model.model_dump(mode="json")
    assert "remaining_target_gap_amount" in dumped
    assert "remaining_target_gap" not in dumped


def test_alias_conflict_is_hard_validation_fail():
    raw = {
        "asset_id": "SGOV",
        "remaining_target_gap": {"amount": "10", "currency": "USD"},
        "remaining_target_gap_amount": {"amount": "11", "currency": "USD"},
        "existing_position_amount": {"amount": "0", "currency": "USD"},
        "currency": "USD",
    }
    with pytest.raises(ValidationError):
        PerAssetDeploymentInput.model_validate(raw)


def test_same_alias_and_canonical_value_is_accepted_then_legacy_removed():
    raw = {
        "asset_id": "SGOV",
        "remaining_target_gap": {"amount": "10", "currency": "USD"},
        "remaining_target_gap_amount": {"amount": "10", "currency": "USD"},
        "existing_position_amount": {"amount": "0", "currency": "USD"},
        "currency": "USD",
    }
    model = PerAssetDeploymentInput.model_validate(raw)
    assert model.remaining_target_gap_amount.amount == 10


def test_cross_account_holding_fails():
    payload = cloned_payload()
    payload["existing_bond_holdings"][0]["broker_account_id"] = "TW-OTHER"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)


def test_us_budget_not_expanded_by_other_broker_cash():
    payload = cloned_payload()
    payload["TW_LOCAL_BROKER"] = {"broker_cash_available": {"amount": "10000000", "currency": "TWD"}}
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"
    assert any(issue.code == "SCHEMA_VALIDATION_ERROR" for issue in result.issues)


def test_bank_funding_is_rejected_explicitly():
    payload = cloned_payload()
    payload["bank_cash_available"] = {"amount": "999999", "currency": "TWD"}
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"
    assert any(issue.code == "BANK_FUNDING_OUT_OF_SCOPE" for issue in result.issues)


def test_upstream_three_bucket_context_sum_validation_only():
    from v75_runtime.models import UpstreamFundingContext
    valid = UpstreamFundingContext.model_validate({
        "new_investment_cash_total": {"amount": "1000000", "currency": "TWD"},
        "tw_local_broker_new_investment_amount": {"amount": "300000", "currency": "TWD"},
        "tw_sub_brokerage_new_investment_amount": {"amount": "200000", "currency": "TWD"},
        "us_broker_new_investment_amount": {"amount": "500000", "currency": "TWD"},
    })
    assert valid.new_investment_cash_total.amount == 1000000


def test_upstream_three_bucket_context_sum_mismatch_fails_without_guessing():
    from v75_runtime.models import UpstreamFundingContext
    with pytest.raises(ValidationError):
        UpstreamFundingContext.model_validate({
            "new_investment_cash_total": {"amount": "1000000", "currency": "TWD"},
            "tw_local_broker_new_investment_amount": {"amount": "300000", "currency": "TWD"},
            "tw_sub_brokerage_new_investment_amount": {"amount": "200000", "currency": "TWD"},
            "us_broker_new_investment_amount": {"amount": "400000", "currency": "TWD"},
        })


def test_alias_conflict_comparison_uses_canonical_money_semantics_not_raw_json_form():
    raw = {
        "asset_id": "SGOV",
        "remaining_target_gap": {"amount": 10, "currency": "usd"},
        "remaining_target_gap_amount": {"amount": "10.0", "currency": "USD"},
        "existing_position_amount": {"amount": "0", "currency": "USD"},
        "currency": "USD",
    }
    model = PerAssetDeploymentInput.model_validate(raw)
    assert model.remaining_target_gap_amount.amount == 10
    assert model.remaining_target_gap_amount.currency == "USD"


def test_duplicate_per_asset_inputs_are_rejected_as_ambiguous_canonical_input():
    payload = cloned_payload()
    payload["per_asset_inputs"].append(dict(payload["per_asset_inputs"][0]))
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)
