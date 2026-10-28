"""Bind current advice to original Work3/Work4 and the native money planner.

This is the menu04 cash trial, not a broker/order adapter. A position-only
gap remains explicitly separate from the unknown order-adjusted net gap.
"""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from family_input import digest
from runtime_loader import load_c_module
from current_analysis_delivery import source_target_in_currency


def plain(value):
    if isinstance(value,Decimal):return str(value)
    if hasattr(value,'value'):return value.value
    if hasattr(value,'__dataclass_fields__'):return plain(asdict(value))
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def zero_cash_plan(row,stock,bound,owner):
    from livingwater_v82_runtime.deployment import calculate_position_gap,build_buy_execution_plan
    from livingwater_v82_runtime.core_rules import PermissionResult
    from livingwater_v82_runtime.enums import HardGateState
    symbol=row['symbol'];permission=row['core_observation']['result']['permission']
    target=stock['work3_handoff']['final_target']['payload']['instrument_targets'][symbol]['project_target_position']
    gap=calculate_position_gap(project_target_position_amount=target,
        target_rate=row['current_analysis']['current_judgment']['target_rate_reference'],
        confirmed_position_qty=row['holding']['quantity'],canonical_valuation_price=row['market']['observed_close'],active_orders=())
    return build_buy_execution_plan(gap=gap,
        permission=PermissionResult(HardGateState(permission['hard_gate']),permission['new_buy_order_permission'],tuple(permission['reason_codes'])),
        bound_equity_budget=bound,order_working_price=None,minimum_lot=None,
        normalized_order_price=None,execution_currency=owner['currency'])


def delivery(item):
    # Keep replayable private inputs once at the report root, not repeated in
    # every Work9/Mentor/display copy of the same component delivery.
    return {k:deepcopy(v) for k,v in item.items()
        if k not in ('work3_input','stock_request','work4_result')}


