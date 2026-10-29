"""Bind observed bonds to the original Work5/V75 input and source checks.

Physical SGOV, approved bond targets and logical SGOV roles remain separate.
Missing freshness, role or predicate evidence is never a settled/normal fact.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sys

from family_input import digest
from runtime_loader import load_c_module
from current_analysis_delivery import source_target_in_currency
from bond_engine import V75_PATH


def _runtime(root):
    path=Path(root).resolve()/V75_PATH
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent!=path/'v75_runtime':
        raise PermissionError('BOND_SOURCE_RUNTIME_MISMATCH')
    return path/'v75_runtime'


def _target(request,symbol,fx):
    rows=[r for r in request['confirmed_target']['payload']['draft']['target_lines']
        if r.get('ticker')==symbol]
    # Only an already explicit SGOV_BOND role can select the bond portion of
    # a two-role approval. The physical position is never split by target ratio.
    if symbol=='SGOV' and len(rows)==2 and {r['instrument_id'] for r in rows}=={'SGOV_BOND','SGOV_DRY'}:
        rows=[r for r in rows if r['instrument_id']=='SGOV_BOND']
    if len(rows)!=1:return None
    money=source_target_in_currency(rows[0]['target_amount'],request['owner']['currency'],fx)
    if money is None:return None
    return {'source_line':deepcopy(rows[0]),'money':money}


def delivery(result):
    return {k:deepcopy(v) for k,v in result.items()
        if k not in ('shared_inputs','adapter_request','adapter_result','source_fx','strategic_policy')}


def target_market_observations(request,observations,rows,*,root):
    # The source producer has already fetched these approved symbols once.
    # Reuse that immutable intake; never refetch the household per asset.
    _runtime(root)
    from v75_runtime.work3 import US_LISTED_ASSETS
    target_symbols={r.get('ticker') for r in request['confirmed_target']['payload']['draft']['target_lines']}
    held_symbols={r['symbol'] for r in rows}
    return {r['instrument_key']:deepcopy(r) for r in observations['assets']
        if (r['symbol'] in (target_symbols & set(US_LISTED_ASSETS))-held_symbols
            or r.get('advisory_candidate_scope')=='BOND_RECOMMENDATIONS_ONLY')}


def build(root,request,report,*,shared_inputs,fx_observation,strategic_policy):
    rows=[r for r in report['analysis_result']['positions']
        if r['native_product_identity'].get('engine_route')=='V75_PREDICATES']
    if not rows:return None
    runtime=_runtime(root)
    from v75_runtime.validation import validate_v75_run_input
    from v75_runtime.work3 import build_work3_state
    from v75_runtime.work3 import US_LISTED_ASSETS
    w3=load_c_module(root,3);w5=load_c_module(root,5)
    snapshot=request['client_snapshot']['payload'];owner=request['owner'];run=request['run_id']
    shared=deepcopy(shared_inputs)
    inp=shared['work3_input']
    if (inp['run_id']!=run or inp['client_state_context']['payload']['client_id']!=request['client_id']
        or inp['client_state_context']['payload']['full_client_snapshot']!=snapshot
        or inp['work2_envelope']['owner']!={'funding_domain':'US_BROKER',
            'broker':owner['broker'],'account':owner['account']}
        or inp['work2_envelope']['currency']!=owner['currency']):
        raise PermissionError('BOND_SOURCE_SHARED_BINDING_MISMATCH')
    refs=inp['shared_decision_context']['source_reference_ids']
    market_payload=inp['shared_decision_context']['payload']['bond_market_observations']
    expected={r['instrument_id']:r['market'] for r in rows if r.get('market')}
    expected.update(deepcopy(report.get('bond_target_market_observations',{})))
    if market_payload!=expected:raise PermissionError('BOND_SOURCE_MARKET_BINDING_MISMATCH')
    result={'schema_version':'Family.W8.NativeBondSource.v1','client_id':request['client_id'],
        'run_id':run,'owner':deepcopy(owner),'source_db_sha256':snapshot['source_sha256'],
        'status':'SOURCE_INCOMPLETE','requested_instruments':[r['instrument_id'] for r in rows],
        'shared_inputs':shared,'source_fx':deepcopy(fx_observation),
        'strategic_policy':deepcopy(strategic_policy),'call_trace':[], 'issues':[],
        'policy_audit':deepcopy(report.get('bond_policy_audit')),
        'targets':{},'physical_holdings':{},'predicate_observations':{},
        'sgov_role_source_rows':{k:deepcopy(snapshot['tables'].get(k,[]))
            for k in ('sgov_role_proposal','sgov_role_confirmation')},
        'canonical_result':None,'full_native_canonical_complete':False,'trade_action':'NO_TRADE'}
    gaps=result['issues']
    existing=[];targets=[]
    for row in rows:
        symbol=row['symbol'];market=row.get('market') or {};qty=row['holding'].get('quantity')
        recommendation=row['current_analysis']['recommendation']
        price=market.get('observed_close')
        if (qty is None or price is None or recommendation.get('position_currency')!=owner['currency']):
            gaps.append({'code':'BOND_PHYSICAL_VALUE_SOURCE_REQUIRED',
                'field_path':'existing_bond_holdings.'+symbol})
        else:
            value=Decimal(str(qty))*Decimal(str(price))
            money={'amount':str(value),'currency':owner['currency']}
            existing.append({'asset_id':symbol,'amount':money,'broker_account_id':owner['account']})
            result['physical_holdings'][symbol]={'quantity':str(qty),'valuation':money,
                'market_source_sha256':market.get('source_sha256'),'price_date':market.get('observed_date'),
                'scope':'PHYSICAL_POSITION__SGOV_LOGICAL_ROLE_NOT_INFERRED'}
    target_symbols=({r.get('ticker') for r in request['confirmed_target']['payload']['draft']['target_lines']}
        & set(US_LISTED_ASSETS))|{r['symbol'] for r in rows}
    for symbol in sorted(target_symbols):
        target=_target(request,symbol,fx_observation)
        if target is None:
            gaps.append({'code':'BOND_TARGET_SOURCE_REQUIRED','field_path':'target_bond_holdings.'+symbol})
        else:
            result['targets'][symbol]=target
            targets.append({'asset_id':symbol,'target_amount':
                {k:target['money'][k] for k in ('amount','currency')},'broker_account_id':owner['account']})
    for source in market_payload.values():
        symbol=source['symbol']
        predicates=deepcopy(source.get('v75_original_predicates',{}))
        result['predicate_observations'][symbol]=predicates
        if symbol not in target_symbols:continue
        for pid,entry in predicates.items():
            native=entry['original_result']
            if native.get('assessment_status')!='VALID' or not entry.get('deployment_input_eligible'):
                gaps.append({'code':'V75_PREDICATE_SOURCE_INCOMPLETE',
                    'field_path':'bond_evidence.'+symbol+'.'+pid,
                    'native_assessment':native.get('assessment_status'),
                    'required_input_missing':deepcopy(native.get('required_input_missing',[])),
                    'freshness_verified':bool(entry.get('input_freshness_verified'))})
    # A partial list is not sent as an apparently complete bond portfolio.
    if len(existing)!=len(rows) or len(targets)!=len(target_symbols):return result
    if not strategic_policy or strategic_policy.get('client_id')!=request['client_id']:
        gaps.append({'code':'V75_STRATEGIC_SOURCE_REQUIRED','field_path':'strategic_bond_weight_b0'})
        return result
    parameter_files={name:sha256((runtime/name).read_bytes()).hexdigest()
        for name in ('constants.py','predicates.py','work4.py')}
    result['deployment_parameter_sources']=parameter_files
    # This is a content-addressed identifier of the consumed original code,
    # not a copied fixture's deployment-parameter approval/version label.
    parameter_version='ORIGINAL_V75_CODE_SHA256:'+digest(parameter_files)
    for symbol in target_symbols:
        if symbol not in result['predicate_observations']:
            gaps.append({'code':'V75_TARGET_MARKET_SOURCE_REQUIRED','field_path':'bond_evidence.'+symbol+'.market'})
    times=[r.get('provider_verified_at') for r in market_payload.values() if r['symbol'] in target_symbols]
    if report.get('bond_market_supplement'):
        times.append(report['bond_market_supplement']['available_at'])
    if any(not t for t in times):
        gaps.append({'code':'V75_SOURCE_CAPTURE_TIME_REQUIRED','field_path':'market_snapshot.data_timestamp'})
        return result
    for t in times:
        if datetime.fromisoformat(t.replace('Z','+00:00'))>datetime.fromisoformat(request['evaluation_at'].replace('Z','+00:00')):
            raise PermissionError('BOND_SOURCE_FUTURE_MARKET_CAPTURE')
    market_at=max(times,key=lambda t:datetime.fromisoformat(t.replace('Z','+00:00')))
    v70=inp['v70_runtime_context'];boundary=inp['work2_envelope']['sgov_boundary']
    def role(name):
        value=boundary[name]
        return {'status':'KNOWN' if value is not None else 'UNKNOWN','value':deepcopy(value)}
    src={'contract_name':w5.SOURCE_CONTEXT_NAME,'contract_version':w5.SOURCE_CONTEXT_VERSION,
        'run_id':run,'client_ref':request['client_id'],'deployment_parameter_version':parameter_version,
        'funding_settlement_status':inp['work2_envelope']['settlement']['source_status'],
        'life_stage_code':strategic_policy.get('life_stage_code','UNKNOWN'),
        'strategic_bond_weight_b0':{'value':str(strategic_policy['bond_percent']),'unit':'PERCENT'},
        'existing_bond_holdings':existing,'target_bond_holdings':targets,
        'authorized_universe':[t['asset_id'] for t in targets if Decimal(t['target_amount']['amount'])>0],
        'market_snapshot':{'data_timestamp':market_at,'data_source':'VERIFIED_CACHE_CAPTURE__NOT_EXCHANGE_CLOSE_ATTESTATION',
            'freshness_state':'UNKNOWN','payload':deepcopy(market_payload),'source_lineage':deepcopy(refs)},
        'v70_snapshot':{'data_timestamp':v70['snapshot_as_of'],'data_source':'V70.RUNTIME_CONTEXT',
            'freshness_state':'UNKNOWN','payload':deepcopy(v70['payload']),'source_lineage':deepcopy(v70['source_reference_ids'])},
        'sgov_bond_bucket_amount':role('sgov_bond_bucket_amount'),
        'sgov_dry_powder_bucket_amount':role('sgov_dry_powder_bucket_amount'),
        'source_reference_ids':deepcopy(refs),'data_as_of':{'market':market_at,'v70':v70['snapshot_as_of']}}
    result['authorization_scope']='EXISTING_CONFIRMED_TARGET_UNIVERSE__W1_NEW_BUY_PERMISSION_STILL_SEPARATE'
    result['call_trace'].append('C8C9.Work3.build_context_handoff')
    try:
        handoff=w3.build_context_handoff(inp)
        adapter={'contract_name':w5.INPUT_CONTRACT_NAME,'contract_version':w5.INPUT_CONTRACT_VERSION,
            'baseline_id':w5.BASELINE_ID,'run_id':run,'work3_handoff':handoff,
            'c7_funding_context':deepcopy(shared['c7_funding_context']),'v75_source_context':src}
        result['adapter_request']=adapter
        result['call_trace'].append('C8C9.Work5.build_v75_runtime_input')
        built=w5.build_v75_runtime_input(adapter);result['adapter_result']=built
        result['call_trace'].append('V75.validate_v75_run_input')
        checked=validate_v75_run_input(built['v75_runtime_input'])
        result['native_validation']={'disposition':checked.disposition.value,
            'accepted':checked.accepted,'issues':[vars(i) for i in checked.issues]}
        gaps.extend({'code':i.code,'field_path':i.path,'message':i.message} for i in checked.issues)
        if checked.model is not None:
            result['call_trace'].append('V75.build_work3_state:STRUCTURAL_DIAGNOSTIC_ONLY')
            state=build_work3_state(checked.model)
            result['structural_state']=state.model_dump(mode='json')
            gaps.extend({'code':i.code,'field_path':i.field,'message':i.message}
                for i in state.issues)
            ratio_issues=[i.code for i in state.issues if i.code in (
                'US_GENERIC_CORE_TARGET_RATIO_MISMATCH','TW_GENERIC_CORE_TARGET_RATIO_MISMATCH')]
            from v75_runtime.work3 import US_GENERIC_CORE_WEIGHTS,TW_GENERIC_CORE_WEIGHTS
            result['target_compatibility']={
                'status':'APPROVED_TARGET_RULE_INCOMPATIBILITY' if ratio_issues else 'NATIVE_GENERIC_TEMPLATE_MATCH',
                'native_issue_codes':ratio_issues,
                'source_target_digest':digest(request['confirmed_target']),
                'source_kind':request['confirmed_target'].get('source_kind'),
                'runtime_work3_sha256':sha256((runtime/'work3.py').read_bytes()).hexdigest(),
                'native_us_template':{k:str(v) for k,v in US_GENERIC_CORE_WEIGHTS.items()},
                'native_tw_template':{k:str(v) for k,v in TW_GENERIC_CORE_WEIGHTS.items()},
                'approved_target_amounts':deepcopy(targets),'mapping_complete':True,
                'approved_target_modified':False,'native_rule_overridden':False,
                'exception_route':'NOT_SUPPORTED_BY_FROZEN_RUNTIME',
                'resolution':('COMPARE_NATIVE_PROPOSAL_WITH_UNCHANGED_APPROVAL'
                    if result['policy_audit'] and result['policy_audit'].get('bond_advisory_policy')
                    else 'KEEP_APPROVAL_AND_REPORT_TEMPLATE_DIFFERENCE') if ratio_issues else 'NO_TEMPLATE_CHANGE_REQUIRED'}
        result['status']='ORIGINAL_V75_SOURCE_CHECKED_WITH_GAPS'
    except ValueError as exc:
        result['status']='NATIVE_CONTRACT_REJECTED'
        gaps.append({'code':getattr(exc,'code',type(exc).__name__),
            'field_path':'v75_source_context','message':str(exc)})
    from bond_advisory import build as build_advisory
    advisory=build_advisory(root,request,result)
    if advisory is not None:
        result['advisory_comparison']=advisory
        result['call_trace']+=advisory['call_trace']
    return result


def validate(root,request,report):
    recorded=report.get('native_bond_source')
    if recorded is None:return
    expected=build(root,request,report,shared_inputs=recorded['shared_inputs'],
        fx_observation=recorded['source_fx'],strategic_policy=recorded['strategic_policy'])
    if recorded!=expected:raise PermissionError('NATIVE_BOND_SOURCE_REPLAY_MISMATCH')
    for row in report['analysis_result']['positions']:
        if row['instrument_id'] in recorded['requested_instruments']:
            if row['current_analysis'].get('native_bond_source')!=delivery(expected):
                raise PermissionError('NATIVE_BOND_DELIVERY_REPLAY_MISMATCH')
