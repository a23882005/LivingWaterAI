from decimal import Decimal

from helpers import cloned_payload, unknown_money
from v75_runtime import V75RunInput
from v75_runtime.work3 import build_work3_state


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
    p["sgov_bond_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "300", "currency": "USD"}}
    p["sgov_dry_powder_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "400", "currency": "USD"}}
    return p


def build(p):
    return build_work3_state(V75RunInput.model_validate(p))


def gap(s, asset):
    return next(x for x in s.gap_calculations if x.asset_id == asset)


def pai(s, asset):
    return next(x for x in s.per_asset_inputs if x.asset_id == asset)


def test_us_long_term_bucket_70_30_reconciles():
    s = build(us_payload())
    r = s.bucket_reconciliation
    assert r is not None
    assert r.us_core_ratio_valid is True
    assert r.tw_core_ratio_valid is None
    assert r.us_generic_long_term_target.amount == Decimal("1000")
    assert r.bond_long_term_target.amount == Decimal("1000")
    assert r.target_sum_reconciled is True


def test_us_pair_missing_member_is_invalid():
    p = us_payload()
    p["target_bond_holdings"] = [p["target_bond_holdings"][0]]
    s = build(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "US_GENERIC_CORE_TARGET_RATIO_MISMATCH" in s.reason_codes


def test_us_ratio_mismatch_is_invalid():
    p = us_payload()
    p["target_bond_holdings"][0]["target_amount"]["amount"] = "600"
    p["target_bond_holdings"][1]["target_amount"]["amount"] = "400"
    s = build(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert s.bucket_reconciliation.us_core_ratio_valid is False


def test_duplicate_target_asset_is_invalid():
    p = us_payload()
    p["target_bond_holdings"].append({"asset_id": "SGOV", "target_amount": {"amount": "0", "currency": "USD"}, "broker_account_id": "US-001"})
    s = build(p)
    assert s.evaluation_state.value == "INVALID_INPUT"
    assert "DUPLICATE_TARGET_ASSET_ID" in s.reason_codes


def test_taiwan_long_term_bucket_80_20_reconciles():
    p = us_payload()
    p["broker_account_id"] = "TW-001"
    p["broker_domain_type"] = "TW_LOCAL_BROKER"
    p["currency"] = "TWD"
    p["bond_executable_budget"] = {"amount": "100000", "currency": "TWD"}
    for f, a in (("broker_cash_total", "120000"), ("broker_cash_available", "100000"), ("broker_cash_unsettled", "20000"), ("broker_cash_reserved", "0")):
        p[f] = {"status": "KNOWN", "value": {"amount": a, "currency": "TWD"}}
    p["sgov_bond_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["sgov_dry_powder_bucket_amount"] = {"status": "NOT_APPLICABLE", "value": None}
    p["existing_bond_holdings"] = [
        {"asset_id": "00859B", "amount": {"amount": "20000", "currency": "TWD"}, "broker_account_id": "TW-001"},
        {"asset_id": "00860B", "amount": {"amount": "5000", "currency": "TWD"}, "broker_account_id": "TW-001"},
    ]
    p["target_bond_holdings"] = [
        {"asset_id": "00859B", "target_amount": {"amount": "80000", "currency": "TWD"}, "broker_account_id": "TW-001"},
        {"asset_id": "00860B", "target_amount": {"amount": "20000", "currency": "TWD"}, "broker_account_id": "TW-001"},
    ]
    p["authorized_universe"] = ["00859B", "00860B"]
    p["per_asset_inputs"] = []
    s = build(p)
    assert s.work3_complete
    assert s.bucket_reconciliation.tw_core_ratio_valid is True
    assert s.bucket_reconciliation.tw_generic_long_term_target.amount == Decimal("100000")
    assert gap(s, "00859B").remaining_target_gap_amount.value.amount == Decimal("60000")
    assert gap(s, "00860B").remaining_target_gap_amount.value.amount == Decimal("15000")


def test_sgov_gap_uses_bond_bucket_not_raw_holding_or_dry_powder():
    s = build(us_payload())
    g = gap(s, "SGOV")
    assert g.eligible_existing_amount.value.amount == Decimal("300")
    assert g.remaining_target_gap_amount.value.amount == Decimal("400")
    assert pai(s, "SGOV").existing_position_amount.amount == Decimal("300")


def test_spsb_gap_uses_same_account_existing_holdings():
    s = build(us_payload())
    g = gap(s, "SPSB")
    assert g.eligible_existing_amount.value.amount == Decimal("100")
    assert g.remaining_target_gap_amount.value.amount == Decimal("200")


def test_existing_holdings_multiple_lots_are_summed_same_account():
    p = us_payload()
    p["existing_bond_holdings"].append({"asset_id": "SPSB", "amount": {"amount": "25", "currency": "USD"}, "broker_account_id": "US-001"})
    s = build(p)
    assert gap(s, "SPSB").eligible_existing_amount.value.amount == Decimal("125")
    assert gap(s, "SPSB").remaining_target_gap_amount.value.amount == Decimal("175")


def test_gap_is_floored_at_zero():
    p = us_payload()
    p["existing_bond_holdings"][1]["amount"]["amount"] = "500"
    s = build(p)
    assert gap(s, "SPSB").remaining_target_gap_amount.value.amount == Decimal("0")


def test_positive_sgov_target_with_unknown_bond_bucket_is_insufficient_and_fail_closed():
    p = us_payload()
    p["sgov_bond_bucket_amount"] = unknown_money()
    s = build(p)
    assert s.evaluation_state.value == "INSUFFICIENT_DATA"
    assert "sgov_bond_bucket_amount" in s.missing_required_fields
    assert gap(s, "SGOV").remaining_target_gap_amount.status.value == "UNKNOWN"
    assert s.per_asset_inputs == []


def test_unknown_dry_powder_does_not_block_bond_gap_or_work3_completion():
    p = us_payload()
    p["sgov_dry_powder_bucket_amount"] = unknown_money()
    s = build(p)
    assert s.work3_complete
    assert gap(s, "SGOV").remaining_target_gap_amount.value.amount == Decimal("400")
    assert s.sgov_reconciliation.observed_role_total_amount.status.value == "UNKNOWN"


def test_existing_sgov_with_unknown_bond_role_is_insufficient_even_when_target_zero():
    p = us_payload()
    p["target_bond_holdings"] = []
    p["existing_bond_holdings"] = [{"asset_id": "SGOV", "amount": {"amount": "10", "currency": "USD"}, "broker_account_id": "US-001"}]
    p["sgov_bond_bucket_amount"] = unknown_money()
    s = build(p)
    assert not s.work3_complete
    assert s.evaluation_state.value == "INSUFFICIENT_DATA"
    assert "SGOV_BOND_ROLE_UNKNOWN_WITH_EXISTING_HOLDING" in s.reason_codes
    assert "sgov_bond_bucket_amount" in s.missing_required_fields
    assert s.per_asset_inputs == []


def test_zero_sgov_target_without_sgov_holding_does_not_need_known_bond_bucket():
    p = us_payload()
    p["target_bond_holdings"] = []
    p["existing_bond_holdings"] = []
    p["sgov_bond_bucket_amount"] = unknown_money()
    s = build(p)
    assert s.work3_complete
    assert all(x.asset_id != "SGOV" for x in s.gap_calculations)


def test_confirmed_sgov_bond_role_is_emitted_even_when_raw_existing_list_omits_sgov():
    p = us_payload()
    p["target_bond_holdings"] = []
    p["existing_bond_holdings"] = []
    p["authorized_universe"] = ["SGOV"]
    p["sgov_bond_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "250", "currency": "USD"}}
    p["sgov_dry_powder_bucket_amount"] = {"status": "KNOWN", "value": {"amount": "400", "currency": "USD"}}
    s = build(p)
    assert s.work3_complete
    g = gap(s, "SGOV")
    assert g.target_amount.amount == Decimal("0")
    assert g.eligible_existing_amount.value.amount == Decimal("250")
    assert pai(s, "SGOV").existing_position_amount.amount == Decimal("250")


def test_non_core_target_is_counted_separately_without_generic_weight_invention():
    p = us_payload()
    p["authorized_universe"].append("IEF")
    p["target_bond_holdings"].append({"asset_id": "IEF", "target_amount": {"amount": "100", "currency": "USD"}, "broker_account_id": "US-001"})
    s = build(p)
    assert s.work3_complete
    assert s.bucket_reconciliation.non_core_long_term_target.amount == Decimal("100")
    line = next(x for x in s.long_term_bucket_lines if x.asset_id == "IEF")
    assert line.template_weight_pct is None
    assert s.bond_long_term_target.amount == Decimal("1100")


def test_target_sum_reconciliation_invariant():
    s = build(us_payload())
    r = s.bucket_reconciliation
    assert r.us_generic_long_term_target.amount + r.tw_generic_long_term_target.amount + r.non_core_long_term_target.amount == r.bond_long_term_target.amount


def test_work3_rebuilds_per_asset_inputs_instead_of_trusting_work2_placeholder_values():
    p = us_payload()
    p["per_asset_inputs"][0]["remaining_target_gap_amount"]["amount"] = "999999"
    s = build(p)
    assert pai(s, "SPSB").remaining_target_gap_amount.amount == Decimal("200")


def test_per_asset_input_uses_canonical_remaining_target_gap_amount_field():
    s = build(us_payload())
    dumped = pai(s, "SPSB").model_dump(mode="json")
    assert "remaining_target_gap_amount" in dumped
    assert "remaining_target_gap" not in dumped
