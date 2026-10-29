"""Same-run native engine pipeline, called after Family input authorization.

This internal entry point accepts already-bound native inputs. It does not
replace prepare_input or authenticate external requests.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from runtime_loader import load_c_module
from stock_engine import run_stock_engine,assemble_stock_output
from bond_engine import run_bond_engine
from funding_guard import check_aggregate
from sgov_bridge import reconcile_sgov
from stock_source_bridge import apply_stock_policy
from funding_bridge import reconcile_funding
from permission_bridge import protect_existing


class PipelineError(ValueError):
    pass


def run_native_pipeline(repo_path, bundle, stock_source=None, family_sources=None, *, c7_source=None):
    data=apply_stock_policy(bundle,stock_source)
    stock_req,bond_req=data['stock_request'],data['bond_request']
    w3=stock_req['work3_handoff']
    for name in ('work3_handoff','c7_funding_context'):
        if digest(stock_req[name])!=digest(bond_req[name]):
            raise PipelineError('SHARED_SOURCE_MISMATCH:'+name)
    run_id=w3['run_id'];client=w3['client_state_context']['payload']['client_id']
    framework=data['asset_framework']
    c7_computation=None if family_sources is None else family_sources.get('c7')
    if c7_source is not None:
        from c7_engine import run_c7_engine
        computed=run_c7_engine(repo_path,c7_source)
        if c7_computation is not None and computed!=c7_computation:
            raise PipelineError('C7_SOURCE_MISMATCH')
        c7_computation=computed
    if c7_computation is not None:
        if digest(framework)!=digest(c7_computation['result']):
            raise PipelineError('C7_COMPUTED_FRAMEWORK_MISMATCH')
        framework=deepcopy(c7_computation['result'])
    if framework['identity']['client_id']!=client or framework['identity']['run_id']!=run_id:
        raise PipelineError('FRAMEWORK_CLIENT_RUN_MISMATCH')
    if framework['work6_final_target_reference']['allocation_id']!=w3['final_target']['allocation_id']:
        raise PipelineError('FRAMEWORK_TARGET_MISMATCH')
    # Reconcile the C framework's funding snapshot with the exact dispatched C7.
    funding_snapshot=framework['funding_context_snapshot'];c7=stock_req['c7_funding_context']
    for name in ('base_currency','total_new_investment_amount','contexts','bank_cash_scope'):
        if digest(funding_snapshot[name])!=digest(c7[name]):
            raise PipelineError('FRAMEWORK_FUNDING_MISMATCH:'+name)
    stock=run_stock_engine(repo_path,stock_req,data['stock_evidence'],data['producer_contract'])
    if stock.get('execution') is None:
        return {'status':'DATA_UNAVAILABLE','unified_result':None,'trade_action':'NO_TRADE',
                'issue_codes':['NATIVE_TECHNICAL_DEPLOYMENT_UNRESOLVED'],'call_trace':stock['call_trace']}
    stock_output=assemble_stock_output(repo_path,stock,data['stock_source_fields'],c7_computation)
    target_projection=None
    if c7_computation is not None:
        from target_units import project_target_units
        target_projection=project_target_units(stock,c7_computation)
    bond=run_bond_engine(repo_path,bond_req,data['bond_evidence'],
                         None if family_sources is None else family_sources['bond'])
    if (bond.get('canonical') is None or not bond.get('runtime_ready',{}).get('runtime_ready')
            or not bond['runtime_ready']['output'].get('formal_output_eligible')):
        return {'status':bond['status'],'stock_result':stock_output,'bond_result':bond,
                'unified_result':None,'trade_action':'NO_TRADE','input_digest':digest(data)}
    trace=[*data.get('technical_intake',{}).get('call_trace',[]),*stock['call_trace'],*bond['call_trace']]
    if c7_computation is not None:
        trace=c7_computation['call_trace']+trace
    def request(module,**payload):
        return {'contract_name':module.INPUT_CONTRACT_NAME,'contract_version':module.INPUT_CONTRACT_VERSION,
                'baseline_id':module.BASELINE_ID,'run_id':run_id,**payload}
    work6=load_c_module(repo_path,6)
    funding_request=request(work6,work3_handoff=w3,c7_funding_context=c7,
        work4_adapter_result=stock['built_input'],work5_adapter_result=bond['built_input'])
    owner=({'client_id':client,**w3['owner'],'currency':w3['currency']} if family_sources is None
           else family_sources['funding']['family_owner'])
    claims=[{'claim_id':'V82:'+stock_output['asset_id'],'owner':owner,'run_id':run_id,
             'asset_class':'EQUITY','amount':stock['execution'].execution_amount}]
    for d in bond['runtime_ready']['output']['per_asset_decisions']:
        if d['deploy_amount'] is None:raise PipelineError('BOND_DEPLOYMENT_UNKNOWN')
        claims.append({'claim_id':'V75:'+d['asset_id'],'owner':owner,'run_id':run_id,
                       'asset_class':'BOND','amount':d['deploy_amount']['amount']})
    funding_reconciliation=None
    if family_sources is not None:
        f=family_sources['funding']
        funding_reconciliation=reconcile_funding(repo_path,family_owner=owner,native_request=funding_request,
            owner_binding=f['owner_binding'],expected_binding_digest=f['expected_binding_digest'],claims=claims)
        isolated=funding_reconciliation['native_work6'];aggregate=funding_reconciliation['aggregate']
        trace.append('W5.reconcile_funding:Family_owner_actual_native_claims')
    else:
        isolated=work6.validate_funding_account_isolation(funding_request)
        cash=isolated['cash_eligibility']
        aggregate=check_aggregate(owner=owner,run_id=run_id,claims=claims,available=cash['available'],
            equity_budget=cash['equity_executable_budget'],bond_budget=cash['bond_executable_budget'])
    trace.append('C8C9.Work6.validate_funding_account_isolation')
    trace.append('W5.check_aggregate:actual_native_claims')
    work7=load_c_module(repo_path,7)
    physical=reconcile_sgov(repo_path,request(work7,work3_handoff=w3,
        work4_v82_adapter_result=stock['built_input'],work5_v75_integration_result=bond['canonical'],
        work6_funding_isolation_result=isolated),data['physical_sgov'])
    trace.extend(['C8C9.Work7.validate_sgov_runtime_roles','W5.reconcile_sgov'])
    work8=load_c_module(repo_path,8)
    protected_request=request(work8,c_work7_asset_framework_result=framework,work4_v82_integration_result=stock_output)
    family_protection=None
    if family_sources is None:
        protected=work8.protect_client_action(protected_request)
    else:
        p=family_sources['protection']
        family_protection=protect_existing(repo_path,native_request=protected_request,
            projection=p['projection'],instrument_binding=p['instrument_binding'])
        protected=family_protection['native_work8']
    trace.append('C8C9.Work8.protect_client_action')
    work9=load_c_module(repo_path,9)
    unified_request=request(work9,work4_v82_integration_result=stock_output,
        work5_v75_integration_result=bond['canonical'],work6_funding_account_isolation_result=isolated,
        work7_sgov_runtime_role_result=physical['native_work7'],work8_protected_holding_result=protected)
    unified=work9.build_unified_deployment(unified_request)
    trace.append('C8C9.Work9.build_unified_deployment')
    return {'status':'NATIVE_PIPELINE_COMPLETE','input_digest':digest(bundle),'effective_input_digest':digest(data),
        **({'predicate_amendments':deepcopy(bond['predicate_amendments'])} if bond.get('predicate_amendments') else {}),
        'stock_source':deepcopy(stock_source),'family_sources':deepcopy(family_sources),
        'target_unit_projection':target_projection,
        'funding_reconciliation':funding_reconciliation,'family_protection':family_protection,'client_id':client,'run_id':run_id,
        'stock_result':stock_output,'bond_result':bond['canonical'],'funding_aggregate':aggregate,
        'sgov_reconciliation':physical,'protected_holding':protected,'unified_result':unified,
        'mentor_return':deepcopy(unified['mentor_return']),'work9_request':unified_request,'call_trace':trace,
        'production':'HOLD','trade_action':'NO_TRADE'}
