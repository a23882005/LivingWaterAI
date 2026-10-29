"""Produce native evidence from the verified same-run holdings analysis.

Source production and original validation are recorded separately. No C7
framework or Work6 confirmation is fabricated to make an assembly pass.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from family_boundary import BoundaryError

CALCULATED={'latest_price','market_data_as_of','left_buy_point_state','primary_special_classification',
    'fundamental_state','valuation_state','right_confirmation_state','runaway_state',
    'project_target_position','confirmed_position','actual_completion_rate','normal_deployment_mode',
    'execution_action','canonical_deployment_target_rate','execution_amount','execution_quantity',
    'execution_price','projected_post_fill_completion_rate','order_submission_plan'}


def market_reference(symbol,exchange,currency,source_digest,reference):
    return {'asset_id':symbol,'exchange':exchange,'currency':currency,
        'source_digest':source_digest,'source_reference':reference,
        'scope':'ANALYSIS_MARKET_REFERENCE__NOT_HELD_OR_EXECUTION_VENUE'}


def _issue(out,section,error):
    out['source_validation_issues'].append({'source_section':section,
        **deepcopy(getattr(error,'issue',{'code':getattr(error,'code',type(error).__name__),
            'field_path':section,'message':str(error)}))})


def stock_sources(root,request,analysis,out):
    from formal_mode_analysis import native,native_orders
    from native_funding_advice import plain
    from tactical_budget import tactical_cap
    from family_technical_bridge import bind_technical_source,apply_technical_source
    from stock_engine import run_stock_engine
    native(root)
    from livingwater_v82_runtime.canonical_output import CANONICAL_FIELD_NAMES
    bundle=out['native_bundle'];stock=bundle['stock_request']
    symbol=stock['asset_context']['asset']['asset_id']
    technical=out['trusted_context'].get('technical_source')
    if technical is None:return
    row=next(r for r in analysis['analysis_result']['positions'] if r['symbol']==symbol)
    core=row.get('core_observation');equity=analysis['qualified_equity_inputs']['items'][symbol]
    if not core:return
    orders=row['current_analysis']['recommendation'].get('order_source') or {}
    if not (orders.get('status')=='VERIFIED' or orders.get('complete_for_open_order_exposure')):
        return
    # The observed zero tactical cap already bounds this no-new-money run.
    # A positive-cap deployment still needs its additional source-owned caps.
    zero_cap=tactical_cap(stock['work3_handoff'],'equity')['amount']==0
    meta=technical['metadata']
    contract={'producer':'Family.W8.QualifiedStockEvidence','version':'1.0',
        'exchange':meta['exchange'],'currency':meta['currency'],'timeframe':meta['timeframe'],
        'adjustment':meta['provider_price_basis'],'parameters':{'history_digest':meta['history_digest'],
            'core_input_digest':digest(core['actual_inputs']),
            'owner_approved_rule_sha256':technical['owner_approved_rule_source']['sha256']}}
    facts={**deepcopy(contract),'asset_id':symbol,'run_id':request['run_id'],
        'source_reference':'VERIFIED-ANALYSIS:'+analysis['report_digest']+';PRICE:'+equity['digest'],
        'market_identity_digest':equity['digest'],'evaluated_at':request['evaluation_at'],
        'as_of':equity['session_close_at'],'available_at':request['evaluation_at'],
        'availability_basis':'COMPOSITE_BOUND_SNAPSHOT__NOT_ORIGINAL_PUBLICATION_TIME',
        'price_field':meta['price_field'],'sample_state':equity['technical_sample_state'],
        'swings':[],'core':deepcopy(core['actual_inputs']),
        'left_buy_point':row.get('formal_conclusion',{}).get('market_predicates',{}).get('left','UNKNOWN'),
        'left_stage':None,'trend_stage':None,'risk_reduction_predicate':'UNKNOWN',
        'technical_reduction_predicate':'UNKNOWN','active_orders':plain(native_orders(root,orders,symbol)),
        'order_source':deepcopy(orders),'valuation_price':equity['rows'][-1]['Close'],
        'order_working_price':None,'normalized_order_price':None,'minimum_lot':None,
        'required_known_caps':[] if zero_cap else [None],'order_intent_id':None,
        'source_gaps':['formal_stage_reference','risk_reduction_predicate','technical_reduction_predicate',
            'qualified_order_price','minimum_lot']+([] if zero_cap else ['additional_position_caps'])}
    fields={k:'UNKNOWN' for k in CANONICAL_FIELD_NAMES if k not in CALCULATED}
    fields.update(asset_behavior_classification=row['scenario_class']['formal_v82_class'],
        primary_framework=row.get('primary_framework') or 'UNKNOWN')
    bundle.update(stock_evidence=facts,producer_contract=contract,stock_source_fields=fields)
    out['native_binding']['stock_instrument']['market_reference']=market_reference(
        symbol,meta['exchange'],meta['currency'],equity['digest'],meta['source_reference'])
    probe=deepcopy(request);probe['native_bundle']=deepcopy(bundle);probe['technical_source_digest']=digest(technical)
    bound=bind_technical_source(root,probe,{**out['trusted_context'],'native_binding':out['native_binding']})
    effective=apply_technical_source(bundle,bound)
    result=run_stock_engine(root,effective['stock_request'],effective['stock_evidence'],effective['producer_contract'])
    if plain(result['core_state'])!=core['result']:raise PermissionError('DEPLOYMENT_CORE_SOURCE_REPLAY_MISMATCH')
    out['component_results']['stock']=plain(result)
    out['context_bindings']['stock_evidence']={'status':'ORIGINAL_STOCK_COMPONENT_REPLAY_PASSED',
        'source_digest':digest(facts),'core_replayed':True,'full_native_canonical_complete':False}
    out['context_call_trace']+=['W8.produce_stock_evidence_and_contract',*result['call_trace']]


def bond_sources(request,analysis,prepared,out):
    from v75_native_attempt import normalized_evidence
    source=analysis['native_bond_source'];evidence,excluded=normalized_evidence(request,source)
    if not evidence:return
    pool=analysis.get('v75_macro_inputs') or {};mappings={}
    for symbol,facts in evidence.items():
        market=pool.get('qualified_bond_markets',{}).get(symbol)
        if not market or not market['eligible']:continue
        facts['market_identity_digest']=market['digest']
        positions=[p for p in prepared.payload['positions'] if p['source_instrument'].get('ticker')==symbol]
        registered=[r for r in request['client_snapshot']['payload']['tables']['portfolio_instrument'] if r.get('ticker')==symbol]
        target=source['targets'].get(symbol,{}).get('source_line')
        if positions:key=positions[0]['instrument_key']
        elif len(registered)==1:key=registered[0]['instrument_key']
        elif target:key='APPROVED_TARGET:'+target['instrument_id']
        else:continue
        mapping={'asset_id':symbol,'instrument_key':key,'account_key':request['owner']['account'],
            'native_owner':deepcopy(out['native_binding']['native_owner']),
            'exchange':market['broker_exchange'],'source_reference':'VERIFIED-BOND-MARKET:'+market['digest'],
            'market_reference':market_reference(symbol,market['broker_exchange'],market['currency'],
                market['digest'],market['source_reference'])}
        if not positions and not registered:mapping['approved_target_source']=deepcopy(target)
        mappings[symbol]=mapping
    out['native_bundle']['bond_evidence']=evidence
    if set(mappings)==set(evidence):out['native_binding']['bond_instruments']=mappings
    out['component_results']['bond']={'status':source['native_runtime_attempt']['status'],
        'unqualified_predicates_not_substituted':excluded,'normalized_evidence_digest':digest(evidence),
        'canonical_returned':source['native_runtime_attempt'].get('canonical') is not None,
        'formal_output_eligible':False}
    out['context_call_trace'].append('W8.produce_bond_evidence_and_physical_logical_mapping')


def valuation_source(request,analysis,out):
    bundle=out['native_bundle'];mappings=out['native_binding'];prices={}
    if not all(k in bundle for k in ('stock_evidence','bond_evidence','physical_sgov')):return
    if not mappings.get('bond_instruments'):return
    facts=bundle['stock_evidence'];symbol=facts['asset_id'];at=request['evaluation_at']
    prices[symbol]={'state':'KNOWN','value':str(facts['valuation_price']),'currency':facts['currency'],
        'unit':'CURRENCY_PER_SHARE','instrument_key':mappings['stock_instrument']['instrument_key'],
        'as_of':at,'price_observation_as_of':facts['as_of'],
        'price_source_digest':facts['market_identity_digest'],'source_reference':facts['source_reference'],
        'valuation_basis':'CURRENT_QUANTITY_AT_KNOWN_REFERENCE_PRICE'}
    for asset,mapping in mappings['bond_instruments'].items():
        if asset=='SGOV':
            physical=analysis['sgov_role_source']['physical'];price=physical['price'];when=physical['valuation_as_of']
            observation=physical['price_observation_date'];ref=physical['source_reference']
        else:
            market=analysis['v75_macro_inputs']['qualified_bond_markets'][asset]
            price=market['close'];when=at;observation=market['session_close_at'];ref=market['source_reference']
        prices[asset]={'state':'KNOWN','value':str(price),'currency':request['owner']['currency'],
            'unit':'CURRENCY_PER_SHARE','instrument_key':mapping['instrument_key'],'as_of':when,
            'price_observation_as_of':observation,'source_reference':ref,
            'valuation_basis':'CURRENT_QUANTITY_AT_KNOWN_REFERENCE_PRICE',
            'price_source_digest':bundle['bond_evidence'][asset]['market_identity_digest']}
    out['trusted_context']['valuation_source']={'schema_version':'Family.W8.PositionValuationSource.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],'family_owner':deepcopy(request['owner']),
        'prices':prices,'fx':{},'source_reference':'VERIFIED-ANALYSIS:'+analysis['report_digest'],
        'portfolio_nav':{'state':'UNKNOWN','value':None,'currency':request['owner']['currency'],
            'reason':'FULL_C7_CURRENT_ALLOCATION_DENOMINATOR_NOT_PRODUCED; APPROVED_CAPITAL_IS_NOT_CURRENT_NAV'},
        'scope':'SELECTED_ACCOUNT_POSITION_VALUES__NOT_GLOBAL_NAV_OR_EARNINGS_PIT'}
    out['context_call_trace'].append('W8.produce_position_valuation_sources')


def extend(root,request,analysis,prepared,sources,*,trusted_context=None):
    from stock_source_bridge import bind_stock_source
    from bond_source_bridge import bind_bond_sources
    from position_source_bridge import bind_position_values
    out=deepcopy(sources);out['component_results']={}
    for section,produce in (
        ('native_bundle.stock_evidence',lambda:stock_sources(root,request,analysis,out)),
        ('native_bundle.bond_evidence',lambda:bond_sources(request,analysis,prepared,out)),
        ('trusted_context.valuation_source',lambda:valuation_source(request,analysis,out))):
        try:produce()
        except (BoundaryError,ValueError,KeyError,TypeError) as error:_issue(out,section,error)
    probe=deepcopy(request);probe['native_bundle']=deepcopy(out['native_bundle'])
    checked=deepcopy(prepared);binding=out['native_binding']
    context={**deepcopy(trusted_context or {}),**out['trusted_context'],'native_binding':binding}
    for section,bind in (
        ('stock_instrument',lambda:bind_stock_source(probe,checked,binding)),
        ('bond_instruments',lambda:bind_bond_sources(probe,checked,binding))):
        if (section=='stock_instrument' and 'stock_evidence' not in probe['native_bundle']) or (
            section=='bond_instruments' and not binding.get(section)):continue
        try:bound=bind()
        except (BoundaryError,ValueError,KeyError,TypeError) as error:_issue(out,'native_binding.'+section,error)
        else:
            if section=='stock_instrument':checked.payload['stock_source']=bound
            else:checked.payload['family_sources']={'bond':bound}
            out['context_bindings'][section]={'status':'ORIGINAL_SOURCE_BINDING_PASSED',
                'source_digest':digest(bound),'physical_and_logical_quantities_kept_separate':True}
    if ('stock_source' in checked.payload and 'family_sources' in checked.payload
        and 'valuation_source' in context):
        probe['valuation_digest']=digest(context['valuation_source'])
        try:valued=bind_position_values(probe,checked,context)
        except (BoundaryError,ValueError,KeyError,TypeError) as error:_issue(out,'trusted_context.valuation_source',error)
        else:
            out['component_results']['position_valuation']=valued
            out['context_bindings']['valuation_source']={'status':'ORIGINAL_POSITION_VALUATION_PASSED',
                'source_digest':digest(context['valuation_source']),'result_digest':digest(valued),
                'portfolio_nav_bound':False}
            out['context_call_trace'].append('W5.bind_position_values')
    return out
