"""Read-only Family boundary. Callers supply separately trusted identity/version context."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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


def validate_target(target,client_id,evaluation_at):
    """Validate an existing W2-18 record; never create/confirm a target."""
    require(isinstance(target,dict),'TARGET_REQUIRED','confirmed_target','W2','DATA_UNAVAILABLE')
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


def bind_owner(snapshot,owner,evaluation_at):
    tables=snapshot['tables'];client=snapshot['client_id'];key=owner_key(owner)
    require(key[0]==client,'OWNER_CLIENT_MISMATCH','owner.client_id')
    account=one([r for r in tables['portfolio_account'] if r['account_key']==owner['account']], 'portfolio_account')
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


def position_view(snapshot,account,evaluation_at,completeness):
    """Never infer an empty portfolio from no rows. Completeness is caller evidence."""
    require(isinstance(completeness,dict) and completeness.get('state')=='COMPLETE' and nonempty(completeness.get('source_reference')),'HOLDINGS_COMPLETENESS_UNKNOWN','holdings_completeness','W1','DATA_UNAVAILABLE')
    require(completeness.get('snapshot_digest')==snapshot['payload_digest'] and completeness.get('account_key')==account and timestamp(completeness.get('as_of'),'holdings_completeness.as_of')<=evaluation_at,'HOLDINGS_SNAPSHOT_MISMATCH','holdings_completeness','W1')
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
    target=validate_target(req.get('confirmed_target'),req['client_id'],at)
    require(str(target['target_version'])==versions['target'] and target['target_hash']==ctx.get('target_hash'),'TARGET_VERSION_CONFLICT','confirmed_target','W2')
    owner=bind_owner(payload,req.get('owner',{}),at)
    positions=position_view(payload,req['owner']['account'],at,ctx.get('holdings_completeness'))
    macro=req.get('macro_snapshot',{})
    require(macro.get('digest')==digest(macro.get('payload'))==versions['market'],'MACRO_DIGEST_MISMATCH','macro_snapshot','W3')
    require(macro.get('asOf')==macro.get('payload',{}).get('asOf'),'MACRO_ASOF_MISMATCH','macro_snapshot.asOf','W3')
    require(timestamp(macro.get('asOf'),'macro_snapshot.asOf')<=at,'FUTURE_MACRO','macro_snapshot.asOf','W3')
    for k in ('source_path','source_commit','source_sha256','reader_sha256'):require(nonempty(macro.get(k)),'MACRO_SOURCE_REQUIRED','macro_snapshot.'+k,'W3')
    binding={'schema_version':'Family.W5.TargetBinding.v1','target_version':target['target_version'],'target_hash':target['target_hash'],
        'allocation_id':target['payload']['target_id'],'confirmation_run_id':target['confirmation_run_id'],'analysis_run_id':req['run_id'],
        'original_payload_digest':digest(target['payload'])}
    binding['binding_digest']=digest(binding)
    return PreparedInput(digest(req),{'request':req,'target_binding':binding,'owner_binding':owner,'positions':positions,'engine_calls':0,'trade_action':'NO_TRADE'})
