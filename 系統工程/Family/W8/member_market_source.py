"""Immutable market intake for the existing member V82 observation chain.

Provider OHLC is observed data, not an attestation of raw unadjusted wealth,
historical publication timing, order completeness or funding availability.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from family_input import digest


def time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('MEMBER_MARKET_TIMEZONE_REQUIRED')
    return result


def read_json(source):
    raw = Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest() != source['sha256']:
        raise PermissionError('MEMBER_SOURCE_HASH_MISMATCH')
    return json.loads(raw, parse_float=Decimal)


def _daily_rows(source,meta,quotes,stamps,by_date,cutoff,*,final_close_required=True):
    rows = {}; close_rows = {}; excluded = []; invalid = []; seen_dates = set()
    quote_stamp=meta.get('regularMarketTime')
    quote_at=(datetime.fromtimestamp(quote_stamp,ZoneInfo(source['timezone']))
        if type(quote_stamp) in (int,float) else None)
    acquired_day=time(source['retrieved_at']).astimezone(ZoneInfo(source['timezone'])).date().isoformat()
    for i, stamp in enumerate(stamps):
        date = datetime.fromtimestamp(stamp, ZoneInfo(source['timezone'])).date().isoformat()
        if date in seen_dates:
            raise ValueError('MEMBER_MARKET_DUPLICATE_SESSION')
        seen_dates.add(date)
        if date not in by_date:
            excluded.append({'date': date, 'reason': 'SESSION_NOT_COMPLETED_AT_ACQUISITION_OR_NOT_IN_CALENDAR'})
            continue
        if source['provider']=='YAHOO_CHART' and date==acquired_day and (quote_at is None or quote_at>cutoff or quote_at<time(by_date[date]['open_at'])
                or final_close_required and quote_at<time(by_date[date]['close_at'])):
            # A delayed current quote can still inhabit today's daily bar
            # after the exchange closes. Calendar completion alone does not
            # attest that the provider has published the final daily close.
            excluded.append({'date':date,'reason':'PROVIDER_LATEST_BAR_FINAL_CLOSE_NOT_CONFIRMED',
                'provider_regular_market_time':quote_at.isoformat() if quote_at else None})
            continue
        values = {k.title(): quotes[k][i] for k in ('open', 'high', 'low', 'close', 'volume')}
        try:
            close = Decimal(str(values['Close']))
            if close.is_finite() and close > 0:
                close_rows[date] = {'Date': date, 'Close': float(close), '_source_decimal': {'Close': str(close)}}
        except (InvalidOperation, ValueError, TypeError):
            pass
        try:
            nums = {k: Decimal(str(v)) for k, v in values.items()}
            valid = (all(v.is_finite() for v in nums.values())
                     and min(nums[k] for k in ('Open', 'High', 'Low', 'Close')) > 0
                     and nums['Volume'] >= 0 and nums['Low'] <= min(nums['Open'], nums['Close'])
                     and nums['High'] >= max(nums['Open'], nums['Close']))
        except (InvalidOperation, ValueError, TypeError):
            valid = False
        if not valid:
            invalid.append({'date': date, 'original_values': {k: str(v) for k, v in values.items()}})
            continue
        rows[date] = {'Date': date, **{k: float(v) for k, v in nums.items()},
                      '_source_decimal': {k: str(v) for k, v in nums.items()}}
    return rows,close_rows,excluded,invalid


def _london_daily(source, calendar):
    data = read_json(source)
    listing = source['symbol']+'.LON'
    identity = read_json(source['identity_source'])
    matches = [row for row in identity['bestMatches'] if row['1. symbol'] == listing]
    if (len(matches) != 1 or source['provider_symbol'] != source['symbol']
            or source['exchange'] != 'XLON' or source['provider_exchange'] != 'LSEETF'
            or source['timezone'] != 'Europe/London' or source['currency'] != 'USD'
            or matches[0]['2. name'] != source['expected_listing_name']
            or matches[0]['3. type'] != 'ETF' or matches[0]['4. region'] != 'United Kingdom'
            or matches[0]['8. currency'] != 'USD'
            or source['source_reference'] != 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol='+listing+'&outputsize=compact'):
        raise PermissionError('MEMBER_MARKET_LONDON_ETF_LISTING')
    meta = data['Meta Data']
    series = data['Time Series (Daily)']
    days = sorted(series)
    if (not days or meta['2. Symbol'] != listing or meta['3. Last Refreshed'] != days[-1]
            or meta['4. Output Size'].lower() != 'compact' or 'Daily Prices' not in meta['1. Information']):
        raise PermissionError('MEMBER_MARKET_LONDON_DAILY_METADATA')
    sessions = {row['session_id']:row for row in calendar['sessions'] if days[0]<=row['session_id']<=days[-1]}
    if list(sessions) != days or time(sessions[days[-1]]['close_at']) > time(source['retrieved_at']):
        raise ValueError('MEMBER_MARKET_LONDON_DAILY_SESSION_COVERAGE')
    actions = read_json(source['actions_source'])
    if time(actions['retrieved_at']) > time(source['retrieved_at']):
        raise PermissionError('MEMBER_MARKET_LONDON_ACTIONS_AFTER_CAPTURE')
    if any(actions[name]['symbol'] != listing or actions[name]['data'] != [] for name in ('splits','dividends')):
        raise ValueError('MEMBER_MARKET_LONDON_ACTION_HISTORY_REQUIRES_QUALIFICATION')
    fields = {'open':'1. open','high':'2. high','low':'3. low','close':'4. close','volume':'5. volume'}
    quotes = {key:[series[d][field] for d in days] for key,field in fields.items()}
    # The API supplies trading dates only; use the identified London sessions for
    # the common daily-bars adapter, without claiming a provider timestamp.
    stamps = [int(time(sessions[d]['close_at']).timestamp()) for d in days]
    identity = {'symbol':source['symbol'], 'currency':'USD','exchangeName':'LSEETF',
                'exchangeTimezoneName':'Europe/London','instrumentType':'ETF'}
    evidence={'provider':source['provider'],'provider_listing':listing,'returned_rows':len(days),
              'provider_metadata_timezone':meta['5. Time Zone'],'session_date_source':'XLON_CALENDAR',
              'price_basis':'PROVIDER_DAILY_OHLC__SINGLE_SOURCE','actions_source_sha256':source['actions_source']['sha256'],
              'provider_reported_actions':{'splits':[],'dividends':[]},'historical_PIT_attested':False}
    return identity,quotes,stamps,evidence


def read_market(source, *, symbol, evaluation_at, repo_root, profile, is_etf, observation_route='V82'):
    options = dict(symbol=symbol, evaluation_at=evaluation_at, repo_root=repo_root, profile=profile,
                   is_etf=is_etf, observation_route=observation_route)
    original = _read_market(source, **options)
    alternate = (source or {}).get('independent_daily_ohlc_source')
    if not alternate or time(alternate['retrieved_at']) > time(evaluation_at):
        return original
    try:
        return _compare_independent_history(source, alternate, original, options, observation_route)
    except (ValueError, PermissionError, KeyError, ArithmeticError) as error:
        # A failed alternate source cannot erase the already verified original.
        original['independent_history_candidate_error'] = {'source_sha256':alternate.get('sha256'),
            'reason':str(error), 'retained_source_sha256':source['sha256']}
        return original


def _compare_independent_history(source, alternate, original, options, observation_route):
    if (source['provider'] != 'IBKR_LAST_DAILY_OBSERVATION' or alternate['provider'] != 'ALPHA_VANTAGE_LONDON_ETF_DAILY'
            or alternate['base_history_sha256'] != source['sha256'] or alternate['contract_id'] != source['contract_id']
            or alternate['calendar_source'] != source['calendar_source'] or observation_route != 'V82'):
        raise PermissionError('MEMBER_MARKET_INDEPENDENT_SOURCE_BINDING')
    second = _read_market(alternate, **options)
    if (second['market_identity'] != original['market_identity'] or second['observed_date'] != original['observed_date']
            or Decimal(str(second['observed_close'])) != Decimal(str(original['observed_close']))):
        raise PermissionError('MEMBER_MARKET_INDEPENDENT_SOURCE_CURRENT_QUOTE_CONFLICT')
    if second['history_quality']['invalid_source_rows'] or second['rows'] != second['provider_completion_evidence']['returned_rows']:
        raise ValueError('MEMBER_MARKET_INDEPENDENT_SOURCE_INVALID_DAILY_BARS')
    from pm_source_document import history
    raw, _ = history(source)
    ib = {time(t).astimezone(ZoneInfo(source['timezone'])).date().isoformat(): Decimal(str(price))
          for t,price in zip(raw['time'],raw['close'])}
    av = read_json(alternate)['Time Series (Daily)']
    if set(av) - set(ib):
        raise ValueError('MEMBER_MARKET_INDEPENDENT_SOURCE_SESSION_CONFLICT')
    if second['rows'] <= original['rows']:
        return original
    second['independent_broker_observation'] = original
    second['independent_history_comparison'] = {'same_completed_session_count':len(av),
        'maximum_absolute_close_difference':str(max(abs(ib[d]-Decimal(av[d]['4. close'])) for d in av)),
        'volume_or_ohlc_spliced':False,'technical_source_sha256':alternate['sha256'],
        'position_valuation_source_sha256':source['sha256'],'original_contract_id':source['contract_id']}
    return second


def _read_market(source, *, symbol, evaluation_at, repo_root, profile, is_etf, observation_route='V82'):
    if observation_route not in ('V82', 'V75'):
        raise ValueError('MEMBER_MARKET_UNKNOWN_OBSERVATION_ROUTE')
    if source is None:
        return None
    if (source.get('provider') not in ('YAHOO_CHART','NASDAQ_HISTORICAL','MASSIVE_RAW_DAILY','IBKR_LAST_DAILY_OBSERVATION','TWSE_STOCK_DAY','ALPHA_VANTAGE_LONDON_ETF_DAILY') or source.get('symbol') != symbol
            or not source.get('source_reference') or time(source['retrieved_at']) > time(evaluation_at)):
        raise PermissionError('MEMBER_MARKET_SOURCE_IDENTITY_OR_TIME')
    calendar = read_json(source['calendar_source'])
    if (calendar.get('exchange') != source['exchange'] or calendar.get('timezone') != source['timezone']
            or not calendar.get('provider') or not calendar.get('version')
            or time(calendar['coverage_cutoff']) < time(evaluation_at)):
        raise ValueError('MEMBER_MARKET_CALENDAR_COVERAGE')
    sessions = calendar['sessions']; dates = [r['session_id'] for r in sessions]
    if dates != sorted(set(dates)) or any(time(r['open_at']) >= time(r['close_at']) for r in sessions):
        raise ValueError('MEMBER_MARKET_CALENDAR_ORDER')
    completion=None
    if source['provider']=='NASDAQ_HISTORICAL':
        from nasdaq_daily_source import load
        meta,quotes,stamps,completion=load(source,evaluation_at)
    elif source['provider']=='MASSIVE_RAW_DAILY':
        from massive_daily_source import load
        meta,quotes,stamps,completion=load(source,evaluation_at)
    elif source['provider']=='IBKR_LAST_DAILY_OBSERVATION':
        from ibkr_daily_source import load
        meta,quotes,stamps,completion=load(source,evaluation_at)
    elif source['provider']=='ALPHA_VANTAGE_LONDON_ETF_DAILY':
        meta,quotes,stamps,completion=_london_daily(source,calendar)
    elif source['provider']=='TWSE_STOCK_DAY':
        from twse_own_history_source import load_daily
        meta,quotes,stamps,completion=load_daily(source,evaluation_at,sessions,is_etf=is_etf)
    else:
        chart = read_json(source)['chart']
        if chart.get('error') or len(chart.get('result') or []) != 1:
            raise ValueError('MEMBER_MARKET_PROVIDER_ERROR')
        raw = chart['result'][0]; meta = raw['meta']
        quotes = raw['indicators']['quote'][0]; stamps = raw['timestamp']
    expected = {'symbol': source['provider_symbol'], 'currency': source['currency'],
                'exchangeTimezoneName': source['timezone'], 'exchangeName': source['provider_exchange']}
    if any(meta.get(k) != v for k, v in expected.items()):
        raise PermissionError('MEMBER_MARKET_PROVIDER_IDENTITY_CONFLICT')
    if (meta.get('instrumentType') not in ('ETF', 'EQUITY')
            or is_etf is True and meta['instrumentType'] != 'ETF'
            or is_etf is False and meta['instrumentType'] != 'EQUITY'):
        raise PermissionError('MEMBER_MARKET_PRODUCT_TYPE_CONFLICT')
    # A bar must have completed before both acquisition and evaluation. A
    # current-session quote must not become a final close when replayed later.
    acquisition=(source['historical_retrieved_at'] if source['provider']=='NASDAQ_HISTORICAL' else source['retrieved_at'])
    cutoff = min(time(evaluation_at), time(acquisition))
    completed = [r for r in sessions if time(r['close_at']) <= cutoff]
    evaluation_completed = [r for r in sessions if time(r['close_at']) <= time(evaluation_at)]
    if not completed:
        raise ValueError('MEMBER_MARKET_NO_COMPLETED_SESSIONS')
    window=calendar.get('actual_session_window')
    calendar_evidence=({'calendar_actual_session_window':window,
        'calendar_completed_window_verified':bool(window.get('verified') and evaluation_completed
            and evaluation_completed[-1]['session_id']<=window['through']),
        'calendar_historical_pit_verified':calendar.get('historical_pit_verified') is True} if window else {})
    by_date = {r['session_id']: r for r in completed}
    if stamps != sorted(set(stamps)):
        raise ValueError('MEMBER_MARKET_SOURCE_TIMESTAMP_ORDER')
    if any(len(quotes[k]) != len(stamps) for k in ('open', 'high', 'low', 'close', 'volume')):
        raise ValueError('MEMBER_MARKET_ARRAY_LENGTH')
    rows,close_rows,excluded,invalid=_daily_rows(source,meta,quotes,stamps,by_date,cutoff)
    latest_source=source;supplement_audit=None;reference_quote=None
    supplement=source.get('current_observation_source')
    if supplement is not None:
        if source['provider']!='YAHOO_CHART' or supplement.get('provider')!='YAHOO_CHART':
            raise PermissionError('MEMBER_CURRENT_QUOTE_PROVIDER_MISMATCH')
        if time(supplement['retrieved_at'])>time(evaluation_at):
            raise PermissionError('MEMBER_CURRENT_QUOTE_AFTER_CUTOFF')
        chart=read_json(supplement)['chart']
        if chart.get('error') or len(chart.get('result') or [])!=1:
            raise ValueError('MEMBER_MARKET_CURRENT_PROVIDER_ERROR')
        current_raw=chart['result'][0];current_meta=current_raw['meta']
        if (any(current_meta.get(k)!=v for k,v in expected.items())
            or current_meta.get('instrumentType')!=meta['instrumentType']):
            raise PermissionError('MEMBER_CURRENT_QUOTE_IDENTITY_CURRENCY_OR_TYPE_CONFLICT')
        current_stamps=current_raw['timestamp'];current_quotes=current_raw['indicators']['quote'][0]
        if (current_stamps!=sorted(set(current_stamps))
            or any(len(current_quotes[k])!=len(current_stamps) for k in ('open','high','low','close','volume'))):
            raise ValueError('MEMBER_MARKET_CURRENT_ARRAY_OR_TIMESTAMP_ORDER')
        current_cutoff=min(time(evaluation_at),time(supplement['retrieved_at']))
        current_sessions={r['session_id']:r for r in sessions if time(r['close_at'])<=current_cutoff}
        current_rows,current_closes,current_excluded,current_invalid=_daily_rows(
            {**source,**supplement},current_meta,current_quotes,current_stamps,current_sessions,current_cutoff)
        reference_rows,_,_,_=_daily_rows({**source,**supplement},current_meta,current_quotes,
            current_stamps,current_sessions,current_cutoff,final_close_required=False)
        if reference_rows:
            reference_day=max(reference_rows)
            reference_quote={'observed_date':reference_day,
                'observed_close':reference_rows[reference_day]['_source_decimal']['Close'],
                'source_sha256':supplement['sha256'],'source_path':supplement['local_path'],
                'source_reference':supplement['source_reference'],'currency':source['currency'],
                'original_final_close_verified':reference_day in current_rows,
                'completed_calendar_session_close_at':current_sessions[reference_day]['close_at'],
                'formal_price_qualification_created':False,
                'final_close_qualification_issues':[r for r in current_excluded if r['date']==reference_day]}
        last_original=max(set(rows)|set(close_rows),default='')
        appended=sorted(day for day in current_rows if day>last_original)
        required_bridge=[r['session_id'] for r in sessions if appended and last_original<r['session_id']<=appended[-1]]
        missing_bridge=[day for day in required_bridge if day not in current_rows]
        unappended=list(appended) if missing_bridge else []
        if missing_bridge:appended=[]
        for day in appended:rows[day]=current_rows[day]
        for day,value in current_closes.items():
            if not missing_bridge and day>last_original:close_rows[day]=value
        if appended:latest_source={**source,**supplement}
        completed=[r for r in sessions if time(r['close_at'])<=max(cutoff,current_cutoff)]
        by_date={r['session_id']:r for r in completed}
        supplement_audit={'schema_version':'Family.W8.CurrentQuoteAppend.v1',
            'original_source_sha256':source['sha256'],'current_source_sha256':supplement['sha256'],
            'original_last_completed_date':last_original,'appended_completed_dates':appended,
            'missing_bridge_sessions':missing_bridge,'current_dates_kept_reference_only':unappended,
            'overlapping_dates_retained_from_original':sorted(set(current_rows)&set(rows)-set(appended)),
            'excluded_current_capture_rows':current_excluded,'invalid_current_capture_rows':current_invalid,
            'history_replaced':False,'historical_PIT_or_canonical_price_qualification_created':False}
    # Do not silently concatenate samples across missing/invalid sessions.
    valid_dates = sorted(rows)
    if not valid_dates:
        raise ValueError('MEMBER_MARKET_NO_COMPLETED_VALID_ROWS')
    expected_dates = [r['session_id'] for r in completed
                      if valid_dates[0] <= r['session_id'] <= valid_dates[-1]]
    last_gap = max((i for i, day in enumerate(expected_dates) if day not in rows), default=-1)
    used = [rows[day] for day in expected_dates[last_gap + 1:] if day in rows]
    if not used:
        raise ValueError('MEMBER_MARKET_NO_CONTIGUOUS_VALID_SUFFIX')
    if observation_route == 'V75':
        # Share exactly the same immutable intake and completed-session checks.
        # V75 receives its own named predicates, never V82 votes or stages.
        return {'symbol':symbol,'completed_rows':deepcopy_rows(used),
            'observed_date':used[-1]['Date'],'observed_close':used[-1]['_source_decimal']['Close'],
            'latest_expected_completed_session':evaluation_completed[-1]['session_id'],
            'completed_session_close_at':by_date[used[-1]['Date']]['close_at'],
            'source_sha256':latest_source['sha256'],'source_path':latest_source['local_path'],
            'source_reference':latest_source['source_reference'],'provider_verified_at':latest_source['retrieved_at'],
            'source_descriptor_digest':digest(source),
            'market_identity':{'exchange':source['exchange'],'currency':source['currency'],
                'provider_symbol':source['provider_symbol'],'provider_type':meta['instrumentType']},
            'history_quality':{'excluded_uncompleted_rows':excluded,'invalid_source_rows':invalid,
                'discarded_before_last_gap':len(valid_dates)-len(used),
                'price_basis':(completion or {}).get('price_basis') or ('RAW_UNADJUSTED_PROVIDER_OHLC__NOT_PIT_WEALTH' if
                    (completion or {}).get('raw_unadjusted_request_verified') is True else
                    'PROVIDER_OHLC__RAW_UNADJUSTED_NOT_ATTESTED'),
                'corporate_action_pit_coverage':'UNVERIFIED','formal_deployment_eligible':False},
            'calendar_scope':calendar.get('scope','IDENTIFIED_EXCHANGE_CALENDAR_SOURCE'),
            **({'provider_completion_evidence':completion} if completion else {}),
            **calendar_evidence,
            **({'current_quote_append':supplement_audit} if supplement_audit is not None else {}),
            **({'current_reference_quote':reference_quote} if reference_quote is not None else {}),
            'call_trace':['W8.member_market_source:original_completed_session_intake']}
    from on_demand_market_observations import evaluate_observed_history
    observed = evaluate_observed_history(used, repo_root=repo_root, evaluation_at=evaluation_at,
        macro=None, asset_id=symbol, approved_rule_profile=profile, is_etf=is_etf)
    # Keep long, valid Close observations independently usable when a High/Low
    # error truncates the full OHLC window. Never merge their votes into the
    # OHLC result or repair any provider prices.
    close_dates = sorted(close_rows)
    close_expected = [r['session_id'] for r in completed
                      if close_dates[0] <= r['session_id'] <= close_dates[-1]]
    close_gap = max((i for i, day in enumerate(close_expected) if day not in close_rows), default=-1)
    close_used = [close_rows[day] for day in close_expected[close_gap+1:]]
    if len(close_used) > len(used):
        from on_demand_market_observations import evaluate_close_history
        independent = evaluate_close_history(close_used, repo_root=repo_root, approved_rule_profile=profile, is_etf=is_etf)
        independent.update(scope='SEPARATE_CLOSE_ONLY_COMPONENTS__NOT_MERGED_VOTES', rows=len(close_used),
            observed_date=close_used[-1]['Date'], observed_close=close_used[-1]['Close'],
            source_sha256=latest_source['sha256'], source_path=latest_source['local_path'])
        observed['independent_close_observation'] = independent
    observed.update(symbol=symbol, source_path=latest_source['local_path'], source_sha256=latest_source['sha256'],
        provider_verified_at=latest_source['retrieved_at'], observed_date=used[-1]['Date'],
        observed_close=used[-1]['Close'], rows=len(used), source_reference=latest_source['source_reference'],
        market_identity={'exchange': source['exchange'], 'currency': source['currency'],
                         'provider_symbol': source['provider_symbol'], 'provider_type': meta['instrumentType']},
        completed_session_close_at=by_date[used[-1]['Date']]['close_at'],
        # Acquisition bounds which source bars may be consumed; evaluation
        # bounds which completed session is now expected. A pre-close capture
        # replayed after the close must not certify its own stale cutoff fresh.
        latest_expected_completed_session=evaluation_completed[-1]['session_id'],
        history_quality={'excluded_uncompleted_rows': excluded, 'invalid_source_rows': invalid,
            'discarded_before_last_gap': len(valid_dates)-len(used),
            'scope': 'CONTIGUOUS_PROVIDER_OHLC_OBSERVATIONS__NOT_PIT_WEALTH',
            'price_basis': (completion or {}).get('price_basis') or ('RAW_UNADJUSTED_PROVIDER_OHLC__NOT_PIT_WEALTH' if
                (completion or {}).get('raw_unadjusted_request_verified') is True else
                'PROVIDER_OHLC__RAW_UNADJUSTED_NOT_ATTESTED'),
            'corporate_action_pit_coverage': 'UNVERIFIED', 'formal_deployment_eligible': False},
        source_descriptor_digest=digest(source),
        **calendar_evidence,
        **({'provider_completion_evidence':completion} if completion else {}))
    if supplement_audit is not None:observed['current_quote_append']=supplement_audit
    if reference_quote is not None:observed['current_reference_quote']=reference_quote
    return observed


def deepcopy_rows(rows):
    # Return original Decimal spellings rather than round-tripping the float
    # rendering used by the older observation boundary.
    return [{'Date':r['Date'],**r['_source_decimal']} for r in rows]
