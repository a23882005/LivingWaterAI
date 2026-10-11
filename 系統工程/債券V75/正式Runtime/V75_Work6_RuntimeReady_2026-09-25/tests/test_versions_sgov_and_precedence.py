from decimal import Decimal

from helpers import cloned_payload
from v75_runtime.constants import DEPLOYMENT_PCT_CONTRACT, GLOBAL_EVALUATION_PRECEDENCE
from v75_runtime.enums import DeploymentState
from v75_runtime.validation import validate_v75_run_input


def test_predicate_version_is_only_v103_and_mismatch_is_review_required():
    payload = cloned_payload()
    payload["predicate_version"] = "V75_PREDICATE_PARAMS_v1.0.2"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any(i.code == "VERSION_MISMATCH" for i in result.issues)


def test_rule_version_mismatch_can_safe_fail_review_required_without_guessing():
    payload = cloned_payload()
    result = validate_v75_run_input(payload, expected_rule_version="SOME_NEW_RULE")
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any(i.code == "VERSION_MISMATCH" for i in result.issues)


def test_deployment_parameter_version_mismatch_is_review_required():
    payload = cloned_payload()
    result = validate_v75_run_input(payload, expected_deployment_parameter_version="P0-02-EXPECTED")
    assert result.disposition.value == "REVIEW_REQUIRED"


def test_sgov_roles_remain_distinct_fields():
    payload = cloned_payload()
    payload["sgov_bond_bucket_amount"]["value"]["amount"] = "111"
    payload["sgov_dry_powder_bucket_amount"]["value"]["amount"] = "222"
    result = validate_v75_run_input(payload)
    assert result.accepted
    assert result.model.sgov_bond_bucket_amount.value.amount == Decimal("111")
    assert result.model.sgov_dry_powder_bucket_amount.value.amount == Decimal("222")


def test_global_precedence_exactly_preserved():
    assert GLOBAL_EVALUATION_PRECEDENCE == (
        "DATA_QUALITY_VERSION_SETTLEMENT_ACCOUNT_ISOLATION",
        "ETF_STRUCTURE_LIQUIDITY_SEVERE_ABNORMAL",
        "LIQUIDITY_SYSTEM_STATE",
        "INFLATION_LOSS_OF_CONTROL",
        "CREDIT_CRISIS_STRESS",
        "FED_POLICY_RATE_HAWKISH_REPRICING",
        "TREASURY_YIELD_VELOCITY",
        "YIELD_ATTRACTIVENESS",
        "TECHNICAL_ZONE",
        "V75_ASSET_SPECIFIC_BRANCH",
        "P0_02_DEPLOYMENT_MAPPING",
    )


def test_deployment_mapping_is_data_contract_only_and_exact():
    assert DEPLOYMENT_PCT_CONTRACT == {
        DeploymentState.HARD_WAIT: Decimal("0"),
        DeploymentState.PAUSE: Decimal("0"),
        DeploymentState.SMALL_BUY: Decimal("25"),
        DeploymentState.LEFT_BUY: Decimal("50"),
        DeploymentState.DEEP_LEFT_BUY: Decimal("75"),
        DeploymentState.RIGHT_COMPLETE: Decimal("100"),
    }


def test_per_asset_decision_rejects_noncanonical_mapping_and_numeric_trim():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import PerAssetDecision
    with pytest.raises(ValidationError):
        PerAssetDecision.model_validate({
            "asset_id": "SPSB", "deployment_state": "SMALL_BUY",
            "deployment_pct": {"value": "30", "unit": "PERCENT"},
            "gate_state": "PASS", "evaluation_state": "COMPLETE"
        })
    with pytest.raises(ValidationError):
        PerAssetDecision.model_validate({
            "asset_id": "SPSB", "deployment_state": "SMALL_BUY",
            "deployment_pct": {"value": "25", "unit": "PERCENT"},
            "existing_reduction_pct": {"value": "10", "unit": "PERCENT"},
            "gate_state": "PASS", "evaluation_state": "COMPLETE"
        })


