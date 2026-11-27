"""Replay account-bound ETF lookthrough and documented mandate scope.

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


def read_mandate_source(descriptor, evaluation_at):
    source = json.loads(checked(descriptor))
    if source.get('schema_version') != 'Family.W8.RegisteredMandateRevisions.v1':
        return source, None
    # A single pinned private source carries the unchanged approved document and
    # its dated interpretations. Replays see only revisions known at the cutoff.
    raw = source['approved_document_utf8'].encode('utf-8')
    available = {}
    for revision in source['revisions']:
        date = time(revision['available_at'])
        if date in available or sha256(raw).hexdigest() != revision['approved_document']['sha256']:
            raise ValueError('INVALID_REGISTERED_MANDATE_REVISION')
        available[date] = revision
    eligible = [date for date in available if date <= time(evaluation_at)]
    if not eligible:
        raise ValueError('NO_AVAILABLE_MANDATE_REVISION')
    return available[max(eligible)], raw


def mandate_scopes(target, decision, evaluation_at):
    """Consume a trusted interpretation of exact approved rows, independent of issuer facts."""
    descriptor = decision['source_descriptor'].get('mandate_source')
    if descriptor is None or target.get('source_kind') != 'EXISTING_APPROVED_DOCUMENT':
        return {}
    record = target['payload']
    draft = record['draft']
    confirmation = record.get('confirmation_evidence') or {}
    try:
        data, original_bytes = read_mandate_source(descriptor, evaluation_at)
        available = time(data['available_at'])
        approved_at = time(confirmation['confirmed_at'])
        document = data['approved_document']
        source_ref = document['source_reference']
        source_sha = document['sha256']
        if not (
            data['schema_version'] == 'Family.W8.OwnerETFMandateSource.v1'
            and data['trade_authorization'] == 'NONE'
            and data['work_order_reference']
            and data['client_id'] == decision['client_id'] == draft['identity']['client_id']
            and data['account_key'] == decision['account_key']
            and data['source_db_sha256'] == decision['source_db_sha256']
            and data['target_version'] == target['target_version']
            and data['allocation_version'] == draft['original_allocation_version']
            and record['status'] == 'APPROVED_DOCUMENT_VIEW'
            and confirmation['action'] == 'READ_EXISTING_APPROVAL'
            and digest(confirmation) == record['confirmation_evidence_hash']
            and record['source_reference_ids'] == confirmation['source_reference_ids'] == [source_ref]
            and target['confirmation_run_id'] == 'APPROVED-DOC-' + source_sha[:24]
            and draft['allocation_id'] == 'DOC-TARGET-' + digest({
                'client': decision['client_id'], 'source': source_sha,
                'version': data['allocation_version'],
            })[:24]
            and approved_at <= available <= time(evaluation_at)
            and isinstance(data['items'], dict)
        ):
            return {}
        if original_bytes is None:
            original_bytes = checked(document)
        document_lines = original_bytes.decode('utf-8').splitlines()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}

    scopes = {}
    for symbol, item in data['items'].items():
        if symbol not in decision['symbols'] or not isinstance(item, dict):
            continue
        lines = [line for line in draft['target_lines'] if line.get('ticker') == symbol]
        if len(lines) != 1:
            continue
        line = lines[0]
        original = item.get('original_document_row')
        if (not original or document_lines.count(original) != 1
                or original != line.get('original_document_row')
                or item.get('instrument_id') != line['instrument_id']
                or line.get('source_reference_ids') != [source_ref]):
            continue
        components = item.get('allowed_mandate_components')
        missing_clause = item.get('missing_approval_clause')
        if components is not None:
            if (not isinstance(components, list) or not components or missing_clause is not None
                    or not all(isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]*', value)
                               for value in components)
                    or len(set(components)) != len(components)):
                continue
        elif not isinstance(missing_clause, str) or not missing_clause.strip():
            continue
        evidence = {
            'source_reference': source_ref, 'document_sha256': source_sha,
            'document_line_number': document_lines.index(original) + 1,
            'original_document_row': original, 'instrument_id': line['instrument_id'],
            'target_version': target['target_version'], 'allocation_version': data['allocation_version'],
            'available_at': available.isoformat(), 'work_order_reference': data['work_order_reference'],
            'scope_source_sha256': descriptor['sha256'],
        }
        if 'product_basis' in item:
            evidence['product_basis'] = deepcopy(item['product_basis'])
        if missing_clause is not None:
            evidence['missing_approval_clause'] = missing_clause
        scopes[symbol] = {'mandate_scope_source': evidence}
        if components is not None:
            scopes[symbol]['allowed_mandate_components'] = list(components)
    return scopes


def project(snapshot,config,evaluation_at,target):
    decision=read(snapshot,config,evaluation_at)
    if decision is None:return target
    if target.get('owner_etf_constraints_projection') is not None:
        raise PermissionError('OWNER_ETF_DECISION_DUPLICATE_PROJECTION')
    mandates = mandate_scopes(target, decision, evaluation_at)
    out=deepcopy(target);draft=out['payload']['draft']
    constraints=draft.setdefault('etf_constraints',{})
    for symbol in decision['symbols']:
        constraints[symbol]={**deepcopy(constraints.get(symbol) or {}),
            'client_id':snapshot['client_id'],'symbol':symbol,'account_key':decision['account_key'],
            'lookthrough_restrictions':'EXPLICIT_APPROVED_NONE',
            'authority_reference':decision['authority_reference'],
            'owner_decision_source':deepcopy(decision)}
        if symbol in mandates and 'allowed_mandate_components' not in constraints[symbol]:
            constraints[symbol].update(mandates[symbol])
    # Approval replay keeps the exact original target, including its hashes;
    # the derived analysis view gets its own coherent hash, not a new approval.
    if 'draft_hash' in draft:
        draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
        if 'target_hash' in out:out['target_hash']=draft['draft_hash']
        if 'target_hash' in out['payload']:out['payload']['target_hash']=draft['draft_hash']
    out['owner_etf_constraints_projection']={'original_target':deepcopy(target),
        'original_target_digest':digest(target),'decision':deepcopy(decision),
        'scope':('ETF_CONSTRAINT_POLICY_ONLY__ALLOCATION_AND_APPROVAL_UNCHANGED' if mandates
                 else 'LOOKTHROUGH_POLICY_ONLY__ALLOCATION_AND_APPROVAL_UNCHANGED')}
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
