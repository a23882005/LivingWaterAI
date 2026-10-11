from livingwater_v82_runtime.core_rules import *
from livingwater_v82_runtime.enums import *

def main():
    checks=[]
    def ck(name,cond): checks.append((name,bool(cond)))
    # relative valuation boundaries
    vals=[(.79,ValuationLevel.CHEAP),(.8,ValuationLevel.NORMAL),(1.09,ValuationLevel.NORMAL),(1.1,ValuationLevel.PRICEY),(1.24,ValuationLevel.PRICEY),(1.25,ValuationLevel.EXPENSIVE),(1.44,ValuationLevel.EXPENSIVE),(1.45,ValuationLevel.EXTREME_CANDIDATE)]
    for i,(r,e) in enumerate(vals): ck(f'VAL-{i+1:02}',relative_multiple_level(r,1)==e)
    # threshold three-value semantics
    T,F,U=PredicateTruth.TRUE,PredicateTruth.FALSE,PredicateTruth.UNKNOWN
    ck('TRI-01',threshold_truth([T,T,T],3)==T); ck('TRI-02',threshold_truth([T,T,U],3)==U); ck('TRI-03',threshold_truth([T,T,F],3)==F)
    ck('TRI-04',tri_and(T,T)==T); ck('TRI-05',tri_and(T,U)==U); ck('TRI-06',tri_and(T,F)==F)
    # sufficiency partial/fail closed
    ok=EvidenceFact('x',1,RequirementLevel.SAFETY_REQUIRED,DataQuality.OK,Freshness.FRESH,PitStatus.VERIFIED)
    bad=EvidenceFact('y',None,RequirementLevel.SAFETY_REQUIRED,DataQuality.INSUFFICIENT,Freshness.UNKNOWN,PitStatus.UNVERIFIABLE,issue_codes=('MISSING',))
    opt=EvidenceFact('z',None,RequirementLevel.OPTIONAL,DataQuality.INSUFFICIENT,Freshness.UNKNOWN)
    ck('DATA-01',evaluate_sufficiency([ok]).formal_output_eligible)
    ck('DATA-02',not evaluate_sufficiency([ok,bad]).formal_output_eligible)
    ck('DATA-03',evaluate_sufficiency([ok,opt]).formal_output_eligible)
    ck('DATA-04','MISSING' in evaluate_sufficiency([bad]).issue_codes)
    pit_bad=EvidenceFact('pit',1,RequirementLevel.SAFETY_REQUIRED,DataQuality.OK,Freshness.FRESH,PitStatus.UNVERIFIABLE)
    pit_opt=EvidenceFact('pit_optional',1,RequirementLevel.OPTIONAL,DataQuality.OK,Freshness.FRESH,PitStatus.UNVERIFIABLE)
    ck('DATA-05',not evaluate_sufficiency([pit_bad]).formal_output_eligible)
    ck('DATA-06',evaluate_sufficiency([pit_bad]).quality==DataQuality.UNKNOWN)
    ck('DATA-07',evaluate_sufficiency([pit_opt]).formal_output_eligible)
    # valuation fallback/extreme
    v=resolve_valuation([{'metric_name':'PE','data_quality':'OK','freshness':'FRESH','pit_status':'VERIFIED','current':15,'historical_median':20,'secondary_confirmation':'UNAVAILABLE'}],['PE'])
    ck('VAL-09',v.level==ValuationLevel.CHEAP and v.formal_output_eligible)
    v2=resolve_valuation([{'metric_name':'PE','data_quality':'INSUFFICIENT','freshness':'STALE','pit_status':'VERIFIED'}],['PE'])
    ck('VAL-10',not v2.formal_output_eligible and v2.completion==CompletionState.INCOMPLETE)
    v3=resolve_valuation([{'metric_name':'EV','data_quality':'OK','freshness':'FRESH','pit_status':'VERIFIED','current':1.5,'historical_median':1,'expensiveness_percentile':96,'secondary_confirmation':'STRONG'}],['PE','EV'])
    ck('VAL-11',v3.fallback_used and v3.extreme_flag==ExtremeValuationFlag.ON)
    # fundamentals
    fgood=[{'field_name':'rev','requirement_level':'MODULE_REQUIRED','field_value_state':'KNOWN','data_quality':'OK','direction':'IMPROVING'}]
    fbad=[{'field_name':'rev','requirement_level':'MODULE_REQUIRED','field_value_state':'UNKNOWN','data_quality':'UNKNOWN','direction':'UNKNOWN'}]
    ck('FUND-01',evaluate_fundamentals(fgood).context==ContextStatus.POSITIVE)
    ck('FUND-02',not evaluate_fundamentals(fbad).formal_output_eligible)
    # technical exact approved counts
    tech=evaluate_technical(right_signals=[T,T,T],up_price=[T],up_confirm=[T,T,T],down_break=[F],down_accel=[T,T])
    ck('TECH-01',tech.right_confirmation==T); ck('TECH-02',tech.runaway_up==T); ck('TECH-03',tech.runaway_down==F)
    tech2=evaluate_technical(right_signals=[T,T,U],up_price=[U],up_confirm=[T,T,T],down_break=[T],down_accel=[T,U])
    ck('TECH-04',tech2.right_confirmation==U); ck('TECH-05',tech2.runaway_up==U); ck('TECH-06',tech2.runaway_down==U)
    # structural mapping
    for n,g,cap in [(0,CompanyRiskGrade.NONE,100),(1,CompanyRiskGrade.R1,50),(2,CompanyRiskGrade.R2,25),(3,CompanyRiskGrade.R3,0)]:
        r=evaluate_structural_risk([{'state':'FAILED','critical':False} for _ in range(n)],T)
        ck(f'RISK-{n+1:02}',r.risk_grade==g and r.fundamental_cap_pct==Decimal(str(cap)))
    r=evaluate_structural_risk([{'state':'FAILED','critical':True}],T); ck('RISK-05',r.risk_grade==CompanyRiskGrade.R3)
    r=evaluate_structural_risk([{'state':'FAILED','critical':False}],F); ck('RISK-06',r.state==StructuralBreakState.PENDING_CONFIRMATION)
    # hard gate permission separation
    suff=evaluate_sufficiency([ok]); struct=evaluate_structural_risk([],T)
    p=arbitrate_permission(safety_sufficiency=suff,hard_gate_predicates=[F],runaway_down=F,structural=struct)
    ck('GATE-01',p.hard_gate==HardGateState.NOT_TRIGGERED and p.new_buy_order_permission)
    p=arbitrate_permission(safety_sufficiency=suff,hard_gate_predicates=[T],runaway_down=F,structural=struct)
    ck('GATE-02',p.hard_gate==HardGateState.TRIGGERED and not p.new_buy_order_permission)
    p=arbitrate_permission(safety_sufficiency=evaluate_sufficiency([bad]),hard_gate_predicates=[F],runaway_down=F,structural=struct)
    ck('GATE-03',p.hard_gate==HardGateState.UNKNOWN and 'DATA_INSUFFICIENCY' in p.reason_codes)
    p=arbitrate_permission(safety_sufficiency=suff,hard_gate_predicates=[F],runaway_down=T,structural=struct)
    ck('GATE-04',not p.new_buy_order_permission and 'RUNAWAY_DOWN' in p.reason_codes)
    p=arbitrate_permission(safety_sufficiency=suff,hard_gate_predicates=[F],runaway_down=F,structural=evaluate_structural_risk([{'state':'FAILED','critical':False}],T))
    ck('GATE-05',not p.new_buy_order_permission and 'STRUCTURAL_RISK_PREEMPTION' in p.reason_codes)
    failed=[n for n,c in checks if not c]
    import json, pathlib
    out={'gate':'A78_W07_CORE_RULE_ENGINE_GATE','total':len(checks),'passed':len(checks)-len(failed),'failed':failed,'status':'PASS' if not failed else 'FAIL','checks':[{'id':n,'pass':c} for n,c in checks]}
    path=pathlib.Path(__file__).resolve().parents[2]/'QA_Results'; path.mkdir(exist_ok=True); (path/'A78_W07_CORE_RULE_ENGINE_GATE.json').write_text(json.dumps(out,indent=2))
    print(f"{out['passed']}/{out['total']} PASS" if not failed else out)
    raise SystemExit(1 if failed else 0)
if __name__=='__main__': main()
