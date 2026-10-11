from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .constants import PREDICATE_VERSION, RULE_SOT_VERSION
from .enums import (
    DeploymentState,
    EvaluationState,
    ExistingPositionAction,
    GateState,
    NewMoneyAction,
)
from .models import Money, PerAssetDecision, V75RunInput, V75RunOutput
from .work3_models import Work3State
from .work5_models import Work5FinalClassification, Work5FinalSnapshot

WORK5_ENGINE_VERSION = "V75_WORK5_FINAL_CLASSIFICATION_SNAPSHOT_v1.0.0"
WORK5_CONTRACT_ID = "V75_WORK5_LIVINGWATERAI_INTEGRATION_OUTPUT_v1.0.0"


def _money_json(value: Money | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": str(value.amount), "currency": value.currency}


def _decision_classification(decision: PerAssetDecision) -> list[str]:
    """Derive labels only from frozen Work4 output; never change the decision."""
    labels = [
        f"DEPLOYMENT:{decision.deployment_state.value}" if decision.deployment_state else "DEPLOYMENT:UNRESOLVED",
        f"NEW_MONEY:{decision.new_money_action.value}" if decision.new_money_action else "NEW_MONEY:UNRESOLVED",
        f"EXISTING:{decision.existing_position_action.value}" if decision.existing_position_action else "EXISTING:UNRESOLVED",
        f"GATE:{decision.gate_state.value}",
        f"EVALUATION:{decision.evaluation_state.value}",
    ]
    return labels


def classify_final(decisions: Iterable[PerAssetDecision], evaluation_state: EvaluationState) -> Work5FinalClassification:
    decisions = list(decisions)
    if evaluation_state == EvaluationState.INVALID_INPUT:
        return Work5FinalClassification.INVALID_INPUT
    if evaluation_state == EvaluationState.INSUFFICIENT_DATA:
        return Work5FinalClassification.INSUFFICIENT_DATA
    if evaluation_state == EvaluationState.REVIEW_REQUIRED:
        return Work5FinalClassification.REVIEW_REQUIRED
    if any(d.gate_state == GateState.HARD_WAIT or d.deployment_state == DeploymentState.HARD_WAIT for d in decisions):
        return Work5FinalClassification.HARD_WAIT
    if any(d.existing_position_action in {
        ExistingPositionAction.REBOUND_SMALL_SELL,
        ExistingPositionAction.TECHNICAL_TRIM,
        ExistingPositionAction.TRUE_RISK_REDUCTION,
    } for d in decisions):
        return Work5FinalClassification.EXISTING_POSITION_REVIEW
    if any(d.new_money_action in {
        NewMoneyAction.SMALL_BUY,
        NewMoneyAction.LEFT_BUY,
        NewMoneyAction.DEEP_LEFT_BUY,
        NewMoneyAction.RIGHT_COMPLETE,
    } and d.deploy_amount is not None and d.deploy_amount.amount > 0 for d in decisions):
        return Work5FinalClassification.ACTIONABLE
    return Work5FinalClassification.NO_NEW_MONEY_ACTION


def _normalize_decisions(decisions: list[PerAssetDecision], currency: str) -> list[PerAssetDecision]:
    seen: set[str] = set()
    out: list[PerAssetDecision] = []
    for d in decisions:
        aid = d.asset_id.strip().upper()
        if aid in seen:
            raise ValueError("Work5 cannot assemble duplicate per-asset decisions")
        seen.add(aid)
        if d.deploy_amount is not None and d.deploy_amount.currency != currency:
            raise ValueError("Work5 decision currency must match account currency")
        data = d.model_dump()
        data["asset_id"] = aid
        data["classification"] = _decision_classification(d)
        data["source_lineage"] = list(dict.fromkeys([*d.source_lineage, WORK5_ENGINE_VERSION]))
        out.append(PerAssetDecision.model_validate(data))
    return out


def assemble_final_snapshot(
    *,
    run: V75RunInput,
    work3_state: Work3State,
    decisions: list[PerAssetDecision],
    v75_undeployed_to_sgov: Money | None,
) -> Work5FinalSnapshot:
    """Assemble Work5 final classification + final integration snapshot.

    Work5 is intentionally non-authoritative for Work1-4 calculations. It validates
    identity/budget boundaries and serializes their canonical results.
    """
    if work3_state.run_id != run.run_id or work3_state.broker_account_id != run.broker_account_id:
        raise ValueError("Work5 requires same-run, same-account Work3 state")
    if work3_state.currency != run.currency:
        raise ValueError("Work5 Work3/run currency mismatch")
    if work3_state.rule_version != RULE_SOT_VERSION or work3_state.predicate_version != PREDICATE_VERSION:
        raise ValueError("Work5 upstream Work3 version mismatch")

    if not work3_state.work3_complete or work3_state.evaluation_state != EvaluationState.COMPLETE:
        eval_state = work3_state.evaluation_state
        formal = False
        normalized: list[PerAssetDecision] = []
        missing = list(work3_state.missing_required_fields)
        reasons = list(dict.fromkeys([*work3_state.reason_codes, "WORK3_NOT_COMPLETE_FAIL_CLOSED", WORK5_ENGINE_VERSION]))
    else:
        eval_state = EvaluationState.COMPLETE
        normalized = _normalize_decisions(decisions, run.currency)
        expected_assets = {x.asset_id.strip().upper() for x in work3_state.per_asset_inputs}
        actual_assets = {x.asset_id for x in normalized}
        if expected_assets != actual_assets:
            raise ValueError("Work5 decisions must exactly cover Work3 per_asset_inputs")
        if any(d.evaluation_state != EvaluationState.COMPLETE for d in normalized):
            raise ValueError("Work5 formal assembly requires COMPLETE Work4 decisions")
        deployed = sum((d.deploy_amount.amount for d in normalized if d.deploy_amount), Decimal("0"))
        if deployed > run.bond_executable_budget.amount:
            raise ValueError("Work5 deployed total exceeds same-account bond_executable_budget")
        if v75_undeployed_to_sgov is not None:
            if v75_undeployed_to_sgov.currency != run.currency:
                raise ValueError("Work5 undeployed-to-SGOV currency mismatch")
            if deployed + v75_undeployed_to_sgov.amount != run.bond_executable_budget.amount:
                raise ValueError("Work5 deployed + undeployed-to-SGOV must reconcile to executable budget")
        formal = True
        missing = []
        reasons = [WORK5_CONTRACT_ID, WORK5_ENGINE_VERSION, "WORK1_TO_WORK4_RESULTS_PRESERVED_NO_RECOMPUTE"]

    allocation = {
        "contract_id": WORK5_CONTRACT_ID,
        "account_scope": {
            "broker_account_id": run.broker_account_id,
            "broker_domain_type": run.broker_domain_type.value,
            "currency": run.currency,
        },
        "bond_long_term_target": _money_json(work3_state.bond_long_term_target),
        "per_asset": [
            {
                "asset_id": d.asset_id,
                "deployment_state": d.deployment_state.value if d.deployment_state else None,
                "deployment_pct": str(d.deployment_pct.value) if d.deployment_pct else None,
                "deploy_amount": _money_json(d.deploy_amount),
                "new_money_action": d.new_money_action.value if d.new_money_action else None,
                "existing_position_action": d.existing_position_action.value if d.existing_position_action else None,
                "classification": d.classification,
                "gate_state": d.gate_state.value,
                "evaluation_state": d.evaluation_state.value,
                "reason_codes": d.reason_codes,
            }
            for d in normalized
        ],
        "v75_undeployed_to_sgov": _money_json(v75_undeployed_to_sgov),
        "semantic_guards": [
            "SGOV_BOND_BUCKET_PRESERVED",
            "SGOV_DRY_POWDER_INPUT_NOT_AGGREGATED_IN_OUTPUT",
            "SAME_ACCOUNT_NO_CROSS_FUNDING",
            "NO_WORK5_RECOMPUTE_OF_TARGET_GAP_PREDICATE_OR_DEPLOYMENT",
        ],
    }

    output = V75RunOutput(
        run_id=run.run_id,
        rule_version=RULE_SOT_VERSION,
        predicate_version=PREDICATE_VERSION,
        deployment_parameter_version=run.deployment_parameter_version,
        broker_account_id=run.broker_account_id,
        broker_domain_type=run.broker_domain_type,
        currency=run.currency,
        bond_long_term_target=work3_state.bond_long_term_target,
        bond_allocation_final=allocation,
        per_asset_decisions=normalized,
        sgov_bond_bucket_amount=run.sgov_bond_bucket_amount,
        v75_undeployed_to_sgov=v75_undeployed_to_sgov,
        formal_output_eligible=formal,
        evaluation_state=eval_state,
        missing_required_fields=missing,
        reason_codes=reasons,
        source_lineage=list(dict.fromkeys([*run.source_lineage, *work3_state.source_lineage, WORK5_ENGINE_VERSION])),
    )
    final_class = classify_final(normalized, eval_state)
    gate = GateState.HARD_WAIT if final_class == Work5FinalClassification.HARD_WAIT else (
        GateState.PASS if eval_state == EvaluationState.COMPLETE else GateState.INSUFFICIENT_DATA
    )
    return Work5FinalSnapshot(
        run_id=run.run_id,
        broker_account_id=run.broker_account_id,
        currency=run.currency,
        final_classification=final_class,
        gate_state=gate,
        evaluation_state=eval_state,
        bond_long_term_target=work3_state.bond_long_term_target,
        output=output,
        source_lineage=list(dict.fromkeys([*output.source_lineage, WORK5_CONTRACT_ID])),
    )
