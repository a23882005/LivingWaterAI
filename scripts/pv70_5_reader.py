#!/usr/bin/env python3
"""W3-02: parse an immutable local source snapshot. Standard library; no network.

The external source lock pins commit + original Git blob SHA-1 + SHA-256.
This module does not fetch data, calculate V70 scores, or infer instrument identity.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CANONICAL = '系統工程/總經V70/V70_macro_latest.json'
SCHEMAS = {
    'data/18_macro_verification.json': 'V70.3/18-macro-collector-v1',
    'data/8_macro_supplement_verified.json': 'V70.3/10h-eight-supplement-v3',
    CANONICAL: 'V70.3/family-macro-feed-v3',
    'data/wallstreet5_forecasts.json': 'V70.3/wallstreet-five-forecast-v1',
}
STATES = {'OK', 'USABLE', 'STALE', 'MISSING', 'UNKNOWN', 'BLOCKED'}
GOOD = {'OK', 'USABLE'}

def content_sha256(data):
    return hashlib.sha256(data).hexdigest()

def git_blob_sha1(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None

def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def strict_json(data):
    def invalid_constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError('duplicate JSON key: ' + k)
            d[k] = v
        return d
    return json.loads(data, parse_constant=invalid_constant, object_pairs_hook=pairs)

class SourceReader:
    def __init__(self, repo, commit, lock):
        self.repo = Path(repo).resolve()
        self.commit = commit
        self.lock = lock if isinstance(lock, dict) else {}
        self.issues = []
        self.source_files = {}
        self.cache = {}
        if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
            self.issue('SOURCE_COMMIT_INVALID')
        if self.lock.get('source_commit') != commit:
            self.issue('SOURCE_COMMIT_MISMATCH')
        if self.lock.get('schema') != 'LivingWaterAI/p70-5-source-lock-v1' or not isinstance(self.lock.get('files'), dict):
            self.issue('SOURCE_LOCK_SCHEMA_INVALID')

    def issue(self, code, path=None):
        self.issues.append(code + (':' + path if path else ''))

    def raw(self, path):
        if path in self.cache:
            return self.cache[path]
        q = (self.repo / path).resolve()
        if Path(path).is_absolute() or not q.is_relative_to(self.repo):
            self.issue('SOURCE_PATH_OUTSIDE_REPO', path)
            return None
        expected = self.lock.get('files', {}).get(path)
        if not isinstance(expected, dict):
            self.issue('SOURCE_NOT_IN_LOCK', path)
            return None
        if expected.get('source_commit') != self.commit:
            self.issue('SOURCE_FILE_COMMIT_MISMATCH', path)
            return None
        try:
            b = q.read_bytes()
        except OSError:
            self.issue('SOURCE_MISSING', path)
            return None
        sha, blob = content_sha256(b), git_blob_sha1(b)
        if expected.get('size') != len(b) or expected.get('sha256') != sha or expected.get('git_blob_sha1') != blob:
            self.issue('SOURCE_HASH_OR_SIZE_MISMATCH', path)
            return None
        self.source_files[path] = {'path': path, 'source_commit': self.commit,
            'git_blob_sha1': blob, 'blob_sha256': sha, 'size': len(b),
            'producer': expected.get('producer', 'UNKNOWN'),
            'use_class': expected.get('use_class', 'UNKNOWN'),
            'schema': expected.get('schema', 'UNDECLARED'),
            'data_date': expected.get('data_date', 'UNKNOWN')}
        self.cache[path] = b
        return b

    def json(self, path, expected_schema=None):
        b = self.raw(path)
        if b is None:
            return None
        try:
            d = strict_json(b)
            if not isinstance(d, dict):
                raise ValueError('object required')
        except (ValueError, UnicodeError):
            self.issue('JSON_INVALID', path)
            return None
        if expected_schema and d.get('schema') != expected_schema:
            self.issue('SCHEMA_MISMATCH', path)
            return None
        return d

    def csv(self, path, required=()):
        b = self.raw(path)
        if b is None:
            return None
        try:
            reader = csv.DictReader(io.StringIO(b.decode('utf-8-sig')), strict=True)
            fields = reader.fieldnames
            if not fields or len(set(fields)) != len(fields) or not set(required).issubset(fields):
                raise ValueError('header invalid')
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ValueError('row length mismatch')
            return rows
        except (ValueError, UnicodeError, csv.Error):
            self.issue('CSV_INVALID', path)
            return None

    def quote(self, region, symbol, item, manifest):
        path = f'data/market_history/{region}/{symbol.replace("/", "_")}.csv'
        status = item.get('status', 'UNKNOWN')
        quote = {'symbol': symbol, 'original_symbol': symbol, 'instrument_id': item.get('instrument_id'),
            'currency': item.get('currency'), 'exchange': item.get('exchange'),
            'field': 'Close', 'value': None, 'adjusted_value': None,
            'price_basis': 'UNADJUSTED_CLOSE', 'adjusted_price_basis': 'PROVIDER_ADJUSTED_CLOSE',
            'provider': manifest.get('data_source', 'UNKNOWN'), 'source_path': path,
            'source_blob_sha256': None, 'source_git_blob_sha1': None, 'source_commit': self.commit,
            'observation_date': None, 'manifest_observation_date': item.get('latest_observation'),
            'manifest_generated_utc': manifest.get('generated_utc'), 'raw_status': status,
            'status': status if status in STATES else 'UNKNOWN', 'value_state': 'UNKNOWN', 'issue_codes': [],
            'source_csv_line': None, 'date_validity_state': 'NOT_EVALUATED_REQUIRES_REQUEST_POLICY'}
        if status not in GOOD:
            quote['value_state'] = status if status in STATES else 'UNKNOWN'
            quote['issue_codes'].append('MANIFEST_STATUS_' + str(status))
            self.issue('REQUIRED_MARKET_STATUS_' + str(status), symbol)
        if path not in self.lock.get('files', {}):
            quote['issue_codes'].append('QUOTE_SOURCE_NOT_PRESENT')
            if status in GOOD:
                self.issue('REQUIRED_QUOTE_MISSING', symbol)
            return quote
        rows = self.csv(path, ('Date', 'Close'))
        if rows is None or not rows:
            quote['issue_codes'].append('QUOTE_CSV_UNREADABLE_OR_EMPTY')
            self.issue('REQUIRED_QUOTE_UNREADABLE', symbol)
            return quote
        quote['source_blob_sha256'] = self.source_files[path]['blob_sha256']
        quote['source_git_blob_sha1'] = self.source_files[path]['git_blob_sha1']
        dates = [parse_date(row['Date']) for row in rows]
        if None in dates or dates != sorted(set(dates)):
            quote['issue_codes'].append('CSV_DATE_ORDER_OR_DUPLICATE_INVALID')
            self.issue('CSV_DATES_INVALID', symbol)
            return quote
        good = [(i, row) for i, row in enumerate(rows, 2) if finite_number(row['Close']) is not None and finite_number(row['Close']) > 0]
        if not good:
            quote['issue_codes'].append('NO_VALID_ORIGINAL_CLOSE')
            self.issue('ORIGINAL_CLOSE_MISSING', symbol)
            return quote
        line, row = good[-1]
        quote.update(value=finite_number(row['Close']), adjusted_value=finite_number(row.get('Adj Close')),
                     observation_date=row['Date'], source_csv_line=line)
        if item.get('rows') != len(rows) or item.get('latest_observation') != row['Date'] or row['Date'] != rows[-1]['Date']:
            quote['issue_codes'].append('MANIFEST_CSV_COUNT_OR_DATE_MISMATCH')
            self.issue('MANIFEST_CSV_MISMATCH', symbol)
        if not quote['currency'] or not quote['exchange'] or not quote['instrument_id']:
            quote['issue_codes'].append('INSTRUMENT_IDENTITY_EVIDENCE_MISSING')
        quote['value_state'] = status if status in GOOD and not quote['issue_codes'] else 'UNKNOWN'
        return quote

    def run(self, generated_at=None):
        # Commit failures block before interpreting any source values.
        if self.issues:
            return self.result({}, {}, None, [], [], [], generated_at)
        core = self.json('data/18_macro_verification.json', SCHEMAS['data/18_macro_verification.json'])
        extra = self.json('data/8_macro_supplement_verified.json', SCHEMAS['data/8_macro_supplement_verified.json'])
        formal = self.json(CANONICAL, SCHEMAS[CANONICAL])
        five = self.json('data/wallstreet5_forecasts.json', SCHEMAS['data/wallstreet5_forecasts.json'])
        daily = self.csv('data/macro_safety_daily.csv', ('daily_record_id', 'observation_date', 'score_status', 'health_score', 'source_commit'))
        for d, expected_count, name in [(core, 18, 'macro18'), (extra, 8, 'macro8')]:
            items = (d or {}).get('items')
            if not isinstance(items, dict):
                self.issue('MACRO_ITEMS_INVALID', name)
                continue
            actual_count = len(items) - int(name == 'macro18' and 's03' in items)
            if actual_count != expected_count:
                self.issue('MACRO_ITEM_COUNT_INVALID', name)
            for key, row in items.items():
                if not isinstance(row, dict) or row.get('status') not in GOOD:
                    self.issue('MACRO_STATUS_NOT_USABLE', name + '/' + key)
                elif finite_number(row.get('value')) is None or parse_date(row.get('observation_date')) is None:
                    self.issue('MACRO_VALUE_OR_DATE_INVALID', name + '/' + key)
        if formal:
            v = formal.get('verification', {})
            if not isinstance(v, dict):
                v = {}
            if v.get('ready') is not True or v.get('requiredScoringIndicatorsValidated') != 22:
                self.issue('CANONICAL_FEED_NOT_READY')
            for key, path in [('macro18', 'data/18_macro_verification.json'), ('macro8', 'data/8_macro_supplement_verified.json'), ('wallstreet5', 'data/wallstreet5_forecasts.json'), ('officialReleaseCalendar', 'data/v703_official_monthly_release_calendar.json')]:
                b = self.raw(path)
                if b is None or formal.get('sourceSnapshot', {}).get(key) != git_blob_sha1(b):
                    self.issue('FORMAL_SOURCE_SNAPSHOT_MISMATCH', key)
            # Formal feed is preserved, not recomputed or augmented by research.
            if not isinstance(formal.get('indicators'), dict):
                self.issue('FORMAL_INDICATORS_INVALID')
        quotes = []
        for region in ['global', 'taiwan']:
            p = f'data/market_history/{region}/manifest.json'
            m = self.json(p)
            if not m or m.get('region') != region or not isinstance(m.get('items'), dict):
                self.issue('REGION_MANIFEST_INVALID', region)
                continue
            for symbol, item in sorted(m['items'].items()):
                if not isinstance(item, dict):
                    self.issue('MANIFEST_ITEM_INVALID', symbol)
                    continue
                quotes.append(self.quote(region, symbol, item, m))
        forecasts = (five or {}).get('forecasts', [])
        if not isinstance(forecasts, list) or len(forecasts) != 5:
            self.issue('FIVE_INSTITUTION_COUNT_INVALID')
            forecasts = []
        return self.result(core, extra, formal, forecasts, daily or [], quotes, generated_at)

    def result(self, core, extra, formal, forecasts, daily, quotes, generated_at):
        stamp = generated_at or (formal or {}).get('asOf')
        if stamp:
            try:
                dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    raise ValueError('timezone required')
                stamp = dt.astimezone(ZoneInfo('Asia/Taipei')).isoformat()
            except (ValueError, TypeError, AttributeError):
                self.issue('GENERATED_AT_TIMESTAMP_INVALID')
                stamp = None
        value_state = 'BLOCKED' if self.issues else 'USABLE' if any(q['value_state'] not in GOOD for q in quotes) else 'OK'
        return {'schema': 'LivingWaterAI/p70-5-reader-v1', 'repo': 'a23882005/LivingWaterAI',
            'source_commit': self.commit, 'value_state': value_state,
            'issue_codes': sorted(set(self.issues)),
            'generated_at_taipei': stamp,
            'as_of': (formal or {}).get('asOf'),
            'source_files': [self.source_files[k] for k in sorted(self.source_files)],
            'macro18': core, 'macro8': extra, 'formal_feed': formal,
            'wallstreet5': [{'raw': row, 'use_class': 'DISPLAY_ONLY'} for row in forecasts],
            'daily_macro_history': daily, 'quotes': quotes,
            'research_assets': [], 'research_use_policy': 'RESEARCH_ONLY_NOT_SCORING'}

def read_sources(repo, commit, lock, generated_at=None):
    return SourceReader(repo, commit, lock).run(generated_at)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--source-lock', default=str(Path(__file__).resolve().parents[1] / 'config/p70_5_source_lock.json'))
    p.add_argument('--generated-at-taipei')
    a = p.parse_args(argv)
    try:
        lock = strict_json(Path(a.source_lock).read_bytes())
        result = read_sources(a.repo, a.commit, lock, a.generated_at_taipei)
    except (OSError, ValueError, TypeError) as exc:
        result = {'schema': 'LivingWaterAI/p70-5-reader-v1', 'source_commit': a.commit,
                  'value_state': 'BLOCKED', 'issue_codes': ['SOURCE_LOCK_UNREADABLE:' + type(exc).__name__]}
    out = Path(a.out).resolve()
    repo = Path(a.repo).resolve()
    if out.is_relative_to(repo) and not out.is_relative_to(repo / 'build'):
        p.error('--out within repo must be under build/; sources are read-only')
    out.mkdir(parents=True, exist_ok=True)
    b = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    (out / 'reader_result.json').write_bytes(b)
    print(json.dumps({'value_state': result['value_state'], 'issue_codes': result['issue_codes'], 'output_sha256': content_sha256(b)}, ensure_ascii=False))
    return 2 if result['value_state'] == 'BLOCKED' else 0

if __name__ == '__main__':
    raise SystemExit(main())
