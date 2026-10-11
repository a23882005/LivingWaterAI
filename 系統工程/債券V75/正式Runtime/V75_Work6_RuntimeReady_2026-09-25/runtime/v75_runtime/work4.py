from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum
import json
from pathlib import Path
from typing import Iterable, Mapping

from .constants import DEPLOYMENT_PCT_CONTRACT, PREDICATE_VERSION
from .enums import DeploymentState, ExistingPositionAction, PredicateAssessmentStatus
from .models import Money, PerAssetDecision, PerAssetDeploymentInput, PercentValue, PredicateResult

CONTRACT_ID = "V75_DEPLOYMENT_STATE_SELECTION_v1.0.0_RECHECK2_FINAL"

class AssetCreditClass(StrEnum):
    TREASURY = "TREASURY"
    CORPORATE = "CORPORATE"
    MIXED = "MIXED"

class DurationBucket(StrEnum):
    LE_1Y = "LE_1Y"
    GT_1Y_LE_3Y = "GT_1Y_LE_3Y"
    GT_3Y_LE_7Y = "GT_3Y_LE_7Y"
    GT_7Y_LE_12Y = "GT_7Y_LE_12Y"
    GT_12Y_LE_18Y = "GT_12Y_LE_18Y"
    GT_18Y = "GT_18Y"

@dataclass(frozen=True)
class ExistingPositionPolicy:
    current_position_quantity: Decimal
    capital_gain_harvest_eligible: bool | None = None
    rebound_reduction_eligible: bool | None = None
    investment_logic_invalidated: bool | None = None

@dataclass(frozen=True)
class Step10Trace:
    deployment_state: DeploymentState
    deployment_pct: Decimal
    existing_position_action: ExistingPositionAction
    step10_rule_ids: tuple[str, ...]
    step10_direct_veto_rule_ids: tuple[str, ...]
    step10_cap_rule_ids: tuple[str, ...]
    step10_base_rule: str


def _contract() -> dict:
    p = Path(__file__).resolve().parents[2] / "contracts" / "V75_Work4_Deployment_State_Selection_Contract_RECHECK2_FINAL.json"
    if not p.exists():
        # packaged runtime may place contracts one level above runtime/
        p = Path(__file__).resolve().parents[3] / "contracts" / p.name
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("contract_id") != CONTRACT_ID:
        raise RuntimeError("Work4 contract identity mismatch")
    if data.get("upstream_predicate_version") != PREDICATE_VERSION:
        raise RuntimeError("Work4 upstream predicate version mismatch")
    if data.get("duration_matrix_row_count") != 864 or len(data.get("duration_matrix", [])) != 864:
        raise RuntimeError("Work4 duration matrix must contain exactly 864 rows")
    return data

CONTRACT = _contract()
_DURATION_INDEX = {(r["duration_bucket"], r["PRED-001"], r["PRED-002"], r["PRED-003"], r["PRED-006"]): r["action"] for r in CONTRACT["duration_matrix"]}
if len(_DURATION_INDEX) != 864: raise RuntimeError("duration matrix keys must be unique")


def duration_bucket(d: Decimal) -> DurationBucket:
    d = Decimal(d)
    if d < 0:
        raise ValueError("effective_duration_years must be >= 0")
    if d <= 1: return DurationBucket.LE_1Y
    if d <= 3: return DurationBucket.GT_1Y_LE_3Y
    if d <= 7: return DurationBucket.GT_3Y_LE_7Y
    if d <= 12: return DurationBucket.GT_7Y_LE_12Y
    if d <= 18: return DurationBucket.GT_12Y_LE_18Y
    return DurationBucket.GT_18Y


def _predicate_map(results: Iterable[PredicateResult]) -> dict[str, PredicateResult]:
    out = {r.predicate_id: r for r in results}
    required = {f"PRED-{i:03d}" for i in range(1, 11)}
    if set(out) != required:
        raise ValueError("Step10 requires exactly PRED-001..010")
    for pid, r in out.items():
        if r.assessment_status != PredicateAssessmentStatus.VALID:
            raise ValueError(f"{pid} is not VALID; Step10 must fail-closed before invocation")
        if not r.aggregate_state:
            raise ValueError(f"{pid} VALID result lacks aggregate_state")
    return out


