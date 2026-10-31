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


def read_market(source, *, symbol, evaluation_at, repo_root, profile, is_etf):
    if source is None:
        return None
    if (source.get('provider') != 'YAHOO_CHART' or source.get('symbol') != symbol
            or not source.get('source_reference') or time(source['retrieved_at']) > time(evaluation_at)):
        raise PermissionError('MEMBER_MARKET_SOURCE_IDENTITY_OR_TIME')
    chart = read_json(source)['chart']
    if chart.get('error') or len(chart.get('result') or []) != 1:
        raise ValueError('MEMBER_MARKET_PROVIDER_ERROR')
    raw = chart['result'][0]; meta = raw['meta']
    expected = {'symbol': source['provider_symbol'], 'currency': source['currency'],
                'exchangeTimezoneName': source['timezone'], 'exchangeName': source['provider_exchange']}
    if any(meta.get(k) != v for k, v in expected.items()):
        raise PermissionError('MEMBER_MARKET_PROVIDER_IDENTITY_CONFLICT')
    if (meta.get('instrumentType') not in ('ETF', 'EQUITY')
            or is_etf is True and meta['instrumentType'] != 'ETF'
            or is_etf is False and meta['instrumentType'] != 'EQUITY'):
        raise PermissionError('MEMBER_MARKET_PRODUCT_TYPE_CONFLICT')
    calendar = read_json(source['calendar_source'])
    if (calendar.get('exchange') != source['exchange'] or calendar.get('timezone') != source['timezone']
            or not calendar.get('provider') or not calendar.get('version')
            or time(calendar['coverage_cutoff']) < time(evaluation_at)):
        raise ValueError('MEMBER_MARKET_CALENDAR_COVERAGE')
    sessions = calendar['sessions']; dates = [r['session_id'] for r in sessions]
    if dates != sorted(set(dates)) or any(time(r['open_at']) >= time(r['close_at']) for r in sessions):
        raise ValueError('MEMBER_MARKET_CALENDAR_ORDER')
    # A bar must have completed before both acquisition and evaluation. A
    # current-session quote must not become a final close when replayed later.
    cutoff = min(time(evaluation_at), time(source['retrieved_at']))
    completed = [r for r in sessions if time(r['close_at']) <= cutoff]
    evaluation_completed = [r for r in sessions if time(r['close_at']) <= time(evaluation_at)]
    if not completed:
        raise ValueError('MEMBER_MARKET_NO_COMPLETED_SESSIONS')
    by_date = {r['session_id']: r for r in completed}
    quotes = raw['indicators']['quote'][0]; stamps = raw['timestamp']
    if stamps != sorted(set(stamps)):
        raise ValueError('MEMBER_MARKET_SOURCE_TIMESTAMP_ORDER')
    if any(len(quotes[k]) != len(stamps) for k in ('open', 'high', 'low', 'close', 'volume')):
        raise ValueError('MEMBER_MARKET_ARRAY_LENGTH')
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
        if date==acquired_day and (quote_at is None or quote_at<time(by_date[date]['close_at']) or quote_at>cutoff):
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
            source_sha256=source['sha256'], source_path=source['local_path'])
        observed['independent_close_observation'] = independent
    observed.update(symbol=symbol, source_path=source['local_path'], source_sha256=source['sha256'],
        provider_verified_at=source['retrieved_at'], observed_date=used[-1]['Date'],
        observed_close=used[-1]['Close'], rows=len(used), source_reference=source['source_reference'],
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
            'price_basis': 'PROVIDER_OHLC__RAW_UNADJUSTED_NOT_ATTESTED',
            'corporate_action_pit_coverage': 'UNVERIFIED', 'formal_deployment_eligible': False},
        source_descriptor_digest=digest(source))
    return observed
