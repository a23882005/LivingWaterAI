"""Source-bound Base/Left/Right/Trend analysis using the original V82 functions.

This view does not invoke funding Work4, create an order, or pretend unresolved
Stage/FX/orders are zero. Canonical deployment and Work9 remain independent.
"""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import sys
from approved_v04_technical import both,either,truth
from family_input import digest


def tri(value):
    if value is True or value=='TRUE':return True
    if value is False or value=='FALSE':return False
    return None


def neg(value):return None if value is None else not value


def native(root):
    path=Path(root)/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    import livingwater_v82_runtime as runtime
    if Path(runtime.__file__).resolve().parent!=path/'livingwater_v82_runtime':
        raise PermissionError('FORMAL_MODE_RUNTIME_SOURCE_MISMATCH')
    from livingwater_v82_runtime import deployment as dep
    from livingwater_v82_runtime.enums import PredicateTruth,NormalDeploymentMode
    return dep,PredicateTruth,NormalDeploymentMode


def resolve_mode_context(root,*,up,right,left_price_conditions,fundamentals_viable,left_safety,
                         stage_facts,left_stage=None,trend_stage=None):
    dep,P,M=native(root)
    price=either(*(left_price_conditions.values())) if left_price_conditions else None
    left=both(price,fundamentals_viable,left_safety)
    mode=dep.select_deployment_mode(runaway_up=P(truth(up)),right_add=P(truth(right)),left_buy_point=P(truth(left)))
    stage=dep.resolve_deployment_stage(mode=mode,left_stage=left_stage,trend_stage=trend_stage)
    required={'asset_identity','primary_framework','fundamentals_viable','valuation_legal'}
    unknown=sorted(required-set(stage_facts))
    unknown+=sorted(k for k,v in stage_facts.items() if v is None)
    blocked=sorted(k for k,v in stage_facts.items() if v is False)
    stage_ready=not unknown and not blocked and stage.stage!='UNKNOWN'
    return {'market_predicates':{'runaway_up':truth(up),'right':truth(right),'left':truth(left)},
        'left_inputs':{'price_condition_at_least_one':truth(price),
            'price_conditions':{k:truth(v) for k,v in left_price_conditions.items()},
            'fundamentals_long_term_viable':truth(fundamentals_viable),'left_safety_negations_absent':truth(left_safety)},
        'four_modes':{'Base':{'selection_predicate':truth(both(neg(up),neg(right),neg(left))),
                'technical_confirmation_required':False,'reference_stage':'STAGE_1'},
            'Left':{'market_predicate':truth(left),'reference_stages':['STAGE_'+str(i) for i in range(2,8)],
                'oversold_required_for_entry':False},
            'Right':{'market_predicate':truth(right),'reference_stage':'STAGE_8'},
            'Trend':{'market_predicate':truth(up),'reference_stage_maximum':'STAGE_9'}},
        'selected_mode':mode.value,'native_stage_result':{
            'mode':stage.mode.value,'stage':stage.stage,'target_rate':str(stage.target_rate) if stage.target_rate is not None else None,
            'reason_codes':list(stage.reason_codes)},
        'formal_stage':stage.stage if stage_ready else 'UNKNOWN',
        'canonical_target_rate':str(stage.target_rate) if stage_ready else None,
        'stage_required_unknown_fields':unknown,'stage_disallowed_fields':blocked,
        'call_trace':['V82.select_deployment_mode','V82.resolve_deployment_stage']}


def target_for_symbol(request,symbol,*,projection=None):
    lines=request.get('confirmed_target',{}).get('payload',{}).get('draft',{}).get('target_lines',[])
    found=[r for r in lines if r.get('ticker')==symbol]
    if not found and projection and symbol in projection.get('targets',{}):
        return deepcopy(projection['targets'][symbol]['target_amount'])
    if len(found)!=1:
        return {'value_state':'UNKNOWN','amount':None,'currency':None,
            'reason':'NO_UNIQUE_TARGET_FOR_THIS_SYMBOL_IN_CURRENT_APPROVED_ALLOCATION',
            'absence_is_not_zero':True}
    return deepcopy(found[0]['target_amount'])


