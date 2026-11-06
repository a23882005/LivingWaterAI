"""Read hash-pinned PM source exports without promoting their qualifications.

The complete text export remains the original. JSON numbers retain their
source spellings; account observations cannot be used as public market data.
"""
from hashlib import sha256
from pathlib import Path
import json


def _pairs(items):
    out={}
    for key,value in items:
        if key in out:raise ValueError('PM_SOURCE_DUPLICATE_JSON_KEY')
        out[key]=value
    return out


def decode(text):
    decoder=json.JSONDecoder(parse_float=str,object_pairs_hook=_pairs,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('PM_SOURCE_NONFINITE_JSON')))
    return decoder.raw_decode(text)


def read(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('PM_SOURCE_ORIGINAL_BYTES_CHANGED')
    text=raw.decode('utf-8-sig')
    start=text.find('{')
    if start<0:raise ValueError('PM_SOURCE_JSON_REQUIRED')
    value,end=decode(text[start:])
    if not isinstance(value,dict):raise ValueError('PM_SOURCE_OBJECT_REQUIRED')
    return value,text[start+end:]


def history(source):
    """Select one exact original public-price response, never an account view."""
    from member_market_source import time
    root,tail=read(source);symbol=source['symbol']
    if root.get('schema')=='Family.PM.IBKR.PublicHistoricalBatch.v1':
        if tail.strip() or root.get('source_tool')!='IB.get_price_history':
            raise PermissionError('PM_HISTORY_ORIGINAL_FORMAT')
        rows=root.get('observations')
        if not isinstance(rows,list):raise ValueError('PM_HISTORY_OBSERVATIONS_REQUIRED')
        matches=[r for r in rows if r.get('ticker')==symbol]
        if len(matches)!=1:raise PermissionError('PM_HISTORY_EXACT_ASSET_REQUIRED')
        item=matches[0];query=root['query'];started=item['started_at'];retrieved=item['retrieved_at']
        contract=item['contract_id'];exchange=item['exchange'];data=item['source']
    elif root.get('schema')=='Family.PM.PublicVT5Y_IndependentSources.v1':
        marker='## IB Connector original parsed response (exact JSON serialization from tools)'
        if symbol!='VT' or tail.count(marker)!=1:raise PermissionError('PM_HISTORY_EXACT_ASSET_REQUIRED')
        queries=[r for r in root['original_requested_sources'] if r.get('tool')=='IB.get_price_history']
        if len(queries)!=1:raise PermissionError('PM_HISTORY_QUERY_REQUIRED')
        query=queries[0]['args'];contract=query['contract_id'];exchange='NYSE ARCA'
        section=tail.split(marker,1)[1].lstrip();data,end=decode(section)
        if not section[end:].lstrip().startswith('## Massive daily original returned CSV'):
            raise ValueError('PM_HISTORY_SECTION_BOUNDARY')
        started=None;retrieved=root['captured_at_utc']
    else:raise PermissionError('PM_HISTORY_PUBLIC_PRICE_DOCUMENT_REQUIRED')
    expected={'period':'FIVE_YEARS','step':'ONE_DAY','outside_rth':False,'include_corporate_actions':True}
    if (any(query.get(k)!=v or type(query.get(k)) is not type(v) for k,v in expected.items())
        or query.get('security_type','STK')!='STK' or type(contract) is not int or contract<=0
        or contract!=source.get('contract_id') or exchange!=source.get('provider_exchange')
        or retrieved!=source.get('retrieved_at') or started and time(started)>time(retrieved)):
        raise PermissionError('PM_HISTORY_QUERY_CONTRACT_OR_CAPTURE_MISMATCH')
    return data,dict(contract_id=contract,provider_exchange=exchange,query=query,
        started_at=started,retrieved_at=retrieved,original_document_sha256=source['sha256'],
        historical_publication_times_attested=False)


def account(source,available_at):
    from member_market_source import time
    root,tail=read(source)
    if (root.get('schema')!='Family.PM.IBKR.ReadOnlyObservation.v1' or tail.strip()
        or not root.get('client_scope','').startswith('Joseph ONLY;')
        or root.get('finance_eligibility')!='OBSERVED_NOT_CONFIRMED_FULL_FINANCE'
        or root.get('trading')!='NONE' or time(root['retrieved_at_utc'])>time(available_at)):
        raise PermissionError('PM_ACCOUNT_ORIGINAL_SCOPE_OR_TIME')
    expected={'get_account_balances','get_account_positions','get_account_summary',
        'get_account_orders(show_completed=true)','get_account_trades(DAYS_30)'}
    if set(root.get('source_tool_names',[]))!=expected:raise PermissionError('PM_ACCOUNT_ORIGINAL_METHODS_REQUIRED')
    calls={k:root[v] for k,v in [('balances','balances'),('positions','positions'),('summary','summary'),
        ('orders','orders'),('trades','recent_trades')]}
    if any(not isinstance(v,dict) for v in calls.values()):raise ValueError('PM_ACCOUNT_CALL_OBJECT_REQUIRED')
    return calls,root
