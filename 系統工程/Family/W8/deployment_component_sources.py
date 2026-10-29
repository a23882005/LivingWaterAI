"""Reuse verified analysis components at the full native assembly boundary.

Missing deployment evidence stays absent. The original assembler reports all
remaining sections; this module cannot make an incomplete bundle executable.
"""
from copy import deepcopy
from family_input import digest
from runtime_loader import load_c_module


def collect(root,request,analysis,symbol):
    funding=analysis.get('native_funding_advice') or {};bond=analysis.get('native_bond_source') or {}
    rows=[r for r in analysis['analysis_result']['positions'] if r['symbol']==symbol]
    if len(rows)!=1:return None
    row=rows[0];item=funding.get('items',{}).get(row['instrument_id'],{})
    stock=item.get('stock_request');bond_request=bond.get('adapter_request')
    if stock is None or bond_request is None or item.get('work4_result') is None:return None
    identity={'client_id':request['client_id'],'run_id':request['run_id'],'owner':request['owner'],
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256']}
    for key,value in identity.items():
        if analysis.get(key)!=value:raise PermissionError('DEPLOYMENT_ANALYSIS_SOURCE_MISMATCH:'+key)
        if key!='owner' and funding.get(key)!=value:raise PermissionError('DEPLOYMENT_STOCK_SOURCE_MISMATCH:'+key)
        if bond.get(key)!=value:raise PermissionError('DEPLOYMENT_BOND_SOURCE_MISMATCH:'+key)
    if item.get('owner')!=request['owner'] or item.get('symbol')!=symbol:
        raise PermissionError('DEPLOYMENT_FOCUS_SOURCE_MISMATCH')
    for key in ('work3_handoff','c7_funding_context'):
        if stock[key]!=bond_request[key]:raise PermissionError('DEPLOYMENT_SHARED_SOURCE_MISMATCH:'+key)
    handoff=stock['work3_handoff']
    if (stock['run_id']!=request['run_id'] or handoff['run_id']!=request['run_id']
        or handoff['client_state_context']['payload']['client_id']!=request['client_id']
        or any(handoff['owner'][k]!=request['owner'][k] for k in ('account','broker'))
        or handoff['currency']!=request['owner']['currency']):
        raise PermissionError('DEPLOYMENT_NATIVE_SOURCE_IDENTITY_MISMATCH')
    if stock['work3_handoff']!=load_c_module(root,3).build_context_handoff(item['work3_input']):
        raise PermissionError('DEPLOYMENT_WORK3_REPLAY_MISMATCH')
    if item['work4_result']!=load_c_module(root,4).build_v82_runtime_input(stock):
        raise PermissionError('DEPLOYMENT_WORK4_REPLAY_MISMATCH')
    if bond.get('adapter_result')!=load_c_module(root,5).build_v75_runtime_input(bond_request):
        raise PermissionError('DEPLOYMENT_WORK5_REPLAY_MISMATCH')
    bundle={'stock_request':deepcopy(stock),'bond_request':deepcopy(bond_request)}
    roles=analysis.get('sgov_role_source')
    if roles and roles.get('status')=='SOURCE_DERIVED_ACCOUNTING' and roles.get('physical'):
        physical=roles['physical']
        boundary=handoff['funding_context']['sgov_boundary']
        if (any(roles.get(k)!=v for k,v in identity.items())
            or any(boundary[k]!=v for k,v in roles['roles'].items())
            or physical['valuation']['currency']!=request['owner']['currency']):
            raise PermissionError('DEPLOYMENT_SGOV_ROLE_SOURCE_MISMATCH')
        bundle['physical_sgov']={'client_id':request['client_id'],'run_id':request['run_id'],
            'owner':deepcopy(stock['work3_handoff']['owner']),'currency':request['owner']['currency'],
            'physical_market_value':physical['valuation']['amount'],'as_of':physical['valuation_as_of'],
            'role_valuation_as_of':physical['valuation_as_of'],'source_reference':physical['source_reference']}
    return {'source_reference':'VERIFIED-HOLDINGS-COMPONENTS:'+analysis['report_digest'],
        'native_bundle':bundle,'trusted_context':{},'native_binding':{
        'schema_version':'Family.W5.NativeBinding.v1','data_provenance':'SOURCE_BACKED',
        'native_owner':deepcopy(stock['work3_handoff']['owner']),
        'source_reference':'VERIFIED-HOLDINGS-COMPONENTS:'+analysis['report_digest']},
        'component_binding':{'analysis_report_digest':analysis['report_digest'],
            'shared_work3_digest':digest(stock['work3_handoff']),
            'work4_result_digest':digest(item['work4_result']),
            'work5_result_digest':digest(bond['adapter_result'])}}


def build(producer,request,context,analysis,prepared,holdings,trial,observations,investment,asset_class,held):
    sources=collect(producer.root,request,analysis,producer.symbol)
    if sources is None:return None
    # The same source replay used by the holdings entry remains mandatory.
    # Switching entry modes never bypasses its owner/cash/target/market guards.
    from holdings_analysis import HoldingsAnalysisRunner
    HoldingsAnalysisRunner(context=context,report=analysis).analyze(request)
    from deployment_context_sources import extend
    sources=extend(producer.root,request,analysis,prepared,sources)
    from on_demand_analysis import assemble_native_input,NativeSourceAssemblyError
    try:assemble_native_input(request,context,sources)
    except NativeSourceAssemblyError as error:missing=list(error.missing)
    else:raise PermissionError('PARTIAL_COMPONENT_SOURCES_MUST_NOT_DISPATCH')
    row=next(r for r in analysis['analysis_result']['positions'] if r['symbol']==producer.symbol)
    item=analysis['native_funding_advice']['items'][row['instrument_id']];bond=analysis['native_bond_source']
    owner=deepcopy(item['stock_request']['work3_handoff']['owner'])
    _,cash_sources=producer.funding_contexts(request['client_snapshot']['payload'],owner,trial,
        request['run_id'],'DB:'+analysis['source_db_sha256'])
    outputs={'work3':deepcopy(item['stock_request']['work3_handoff']),
        'work4':deepcopy(item['work4_result']),'work5':deepcopy(bond['adapter_result']),
        'v75_runtime_attempt':deepcopy(bond.get('native_runtime_attempt'))}
    if row.get('core_observation'):outputs['v82_core_observation']=deepcopy(row['core_observation'])
    failure={'function':'W8.assemble_native_input','code':'NATIVE_SOURCE_INPUTS_REQUIRED',
        'field_path':'native_sources','missing_fields':missing,
        'raw_error':'Remaining native source sections: '+','.join(missing)}
    report={'schema_version':'Family.W8.NativeSourceProduction.v1','status':'SOURCE_STAGE_INCOMPLETE',
        'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
        'source_db_sha256':analysis['source_db_sha256'],'request_digest':digest(request),
        'focus_symbol':producer.symbol,'classification':deepcopy(asset_class),
        'prepared_account_positions':deepcopy(prepared.payload['positions']),
        'full_household_sources':deepcopy(holdings),'cash_trial':deepcopy(trial),
        'cash_by_domain':cash_sources,'market_observations':deepcopy(observations),
        'holdings_analysis':deepcopy(analysis),'new_investment_scenario':deepcopy(investment),
        'native_inputs':{'work3':deepcopy(item['work3_input']),**deepcopy(sources['native_bundle'])},
        'native_outputs':outputs,'native_sources':sources,
        'context_source_bindings':deepcopy(sources['context_bindings']),
        'source_validation_issues':deepcopy(sources['source_validation_issues']),'first_failure':failure,
        'analysis_source_call_trace':deepcopy(analysis['call_trace']),
        'call_trace_scope':'COMPONENT_SOURCE_REPLAY_AND_ASSEMBLY_ONLY',
        'call_trace':['W8.reuse_verified_analysis_components','W8.HoldingsAnalysisRunner.analyze:source_replay',
            'C8C9.Work3.build_context_handoff:component_replay','C8C9.Work4.build_v82_runtime_input:component_replay',
            'C8C9.Work5.build_v75_runtime_input:component_replay',*sources['context_call_trace'],
            'W8.assemble_native_input:report_all_missing_sources'],
        'mode':'CASH_ZERO_SIMULATION','analysis_mode':'CASH_ZERO_SIMULATION',
        'source_data_provenance':'SOURCE_BACKED','effective_input_provenance':'CASH_ZERO_SIMULATION',
        'complete_native_bundle':False,'full_native_mentor_reached':False,'mentor':None,
        'trade_authorization':'NONE','trade_action':'NO_TRADE',
        'issues':[{'code':'NATIVE_SOURCE_INPUTS_REQUIRED','stage':'NATIVE_INPUT_READY',
            'field_path':field,'source_id':'VERIFIED-ANALYSIS:'+analysis['report_digest'],
            'producer':'W8.assemble_native_input','missing_reason':'Required source section has not been produced',
            'remediation':'Bind the identified original source; retain existing approved allocation',
            'retryable':False,'evidence_ref':'native_sources'} for field in missing],
        'stage_status':{'SOURCE_LOADING':'COMPLETED','SOURCE_READY':'COMPLETED','MAPPING_READY':'PARTIAL',
            'NATIVE_INPUT_READY':'BLOCKED','NATIVE_COMPLETE':'NOT_REACHED','MENTOR_READY':'NOT_REACHED'},
        'source_inventory':{key:('REUSED_VERIFIED_SHARED_COMPONENT' if key in sources['native_bundle'] else
            'REQUIRED_ORIGINAL_SOURCE_NOT_PRODUCED') for key in ('stock_request','bond_request','stock_evidence',
                'producer_contract','stock_source_fields','bond_evidence','asset_framework','physical_sgov')},
        'context_source_inventory':{key:('REUSED_VERIFIED_SHARED_CONTEXT' if key in sources['trusted_context']
            else 'REQUIRED_ORIGINAL_SOURCE_NOT_PRODUCED') for key in
                ('funding_source','valuation_source','v70_source','c7_source','technical_source')},
        'coverage':[{'instrument_id':r['instrument_id'],'symbol':r['symbol'],'status':'BLOCKED',
            'native_complete':False,'mentor_ready':False,'holding_analysis_status':r['status'],
            'reason':'FULL_NATIVE_SOURCE_ASSEMBLY_INCOMPLETE'} for r in analysis['analysis_result']['positions']],
        'coverage_scope':analysis['analysis_result']['scope'],
        'readable_analysis':{'symbol':producer.symbol,'classification':asset_class['primary_class'],
            'framework':asset_class['primary_framework'],'source_quantity':held['quantity'],
            'asset_type':asset_class['asset_type'],'asset_grade':asset_class['asset_grade'],
            'observed_close':row['market'].get('observed_close') if row.get('market') else None,
            'price_observation_date':row['market'].get('observed_date') if row.get('market') else None,
            'original_core_state':outputs.get('v82_core_observation',{}).get('result'),
            'cash_assumption':trial['label'],'native_deployment_completed':False,
            'native_work9_mentor_completed':False,'first_blocker':failure},
        'analysis_summary':'已重用並重播同輪持倉分析及原生股債組件；完整原生部署仍缺：'+','.join(missing)}
    report['manifest']=producer.source_manifest(report,request,held,'DB:'+analysis['source_db_sha256'])
    report['manifest_digest']=digest(report['manifest']);report['report_digest']=digest(report)
    return report
