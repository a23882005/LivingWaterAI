"""Audit acquired raw history before it can become a native PV2 source.

Provider entitlement gaps, empty warning text and date-only declarations do
not become complete calendars, empty action books or historical PIT receipts.
No price substitution, adjusted-close wealth, qP/qV value or buy rule is made.
"""
from copy import deepcopy
from datetime import datetime,date,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from io import StringIO
import calendar,csv,json,re
from family_input import digest
from sec_publication_source import instant


def pinned(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('HISTORY_INTAKE_ORIGINAL_BYTES_CHANGED')
    return raw.decode('utf-8-sig')


def nonnegative(value,*,positive=False):
    if value is None or isinstance(value,bool):raise ValueError('HISTORY_INTAKE_ORIGINAL_NUMBER_REQUIRED')
    result=Decimal(str(value))
    if not result.is_finite() or result<0 or positive and result==0:raise ValueError('HISTORY_INTAKE_INVALID_NUMBER')
    return result


def table(text,required):
    if text.startswith('Warning ['):
        return None,text.strip()
    reader=csv.DictReader(StringIO(text))
    if not set(required)<=set(reader.fieldnames or []):raise ValueError('HISTORY_INTAKE_ORIGINAL_COLUMNS_REQUIRED')
    rows=list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('HISTORY_INTAKE_CSV_ROW_COVERAGE')
    return rows,None


def receipt_table(source, path, known_by):
    receipt = json.loads(pinned(source))
    if (receipt.get('path') != path
            or not instant(receipt['started_at']) <= instant(receipt['retrieved_at']) <= instant(known_by)
            or not isinstance(receipt.get('params'), dict) or not isinstance(receipt.get('provider_response'), str)):
        raise PermissionError('HISTORY_INTAKE_PROVIDER_RECEIPT_SCOPE_OR_TIME')
    return receipt


def price_bars(text, start, end):
    rows, warning = table(text, ('o','h','l','c','v','t'))
    bars=[];stamps=[];sessions=set()
    for row in rows or []:
        if not re.fullmatch(r'\d+',row['t']):raise ValueError('HISTORY_INTAKE_BAR_TIMESTAMP_REQUIRED')
        stamp=int(row['t']);session=datetime.fromtimestamp(stamp/1000,ZoneInfo('America/New_York')).date()
        if not start<=session<=end or session in sessions:raise ValueError('HISTORY_INTAKE_DUPLICATE_OR_OUTSIDE_SESSION')
        values={k:nonnegative(row[k],positive=k!='v') for k in ('o','h','l','c','v')}
        if values['l']>min(values['o'],values['c']) or values['h']<max(values['o'],values['c']):
            raise ValueError('HISTORY_INTAKE_ORIGINAL_OHLC_CONFLICT')
        stamps.append(stamp);sessions.add(session)
        bars.append({'session_id':str(session),'timestamp':stamp,'open':str(values['o']),'high':str(values['h']),
            'low':str(values['l']),'close':str(values['c']),'volume':str(values['v']),
            'available_at':None,'historical_PIT_verified':False})
    if stamps!=sorted(stamps):raise ValueError('HISTORY_INTAKE_BAR_ORDER')
    return bars, warning


def read_market(descriptor,symbol,evaluation_at):
    manifest=json.loads(pinned(descriptor))
    if (manifest.get('schema_version')!='Family.W8.HistoricalMarketIntake.v1'
        or manifest.get('symbol')!=symbol or manifest.get('provider')!='MASSIVE'
        or manifest.get('exchange_timezone')!='America/New_York'
        or instant(manifest['known_by'])>instant(evaluation_at)):
        raise PermissionError('HISTORY_INTAKE_SYMBOL_PROVIDER_OR_TIME_MISMATCH')
    start=date.fromisoformat(manifest['requested_start']);end=date.fromisoformat(manifest['requested_end'])
    if start>end or end>instant(evaluation_at).astimezone(ZoneInfo('America/New_York')).date():
        raise ValueError('HISTORY_INTAKE_REQUEST_DATE_ORDER')
    price=manifest['prices']
    expected='/v2/aggs/ticker/'+symbol+'/range/1/day/'+str(start)+'/'+str(end)
    current = manifest.get('capture_format') == 'MASSIVE_PROVIDER_RESPONSE_V1'
    if current:
        query = receipt_table(price['source'], expected, manifest['known_by'])
        unadjusted = query['params'] == {'adjusted':'false','sort':'asc','limit':50000}
        payload = query['provider_response']
    else:
        query = price['query']
        unadjusted = query.get('params',{}).get('adjusted') is False and query['params'].get('sort')=='asc'
        payload = pinned(price['source'])
    if query.get('path')!=expected or not unadjusted:
        raise PermissionError('HISTORY_INTAKE_UNADJUSTED_EXACT_QUERY_REQUIRED')
    bars, warning = price_bars(payload, start, end)
    issues=[]
    if warning:issues.append({'field':'raw_prices','code':'PROVIDER_WARNING_NOT_A_HISTORY_DATASET','original':warning})
    if bars and bars[0]['session_id']!=str(start):issues.append({'field':'raw_prices.requested_start',
        'code':'REQUESTED_START_NOT_RETURNED__LISTING_CALENDAR_OR_ENTITLEMENT_PROOF_REQUIRED',
        'requested':str(start),'observed':bars[0]['session_id']})
    actions={}
    for kind,endpoint,date_column in (('dividends','/stocks/v1/dividends','ex_dividend_date'),('splits','/stocks/v1/splits','execution_date')):
        source=manifest[kind]
        if current:
            args = receipt_table(source['source'], endpoint, manifest['known_by'])
            action_start = date.fromisoformat(args['params'][date_column+'.gte'])
            payload = args['provider_response']
        else:
            args = source['query']
            action_start = start
            payload = pinned(source['source'])
        params = args.get('params',{})
        if (args.get('path')!=endpoint or params.get('ticker')!=symbol or not start<=action_start<=end
            or params.get(date_column+'.gte')!=str(action_start) or params.get(date_column+'.lte')!=str(end)):
            raise PermissionError('HISTORY_INTAKE_ACTION_SCOPE_QUERY_MISMATCH')
        raw,warning=table(payload,('id','ticker',date_column));events=[];seen=set()
        if warning:issues.append({'field':kind,'code':'EMPTY_OR_OTHER_WARNING_IS_NOT_COMPLETE_ZERO_EVENTS','original':warning})
        for row in raw or []:
            day=date.fromisoformat(row[date_column]);identity=row['id']
            if not identity or identity in seen or row['ticker']!=symbol or not action_start<=day<=end:
                raise ValueError('HISTORY_INTAKE_ACTION_IDENTITY_OR_DATE_CONFLICT')
            seen.add(identity)
            if kind=='dividends':
                value={'original_cash_amount':str(nonnegative(row.get('cash_amount'))),'currency':row.get('currency'),
                    'declaration_date':row.get('declaration_date') or None,
                    'split_adjusted_cash_amount_not_used':row.get('split_adjusted_cash_amount')}
                if value['currency']!=manifest['quote_currency']:raise PermissionError('HISTORY_INTAKE_DIVIDEND_CURRENCY_CONFLICT')
            else:
                if current and row.get('adjustment_type') not in ('forward_split','reverse_split','stock_dividend'):
                    raise ValueError('HISTORY_INTAKE_UNKNOWN_SPLIT_TYPE')
                old=nonnegative(row.get('split_from'),positive=True);new=nonnegative(row.get('split_to'),positive=True)
                value={'new_per_old':str(new/old),'adjustment_type':row.get('adjustment_type'),
                    'historical_adjustment_factor_not_used':row.get('historical_adjustment_factor')}
            events.append({'event_id':identity,'session_id':str(day),**value,'source_row':deepcopy(row),
                'available_at':None,'historical_PIT_verified':False,'native_wealth_event_applied':False})
        actions[kind]={'records':events,'warning':warning,'complete_event_coverage_verified':False}
        if current:
            actions[kind].update(requested_start=str(action_start),requested_end=str(end),
                original_source=source['source'],retrieved_at=args['retrieved_at'])
    issues.extend([{'field':'raw_prices.available_at/revision','code':'HISTORICAL_PRICE_PUBLICATION_AND_REVISION_RECEIPTS_REQUIRED'},
        {'field':'corporate_actions.available_at/coverage','code':'DATE_ONLY_DECLARATION_AND_QUERY_ROWS_DO_NOT_ATTEST_PIT_OR_EVENT_COMPLETENESS'},
        {'field':'calendar','code':'SOURCE_OWNED_COMPLETED_CALENDAR_AND_KNOWLEDGE_TIMES_REQUIRED'},
        {'field':'valuation_history','code':'CURRENT_PE_OR_RAW_PRICE_IS_NOT_OWN_PRIMARY_METRIC_HISTORY'}])
    out=dict(schema_version=manifest['schema_version'],symbol=symbol,evaluation_at=evaluation_at,
        source_descriptor=deepcopy(descriptor),provider='MASSIVE',requested_start=str(start),requested_end=str(end),
        query_requested_unadjusted=True,raw_observed_bars=bars,corporate_action_observations=actions,
        returned_bar_count=len(bars),known_by=manifest['known_by'],issues=issues,
        source_complete_for_requested_range=False,qualified_native_price_history=None,
        qP_history_qualified=False,qV_history_qualified=False,historical_price_PIT_verified=False,
        adjusted_close_or_split_adjusted_dividend_used=False,trade_action='NO_TRADE')
    if current:
        out['current_history'] = current_history(manifest, query, bars, evaluation_at, start, end, expected)
    out['digest']=digest(out);return out


def current_history(manifest, canonical, bars, evaluation_at, start, end, price_path):
    import exchange_calendars as xc

    if not bars or manifest['exchange'] != 'XNAS' or manifest['quote_currency'] != 'USD':
        raise PermissionError('HISTORY_INTAKE_CURRENT_LISTING_OR_PRICE_RANGE')
    # Include both enclosing calendar periods so partial edge periods are never
    # treated as complete. Calendar sessions are independent of provider rows.
    evaluation_day = instant(evaluation_at).astimezone(ZoneInfo('America/New_York')).date()
    listing = xc.get_calendar('XNAS', start=min(start.replace(day=1), start-timedelta(days=start.weekday())),
        end=max(evaluation_day, end.replace(day=calendar.monthrange(end.year,end.month)[1]),
                end+timedelta(days=6-end.weekday())))
    summary = json.loads(pinned(manifest['calendar_check']))['XNAS']
    first = date.fromisoformat(bars[0]['session_id'])
    expected = [session.date().isoformat() for session in listing.sessions_in_range(first, end)]
    if (first<start or expected != [bar['session_id'] for bar in bars]
            or summary != {'sessions':len(expected),'missing':[],'extra':[],'calendar_version':xc.__version__}
            or listing.session_close(expected[-1]).to_pydatetime() > instant(canonical['retrieved_at'])):
        raise ValueError('HISTORY_INTAKE_CURRENT_CALENDAR_OR_COMPLETION_MISMATCH')
    # No earlier data may silently disappear after the archive's observed
    # first row. A shorter provider entitlement must be explicit in the manifest.
    if manifest['first_covered_session'] != expected[0]:
        raise ValueError('HISTORY_INTAKE_CURRENT_FIRST_COVERED_SESSION_MISMATCH')
    completed = [session.date().isoformat() for session in listing.sessions
        if listing.session_close(session).to_pydatetime() <= instant(evaluation_at)]
    if not completed or completed[-1] != expected[-1]:
        raise ValueError('HISTORY_INTAKE_CURRENT_CLOSE_STALE')
    adjusted = manifest.get('adjusted_prices')
    adjusted_evidence = None
    if adjusted is not None:
        receipt = receipt_table(adjusted,price_path,manifest['known_by'])
        if receipt['params'] != {'adjusted':'true','sort':'asc','limit':50000}:
            raise PermissionError('HISTORY_INTAKE_ADJUSTED_EXACT_QUERY_REQUIRED')
        adjusted_bars, warning = price_bars(receipt['provider_response'], start, end)
        if warning or expected != [bar['session_id'] for bar in adjusted_bars]:
            raise ValueError('HISTORY_INTAKE_ADJUSTED_CALENDAR_MISMATCH')
        adjusted_evidence = {'original_source':adjusted,'retrieved_at':receipt['retrieved_at'],
            'returned_bar_count':len(adjusted_bars),'used_for_technical':False}
    return {'raw_source':manifest['prices']['source'],'raw_retrieved_at':canonical['retrieved_at'],
        'adjusted_price_evidence':adjusted_evidence,'continuous_completed_session_count':len(expected),
        'first_covered_session':expected[0],'latest_completed_session':expected[-1],
        'latest_completed_session_close_at':listing.session_close(expected[-1]).isoformat(),
        'exchange':'XNAS','currency':'USD','calendar_version':xc.__version__,
        'calendar_check_sha256':manifest['calendar_check']['sha256'],
        'calendar_period_sessions':[session.date().isoformat() for session in listing.sessions]}


def bind(sources,request,symbol):
    result={}
    if not isinstance(sources,dict) or not sources:raise ValueError('HISTORY_INTAKE_NAMED_SOURCE_REQUIRED')
    if set(sources)-{'sec_filings','market_acquisition','twse_own_history','ibkr_history','corporate_actions','issuer_distributions'}:raise ValueError('HISTORY_INTAKE_UNKNOWN_SOURCE_ROUTE')
    if sources.get('issuer_distributions') is not None:
        from ishares_distribution_source import read
        result['issuer_distributions']=read(sources['issuer_distributions'],symbol,request['evaluation_at'])
    if sources.get('corporate_actions') is not None:
        from massive_action_source import read
        result['corporate_actions']=read(sources['corporate_actions'],symbol,request['evaluation_at'])
    if sources.get('sec_filings') is not None:
        from sec_publication_source import read
        result['sec_filings']=read(sources['sec_filings'],symbol,request['evaluation_at'])
    if sources.get('market_acquisition') is not None:
        result['market_acquisition']=read_market(sources['market_acquisition'],symbol,request['evaluation_at'])
    if sources.get('twse_own_history') is not None:
        from twse_own_history_source import read
        result['twse_own_history']=read(sources['twse_own_history'],symbol,request['evaluation_at'])
    if sources.get('ibkr_history') is not None:
        from ibkr_daily_source import audit
        source=sources['ibkr_history']
        if source.get('symbol')!=symbol:raise PermissionError('HISTORY_INTAKE_IBKR_ASSET_MISMATCH')
        result['ibkr_history']=audit(source,request['evaluation_at'])
    out=dict(schema_version='Family.W8.AssetHistorySourceQualification.v1',client_id=request['client_id'],
        run_id=request['run_id'],asset_id=symbol,evaluation_at=request['evaluation_at'],
        source_db_sha256=request['client_snapshot']['payload']['source_sha256'],sources=result,
        qualified_qP_history=None,qualified_qV_history=None,financial_qualification_released=False,trade_action='NO_TRADE')
    out['digest']=digest(out);return out


def technical_market(observed, *, evaluation_at, repo_root, profile, is_etf, formal_rule_source=None):
    """Use the current raw segment in the approved technical producer."""
    history = observed.get('current_history')
    if not history:
        return None
    from approved_v04_technical import trend
    from on_demand_market_observations import evaluate_observed_history

    bars = observed['raw_observed_bars']
    split_days = sorted({row['session_id'] for row in observed['corporate_action_observations']['splits']['records']})
    sessions = {bar['session_id'] for bar in bars}
    if any(day not in sessions for day in split_days):
        raise ValueError('HISTORY_INTAKE_SPLIT_SESSION_UNVERIFIED')
    segment_start = split_days[-1] if split_days else bars[0]['session_id']
    rows = []
    for bar in bars:
        if bar['session_id'] < segment_start:
            continue
        values = {key.title():bar[key] for key in ('open','high','low','close','volume')}
        rows.append({'Date':bar['session_id'],**{k:float(v) for k,v in values.items()},'_source_decimal':values})

    result = evaluate_observed_history(rows, repo_root=repo_root, evaluation_at=evaluation_at, macro=None,
        asset_id=observed['symbol'], approved_rule_profile=profile, is_etf=is_etf,
        formal_rule_source=formal_rule_source, equity_only=True)
    closes = {row['Date']:Decimal(row['_source_decimal']['Close']) for row in rows}
    for timeframe in ('weekly','monthly'):
        groups = {}
        for session in history['calendar_period_sessions']:
            day = date.fromisoformat(session)
            key = tuple(day.isocalendar()[:2]) if timeframe == 'weekly' else (day.year,day.month)
            groups.setdefault(key,[]).append(session)
        period_closes = [closes[group[-1]] for group in groups.values() if all(s in closes for s in group)]
        result['approved_technical']['timeframes'][timeframe] = {
            **trend(period_closes),'aggregation':'LAST_CLOSE_OF_CALENDAR_COMPLETE_RAW_SEGMENT_PERIOD',
            'calendar_coverage_verified':True,'completed_period_count':len(period_closes),
            'historical_PIT_verified':False}
    source = history['raw_source']
    return {**result,'symbol':observed['symbol'],'observed_date':rows[-1]['Date'],
        'observed_close':rows[-1]['Close'],'rows':len(rows),'source_path':source['local_path'],
        'source_sha256':source['sha256'],'provider_symbol':observed['symbol'],'provider':'MASSIVE_RAW_DAILY',
        'source_reference':'https://api.massive.com/v2/aggs/ticker/'+observed['symbol']+'/range/1/day/'
            +observed['requested_start']+'/'+observed['requested_end']+'?adjusted=false&sort=asc&limit=50000',
        'provider_verified_at':history['raw_retrieved_at'],'market_identity':{'exchange':history['exchange'],
            'currency':history['currency'],'provider_symbol':observed['symbol'],'provider_type':'ETF' if is_etf else 'EQUITY'},
        'completed_session_close_at':history['latest_completed_session_close_at'],
        'latest_expected_completed_session':history['latest_completed_session'],
        'cache_validation':'PINNED_MASSIVE_RESPONSE_AND_COMPLETED_SESSION_CALENDAR',
        'formal_identity_verified':False,
        'source_gaps':['HISTORICAL_PUBLICATION_AND_REVISION','CORPORATE_ACTION_PIT_COVERAGE'],
        'current_history_digest':observed['digest'],'history_quality':{
            'price_basis':'CANONICAL_CLOSE_VERIFIED_RAW_SEGMENTED_V1','analysis_start':segment_start,
            'invalid_source_rows':[],'discarded_before_last_gap':0,
            'continuous_source_sessions':history['continuous_completed_session_count'],'used_rows':len(rows),
            'observed_split_sessions':split_days,'discarded_before_latest_observed_split':len(bars)-len(rows),
            'corporate_action_pit_coverage':'UNVERIFIED','adjusted_prices_used':False,
            'formal_deployment_eligible':False},
        'call_trace':['W8.historical_source_qualification:current_raw_technical_segment',*result['call_trace']]}