def _duration_action(bucket: DurationBucket, p: Mapping[str, PredicateResult]) -> dict:
    key = (bucket.value, p["PRED-001"].aggregate_state, p["PRED-002"].aggregate_state,
           p["PRED-003"].aggregate_state, p["PRED-006"].aggregate_state)
    try:
        return _DURATION_INDEX[key]
    except KeyError as exc:
        raise RuntimeError(f"duration matrix missing legal key {key}") from exc


def _existing_action(asset_credit_class: AssetCreditClass, p: Mapping[str, PredicateResult], policy: ExistingPositionPolicy) -> ExistingPositionAction:
    q = Decimal(policy.current_position_quantity)
    if q < 0:
        raise ValueError("current_position_quantity must be >=0")
    if q <= 0:
        return ExistingPositionAction.NOT_APPLICABLE
    if policy.investment_logic_invalidated is True:
        return ExistingPositionAction.TRUE_RISK_REDUCTION
    if asset_credit_class in {AssetCreditClass.CORPORATE, AssetCreditClass.MIXED} and p["PRED-004"].aggregate_state == "CREDIT_CRISIS":
        return ExistingPositionAction.TRUE_RISK_REDUCTION
    if policy.capital_gain_harvest_eligible is True and p["PRED-009"].aggregate_state == "TRIM_WATCH" and p["PRED-008"].aggregate_state == "LOW_ATTRACTIVENESS":
        return ExistingPositionAction.TECHNICAL_TRIM
    if policy.rebound_reduction_eligible is True and p["PRED-009"].aggregate_state == "RIGHT_CONFIRM":
        return ExistingPositionAction.REBOUND_SMALL_SELL
    return ExistingPositionAction.HOLD


def evaluate_step10(*, predicate_results: Iterable[PredicateResult], asset_credit_class: AssetCreditClass | str,
                    effective_duration_years: Decimal, existing_policy: ExistingPositionPolicy) -> Step10Trace:
    p = _predicate_map(predicate_results)
    try:
        credit = AssetCreditClass(asset_credit_class)
    except Exception as exc:
        raise ValueError("asset_credit_class must be authoritative TREASURY/CORPORATE/MIXED") from exc
    bucket = duration_bucket(Decimal(effective_duration_years))
    directs: list[tuple[str, str]] = []
    caps: list[tuple[int, str]] = []
    all_rule_ids: list[str] = []

    safety = CONTRACT["safety_action_tables"][credit.value]
    for pid in ("PRED-010", "PRED-007", "PRED-006", "PRED-005", "PRED-004"):
        action = safety[pid][p[pid].aggregate_state]
        all_rule_ids.append(action["rule_id"])
        if action["kind"] == "DIRECT": directs.append((action["state"], action["rule_id"]))
        elif action["kind"] == "CAP": caps.append((int(action["ceiling_pct"]), action["rule_id"]))

    da = _duration_action(bucket, p)
    all_rule_ids.append(da["rule_id"])
    if da["kind"] == "DIRECT": directs.append((da["state"], da["rule_id"]))
    elif da["kind"] == "CAP": caps.append((int(da["ceiling_pct"]), da["rule_id"]))

    tech = p["PRED-009"].aggregate_state
    yld = p["PRED-008"].aggregate_state
    base_name = CONTRACT["yield_technical_base_matrix"][tech][yld]
    base = DeploymentState(base_name)
    base_rule = f"C_{tech}_{yld}"
    all_rule_ids.append(base_rule)

    if any(s == "HARD_WAIT" for s, _ in directs): state = DeploymentState.HARD_WAIT
    elif any(s == "PAUSE" for s, _ in directs) or base == DeploymentState.PAUSE: state = DeploymentState.PAUSE
    else:
        base_pct = int(DEPLOYMENT_PCT_CONTRACT[base])
        cap_pct = min((c for c, _ in caps), default=100)
        final_pct = min(base_pct, cap_pct)
        state = {25: DeploymentState.SMALL_BUY, 50: DeploymentState.LEFT_BUY,
                 75: DeploymentState.DEEP_LEFT_BUY, 100: DeploymentState.RIGHT_COMPLETE}[final_pct]

    existing = _existing_action(credit, p, existing_policy)
    if existing == ExistingPositionAction.TRUE_RISK_REDUCTION:
        state = DeploymentState.HARD_WAIT
        all_rule_ids.append("NO_CHURN_TRUE_RISK_REDUCTION")
    elif existing in {ExistingPositionAction.TECHNICAL_TRIM, ExistingPositionAction.REBOUND_SMALL_SELL}:
        state = DeploymentState.PAUSE
        all_rule_ids.append("NO_CHURN_EXISTING_SELL")

    return Step10Trace(
        deployment_state=state,
        deployment_pct=DEPLOYMENT_PCT_CONTRACT[state],
        existing_position_action=existing,
        step10_rule_ids=tuple(all_rule_ids),
        step10_direct_veto_rule_ids=tuple(r for _, r in directs),
        step10_cap_rule_ids=tuple(r for _, r in caps),
        step10_base_rule=base_rule,
    )


