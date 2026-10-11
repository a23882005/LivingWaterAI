from helpers import cloned_payload, unknown_money
from v75_runtime.validation import validate_v75_run_input


def test_unsettled_positive_budget_rejected():
    payload = cloned_payload()
    payload["funding_settlement_status"] = "UNSETTLED"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"


def test_declared_but_not_available_cash_cannot_be_executable():
    payload = cloned_payload()
    payload["broker_cash_available"] = {"status": "KNOWN", "value": {"amount": "0", "currency": "USD"}}
    payload["broker_cash_unsettled"] = {"status": "KNOWN", "value": {"amount": "1000", "currency": "USD"}}
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"


def test_unknown_available_cash_with_positive_budget_safe_fails_insufficient_data():
    payload = cloned_payload()
    payload["broker_cash_available"] = unknown_money()
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"


def test_unknown_settlement_with_positive_budget_safe_fails_insufficient_data():
    payload = cloned_payload()
    payload["funding_settlement_status"] = "UNKNOWN"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"


def test_stale_required_snapshot_safe_fails_insufficient_data():
    payload = cloned_payload()
    payload["market_snapshot"]["freshness_state"] = "STALE"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"
    assert any(i.code == "STALE_REQUIRED_INPUT" for i in result.issues)


def test_mixed_timezone_awareness_safe_fails_instead_of_raising_typeerror():
    payload = cloned_payload()
    payload["analysis_timestamp"] = "2026-09-24T18:00:00"
    payload["market_snapshot"]["data_timestamp"] = "2026-09-24T17:00:00+00:00"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"
    assert any(i.code == "SCHEMA_VALIDATION_ERROR" for i in result.issues)


def test_missing_required_strategic_bond_weight_field_is_invalid_input():
    payload = cloned_payload()
    payload.pop("strategic_bond_weight_b0")
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INVALID_INPUT"


def test_unknown_required_snapshot_uses_missing_not_stale_reason_code():
    payload = cloned_payload()
    payload["market_snapshot"]["freshness_state"] = "UNKNOWN"
    result = validate_v75_run_input(payload)
    assert result.disposition.value == "INSUFFICIENT_DATA"
    assert any(i.code == "MISSING_REQUIRED_INPUT" for i in result.issues)
    assert not any(i.code == "STALE_REQUIRED_INPUT" and i.path == "market_snapshot.freshness_state" for i in result.issues)