def order_source(request,confirmation=None,*,broker_orders=None):
    if broker_orders is not None:
        if (broker_orders.get('schema_version')!='Family.W5.BrokerOrderExposure.v1'
            or broker_orders.get('client_id')!=request['client_id']
            or broker_orders.get('owner')!=request['owner'] or broker_orders.get('run_id')!=request['run_id']
            or broker_orders.get('source_descriptor_digest')!=request.get('broker_snapshot_source_digest')):
            raise PermissionError('BROKER_ORDER_SOURCE_BINDING_MISMATCH')
        return deepcopy(broker_orders)
    if confirmation is not None:
        if (confirmation.get('schema_version')!='Family.W8.OwnerNoOpenOrders.v1'
            or confirmation.get('client_id')!=request.get('client_id')
            or confirmation.get('owner')!=request.get('owner')
            or confirmation.get('no_open_orders') is not True
            or not confirmation.get('source_reference')):
            raise PermissionError('OWNER_NO_OPEN_ORDERS_SCOPE_MISMATCH')
        return {'status':'VERIFIED','active_orders':[],
            'basis':'OWNER_EXPLICIT_NO_OPEN_ORDERS','source':deepcopy(confirmation),
            'run_id':request['run_id'],'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
            'historical_order_or_fill_completeness_asserted':False}

    tables=request['client_snapshot']['payload']['tables'];badge=[]
    for row in tables.get('portfolio_snapshot_item',[]):
        if row.get('entity_key')=='IB_SCREEN' and row.get('field_key')=='order_tab_count':
            badge.append(deepcopy(row))
    # A screenshot tab badge is not an order ledger. No default active_orders=[]
    # is admitted when the owner has supplied only holdings or a badge count.
    return {'status':'UNKNOWN','active_orders':None,'screenshot_badge_facts':badge,
        'reason':'ORDER_DIRECTION_REMAINING_QTY_STATE_AND_FILL_RECONCILIATION_NOT_IN_SOURCE',
        'required_fields':['asset_id','side','state','order_qty','confirmed_filled_qty','as_of','available_at'],
        'checked_sources':['official SQLite portfolio_snapshot_item','official SQLite table schema','approved Project source'],
        'holdings_acceptance_is_not_order_completeness':True}


def native_orders(root,orders,symbol):
    if not orders.get('complete_for_open_order_exposure'):return ()
    dep,_,_=native(root)
    from livingwater_v82_runtime.enums import OrderLifecycleState
    return tuple(dep.ActiveOrderExposure(order_intent_id=o['order_intent_id'],side=o['side'],
        state=OrderLifecycleState(o['state']),order_qty=Decimal(o['order_qty']),
        confirmed_filled_qty=Decimal(o['confirmed_filled_qty']))
        for o in orders['active_orders'] if o['asset_id']==symbol)


def order_result_status(orders):
    if orders.get('complete_for_open_order_exposure'):
        return ('BROKER_WORKING_EXPOSURE_ACCOUNTED' if orders.get('lifecycle_fully_resolved')
            else 'BROKER_WORKING_EXPOSURE_ACCOUNTED__REPLACEMENT_LIFECYCLE_PENDING')
    return 'OWNER_CONFIRMED_NO_OPEN_ORDERS' if orders.get('status')=='VERIFIED' else 'PENDING_OWNER_ORDER_CONFIRMATION'


def event_coverage(request):
    raw=request.get('macro_snapshot',{}).get('payload',{})
    news=raw.get('news',[])
    return {'status':'NOT_VERIFIED','confirmed_no_active_event':None,'absence_asserted':False,
        'source_digest':request.get('macro_snapshot',{}).get('digest'),
        'source_path':request.get('macro_snapshot',{}).get('source_path'),
        'existing_news_rows':len(news) if isinstance(news,list) else None,
        'required_fields':['required_domain_coverage','event_registry_checkpoint','active_event_status','coverage_cutoff'],
        'reason':'NEWS_ROWS_ARE_NOT_A_VERIFIED_NEGATIVE_EVENT_SEARCH_OR_COMPLETE_ACTIVE_EVENT_REGISTRY'}


