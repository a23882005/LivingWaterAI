"""Qualify explicit bond histories with independent contract and session proof.

Qualification covers a completed regular-session bond market snapshot. It
does not certify equity events, valuation/PIT history, settlement or orders.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from family_input import digest
from v75_remaining_inputs import time,number

VENUES={'NYQ':'NYSE','PCX':'ARCA','NMS':'NASDAQ','NGM':'NASDAQ','NCM':'NASDAQ'}


def qualify(pool,data,proofs,manifest,evaluation_at):
    sources=manifest.get('bond_market_identity_sources')
    if sources is None:return pool
    pool['qualified_bond_markets']={}
    for symbol,item in sources.items():
        key='YAHOO_'+symbol
        if symbol not in ('SGOV','SPSB') or key not in data:
            raise ValueError('V75_MARKET_SUPPORTED_SOURCE_REQUIRED')
        raw=Path(item['local_path']).read_bytes()
        if sha256(raw).hexdigest()!=item['sha256']:raise PermissionError('V75_MARKET_IDENTITY_BYTES_CHANGED')
        if (item.get('tool_name')!='search_contracts' or item.get('arguments')!={'query':symbol}
            or time(item['available_at'])>time(evaluation_at)):
            raise PermissionError('V75_MARKET_IDENTITY_METHOD_OR_TIME')
        response=json.loads(raw)
        if response.get('status')!='fulfilled' or response['value'].get('isError'):
            raise ValueError('V75_MARKET_IDENTITY_SOURCE_UNAVAILABLE')
        root=json.loads(data[key],parse_float=Decimal)['chart']['result'][0];meta=root['meta']
        matches=[r for r in response['value']['structuredContent']['results'] if
            r.get('symbol')==symbol and r.get('country_code')=='US'
            and r.get('exchange')==VENUES.get(meta.get('exchangeName'))
            and any(s.get('security_type')=='STK' for s in r.get('sections',[]))]
        if len(matches)!=1:raise ValueError('V75_MARKET_CONTRACT_AMBIGUOUS')
        contract=matches[0];cid=contract['underlying_contract_id']
        if not isinstance(cid,int) or isinstance(cid,bool) or cid<=0:
            raise ValueError('V75_MARKET_CONTRACT_ID_REQUIRED')
        # cash_yield_history already checked every Close timestamp against
        # XNYS. Check the remaining raw OHLCV fields without repairing bars.
        quote=root['indicators']['quote'][0];length=len(root['timestamp'])
        if any(len(quote[k])!=length for k in ('open','high','low','close','volume')):
            raise ValueError('V75_MARKET_BAR_LENGTH_CONFLICT')
        for i in range(length):
            o,h,l,c,v=[number(quote[k][i]) for k in ('open','high','low','close','volume')]
            if min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c) or v<0 or v!=v.to_integral_value():
                raise ValueError('V75_MARKET_INVALID_OHLCV')
        calculation=pool['calculations'][symbol+'.PRED-008']
        import exchange_calendars as xc
        at=time(evaluation_at);day=calculation['observed_date']
        cal=xc.get_calendar('XNYS',start=day,end=at.date()+timedelta(days=7))
        sessions=cal.sessions_in_range(day,str(at.astimezone(ZoneInfo('America/New_York')).date()))
        completed=[s for s in sessions if cal.session_close(s).to_pydatetime()<=at]
        latest=str(completed[-1].date()) if completed else None
        close_at=cal.session_close(day).to_pydatetime().isoformat()
        if time(proofs[key]['available_at'])<time(close_at):raise PermissionError('V75_MARKET_PRE_CLOSE_CAPTURE')
        state='FRESH' if latest==day else 'STALE'
        entry={'schema_version':'Family.W8.QualifiedBondMarket.v1','symbol':symbol,'currency':'USD',
            'status':state,'eligible':state=='FRESH','scope':'COMPLETED_RTH_BOND_MARKET_SNAPSHOT_ONLY',
            'contract_id':cid,'broker_exchange':contract['exchange'],'provider_exchange':meta['exchangeName'],
            'identity_source_sha256':item['sha256'],'identity_available_at':item['available_at'],
            'source_sha256':proofs[key]['source_sha256'],'source_reference':proofs[key]['source_reference'],
            'source_descriptor':deepcopy(manifest['sources'][key]),
            'source_available_at':proofs[key]['available_at'],'observed_date':day,'session_close_at':close_at,
            'last_completed_session_at_evaluation':latest,'close':calculation['unadjusted_close'],
            'price_field':'Close','adjustment':'NO_DIVIDEND_ADJUSTMENT__NO_SPLITS_IN_SOURCE',
            'calendar':deepcopy(calculation['calendar']),'all_ohlcv_bars_validated':length,
            'excluded_quote_bars':deepcopy(calculation['excluded_forming_or_quote_bars']),
            'equity_deployment_attestation':False,'historical_publication_times_asserted':False}
        entry['digest']=digest(entry);pool['qualified_bond_markets'][symbol]=entry
    pool['available_at']=max([pool['available_at']]+[v['available_at'] for v in sources.values()],key=time)
    return pool


def updates(row,pool,*,repo_root,evaluation_at,macro):
    contract=pool.get('qualified_bond_markets',{}).get(row['symbol'])
    if contract is None:return {}
    raw=Path(contract['source_descriptor']['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=contract['source_sha256']:raise PermissionError('V75_QUALIFIED_MARKET_BYTES_CHANGED')
    root=json.loads(raw,parse_float=Decimal)['chart']['result'][0];q=root['indicators']['quote'][0]
    rows=[];zone=ZoneInfo('America/New_York')
    for i,stamp in enumerate(root['timestamp']):
        moment=datetime.fromtimestamp(stamp,zone);day=moment.date().isoformat()
        if moment.isoformat() in contract['excluded_quote_bars']:continue
        if day>contract['observed_date']:continue
        rows.append({'Date':day,**{k:float(q[key][i]) for k,key in
            [('Open','open'),('High','high'),('Low','low'),('Close','close'),('Volume','volume')]}})
    from on_demand_market_observations import evaluate_observed_history
    result=evaluate_observed_history(rows,repo_root=repo_root,evaluation_at=evaluation_at,
        macro=macro,asset_id=row['symbol'],is_etf=True)
    technical=result['v75_original_predicates']['PRED-009']
    technical.update(input_freshness_verified=contract['eligible'],
        deployment_input_eligible=contract['eligible'] and technical['original_result']['assessment_status']=='VALID',
        market_contract_digest=contract['digest'])
    return {**result,'qualified_bond_market':deepcopy(contract),'observed_date':contract['observed_date'],
        'observed_close':float(Decimal(contract['close'])),'rows':len(rows),
        'source_path':contract['source_descriptor']['local_path'],'source_sha256':contract['source_sha256'],
        'manifest_sha256':pool['manifest_sha256'],'provider_symbol':row['symbol'],
        'provider':'Yahoo Finance chart / raw quote OHLCV + IBKR contract identity',
        'provider_verified_at':pool['available_at'],'provider_symbol_match_only':False,'formal_identity_verified':True,
        'alternative_source_receipt':None,'source_gaps':[],
        'history_quality':{'state':'ALL_COMPLETED_SESSIONS_VALIDATED','calendar':deepcopy(contract['calendar'])},
        'cache_validation':{'state':'VERIFIED_ORIGINAL_RAW_BYTES','invalid_bars_repaired':False},
        'call_trace':result['call_trace']+['W8.qualify_bond_market:identity/calendar/raw_OHLCV'],
        'formal_deployment_eligible':False}


def apply(observations,pool,*,repo_root,evaluation_at,macro):
    if not pool.get('qualified_bond_markets'):return deepcopy(observations)
    out=deepcopy(observations)
    for row in out['assets']:
        row.update(updates(row,pool,repo_root=repo_root,evaluation_at=evaluation_at,macro=macro))
    return out


def validate(request,context,report,root):
    pool=report.get('v75_macro_inputs') or {}
    if not pool.get('qualified_bond_markets'):return
    markets=[r['market'] for r in report['analysis_result']['positions'] if r.get('market')]
    markets+=list(report.get('bond_target_market_observations',{}).values())
    for row in markets:
        expected=updates(row,pool,repo_root=root,evaluation_at=request['evaluation_at'],macro=request['macro_snapshot'])
        if not expected:continue
        for key,value in expected.items():
            if key in ('call_trace','v75_original_predicates'):continue
            if row.get(key)!=value:raise PermissionError('V75_QUALIFIED_MARKET_REPLAY_MISMATCH:'+key)
        if row['v75_original_predicates']['PRED-009']!=expected['v75_original_predicates']['PRED-009']:
            raise PermissionError('V75_QUALIFIED_TECHNICAL_REPLAY_MISMATCH')
