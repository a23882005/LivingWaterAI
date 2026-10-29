"""V82 approved v1.0 PV3 / CMR7. Pure analysis, never order authorization.

The historical selector's thresholds are retained. The owner-approved profile
now supplies native stages, with named range/constraint evidence and complete
Right Entry, instead of accepting an unexplained external stage number.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .enums import PredicateTruth, NormalDeploymentMode
from .core_rules import tri_and, threshold_truth
from .deployment import DeploymentDecision, STAGE_RATE_PCT, select_deployment_mode

VERSION = 'V82_APPROVED_IMPLEMENTATION_1.0'
SPEC_SHA256 = '816adc16dc23d982a327e0c99a8cfba992a5fb3a58cfeb5ec10bcdf61cdc9a4f'
P = PredicateTruth
CUTS = {'GLOBAL_EQUITY_ETF': ('14','18'), 'US_LARGE_CORE_ETF': ('16','20'),
    'TECH_AI_HIGH_GROWTH_ETF': ('18','24'), 'TAIWAN_LARGE_CAP_ETF': ('14','19'),
    'PHARMA_HEALTHCARE_ETF': ('14','19'), 'US_SMALL_MID_CAP_ETF': ('13','18'),
    'SEMICONDUCTOR_ETF': None, 'DEFENSE_MILITARY_ETF': None, 'SECTOR_THEME_ETF': None,
    'LARGE_MATURE_HIGH_QUALITY_STOCK': None, 'HIGH_BETA_EVENT_STOCK': None}
METRICS = frozenset(('FORWARD_PE','TRAILING_PE','CAPE','PB','PTBV','EV_EBITDA','EV_SALES','PS','FCF_YIELD'))


def number(value, low=None, high=None):
    if value is None or isinstance(value, (bool,float)): return None
    try: value = Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError): return None
    if not value.is_finite() or (low is not None and value<Decimal(low)) or (high is not None and value>Decimal(high)): return None
    return value


def truth(value):
    if value is True:return P.TRUE
    if value is False:return P.FALSE
    if value is None:return P.UNKNOWN
    return P(value)


def negate(value):
    value=truth(value)
    return P.FALSE if value is P.TRUE else P.TRUE if value is P.FALSE else P.UNKNOWN


def compare(value, operator, bound):
    value=number(value);bound=number(bound)
    if value is None or bound is None:return P.UNKNOWN
    return truth({'LT':lambda:value<bound,'LE':lambda:value<=bound,'GT':lambda:value>bound,
        'GE':lambda:value>=bound,'EQ':lambda:value==bound}[operator]())


def absolute_range(*, profile, metric, current, proof, snapshot_id, decision_at):
    """Class membership alone is insufficient evidence that a range applies."""
    out={'normal':P.UNKNOWN.value,'cheap':P.UNKNOWN.value,'status':'RANGE_RESOLUTION_UNAVAILABLE',
        'proof':deepcopy(proof),'reason_codes':[]}
    if metric not in METRICS:
        out['reason_codes']=['NONVALUATION_PRIMARY_UNSUPPORTED'];return out
    if metric!='FORWARD_PE':
        return {**out,'normal':'TRUE','cheap':'TRUE','status':'NOT_APPLICABLE_NON_FORWARD_PE'}
    proof=proof or {}
    if proof.get('override_requested'):
        out['reason_codes']=['DEDICATED_RANGE_OVERRIDE_UNSUPPORTED'];return out
    if profile not in CUTS or proof.get('snapshot_id')!=snapshot_id or not proof.get('source_reference'):
        out['reason_codes']=['RANGE_IDENTITY_OR_SOURCE_REQUIRED'];return out
    if proof.get('profile')!=profile or proof.get('product_type_verified') is not True:
        out['reason_codes']=['RANGE_PRODUCT_TYPE_NOT_VERIFIED'];return out
    try:
        at=datetime.fromisoformat(decision_at.replace('Z','+00:00'))
        start=datetime.fromisoformat(proof['effective_from'].replace('Z','+00:00'))
        end=datetime.fromisoformat(proof['effective_until'].replace('Z','+00:00')) if proof.get('effective_until') else None
        valid=at.utcoffset() is not None and start.utcoffset() is not None and start<=at and (end is None or at<end)
    except (KeyError,ValueError,TypeError):valid=False
    if not valid or not proof.get('range_version'):
        out['reason_codes']=['RANGE_VERSION_OR_EFFECTIVITY_REQUIRED'];return out
    applies=truth(proof.get('applicability'))
    if applies is P.FALSE and proof.get('no_applicable_range_verified') is True:
        return {**out,'normal':'TRUE','cheap':'TRUE','status':'NOT_APPLICABLE_VERIFIED_NO_FIXED_RANGE'}
    if applies is not P.TRUE or CUTS[profile] is None:
        out['reason_codes']=['RANGE_APPLICABILITY_UNKNOWN_OR_UNSUPPORTED'];return out
    if proof.get('range_id')!=profile+'_FORWARD_PE' or number(current,'0') in (None,Decimal(0)):
        out['reason_codes']=['RANGE_OR_CURRENT_PRIMARY_INVALID'];return out
    cheap,normal=CUTS[profile]
    return {**out,'normal':compare(current,'LT',normal).value,'cheap':compare(current,'LT',cheap).value,
        'status':'APPLICABLE','normal_upper_exclusive':normal,'cheap_upper_exclusive':cheap}


def _select(states, *, nested=False):
    """Select a highest TRUE only when all higher candidates are FALSE."""
    ordered=sorted(states)
    if nested and any(states[a] is P.FALSE and states[b] is P.TRUE for a in ordered for b in ordered if a<b):
        return {'stage':None,'status':'NESTING_OR_INPUT_CONFLICT','known_lower_bound':None,'possible_upper_bound':None}
    known=[s for s in ordered if states[s] is P.TRUE]
    possible=[s for s in ordered if states[s] is not P.FALSE]
    lower=max(known) if known else None;upper=max(possible) if possible else None
    stage=lower if lower==upper else None
    return {'stage':'STAGE_'+str(stage) if stage else None,
        'status':'COMPLETE' if stage else 'UNKNOWN' if possible else 'NO_STAGE_SUPPORTED_BY_THIS_PROFILE',
        'known_lower_bound':lower,'possible_upper_bound':upper}


def left_profile(*, price_entry, valuation_legal, depth, q_price, q_value, metric, current, range_result):
    legal=truth(valuation_legal) if metric in METRICS else P.UNKNOWN
    if metric=='FORWARD_PE' and number(current,'0') in (None,Decimal(0)):legal=tri_and(legal,P.UNKNOWN)
    b2=tri_and(truth(price_entry),legal)
    states={2:b2};clauses={2:{'price_entry':truth(price_entry).value,'valuation_legal':legal.value}}
    qp=number(q_price,'0','100');qv=number(q_value,'0','100');d=number(depth,'0')
    for stage,p_cut,v_cut in ((3,'75','60'),(4,'75','40'),(5,'90','40'),(6,'90','20'),(7,'97.5','20')):
        parts={'B2':b2,'positive_depth':compare(d,'GT','0'),
            'qP':compare(qp,'GE',p_cut),'qV':compare(qv,'LT',v_cut),
            'absolute_range':truth(range_result.get('cheap' if stage>=6 else 'normal'))}
        states[stage]=tri_and(*parts.values());clauses[stage]={k:v.value for k,v in parts.items()}
    return {**_select(states,nested=True),'eligible':{str(k):v.value for k,v in states.items()},
        'clauses':{str(k):v for k,v in clauses.items()},'raw_inputs':{'depth':str(d) if d is not None else None,
            'qP':str(qp) if qp is not None else None,'qV':str(qv) if qv is not None else None},
        'range_result':deepcopy(range_result),'profile_version':VERSION}


def event_recheck(dependencies, *, dependency_scope_verified):
    if dependency_scope_verified is not True:return P.UNKNOWN
    results=[];seen=set()
    for event in dependencies:
        eid=event.get('event_id')
        if not eid or eid in seen:raise ValueError('RIGHT_EVENT_IDENTITY_OR_DUPLICATE')
        seen.add(eid);depends=truth(event.get('depends_on_event_gap'))
        if depends is P.FALSE:continue
        if depends is P.UNKNOWN:results.append(P.UNKNOWN)
        else:results.append(P.TRUE if event.get('recheck_state')=='PASSED' else
            P.FALSE if event.get('recheck_state') in ('PENDING','FAILED') else P.UNKNOWN)
    # Empty is neutral only with an explicitly verified dependency scope.
    return tri_and(*results) if results else P.TRUE


def right_entry(*, off_low, right_confirmation, fundamentals_viable, credit_allows,
                runaway_down, valuation_condition, event_dependencies, dependency_scope_verified):
    parts={'off_low':truth(off_low),'right_confirmation':truth(right_confirmation),
        'fundamentals_viable':truth(fundamentals_viable),'credit_liquidity_allows':truth(credit_allows),
        'not_runaway_down':negate(runaway_down),'applicable_valuation':truth(valuation_condition),
        'event_required_t_plus_1':event_recheck(event_dependencies,dependency_scope_verified=dependency_scope_verified)}
    return {'truth':tri_and(*parts.values()).value,'components':{k:v.value for k,v in parts.items()},
        'rule':'CMR7.2 / TECH4.1','hard_gate_is_not_a_right_analysis_dependency':True,
        'event_dependencies':deepcopy(event_dependencies)}


def apply_restrictions(states, restrictions, *, snapshot_id):
    out={int(k):truth(v) for k,v in states.items()};audit=[]
    seen=set()
    for row in restrictions:
        rid=row.get('restriction_id');effect=row.get('effect') or {};expression=row.get('expression')
        valid=(bool(rid) and rid not in seen and bool(row.get('source')) and bool(row.get('authority'))
            and row.get('snapshot_id')==snapshot_id and isinstance(expression,str) and bool(expression.strip())
            and effect.get('kind') in ('MAX_STAGE','REQUIRE_STAGE_PREDICATE'))
        if rid:seen.add(rid)
        applies=truth(row.get('applies_when')) if valid else P.UNKNOWN
        limit=effect.get('stage');requirement=truth(row.get('expression_truth')) if valid else P.UNKNOWN
        if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=9:valid=False
        for stage in out:
            if not valid:
                out[stage]=tri_and(out[stage],P.UNKNOWN);continue
            if applies is P.FALSE:continue
            affected=stage>limit if effect['kind']=='MAX_STAGE' else stage>=limit
            if affected:
                condition=P.FALSE if effect['kind']=='MAX_STAGE' else requirement
                if applies is P.UNKNOWN and condition is not P.TRUE:condition=P.UNKNOWN
                out[stage]=tri_and(out[stage],condition)
        audit.append({'restriction_id':rid,'source':row.get('source'),'authority':row.get('authority'),
            'expression':expression,'effect':deepcopy(effect),'valid':valid,
            'reason':None if valid else 'NAMED_STAGE_CONSTRAINT_UNRESOLVED'})
    return out,audit


def resolve_approved_stage(*, mode, left_result, q_value, range_result, required_facts,
                           restrictions, snapshot_id):
    mode=NormalDeploymentMode(mode)
    required={'asset_identity','primary_framework','fundamentals_viable','valuation_legal'}
    unknown=sorted(required-set(required_facts))+sorted(k for k,v in required_facts.items() if truth(v) is P.UNKNOWN)
    rejected=sorted(k for k,v in required_facts.items() if truth(v) is P.FALSE)
    if mode is NormalDeploymentMode.LEFT_OVERWEIGHT:
        states={int(k):truth(v) for k,v in left_result['eligible'].items()}
    elif mode is NormalDeploymentMode.TREND_DEPLOYMENT:
        full=tri_and(compare(number(q_value,'0','100'),'LT','60'),truth(range_result.get('normal')))
        states={8:P.TRUE,9:full}
    elif mode is NormalDeploymentMode.BASE_DEPLOYMENT:states={1:P.TRUE}
    elif mode is NormalDeploymentMode.RIGHT_CONFIRMATION:states={8:P.TRUE}
    else:states={}
    states,audit=apply_restrictions(states,restrictions,snapshot_id=snapshot_id)
    selection=_select(states,nested=mode is NormalDeploymentMode.LEFT_OVERWEIGHT)
    stage=selection['stage'] if not unknown and not rejected else None
    reasons=[*('STAGE_REQUIRED_UNKNOWN:'+k for k in unknown),*('STAGE_REQUIRED_FALSE:'+k for k in rejected)]
    if stage is None:reasons.append(selection['status'] if not unknown and not rejected else 'STAGE_NECESSARY_FACTS_UNRESOLVED')
    decision=DeploymentDecision(mode,stage or 'UNKNOWN',STAGE_RATE_PCT[stage]/100 if stage else None,tuple(reasons))
    return decision,{'profile_version':VERSION,'selection':selection,'required_unknown_fields':unknown,
        'required_false_fields':rejected,'candidate_stage_evidence':{str(k):v.value for k,v in states.items()},
        'stage_restrictions':audit,'snapshot_id':snapshot_id}


def select_with_entries(*, runaway_up, runaway_down, right, left):
    up,down=truth(runaway_up),truth(runaway_down)
    if up is P.TRUE and down is P.TRUE:
        return NormalDeploymentMode.UNKNOWN,('INCOMPATIBLE_UP_DOWN_SAME_RUN_RECONCILIATION_REQUIRED',)
    return select_deployment_mode(runaway_up=up,right_add=truth(right),left_buy_point=truth(left)),()