def build(producer,request,report,*,trial,investment,tactical):
    """Consume verified same-member sources; preserve every native rejection."""
    run=request['run_id'];owner=request['owner'];snapshot=request['client_snapshot']['payload']
    ref='DB:'+snapshot['source_sha256'];macro=request['macro_snapshot'];when=request['evaluation_at']
    w3=load_c_module(producer.root,3);w4=load_c_module(producer.root,4)
    native_owner={k:owner[k] for k in ('broker','account')};native_owner['funding_domain']='US_BROKER'
    contexts,cash_sources=producer.funding_contexts(snapshot,native_owner,trial,run,ref)
    from new_investment_scenario import apply_plan,wire_number
    contexts=apply_plan(contexts,investment)
    c7={'contract_name':'LivingWaterAI.C.Work7.FundingContext',
        'contract_version':'C-W7-FUND-v1.1.0-ABSENT' if any(x.get('account_presence')=='OWNER_CONFIRMED_ABSENT' for x in contexts) else 'C-W7-FUND-v1.0.0',
        'run_id':run,'base_currency':owner['currency'],'bank_cash_scope':'OUT_OF_SCOPE',
        'total_new_investment_amount':wire_number(investment['total_new_investment_amount']),
        'contexts':contexts,'source_reference_ids':[ref]}
    target=request['confirmed_target']['payload'];draft=target['draft']
    converted={r['instrument_id']:{'project_target_position':
        (source_target_in_currency(r['target_amount'],owner['currency'],producer.fx_observation) or {}).get('amount')}
        for r in draft['target_lines']}
    v70id='V70-SOURCE-INPUT-'+macro['digest'][:24]
    amounts=(tactical or {}).get('native_currency_amounts') or {}
    v70={'run_id':run,'source_namespace':'V70.RUNTIME_CONTEXT','upstream_v70_snapshot_id':v70id,
        'snapshot_as_of':macro['asOf'],'data_as_of':{'macro':macro['asOf']},'source_reference_ids':[ref],
        'payload':{'run_id':run,'stock_tactical_amount':amounts.get('stock'),
            'bond_tactical_amount':amounts.get('bond'),'v70_original_dry_powder_amount':amounts.get('dry_powder'),
            'value_state':'KNOWN' if amounts else 'UNKNOWN','data_quality':'FALLBACK_USED' if amounts else 'UNKNOWN',
            'issue_codes':[] if amounts else ['V70_MONETARY_SOURCE_NOT_PRODUCED']}}
    # No account total is promoted to available cash. The authorized overlay
    # preserves formal totals and explicitly supplies zero only where absent.
    available=Decimal(trial['decimal_values']['available'])
    budget='0' if available==0 else None
    legs={leg:{'amount':budget,'currency':owner['currency'],'cash_basis':'AVAILABLE',
        'owner':deepcopy(native_owner)} for leg in ('equity','bond')}
    envelope={'contract_name':w3.WORK2_ENVELOPE_NAME,'contract_version':w3.WORK2_ENVELOPE_VERSION,
        'baseline_id':w3.BASELINE_ID,'run_id':run,'owner':native_owner,'currency':owner['currency'],
        'settlement':{'cash_basis':'AVAILABLE','cash_state':deepcopy(trial['cash_state']),
            'source_status':'TRIAL_MISSING_CASH_ZERO'},
        'final_target':{'allocation_id':draft['allocation_id'],'authorization_reference':draft['allocation_id'],
            'confirmation_proof':{k:target['confirmation_evidence'][k] for k in ('confirmed_at','confirmed_by')},
            'payload':{'instrument_targets':converted}},
        'remaining_target_gap':{'v82':{'mode':'V82_EXISTING_RUNTIME_DERIVED','payload':{'source_owned':True}},
            'v75':{'mode':'V75_EXISTING_EXPLICIT_GAP','payload':{'remaining_target_gap_amount':None}}},
        'executable_budget':legs,'temporal':{'as_of':when,'data_as_of':{'W1':request['client_snapshot']['as_of'],'V70':macro['asOf']}},
        'versions':{'rule':request['expected_versions'],'data':{'W1':snapshot['source_sha256']},'schema':{'Family':'W5.request.v1'}},
        'lineage':{'source_reference_ids':[ref],'upstream_snapshot_ids':{'v70':v70id,'c7':None}},
        'reason_status':{'source_reason_codes':{'C7':['C7_FULL_FRAMEWORK_NOT_PRODUCED']},'source_status_codes':{'C7':'FUNDING_CONTEXT_ONLY'},'integration_diagnostics':[]},
        'sgov_boundary':{'v70_original_dry_powder':{'amount':({'amount':amounts['dry_powder'],'currency':owner['currency']} if amounts else None),'weight':None,'source_status':'KNOWN' if amounts else 'UNKNOWN'},
            'sgov_bond_bucket_amount':None,'sgov_dry_powder_bucket_amount':None,
            'v75_undeployed_to_sgov':None,'v82_undeployed_to_sgov':None,'roles_kept_separate':True,
            'v82_access_forbidden':True,'v82_raw_equity_budget_auto_route_forbidden':True,
            'final_aggregate_computed_in_work2':False,'physical_subledger_out_of_scope':True}}
    work3_input={'contract_name':w3.INPUT_CONTRACT_NAME,'contract_version':w3.INPUT_CONTRACT_VERSION,
        'baseline_id':w3.BASELINE_ID,'run_id':run,'work2_envelope':envelope,
        'client_state_context':{'run_id':run,'source_namespace':'C.CLIENT_STATE',
            'payload':{'client_id':request['client_id'],'portfolio_id':owner['account'],'full_client_snapshot':deepcopy(snapshot)},
            'data_as_of':request['client_snapshot']['as_of'],'source_reference_ids':[ref]},
        'v70_runtime_context':v70,'shared_decision_context':{'run_id':run,
            'source_namespace':'LOOP2.SHARED_DECISION_CONTEXT','context_id':'CTX-'+run,
            'context_version':'Family.W8.CurrentAdvice.v1','as_of':when,'data_as_of':{'macro':macro['asOf']},
            'payload':{'macro':deepcopy(macro['payload']),'cash_trial':deepcopy(trial)},
            'source_reference_ids':[ref],'versions':{'source_db':snapshot['source_sha256']}}}
    results={};trace=[]
    for row in report['analysis_result']['positions']:
        identity=row['native_product_identity'];advice=row['current_analysis'];symbol=row['symbol']
        out={'status':'INPUT_UNAVAILABLE','symbol':symbol,'run_id':run,'owner':deepcopy(owner),
            'source_db_sha256':snapshot['source_sha256'],'call_trace':[],
            'full_native_canonical_complete':False,'trade_action':'NO_TRADE','issues':[]}
        results[row['instrument_id']]=out
        missing=[]
        if not row.get('core_observation'):missing.append('native_product_identity.asset_type_and_core')
        if symbol not in converted or converted[symbol]['project_target_position'] is None:missing.append('approved_project_target_amount')
        if identity.get('asset_type') is None:missing.append('native_product_identity.asset_type')
        if identity.get('asset_grade')=='UNKNOWN':missing.append('native_product_identity.asset_grade')
        if budget is None:missing.append('funding.equity_executable_budget_assignment')
        if missing:
            out['issues']=[{'field_path':f,'code':'REQUIRED_SOURCE_UNAVAILABLE'} for f in missing];continue
        function='C8C9.Work3.build_context_handoff'
        try:
            out['call_trace'].append(function);out['work3_input']=deepcopy(work3_input)
            handoff=w3.build_context_handoff(work3_input)
            stock={'contract_name':w4.INPUT_CONTRACT_NAME,'contract_version':w4.INPUT_CONTRACT_VERSION,
                'baseline_id':w4.BASELINE_ID,'run_id':run,'work3_handoff':handoff,'c7_funding_context':c7,
                'asset_context':{'asset':{'asset_id':symbol,'asset_type':identity['asset_type'],
                    'asset_grade':identity['asset_grade'],'portfolio_role':'UNKNOWN'},
                    'client_project_version':str(draft.get('original_allocation_version',request['expected_versions']['target'])),
                    'project_target_pointer':'/instrument_targets/'+symbol+'/project_target_position',
                    'confirmed_position_snapshot':{'quantity':row['holding']['quantity'],'source':'BROKER'}}}
            function='C8C9.Work4.build_v82_runtime_input';out['call_trace'].append(function)
            out['stock_request']=stock;out['work4_result']=w4.build_v82_runtime_input(stock)
            from formal_mode_analysis import native
            native(producer.root)
            from livingwater_v82_runtime.validation import validate_and_bind_funding
            function='V82.validate_and_bind_funding';out['call_trace'].append(function)
            bound=validate_and_bind_funding(out['work4_result']['v82_runtime_input'])
            out['bound_equity_budget']=plain(bound.bound_equity_budget)
            out['status']='FUNDING_BOUND'
            component=advice['recommendation'].get('confirmed_holdings_component')
            if component is None:
                out['issues'].append({'field_path':'native_mode_and_stage_target_rate','code':'REQUIRED_SOURCE_UNAVAILABLE'});continue
            # Only the explicit zero-available-cash trial reaches this path.
            # A positive shared budget requires original allocation/reconciliation.
            function='V82.build_buy_execution_plan';out['call_trace']+=['V82.calculate_position_gap:confirmed_holdings_component_only',function]
            plan=zero_cash_plan(row,stock,bound.bound_equity_budget,owner)
            out['native_plan']=plain(plan);out['status']='CASH_TRIAL_ADVICE_COMPUTED'
            out['amount_scope']='ZERO_AVAILABLE_CASH_TRIAL__NOT_EXISTING_ASSET_REDEPLOYMENT_OR_ORDER_ADJUSTED_NET'
            out['active_orders_assumed_empty']=False
            out['position_gap_scope']='CONFIRMED_HOLDINGS_COMPONENT_ONLY'
            out['order_adjusted_net_status']='PENDING_OWNER_ORDER_CONFIRMATION'
        except ValueError as error:
            from native_asset_source import native_error_path
            out['status']='NATIVE_CONTRACT_REJECTED'
            out['issues'].append({'function':function,'field_path':native_error_path(error),
                'code':getattr(error,'code',type(error).__name__),'raw_error':str(error)})
        finally:trace.extend({'instrument_id':row['instrument_id'],'function':f} for f in out['call_trace'])
    return {'schema_version':'Family.W8.NativeFundingAdvice.v1','client_id':request['client_id'],
        'run_id':run,'source_db_sha256':snapshot['source_sha256'],'items':results,'call_trace':trace,
        'funding_source_digest':digest(c7),'new_external_money':investment['total_new_investment_amount'],
        'full_native_canonical_complete':False,'trade_action':'NO_TRADE'}


