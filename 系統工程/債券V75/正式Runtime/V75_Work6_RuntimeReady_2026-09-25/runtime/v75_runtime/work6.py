from __future__ import annotations

from .constants import PREDICATE_VERSION, RULE_SOT_VERSION
from .enums import EvaluationState, GateState
from .work5 import WORK5_CONTRACT_ID, WORK5_ENGINE_VERSION
from .work5_models import Work5FinalClassification, Work5FinalSnapshot
from .work6_models import Work6CutoverState, Work6RuntimeReadySnapshot

WORK6_ENGINE_VERSION = "V75_WORK6_CUTOVER_RUNTIME_READY_v1.0.0"
WORK6_CONTRACT_ID = "V75_WORK6_RUNTIME_READY_CONTRACT_v1.0.0"

_BLOCKING_FINAL_CLASSES = {
    Work5FinalClassification.HARD_WAIT,
    Work5FinalClassification.INSUFFICIENT_DATA,
    Work5FinalClassification.INVALID_INPUT,
    Work5FinalClassification.REVIEW_REQUIRED,
}


def evaluate_runtime_ready(snapshot: Work5FinalSnapshot) -> Work6RuntimeReadySnapshot:
    """Validate Work5 integration output for runtime cutover without recomputation.

    Work6 is a fail-closed readiness gate. It consumes the frozen Work5 snapshot,
    verifies version/identity/formal-output invariants, and emits a deterministic
    READY/BLOCKED envelope. It does not alter allocations, deployment, funding,
    settlement, account isolation, SGOV semantics, or any Work1-Work5 decision.
    """
    reasons: list[str] = []
    out = snapshot.output

    if out.rule_version != RULE_SOT_VERSION:
        reasons.append("WORK6_RULE_VERSION_MISMATCH")
    if out.predicate_version != PREDICATE_VERSION:
        reasons.append("WORK6_PREDICATE_VERSION_MISMATCH")
    if WORK5_CONTRACT_ID not in out.reason_codes:
        reasons.append("WORK6_WORK5_CONTRACT_MISSING")
    if WORK5_ENGINE_VERSION not in out.reason_codes:
        reasons.append("WORK6_WORK5_ENGINE_MISSING")
    if not out.formal_output_eligible:
        reasons.append("WORK6_FORMAL_OUTPUT_NOT_ELIGIBLE")
    if snapshot.evaluation_state != EvaluationState.COMPLETE:
        reasons.append("WORK6_EVALUATION_NOT_COMPLETE")
    if snapshot.gate_state != GateState.PASS:
        reasons.append("WORK6_UPSTREAM_GATE_NOT_PASS")
    if snapshot.final_classification in _BLOCKING_FINAL_CLASSES:
        reasons.append(f"WORK6_BLOCKING_CLASSIFICATION:{snapshot.final_classification.value}")

    # Work5 already enforces account/currency identity in its model. Re-check the
    # integration allocation scope at the cutover boundary so serialized/tampered
    # payloads fail closed before production integration.
    allocation = out.bond_allocation_final
    if not isinstance(allocation, dict):
        reasons.append("WORK6_ALLOCATION_NOT_OBJECT")
    else:
        if allocation.get("contract_id") != WORK5_CONTRACT_ID:
            reasons.append("WORK6_ALLOCATION_CONTRACT_MISMATCH")
        scope = allocation.get("account_scope")
        if not isinstance(scope, dict):
            reasons.append("WORK6_ACCOUNT_SCOPE_MISSING")
        else:
            if scope.get("broker_account_id") != snapshot.broker_account_id:
                reasons.append("WORK6_ACCOUNT_SCOPE_ID_MISMATCH")
            if scope.get("currency") != snapshot.currency:
                reasons.append("WORK6_ACCOUNT_SCOPE_CURRENCY_MISMATCH")

    reasons = list(dict.fromkeys(reasons))
    ready = not reasons
    return Work6RuntimeReadySnapshot(
        run_id=snapshot.run_id,
        broker_account_id=snapshot.broker_account_id,
        currency=snapshot.currency,
        cutover_state=Work6CutoverState.READY if ready else Work6CutoverState.BLOCKED,
        runtime_ready=ready,
        gate_state=GateState.PASS if ready else GateState.HARD_WAIT,
        evaluation_state=snapshot.evaluation_state,
        final_classification=snapshot.final_classification,
        output=out,
        blocking_reason_codes=reasons,
        source_lineage=list(dict.fromkeys([*snapshot.source_lineage, WORK6_CONTRACT_ID, WORK6_ENGINE_VERSION])),
    )
