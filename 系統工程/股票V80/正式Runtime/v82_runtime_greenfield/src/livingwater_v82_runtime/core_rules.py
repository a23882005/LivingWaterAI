"""W7 deterministic V82 core-rule engine.

Scope: data sufficiency/PIT/freshness, valuation, fundamentals, price/technical
predicates, hard-gate permission, and structural-risk state.  It deliberately
stops before W8 deployment/order sizing and W9 persistence/ports.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence
from .enums import (CompanyRiskGrade, CompletionState, ContextStatus, DataQuality,
    ExtremeValuationFlag, Freshness, HardGateState, PitStatus, PredicateTruth,
    RequirementLevel, StructuralBreakState, ThesisState, ValuationLevel)

UNKNOWN="UNKNOWN"

def _d(v: Any) -> Decimal | None:
    try:
        d=Decimal(str(v)); return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError): return None

def tri_and(*xs: PredicateTruth) -> PredicateTruth:
    if PredicateTruth.FALSE in xs: return PredicateTruth.FALSE
    if PredicateTruth.UNKNOWN in xs: return PredicateTruth.UNKNOWN
    return PredicateTruth.TRUE

def threshold_truth(signals: Sequence[PredicateTruth], minimum: int) -> PredicateTruth:
    t=sum(x is PredicateTruth.TRUE for x in signals); u=sum(x is PredicateTruth.UNKNOWN for x in signals)
    if t>=minimum: return PredicateTruth.TRUE
    if t+u<minimum: return PredicateTruth.FALSE
    return PredicateTruth.UNKNOWN

@dataclass(frozen=True, slots=True)
class EvidenceFact:
    name: str; value: Any; requirement: RequirementLevel
    data_quality: DataQuality; freshness: Freshness=Freshness.NOT_APPLICABLE
    pit_status: PitStatus=PitStatus.NOT_APPLICABLE; source_reference: str=""
    issue_codes: tuple[str,...]=()

@dataclass(frozen=True, slots=True)
class SufficiencyResult:
    formal_output_eligible: bool; quality: DataQuality; missing_required: tuple[str,...]
    issue_codes: tuple[str,...]

def evaluate_sufficiency(facts: Iterable[EvidenceFact]) -> SufficiencyResult:
    missing=[]; issues=[]; fallback=False; unknown=False
    for f in facts:
        issues.extend(f.issue_codes)
        if f.requirement is RequirementLevel.INAPPLICABLE: continue
        # Required evidence must satisfy quality, freshness, *and* PIT verifiability.
        # W7 previously carried pit_status but failed to consume UNVERIFIABLE here,
        # which could incorrectly allow a formal output from non-PIT-verifiable data.
        bad_quality=f.data_quality in (DataQuality.INSUFFICIENT,DataQuality.UNKNOWN)
        bad_freshness=f.freshness in (Freshness.STALE,Freshness.UNKNOWN)
        bad_pit=f.pit_status is PitStatus.UNVERIFIABLE
        bad=bad_quality or bad_freshness or bad_pit
        if f.requirement in (RequirementLevel.SAFETY_REQUIRED,RequirementLevel.MODULE_REQUIRED) and bad: missing.append(f.name)
        fallback |= f.data_quality is DataQuality.FALLBACK_USED
        unknown |= f.data_quality is DataQuality.UNKNOWN or f.freshness is Freshness.UNKNOWN or bad_pit
    if missing: q=DataQuality.UNKNOWN if unknown else DataQuality.INSUFFICIENT
    else: q=DataQuality.FALLBACK_USED if fallback else DataQuality.OK
    return SufficiencyResult(not missing,q,tuple(missing),tuple(dict.fromkeys(issues)))

@dataclass(frozen=True, slots=True)
class ValuationResult:
    level: ValuationLevel; completion: CompletionState; extreme_flag: ExtremeValuationFlag
    formal_output_eligible: bool; primary_metric: str|None; fallback_used: bool; reason_codes: tuple[str,...]

def relative_multiple_level(current: Any, historical_median: Any) -> ValuationLevel:
    c,m=_d(current),_d(historical_median)
    if c is None or m is None or m<=0: return ValuationLevel.UNKNOWN
    r=c/m
    if r<Decimal('.80'): return ValuationLevel.CHEAP
    if r<Decimal('1.10'): return ValuationLevel.NORMAL
    if r<Decimal('1.25'): return ValuationLevel.PRICEY
    if r<Decimal('1.45'): return ValuationLevel.EXPENSIVE
    return ValuationLevel.EXTREME_CANDIDATE

def resolve_valuation(metrics: Sequence[Mapping[str,Any]], waterfall: Sequence[str]) -> ValuationResult:
    by={str(x.get('metric_name')):x for x in metrics}; chosen=None; fallback=False; reasons=[]
    for i,name in enumerate(waterfall):
        m=by.get(name)
        if not m: continue
        if m.get('data_quality') not in ('OK','FALLBACK_USED'): continue
        if m.get('freshness') not in ('FRESH','NOT_APPLICABLE'): continue
        if m.get('pit_status') not in ('VERIFIED','NOT_APPLICABLE'): continue
        chosen=m; fallback=i>0 or m.get('data_quality')=='FALLBACK_USED'; break
    if not chosen:
        return ValuationResult(ValuationLevel.UNKNOWN,CompletionState.INCOMPLETE,ExtremeValuationFlag.UNKNOWN,False,None,False,('VALUATION_DATA_INSUFFICIENT',))
    lvl=ValuationLevel(str(chosen.get('valuation_level','UNKNOWN'))) if str(chosen.get('valuation_level','UNKNOWN')) in {x.value for x in ValuationLevel} else ValuationLevel.UNKNOWN
    if lvl is ValuationLevel.UNKNOWN and chosen.get('current') is not None and chosen.get('historical_median') is not None:
        lvl=relative_multiple_level(chosen['current'],chosen['historical_median'])
    sec=str(chosen.get('secondary_confirmation','UNAVAILABLE')).upper(); pct=_d(chosen.get('expensiveness_percentile'))
    ratio=None
    if chosen.get('current') is not None and chosen.get('historical_median') is not None:
        c,m=_d(chosen['current']),_d(chosen['historical_median']); ratio=(c/m if c is not None and m and m>0 else None)
    extreme_candidate=lvl is ValuationLevel.EXTREME_CANDIDATE
    confirm_extreme=sec in ('STRONG','EXTREME')
    hist_extreme=pct is not None and pct>=95
    ratio_extreme=ratio is not None and ratio>=Decimal('1.45')
    flag=ExtremeValuationFlag.ON if extreme_candidate and (hist_extreme or confirm_extreme) else ExtremeValuationFlag.OFF
    if not extreme_candidate and (hist_extreme or ratio_extreme) and confirm_extreme: flag=ExtremeValuationFlag.ON
    if lvl is ValuationLevel.UNKNOWN: reasons.append('VALUATION_LEVEL_UNKNOWN')
    return ValuationResult(lvl,CompletionState.COMPLETE if lvl is not ValuationLevel.UNKNOWN else CompletionState.UNKNOWN,flag,lvl is not ValuationLevel.UNKNOWN,str(chosen.get('metric_name')),fallback,tuple(reasons))

@dataclass(frozen=True, slots=True)
class FundamentalsResult:
    context: ContextStatus; formal_output_eligible: bool; missing_required_fields: tuple[str,...]; reason_codes: tuple[str,...]

def evaluate_fundamentals(fields: Sequence[Mapping[str,Any]]) -> FundamentalsResult:
    missing=[]; directions=[]
    for f in fields:
        req=str(f.get('requirement_level','OPTIONAL'))
        state=str(f.get('field_value_state','UNKNOWN'))
        q=str(f.get('data_quality','UNKNOWN'))
        if req in ('SAFETY_REQUIRED','MODULE_REQUIRED') and (state=='UNKNOWN' or q in ('INSUFFICIENT','UNKNOWN')): missing.append(str(f.get('field_name','?')))
        directions.append(str(f.get('direction','UNKNOWN')))
    if missing: return FundamentalsResult(ContextStatus.UNKNOWN,False,tuple(missing),('FUNDAMENTAL_DATA_INSUFFICIENT',))
    known=[d for d in directions if d not in ('UNKNOWN','NOT_APPLICABLE')]
    if not known: return FundamentalsResult(ContextStatus.UNKNOWN,False,(),('FUNDAMENTAL_CONTEXT_UNKNOWN',))
    if 'DETERIORATING' in known: ctx=ContextStatus.NEGATIVE
    elif 'IMPROVING' in known: ctx=ContextStatus.POSITIVE
    else: ctx=ContextStatus.NEUTRAL
    return FundamentalsResult(ctx,True,(),())

@dataclass(frozen=True, slots=True)
class TechnicalState:
    right_confirmation: PredicateTruth; runaway_up: PredicateTruth; runaway_down: PredicateTruth

def evaluate_technical(*, right_signals:Sequence[PredicateTruth], up_price:Sequence[PredicateTruth], up_confirm:Sequence[PredicateTruth], down_break:Sequence[PredicateTruth], down_accel:Sequence[PredicateTruth], ma20_ok:PredicateTruth=PredicateTruth.TRUE) -> TechnicalState:
    right=threshold_truth(right_signals,3)
    up=tri_and(threshold_truth(up_price,1),threshold_truth(up_confirm,3),ma20_ok)
    down=tri_and(threshold_truth(down_break,1),threshold_truth(down_accel,2))
    return TechnicalState(right,up,down)

@dataclass(frozen=True, slots=True)
class StructuralRiskResult:
    state: StructuralBreakState; risk_grade: CompanyRiskGrade; fundamental_cap_pct: Decimal|None; failed_count:int|None; reason_codes:tuple[str,...]

def evaluate_structural_risk(theses: Sequence[Mapping[str,Any]], confirmation: PredicateTruth) -> StructuralRiskResult:
    if any(str(t.get('state','UNKNOWN'))=='UNKNOWN' for t in theses): return StructuralRiskResult(StructuralBreakState.UNKNOWN,CompanyRiskGrade.UNKNOWN,None,None,('THESIS_STATE_UNKNOWN',))
    failed=[t for t in theses if str(t.get('state'))=='FAILED']; critical=any(bool(t.get('critical')) for t in failed); n=len(failed)
    if critical or n>=3: grade,cap=CompanyRiskGrade.R3,Decimal('0')
    elif n==2: grade,cap=CompanyRiskGrade.R2,Decimal('25')
    elif n==1: grade,cap=CompanyRiskGrade.R1,Decimal('50')
    else: return StructuralRiskResult(StructuralBreakState.RESOLVED,CompanyRiskGrade.NONE,Decimal('100'),0,())
    if confirmation is PredicateTruth.UNKNOWN: state=StructuralBreakState.UNKNOWN
    elif confirmation is PredicateTruth.FALSE: state=StructuralBreakState.PENDING_CONFIRMATION
    else: state=StructuralBreakState.ACTIVE
    return StructuralRiskResult(state,grade,cap,n,())

@dataclass(frozen=True, slots=True)
class PermissionResult:
    hard_gate: HardGateState; new_buy_order_permission: bool; reason_codes: tuple[str,...]

def arbitrate_permission(*, safety_sufficiency:SufficiencyResult, hard_gate_predicates:Sequence[PredicateTruth], runaway_down:PredicateTruth, structural:StructuralRiskResult, emergency_status:str='NONE') -> PermissionResult:
    # Missing safety data is fail-closed but is not fabricated as a triggered market gate.
    if not safety_sufficiency.formal_output_eligible:
        return PermissionResult(HardGateState.UNKNOWN,False,('DATA_INSUFFICIENCY',))
    if any(x is PredicateTruth.TRUE for x in hard_gate_predicates): gate=HardGateState.TRIGGERED
    elif any(x is PredicateTruth.UNKNOWN for x in hard_gate_predicates): gate=HardGateState.UNKNOWN
    else: gate=HardGateState.NOT_TRIGGERED
    # Preserve the W3 cross-domain preemption order in diagnostics as well:
    # confirmed emergency > structural risk > pending emergency > hard gate > special.
    reasons=[]
    if emergency_status == 'CONFIRMED': reasons.append('EMERGENCY_PREEMPTION_CONFIRMED')
    if structural.state is StructuralBreakState.ACTIVE: reasons.append('STRUCTURAL_RISK_PREEMPTION')
    if emergency_status == 'PENDING_VERIFICATION': reasons.append('EMERGENCY_PREEMPTION_PENDING_VERIFICATION')
    if gate is HardGateState.TRIGGERED: reasons.append('HARD_GATE_TRIGGERED')
    if gate is HardGateState.UNKNOWN: reasons.append('HARD_GATE_UNKNOWN')
    if runaway_down is PredicateTruth.TRUE: reasons.append('RUNAWAY_DOWN')
    if runaway_down is PredicateTruth.UNKNOWN: reasons.append('RUNAWAY_DOWN_UNKNOWN')
    allow=not reasons
    return PermissionResult(gate,allow,tuple(reasons))

PRIMARY_SPECIAL_PRIORITY = (
    ("TRUE_RISK_REDUCTION", "真正降低風險"),
    ("RUNAWAY_DOWN", "Runaway Down"),
    ("TECHNICAL_REDUCTION", "技術減碼"),
    ("RUNAWAY_UP", "Runaway Up"),
    ("RIGHT_ADD", "右側加碼"),
    ("LEFT_BUY_POINT", "左側買點"),
)

def arbitrate_primary_special_classification(predicates: Mapping[str, PredicateTruth]) -> str:
    """W3 six-class priority with fail-closed UNKNOWN propagation."""
    higher_unknown=False
    for key, label in PRIMARY_SPECIAL_PRIORITY:
        state=predicates.get(key, PredicateTruth.UNKNOWN)
        if state is PredicateTruth.UNKNOWN:
            higher_unknown=True
            continue
        if state is PredicateTruth.TRUE:
            return "UNKNOWN" if higher_unknown else label
    return "UNKNOWN" if higher_unknown else "無特殊分類"

@dataclass(frozen=True, slots=True)
class CoreRuleState:
    valuation: ValuationResult
    fundamentals: FundamentalsResult
    technical: TechnicalState
    structural_risk: StructuralRiskResult
    permission: PermissionResult


def evaluate_core_rule_state(*, valuation_metrics:Sequence[Mapping[str,Any]], valuation_waterfall:Sequence[str],
    fundamental_fields:Sequence[Mapping[str,Any]], safety_facts:Sequence[EvidenceFact],
    right_signals:Sequence[PredicateTruth], up_price:Sequence[PredicateTruth], up_confirm:Sequence[PredicateTruth],
    down_break:Sequence[PredicateTruth], down_accel:Sequence[PredicateTruth], hard_gate_predicates:Sequence[PredicateTruth],
    theses:Sequence[Mapping[str,Any]], structural_confirmation:PredicateTruth, ma20_ok:PredicateTruth=PredicateTruth.TRUE,
    emergency_status:str='NONE') -> CoreRuleState:
    """Canonical W7 ordering after upstream Macro Safety facts are supplied.

    This is deliberately not a deployment engine: it produces state/permission
    only and never computes stage, target, gap, quantity, notional, or orders.
    """
    valuation=resolve_valuation(valuation_metrics,valuation_waterfall)
    fundamentals=evaluate_fundamentals(fundamental_fields)
    technical=evaluate_technical(right_signals=right_signals,up_price=up_price,up_confirm=up_confirm,
        down_break=down_break,down_accel=down_accel,ma20_ok=ma20_ok)
    structural=evaluate_structural_risk(theses,structural_confirmation)
    permission=arbitrate_permission(safety_sufficiency=evaluate_sufficiency(safety_facts),hard_gate_predicates=hard_gate_predicates,
        runaway_down=technical.runaway_down,structural=structural,emergency_status=emergency_status)
    return CoreRuleState(valuation,fundamentals,technical,structural,permission)
