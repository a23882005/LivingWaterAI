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


def produce(root,request,symbol,descriptor,*,producer_factory=None,observation_cache=None):
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
    if cfg is None:
        gaps=deepcopy(data.get('missing_source_facts') or [])
        if not gaps:raise PermissionError('MEMBER_PRODUCER_EXACT_ROOT_GAPS_REQUIRED')
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE','known_source_inputs':deepcopy(data.get('known_source_inputs',{})),
            'issues':gaps,'source_reference':data['source_reference']},None
    seed=cfg.get('request_seed') or {};context=cfg.get('context_seed') or {};owner=seed.get('owner') or {}
    if (seed.get('client_id')!=request['client_id'] or seed.get('client_snapshot',{}).get('payload')!=request['client_snapshot']['payload']
        or owner.get('client_id')!=request['client_id']
        or any(not owner.get(k) for k in ('account','broker','currency','funding_domain'))
        or context.get('client_id')!=request['client_id'] or seed.get('trade_authorization')!='NONE'
        or any(k in seed for k in ('native_bundle','native_result','analysis_report'))):
        raise PermissionError('MEMBER_PRODUCER_ORIGINAL_BOOTSTRAP_SCOPE_MISMATCH')
    from deployment_c7_sources import FAMILY_PROFILE
    if context.get('family_c7_profile')!=FAMILY_PROFILE:raise PermissionError('MEMBER_PRODUCER_EXPLICIT_C7_PROFILE_REQUIRED')
    # The Member's current approval governs this run. An older bootstrap may
    # retain a withdrawn historical money table; never calculate from it when
    # the current approved investment pool is unresolved.
    lines=request['confirmed_target'].get('payload',{}).get('draft',{}).get('target_lines') or []
    unavailable=[i for i,row in enumerate(lines) if row.get('target_amount',{}).get('value_state')!='KNOWN'
        or row['target_amount'].get('amount') is None or not row['target_amount'].get('currency')]
    if not lines or unavailable:
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE','issues':[{
            'code':'CURRENT_APPROVED_INVESTMENT_POOL_MONEY_BASE_REQUIRED',
            'field_path':'confirmed_target.payload.draft.target_lines'+('['+str(i)+'].target_amount' if i is not None else ''),
            'kind':'EXTERNAL_ROOT_FACT_REQUIRED','value_state':'UNKNOWN','historical_bootstrap_money_substituted':False}
            for i in unavailable or [None]]},None
    if request.get('macro_snapshot') is None:
        return {**attempt,'status':'ROOT_SOURCE_FACTS_UNAVAILABLE','issues':[{
            'code':'MEMBER_PRODUCER_PRECAPTURED_MACRO_REQUIRED','field_path':'request.macro_snapshot',
            'kind':'ORIGINAL_PRODUCER_SOURCE_REQUIRED'}]},None
    cfg.update(repo_root=root,focus_symbol=symbol,flow='DEPLOYMENT',observation_cache=observation_cache,run_binding={
        'client_id':request['client_id'],'run_id':request['run_id'],'evaluation_at':request['evaluation_at'],
        'source_db_sha256':data['source_db_sha256'],'owner':deepcopy(owner),'macro_snapshot':deepcopy(request['macro_snapshot'])})
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
        normalized=[]
        for issue in issues or []:
            normalized.append(deepcopy(issue) if isinstance(issue,dict) else {
                'code':getattr(issue,'code',type(issue).__name__),'field_path':str(getattr(issue,'path','')),
                'message':str(getattr(issue,'message',issue))})
        code=getattr(error,'code',None)
        if not code and normalized:code=normalized[0].get('code')
        if not code:
            match=re.match(r'([A-Z][A-Z0-9_.]+)(?:[: ]|$)',str(error));code=match.group(1) if match else type(error).__name__
        return {**attempt,'status':'ORIGINAL_SOURCE_PRODUCER_REJECTED','issues':[{
            'code':code,'message':str(error),
            'field_path':(normalized[0].get('field_path') if normalized else None) or native_error_path(error) or 'AssetSourceProducer.original_inputs','original_issues':normalized,
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
            'issues':deepcopy(production.get('source_validation_issues') or [production.get('first_failure')]),
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
