"""Reproduce the bounded VOO source review; never grant investment eligibility.

The review digest must come from the release configuration, not request input.
Official schedules describe planned sessions, not actual bar publication times.
"""
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def schedule(calendar, start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or first.year != calendar['year'] or last.year != calendar['year']:
        raise ValueError('CALENDAR_COVERAGE')
    result = []
    day = first
    while day <= last:
        key = day.isoformat()
        if day.weekday() < 5 and key not in calendar['holidays']:
            close = time.fromisoformat(calendar['early_closes'].get(key, calendar['regular_close']))
            instant = datetime.combine(day, close, ZoneInfo(calendar['timezone']))
            result.append({'session': key, 'scheduled_close_at': instant.astimezone(timezone.utc).isoformat()})
        day += timedelta(days=1)
    return result


def compare(rows, review):
    dates = [r['Date'] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError('HISTORY_ORDER_OR_DUPLICATE')
    begin, end = review['window']['start'], review['window']['end']
    planned = schedule(review['calendar'], begin, end)
    actual = [r for r in rows if begin <= r['Date'] <= end]
    if [r['Date'] for r in actual] != [r['session'] for r in planned]:
        raise ValueError('SESSION_SET_MISMATCH')
    by_date = {r['Date']: r for r in rows}
    dividends = []
    expected_dates = set(review['dividends'])
    if {r['Date'] for r in actual if Decimal(r['Dividends']) != 0} != expected_dates:
        raise ValueError('DIVIDEND_EVENT_SET_MISMATCH')
    for day, amount in review['dividends'].items():
        observed = Decimal(by_date[day]['Dividends'])
        if not observed.is_finite() or observed.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) != Decimal(amount):
            raise ValueError('DIVIDEND_PUBLISHED_PRECISION_MISMATCH')
        dividends.append({'session': day, 'csv_amount': str(observed), 'issuer_amount_2dp': amount,
                          'status': 'MATCH_AT_PUBLISHED_PRECISION'})
    event = review['split_event']
    if Decimal(by_date[event['provider_event_date']]['Stock Splits']) != Decimal(event['new_per_old']):
        raise ValueError('SPLIT_RATIO_MISMATCH')
    return {'status': 'PASS_BOUNDED_SOURCE_REVIEW', 'symbol': review['instrument']['symbol'],
            'instrument': review['instrument'], 'window': review['window'],
            'calendar_sessions_matched': len(actual), 'scheduled_sessions': planned,
            'dividends': dividends, 'split_event_ratio': 'MATCH',
            'split_effective_time_mapping': 'OPEN_PROVIDER_DAY_VS_ISSUER_CLOSE_OF_BUSINESS',
            'retrieval_date': review['retrieval_date'],
            'per_bar_publication_verified': False, 'full_adjustment_basis_verified': False,
            'historical_ready': False, 'decision_eligible': False, 'trade_authorization': 'NONE'}


def verify(csv_path, evidence_root, trusted_review_sha256):
    root = Path(evidence_root).resolve()
    config = root / 'review.json'
    if sha(config) != trusted_review_sha256:
        raise ValueError('REVIEW_DIGEST_MISMATCH')
    review = json.loads(config.read_text())
    if sha(csv_path) != review['csv_sha256']:
        raise ValueError('CSV_DIGEST_MISMATCH')
    for artifact in review['artifacts']:
        path = (root / artifact['file']).resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError('EVIDENCE_PATH_OUTSIDE_ROOT')
        if sha(path) != artifact['sha256']:
            raise ValueError('OFFICIAL_ARTIFACT_CHANGED')
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as stream:
        result = compare(list(csv.DictReader(stream)), review)
    result['review_sha256'] = trusted_review_sha256
    result['csv_sha256'] = review['csv_sha256']
    return result


if __name__ == '__main__':
    import sys
    result = verify(*sys.argv[1:4])
    Path(sys.argv[4]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'scheduled_sessions'}, ensure_ascii=False))
