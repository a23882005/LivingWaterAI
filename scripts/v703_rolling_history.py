"""Map audited V70 snapshots to completed NYSE sessions for a continuous chart.

The immutable Taipei-date archive is preserved. A weekend/holiday snapshot maps
onto the most recent completed US session; each session keeps its latest valid
snapshot and its original Taipei observation date for traceability.
"""
import bisect
import csv
import datetime as dt
from functools import lru_cache
from importlib.metadata import version
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'data/macro_safety_daily.csv'
SCHEMA = 'V70.3/trading-observation-v2'


def evaluation_time(today=None, now=None):
    stamp = now or (dt.datetime.combine(today, dt.time(12), ZoneInfo('Asia/Taipei'))
                    if today else dt.datetime.now(dt.timezone.utc))
    if stamp.tzinfo is None:
        raise ValueError('Observation clock must be timezone-aware')
    return stamp.astimezone(dt.timezone.utc)


@lru_cache(maxsize=8)
def trading_calendar(today):
    # Lazy import: unrelated V70 calculations do not require the calendar package.
    import exchange_calendars as xcals
    start, end = today - dt.timedelta(days=180), today + dt.timedelta(days=400)
    calendar = xcals.get_calendar('XNYS', start=start.isoformat(), end=end.isoformat())
    sessions = [{'date': day.date().isoformat(), 'closeUtc': row['close'].isoformat().replace('+00:00', 'Z')}
                for day, row in calendar.schedule.loc[start.isoformat():end.isoformat()].iterrows()]
    return {'exchange':'XNYS', 'timezone':'America/New_York',
            'source':'https://www.nyse.com/markets/hours-calendars',
            'provider':'exchange_calendars', 'providerVersion':version('exchange_calendars'),
            'coverageStart':start.isoformat(), 'coverageEnd':end.isoformat(), 'sessions':sessions}


def _close_times(calendar):
    return [dt.datetime.fromisoformat(row['closeUtc'].replace('Z', '+00:00'))
            for row in calendar['sessions']]


def session_date(calendar, stamp):
    index = bisect.bisect_right(_close_times(calendar), stamp) - 1
    return calendar['sessions'][index]['date'] if index >= 0 else None


def history_payload(path=ARCHIVE, today=None, now=None):
    now = evaluation_time(today, now)
    local_today = now.astimezone(ZoneInfo('Asia/Taipei')).date()
    calendar = trading_calendar(local_today)
    closes = _close_times(calendar)
    days = {}
    if Path(path).exists():
        with Path(path).open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            required = {'observation_date', 'health_score', 'score_status', 'feed_asof_utc',
                        'run_timestamp_utc', 'daily_record_id', 'source_commit', 'v70_version'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('Rolling history archive schema is incomplete')
            for row in reader:
                if row['score_status'] != 'FORMAL_VALID' or row.get('neutral_imputed_items'):
                    continue
                try:
                    observed = dt.date.fromisoformat(row['observation_date'])
                    score = float(row['health_score'])
                    feed = dt.datetime.fromisoformat(row['feed_asof_utc'].replace('Z', '+00:00'))
                    run = dt.datetime.fromisoformat(row['run_timestamp_utc'].replace('Z', '+00:00'))
                    if feed.tzinfo is None or run.tzinfo is None or feed > now:
                        continue
                    if feed.astimezone(ZoneInfo('Asia/Taipei')).date() != observed:
                        continue
                    if not math.isfinite(score) or not 0 <= score <= 100:
                        continue
                    if not local_today - dt.timedelta(days=90) <= observed <= local_today:
                        continue
                    if not all(row[key] for key in ('daily_record_id', 'source_commit', 'v70_version')):
                        continue
                    index = bisect.bisect_right(closes, feed) - 1
                    if index < 0:
                        continue
                    day = calendar['sessions'][index]['date']
                except (ValueError, TypeError):
                    continue
                order = (feed, run, row['daily_record_id'])
                if day not in days or order > days[day][0]:
                    days[day] = (order, {
                        'date':day, 'snapshotDateTaipei':observed.isoformat(), 'score':score,
                        'version':row['v70_version'], 'feedAsOf':row['feed_asof_utc'],
                        'recordId':row['daily_record_id'], 'sourceCommit':row['source_commit'], 'kind':'archive',
                    })
    return {'schema':SCHEMA, 'calendar':calendar,
            'archiveThrough':max(days) if days else None,
            'rows':[days[day][1] for day in sorted(days)]}


def embed_history(markup, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    result, count = re.subn(
        r'(<script id="v703-daily-history" type="application/json">).*?(</script>)',
        lambda match:match[1] + encoded + match[2], markup, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Missing V70 daily history embedding point')
    return result


def observation_summary(payload, today=None, now=None):
    """Only open, completed sessions can be missing; holidays never count as NA."""
    now = evaluation_time(today, now)
    calendar = payload['calendar']
    sessions = [row['date'] for row, close in zip(calendar['sessions'], _close_times(calendar)) if close <= now][-15:]
    available = {row['date'] for row in payload['rows'] if row['date'] in sessions}
    return {'schema':SCHEMA, 'exchange':'XNYS', 'timezone':'America/New_York',
            'snapshotTimezone':'Asia/Taipei', 'tradingDays':15,
            'windowStart':sessions[0] if sessions else None, 'windowEnd':sessions[-1] if sessions else None,
            'sessionDates':sessions, 'validArchivedDays':len(available),
            'missingDates':[day for day in sessions if day not in available],
            'archiveThrough':payload.get('archiveThrough')}
