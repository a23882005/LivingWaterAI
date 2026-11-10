"""Isolated market-data observer. Not a V82 strategy implementation or broker."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math

SCHEMA = 'LW_MARKET_OBSERVER_V1'

def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def session(ts, zone):
    d = datetime.fromtimestamp(ts, ZoneInfo(zone))
    m = d.hour * 60 + d.minute
    if d.weekday() >= 5:
        return 'UNKNOWN'  # Timestamp alone is not an exchange holiday calendar.
    if zone == 'America/New_York':
        return 'PRE' if 240 <= m < 570 else 'RTH' if 570 <= m < 960 else 'POST' if 960 <= m < 1200 else 'UNSUPPORTED_OVERNIGHT'
    if zone == 'Asia/Taipei':
        return 'RTH' if 540 <= m < 810 else 'OUTSIDE_RTH'
    return 'UNKNOWN'

def observe(payload, symbol, now, interval_seconds=300, publication_delay_seconds=0):
    """Use finalized-by-time bars, not quote metadata. Completion is not vendor finality."""
    out = dict(schema=SCHEMA, symbol=symbol, source='Yahoo Finance chart',
               observed_at=datetime.fromtimestamp(now, timezone.utc).isoformat(),
               signal='UNKNOWN', formal_v82_executed=False, executable=False,
               data_status='UNKNOWN', publication_delay_seconds=publication_delay_seconds)
    try:
        result = payload['chart']['result'][0]
        meta = result['meta']
        if meta['symbol'].upper() != symbol.upper():
            return {**out, 'reason':'SYMBOL_MISMATCH'}
        zone = meta['exchangeTimezoneName']
        quote = result['indicators']['quote'][0]
        candidates = []
        for i, ts in enumerate(result['timestamp']):
            if not number(ts) or ts + interval_seconds > now - publication_delay_seconds:
                continue
            row = {k:quote[k][i] for k in ('open','high','low','close','volume')}
            if not all(number(x) for x in row.values()):
                continue
            if row['low'] <= 0 or row['volume'] < 0 or not row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high']:
                continue
            # Non-aligned final Yahoo quote timestamps are not complete interval bars.
            if ts % interval_seconds:
                continue
            candidates.append((ts,row))
        if not candidates:
            return {**out, 'reason':'NO_COMPLETE_VALID_BAR'}
        ts,row = max(candidates, key=lambda x:x[0])
        return {**out, 'data_status':'OBSERVED_NOT_REALTIME_CERTIFIED',
                'bar_start_utc':datetime.fromtimestamp(ts,timezone.utc).isoformat(),
                'bar_end_utc':datetime.fromtimestamp(ts+interval_seconds,timezone.utc).isoformat(),
                'age_seconds':max(0,now-ts-interval_seconds),
                'exchange_timezone':zone, 'session':session(ts,zone),
                'ohlcv':row, 'reason':'MARKET_REFERENCE_ONLY'}
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        return {**out, 'reason':'MALFORMED_OR_UNAVAILABLE_RESPONSE'}

def data_event_id(row):
    """Stable across retries; no account or holdings included."""
    keys = ['schema','symbol','source','data_status','reason','bar_start_utc','ohlcv']
    return hashlib.sha256(json.dumps({k:row.get(k) for k in keys},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def notification_decision(row, previous_status, sent_ids, watch_enabled=False):
    # No thresholds, proxy buys, inferred Stage, or automatic activation.
    if not watch_enabled:
        return 'WATCH_DISABLED'
    if data_event_id(row) in sent_ids:
        return 'DUPLICATE'
    if previous_status is None:
        return 'INITIAL_STATUS'
    if row['data_status'] != previous_status:
        return 'DATA_STATUS_CHANGED'
    return 'NO_APPROVED_STRATEGY_EVENT'
