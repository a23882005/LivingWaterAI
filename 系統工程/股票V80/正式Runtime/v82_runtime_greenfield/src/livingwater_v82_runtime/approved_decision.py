"""One approved v1.0 analysis/velocity contract for Family and native V82."""
from copy import deepcopy
from .approved_profiles import (VERSION,SPEC_SHA256,P,truth,negate,number,absolute_range,
    left_profile,right_entry,resolve_approved_stage,select_with_entries)
from .core_rules import tri_and
from .own_history import valuation_percentile,price_percentile,unknown
from .daily_slice import maturity,speed,trend_timing,cycle_room,validate_cycle
from .slice_allocation import funding_layers


def _or(values):
    values=[truth(v) for v in values]
    return P.TRUE if P.TRUE in values else P.UNKNOWN if P.UNKNOWN in values or not values else P.FALSE


def evaluate(context, core):
    """No cash, gap, or permission participates in Mode / Stage selection.

    core is the original core's JSON-compatible result. qP/qV are recomputed
    from their own source records; unqualified direct percentile numbers are
    not an alternate input route.
    """
    if context.get('schema_version')!='V82.ApprovedDecisionContext.v1' or context.get('spec_sha256')!=SPEC_SHA256:
        raise ValueError('APPROVED_V10_CONTEXT_VERSION_MISMATCH')
    identity=context['identity'];technical=core['technical'];valuation=core['valuation']
    snapshot=identity['snapshot_id'];at=identity['evaluation_at'];asset=identity['asset_id']
    selected=valuation.get('primary_metric');current=context.get('current_metric_value')
    legal='TRUE' if valuation.get('formal_output_eligible') is True else 'UNKNOWN'
    qv=unknown('OWN_METRIC_COMPARABLE_PIT_HISTORY_SOURCE_UNAVAILABLE')
    qp=unknown('OWN_RAW_PRICE_CALENDAR_AND_EVENT_COVERAGE_SOURCE_UNAVAILABLE',depth=None)
    for key,fn in (('valuation_history',valuation_percentile),('price_history',price_percentile)):
        source=context.get(key)
        if source is None:continue
        source=deepcopy(source)
        if (source.get('identity',{}).get('asset_id')!=asset
                or source.get('identity',{}).get('currency')!=identity['owner']['currency']
                or any(source.get('identity',{}).get(k)!=context.get('market_identity',{}).get(k) for k in ('listing','share_class'))):
            result=unknown('PV2_SOURCE_INSTRUMENT_IDENTITY_CONFLICT',depth=None)
        elif key=='valuation_history' and (source['identity'].get('metric_name')!=selected
                or number(source.get('current',{}).get('value'))!=number(current)):
            result=unknown('PV2_CURRENT_PRIMARY_SOURCE_CONFLICT')
        else:
            source['decision_at']=at;result=fn(**source)
        if key=='valuation_history':qv=result
        else:qp=result
    ranged=absolute_range(profile=context['profile_id'],metric=selected,current=current,
        proof=context.get('absolute_range_proof'),snapshot_id=snapshot,decision_at=at)
    price=_or(context.get('left_price_conditions',{}).values())
    fundamental=truth(context.get('fundamentals_viable'))
    safety=truth(context.get('left_safety'))
    if core['permission']['hard_gate']=='TRIGGERED':safety=P.FALSE
    left=tri_and(price,fundamental,safety)
    right=right_entry(off_low=context.get('off_low'),right_confirmation=technical['right_confirmation'],
        fundamentals_viable=fundamental,credit_allows=context.get('credit_allows_right'),
        runaway_down=technical['runaway_down'],valuation_condition=tri_and(truth(legal),truth(context.get('right_valuation_condition'))),
        event_dependencies=context.get('right_event_dependencies',[]),
        dependency_scope_verified=context.get('right_event_dependency_scope_verified'))
    mode,conflicts=select_with_entries(runaway_up=technical['runaway_up'],runaway_down=technical['runaway_down'],
        right=right['truth'],left=left)
    pv=left_profile(price_entry=price,valuation_legal=legal,depth=qp.get('depth'),q_price=qp['value'],q_value=qv['value'],
        metric=selected,current=current,range_result=ranged)
    required={**context.get('stage_required_facts',{}),'fundamentals_viable':fundamental.value,'valuation_legal':legal}
    decision,stage_audit=resolve_approved_stage(mode=mode,left_result=pv,q_value=qv['value'],range_result=ranged,
        required_facts=required,restrictions=context.get('stage_restrictions',[]),snapshot_id=snapshot,
        constraint_facts=context.get('stage_constraint_facts'))
    if conflicts:
        decision=type(decision)(mode,'UNKNOWN',None,conflicts)
    mat=maturity(context.get('maturity_signals',[]))
    velocity=speed(mode=mode,maturity_result=mat,credit_level=context.get('credit_level'),
        core_etf=context.get('core_etf'),high_beta=context.get('high_beta'),
        macro_pressure=context.get('macro_pressure'),extreme_valuation=valuation['extreme_flag'])
    timing={'truth':'TRUE','status':'NOT_APPLICABLE_NON_TREND'}
    if mode.value=='Trend Deployment':
        timing=trend_timing(**context.get('trend_timing_inputs',{
            'bars':[],'ma5':None,'ma10':None,'ma20':None,'previous_atr14':None,'previous_close':None,
            'breakout_retest_success':'UNKNOWN'}),current_up=technical['runaway_up'])
    layers=None
    if context.get('funding_layers') is not None:
        try:layers=funding_layers(**context['funding_layers'])
        except (ValueError,TypeError,KeyError) as error:layers={'status':'SOURCE_CONFLICT','reason_codes':[str(error)]}
    return {'profile_version':VERSION,'spec_sha256':SPEC_SHA256,'identity':deepcopy(identity),
        'market_predicates':{'runaway_up':technical['runaway_up'],'right':right['truth'],'left':left.value},
        'left_inputs':{'price_condition_at_least_one':price.value,
            'price_conditions':deepcopy(context.get('left_price_conditions',{})),
            'fundamentals_long_term_viable':fundamental.value,'left_safety_negations_absent':safety.value},
        'right_entry':right,'range_result':ranged,'qV':qv,'qP':qp,'left_stage_profile':pv,
        'selected_mode':mode.value,'formal_stage':decision.stage,
        'canonical_target_rate':str(decision.target_rate) if decision.target_rate is not None else None,
        'stage_audit':stage_audit,'reason_codes':list(decision.reason_codes),'conflicts':list(conflicts),
        'maturity':mat,'speed':velocity,'trend_timing':timing,
        'funding_layers':layers,
        'call_trace':['V82.PV2.own_history','V82.PV3.left_profile','V82.CMR7.complete_right_entry',
            'V82.select_deployment_mode','V82.CMR7.resolve_approved_stage','V82.CMR8.maturity_speed_trend_timing'],
        'trade_action':'NO_TRADE'}


