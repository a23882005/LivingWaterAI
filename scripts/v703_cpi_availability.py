"""Narrow, source-verified CPI data-only exception. Never invent a YoY value."""
import csv
import datetime as dt
import hashlib
import html
import io
import math
import re

FRED_CPI = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPILFESL'
BLS_CPI = 'https://www.bls.gov/news.release/cpi.htm'
REASON = 'CPI_YOY_BASE_PERIOD_MISSING'
NOTICE = '官方資料不足：2025-10 同比基期缺失，2026-10 核心 CPI 年增率無法計算；正式總分停算。'


def _text(raw):
    value = raw.decode('utf-8', 'replace')
    value = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', ' ', value, flags=re.I|re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value)))


def verify_official_gap(csv_raw, bls_raw, now):
    """Only October 2026's documented absent October 2025 denominator qualifies."""
    if now.tzinfo is None:
        raise ValueError('CPI verification clock must be aware')
    rows = list(csv.DictReader(io.StringIO(csv_raw.decode('utf-8-sig'))))
    values = {}
    for row in rows:
        day = row.get('DATE') or row.get('observation_date')
        if not day or 'CPILFESL' not in row:
            raise ValueError('CPI CSV identity/date column invalid')
        raw = row['CPILFESL'].strip()
        if raw in ('', '.'):
            values[day] = None
        else:
            value = float(raw)
            if not math.isfinite(value) or value <= 0:
                raise ValueError('CPI index must be finite and positive')
            values[day] = value
    current = max((day for day, value in values.items() if value is not None), default='')
    if current != '2026-10-01' or values.get('2025-10-01') is not None:
        return None
    # Missing row and explicit missing value both require the same official notice.
    page = _text(bls_raw)
    required = ('CONSUMER PRICE INDEX - OCTOBER 2026',
                'BLS did not collect survey data for October 2025',
                'BLS cannot publish 12-month percent changes for October 2026',
                'November 10, 2026',
                'The Consumer Price Index news release for November 2026 is scheduled to be published on Thursday, December 10, 2026, at 8:30 a.m. (ET).')
    if not all(part in page for part in required):
        raise ValueError('CPI missing base is not confirmed by the current official release')
    published = dt.datetime(2026,11,10,13,30,tzinfo=dt.timezone.utc)
    expires = dt.datetime(2026,12,10,13,30,tzinfo=dt.timezone.utc)
    if not published <= now < expires:
        raise ValueError('CPI official-unavailability exception outside its release window')
    return {'schema':'V70.3/cpi-official-unavailability-v1', 'reason':REASON,
            'observationMonth':'2026-10', 'missingBaseMonth':'2025-10',
            'currentIndex':values[current], 'baseIndex':None,
            'publicationDate':'2026-11-10', 'nextReleaseAtUtc':expires.isoformat(),
            'verifiedAtUtc':now.isoformat(), 'sourceUrl':BLS_CPI, 'seriesUrl':FRED_CPI,
            'sourceSha256':hashlib.sha256(bls_raw).hexdigest(),
            'seriesSha256':hashlib.sha256(csv_raw).hexdigest(), 'message':NOTICE}


def valid_official_gap(evidence, now):
    """Validate exact evidence contract and freshness; no status-only exception."""
    if not isinstance(evidence, dict) or now.tzinfo is None:
        return False
    try:
        verified = dt.datetime.fromisoformat(evidence['verifiedAtUtc'].replace('Z','+00:00'))
        expires = dt.datetime.fromisoformat(evidence['nextReleaseAtUtc'].replace('Z','+00:00'))
        index = evidence['currentIndex']
        return (evidence.get('schema') == 'V70.3/cpi-official-unavailability-v1'
                and evidence.get('reason') == REASON
                and evidence.get('observationMonth') == '2026-10'
                and evidence.get('missingBaseMonth') == '2025-10'
                and evidence.get('publicationDate') == '2026-11-10'
                and expires == dt.datetime(2026,12,10,13,30,tzinfo=dt.timezone.utc)
                and dt.datetime(2026,11,10,13,30,tzinfo=dt.timezone.utc) <= verified <= now+dt.timedelta(minutes=5)
                and now-verified < dt.timedelta(hours=26) and now < expires
                and not isinstance(index,bool) and isinstance(index,(int,float)) and math.isfinite(index) and index > 0
                and evidence.get('baseIndex') is None
                and evidence.get('sourceUrl') == BLS_CPI and evidence.get('seriesUrl') == FRED_CPI
                and all(re.fullmatch('[0-9a-f]{64}', evidence.get(k,'')) for k in ('sourceSha256','seriesSha256')))
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
