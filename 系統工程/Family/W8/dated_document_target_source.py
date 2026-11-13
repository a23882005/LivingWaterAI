"""Rebuild dated reported-asset money under an existing document approval.

This optional source seam owns no allocation or funding rule. Original document
weights and confirmation remain authoritative; the dated pool is not settlement,
current NAV qualification, a new approval, or a new trade authorization.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path
import json

from family_input import digest, read_snapshot
from member_market_source import time

SCHEMA='Family.W8.DatedDocumentPoolSource.v1'
OPERATION='READ_DATED_REPORTED_POOL_WITH_EXISTING_APPROVAL'
ALIASES={'SGOV_DRY_POWDER':'SGOV_DRY','TWD_CASH_TARGET':'TWD_CASH'}


def require(ok,code):
    if not ok:raise PermissionError('DATED_TARGET_'+code)


def original(source):
    raw=Path(source['local_path']).read_bytes()
    require(sha256(raw).hexdigest()==source.get('sha256'),'SOURCE_BYTES_CHANGED')
    require(bool(source.get('source_reference')),'SOURCE_REFERENCE_REQUIRED')
    return raw


def number(value):
    require(isinstance(value,(str,int)) and not isinstance(value,bool),'EXACT_NUMBER_REQUIRED')
    try:value=Decimal(str(value))
    except InvalidOperation:raise PermissionError('DATED_TARGET_EXACT_NUMBER_REQUIRED')
    require(value.is_finite() and value>=0,'NONNEGATIVE_FINITE_NUMBER_REQUIRED')
    return value


def approval_signature(view):
    record=view['payload'];draft=record['draft']
    return {'target_version':view['target_version'],'confirmation_run_id':view['confirmation_run_id'],
        'target_id':record['target_id'],'status':record['status'],
        'confirmation_evidence':record['confirmation_evidence'],
        'confirmation_evidence_hash':record['confirmation_evidence_hash'],
        'source_reference_ids':record['source_reference_ids'],
        'allocation_version':draft['original_allocation_version'],
        'lines':[{k:deepcopy(row.get(k)) for k in
            ('instrument_id','ticker','asset_type','weight','original_document_row','source_reference_ids')}
            for row in draft['target_lines']]}


def project(pack,descriptor,document_inputs,evaluation_at):
    """Read all pinned originals and calculate money from their source precision."""
    require(evaluation_at is not None,'EVALUATION_TIME_REQUIRED')
    source=json.loads(original(descriptor));view=deepcopy(pack['target']);proof=deepcopy(pack['trusted_approved_target_source'])
    require(source.get('schema_version')==SCHEMA,'SOURCE_SCHEMA_REQUIRED')
    expected={'client_id':proof['client_id'],'document_sha256':proof['source_sha256'],
        'target_version':view['target_version'],'allocation_version':view['payload']['draft']['original_allocation_version']}
    require(all(source.get(k)==v for k,v in expected.items()),'MEMBER_DOCUMENT_OR_VERSION_MISMATCH')
    intake=json.loads(original(source['intake_source']))
    pool=json.loads(original(source['pool_source']))
    require(intake.get('schema')=='Family.PM.H32Menu04InputProjection.v1'
        and pool.get('schema')=='Family.PM.H32.ReportedAssetPoolCalculation.v1','INTAKE_OR_POOL_SCHEMA_REQUIRED')
    require(intake.get('original_source')==pool and intake.get('source_sha256')==source['pool_source']['sha256'],
        'INTAKE_ORIGINAL_POOL_MISMATCH')
    binding=intake.get('request_binding') or {};prior=intake.get('preserved_original_request') or {}
    require(binding.get('client_id')==proof['client_id']
        and binding.get('official_db_sha256')==source.get('source_db_sha256')
        and binding.get('original_target_version')==view['target_version']
        and (binding.get('original_approved_document') or {}).get('sha256')==proof['source_sha256'],
        'INTAKE_MEMBER_DB_DOCUMENT_OR_VERSION_MISMATCH')
    require(source['member_db_source']['sha256']==source['source_db_sha256'],'MEMBER_DB_SOURCE_MISMATCH')
    original(source['member_db_source'])
    snapshot=read_snapshot(source['member_db_source']['local_path'],expected_client_id=proof['client_id'])
    require(snapshot==prior.get('client_snapshot',{}).get('payload'),'ORIGINAL_SNAPSHOT_MISMATCH')
    require(prior.get('client_id')==proof['client_id'] and prior.get('trade_authorization')=='NONE'
        and approval_signature(prior['confirmed_target'])==approval_signature(view),'ORIGINAL_APPROVAL_MISMATCH')
    available=source.get('source_available_at')
    review=intake.get('dated_source_review_request') or {}
    require(available==source['pool_source'].get('available_at')==review.get('evaluation_at'),
        'ORIGINAL_AVAILABILITY_REQUIRED')
    require(time(available)<=time(evaluation_at),'SOURCE_AFTER_CUTOFF')
    require(review.get('run_id') and review['run_id']!=prior.get('run_id')
        and review.get('client_id')==proof['client_id'],'DATED_REVIEW_RUN_REQUIRED')
    require(time(pool['taiwan_securities']['source_time'])<=time(available)
        and time(pool['rate_time'])<=time(available),'COMPONENT_AFTER_SOURCE_AVAILABILITY')
    require(pool.get('ib_nav_includes_cash') is True and pool.get('new_trade_authorization')=='NONE'
        and pool.get('formal_db_writes')==0 and pool.get('formal_ledger_writes')==0,'POOL_SCOPE_REQUIRED')
    require(intake.get('denominator',{}).get('scope')==pool.get('scope') and bool(pool.get('scope')),
        'REPORTED_ASSET_SCOPE_REQUIRED')
    require(binding.get('role_aliases')==ALIASES,'ROLE_ALIASES_MISMATCH')
    lines=view['payload']['draft']['target_lines'];by_id={r['instrument_id']:r for r in lines}
    rows=pool.get('target_rows') or [];roles={};mapping={}
    require(len(lines)==len(by_id)==len(rows),'ROLE_COVERAGE_MISMATCH')
    for row in rows:
        role=row['role'];iid=ALIASES.get(role,role)
        require(role not in roles and iid not in mapping,'DUPLICATE_ROLE')
        require(iid in by_id,'UNMAPPED_ROLE')
        roles[role]=row;mapping[iid]=role
    bound_rows=binding.get('bindings') or [];bound={r['instrument_id']:r for r in bound_rows}
    projected_rows=intake.get('target_lines_by_source_role') or []
    projected={r['source_role']:r for r in projected_rows}
    require(len(bound_rows)==len(bound)==len(lines) and set(bound)==set(by_id)
        and len(projected_rows)==len(projected)==len(roles) and set(projected)==set(roles),'BOUND_ROLE_COVERAGE_MISMATCH')
    with localcontext() as ctx:
        ctx.prec=60
        fx=number(pool['USD_TWD_rate']);require(fx>0,'POSITIVE_FX_REQUIRED')
        # NAV already includes cash. Never add the observed cash a second time.
        total=number(pool['taiwan_securities']['amount_twd'])+number(pool['ib_nav_usd'])*fx
        require(total==number(pool['pool_twd_exact'])==number(intake['denominator']['amount'])
            and intake['denominator'].get('currency')=='TWD','POOL_RECALCULATION_MISMATCH')
        weight_sum=Decimal(0);target_sum=Decimal(0)
        for line in lines:
            iid=line['instrument_id'];role=mapping[iid];row=roles[role];bound_row=bound[iid]
            require(bound_row.get('source_role')==role and all(bound_row.get(k)==line.get(k) for k in ('ticker','asset_type')),
                'ORIGINAL_ROLE_IDENTITY_MISMATCH')
            weight=number(str(line['weight']['value']));amount=total*weight
            require(weight==number(row['weight_percent'])/100
                ==number(projected[role]['weight']['value']),'ORIGINAL_WEIGHT_MISMATCH')
            require(amount==number(row['target_twd_exact'])
                ==number(projected[role]['target_amount']['amount'])
                ==number(bound_row['new_target_amount']['amount'])
                and projected[role]['target_amount'].get('currency')=='TWD'
                and bound_row['new_target_amount'].get('currency')=='TWD','TARGET_RECALCULATION_MISMATCH')
            line['original_document_target_amount']=deepcopy(line['target_amount'])
            line['target_amount']={'value_state':'KNOWN','amount':format(amount.normalize(),'f'),'currency':'TWD',
                'source_reference':source['pool_source']['source_reference'],
                'source_sha256':source['pool_source']['sha256'],'source_role':role,
                'source_available_at':available,'scope':'DATED_REPORTED_ASSET_VALUATION__NOT_SETTLED_CASH'}
            weight_sum+=weight;target_sum+=amount
        require(weight_sum==1 and target_sum==total,'TARGET_SUM_MISMATCH')
    draft=view['payload']['draft']
    draft['denominator']={'value_state':'KNOWN','amount':str(total),'currency':'TWD','scope':pool['scope'],
        'source_available_at':available,'valuation_date':pool['taiwan_securities']['source_time'],
        'fx_as_of':pool['rate_time'],'current_nav_qualified':False,'settlement_qualified':False,
        'unreported_cash_in_scope':False}
    draft['source_mapping_lineage']={'operation':OPERATION,'approval_unchanged':True,
        'original_target_view_digest':digest(pack['target']),'original_target_hash':pack['target']['target_hash'],
        'document_sha256':proof['source_sha256'],'pool_source_sha256':source['pool_source']['sha256'],
        'intake_sha256':source['intake_source']['sha256'],'source_db_sha256':snapshot['source_sha256']}
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    view['payload']['target_hash']=view['target_hash']=draft['draft_hash'];view['weight_denominator']='1'
    proof['dated_pool_binding']={'source_descriptor':deepcopy(descriptor),'document_inputs':deepcopy(document_inputs),
        'source_db_sha256':snapshot['source_sha256'],'snapshot_digest':snapshot['payload_digest'],
        'source_available_at':available,'scope':pool['scope'],'approval_created':False}
    proof['target_view_digest']=digest(view)
    return {'target':view,'trusted_approved_target_source':proof,'trade_authorization':'NONE','database_written':False}


def is_dated(view,proof=None):
    return bool((proof or {}).get('dated_pool_binding') or
        (view.get('payload',{}).get('draft',{}).get('source_mapping_lineage') or {}).get('operation')==OPERATION)


def replay(view,proof,*,evaluation_at=None,snapshot=None):
    """Rebuild from the original document and pool, even if hashes were re-pasted."""
    from approved_target_input import build_approved_target_view
    bound=proof.get('dated_pool_binding') or {};require(bool(bound),'REPLAY_PROOF_REQUIRED')
    at=evaluation_at or bound['source_available_at']
    base=build_approved_target_view(**bound['document_inputs'])
    expected=project(base,bound['source_descriptor'],bound['document_inputs'],at)
    require(expected['target']==view and expected['trusted_approved_target_source']==proof,'SOURCE_REPLAY_MISMATCH')
    if snapshot is not None:
        require(snapshot.get('client_id')==proof['client_id']
            and snapshot.get('source_sha256')==bound['source_db_sha256']
            and snapshot.get('payload_digest')==bound['snapshot_digest'],'CURRENT_MEMBER_SNAPSHOT_MISMATCH')
    return deepcopy(view),deepcopy(proof)


def bind_producer_seed(configuration,request,normalized=None):
    """Carry the current replayed money proof into the original producer seed."""
    from approved_target_input import build_approved_target_view
    cfg=deepcopy(configuration);ctx=cfg['context_seed'];prior=cfg['request_seed']['confirmed_target']
    document=(normalized or {}).get('original_target_sources',{}).get('document_target') or {}
    if document.get('dated_pool_source') is not None:
        args=deepcopy(document);expected=args.pop('sha256')
        require(sha256(Path(args['source_path']).read_bytes()).hexdigest()==expected,'DOCUMENT_BYTES_CHANGED')
        pack=build_approved_target_view(**args,evaluation_at=request['evaluation_at'])
        view,proof=pack['target'],pack['trusted_approved_target_source']
        replay(view,proof,evaluation_at=request['evaluation_at'],snapshot=request['client_snapshot']['payload'])
    else:
        proof=ctx.get('approved_document_target_source') or {}
        require(bool(proof.get('dated_pool_binding')),'PRODUCER_REPLAY_SOURCE_REQUIRED')
        view,proof=replay(request['confirmed_target'],proof,evaluation_at=request['evaluation_at'],
            snapshot=request['client_snapshot']['payload'])
    require(view==request['confirmed_target'],'PRODUCER_TARGET_REPLAY_MISMATCH')
    old_proof=ctx.get('approved_document_target_source') or {}
    old_signature=approval_signature(prior);current_signature=approval_signature(view)
    # A bootstrap can retain an older capture of the same document. Its
    # content-derived IDs/availability are history, not authority to replace
    # the current replayed source. Check the original bytes and require the
    # same document, version, allocation and exact instrument/weight rows.
    require(old_proof.get('schema_version')=='Family.W5.ApprovedDocumentTargetSource.v1'
        and old_proof.get('client_id')==request['client_id']
        and prior.get('source_kind')=='EXISTING_APPROVED_DOCUMENT'
        and prior['payload']['draft']['identity'].get('client_id')==request['client_id']
        and old_proof.get('source_reference')==proof['source_reference']
        and old_proof.get('target_view_digest')==digest(prior)
        and sha256(Path(old_proof['local_source_path']).read_bytes()).hexdigest()==old_proof.get('source_sha256')
        and time(old_proof['source_available_at'])<=time(request['evaluation_at'])
        and all(old_signature[k]==current_signature[k] for k in
            ('target_version','status','source_reference_ids','allocation_version','lines')),
        'PRODUCER_APPROVAL_CHANGED')
    cfg['request_seed']['confirmed_target']=deepcopy(view)
    ctx['approved_document_target_source']=deepcopy(proof);ctx['target_hash']=view['target_hash']
    if ctx.get('approved_document_account_scope'):
        ctx['approved_document_account_scope']['source']=deepcopy(proof)
    return cfg,{'target_view_digest':proof['target_view_digest'],
        'pool_binding':deepcopy(proof['dated_pool_binding']),'approval_created':False,
        'historical_seed_source':{'proof':deepcopy(old_proof),'target_hash':prior['target_hash'],
            'confirmation_run_id':prior['confirmation_run_id'],
            'confirmation_evidence':deepcopy(prior['payload']['confirmation_evidence'])},
        'historical_bootstrap_money_substituted':False}