def build_formal_conclusion(root,row,request,*,target_projection=None,approved_source_descriptor=None):
    dep,P,M=native(root);core=row['core_observation']['result'];market=row['market'];approved=market.get('approved_technical',{})
    technical=core['technical'];up=tri(technical['runaway_up']);right_technical=tri(technical['right_confirmation']);down=tri(technical['runaway_down'])
    valuation=core['valuation'];legal=True if valuation['formal_output_eligible'] else None
    value_level=valuation['level'];value_zone=(value_level in ('CHEAP','NORMAL')) if legal else None
    # Required ETF structural facts are distinct from the company-thesis score
    # and the sign of aggregate earnings growth. The source facts are absent.
    viability=(etf_viability_audit(row,request) if row['native_product_identity'].get('asset_type')!='INDIVIDUAL_STOCK' else
        {'leaves':{'preregistered_thesis_contract':{'truth':'UNKNOWN'}},
            'call_trace':['V82.CMR6.individual_thesis_input_required'],'scope':'INDIVIDUAL_STOCK__NOT_ETF_VIABILITY'})
    fundamental_facts={k:tri(v['truth']) for k,v in viability['leaves'].items()}
    fundamental=both(*fundamental_facts.values())
    credit=(row.get('macro_observations') or {}).get('credit',{}).get('risk_level','UNKNOWN')
    credit_right=(credit<=1) if isinstance(credit,int) and not isinstance(credit,bool) else None
    credit_base=credit_right if credit!='UNKNOWN' else None
    if credit==2:credit_base=None # Explicit core/high-beta applicability evidence is required.
    hard_gate=core['permission']['hard_gate']
    gate_clear=True if hard_gate=='NOT_TRIGGERED' else False if hard_gate=='TRIGGERED' else None
    coverage=event_coverage(request)
    uncontrollable_event_gap_clear=None
    left_safety=both(gate_clear,neg(down),credit_base,uncontrollable_event_gap_clear)
    target=target_for_symbol(request,row['symbol'],projection=target_projection)
    price_conditions={'valuation_reasonable_or_cheap':value_zone,'price_map_zone':None,
        'near_confirmed_low':None,'near_important_ma_or_support':None,'meaningful_drawdown':None}
    from v82_approved_context import build as build_approved_context
    approved_context,decision=build_approved_context(root,row,request,fundamental=fundamental,
        price_conditions=price_conditions,left_safety=left_safety,source_descriptor=approved_source_descriptor)
    right=tri(decision['market_predicates']['right'])
    fundamental=tri(approved_context['fundamentals_viable'])
    modes={k:deepcopy(decision[k]) for k in ('market_predicates','left_inputs','selected_mode','formal_stage','canonical_target_rate','call_trace')}
    modes.update(approved_v10_context=approved_context,approved_v10_analysis=decision,
        native_stage_result={'mode':decision['selected_mode'],'stage':decision['formal_stage'],
            'target_rate':decision['canonical_target_rate'],'reason_codes':decision['reason_codes']},
        stage_required_unknown_fields=decision['stage_audit']['required_unknown_fields'],
        stage_disallowed_fields=decision['stage_audit']['required_false_fields'],
        four_modes={'Base':{'selection_predicate':truth(both(neg(up),neg(right),neg(tri(modes['market_predicates']['left'])))),
                'technical_confirmation_required':False,'reference_stage':'STAGE_1'},
            'Left':{'market_predicate':modes['market_predicates']['left'],
                'reference_stages':['STAGE_'+str(i) for i in range(2,8)],'oversold_required_for_entry':False},
            'Right':{'market_predicate':decision['right_entry']['truth'],'reference_stage':'STAGE_8',
                'complete_entry':deepcopy(decision['right_entry'])},
            'Trend':{'market_predicate':truth(up),'reference_stage_maximum':'STAGE_9'}})
    base_entry=both((Decimal(target['amount'])>0) if target['value_state']=='KNOWN' else None,
        fundamental,legal,credit_base,gate_clear,neg(down))
    if down is True and (up is True or right is True or tri(modes['market_predicates']['left']) is True):
        modes['conflict']={'code':'INCOMPATIBLE_UP_RIGHT_LEFT_AND_DOWN','reconciliation_required':True,
            'native_selected_mode':modes['selected_mode']}
        modes['selected_mode']='UNKNOWN';modes['formal_stage']='UNKNOWN';modes['canonical_target_rate']=None
    modes['call_trace']+=viability['call_trace']
    modes['technical_only_predicates']={'right_confirmation':truth(right_technical),
        'runaway_up':truth(up),'runaway_down':truth(down)}
    modes['four_modes']['Base']['entry_eligibility']=truth(base_entry)
    modes['four_modes']['Base']['entry_reasons']=['APPROVED_LONG_TERM_ALLOCATION','FUNDAMENTALS','LEGAL_VALUATION','CREDIT_SAFETY','HARD_GATE','NOT_RUNAWAY_DOWN']
    orders=order_source(request,row.get('owner_order_confirmation'),broker_orders=row.get('broker_order_source'));missing=[]
    if modes['canonical_target_rate'] is None:missing.append('canonical_target_rate')
    if target['value_state']!='KNOWN':missing.append('approved_project_target_amount')
    if target['value_state']=='KNOWN' and target.get('currency')!=request['owner']['currency']:missing.append('verified_same_run_target_FX')
    if not row.get('position_valuation_allowed',False):missing.append('canonical_valuation_price_identity_and_validity')
    if orders['status']!='VERIFIED' and not orders.get('complete_for_open_order_exposure'):
        missing.append('active_orders_and_fill_reconciliation')
    gap={'status':'NOT_RUN_REQUIRED_INPUTS_UNRESOLVED','value':None,'missing_fields':missing,
        'function':'V82.calculate_position_gap','active_orders_defaulted_to_empty':False}
    if not missing:
        result=dep.calculate_position_gap(project_target_position_amount=target['amount'],
            target_rate=modes['canonical_target_rate'],confirmed_position_qty=row['holding']['quantity'],
            canonical_valuation_price=market['observed_close'],active_orders=native_orders(root,orders,row['symbol']))
        gap={'status':'COMPUTED','value':{k:str(v) if isinstance(v,Decimal) else v for k,v in asdict(result).items()},
            'function':'V82.calculate_position_gap','missing_fields':[]}
        modes['call_trace'].append('V82.calculate_position_gap')
    reference=[]
    for stage,rate in dep.STAGE_RATE_PCT.items():
        reference.append({'stage':stage,'cumulative_rate':str(rate/100),
            'approved_target_currency':target.get('currency'),
            'reference_target_amount':str(Decimal(target['amount'])*rate/100) if target['value_state']=='KNOWN' else None,
            'scope':'LADDER_REFERENCE_ONLY__NOT_SELECTED_STAGE_OR_ORDER_AMOUNT'})
    # Permission is copied from the original safety arbiter. Missing safety
    # closes new buys; lack of Right/Up confirmations is not its reason.
    permission={'value':bool(core['permission']['new_buy_order_permission']),
        'reason_codes':deepcopy(core['permission']['reason_codes']),
        'scope':'ORIGINAL_CORE_SAFETY_PERMISSION__FULL_EXECUTION_NOT_RUN',
        'right_or_runaway_false_is_not_buy_veto':True,'gap_used_in_permission':False,
        'broker_trade_authorization':request['trade_authorization']}
    groups=gap_matrix(row,target,coverage,orders)
    result={'schema_version':'Family.W8.FormalModeConclusion.v1','status':'INCOMPLETE_REQUIRED_FACTS',
        'binding':{'client_id':request['client_id'],'run_id':request['run_id'],
            'owner':deepcopy(request['owner']),'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
            'request_digest':digest(request),'core_input_digest':digest(row['core_observation']['actual_inputs'])},
        'classification':deepcopy(row['native_product_identity']),'scenario_class':deepcopy(row['scenario_class']),
        'valuation_validity':{'native_result':deepcopy(valuation),'source_metrics':deepcopy(row['valuation_observations'])},
        'fundamentals_viability_facts':{k:truth(v) for k,v in fundamental_facts.items()},
        'etf_viability_audit':viability if row['native_product_identity'].get('asset_type')!='INDIVIDUAL_STOCK' else None,
        'individual_thesis_audit':viability if row['native_product_identity'].get('asset_type')=='INDIVIDUAL_STOCK' else None,
        'left_safety_inputs':{'hard_gate_clear':truth(gate_clear),'not_runaway_down':truth(neg(down)),
            'credit_allows_normal_addition':truth(credit_base),
            'uncontrollable_event_gap_negations_absent':truth(uncontrollable_event_gap_clear)},
        **modes,'approved_project_target':target,'nine_stage_reference':reference,'order_source':orders,
        'deployment_gap':gap,'buy_permission':permission,'event_coverage':coverage,
        'gap_groups':groups,'trade_action':'NO_TRADE','deployment_status':'NOT_RUN'}
    result['conclusion_digest']=digest(result)
    return result