def slice_cap(analysis,context,*,permission,positive_gap,known_zero_capacity=False):
    """Consume an already persisted cycle. A missing ledger is not an empty one."""
    cycle=(context.get('cycle_snapshot') or {}).get('cycle')
    session=context.get('session') or {};timing=analysis['trend_timing']['truth']
    out={'profile_version':VERSION,'speed':deepcopy(analysis['speed']),
        'maturity':deepcopy(analysis['maturity']),'trend_timing':deepcopy(analysis['trend_timing']),
        'cap':None,'cycle':None,'status':'CYCLE_LEDGER_SOURCE_UNAVAILABLE',
        'unknown_cash_defaulted_to_zero':False,'cash_reservation_deducted':False}
    if cycle is not None:
        validate_cycle(cycle)
        expected=context['identity']
        if (cycle['owner']!=expected['owner'] or cycle['asset_id']!=expected['asset_id']
                or cycle['exchange']!=session.get('exchange') or cycle['profile_version']!=VERSION):
            raise ValueError('V10_CYCLE_OWNER_ASSET_EXCHANGE_MISMATCH')
        result=cycle_room(cycle,speed_result=analysis['speed'],permission=permission,
            trend_allowed=timing,session_id=session.get('session_id'),session_open=session.get('open_for_planning'))
        out.update(cap=result['cycle_room'],cycle=result,status='COMPUTED' if result['cycle_room'] is not None else 'NECESSARY_SLICE_INPUT_UNKNOWN')
    if permission is False or timing=='FALSE' or known_zero_capacity or number(positive_gap)==0 or analysis['speed'].get('credit_multiplier')=='0':
        out.update(cap='0',status='KNOWN_NO_NEW_BUY__ORIGINAL_UNKNOWNS_RETAINED')
    return out
