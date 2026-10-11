import pytest
from pydantic import ValidationError

from v75_runtime.models import PredicateResult
from v75_runtime.validation import validate_predicate_result


def valid_pred(**overrides):
    data = {
        "predicate_id": "PRED-003",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "aggregate_state": "NORMALIZING",
        "sub_states": ["NORMALIZING"],
        "assessment_status": "VALID",
        "as_of": "2026-09-24T09:00:00+08:00",
        "source_lineage": ["FRED:DGS10"],
        "input_freshness_state": "FRESH",
        "reason_codes": [],
        "required_input_missing": [],
    }
    data.update(overrides)
    return data


def test_valid_requires_aggregate_in_substates():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(sub_states=["MIXED_STABLE"]))


def test_valid_requires_non_null_aggregate():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(aggregate_state=None))


def test_non_valid_must_clear_semantic_state():
    p = valid_pred(assessment_status="INSUFFICIENT_DATA", aggregate_state=None, sub_states=[], required_input_missing=["yield_delta_5bd_bps"])
    result = PredicateResult.model_validate(p)
    assert result.aggregate_state is None
    assert result.sub_states == []


def test_non_valid_cannot_carry_guessed_normal():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(assessment_status="INSUFFICIENT_DATA", aggregate_state="MIXED_STABLE", sub_states=["MIXED_STABLE"]))


def test_wrong_predicate_version_requires_review_not_schema_guess():
    from v75_runtime.validation import validate_predicate_result
    result = validate_predicate_result(valid_pred(predicate_version="V75_PREDICATE_PARAMS_v1.0.2"))
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any(i.code == "VERSION_MISMATCH" for i in result.issues)


def test_generic_assessment_token_not_semantic_substate():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(aggregate_state="NORMALIZING", sub_states=["NORMALIZING", "SHORT_HISTORY"]))


def test_pred010_component_state_cannot_leak_to_common_substates():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(
            predicate_id="PRED-010",
            aggregate_state="ETF_QUALITY_NORMAL",
            sub_states=["ETF_QUALITY_NORMAL", "STRUCTURE_OK"],
        ))


def test_valid_predicate_cannot_be_stale():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(input_freshness_state="STALE"))


def test_pred003_legacy_display_alias_normalizes_once():
    model = PredicateResult.model_validate(valid_pred(aggregate_state="MIXED/STABLE", sub_states=["MIXED/STABLE"]))
    assert model.aggregate_state == "MIXED_STABLE"
    assert model.sub_states == ["MIXED_STABLE"]

def test_substates_must_follow_precedence_order():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(
            predicate_id="PRED-009",
            aggregate_state="RIGHT_CONFIRM",
            sub_states=["LEFT_MATURE", "RIGHT_CONFIRM"],
        ))


def test_aggregate_must_be_highest_precedence_state_not_merely_member():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(
            predicate_id="PRED-005",
            aggregate_state="SURGE",
            sub_states=["EXTREME", "SURGE"],
        ))


def test_old_predicate_version_preflights_to_review_even_with_legacy_schema_shape():
    legacy_payload = {
        "predicate_id": "PRED-003",
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.2",
        "state": "MIXED/STABLE",
        "assessment_status": "VALID",
        "as_of": "2026-09-24T09:00:00+08:00",
        "source_lineage": ["LEGACY"],
        "input_freshness_state": "FRESH",
    }
    result = validate_predicate_result(legacy_payload)
    assert result.disposition.value == "REVIEW_REQUIRED"
    assert any(i.code == "VERSION_MISMATCH" for i in result.issues)


def test_valid_predicate_requires_fresh_not_not_applicable_freshness():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(input_freshness_state="NOT_APPLICABLE"))


def test_valid_predicate_cannot_claim_missing_required_inputs():
    with pytest.raises(ValidationError):
        PredicateResult.model_validate(valid_pred(required_input_missing=["required_field_x"]))


def test_missing_predicate_version_is_insufficient_data_in_safe_validator():
    payload = valid_pred()
    payload.pop("predicate_version")
    result = validate_predicate_result(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"
    assert any(i.code == "MISSING_REQUIRED_INPUT" for i in result.issues)
