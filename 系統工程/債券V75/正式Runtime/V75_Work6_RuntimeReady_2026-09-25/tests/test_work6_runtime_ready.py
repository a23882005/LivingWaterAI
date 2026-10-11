from copy import deepcopy
from decimal import Decimal

from v75_runtime import V75RunInput
from v75_runtime.enums import EvaluationState, ExistingPositionAction, GateState, NewMoneyAction
from v75_runtime.models import Money, PerAssetDecision, PercentValue
from v75_runtime.work3 import build_work3_state
from v75_runtime.work5 import assemble_final_snapshot
from v75_runtime.work6 import evaluate_runtime_ready
from v75_runtime.work6_models import Work6CutoverState
from helpers import cloned_payload


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
    p["authorized_universe"] = ["SGOV", "SPSB"]
    return V75RunInput.model_validate(p)


def _decision(asset_id, currency):
    from v75_runtime.enums import DeploymentState
    return PerAssetDecision(
        asset_id=asset_id, deployment_state=DeploymentState.SMALL_BUY,
        deployment_pct=PercentValue(value=Decimal("25")),
        deploy_amount=Money(amount=Decimal("0"), currency=currency),
        new_money_action=NewMoneyAction.SMALL_BUY,
        existing_position_action=ExistingPositionAction.HOLD,
        existing_reduction_pct=None, classification=[], gate_state=GateState.PASS,
        evaluation_state=EvaluationState.COMPLETE, reason_codes=["WORK4_TEST"], source_lineage=["WORK4"],
    )


def _work5_snapshot():
    run = _run(); w3 = build_work3_state(run)
    decisions = [_decision(x.asset_id, run.currency) for x in w3.per_asset_inputs]
    undeployed = Money(amount=run.bond_executable_budget.amount, currency=run.currency)
    return assemble_final_snapshot(run=run, work3_state=w3, decisions=decisions, v75_undeployed_to_sgov=undeployed)


def test_work6_ready_for_valid_formal_work5_snapshot():
    w6 = evaluate_runtime_ready(_work5_snapshot())
    assert w6.runtime_ready is True
    assert w6.cutover_state == Work6CutoverState.READY
    assert w6.gate_state == GateState.PASS
    assert w6.blocking_reason_codes == []


def test_work6_preserves_work5_output_exactly():
    snap = _work5_snapshot()
    before = snap.output.model_dump(mode="json")
    w6 = evaluate_runtime_ready(snap)
    assert w6.output.model_dump(mode="json") == before


def test_work6_fail_closed_if_formal_output_not_eligible():
    snap = _work5_snapshot()
    data = snap.model_dump()
    data["output"]["formal_output_eligible"] = False
    from v75_runtime.work5_models import Work5FinalSnapshot
    bad = Work5FinalSnapshot.model_validate(data)
    w6 = evaluate_runtime_ready(bad)
    assert not w6.runtime_ready
    assert "WORK6_FORMAL_OUTPUT_NOT_ELIGIBLE" in w6.blocking_reason_codes


def test_work6_fail_closed_on_serialized_account_scope_tamper():
    snap = _work5_snapshot()
    data = snap.model_dump()
    data["output"]["bond_allocation_final"] = deepcopy(data["output"]["bond_allocation_final"])
    data["output"]["bond_allocation_final"]["account_scope"]["broker_account_id"] = "OTHER"
    from v75_runtime.work5_models import Work5FinalSnapshot
    bad = Work5FinalSnapshot.model_validate(data)
    w6 = evaluate_runtime_ready(bad)
    assert not w6.runtime_ready
    assert "WORK6_ACCOUNT_SCOPE_ID_MISMATCH" in w6.blocking_reason_codes


def test_work6_is_deterministic_and_idempotent_as_readiness_evaluation():
    snap = _work5_snapshot()
    a = evaluate_runtime_ready(snap).model_dump(mode="json")
    b = evaluate_runtime_ready(snap).model_dump(mode="json")
    assert a == b
