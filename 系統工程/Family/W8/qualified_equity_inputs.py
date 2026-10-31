"""Replay qualified equity history, identity, calendar and acquisition receipts.

Only market and technical-sample facts are supplied. These sources cannot
establish valuation legality, safety, event coverage, orders or funding.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from zoneinfo import ZoneInfo
import json
from family_input import digest
from technical_source_bridge import read_history,build_partial_technical,VERSION
from v75_market_contract import VENUES


def time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00').replace(' UTC','+00:00'))
    if at.utcoffset() is None:raise ValueError('EQUITY_SOURCE_TIMEZONE_REQUIRED')
    return at


def checked(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('EQUITY_SOURCE_BYTES_CHANGED')
    return raw


def item(symbol,source,evaluation_at,root):
    if symbol not in ('VT','QQQ'):raise ValueError('EQUITY_QUALIFIED_ROUTE_NOT_IMPLEMENTED')
    raw=checked(source);qualified=json.loads(raw);at=time(evaluation_at)
    if (qualified.get('schema_version')!='Family.W8.EquitySourceQualification.v1'
        or qualified.get('symbol')!=symbol or time(qualified['source_evaluation_at'])>at):
        raise PermissionError('EQUITY_QUALIFICATION_IDENTITY_OR_TIME')
    artifacts=qualified['source_artifacts'];yahoo=artifacts['yahoo'];history_raw=checked(yahoo)
    receipt_raw=Path(yahoo['receipt_path']).read_bytes()
    if sha256(receipt_raw).hexdigest()!=yahoo['receipt_sha256']:
        raise PermissionError('EQUITY_SOURCE_RECEIPT_CHANGED')
    receipt=json.loads(receipt_raw);url=urlparse(receipt['url'])
    if (receipt['http_status']!=200 or receipt['sha256']!=yahoo['sha256']
        or url.scheme!='https' or url.netloc!='query1.finance.yahoo.com'
        or url.path!='/v8/finance/chart/'+symbol
        or parse_qs(url.query)!={'range':['5y'],'interval':['1d'],'events':['div,splits']}
        or not time(receipt['requested_at'])<=time(receipt['available_at'])
            <=time(receipt['artifact_written_at'])<=time(qualified['source_evaluation_at'])<=at):
        raise PermissionError('EQUITY_SOURCE_RECEIPT_BINDING_OR_TIME')
    chart=json.loads(history_raw,parse_float=Decimal)['chart']
    if chart.get('error') or len(chart.get('result') or [])!=1:
        raise ValueError('EQUITY_SOURCE_CHART_REQUIRED')
    data=chart['result'][0];meta=data['meta']
    if (meta.get('symbol')!=symbol or meta.get('currency')!='USD'
        or meta.get('instrumentType')!='ETF' or meta.get('dataGranularity')!='1d'):
        raise PermissionError('EQUITY_SOURCE_MARKET_IDENTITY_MISMATCH')
    identity=json.loads(checked(artifacts['ibkr_identity']))
    if 'response' in identity:identity=identity['response']
    if identity.get('isError'):raise ValueError('EQUITY_CONTRACT_SOURCE_UNAVAILABLE')
    matches=[r for r in identity['structuredContent']['results'] if r.get('symbol')==symbol
        and r.get('country_code')=='US' and r.get('exchange')==VENUES.get(meta['exchangeName'])
        and any(s.get('security_type')=='STK' for s in r.get('sections',[]))]
    if len(matches)!=1 or matches[0]!=qualified['contract']:
        raise PermissionError('EQUITY_CONTRACT_AMBIGUOUS_OR_CHANGED')
    contract=matches[0];ibkr=json.loads(checked(artifacts['ibkr_history']))
    if (not isinstance(contract['underlying_contract_id'],int)
        or isinstance(contract['underlying_contract_id'],bool) or contract['underlying_contract_id']<=0):
        raise ValueError('EQUITY_CONTRACT_ID_REQUIRED')
    if not time(ibkr['requested_at'])<=time(ibkr['available_at'])<=time(qualified['source_evaluation_at']):
        raise PermissionError('EQUITY_IBKR_CAPTURE_TIME')
    expected_args={'contract_id':contract['underlying_contract_id'],'exchange':contract['exchange'],
        'security_type':'STK','outside_rth':False,'period':'FIVE_YEARS','step':'ONE_DAY',
        'include_corporate_actions':True}
    actions=ibkr['response'].get('structuredContent',{}).get('corp_actions')
    if (ibkr.get('args')!=expected_args or ibkr.get('contract')!=contract
        or ibkr['response'].get('isError') or not actions
        or any(r.get('type')!='CashDividends' for r in actions)
        or data.get('events',{}).get('splits')):
        raise PermissionError('EQUITY_PRICE_BASIS_OR_CORPORATE_ACTION_SOURCE')
    template=deepcopy(qualified['technical_source_template']);rows=read_history(template['csv_path'],template['sha256'])
    stamps=data['timestamp'];quote=data['indicators']['quote'][0]
    if any(len(quote[k])!=len(stamps) for k in ('open','high','low','close','volume')):
        raise ValueError('EQUITY_SOURCE_BAR_COVERAGE')
    zone=ZoneInfo('America/New_York');dates=[datetime.fromtimestamp(t,zone).date().isoformat() for t in stamps]
    if not dates or dates!=sorted(set(dates)):raise ValueError('EQUITY_SOURCE_SESSION_ORDER')
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start=dates[0],end=at.date()+timedelta(days=7))
    expected=[];receipts=[];excluded=[]
    for i,day in enumerate(dates):
        opening=cal.session_open(day).to_pydatetime();closing=cal.session_close(day).to_pydatetime()
        if datetime.fromtimestamp(stamps[i],opening.tzinfo)!=opening:
            raise ValueError('EQUITY_SOURCE_RTH_TIMESTAMP_MISMATCH')
        if closing>time(receipt['available_at']):
            excluded.append({'session':day,'reason':'RTH_SESSION_NOT_COMPLETE_AT_CAPTURE'});continue
        if any(quote[k][i] is None or isinstance(quote[k][i],bool) for k in ('open','high','low','close','volume')):
            raise ValueError('EQUITY_SOURCE_OHLCV_REQUIRED')
        values={k:Decimal(str(quote[key][i])) for k,key in
            [('Open','open'),('High','high'),('Low','low'),('Close','close'),('Volume','volume')]}
        if (any(not v.is_finite() for v in values.values())
            or min(values[k] for k in ('Open','High','Low','Close'))<=0
            or not values['Low']<=min(values['Open'],values['Close'])<=max(values['Open'],values['Close'])<=values['High']
            or values['Volume']<0 or values['Volume']!=values['Volume'].to_integral_value()):
            raise ValueError('EQUITY_SOURCE_INVALID_OHLCV')
        expected.append({'Date':day,**{k:str(v) for k,v in values.items()}})
        receipts.append({'session':day,'close_at':closing.isoformat(),'available_at':receipt['available_at'],
            'completed':True,'formal_close_available':True})
    sessions=[str(s.date()) for s in cal.sessions_in_range(expected[0]['Date'],expected[-1]['Date'])]
    if (rows!=expected or qualified['excluded_bars']!=excluded or qualified['rows']!=len(rows)
        or sessions!=[r['Date'] for r in rows]):raise PermissionError('EQUITY_HISTORY_RAW_OR_CALENDAR_MISMATCH')
    metadata=template['metadata']
    must={'asset_id':symbol,'symbol':symbol,'exchange':contract['exchange'],'currency':meta['currency'],
        'instrument_reference':'IBKR:'+str(contract['underlying_contract_id']),
        'source_reference':receipt['url'],'receipt_reference':'SHA256:'+sha256(receipt_raw).hexdigest(),
        'calendar_reference':'exchange_calendars@'+xc.__version__+':XNYS','session_timezone':'America/New_York',
        'provider_price_basis':'RAW_QUOTE_CLOSE_NOT_ADJ_CLOSE__NO_SPLIT_EVENTS_IN_WINDOW',
        'source_run':'READONLY_CAPTURE:'+receipt['sha256'],
        'producer_version':VERSION,'timeframe':'DAILY','price_field':'Close','auto_adjust':False,
        'split_basis_verified':True,'calendar_sessions':sessions,'bar_receipts':receipts,'history_digest':digest(rows),
        'evaluation_mode':'SNAPSHOT_AFTER_ACQUISITION','artifact_written_at':receipt['artifact_written_at'],
        'fetch_completed_at':receipt['available_at'],'data_provenance':'SOURCE_BACKED'}
    if any(metadata.get(k)!=v for k,v in must.items()):raise PermissionError('EQUITY_TECHNICAL_METADATA_MISMATCH')
    native=build_partial_technical(rows,metadata=metadata,evaluated_at=evaluation_at,repo_path=root)
    if native['sample_state']!='COMPLETE' or native['issue_codes']:
        raise ValueError('EQUITY_ORIGINAL_TECHNICAL_SAMPLE_UNAVAILABLE')
    completed=[s for s in cal.sessions_in_range(rows[-1]['Date'],str(at.astimezone(zone).date()))
        if cal.session_close(s).to_pydatetime()<=at]
    fresh=bool(completed) and str(completed[-1].date())==rows[-1]['Date']
    result={'symbol':symbol,'status':'FRESH' if fresh else 'STALE','contract':deepcopy(contract),
        'source_reference':receipt['url'],'source_sha256':yahoo['sha256'],'qualification_sha256':source['sha256'],
        'source_available_at':qualified['source_evaluation_at'],
        'raw_history_available_at':receipt['artifact_written_at'],'observed_date':rows[-1]['Date'],
        'session_close_at':receipts[-1]['close_at'],'rows':rows,'technical_source_template':template,
        'technical_sample_state':native['sample_state'],'formal_technical_producer_complete':False,
        'historical_publication_times_asserted':False,'full_equity_deployment_attestation':False}
    result['digest']=digest(result);return result


def read(source,evaluation_at,root):
    if source is None:return None
    if source.get('schema_version')!='Family.W8.QualifiedEquityManifestSource.v1':
        raise ValueError('EQUITY_MANIFEST_SOURCE_SCHEMA')
    raw=checked(source);manifest=json.loads(raw)
    if manifest.get('schema_version')!='Family.W8.EquitySourceQualificationManifest.v1':
        raise ValueError('EQUITY_MANIFEST_SCHEMA')
    result={'schema_version':'Family.W8.QualifiedEquityInputs.v1','manifest_sha256':source['sha256'],
        'items':{symbol:item(symbol,value,evaluation_at,root) for symbol,value in manifest['items'].items()}}
    result['digest']=digest(result);return result


def updates(row,pool,request,root,class_source,profile,prepared_positions=None):
    if pool is None or row['symbol'] not in pool['items']:return {}
    source=pool['items'][row['symbol']];symbol=row['symbol']
    if source['observed_date']<row['observed_date']:raise ValueError('EQUITY_QUALIFIED_SOURCE_OLDER_THAN_ANALYSIS')
    instruments=([p['source_instrument'] for p in prepared_positions
        if p['source_instrument'].get('ticker')==symbol] if prepared_positions is not None else
        [r for r in request['client_snapshot']['payload']['tables']['portfolio_instrument'] if r.get('ticker')==symbol])
    if (len(instruments)!=1 or instruments[0].get('quote_currency')!=source['technical_source_template']['metadata']['currency']
        or instruments[0].get('exchange_code') not in (None,'',source['contract']['exchange'])):
        raise PermissionError('EQUITY_PREPARED_INSTRUMENT_SOURCE_MISMATCH')
    rows=[{'Date':r['Date'],**{k:float(r[k]) for k in ('Open','High','Low','Close','Volume')},
        '_source_decimal':{k:r[k] for k in ('Open','High','Low','Close','Volume')}} for r in source['rows']]
    from on_demand_market_observations import evaluate_observed_history
    result=evaluate_observed_history(rows,repo_root=root,evaluation_at=request['evaluation_at'],macro=request['macro_snapshot'],
        asset_id=symbol,formal_rule_source=class_source,approved_rule_profile=profile,is_etf=True)
    binding={'symbol':symbol,'provider_symbol':symbol,
        'source_sha256':source['technical_source_template']['sha256'],'manifest_sha256':pool['manifest_sha256'],
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'observed_session':source['observed_date'],'evaluated_at':request['evaluation_at'],
        'provider_verified_at':source['source_available_at']}
    result['approved_technical']['source_binding']=binding
    for slots in result['observed_named_signals'].values():
        for slot in slots:
            slot['source_ids_and_digests']=deepcopy(binding);slot['numeric_context_reference']='approved_technical.numeric_decimal'
    return {**result,'qualified_equity_market_digest':source['digest'],
        'observed_date':source['observed_date'],'observed_close':float(source['rows'][-1]['Close']),'rows':len(rows),
        'source_path':source['technical_source_template']['csv_path'],'source_sha256':source['technical_source_template']['sha256'],
        'manifest_sha256':pool['manifest_sha256'],'provider_symbol':symbol,
        'provider':'Yahoo Finance raw quote OHLCV + IBKR contract/corporate-action cross-check',
        'analysis_identity_mapping':{'scope':'VERIFIED_MARKET_REFERENCE__HELD_VENUE_SOURCE_SEPARATE',
            'reference_exchange':source['contract']['exchange'],
            'quote_currency':source['technical_source_template']['metadata']['currency'],
            'reference_timezone':source['technical_source_template']['metadata']['session_timezone'],
            'source_url':source['source_reference'],'catalog_sha256':pool['manifest_sha256'],
            'contract_id':source['contract']['underlying_contract_id'],
            'provider_independent_attestation':True,'held_exchange_inferred':False},
        'provider_verified_at':source['source_available_at'],'provider_symbol_match_only':False,'formal_identity_verified':True,
        'alternative_source_receipt':None,'source_gaps':[],
        'history_quality':{'state':'ALL_COMPLETED_SESSIONS_VALIDATED','source_values_modified':False,
            'used_rows':len(rows),'source_history_digest':source['technical_source_template']['metadata']['history_digest']},
        'cache_validation':{'state':'VERIFIED_ORIGINAL_RAW_BYTES','invalid_bars_repaired':False},
        'call_trace':result['call_trace']+['W8.qualified_equity_inputs:identity/calendar/raw_OHLCV'],
        'formal_deployment_eligible':False}


def apply(observations,pool,request,root,class_source,profile,prepared_positions=None):
    if pool is None:return observations
    out=deepcopy(observations);out['qualified_equity_inputs']=deepcopy(pool)
    for row in out['assets']:row.update(updates(row,pool,request,root,class_source,profile,prepared_positions))
    return out


def validate(request,context,report,root,*,prepared_positions=None):
    descriptor=context.get('qualified_equity_source_manifest')
    if request.get('qualified_equity_source_digest')!=(digest(descriptor) if descriptor is not None else None):
        raise PermissionError('EQUITY_REQUEST_SOURCE_BINDING_MISMATCH')
    pool=read(descriptor,request['evaluation_at'],root)
    if report.get('qualified_equity_inputs')!=pool:raise PermissionError('EQUITY_POOL_REPLAY_MISMATCH')
    if pool is None:return
    from approved_v04_technical import load_profile
    profile=load_profile(Path(__file__).parent/'owner_approved_v10.json')
    for position in report['analysis_result']['positions']:
        market=position.get('market')
        if not market:continue
        expected=updates(market,pool,request,root,context['sgov_role_classification_source'],profile,prepared_positions)
        if any(market.get(k)!=v for k,v in expected.items() if k!='call_trace'):
            raise PermissionError('EQUITY_MARKET_REPLAY_MISMATCH')