def test_v75_undeployed_to_sgov_output_is_us_broker_usd_only():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput
    common = {
        "run_id": "R", "rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "TW-1", "broker_domain_type": "TW_LOCAL_BROKER", "currency": "TWD",
        "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}},
        "v75_undeployed_to_sgov": {"amount": "10", "currency": "TWD"},
        "formal_output_eligible": False, "evaluation_state": "INSUFFICIENT_DATA"
    }
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(common)


def test_missing_predicate_version_is_insufficient_data_not_guessed():
    payload = cloned_payload()
    payload.pop("predicate_version")
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"
    assert any(i.code == "MISSING_REQUIRED_INPUT" for i in result.issues)


def test_final_sgov_dry_powder_aggregate_field_is_not_in_v75_output_schema():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            "run_id": "R", "rule_version": "債券V75.md v2.7.0",
            "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
            "deployment_parameter_version": "P0-02-FROZEN",
            "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
            "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "USD"}},
            "v75_undeployed_to_sgov": {"amount": "10", "currency": "USD"},
            "SGOV_DRY_POWDER_BUCKET": {"amount": "10", "currency": "USD"},
            "formal_output_eligible": True, "evaluation_state": "COMPLETE"
        })


def test_version_mismatch_preflights_before_legacy_schema_errors():
    payload = cloned_payload()
    payload["predicate_version"] = "V75_PREDICATE_PARAMS_v1.0.2"
    payload["legacy_v102_only_field"] = {"state": "OLD"}
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any(i.code == "VERSION_MISMATCH" for i in result.issues)


def test_output_all_money_fields_must_match_output_currency():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput
    base = {
        "run_id": "R", "rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
        "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "10", "currency": "USD"}},
        "formal_output_eligible": True, "evaluation_state": "COMPLETE"
    }
    bad_target = dict(base)
    bad_target["bond_long_term_target"] = {"amount": "100", "currency": "TWD"}
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(bad_target)

    bad_sgov = dict(base)
    bad_sgov["sgov_bond_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "10", "currency": "TWD"}}
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(bad_sgov)

    bad_decision = dict(base)
    bad_decision["per_asset_decisions"] = [{
        "asset_id": "SPSB",
        "deploy_amount": {"amount": "10", "currency": "TWD"},
        "gate_state": "PASS",
        "evaluation_state": "COMPLETE",
    }]
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(bad_decision)


def test_nested_predicate_version_mismatch_is_review_required_before_model_parse():
    payload = cloned_payload()
    payload["predicate_results"] = [{
        "predicate_id": "PRED-003",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.2",
        "aggregate_state": "MIXED_STABLE",
        "sub_states": ["MIXED_STABLE"],
        "assessment_status": "VALID",
        "as_of": "2026-09-24T09:00:00+08:00",
        "source_lineage": ["OLD"],
        "input_freshness_state": "FRESH",
    }]
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any("predicate_results[0].predicate_version" == i.path for i in result.issues)


def test_output_schema_rejects_noncanonical_predicate_version():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            "run_id": "R", "rule_version": "債券V75.md v2.7.0",
            "predicate_version": "V75_PREDICATE_PARAMS_v1.0.2",
            "deployment_parameter_version": "P0-02-FROZEN",
            "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
            "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "USD"}},
            "formal_output_eligible": False, "evaluation_state": "REVIEW_REQUIRED"
        })


def test_direct_models_reject_wrong_frozen_rule_version():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunInput, V75RunOutput

    bad_input = cloned_payload()
    bad_input["expected_rule_version"] = "債券V75.md v2.6.0"
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(bad_input)

    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            "run_id": "R", "rule_version": "債券V75.md v2.6.0",
            "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
            "deployment_parameter_version": "P0-02-FROZEN",
            "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
            "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "USD"}},
            "formal_output_eligible": False, "evaluation_state": "REVIEW_REQUIRED"
        })