def validate(root,report,request):
    """Replay actual native contracts before accepting a cash-trial amount."""
    source=report.get('native_funding_advice')
    if source is None:return
    for key,expected in (('client_id',request['client_id']),('run_id',request['run_id']),
            ('source_db_sha256',request['client_snapshot']['payload']['source_sha256'])):
        if source.get(key)!=expected:raise PermissionError('NATIVE_FUNDING_ADVICE_BINDING_MISMATCH')
    rows={r['instrument_id']:r for r in report['analysis_result']['positions']}
    if set(source['items'])!=set(rows):raise PermissionError('NATIVE_FUNDING_ADVICE_COVERAGE_MISMATCH')
    for key,item in source['items'].items():
        row=rows[key]
        if (item.get('owner')!=request['owner'] or item.get('run_id')!=request['run_id']
            or item.get('symbol')!=row['symbol'] or item.get('source_db_sha256')!=source['source_db_sha256']):
            raise PermissionError('NATIVE_FUNDING_ADVICE_BINDING_MISMATCH')
        if delivery(item)!=row['current_analysis'].get('native_funding_advice'):
            raise PermissionError('NATIVE_FUNDING_ADVICE_DELIVERY_MISMATCH')
        if item['status']!='CASH_TRIAL_ADVICE_COMPUTED':continue
        stock=item['stock_request'];input3=item['work3_input']
        if (stock['run_id']!=request['run_id'] or stock['asset_context']['asset']['asset_id']!=row['symbol']
            or stock['asset_context']['confirmed_position_snapshot']['quantity']!=row['holding']['quantity']
            or input3['client_state_context']['payload']['full_client_snapshot']!=request['client_snapshot']['payload']):
            raise PermissionError('NATIVE_FUNDING_ADVICE_SOURCE_MISMATCH')
        if stock['work3_handoff']!=load_c_module(root,3).build_context_handoff(input3):
            raise PermissionError('NATIVE_FUNDING_ADVICE_WORK3_MISMATCH')
        built=load_c_module(root,4).build_v82_runtime_input(stock)
        if built!=item['work4_result']:raise PermissionError('NATIVE_FUNDING_ADVICE_WORK4_MISMATCH')
        from livingwater_v82_runtime.validation import validate_and_bind_funding
        bound=validate_and_bind_funding(built['v82_runtime_input']).bound_equity_budget
        if plain(bound)!=item['bound_equity_budget'] or bound.amount!=0:
            raise PermissionError('NATIVE_FUNDING_ADVICE_ZERO_TRIAL_BINDING_MISMATCH')
        # The native zero-budget result cannot be re-signed into a positive
        # recommendation, an executable order or an order-adjusted net gap.
        plan=item['native_plan']
        if (plan!=plain(zero_cash_plan(row,stock,bound,request['owner']))
            or plan['execution_amount']!='0' or plan['execution_quantity']!='0'
            or plan['order_plan']['should_place_order'] is not False
            or item['full_native_canonical_complete'] is not False
            or item['active_orders_assumed_empty'] is not False):
            raise PermissionError('NATIVE_FUNDING_ADVICE_PLAN_MISMATCH')
