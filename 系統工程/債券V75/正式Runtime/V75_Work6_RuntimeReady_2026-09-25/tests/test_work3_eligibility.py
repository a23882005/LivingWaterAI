from decimal import Decimal

from helpers import cloned_payload
from v75_runtime import V75RunInput
from v75_runtime.work3 import build_work3_state
from v75_runtime.work3_models import Work3EligibilityState


def us_payload():
    p = cloned_payload()
    p["existing_bond_holdings"] = [
        {"asset_id": "SGOV", "amount": {"amount": "999", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "amount": {"amount": "100", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["target_bond_holdings"] = [
        {"asset_id": "SGOV", "target_amount": {"amount": "700", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "SPSB", "target_amount": {"amount": "300", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["authorized_universe"] = ["SGOV", "SPSB"]
    return p


def state(payload=None):
    return build_work3_state(V75RunInput.model_validate(payload or us_payload()))


def assessment(s, asset):
    return next(x for x in s.eligibility_assessments if x.asset_id == asset)


def test_generic_us_core_is_structurally_eligible():
    s = state()
    assert assessment(s, "SGOV").eligibility_state == Work3EligibilityState.ELIGIBLE
    assert assessment(s, "SPSB").eligibility_state == Work3EligibilityState.ELIGIBLE
    assert s.work3_complete


def test_supported_non_core_can_be_eligible_only_when_authorized():
    p = us_payload()
    p["authorized_universe"].append("IEF")
    p["existing_bond_holdings"].append({"asset_id": "IEF", "amount": {"amount": "25", "currency": "USD"}, "broker_account_id": "US-001"})
    s = state(p)
    a = assessment(s, "IEF")
    assert a.eligibility_state == Work3EligibilityState.ELIGIBLE
    assert a.new_long_term_target_allowed is True
    assert "AUTHORIZED_NON_CORE_NO_GENERIC_TEMPLATE_WEIGHT" in a.reason_codes


def test_bndw_is_never_new_allocation_eligible_but_existing_management_remains_allowed():
    p = us_payload()
    p["authorized_universe"].append("BNDW")
    p["existing_bond_holdings"].append({"asset_id": "BNDW", "amount": {"amount": "50", "currency": "USD"}, "broker_account_id": "US-001"})
    s = state(p)
    a = assessment(s, "BNDW")
    assert a.eligibility_state == Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION
    assert a.new_long_term_target_allowed is False
    assert a.existing_position_management_allowed is True
    assert s.work3_complete


def test_positive_bndw_target_fails_closed():
    p = us_payload()
    p["authorized_universe"].append("BNDW")
    p["target_bond_holdings"].append({"asset_id": "BNDW", "target_amount": {"amount": "10", "currency": "USD"}, "broker_account_id": "US-001"})
    s = state(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert not s.work3_complete
    assert s.per_asset_inputs == []
    assert "POSITIVE_TARGET_PROHIBITED_BY_SOT" in s.reason_codes


def test_unknown_authorized_asset_propagates_unknown_and_insufficient_data():
    p = us_payload()
    p["authorized_universe"].append("MYSTERY_BOND")
    s = state(p)
    assert assessment(s, "MYSTERY_BOND").eligibility_state == Work3EligibilityState.UNKNOWN
    assert s.evaluation_state.value == "INSUFFICIENT_DATA"
    assert "eligibility:MYSTERY_BOND" in s.missing_required_fields
    assert s.per_asset_inputs == []


def test_conditional_00985b_does_not_guess_without_missing_preference_contract():
    p = _tw_local_payload()
    p["authorized_universe"].append("00985B")
    s = state(p)
    assert assessment(s, "00985B").eligibility_state == Work3EligibilityState.UNKNOWN
    assert s.evaluation_state.value == "INSUFFICIENT_DATA"


def test_existing_holding_outside_authorized_universe_requires_review():
    p = us_payload()
    p["existing_bond_holdings"].append({"asset_id": "IEF", "amount": {"amount": "10", "currency": "USD"}, "broker_account_id": "US-001"})
    s = state(p)
    assert s.evaluation_state.value == "REVIEW_REQUIRED"
    assert "EXISTING_HOLDING_OUTSIDE_AUTHORIZED_UNIVERSE" in s.reason_codes
    assert s.per_asset_inputs == []


def test_positive_target_outside_authorized_universe_is_invalid():
    p = us_payload()
    p["target_bond_holdings"].append({"asset_id": "IEF", "target_amount": {"amount": "10", "currency": "USD"}, "broker_account_id": "US-001"})
    s = state(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "POSITIVE_TARGET_NOT_AUTHORIZED" in s.reason_codes


def test_duplicate_authorized_universe_case_collision_is_invalid():
    p = us_payload()
    p["authorized_universe"] = ["SGOV", "sgov", "SPSB"]
    s = state(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "DUPLICATE_AUTHORIZED_UNIVERSE_ASSET_ID" in s.reason_codes


def test_blank_authorized_universe_asset_is_invalid():
    p = us_payload()
    p["authorized_universe"].append("   ")
    s = state(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "BLANK_AUTHORIZED_UNIVERSE_ASSET_ID" in s.reason_codes


def test_eligibility_assessment_preserves_authorization_fact():
    p = us_payload()
    p["authorized_universe"].append("SHY")
    s = state(p)
    assert assessment(s, "SHY").authorized is True


def test_life_stage_code_is_passthrough_not_machine_mapped():
    p = us_payload()
    p["life_stage_code"] = "ACCUMULATION"
    s = state(p)
    assert s.life_stage_code_passthrough == "ACCUMULATION"
    assert "LIFE_STAGE_CODE_PASSTHROUGH_NO_UNFROZEN_MACHINE_MAPPING" in s.reason_codes



def _tw_local_payload():
    p = us_payload()
    p["broker_account_id"] = "TW-001"
    p["broker_domain_type"] = "TW_LOCAL_BROKER"
    p["currency"] = "TWD"
    p["bond_executable_budget"] = {"amount": "100000", "currency": "TWD"}
    for f, a in (("broker_cash_total", "120000"), ("broker_cash_available", "100000"), ("broker_cash_unsettled", "20000"), ("broker_cash_reserved", "0")):
        p[f] = {"status": "KNOWN", "value": {"amount": a, "currency": "TWD"}}
    p["sgov_bond_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["sgov_dry_powder_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["existing_bond_holdings"] = []
    p["target_bond_holdings"] = [
        {"asset_id": "00859B", "target_amount": {"amount": "80000", "currency": "TWD"}, "broker_account_id": "TW-001"},
        {"asset_id": "00860B", "target_amount": {"amount": "20000", "currency": "TWD"}, "broker_account_id": "TW-001"},
    ]
    p["authorized_universe"] = ["00859B", "00860B"]
    p["per_asset_inputs"] = []
    return p


def test_us_broker_rejects_active_taiwan_listed_core_target():
    p = us_payload()
    p["existing_bond_holdings"] = []
    p["target_bond_holdings"] = [
        {"asset_id": "00859B", "target_amount": {"amount": "800", "currency": "USD"}, "broker_account_id": "US-001"},
        {"asset_id": "00860B", "target_amount": {"amount": "200", "currency": "USD"}, "broker_account_id": "US-001"},
    ]
    p["authorized_universe"] = ["00859B", "00860B"]
    p["sgov_bond_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["sgov_dry_powder_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["per_asset_inputs"] = []
    s = state(p)
    assert not s.work3_complete
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "BROKER_DOMAIN_ASSET_MISMATCH" in s.reason_codes


def test_tw_local_broker_rejects_active_us_listed_core_target():
    p = _tw_local_payload()
    p["target_bond_holdings"] = [
        {"asset_id": "SGOV", "target_amount": {"amount": "70000", "currency": "TWD"}, "broker_account_id": "TW-001"},
        {"asset_id": "SPSB", "target_amount": {"amount": "30000", "currency": "TWD"}, "broker_account_id": "TW-001"},
    ]
    p["authorized_universe"] = ["SGOV", "SPSB"]
    p["sgov_bond_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}}
    p["sgov_dry_powder_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}}
    s = state(p)
    assert not s.work3_complete
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "BROKER_DOMAIN_ASSET_MISMATCH" in s.reason_codes


def test_tw_sub_brokerage_accepts_us_listed_core_target():
    p = us_payload()
    p["broker_account_id"] = "SUB-001"
    p["broker_domain_type"] = "TW_SUB_BROKERAGE"
    for row in p["existing_bond_holdings"]:
        row["broker_account_id"] = "SUB-001"
    for row in p["target_bond_holdings"]:
        row["broker_account_id"] = "SUB-001"
    p["per_asset_inputs"] = []
    s = state(p)
    assert s.work3_complete
    assert assessment(s, "SGOV").eligibility_state == Work3EligibilityState.ELIGIBLE
    assert assessment(s, "SPSB").eligibility_state == Work3EligibilityState.ELIGIBLE


def test_authorized_only_cross_domain_candidate_does_not_block_current_account():
    p = us_payload()
    p["authorized_universe"].extend(["00859B", "00860B"])
    s = state(p)
    assert s.work3_complete
    assert assessment(s, "00859B").eligibility_state == Work3EligibilityState.INELIGIBLE
    assert assessment(s, "00860B").eligibility_state == Work3EligibilityState.INELIGIBLE
