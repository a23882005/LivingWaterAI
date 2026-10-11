from copy import deepcopy
from decimal import Decimal
import pytest

from v75_runtime.enums import BrokerDomainType, EvaluationState, ExistingPositionAction, GateState, NewMoneyAction, ValueStatus
from v75_runtime.models import Money, MoneyValue, PerAssetDecision, PercentValue
from v75_runtime.work3 import build_work3_state
from v75_runtime.work5 import assemble_final_snapshot, classify_final
from v75_runtime.work5_models import Work5FinalClassification
from helpers import cloned_payload
from v75_runtime import V75RunInput


def _run():
    p = cloned_payload()
    p["existing_bond_holdings"] = [
        {"asset_id":"SGOV","amount":{"amount":"300","currency":"USD"},"broker_account_id":"US-001"},
        {"asset_id":"SPSB","amount":{"amount":"0","currency":"USD"},"broker_account_id":"US-001"},
    ]
    p["target_bond_holdings"] = [
        {"asset_id":"SGOV","target_amount":{"amount":"700","currency":"USD"},"broker_account_id":"US-001"},
        {"asset_id":"SPSB","target_amount":{"amount":"300","currency":"USD"},"broker_account_id":"US-001"},
    ]
    p["authorized_universe"]=["SGOV","SPSB"]
    return V75RunInput.model_validate(p)


def _decision(asset_id, currency, amount, state="SMALL_BUY", pct="25", existing="HOLD"):
    from v75_runtime.enums import DeploymentState
    return PerAssetDecision(
        asset_id=asset_id,
        deployment_state=DeploymentState(state),
        deployment_pct=PercentValue(value=Decimal(pct)),
        deploy_amount=Money(amount=Decimal(amount), currency=currency),
        new_money_action=NewMoneyAction(state),
        existing_position_action=ExistingPositionAction(existing),
        existing_reduction_pct=None,
        classification=[], gate_state=GateState.PASS,
        evaluation_state=EvaluationState.COMPLETE,
        reason_codes=["WORK4_TEST"], source_lineage=["WORK4"],
    )


def test_work5_formal_snapshot_reconciles_and_does_not_emit_dry_powder():
    run = _run()
    w3 = build_work3_state(run)
    assert w3.work3_complete
    decisions=[]
    for item in w3.per_asset_inputs:
        decisions.append(_decision(item.asset_id, run.currency, "0"))
    undeployed = Money(amount=run.bond_executable_budget.amount, currency=run.currency) if run.broker_domain_type == BrokerDomainType.US_BROKER else None
    snap = assemble_final_snapshot(run=run, work3_state=w3, decisions=decisions, v75_undeployed_to_sgov=undeployed)
    assert snap.output.formal_output_eligible is True
    assert snap.output.evaluation_state == EvaluationState.COMPLETE
    assert "sgov_dry_powder_bucket_amount" not in str(snap.output.bond_allocation_final).lower()
    assert all(d.classification for d in snap.output.per_asset_decisions)


def test_work5_requires_exact_work3_asset_coverage():
    run=_run(); w3=build_work3_state(run)
    with pytest.raises(ValueError, match="exactly cover"):
        assemble_final_snapshot(run=run, work3_state=w3, decisions=[], v75_undeployed_to_sgov=None)


def test_work5_rejects_cross_currency_decision():
    run=_run(); w3=build_work3_state(run)
    decisions=[_decision(x.asset_id, "EUR", "0") for x in w3.per_asset_inputs]
    with pytest.raises(ValueError, match="currency"):
        assemble_final_snapshot(run=run, work3_state=w3, decisions=decisions, v75_undeployed_to_sgov=None)


def test_work5_rejects_budget_overrun():
    run=_run(); w3=build_work3_state(run)
    decisions=[]
    for i,x in enumerate(w3.per_asset_inputs):
        decisions.append(_decision(x.asset_id, run.currency, str(run.bond_executable_budget.amount + (1 if i == 0 else 0))))
    with pytest.raises(ValueError, match="exceeds"):
        assemble_final_snapshot(run=run, work3_state=w3, decisions=decisions, v75_undeployed_to_sgov=None)


def test_work5_rejects_bad_sgov_reconciliation():
    run=_run(); w3=build_work3_state(run)
    if run.broker_domain_type != BrokerDomainType.US_BROKER:
        pytest.skip("fixture not US broker")
    decisions=[_decision(x.asset_id, run.currency, "0") for x in w3.per_asset_inputs]
    bad=Money(amount=max(Decimal("0"), run.bond_executable_budget.amount-Decimal("1")), currency="USD")
    with pytest.raises(ValueError, match="reconcile"):
        assemble_final_snapshot(run=run, work3_state=w3, decisions=decisions, v75_undeployed_to_sgov=bad)


def test_classification_precedence_is_deterministic():
    assert classify_final([], EvaluationState.INVALID_INPUT) == Work5FinalClassification.INVALID_INPUT
    assert classify_final([], EvaluationState.INSUFFICIENT_DATA) == Work5FinalClassification.INSUFFICIENT_DATA
    assert classify_final([], EvaluationState.REVIEW_REQUIRED) == Work5FinalClassification.REVIEW_REQUIRED


def test_hard_wait_classification():
    from v75_runtime.enums import DeploymentState
    d=PerAssetDecision(asset_id="SGOV", deployment_state=DeploymentState.HARD_WAIT,
        deployment_pct=PercentValue(value=Decimal("0")), deploy_amount=Money(amount=0,currency="USD"),
        new_money_action=NewMoneyAction.WAIT, existing_position_action=ExistingPositionAction.HOLD,
        existing_reduction_pct=None, classification=[], gate_state=GateState.HARD_WAIT,
        evaluation_state=EvaluationState.COMPLETE, reason_codes=[], source_lineage=["W4"])
    assert classify_final([d], EvaluationState.COMPLETE)==Work5FinalClassification.HARD_WAIT
