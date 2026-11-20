"""Replay an explicit, account-bound owner ETF lookthrough decision.

This adds source-backed analysis policy to an unchanged allocation. It does
not approve a whole ETF, change its target or grant funding/trading authority.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import io,json,re,sqlite3,zipfile,xml.etree.ElementTree as ET
from family_input import digest
from member_market_source import time

QUOTE='照原配置，沒有額外上限'


def checked(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('OWNER_ETF_DECISION_SOURCE_CHANGED')
    return raw


def read(snapshot,config,evaluation_at):
    descriptor=config.get('owner_etf_constraints_source')
    if descriptor is None:return None
    data=json.loads(checked(descriptor));client=snapshot['client_id']
    if (data.get('schema_version')!='Family.W8.OwnerETFConstraintsSource.v1'
        or data.get('client_id')!=client or data.get('source_db_sha256')!=snapshot['source_sha256']
        or data.get('trade_authorization')!='NONE' or not data.get('authority_reference')):
        raise PermissionError('OWNER_ETF_DECISION_IDENTITY_OR_AUTHORITY')
    receipt=json.loads(checked(data['registration_receipt']))
    raw=checked(data['original_document'])
    if (receipt.get('schema_version')!='Family.W8.RegisteredDocumentCapture.v1'
        or receipt.get('file_id')!=data.get('document_file_id')
        or receipt.get('source_sha256')!=data['original_document']['sha256']
        or not receipt.get('revision_id') or not receipt.get('modified_at')
        or not data['authority_reference'].startswith('https://docs.google.com/document/d/'+receipt['file_id']+'/')):
        raise PermissionError('OWNER_ETF_DECISION_REGISTRATION_PROOF')
    registered=time(receipt['modified_at'])
    if (time(receipt['captured_at'])<registered
        or time(receipt['revision_modified_at'])>registered):
        raise PermissionError('OWNER_ETF_DECISION_REGISTRATION_TIME')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml=ET.fromstring(z.read('word/document.xml'))
    paragraphs=[''.join(p.itertext()) for p in xml.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
    found=[p for p in paragraphs if p.startswith(data['source_section']+'｜')]
    if len(found)!=1:raise PermissionError('OWNER_ETF_DECISION_SECTION_AMBIGUOUS')
    match=re.match(r'^指揮官原文「'+re.escape(QUOTE)+r'」。只適用 ([^。]+?) 的 ([A-Z0-9、,. -]+)。',
        found[0][len(data['source_section'])+1:])
    if match is None or match[1]!=data.get('member'):
        raise PermissionError('OWNER_ETF_DECISION_EXPLICIT_CLAUSE_REQUIRED')
    symbols=re.split(r'[、,\s]+',match[2].strip())
    if (not symbols or len(set(symbols))!=len(symbols) or symbols!=data.get('symbols')
        or any(not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*',s) for s in symbols)):
        raise PermissionError('OWNER_ETF_DECISION_SYMBOL_SCOPE')
    day=datetime.strptime(data['source_section'][:10],'%Y/%m/%d').replace(tzinfo=ZoneInfo('Asia/Taipei'))
    available=max(registered,day)
    # The retained Drive revision supplies a known-at bound. Later transport
    # capture is not an invented earlier owner signing or market timestamp.
    if time(evaluation_at)<available:return None
    db=Path(config['member_db_path']);before=sha256(db.read_bytes()).hexdigest()
    if before!=snapshot['source_sha256']:raise PermissionError('OWNER_ETF_DECISION_DB_CHANGED')
    scope=data['account_scope']
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        identities=[dict(r) for r in conn.execute('SELECT client_id,family_alias FROM family_member_identity')]
        accounts=[dict(r) for r in conn.execute('SELECT * FROM portfolio_account WHERE account_key=? AND client_id=?',
            (scope['account_key'],client))]
    if (identities!=[{'client_id':client,'family_alias':data['member']}]
        or len(accounts)!=1 or accounts[0]!=scope.get('original_account_row')
        or sha256(db.read_bytes()).hexdigest()!=before):
        raise PermissionError('OWNER_ETF_DECISION_ACCOUNT_MISMATCH')
    from official_holdings_source import project_official_holdings
    holdings=project_official_holdings(snapshot,evaluation_at=evaluation_at)
    positions=holdings['analysis_security_positions']+holdings['ledger_only_positions']
    for symbol in symbols:
        owners={p['account_key'] for p in positions if p.get('symbol')==symbol and p.get('account_key')}
        if owners and owners!={scope['account_key']}:
            raise PermissionError('OWNER_ETF_DECISION_POSITION_ACCOUNT_MISMATCH')
    return {'client_id':client,'symbols':symbols,'account_key':scope['account_key'],
        'decision_quote':QUOTE,'available_at':available.isoformat(),
        'authority_reference':data['authority_reference'],'source_descriptor':deepcopy(descriptor),
        'original_document':deepcopy(data['original_document']),
        'registration_receipt':deepcopy(data['registration_receipt']),
        'member_db_path':str(db),'source_db_sha256':before,'trade_authorization':'NONE'}


def project(snapshot,config,evaluation_at,target):
    decision=read(snapshot,config,evaluation_at)
    if decision is None:return target
    if target.get('owner_etf_constraints_projection') is not None:
        raise PermissionError('OWNER_ETF_DECISION_DUPLICATE_PROJECTION')
    out=deepcopy(target);draft=out['payload']['draft']
    constraints=draft.setdefault('etf_constraints',{})
    for symbol in decision['symbols']:
        constraints[symbol]={**deepcopy(constraints.get(symbol) or {}),
            'client_id':snapshot['client_id'],'symbol':symbol,'account_key':decision['account_key'],
            'lookthrough_restrictions':'EXPLICIT_APPROVED_NONE',
            'authority_reference':decision['authority_reference'],
            'owner_decision_source':deepcopy(decision)}
    # Approval replay keeps the exact original target, including its hashes;
    # the derived analysis view gets its own coherent hash, not a new approval.
    if 'draft_hash' in draft:
        draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
        if 'target_hash' in out:out['target_hash']=draft['draft_hash']
        if 'target_hash' in out['payload']:out['payload']['target_hash']=draft['draft_hash']
    out['owner_etf_constraints_projection']={'original_target':deepcopy(target),
        'original_target_digest':digest(target),'decision':deepcopy(decision),
        'scope':'LOOKTHROUGH_POLICY_ONLY__ALLOCATION_AND_APPROVAL_UNCHANGED'}
    return out


def approval_target(target,snapshot,evaluation_at):
    projection=target.get('owner_etf_constraints_projection')
    if projection is None:return target
    original=projection['original_target'];decision=projection['decision']
    config={'owner_etf_constraints_source':decision['source_descriptor'],'member_db_path':decision['member_db_path']}
    if (digest(original)!=projection['original_target_digest']
        or project(snapshot,config,evaluation_at,original)!=target):
        raise PermissionError('OWNER_ETF_DECISION_PROJECTION_REPLAY_MISMATCH')
    return deepcopy(original)