def test_frozen_mapping_contracts_are_actually_immutable():
    import pytest
    from v75_runtime.constants import DEPLOYMENT_PCT_CONTRACT, PREDICATE_STATE_PRECEDENCE
    from v75_runtime.enums import DeploymentState

    with pytest.raises(TypeError):
        DEPLOYMENT_PCT_CONTRACT[DeploymentState.SMALL_BUY] = Decimal("30")
    with pytest.raises(TypeError):
        PREDICATE_STATE_PRECEDENCE["PRED-003"] = ("BROKEN",)


def test_final_sgov_dry_powder_cannot_be_smuggled_inside_bond_allocation_final():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            "run_id": "R", "rule_version": "債券V75.md v2.7.0",
            "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
            "deployment_parameter_version": "P0-02-FROZEN",
            "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
            "bond_allocation_final": {"integration": {"SGOV_DRY_POWDER_BUCKET": {"amount": "10", "currency": "USD"}}},
            "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "USD"}},
            "formal_output_eligible": False, "evaluation_state": "REVIEW_REQUIRED"
        })


def test_nested_missing_predicate_version_is_insufficient_data():
    payload = cloned_payload()
    payload["predicate_results"] = [{
        "predicate_id": "PRED-003",
        "aggregate_state": "MIXED_STABLE",
        "sub_states": ["MIXED_STABLE"],
        "assessment_status": "VALID",
        "as_of": "2026-09-24T09:00:00+08:00",
        "source_lineage": ["NO_VERSION"],
        "input_freshness_state": "FRESH",
    }]
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"
    assert any(i.path == "predicate_results[0].predicate_version" for i in result.issues)


def test_output_rejects_duplicate_or_blank_per_asset_decision_ids():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput

    base = {
        "run_id": "R", "rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
        "sgov_bond_bucket_amount": {"status": "UNKNOWN", "value": None},
        "formal_output_eligible": False, "evaluation_state": "INSUFFICIENT_DATA",
    }
    duplicate = dict(base)
    duplicate["per_asset_decisions"] = [
        {"asset_id": "SPSB", "gate_state": "INSUFFICIENT_DATA", "evaluation_state": "INSUFFICIENT_DATA"},
        {"asset_id": "SPSB", "gate_state": "INSUFFICIENT_DATA", "evaluation_state": "INSUFFICIENT_DATA"},
    ]
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(duplicate)

    blank = dict(base)
    blank["per_asset_decisions"] = [
        {"asset_id": "", "gate_state": "INSUFFICIENT_DATA", "evaluation_state": "INSUFFICIENT_DATA"},
    ]
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate(blank)


def test_formal_output_eligibility_state_is_internally_consistent():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput

    common = {
        "run_id": "R", "rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
        "sgov_bond_bucket_amount": {"status": "UNKNOWN", "value": None},
    }

    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            **common,
            "formal_output_eligible": True,
            "evaluation_state": "INSUFFICIENT_DATA",
            "missing_required_fields": ["predicate_results"],
        })

    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({
            **common,
            "formal_output_eligible": True,
            "evaluation_state": "COMPLETE",
            "missing_required_fields": ["predicate_results"],
        })


def test_bond_allocation_final_rejects_opaque_or_non_finite_payloads():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import V75RunOutput

    class Opaque:
        pass

    common = {
        "run_id": "R", "rule_version": "債券V75.md v2.7.0",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "deployment_parameter_version": "P0-02-FROZEN",
        "broker_account_id": "US-1", "broker_domain_type": "US_BROKER", "currency": "USD",
        "sgov_bond_bucket_amount": {"status": "UNKNOWN", "value": None},
        "formal_output_eligible": False, "evaluation_state": "INSUFFICIENT_DATA",
    }
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({**common, "bond_allocation_final": {"opaque": Opaque()}})
    with pytest.raises(ValidationError):
        V75RunOutput.model_validate({**common, "bond_allocation_final": {"bad": float("inf")}})
