"""Member Menu04 -> original AssetSourceProducer -> existing financial pack.

Only trusted, hash-checked per-member raw producer settings enter here. A
partial source attempt retains the original failure and is never a ready pack.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from datetime import datetime,timezone
from contextlib import nullcontext
import json
import re
from family_input import digest


def remaining_root_gaps(gaps,normalized):
    accepted=((normalized or {}).get('financial_facts') or {}).get('accepted_owner_financial_facts')
    result=deepcopy(gaps)
    if accepted is None:return result
    for item in result:
        if item.get('code')=='SAME_CUTOFF_SETTLEMENT_RESERVES_ORDERS_AND_FUNDING_DOMAIN_REQUIRED':
            original=deepcopy(item)
            item.update(code='ACCOUNT_BINDING_SELL_FILL_OTHER_COMMITMENT_AND_POLICY_COVERAGE_REQUIRED',
                original_source_issue=original,owner_cash_and_settlement_accepted=True,
                current_buy_absence_accepted=True,accepted_source_digest=accepted['digest'],
                remaining_source_fields=['exact_account_and_funding_domain_binding','same_run_reporting_FX_if_needed',
                    'sell_orders_fills_and_other_commitments','protection_and_cap_applicability'])
    return result


def document_analysis_configuration(request,symbol,descriptor):
    """Build an analysis-only seed from explicit pinned document/account inputs.

    An absent deployment bootstrap need not erase an existing document account
    category. This adapter creates no funding proof or holdings attestation.
    """
    from approved_target_input import build_approved_target_view,bind_document_account_scope
    from member_market_source import time
    from deployment_c7_sources import FAMILY_PROFILE
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('MEMBER_ANALYSIS_SOURCE_BYTES_CHANGED')
    source=json.loads(raw);snapshot=request['client_snapshot']['payload']
    if (source.get('schema_version')!='Family.W8.MemberDocumentAccountAnalysis.v1'
        or source.get('client_id')!=request['client_id'] or source.get('asset_id')!=symbol
        or snapshot.get('client_id')!=request['client_id']
        or snapshot.get('payload_digest')!=digest(snapshot.get('tables'))
        or request.get('trade_authorization')!='NONE'
        or source.get('source_db_sha256')!=snapshot['source_sha256']
        or source.get('target_version')!=request['confirmed_target']['target_version']
        or not source.get('source_reference')
        or any(k in source for k in ('native_bundle','native_result','family_scope','configuration'))):
        raise PermissionError('MEMBER_ANALYSIS_SOURCE_SCOPE_MISMATCH')
    if time(source['available_at'])>time(request['evaluation_at']):
        raise PermissionError('MEMBER_ANALYSIS_SOURCE_AFTER_CUTOFF')
    args=deepcopy(source['document_target']);expected=args.pop('sha256')
    if sha256(Path(args['source_path']).read_bytes()).hexdigest()!=expected:
        raise PermissionError('MEMBER_ANALYSIS_DOCUMENT_BYTES_CHANGED')
    pack=build_approved_target_view(**args,evaluation_at=request['evaluation_at'])
    if pack['target']!=request['confirmed_target']:
        raise PermissionError('MEMBER_ANALYSIS_TARGET_REPLAY_MISMATCH')
    scope=bind_document_account_scope(snapshot,pack,**source['account_category'])
    owner=scope['owner']
    ownership=[r for r in snapshot['tables'].get('account_ownership',[]) if r.get('account_key')==owner['account']]
    brokers=[r for r in snapshot['tables'].get('account_broker_link',[]) if r.get('account_key')==owner['account']]
    if (len(ownership)!=1 or ownership[0].get('owner_client_id')!=request['client_id']
        or ownership[0].get('ownership_state')!='VERIFIED' or len(brokers)!=1
        or brokers[0].get('broker_key')!=owner['broker'] or brokers[0].get('link_state')!='ACTIVE'
        or any(time(r.get('as_of_utc') or r['created_at_utc'])>time(request['evaluation_at'])
            for r in ownership+brokers)):
        raise PermissionError('MEMBER_ANALYSIS_ORIGINAL_ACCOUNT_CLASSIFICATION_REQUIRED')
    versions={'target':str(request['confirmed_target']['target_version']),
        'funding':'UNAVAILABLE_NO_QUALIFIED_FUNDING_SOURCE',
        'market':(request.get('macro_snapshot') or {}).get('digest') or 'UNAVAILABLE_NO_QUALIFIED_MACRO',
        'policy':'ANALYSIS_ONLY_NO_NEW_FUNDS'}
    seed={**deepcopy(request),'schema_version':'Family.W5.request.v1','request_id':request['run_id']+'-analysis',
        'owner':deepcopy(owner),'analysis_permission':'ANALYZE_ONLY','expected_versions':versions,
        'trade_authorization':'NONE','client_snapshot':{'payload':deepcopy(snapshot),
            'digest':digest(snapshot),'snapshot_version':snapshot['source_sha256'],'as_of':request['evaluation_at']}}
    context={'client_id':request['client_id'],'analysis_permission':'ANALYZE_ONLY','expected_versions':deepcopy(versions),
        'snapshot_version':snapshot['source_sha256'],'snapshot_digest':digest(snapshot),
        'target_hash':pack['target']['target_hash'],'approved_document_target_source':pack['trusted_approved_target_source'],
        'approved_document_account_scope':scope,'family_c7_profile':FAMILY_PROFILE}
    return {'request_seed':seed,'context_seed':context,'cash_policy':{},
        'classification_source':deepcopy(source['classification_source']),
        'source_commit':source.get('source_commit')}


def produce(root,request,symbol,descriptor,*,producer_factory=None,observation_cache=None,reconciliation_source=None,public_history_sources=None,issuer_facts_sources=None,equity_only=False,london_market_source=None):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:raise PermissionError('MEMBER_PRODUCER_SOURCE_BYTES_CHANGED')
    data=json.loads(raw)
    if (data.get('schema_version')!='Family.W8.MemberFinancialProducer.v1'
        or data.get('client_id')!=request['client_id'] or data.get('asset_id')!=symbol
        or data.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
        or str(data.get('target_version'))!=str(request['confirmed_target']['target_version'])
        or not data.get('source_reference')
        or any(k in data for k in ('native_bundle','native_result','work6_result','asset_framework'))):
        raise PermissionError('MEMBER_PRODUCER_MEMBER_DB_ASSET_OR_APPROVAL_MISMATCH')
    attempt={'schema_version':'Family.W8.MemberFinancialProducerAttempt.v1','client_id':request['client_id'],
        'asset_id':symbol,'run_id':request['run_id'],'evaluation_at':request['evaluation_at'],
        'source_db_sha256':data['source_db_sha256'],'target_version':data['target_version'],
        'source_descriptor_digest':digest(descriptor),'qualified_financial_pack':False,
        'call_trace':['W8.member_financial_producer'],'trade_action':'NO_TRADE'}
    cfg=deepcopy(data.get('configuration'))
    if cfg is None and data.get('document_account_analysis_source') is not None:
        cfg=document_analysis_configuration(request,symbol,data['document_account_analysis_source'])
        attempt['document_account_analysis_source']=deepcopy(data['document_account_analysis_source'])
    if cfg is not None and issuer_facts_sources is not None:
        cfg['issuer_facts_sources']={**deepcopy(cfg.get('issuer_facts_sources') or {}),
            **deepcopy(issuer_facts_sources)}
    public_binding=None
    if public_history_sources is not None:
        from historical_source_qualification import bind
        observed=bind(public_history_sources,request,symbol)
        public_binding={'client_id':request['client_id'],'run_id':request['run_id'],
            'source_db_sha256':data['source_db_sha256'],'asset_id':symbol,
            'source_descriptors':deepcopy(public_history_sources),'digest':observed['digest']}
        attempt['public_history_source_binding']=deepcopy(public_binding)
    def root_inventory(seed_context=None):
        from family_c7_source_assembly import assemble
        context=deepcopy(seed_context or {})
        if reconciliation_source is not None:context['member_reconciliation_source']=deepcopy(reconciliation_source)
        if public_binding is not None:context['public_history_source_binding']=deepcopy(public_binding)
        context['owner_current_selected_currency']='TWD' if symbol.isdigit() else 'USD'
        return assemble(root,request,context,artifact_directory=Path(data['artifact_directory'])/'c7_root_inventory')
    normalized=None
    if reconciliation_source is not None:
        from member_reconciliation_source import read
        normalized=read(root,reconciliation_source,request)
        attempt['same_run_source_binding']={'source_descriptor':deepcopy(reconciliation_source),
            'source_digest':normalized['digest'],'client_id':normalized['client_id'],
            'run_id':normalized['run_id'],'source_db_sha256':normalized['source_db_sha256'],
            'target_version':normalized['target_version'],'reconciliation_attested':False}
        # Reuse the exact current original base descriptor. An older bootstrap
        # may quote the same amount from an earlier revision of the member's
        # source file; it must not become a second same-run approval lineage.
        if cfg is not None and normalized.get('original_target_sources',{}).get('official_target_base_source') is not None:
            cfg['official_target_base_source']=deepcopy(normalized['original_target_sources']['official_target_base_source'])
        from current_market_contract import new_buy_scope
        buy_scope=new_buy_scope(normalized.get('current_market_contract'),symbol)
        if buy_scope is not None:
            assembly=root_inventory()
            return {**attempt,'status':'NOT_APPLICABLE_NO_ADDITIONAL_BUY_AUTHORIZATION',
                'new_buy_scope':buy_scope,'issues':[],'family_scope_assembly':assembly,
                'independent_source_inventory_issues':deepcopy(assembly['issues']),
                'holding_and_risk_components_preserved':True,
                'call_trace':attempt['call_trace']+['W8.family_c7_source_assembly:holding_source_inventory',
                    'W8.member_financial_producer:PM_no_additional_buy_scope']},None
    if cfg is None:
        if normalized is not None and normalized.get('owner_current_portfolio') is not None:
            assembly=root_inventory()
            return {**attempt,'status':'SOURCE_STAGE_INCOMPLETE',
                'family_scope_assembly':assembly,'issues':deepcopy(assembly['issues']),
                'legacy_source_issues_retained_for_audit':deepcopy(data.get('missing_source_facts') or []),
                'call_trace':attempt['call_trace']+['W8.family_c7_source_assembly:owner_current_logical_categories'],
                'source_reference':data['source_reference']},None
        gaps=remaining_root_gaps(data.get('missing_source_facts') or [],normalized)
        if not gaps:raise PermissionError('MEMBER_PRODUCER_EXACT_ROOT_GAPS_REQUIRED')
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE','known_source_inputs':deepcopy(data.get('known_source_inputs',{})),
            'family_scope_assembly':root_inventory(),
            'issues':gaps,'source_reference':data['source_reference']},None
    seed=cfg.get('request_seed') or {};context=cfg.get('context_seed') or {};owner=seed.get('owner') or {}
    if normalized is not None and normalized.get('owner_current_portfolio') is not None:
        from owner_current_business import order_confirmation
        current=normalized['owner_current_portfolio']['source']
        cfg['order_confirmation']=order_confirmation(current,{**request,'owner':owner})
    if (seed.get('client_id')!=request['client_id'] or seed.get('client_snapshot',{}).get('payload')!=request['client_snapshot']['payload']
        or owner.get('client_id')!=request['client_id']
        or any(not owner.get(k) for k in ('account','broker','currency','funding_domain'))
        or context.get('client_id')!=request['client_id'] or seed.get('trade_authorization')!='NONE'
        or any(k in seed for k in ('native_bundle','native_result','analysis_report'))):
        raise PermissionError('MEMBER_PRODUCER_ORIGINAL_BOOTSTRAP_SCOPE_MISMATCH')
    from deployment_c7_sources import FAMILY_PROFILE
    if context.get('family_c7_profile')!=FAMILY_PROFILE:raise PermissionError('MEMBER_PRODUCER_EXPLICIT_C7_PROFILE_REQUIRED')
    from dated_document_target_source import is_dated,bind_producer_seed
    if is_dated(request['confirmed_target']):
        cfg,attempt['dated_target_source_binding']=bind_producer_seed(cfg,request,normalized)
    scope=cfg['context_seed'].get('approved_document_account_scope')
    if scope is not None:
        # Consume the real W5 analysis-category path before unrelated macro
        # readiness. Its False cash/completeness flags never qualify funding.
        from family_boundary import bind_owner
        from member_market_source import time
        account=bind_owner(request['client_snapshot']['payload'],owner,time(request['evaluation_at']),
            approved_account_scope=scope)
        attempt['account_analysis_binding']=account
        attempt['call_trace'].append('W5.family_boundary.bind_owner:document_analysis_category')
    # The Member's current approval governs this run. An older bootstrap may
    # retain a withdrawn historical money table; never calculate from it when
    # the current approved investment pool is unresolved.
    lines=request['confirmed_target'].get('payload',{}).get('draft',{}).get('target_lines') or []
    unavailable=[i for i,row in enumerate(lines) if row.get('target_amount',{}).get('value_state')!='KNOWN'
        or row['target_amount'].get('amount') is None or not row['target_amount'].get('currency')]
    if not lines or unavailable:
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE','family_scope_assembly':root_inventory(), 'issues':[{
            'code':'CURRENT_APPROVED_INVESTMENT_POOL_MONEY_BASE_REQUIRED',
            'field_path':'confirmed_target.payload.draft.target_lines'+('['+str(i)+'].target_amount' if i is not None else ''),
            'kind':'EXTERNAL_ROOT_FACT_REQUIRED','value_state':'UNKNOWN','historical_bootstrap_money_substituted':False}
            for i in unavailable or [None]]},None
    if request.get('macro_snapshot') is None:
        # Independent account/source qualification still runs when macro data
        # is unavailable. The deployment producer retains its original guard.
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE',
            'family_scope_assembly':root_inventory(context),
            'call_trace':attempt['call_trace']+['W8.family_c7_source_assembly:macro_independent'],
            'issues':[{
            'code':'MEMBER_PRODUCER_PRECAPTURED_MACRO_REQUIRED','field_path':'request.macro_snapshot',
            'kind':'ORIGINAL_PRODUCER_SOURCE_REQUIRED'}]},None
    cfg.update(repo_root=root,focus_symbol=symbol,flow='V82_FINANCIAL' if equity_only else 'DEPLOYMENT',observation_cache=observation_cache,run_binding={
        'client_id':request['client_id'],'run_id':request['run_id'],'evaluation_at':request['evaluation_at'],
        'source_db_sha256':data['source_db_sha256'],'owner':deepcopy(owner),'macro_snapshot':deepcopy(request['macro_snapshot'])})
    cfg['family_c7_assembly_inputs']={'schema_version':'Family.W8.C7AssemblyInputs.v1',
        'artifact_directory':str(Path(data['artifact_directory'])/'c7_sources'),
        'portfolio_reconciliation_source':deepcopy(data.get('portfolio_reconciliation_source'))}
    if reconciliation_source is not None:
        cfg['family_c7_assembly_inputs']['member_reconciliation_source']=deepcopy(reconciliation_source)
    if public_binding is not None:
        cfg['family_c7_assembly_inputs']['public_history_source_binding']=deepcopy(public_binding)
    if london_market_source is not None:
        cfg['family_c7_assembly_inputs']['current_london_daily_source']=deepcopy(london_market_source)
    if producer_factory is None:
        from native_asset_source import AssetSourceProducer
        producer_factory=AssetSourceProducer
    try:
        with observation_cache.activate() if observation_cache is not None else nullcontext():
            pack=producer_factory(**cfg)(deepcopy(request['client_snapshot']['payload']),{'question':request['question']})
    except (ValueError,PermissionError,KeyError,TypeError) as error:
        from native_asset_source import native_error_path
        issues=getattr(error,'issues',None)
        if not issues and isinstance(getattr(error,'issue',None),dict):issues=[error.issue]
        native_issues=[]
        for issue in issues or []:
            native_issues.append(deepcopy(issue) if isinstance(issue,dict) else {
                'code':getattr(issue,'code',type(issue).__name__),'field_path':str(getattr(issue,'path','')),
                'message':str(getattr(issue,'message',issue))})
        code=getattr(error,'code',None)
        if not code and native_issues:code=native_issues[0].get('code')
        if not code:
            match=re.match(r'([A-Z][A-Z0-9_.]+)(?:[: ]|$)',str(error));code=match.group(1) if match else type(error).__name__
        qualified_nav=(normalized or {}).get('current_portfolio_reference',{}).get('formal_NAV_source_qualified') is True
        source_inventory={'family_scope_assembly':root_inventory()} if qualified_nav else {}
        return {**attempt,**source_inventory,'status':'ORIGINAL_SOURCE_PRODUCER_REJECTED','issues':[{
            'code':code,'message':str(error),
            'field_path':(native_issues[0].get('field_path') if native_issues else None) or native_error_path(error) or 'AssetSourceProducer.original_inputs','original_issues':native_issues,
            'kind':'ORIGINAL_SOURCE_CONTRACT_FAILURE'}],
            'call_trace':attempt['call_trace']+['W8.AssetSourceProducer']},None
    child=pack['request']
    if any(child.get(k)!=request.get(k) for k in ('client_id','run_id','evaluation_at')):
        raise PermissionError('MEMBER_PRODUCER_CHILD_RUN_CHANGED')
    attempt['call_trace'].append('W8.AssetSourceProducer')
    production=pack.get('source_production')
    if production is not None:
        folder=Path(data['artifact_directory']).resolve()
        if folder.is_relative_to(Path(root).resolve()):raise PermissionError('MEMBER_PRIVATE_FINANCIAL_ARTIFACT_OUTSIDE_REPO_REQUIRED')
        folder.mkdir(parents=True,exist_ok=True)
        file=folder/(digest({'client':request['client_id'],'run':request['run_id'],'asset':symbol})+'.source-production.json')
        file.write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n')
        return {**attempt,'status':production.get('status','SOURCE_STAGE_INCOMPLETE'),
            **({'owner_scoped_financial_result':deepcopy(production['owner_scoped_financial_result'])}
                if production.get('owner_scoped_financial_result') else {}),
            **({'financial_continuation':deepcopy(production['financial_continuation'])} if production.get('financial_continuation') else {}),
            'issues':deepcopy(production.get('source_validation_issues',[]) or
                ([production['first_failure']] if production.get('first_failure') else [])),
            **({'family_scope_assembly':deepcopy(production['family_scope_assembly'])} if production.get('family_scope_assembly') else {}),
            'raw_producer_artifact':{'local_path':str(file),'sha256':sha256(file.read_bytes()).hexdigest()},
            'call_trace':attempt['call_trace']+production.get('call_trace',[])},None
    if not isinstance(pack.get('native_sources'),dict):
        return {**attempt,'status':'ORIGINAL_SOURCE_PRODUCER_INCOMPLETE','issues':[{
            'code':'ORIGINAL_NATIVE_SOURCES_REQUIRED','field_path':'AssetSourceProducer.native_sources',
            'kind':'ORIGINAL_SOURCE_CONTRACT_FAILURE'}]},None
    # Persist only original producer inputs. OnDemandAnalysisProvider performs
    # original assembly/replay; the existing financial reader binds all money.
    folder=Path(data['artifact_directory']).resolve()
    if folder.is_relative_to(Path(root).resolve()):raise PermissionError('MEMBER_PRIVATE_FINANCIAL_ARTIFACT_OUTSIDE_REPO_REQUIRED')
    folder.mkdir(parents=True,exist_ok=True)
    file=folder/(digest({'client':request['client_id'],'run':request['run_id'],'asset':symbol})+'.json')
    envelope={'schema_version':'Family.W8.MemberV82FinancialSource.v1','client_id':request['client_id'],
        'asset_id':symbol,'run_id':request['run_id'],'evaluation_at':request['evaluation_at'],
        'source_db_sha256':data['source_db_sha256'],'available_at':request['evaluation_at'],
        'source_reference':data['source_reference'],'pack':pack,
        'built_at':datetime.now(timezone.utc).isoformat(),'build_after_cutoff_is_not_new_market_knowledge':True}
    file.write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n')
    result={'local_path':str(file),'sha256':sha256(file.read_bytes()).hexdigest()}
    return {**attempt,'status':'ORIGINAL_PRODUCER_PACK_CREATED__NATIVE_ACCEPTANCE_PENDING',
        'qualified_financial_pack':False,'created_pack_descriptor':result,'issues':[]},result
