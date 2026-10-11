import pytest
from pydantic import ValidationError

from helpers import cloned_payload
from v75_runtime.models import PerAssetPredicateEvidence, V75RunInput


def pred(predicate_id="PRED-003", as_of="2026-09-24T09:00:00+08:00"):
    aggregate = "MIXED_STABLE" if predicate_id == "PRED-003" else "NORMAL"
    return {
        "predicate_id": predicate_id,
        "predicate_version": "V75_PREDICATE_PARAMS_v1.0.3",
        "aggregate_state": aggregate,
        "sub_states": [aggregate],
        "assessment_status": "VALID",
        "as_of": as_of,
        "source_lineage": ["TEST"],
        "input_freshness_state": "FRESH",
        "reason_codes": [],
        "required_input_missing": [],
    }


def test_per_asset_predicate_evidence_scopes_result_without_changing_predicate_contract():
    payload = cloned_payload()
    payload["per_asset_predicate_evidence"] = [{"asset_id": "SPSB", "predicate_results": [pred()]}]
    model = V75RunInput.model_validate(payload)
    assert model.per_asset_predicate_evidence[0].asset_id == "SPSB"
    assert model.per_asset_predicate_evidence[0].predicate_results[0].predicate_id == "PRED-003"


def test_per_asset_predicate_evidence_must_reference_deployment_asset():
    payload = cloned_payload()
    payload["per_asset_predicate_evidence"] = [{"asset_id": "NOT-IN-INPUT", "predicate_results": [pred()]}]
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)


def test_duplicate_predicate_ids_in_one_asset_evidence_are_rejected():
    with pytest.raises(ValidationError):
        PerAssetPredicateEvidence.model_validate({"asset_id": "SPSB", "predicate_results": [pred(), pred()]})


def test_predicate_result_cannot_be_future_dated_relative_to_run():
    payload = cloned_payload()
    payload["per_asset_predicate_evidence"] = [{
        "asset_id": "SPSB",
        "predicate_results": [pred(as_of="2026-09-25T09:00:00+08:00")],
    }]
    with pytest.raises(ValidationError):
        V75RunInput.model_validate(payload)
