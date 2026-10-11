from helpers import cloned_payload
from v75_runtime.models import V75RunInput


def test_deterministic_round_trip_serialization():
    first = V75RunInput.model_validate(cloned_payload())
    serialized = first.model_dump_json(round_trip=True)
    second = V75RunInput.model_validate_json(serialized)
    assert first == second
    assert second.model_dump(mode="json") == first.model_dump(mode="json")


def test_json_schema_generation_is_deterministic_for_same_process():
    s1 = V75RunInput.model_json_schema()
    s2 = V75RunInput.model_json_schema()
    assert s1 == s2


def test_all_canonical_models_generate_json_schema():
    from v75_runtime.models import (
        BasisPointValue,
        BrokerAccountContext,
        HoldingSnapshot,
        Money,
        MoneyValue,
        PerAssetDecision,
        PerAssetDeploymentInput,
        PerAssetPredicateEvidence,
        PercentValue,
        PercentagePointValue,
        PredicateResult,
        RuntimeStateModel,
        SettlementStateModel,
        SnapshotModel,
        TargetHoldingSnapshot,
        UpstreamFundingContext,
        V75RunInput,
        V75RunOutput,
    )
    models = [
        BasisPointValue, BrokerAccountContext, HoldingSnapshot, Money, MoneyValue,
        PerAssetDecision, PerAssetDeploymentInput, PerAssetPredicateEvidence,
        PercentValue, PercentagePointValue, PredicateResult, RuntimeStateModel,
        SettlementStateModel, SnapshotModel, TargetHoldingSnapshot,
        UpstreamFundingContext, V75RunInput, V75RunOutput,
    ]
    for model in models:
        schema = model.model_json_schema()
        assert schema.get("title") == model.__name__


def test_package_star_exports_include_canonical_models_and_states():
    import v75_runtime
    for name in ("V75RunInput", "V75RunOutput", "PredicateResult", "BrokerDomainType", "FreshnessState"):
        assert name in v75_runtime.__all__
        assert hasattr(v75_runtime, name)


def test_snapshot_payload_rejects_non_json_native_object_before_serialization():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import SnapshotModel

    class Opaque:
        pass

    with pytest.raises(ValidationError):
        SnapshotModel.model_validate({
            "data_timestamp": "2026-09-24T09:00:00+08:00",
            "data_source": "TEST",
            "freshness_state": "FRESH",
            "source_lineage": ["TEST"],
            "payload": {"opaque": Opaque()},
        })


def test_snapshot_payload_rejects_non_finite_json_numbers():
    import pytest
    from pydantic import ValidationError
    from v75_runtime.models import SnapshotModel

    with pytest.raises(ValidationError):
        SnapshotModel.model_validate({
            "data_timestamp": "2026-09-24T09:00:00+08:00",
            "data_source": "TEST",
            "freshness_state": "FRESH",
            "source_lineage": ["TEST"],
            "payload": {"bad": float("nan")},
        })


def test_generic_json_payloads_round_trip_without_type_loss():
    from v75_runtime.models import SnapshotModel

    first = SnapshotModel.model_validate({
        "data_timestamp": "2026-09-24T09:00:00+08:00",
        "data_source": "TEST",
        "freshness_state": "FRESH",
        "source_lineage": ["TEST"],
        "payload": {"nested": {"numbers": [1, 2.5], "flag": True, "none": None, "text": "ok"}},
    })
    serialized = first.model_dump_json(round_trip=True)
    second = SnapshotModel.model_validate_json(serialized)
    assert second == first