def etf_viability_audit(row,request):
    from etf_structure_source import evaluate_etf_structure
    return evaluate_etf_structure(row.get('issuer_facts'),request,row['symbol'],
        row['native_product_identity'].get('product_evidence'))


def gap_matrix(row,target,coverage,orders):
    def item(field,kind,source,impact,repair):
        return {'field':field,'gap_kind':kind,'existing_source':source,'affects':impact,'repair':repair}
    return {
        'valuation_and_pit':[
            item('valuation.FORWARD_PE.frequency/valid_until','SOURCE_METADATA_MISSING',deepcopy(row['valuation_observations']),
                ['legal valuation','Left price branch','Stage'], 'Bind provider-specific release/validity contract; do not invent a global age limit'),
            item('qV/qP required history','NATIVE_PRODUCERS_CONNECTED__SOURCE_QUALIFICATION_REQUIRED',
                deepcopy((row.get('formal_conclusion') or {}).get('approved_v10_analysis',{})),
                ['Left Stage3-7','Trend Stage8/9'], 'Native PV2/PV3 consume own-metric PIT history and corporate-action/calendar-qualified wealth; retain exact source reasons')],
        'fundamentals_and_events':[
            item('ETF viable structural facts','SOURCE_FACTS_MISSING','Issuer structure and dated fundamentals; no complete current structural assertions',
                ['Base entry','Left','Right','Stage','buy permission'], 'Bind active fund/mandate/NAV/redemption/termination and authorized exposure facts'),
            item('event coverage/checkpoint','PRODUCER_AND_SOURCE_COVERAGE_MISSING',coverage,
                ['safety','event-dependent T+1','buy permission'], 'Run required-domain event producer and bind cutoff/checkpoint; confirmed absence only after successful coverage')],
        'market_identity_calendar_fx':[
            item('left.price_map_zone/near_confirmed_low/near_important_ma_or_support/meaningful_drawdown',
                'QUALIFIED_PRICE_MAP_PRODUCER_NOT_CONNECTED',
                {'history_path':row['market']['source_path'],'rule':'V82 Work41-A; v1.0 PV2/PV3'},
                ['Left price OR branches'], 'Compute each authorized branch from qualified price/wealth/calendar inputs; do not invent a near-MA tolerance or relabel MA20_OK as Left entry'),
            item('price basis/session availability','SOURCE_ATTESTATION_MISSING','Exact symbol historical cache and issuer identity',
                ['canonical valuation price','weekly/monthly context','gap'], 'Bind provider field basis and actual market-session/availability receipts'),
            item('same-run reporting FX','SOURCE_FACT_MISSING','Target source currency differs from IB USD',
                ['target unit conversion','gap'], 'Read a same-run sourced FX observation; retain original TWD target and source precision')],
        'targets_orders_exposure':[
            item('approved target amount','MAPPED_FROM_EXISTING_SOURCE' if target['value_state']=='KNOWN' else 'NO_UNIQUE_APPROVED_TARGET',
                target,['target','gap'],'Explicit original amount is used; no current NAV substitution or absent-row zero'),
            item('active order details/reconciliation',
                'MAPPED_FROM_BROKER_WORKING_EXPOSURE' if orders.get('complete_for_open_order_exposure') else
                'MAPPED_FROM_OWNER_CONFIRMATION' if orders['status']=='VERIFIED' else 'SOURCE_DETAILS_MISSING',orders,
                [] if orders['status']=='VERIFIED' or orders.get('complete_for_open_order_exposure') else ['projected position','gap','execution safety'],
                'Working-order remaining quantities are included; provider replacement lifecycle caveats remain explicit' if orders.get('complete_for_open_order_exposure') else
                'No open orders confirmed for this owner/account; historical fills are not asserted' if orders['status']=='VERIFIED' else 'Read original order asset/side/remaining quantity/state/fills; tab count is not a complete ledger'),
            item('lookthrough weights/limits','PRODUCER_AND_REQUIRED_SOURCES_NOT_CONNECTED','Issuer partial holdings and accepted account positions',
                ['fund viability','exposure limits','safety'], 'Map complete dated issuer composition and existing authorized limits, preserving uncovered weights')]
    }
