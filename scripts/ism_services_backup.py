"""Original approved ISM headline parser, scoped to the services backup route.

Parsing is retained from P01 parse_ism (also replayed in the PM R2 run).
The wrapper preserves macro18 month-start dates and its current target period.
"""
import calendar
import re
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser

SERVICES_BACKUP_URL = 'https://tradingeconomics.com/united-states/non-manufacturing-pmi'


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)


def plain(body):
    parser = _Text()
    parser.feed(body.decode('utf-8', errors='replace'))
    return ' '.join(' '.join(parser.parts).split())


def parse_ism(body, key):
    """Bind the headline, period and dated news item; ignore forecasts/subindices."""
    html = body.decode('utf-8', errors='replace')
    kind, ticker = {'m04': ('Manufacturing', 'NAPMPMI'),
                    'm15': ('Services', 'UNITEDSTANONMANPMI')}[key]
    title = 'United States ISM ' + kind + ' PMI'
    if not re.search(r"TEAlertsName\s*=\s*['\"]" + re.escape(title) + r"['\"]", html):
        raise ValueError('ISM_HEADLINE_IDENTITY_NOT_BOUND')
    if not re.search(r"TESymbol\s*=\s*['\"]" + ticker + r"['\"]", html):
        raise ValueError('ISM_SERIES_MISMATCH')
    if 'Institute for Supply Management' not in plain(body):
        raise ValueError('ISM_ORIGIN_NOT_IDENTIFIED')
    main = re.search(r'<h2\b[^>]*\bid="description"[^>]*>(.*?)</h2>', html, re.S | re.I)
    if not main:
        raise ValueError('ISM_HEADLINE_MISSING')
    pattern = (r'The ISM ' + kind + r' PMI\s+[^.]{0,65}?\bto\s+(\d+(?:\.\d+)?)'
               r'\s+in\s+([A-Z][a-z]+)\s+(\d{4})\b')
    headline = plain(main[1].encode())
    match = re.search(pattern, headline)
    if not match:
        raise ValueError('ISM_HEADLINE_VALUE_OR_PERIOD_MISSING')
    value = Decimal(match[1])
    if not value.is_finite() or not 0 <= value <= 100:
        raise ValueError('ISM_VALUE_OUTSIDE_RANGE')
    period = datetime.strptime(match[2] + ' ' + match[3], '%B %Y').date()
    day = date(period.year, period.month, calendar.monthrange(period.year, period.month)[1])
    releases = []
    for text, published in re.findall(
            r'<div\b[^>]*class="comment more"[^>]*>(.*?)</div>\s*'
            r'<small\b[^>]*class="te-stream-date"[^>]*>(\d{4}-\d{2}-\d{2})</small>', html, re.S):
        news = re.search(pattern, plain(text.encode()))
        if news and (Decimal(news[1]), news[2], news[3]) == (value, match[2], match[3]):
            releases.append(published)
    if len(set(releases)) != 1:
        raise ValueError('ISM_RELEASE_DATE_NOT_BOUND_TO_SAME_HEADLINE')
    published = date.fromisoformat(releases[0])
    if published <= day or (published - day).days > 15:
        raise ValueError('ISM_RELEASE_PERIOD_CONFLICT')
    return str(value), day.isoformat(), published.isoformat(), {
        'observation_period': day.strftime('%Y-%m'),
        'observation_date_normalization': 'MONTH_END_OF_STATED_REFERENCE_MONTH',
        'headline_excerpt': headline[:450], 'series_symbol': ticker,
        'release_date_basis': 'Dated news item with the identical headline value and reference period',
        'not_selected': 'forecast widgets, services business activity and manufacturing subindices',
        'source_origin': 'Institute for Supply Management; Trading Economics distribution',
    }


def parse_services_pmi(body, target_month, today):
    value, month_end, published, details = parse_ism(body, 'm15')
    if month_end[:7] != target_month:
        raise ValueError('ISM_BACKUP_WRONG_TARGET_MONTH')
    if date.fromisoformat(published) > today:
        raise ValueError('ISM_BACKUP_FUTURE_PUBLICATION')
    # Keep the original macro18 monthly convention; do not label month-end as
    # the actual publication date or change the original input frequency.
    details['original_month_end'] = month_end
    details['observation_date_normalization'] = 'MONTH_START_OF_STATED_REFERENCE_MONTH'
    details['headline_excerpt'] = ' '.join(details['headline_excerpt'].split()[:18])
    return float(value), target_month + '-01', published, details
