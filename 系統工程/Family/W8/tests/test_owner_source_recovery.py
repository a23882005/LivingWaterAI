"""Synthetic original-row binding and corrected-quantity acceptance boundaries."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from owner_target_decision_source import project,read_decision
from official_holdings_source import project_official_holdings


def decision_case(tmp_path):
    client='SYNTHETIC_MEMBER';row=dict(client_id=client,field_key='funding_goal',value_state='KNOWN',
        value_text='2026/10/31本人正式確認目標標的變更：排除OLD；新增NEW及NEXT。比例尚未指定。本次沒有調整其他既有比例。',
        source_kind='OWNER_VERIFIED',source_reference='SYNTHETIC_ORIGINAL_CONVERSATION',
        recorded_at_utc='2026-10-30T00:00:00Z',updated_at_utc='2026-10-31T00:00:00Z')
    db=tmp_path/'original.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE family_member_identity(client_id TEXT)');c.execute('INSERT INTO family_member_identity VALUES(?)',(client,))
        c.execute('CREATE TABLE personal_profile_attribute('+','.join(k+' TEXT' for k in row)+')')
        c.execute('INSERT INTO personal_profile_attribute VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
    snap=dict(client_id=client,source_sha256=sha256(db.read_bytes()).hexdigest())
    raw=dict(schema='Family.PM.OwnerDecisionEvidence.v1',client_id=client,source_db_sha256=snap['source_sha256'],
        original_table='personal_profile_attribute',original_row=row,trade_authorization='NONE',
        PM_projection=dict(excluded=['OLD'],included_weight_pending=['NEW','NEXT'],existing_other_weights='UNCHANGED'))
    path=tmp_path/'source.json';path.write_text(json.dumps(raw,ensure_ascii=False))
    config=dict(member_db_path=str(db),owner_target_decision_source=dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),retrieved_at='2026-11-01T00:00:00Z'))
    lines=[dict(instrument_id=s,ticker=s,asset_type='ETF',weight=dict(value_state='KNOWN',value=w),
        target_amount=dict(value_state='KNOWN',amount='100',currency='USD')) for s,w in [('KEEP','0.8'),('OLD','0.2')]]
    target=dict(target_version=3,payload=dict(draft=dict(target_lines=lines,denominator=dict(value_state='KNOWN',amount='500',currency='USD'))))
    return snap,config,target,raw


def test_same_original_decision_excludes_old_and_keeps_unassigned_weights_unknown(tmp_path):
    snap,cfg,target,_=decision_case(tmp_path);before=deepcopy(target)
    out=project(snap,cfg,'2026-11-02T00:00:00Z',target)
    assert target==before and out['historical_target']==before
    rows={r['ticker']:r for r in out['payload']['draft']['target_lines']}
    assert set(rows)=={'KEEP','NEW','NEXT'} and rows['KEEP']['weight']['value']=='0.8'
    assert all(rows[s]['weight']['value'] is None for s in ('NEW','NEXT'))
    assert not out['complete_allocation'] and not out['approval_created']
    assert out['payload']['draft']['denominator']['value_state']=='UNKNOWN'
    assert out['owner_selection_decision']['additional_contribution_amount'] is None
    assert project(snap,{},'2026-11-02T00:00:00Z',target)==target


@pytest.mark.parametrize('issue',['cross_member','changed_bytes','changed_original_row','invented_selection','source_future','row_future','not_owner','wrong_db'])
def test_decision_source_rejects_identity_tampering_and_future_evidence(tmp_path,issue):
    snap,cfg,target,raw=decision_case(tmp_path);source=cfg['owner_target_decision_source'];path=Path(source['local_path'])
    if issue=='cross_member':raw['client_id']='SYNTHETIC_OTHER'
    elif issue=='changed_bytes':path.write_text('{}')
    elif issue=='changed_original_row':raw['original_row']['source_reference']='SYNTHETIC_REWRITTEN'
    elif issue=='invented_selection':raw['PM_projection']['included_weight_pending']=['UNAPPROVED']
    elif issue=='source_future':source['retrieved_at']='2026-12-01T00:00:00Z'
    elif issue=='row_future':raw['original_row']['updated_at_utc']='2026-12-01T00:00:00Z'
    elif issue=='not_owner':raw['original_row']['source_kind']='ASSISTANT'
    elif issue=='wrong_db':snap['source_sha256']='0'*64
    if issue!='changed_bytes':path.write_text(json.dumps(raw));source['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises((PermissionError,ValueError)):project(snap,cfg,'2026-11-02T00:00:00Z',target)


def corrected_snapshot():
    client='SYNTHETIC_MEMBER';at='2026-10-26T01:00:00Z';ref='SYNTHETIC_OWNER_CORRECTION'
    instrument=dict(client_id=client,instrument_key='POSITION_NEW',ticker='TEST',instrument_type='ETF',quote_currency='USD',exchange_code='US')
    position=dict(client_id=client,account_key='ACCOUNT_A',instrument_key='POSITION_NEW',quantity_decimal='3',
        as_of_utc=at,position_source_reference=ref)
    run=dict(client_id=client,run_id='CORRECTION',run_state='SEALED',source_kind='USER_PROVIDED',as_of_utc=at,version_no=2)
    items=[dict(client_id=client,run_id='CORRECTION',domain_code='HOLDING',entity_key='TEST',field_key=k,
        value_state='KNOWN',value_text=v,source_observed_at_utc=at,source_reference=ref)
        for k,v in [('record_basis','OWNER_CONFIRMED_QUANTITY_CORRECTION'),('quantity','3'),('broker','SYNTHETIC_BROKER')]]
    oldrun={**run,'run_id':'OLD_VALUE','as_of_utc':'2026-10-25T00:00:00Z','version_no':1}
    items.append(dict(client_id=client,run_id='OLD_VALUE',domain_code='USER_CONFIRMED_REAL_HOLDING_VALUE',
        entity_key='TEST',field_key='asset_label',value_state='KNOWN',value_text='TEST'))
    tables=dict(portfolio_instrument=[instrument,{**instrument,'instrument_key':'TARGET_OLD','exchange_code':None}],
        portfolio_position=[position],portfolio_snapshot_run=[oldrun,run],portfolio_snapshot_item=items)
    return dict(client_id=client,source_sha256='a'*64,tables=tables,payload_digest=digest(tables))


def test_owner_quantity_uses_explicit_account_key_and_keeps_reported_value_as_history():
    snap=corrected_snapshot();before=deepcopy(snap)
    out=project_official_holdings(snap,evaluation_at='2026-11-02T00:00:00Z')
    assert snap==before and len(out['analysis_security_positions'])==1
    row=out['analysis_security_positions'][0]
    assert row['quantity']=='3' and row['account_key']=='ACCOUNT_A' and row['instrument_key']=='POSITION_NEW'
    assert row['broker_label']=='SYNTHETIC_BROKER' and not row['settlement_asserted']
    assert len(out['historical_reported_holding_values'])==1 and not out['ledger_only_positions']


def test_another_account_same_instrument_is_not_erased_by_owner_correction():
    snap=corrected_snapshot();position={**snap['tables']['portfolio_position'][0],
        'account_key':'ACCOUNT_B','quantity_decimal':'7','position_source_reference':'SYNTHETIC_OTHER_ACCOUNT'}
    snap['tables']['portfolio_position'].append(position);snap['payload_digest']=digest(snap['tables'])
    out=project_official_holdings(snap,evaluation_at='2026-11-02T00:00:00Z')
    assert len(out['ledger_only_positions'])==1 and out['ledger_only_positions'][0]['account_key']=='ACCOUNT_B'


@pytest.mark.parametrize('issue',['quantity_mismatch','reference_mismatch','foreign_client','duplicate_position'])
def test_correction_requires_original_position_binding(tmp_path,issue):
    snap=corrected_snapshot();row=snap['tables']['portfolio_position'][0]
    if issue=='quantity_mismatch':row['quantity_decimal']='4'
    elif issue=='reference_mismatch':row['position_source_reference']='SYNTHETIC_OTHER'
    elif issue=='foreign_client':row['client_id']='SYNTHETIC_OTHER'
    else:snap['tables']['portfolio_position'].append(deepcopy(row))
    snap['payload_digest']=digest(snap['tables'])
    with pytest.raises((ValueError,PermissionError)):project_official_holdings(snap,evaluation_at='2026-11-02T00:00:00Z')
