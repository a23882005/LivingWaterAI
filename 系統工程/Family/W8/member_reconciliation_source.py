"""Replay original portfolio observations in one member/run source envelope.

This is an input to the existing C7 source assembler, not a reconciliation
attestation. Dated values, account cash, unresolved orders and physical SGOV
remain separate. Only the original complete-facts contract can qualify NAV,
funding, exposure completeness or a real financial cycle.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

from family_input import digest
from member_market_source import time

SCHEMA='Family.W8.MemberReconciliationSource.v1'
INPUTS=('client_id','source_db_sha256','classification_source','product_sources',
    'v75_parameter_source','market_sources','current_broker_sources',
    'position_valuation_inputs','member_db_path','member_drive_binding','ledger_source',
    'official_target_base_source','document_target','owner_target_decision_source')


def binding(request):
    snapshot=request['client_snapshot']['payload']
    if (snapshot['client_id']!=request['client_id']
        or snapshot['payload_digest']!=digest(snapshot['tables'])
        or request.get('trade_authorization')!='NONE'
        or any(r.get('client_id',request['client_id'])!=request['client_id']
            for rows in snapshot['tables'].values() for r in rows)):
        raise PermissionError('MEMBER_RECONCILIATION_SNAPSHOT_OR_TRADE_SCOPE')
    # Native approved-target enrichment may add hashes/labels, but cannot
    # change the original allocation row, selected instrument or weight.
    target=request['confirmed_target'];lines=[]
    for line in target['payload']['draft']['target_lines']:
        lines.append({'instrument_id':(line.get('source_allocation_row') or {}).get('instrument_key',line['instrument_id']),
            'ticker':line.get('ticker'),'weight':line['weight'],
            'source_allocation_row':line.get('source_allocation_row')})
    return dict(client_id=request['client_id'],run_id=request['run_id'],evaluation_at=request['evaluation_at'],
        source_db_sha256=snapshot['source_sha256'],snapshot_digest=snapshot['payload_digest'],
        target_version=target['target_version'],target_lines_digest=digest(sorted(lines,key=lambda r:r['instrument_id'])),
        approved_money_base_digest=digest(target['payload']['draft'].get('denominator')),
        macro_snapshot_digest=digest(request.get('macro_snapshot')))


def source_files(config,evaluation_at):
    """Pin all recursively referenced immutable files, including manifests."""
    files={};visited=set()
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            path=value.get('local_path')
            if path is not None:
                p=Path(path);raw=p.read_bytes();actual=sha256(raw).hexdigest()
                if value.get('sha256')!=actual:
                    raise PermissionError('MEMBER_RECONCILIATION_SOURCE_BYTES_CHANGED:'+str(p))
                for key in ('retrieved_at','captured_at','verified_at'):
                    if value.get(key) and time(value[key])>time(evaluation_at):
                        raise PermissionError('MEMBER_RECONCILIATION_SOURCE_AFTER_CUTOFF:'+key)
                files[str(p.resolve())]={'local_path':str(p.resolve()),'sha256':actual,'bytes':len(raw)}
                if actual not in visited:
                    visited.add(actual)
                    try:nested=json.loads(raw)
                    except (UnicodeDecodeError,json.JSONDecodeError):nested=None
                    if nested is not None:walk(nested)
            for item in value.values():walk(item)
    walk(config)
    return [files[k] for k in sorted(files)]


def normalize(root,request,config):
    bound=binding(request);snapshot=request['client_snapshot']['payload'];at=request['evaluation_at']
    if (config.get('client_id')!=request['client_id']
        or config.get('source_db_sha256')!=snapshot['source_sha256']):
        raise PermissionError('MEMBER_RECONCILIATION_CONFIG_SCOPE')
    pinned=source_files(config,at)
    from member_v82_analysis import universe,target_source
    from all_asset_coverage import build
    from member_position_valuation import produce
    from member_market_source import read_market
    from native_asset_source import classification
    from approved_v04_technical import load_profile
    if target_source(snapshot,config,at)!=request['confirmed_target']:
        raise PermissionError('MEMBER_RECONCILIATION_ORIGINAL_TARGET_SOURCE_REPLAY_MISMATCH')
    coverage=universe(snapshot,request['confirmed_target'],at,root)
    ledger={'status':'MEMBER_LEDGER_NOT_REGISTERED','cycle_count':None,
        'resource_initialized':False,'financial_cycle_initialized':False}
    if config.get('member_db_path'):
        from on_demand_drive_io import Binding,inspect
        from v82_ledger_drive import resolve_resource
        member=Binding(**config['member_drive_binding'])
        if member.client_id!=request['client_id'] or inspect(config['member_db_path'],member)['sha256']!=snapshot['source_sha256']:
            raise PermissionError('MEMBER_RECONCILIATION_OFFICIAL_DB_BYTES_CHANGED')
        ledger=resolve_resource(config['member_db_path'],member,config.get('ledger_source'),evaluation_at=at)
        path=Path(config['member_db_path'])
        pinned.append({'local_path':str(path.resolve()),'sha256':snapshot['source_sha256'],'bytes':path.stat().st_size})
    all_assets=build(request,config,coverage,root,ledger_resource=ledger)
    profile=load_profile(Path(__file__).with_name('owner_approved_v10.json'))
    rows=[]
    for asset in coverage['assets']:
        identity=classification(asset['symbol'],config['classification_source'],config.get('product_sources',{}).get(asset['symbol']))
        instrument=asset.get('instrument') or {}
        is_etf=(False if instrument.get('instrument_type')=='STOCK' or identity['asset_type']=='INDIVIDUAL_STOCK'
            else True if instrument.get('instrument_type')=='ETF' or identity['asset_type'] in
            ('BROAD_ETF','INDUSTRY_ETF','THEME_ETF') else None)
        try:
            market=read_market(config.get('market_sources',{}).get(asset['symbol']),symbol=asset['symbol'],
                evaluation_at=at,repo_root=root,profile=profile,is_etf=is_etf)
        except ValueError as error:
            if not str(error).startswith('MEMBER_MARKET_'):raise
            market=None
        rows.append({'symbol':asset['symbol'],'market':market})
    values=produce(request,all_assets,rows,config['position_valuation_inputs'])
    books=[{'owner':deepcopy(view['owner']),'captured_at':view['captured_at'],
        'cash':deepcopy(view['cash']),'positions':deepcopy(view['positions']),
        'order_source':deepcopy(view['order_source']),
        'reconciliation_quality':deepcopy(view.get('reconciliation_quality'))}
        for view in all_assets['current_broker_views']]
    sgov=next((r for r in all_assets['holding_and_target_rows'] if r['symbol']=='SGOV'),None)
    out=dict(schema_version=SCHEMA,**bound,request_digest=digest(request),
        confirmed_target_digest=digest(request['confirmed_target']),
        original_target_sources={k:deepcopy(config[k]) for k in
            ('official_target_base_source','document_target','owner_target_decision_source') if k in config},
        source_files=pinned,universe_digest=coverage['universe_digest'],
        holdings_projection_digest=coverage['holdings_projection_digest'],
        securities=deepcopy(all_assets['expected']),account_keys=deepcopy(all_assets['account_keys']),
        coverage_digest=all_assets['coverage_digest'],position_values=values,
        account_cash_observations=deepcopy(all_assets['cash_accounts']),broker_books=books,
        sgov=dict(in_scope=sgov is not None,holding_and_target_sources=deepcopy(sgov),
            dated_physical_observations=[deepcopy(r) for r in values['positions'] if r['symbol']=='SGOV'],
            original_role_proposals=deepcopy(snapshot['tables'].get('sgov_role_proposal',[])),
            original_role_confirmations=deepcopy(snapshot['tables'].get('sgov_role_confirmation',[])),
            physical_included_in_cash=False,role_amounts_added_to_physical_value=False,
            qualified_BOND_amount=None,qualified_DRY_amount=None),
        planning_ledger={k:deepcopy(v) for k,v in ledger.items() if k!='cycles'},
        qualified_current_NAV=None,qualified_available_cash=None,qualified_incremental_authorization=None,
        complete_exposure_book=False,reconciliation_attested=False,financial_cycle_initialized_by_adapter=False,
        scope='REPLAYED_ORIGINAL_OBSERVATIONS__COMPLETE_FACTS_CONTRACT_STILL_REQUIRED',
        trade_authorization='NONE',trade_action='NO_TRADE')
    out['digest']=digest(out)
    return out


def persist(root,request,config,directory):
    folder=Path(directory).resolve()
    if folder.is_relative_to(Path(root).resolve()):
        raise PermissionError('MEMBER_RECONCILIATION_PRIVATE_ARTIFACT_OUTSIDE_REPO_REQUIRED')
    inputs={k:deepcopy(config[k]) for k in INPUTS if k in config}
    result=normalize(root,request,inputs)
    envelope=dict(schema_version=SCHEMA,request=deepcopy(request),configuration=inputs,
        binding=binding(request),normalized=result,derived_after_cutoff_is_not_new_source_knowledge=True)
    raw=(json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    folder.mkdir(parents=True,exist_ok=True)
    file=folder/(digest({k:request[k] for k in ('client_id','run_id')})+'.original-financial-sources.json')
    if file.exists():
        if file.read_bytes()!=raw:raise PermissionError('MEMBER_RECONCILIATION_SAVED_RUN_CHANGED')
    else:
        with file.open('xb') as f:f.write(raw)
    return result,{'local_path':str(file),'sha256':sha256(raw).hexdigest()}


def read(root,descriptor,request):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('MEMBER_RECONCILIATION_ENVELOPE_BYTES_CHANGED')
    data=json.loads(raw)
    if (data.get('schema_version')!=SCHEMA or data.get('binding')!=binding(request)
        or data['binding']!=binding(data['request'])):
        raise PermissionError('MEMBER_RECONCILIATION_MEMBER_RUN_DB_TARGET_OR_TIME_MISMATCH')
    original=normalize(root,data['request'],data['configuration'])
    if original!=data.get('normalized'):
        raise PermissionError('MEMBER_RECONCILIATION_ORIGINAL_SOURCE_REPLAY_MISMATCH')
    return original
