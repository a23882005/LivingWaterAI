"""Project a verified instrument-selection decision without allocating weights.

The evidence file must match the original row in the same immutable member DB.
Only the explicit selection clause is interpreted; numbers elsewhere never
authorize weights, a contribution, a cash balance or a complete target version.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

from family_input import digest
from member_market_source import time


def _symbols(text):
    rows=re.split(r'[、,，及與\s]+',text.strip())
    if not rows or len(rows)!=len(set(rows)) or any(not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*',s) for s in rows):
        raise ValueError('OWNER_TARGET_EXPLICIT_SYMBOL_LIST_REQUIRED')
    return rows


def read_decision(snapshot, config, evaluation_at):
    source=config.get('owner_target_decision_source')
    if source is None:return None
    path=Path(config['member_db_path']);expected=snapshot['source_sha256']
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256'] or sha256(path.read_bytes()).hexdigest()!=expected:
        raise PermissionError('OWNER_TARGET_SOURCE_BYTES_CHANGED')
    if time(source['retrieved_at'])>time(evaluation_at):raise PermissionError('OWNER_TARGET_SOURCE_FUTURE')
    data=json.loads(raw);client=snapshot['client_id'];row=data.get('original_row') or {}
    if (data.get('schema')!='Family.PM.OwnerDecisionEvidence.v1' or data.get('client_id')!=client
        or data.get('source_db_sha256')!=expected or data.get('original_table')!='personal_profile_attribute'
        or data.get('trade_authorization')!='NONE' or row.get('client_id')!=client
        or row.get('field_key')!='funding_goal' or row.get('value_state')!='KNOWN'
        or row.get('source_kind')!='OWNER_VERIFIED' or not row.get('source_reference')):
        raise PermissionError('OWNER_TARGET_ORIGINAL_ROW_IDENTITY_OR_AUTHORITY')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        identities=db.execute('SELECT client_id FROM family_member_identity').fetchall()
        originals=db.execute('SELECT * FROM personal_profile_attribute WHERE client_id=? AND field_key=?',
            (client,'funding_goal')).fetchall()
        if len(identities)!=1 or identities[0][0]!=client or len(originals)!=1 or dict(originals[0])!=row:
            raise PermissionError('OWNER_TARGET_ORIGINAL_DB_ROW_MISMATCH')
    if sha256(path.read_bytes()).hexdigest()!=expected:raise PermissionError('OWNER_TARGET_DB_CHANGED_DURING_READ')
    for key in ('recorded_at_utc','updated_at_utc'):
        if not row.get(key) or time(row[key])>time(evaluation_at):raise PermissionError('OWNER_TARGET_DECISION_FUTURE')
    text=row.get('value_text') or ''
    match=re.match(r'^(\d{4}/\d{2}/\d{2})本人正式確認目標標的變更[：:]排除([^；;。]+)[；;]新增([^。]+)。',text)
    if (match is None or '本次沒有調整' not in text or '比例' not in text or '尚未指定' not in text):
        raise ValueError('OWNER_TARGET_SUPPORTED_EXPLICIT_SELECTION_CLAUSE_REQUIRED')
    day=datetime.strptime(match[1],'%Y/%m/%d').date()
    if day>time(row['updated_at_utc']).date() or day>time(evaluation_at).date():
        raise PermissionError('OWNER_TARGET_DECISION_DATE_CONFLICT')
    excluded=_symbols(match[2]);included=_symbols(match[3]);projection=data.get('PM_projection') or {}
    if (set(excluded)&set(included) or projection.get('excluded')!=excluded
        or projection.get('included_weight_pending')!=included
        or projection.get('existing_other_weights')!='UNCHANGED'):
        raise PermissionError('OWNER_TARGET_PROJECTION_NOT_ORIGINAL_SELECTION')
    return {'schema_version':'Family.W8.OwnerInstrumentSelection.v1','client_id':client,
        'source_db_sha256':expected,'original_row':deepcopy(row),'original_row_digest':digest(row),
        'source_descriptor':deepcopy(source),'source_evidence_sha256':source['sha256'],
        'excluded':excluded,'included_weight_pending':included,'complete_allocation':False,
        'additional_contribution_amount':None,'additional_contribution_date':None,
        'other_weights_unchanged':True,'trade_authorization':'NONE'}


def project(snapshot, config, evaluation_at, historical_target):
    decision=read_decision(snapshot,config,evaluation_at)
    if decision is None:return historical_target
    historical=deepcopy(historical_target)
    original=historical.get('original_confirmation') or {}
    confirmed=original.get('confirmed_at_utc')
    if confirmed and time(confirmed)>time(decision['original_row']['updated_at_utc']):
        raise PermissionError('OWNER_TARGET_DECISION_SUPERSEDED_BY_LATER_APPROVAL')
    out=deepcopy(historical);draft=out['payload']['draft'];kept=[]
    existing={r.get('ticker'):r for r in draft['target_lines']}
    for row in draft['target_lines']:
        if row.get('ticker') not in decision['excluded'] and row.get('ticker') not in decision['included_weight_pending']:
            kept.append(deepcopy(row))
    for symbol in decision['included_weight_pending']:
        row=deepcopy(existing.get(symbol) or {})
        row.update(instrument_id=row.get('instrument_id') or 'OWNER_SELECTION:'+symbol,ticker=symbol,
            asset_type=row.get('asset_type') or 'UNKNOWN',
            selection_state='CONFIRMED_INSTRUMENT_WEIGHT_PENDING',
            weight={'value_state':'UNKNOWN','value':None,'reason':'OWNER_HAS_NOT_SPECIFIED_WEIGHT'},
            target_amount={'value_state':'UNKNOWN','amount':None,'currency':None,
                'reason':'OWNER_WEIGHT_AND_CURRENT_POOL_REQUIRED'})
        kept.append(row)
    draft['target_lines']=kept
    # An old denominator is history as well; no target money or portfolio NAV
    # is calculated from an incomplete current selection.
    if 'denominator' in draft:
        draft['historical_denominator']=deepcopy(draft['denominator'])
        draft['denominator']={'value_state':'UNKNOWN','amount':None,'currency':None,
            'reason':'CURRENT_COMPLETE_TARGET_AND_INVESTMENT_POOL_UNCONFIRMED'}
    out.update(source_kind='OWNER_SELECTED_TARGETS_PENDING_COMPLETE_WEIGHTS',
        complete_allocation=False,owner_selection_decision=decision,
        historical_target=historical,historical_target_digest=digest(historical),approval_created=False)
    return out
