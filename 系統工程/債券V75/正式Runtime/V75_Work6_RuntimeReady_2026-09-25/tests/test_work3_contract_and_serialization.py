import json
from decimal import Decimal

from helpers import cloned_payload
from v75_runtime import V75RunInput
from v75_runtime.work3 import TW_GENERIC_CORE_WEIGHTS, US_GENERIC_CORE_WEIGHTS, WORK3_ENGINE_VERSION, build_work3_state
from v75_runtime.work3_models import Work3State


def valid_payload():
    p = cloned_payload()
    p["existing_bond_holdings"] = [
        {"asset_id": "SGOV", "amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "amount": {"amount": "100", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["target_bond_holdings"] = [
        {"asset_id": "SGOV", "target_amount": {"amount": "700", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "target_amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["authorized_universe"] = ["SGOV", "SPSB"]
    return p


def test_work3_engine_version_is_explicit():
    assert WORK3_ENGINE_VERSION == "V75_WORK3_ELIGIBILITY_BUCKET_SGOV_v1.0.1"


def test_frozen_core_weights_are_exact():
    assert US_GENERIC_CORE_WEIGHTS == {"SGOV": Decimal("70"), "SPSB": Decimal("30")}
    assert TW_GENERIC_CORE_WEIGHTS == {"00859B": Decimal("80"), "00860B": Decimal("20")}


def test_work3_state_json_roundtrip():
    s = build_work3_state(V75RunInput.model_validate(valid_payload()))
    payload = json.loads(s.model_dump_json())
    rebuilt = Work3State.model_validate(payload)
    assert rebuilt == s


def test_long_term_bucket_lines_publish_template_weights_only_for_generic_core():
    s = build_work3_state(V75RunInput.model_validate(valid_payload()))
    weights = {x.asset_id: x.template_weight_pct.value for x in s.long_term_bucket_lines}
    assert weights == {"SGOV": Decimal("70"), "SPSB": Decimal("30")}


def test_null_strategic_bond_weight_does_not_invent_portfolio_base_or_block_explicit_account_targets():
    p = valid_payload()
    p["strategic_bond_weight_b0"] = None
    s = build_work3_state(V75RunInput.model_validate(p))
    assert s.work3_complete
    assert s.bond_long_term_target.amount == Decimal("1000")


def test_life_stage_code_change_does_not_reallocate_single_account_targets():
    p1 = valid_payload()
    p2 = valid_payload()
    p1["life_stage_code"] = "ACCUMULATION"
    p2["life_stage_code"] = "RETIREMENT"
    s1 = build_work3_state(V75RunInput.model_validate(p1))
    s2 = build_work3_state(V75RunInput.model_validate(p2))
    assert s1.bond_long_term_target == s2.bond_long_term_target
    assert s1.bucket_reconciliation == s2.bucket_reconciliation
    assert s1.life_stage_code_passthrough != s2.life_stage_code_passthrough


def test_core_ratio_validation_supports_exact_decimal_amounts():
    p = valid_payload()
    p["target_bond_holdings"][0]["target_amount"]["amount"] = "70.0000"
    p["target_bond_holdings"][1]["target_amount"]["amount"] = "30.0000"
    s = build_work3_state(V75RunInput.model_validate(p))
    assert s.work3_complete
    assert s.bucket_reconciliation.us_core_ratio_valid is True


def test_zero_targets_produce_zero_long_term_target_without_forcing_cross_account_allocation():
    p = valid_payload()
    p["target_bond_holdings"] = []
    p["existing_bond_holdings"] = []
    p["sgov_bond_bucket_amount"] = {"status": "UNKNOWN", "value": None}
    s = build_work3_state(V75RunInput.model_validate(p))
    assert s.work3_complete
    assert s.bond_long_term_target.amount == Decimal("0")
    assert s.bucket_reconciliation.us_core_ratio_valid is None
    assert s.bucket_reconciliation.tw_core_ratio_valid is None


def test_bndw_existing_only_is_emitted_with_zero_gap_for_later_existing_position_management():
    p = valid_payload()
    p["authorized_universe"].append("BNDW")
    p["existing_bond_holdings"].append({"asset_id": "BNDW", "amount": {"amount": "12", "currency": "USD"}, "broker_account_id": "US-001"})
    s = build_work3_state(V75RunInput.model_validate(p))
    row = next(x for x in s.per_asset_inputs if x.asset_id == "BNDW")
    assert row.eligibility_state == "INELIGIBLE_NEW_ALLOCATION"
    assert row.remaining_target_gap_amount.amount == Decimal("0")
    assert row.existing_position_amount.amount == Decimal("12")


def test_work3_source_lineage_appends_engine_version_without_destroying_upstream_lineage():
    p = valid_payload()
    p["source_lineage"] = ["WORK1_RECHECK2", "WORK2_RECHECK_FINAL"]
    s = build_work3_state(V75RunInput.model_validate(p))
    assert s.source_lineage == ["WORK1_RECHECK2", "WORK2_RECHECK_FINAL", WORK3_ENGINE_VERSION]
