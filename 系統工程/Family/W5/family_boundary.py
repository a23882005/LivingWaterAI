"""Read-only Family boundary. Callers supply separately trusted identity/version context."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import importlib.util
from family_input import digest
from funding_guard import amount, owner_key


class BoundaryError(ValueError):
    def __init__(self, code, field, producer='W5', status='BLOCKED'):
        super().__init__(code+':'+field)
        self.issue={'code':code,'field_path':field,'producer':producer,'message':code}
        self.status=status


def require(ok,code,field,producer='W5',status='BLOCKED'):
    if not ok:raise BoundaryError(code,field,producer,status)


def timestamp(value,field):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError()
        return dt
    except (ValueError,TypeError,AttributeError):
        raise BoundaryError('INVALID_TIMESTAMP',field,status='ERROR')


def one(rows,field):
    require(len(rows)==1,'SOURCE_ROW_MISSING_OR_AMBIGUOUS',field,'W1','DATA_UNAVAILABLE')
    return rows[0]


def nonempty(value):return isinstance(value,str) and bool(value.strip())


def validate_target(target,client_id,evaluation_at,*,approved_document_source=None,
                    official_target_source=None,snapshot=None):
    """Validate an existing W2 record or independently bound approved-document view.

    The document view records source availability, not a fictional signing event.
    Its independent trusted proof is required; the legacy W2 path is unchanged.
    """
    require(isinstance(target,dict),'TARGET_REQUIRED','confirmed_target','W2','DATA_UNAVAILABLE')
    if target.get('source_kind')=='OFFICIAL_W1_CONFIRMED_ALLOCATION':
        path=Path(__file__).resolve().parent.parent/'W8/official_target_input.py'
        spec=importlib.util.spec_from_file_location('family_w1_target_reader',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        require(isinstance(snapshot,dict) and snapshot.get('client_id')==client_id,
                'OFFICIAL_TARGET_CLIENT_MISMATCH','confirmed_target')
        return module.validate(target,official_target_source,snapshot,evaluation_at.isoformat())
    if target.get('source_kind')=='EXISTING_APPROVED_DOCUMENT':
        source=approved_document_source or {}
        require(source.get('schema_version')=='Family.W5.ApprovedDocumentTargetSource.v1'
                and source.get('client_id')==client_id and source.get('data_provenance')=='SOURCE_BACKED',
                'APPROVED_TARGET_TRUSTED_SOURCE_REQUIRED','approved_document_source')
        require(source.get('target_view_digest')==digest(target),
                'APPROVED_TARGET_VIEW_MISMATCH','confirmed_target')
        path=Path(source.get('local_source_path',''))
        require(path.is_absolute() and path.is_file(),
                'APPROVED_TARGET_SOURCE_FILE_REQUIRED','approved_document_source')
        require(sha256(path.read_bytes()).hexdigest()==source.get('source_sha256'),
                'APPROVED_TARGET_SOURCE_CHANGED','approved_document_source')
        require(timestamp(source.get('source_available_at'),'approved_target.available_at')<=evaluation_at,
                'APPROVED_TARGET_FUTURE_SOURCE','approved_document_source')
        record=target.get('payload',{});draft=record.get('draft',{})
        require(draft.get('identity',{}).get('client_id')==client_id,
                'TARGET_CLIENT_MISMATCH','confirmed_target')
        require(record.get('status')=='APPROVED_DOCUMENT_VIEW'
                and record.get('confirmation_evidence',{}).get('action')=='READ_EXISTING_APPROVAL',
                'APPROVED_TARGET_ORIGIN_REQUIRED','confirmed_target')
        require(target.get('target_hash')==record.get('target_hash')==draft.get('draft_hash')
                ==digest({k:v for k,v in draft.items() if k!='draft_hash'}),
                'TARGET_HASH_MISMATCH','confirmed_target')
        require(type(target.get('target_version')) is int and target['target_version']>0
                and record.get('version')==target['target_version'],
                'TARGET_VERSION_INVALID','confirmed_target')
        require(target.get('confirmation_run_id')==draft.get('identity',{}).get('run_id')
                and nonempty(target.get('confirmation_run_id')),
                'TARGET_CONFIRMATION_RUN_MISMATCH','confirmed_target')
        return deepcopy(target)
    record=target.get('payload')
    require(isinstance(record,dict),'TARGET_PAYLOAD_REQUIRED','confirmed_target.payload','W2')
    draft=record.get('draft',{});identity=draft.get('identity',{})
    require(identity.get('client_id')==client_id,'TARGET_CLIENT_MISMATCH','confirmed_target','W2')
    version=target.get('target_version')
    require(type(version) is int and version>0 and record.get('version')==version,'TARGET_VERSION_INVALID','confirmed_target.target_version','W2')
    require(record.get('status')=='CONFIRMED','TARGET_NOT_CONFIRMED','confirmed_target.payload.status','W2')
    original_hash=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    require(target.get('target_hash')==record.get('target_hash')==draft.get('draft_hash')==original_hash,'TARGET_HASH_MISMATCH','confirmed_target.target_hash','W2')
    require(nonempty(target.get('confirmation_run_id')) and target['confirmation_run_id']==identity.get('run_id'),'TARGET_CONFIRMATION_RUN_MISMATCH','confirmed_target.confirmation_run_id','W2')
    evidence=record.get('confirmation_evidence') or {}
    require(evidence.get('action')=='CONFIRM' and evidence.get('client_explicit_decision')=='TRUE' and evidence.get('confirmed_by')==client_id,'TARGET_CONFIRMATION_INVALID','confirmed_target.payload.confirmation_evidence','W2')
    require(digest(evidence)==record.get('confirmation_evidence_hash'),'TARGET_CONFIRMATION_HASH_MISMATCH','confirmed_target.payload.confirmation_evidence_hash','W2')
    require(bool(evidence.get('source_reference_ids')) and set(evidence['source_reference_ids']).issubset(set(record.get('source_reference_ids',[]))),'TARGET_CONFIRMATION_SOURCE_MISMATCH','confirmed_target.payload.source_reference_ids','W2')
    confirmed=timestamp(evidence.get('confirmed_at'),'target.confirmed_at')
    require(timestamp(record.get('proposed_at'),'target.proposed_at')<=confirmed<=timestamp(record.get('expires_at'),'target.expires_at') and confirmed<=evaluation_at,'TARGET_TIME_INVALID','confirmed_target','W2')
    # Expiry applies to signing a pending proposal. An already confirmed historical
    # target remains valid until the trusted latest target version changes.
    return deepcopy(target)


def bind_owner(snapshot,owner,evaluation_at,*,approved_account_scope=None):
    tables=snapshot['tables'];client=snapshot['client_id'];key=owner_key(owner)
    require(key[0]==client,'OWNER_CLIENT_MISMATCH','owner.client_id')
    account=one([r for r in tables['portfolio_account'] if r['account_key']==owner['account']], 'portfolio_account')
    if approved_account_scope is not None:
        scope=approved_account_scope;source=scope.get('source',{})
        require(scope.get('schema_version')=='Family.W5.DocumentAccountScope.v1'
                and scope.get('scope_kind')=='MEMBER_LOCAL_BROKER_CATEGORY_ANALYSIS_ONLY'
                and scope.get('trade_authorization')=='NONE'
                and scope.get('owner')==owner and scope.get('original_account_row')==account
                and scope.get('source_snapshot_digest')==snapshot['payload_digest'],
                'DOCUMENT_ACCOUNT_SCOPE_MISMATCH','approved_account_scope')
        require(source.get('client_id')==client and source.get('data_provenance')=='SOURCE_BACKED',
                'DOCUMENT_ACCOUNT_CLIENT_MISMATCH','approved_account_scope')
        path=Path(source.get('local_source_path',''))
        require(path.is_absolute() and path.is_file()
                and sha256(path.read_bytes()).hexdigest()==source.get('source_sha256'),
                'DOCUMENT_ACCOUNT_SOURCE_CHANGED','approved_account_scope')
        require(timestamp(source.get('source_available_at'),'account_source.available_at')<=evaluation_at,
                'DOCUMENT_ACCOUNT_FUTURE_SOURCE','approved_account_scope')
        return {'owner':deepcopy(owner),'w1_funding_purpose':'INVESTMENT_CANDIDATE',
                'source_rows':[deepcopy(account)],'approved_document_category_scope':deepcopy(scope),
                'cash_verified':False,'holdings_completeness_verified':False}
    require(account.get('account_state')=='KNOWN','ACCOUNT_UNKNOWN','portfolio_account.account_state','W1','DATA_UNAVAILABLE')
    own=one([r for r in tables['account_ownership'] if r['account_key']==owner['account']],'account_ownership')
    require(own.get('owner_client_id')==client and own.get('ownership_state')=='VERIFIED','ACCOUNT_OWNER_MISMATCH','account_ownership','W1')
    broker=one([r for r in tables['account_broker_link'] if r['account_key']==owner['account']],'account_broker_link')
    require(broker.get('broker_key')==owner['broker'] and broker.get('link_state')=='ACTIVE','BROKER_MISMATCH','account_broker_link','W1')
    domain=one([r for r in tables['funding_account_domain_link'] if r['account_key']==owner['account'] and r['currency_code']==owner['currency'] and r['funding_domain_key']==owner['funding_domain']],'funding_account_domain_link')
    require(domain.get('link_state')=='VERIFIED','FUNDING_DOMAIN_UNKNOWN','funding_account_domain_link','W1','DATA_UNAVAILABLE')
    purpose=one([r for r in tables['funding_domain'] if r['funding_domain_key']==owner['funding_domain']],'funding_domain')
    require(purpose.get('domain_state')=='ACTIVE' and purpose.get('purpose_code')=='INVESTMENT_CANDIDATE','FUNDING_DOMAIN_NOT_INVESTABLE','funding_domain','W1')
    for name,row in [('account',account),('ownership',own),('broker',broker),('domain',domain),('purpose',purpose)]:
        when=row.get('as_of_utc') or row.get('created_at_utc')
        require(timestamp(when,name+'.as_of')<=evaluation_at,'FUTURE_OWNER_EVIDENCE',name,'W1')
    return {'owner':deepcopy(owner),'w1_funding_purpose':purpose['purpose_code'],'source_rows':deepcopy([account,own,broker,domain,purpose])}


def position_view(snapshot,account,evaluation_at,completeness,*,approved_account_scope=None):
    """Never infer an empty portfolio from no rows. Completeness is caller evidence."""
    require(isinstance(completeness,dict) and completeness.get('state')=='COMPLETE' and nonempty(completeness.get('source_reference')),'HOLDINGS_COMPLETENESS_UNKNOWN','holdings_completeness','W1','DATA_UNAVAILABLE')
    require(completeness.get('snapshot_digest')==snapshot['payload_digest'] and completeness.get('account_key')==account and timestamp(completeness.get('as_of'),'holdings_completeness.as_of')<=evaluation_at,'HOLDINGS_SNAPSHOT_MISMATCH','holdings_completeness','W1')
    if (completeness.get('schema_version')=='Family.W8.OfficialHoldingsAcceptance.v1'
            and approved_account_scope is not None):
        from official_holdings_source import build_official_position_view
        try:
            projected=build_official_position_view(snapshot,account,evaluation_at,completeness,approved_account_scope)
        except (ValueError,PermissionError) as error:
            raise BoundaryError(str(error),'official_holdings_source',status='DATA_UNAVAILABLE') from None
        if projected is not None:return projected
    rows=snapshot['tables']['portfolio_position'];selected={}
    for row in rows:
        if row['account_key']!=account:continue
        when=timestamp(row['as_of_utc'],'portfolio_position.as_of_utc')
        if when>evaluation_at:continue
        instrument=row['instrument_key']
        if instrument not in selected or when>timestamp(selected[instrument]['as_of_utc'],'position.as_of'):
            selected[instrument]=row
    result=[]
    for instrument,row in sorted(selected.items()):
        instrument_row=one([r for r in snapshot['tables']['portfolio_instrument'] if r['instrument_key']==instrument],'portfolio_instrument')
        quantity=row.get('quantity_decimal')
        if quantity is not None:amount(quantity)
        result.append({'instrument_key':instrument,'quantity':quantity,'quantity_state':'KNOWN' if quantity is not None else 'UNKNOWN','source_position':deepcopy(row),'source_instrument':deepcopy(instrument_row)})
    return result


@dataclass(frozen=True)
class PreparedInput:
    input_digest: str
    payload: dict


def prepare_input(request,*,trusted_context):
    req=deepcopy(request);ctx=trusted_context
    require(req.get('schema_version')=='Family.W5.request.v1','REQUEST_SCHEMA_VERSION','schema_version',status='ERROR')
    for k in ('client_id','request_id','run_id'):require(nonempty(req.get(k)),'REQUIRED_FIELD',k,status='ERROR')
    require(req['client_id']==ctx.get('client_id'),'CLIENT_MISMATCH','client_id')
    require(req.get('analysis_permission')==ctx.get('analysis_permission')=='ANALYZE_ONLY','ANALYSIS_PERMISSION_REQUIRED','analysis_permission')
    require(req.get('trade_authorization')=='NONE','TRADE_AUTHORIZATION_INVALID','trade_authorization')
    at=timestamp(req.get('evaluation_at'),'evaluation_at')
    versions=req.get('expected_versions',{})
    require(all(nonempty(versions.get(k)) for k in ('target','funding','market','policy')),'VERSIONS_REQUIRED','expected_versions')
    require(versions==ctx.get('expected_versions'),'VERSION_CONFLICT','expected_versions')
    snap=req.get('client_snapshot',{});payload=snap.get('payload',{})
    require(payload.get('client_id')==req['client_id'],'SNAPSHOT_CLIENT_MISMATCH','client_snapshot','W1')
    require(nonempty(snap.get('snapshot_version')) and snap.get('snapshot_version')==ctx.get('snapshot_version'),'SNAPSHOT_VERSION_MISMATCH','client_snapshot.snapshot_version','W1')
    require(snap.get('digest')==digest(payload)==ctx.get('snapshot_digest'),'SNAPSHOT_DIGEST_MISMATCH','client_snapshot.digest','W1')
    require(payload.get('payload_digest')==digest(payload.get('tables')),'SNAPSHOT_TABLE_DIGEST_MISMATCH','client_snapshot.payload.tables','W1')
    require(timestamp(snap.get('as_of'),'client_snapshot.as_of')<=at,'FUTURE_SNAPSHOT','client_snapshot.as_of','W1')
    for table,rows in payload.get('tables',{}).items():
        require(isinstance(rows,list),'SNAPSHOT_TABLE_TYPE',table,'W1')
        for row in rows:
            if 'client_id' in row:require(row['client_id']==req['client_id'],'CROSS_CLIENT_ROW',table,'W1')
    target=validate_target(req.get('confirmed_target'),req['client_id'],at,
        approved_document_source=ctx.get('approved_document_target_source'),
        official_target_source=ctx.get('official_target_source'),snapshot=payload)
    require(str(target['target_version'])==versions['target'] and target['target_hash']==ctx.get('target_hash'),'TARGET_VERSION_CONFLICT','confirmed_target','W2')
    owner=bind_owner(payload,req.get('owner',{}),at,
        approved_account_scope=ctx.get('approved_document_account_scope'))
    positions=position_view(payload,req['owner']['account'],at,ctx.get('holdings_completeness'),
        approved_account_scope=ctx.get('approved_document_account_scope'))
    broker_source=None
    if ctx.get('broker_snapshot_source') is not None:
        require(req.get('broker_snapshot_source_digest')==digest(ctx['broker_snapshot_source']),
                'BROKER_SOURCE_BINDING_MISMATCH','broker_snapshot_source_digest')
        from broker_snapshot_source import read as read_broker,project_positions as broker_positions
        broker_source=read_broker(req,ctx['broker_snapshot_source'])
        positions=broker_positions(positions,broker_source)
    else:
        require(req.get('broker_snapshot_source_digest') is None,
                'TRUSTED_BROKER_SOURCE_REQUIRED','broker_snapshot_source_digest')
    macro=req.get('macro_snapshot',{})
    if macro.get('capture_receipt') is not None:
        require(digest(macro['capture_receipt'])==ctx.get('macro_capture_digest'),
            'MACRO_CAPTURE_BINDING_MISMATCH','macro_snapshot.capture_receipt','W3')
    selected=ctx.get('verified_macro_feed_source')
    if selected is not None:
        require(selected.get('schema_version')=='Family.W5.VerifiedMacroFeedSource.v1'
                and macro.get('source_sha256')==selected.get('sha256')
                and macro.get('capture_receipt',{}).get('source_selection_digest')==digest(selected),
                'MACRO_SOURCE_SELECTION_MISMATCH','macro_snapshot.source_selection','W3')
    require(macro.get('digest')==digest(macro.get('payload'))==versions['market'],'MACRO_DIGEST_MISMATCH','macro_snapshot','W3')
    require(macro.get('asOf')==macro.get('payload',{}).get('asOf'),'MACRO_ASOF_MISMATCH','macro_snapshot.asOf','W3')
    require(timestamp(macro.get('asOf'),'macro_snapshot.asOf')<=at,'FUTURE_MACRO','macro_snapshot.asOf','W3')
    for k in ('source_path','source_commit','source_sha256','reader_sha256'):require(nonempty(macro.get(k)),'MACRO_SOURCE_REQUIRED','macro_snapshot.'+k,'W3')
    allocation_id=target['payload']['draft'].get('allocation_id')
    require(nonempty(allocation_id),'TARGET_ALLOCATION_ID_REQUIRED','confirmed_target.payload.draft.allocation_id','W2')
    binding={'schema_version':'Family.W5.TargetBinding.v1','target_version':target['target_version'],'target_hash':target['target_hash'],
        'allocation_id':allocation_id,'target_record_id':target['payload']['target_id'],'confirmation_run_id':target['confirmation_run_id'],'analysis_run_id':req['run_id'],
        'original_payload_digest':digest(target['payload'])}
    binding['binding_digest']=digest(binding)
    result={'request':req,'target_binding':binding,'owner_binding':owner,'positions':positions,'engine_calls':0,'trade_action':'NO_TRADE'}
    if broker_source is not None:result['broker_snapshot_source']=broker_source
    return PreparedInput(digest(req),result)
