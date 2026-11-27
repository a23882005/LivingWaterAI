"""Read the narrowly authorized Joseph/QQQ 2026-11-20 rule and cash sources."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,zipfile,io,xml.etree.ElementTree as ET
from family_input import digest
from member_market_source import time
from funding_guard import amount

RULE='FAMILY_PM_JOSEPH_QQQ_20261120'


def checked(descriptor):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('OWNER_QQQ_ORIGINAL_SOURCE_CHANGED')
    return raw


def read(descriptor,request,symbol):
    if descriptor is None:return None
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('V82_APPROVED_SOURCE_HASH_MISMATCH')
    data=json.loads(raw);policy=data.get('owner_qqq_scope')
    if policy is None:return None
    if (symbol!='QQQ' or data.get('schema_version')!='Family.W8.V82ApprovedSource.v1'
        or data.get('client_id')!=request['client_id'] or data.get('owner')!=request['owner']
        or data.get('asset_id')!=symbol or data.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
        or policy.get('rule_id')!=RULE or policy.get('member')!='Joseph'
        or request['owner'].get('broker')!='IBKR' or request['owner'].get('currency')!='USD'
        or request.get('trade_authorization')!='NONE'
        or policy.get('fund_structure')!='NOT_APPLICABLE' or policy.get('interest_futures')!='NOT_APPLICABLE'
        or not policy.get('isolated_test_ledger') or not data.get('source_reference')
        or time(request['evaluation_at'])<time('2026-11-20T00:00:00+08:00')
        or time(data['available_at'])>time(request['evaluation_at'])):
        raise PermissionError('OWNER_QQQ_RULE_SCOPE_OR_TIME_MISMATCH')
    doc=checked(policy['directive_source']);z=zipfile.ZipFile(io.BytesIO(doc))
    xml=ET.fromstring(z.read('word/document.xml'))
    text=''.join(xml.itertext())
    if not all(v in text for v in ('Joseph／QQQ 取消利率期貨依賴','利率期貨絕對不用',
        'Joseph／QQQ 取消基金結構門檻','Joseph／QQQ 已核准現金一次對帳完成')):
        raise PermissionError('OWNER_QQQ_DIRECTIVE_NOT_BOUND')
    cash=json.loads(checked(policy['cash_source']))
    if cash.get('schema')!='Family.PM.OwnerAvailableCashConfirmation.v1':
        raise PermissionError('OWNER_QQQ_CASH_SOURCE_SCHEMA')
    selected=[r for r in cash['accounts'] if r['member']=='Joseph']
    if len(selected)!=2 or {r['currency'] for r in selected}!={'USD','TWD'}:
        raise PermissionError('OWNER_QQQ_CASH_SOURCE_AMBIGUOUS')
    values={r['currency']:str(amount(r['owner_confirmed_available_cash'])) for r in selected}
    usd=next(r for r in selected if r['currency']=='USD')
    if usd.get('broker')!='Interactive Brokers':raise PermissionError('OWNER_QQQ_CASH_BROKER_MISMATCH')
    proof={'rule_id':RULE,'member':'Joseph','asset_id':symbol,
        **{k:deepcopy(request[k]) for k in ('client_id','run_id','evaluation_at','owner')},
        'source_db_sha256':data['source_db_sha256'],'source_descriptor':deepcopy(descriptor),
        'directive_source':deepcopy(policy['directive_source']),'cash_source':deepcopy(policy['cash_source']),
        'fund_structure':'NOT_APPLICABLE','interest_futures':'NOT_APPLICABLE',
        'stockq_reference':'https://m.stockq.org/bond/treasury.php',
        'cash_by_currency':values,'test_ledger_path':policy['isolated_test_ledger'],
        'test_ledger_write_authorized':True,'trade_authorization':'NONE'}
    proof['digest']=digest(proof);return proof


def runtime_rule(proof):
    if proof is None:return None
    return {k:deepcopy(proof[k]) for k in ('rule_id','asset_id','client_id','owner','source_db_sha256',
        'directive_source','source_descriptor','fund_structure','interest_futures')}