def build_decision(asset_input: PerAssetDeploymentInput, trace: Step10Trace, source_lineage: list[str]) -> PerAssetDecision:
    amount = (asset_input.remaining_target_gap_amount.amount * trace.deployment_pct / Decimal("100"))
    state = trace.deployment_state
    new_action = {
        DeploymentState.HARD_WAIT: "WAIT", DeploymentState.PAUSE: "PAUSE",
        DeploymentState.SMALL_BUY: "SMALL_BUY", DeploymentState.LEFT_BUY: "LEFT_BUY",
        DeploymentState.DEEP_LEFT_BUY: "DEEP_LEFT_BUY", DeploymentState.RIGHT_COMPLETE: "RIGHT_COMPLETE",
    }[state]
    from .enums import EvaluationState, GateState, NewMoneyAction
    return PerAssetDecision(
        asset_id=asset_input.asset_id,
        deployment_state=state,
        deployment_pct=PercentValue(value=trace.deployment_pct),
        deploy_amount=Money(amount=amount, currency=asset_input.currency),
        new_money_action=NewMoneyAction(new_action),
        existing_position_action=trace.existing_position_action,
        existing_reduction_pct=None,
        classification=[], gate_state=GateState.HARD_WAIT if state == DeploymentState.HARD_WAIT else GateState.PASS,
        evaluation_state=EvaluationState.COMPLETE,
        reason_codes=list(trace.step10_rule_ids), source_lineage=source_lineage,
    )


def proportional_scale_decisions(decisions: list[PerAssetDecision], budget: Money) -> list[PerAssetDecision]:
    """Scale positive legal demand proportionally when it exceeds same-account executable budget."""
    if any(d.deploy_amount and d.deploy_amount.currency != budget.currency for d in decisions):
        raise ValueError("decision currency must match executable budget")
    total = sum((d.deploy_amount.amount for d in decisions if d.deploy_amount), Decimal("0"))
    if total <= budget.amount or total == 0:
        return decisions
    factor = budget.amount / total
    out=[]
    for d in decisions:
        data=d.model_dump()
        if d.deploy_amount:
            data["deploy_amount"]={"amount": d.deploy_amount.amount * factor, "currency": budget.currency}
            data["reason_codes"]=[*d.reason_codes, "MULTI_ASSET_PROPORTIONAL_BUDGET_SCALE"]
        out.append(PerAssetDecision.model_validate(data))
    return out


def calculate_v75_undeployed_to_sgov(*, broker_domain: str, currency: str, bond_executable_budget: Money,
                                      decisions: list[PerAssetDecision]) -> Money | None:
    """Only US_BROKER/USD gets the V75 undeployed-to-SGOV semantic. Never touches dry-powder input."""
    if broker_domain != "US_BROKER": return None
    if currency != "USD" or bond_executable_budget.currency != "USD":
        raise ValueError("US_BROKER undeployed-to-SGOV must remain USD")
    deployed=sum((d.deploy_amount.amount for d in decisions if d.deploy_amount), Decimal("0"))
    if deployed > bond_executable_budget.amount:
        raise ValueError("deployed amount cannot exceed same-account executable budget")
    return Money(amount=bond_executable_budget.amount-deployed, currency="USD")
