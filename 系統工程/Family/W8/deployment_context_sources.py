"""Bind existing same-run cash and V70 contexts without financial defaults.

Instrument keys identify a prepared position; price and exchange evidence keep
their own required source sections. Cash-trial bindings attest no external
funding event or new available balance.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from family_input import digest
from family_boundary import BoundaryError
from runtime_loader import load_c_module
from funding_bridge import bind_funding_source
from v70_source_bridge import bind_v70_source


def extend(root,request,analysis,prepared,sources):
    identity={'client_id':request['client_id'],'run_id':request['run_id'],'owner':request['owner'],
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256']}
    if any(analysis.get(k)!=v for k,v in identity.items()):
        raise PermissionError('DEPLOYMENT_CONTEXT_ANALYSIS_IDENTITY_MISMATCH')
    out=deepcopy(sources);stock=out['native_bundle']['stock_request'];bond=out['native_bundle']['bond_request']
    handoff=stock['work3_handoff'];owner=handoff['owner'];symbol=stock['asset_context']['asset']['asset_id']
    if (stock['run_id']!=request['run_id'] or handoff['run_id']!=request['run_id']
        or handoff['client_state_context']['payload']['client_id']!=request['client_id']
        or any(owner[k]!=request['owner'][k] for k in ('broker','account'))
        or handoff['currency']!=request['owner']['currency']
        or any(stock[k]!=bond[k] for k in ('work3_handoff','c7_funding_context'))):
        raise PermissionError('DEPLOYMENT_CONTEXT_SHARED_IDENTITY_MISMATCH')
    probe=deepcopy(request);probe['native_bundle']=deepcopy(out['native_bundle'])
    contexts=out.setdefault('trusted_context',{});bindings=out.setdefault('context_bindings',{})
    trace=out.setdefault('context_call_trace',[])
    issues=out.setdefault('source_validation_issues',[])
    raw=handoff['v70_runtime_context']
    v70={'schema_version':'Family.W5.V70Source.v1',
        'producer':'Family.W8.VerifiedSharedV70Context','version':'1.0',
        'source_reference':'VERIFIED-SHARED-V70:'+digest(raw),
        'client_id':request['client_id'],'family_owner':deepcopy(request['owner']),'context':deepcopy(raw)}
    probe['v70_source_digest']=digest(v70)
    trace.append('W5.bind_v70_source:reused_verified_shared_context')
    try:
        bound=bind_v70_source(probe,{'v70_source':v70})
    except BoundaryError as error:
        issues.append({'source_section':'trusted_context.v70_source',**deepcopy(error.issue)})
    else:
        contexts['v70_source']=v70
        bindings['v70_source']={'status':'ORIGINAL_SOURCE_BINDING_PASSED',
            'source_digest':digest(v70),'binding_digest':digest(bound),
            'source_run_id':bound['source_run_id'],'analysis_run_id':bound['analysis_run_id']}
    version=request.get('expected_versions',{}).get('funding')
    if not isinstance(version,str) or not version:
        issues.append({'source_section':'trusted_context.funding_source',
            'code':'FUNDING_EXPECTED_VERSION_REQUIRED','field_path':'expected_versions.funding'})
    else:
        c7=stock['c7_funding_context']
        funding={'schema_version':'Family.W8.SourceBoundCashTrialFunding.v1',
            'scope':'EXACT_SAME_RUN_CASH_TRIAL_ONLY__NOT_EXTERNAL_FUNDING_ATTESTATION',
            'c7_funding_context':deepcopy(c7),'owner_binding':{
                'family_owner':deepcopy(request['owner']),'native_owner':deepcopy(owner),
                'currency':request['owner']['currency'],'version':version,
                'source_reference':'VERIFIED-C7-CASH-TRIAL:'+digest(c7)}}
        w6=load_c_module(root,6)
        isolation_request={'contract_name':w6.INPUT_CONTRACT_NAME,'contract_version':w6.INPUT_CONTRACT_VERSION,
            'baseline_id':w6.BASELINE_ID,'run_id':request['run_id'],'work3_handoff':deepcopy(handoff),
            'c7_funding_context':deepcopy(c7),
            'work4_adapter_result':load_c_module(root,4).build_v82_runtime_input(stock),
            'work5_adapter_result':load_c_module(root,5).build_v75_runtime_input(bond)}
        try:
            trace.append('C8C9.Work6.validate_funding_account_isolation:context_replay')
            isolated=w6.validate_funding_account_isolation(isolation_request)
            trace.append('W5.bind_funding_source:reused_verified_cash_trial')
            bound=bind_funding_source(probe,{'funding_source':funding})
        except (BoundaryError,ValueError) as error:
            issues.append({'source_section':'trusted_context.funding_source',
                **deepcopy(getattr(error,'issue',{'code':getattr(error,'code',type(error).__name__),
                    'field_path':'c7_funding_context','message':str(error)}))})
        else:
            contexts['funding_source']=funding
            bindings['funding_source']={'status':'ORIGINAL_SOURCE_AND_WORK6_ISOLATION_PASSED',
                'source_digest':digest(funding),'binding_digest':digest(bound),
                'work6_input_digest':digest(isolation_request),'work6_result_digest':digest(isolated),
                'expected_family_version_preserved':version,
                'scope':funding['scope'],'external_funding_event_attested':False}
    rows=[p for p in prepared.payload['positions'] if p['source_instrument'].get('ticker')==symbol]
    if len(rows)!=1:
        raise PermissionError('DEPLOYMENT_STOCK_POSITION_MAPPING_MISSING_OR_AMBIGUOUS')
    position=rows[0]
    if (position['instrument_key']!=position['source_instrument']['instrument_key']
        or position['quantity']!=stock['asset_context']['confirmed_position_snapshot']['quantity']):
        raise PermissionError('DEPLOYMENT_STOCK_POSITION_MAPPING_MISMATCH')
    out['native_binding']['stock_instrument']={
        'instrument_key':position['instrument_key'],'asset_id':symbol,
        'account_key':request['owner']['account'],'native_owner':deepcopy(owner),
        'source_reference':'VERIFIED-PREPARED-POSITION:'+digest(position)}
    bindings['stock_instrument']={'status':'PREPARED_POSITION_IDENTITY_ONLY',
        'position_digest':digest(position),'exchange_or_canonical_price_qualification_asserted':False}
    trace.append('W8.map_prepared_stock_instrument')
    equity=(analysis.get('qualified_equity_inputs') or {}).get('items',{}).get(symbol)
    if equity is not None:
        row=next(r for r in analysis['analysis_result']['positions'] if r['instrument_id']==position['instrument_key'])
        market=row.get('market') or {}
        if (market.get('qualified_equity_market_digest')!=equity['digest']
            or market.get('observed_date')!=equity['observed_date']
            or market.get('observed_close')!=float(equity['rows'][-1]['Close'])
            or market.get('source_sha256')!=equity['technical_source_template']['sha256']):
            raise PermissionError('DEPLOYMENT_TECHNICAL_MARKET_SOURCE_MISMATCH')
        if equity['status']=='FRESH':
            technical=deepcopy(equity['technical_source_template'])
            technical.update(client_id=request['client_id'],family_owner=deepcopy(request['owner']))
            approval=Path(root)/'系統工程/Family/W8/owner_approved_v10.json'
            technical['owner_approved_rule_source']={'local_path':str(approval),'sha256':sha256(approval.read_bytes()).hexdigest()}
            technical['verified_asset_type']=row['native_product_identity']['asset_type']
            # Only the identity fields consumed by this original source
            # validator enter the probe. No stock_evidence section is emitted.
            technical_probe=deepcopy(probe)
            technical_probe['native_bundle']['stock_evidence']={k:technical['metadata'][k] for k in ('exchange','currency')}
            technical_probe['technical_source_digest']=digest(technical)
            from family_technical_bridge import bind_technical_source
            trace.append('W5.bind_technical_source:qualified_history_and_owner_rules')
            try:
                bound=bind_technical_source(root,technical_probe,{'technical_source':technical,
                    'native_binding':{'data_provenance':'SOURCE_BACKED'}})
            except BoundaryError as error:
                issues.append({'source_section':'trusted_context.technical_source',**deepcopy(error.issue)})
            else:
                contexts['technical_source']=technical
                bindings['technical_source']={'status':'ORIGINAL_TECHNICAL_SOURCE_BOUND__FULL_FAMILY_VALIDATION_PENDING',
                    'source_digest':digest(technical),'binding_digest':digest(bound),
                    'history_digest':technical['metadata']['history_digest'],
                    'owner_approved_spec_sha256':bound['owner_approved_technical']['spec_sha256'],
                    'source_market_digest':equity['digest'],'original_technical_binding_passed':True,
                    'full_family_technical_binding_passed':False}
    return out
