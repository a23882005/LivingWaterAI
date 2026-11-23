"""Official publishers for the existing m14/m13/m17 definitions; no FRED calls."""
import datetime as dt
from decimal import Decimal
import hashlib
import io
import math
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlparse
from scripts import m14_holiday_rrp as holiday

H41 = 'https://www.federalreserve.gov/releases/h41/data/FRB_h41_xml.zip'
NAMES = {'WALCL': 'RESPPMA_N.WW', 'WDTGAL': 'RESPPLLDT_N.WW'}


def parsed_h41(raw, today):
    """Select consolidated total assets and total TGA, Wednesday levels, USD millions."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if 'H41_data.xml' not in z.namelist():
            raise ValueError('H41_data.xml missing')
        with z.open('H41_data.xml') as source:
            for _, e in ET.iterparse(source, events=('end',)):
                if e.tag.rsplit('}', 1)[-1] != 'Series':
                    continue
                name = next((k for k, v in NAMES.items() if v == e.get('SERIES_NAME')), None)
                if name:
                    if name in out:
                        raise ValueError('H41 duplicate series')
                    if any(e.get(k) != v for k, v in
                           {'FREQ': '19', 'SERIESTYPE': 'L', 'UNIT': 'Currency',
                            'UNIT_MULT': '1000000', 'CURRENCY': 'USD',
                            'DISTRIBUTION': 'TOTC' if name == 'WALCL' else 'TOT'}.items()):
                        raise ValueError('H41 wrong frequency/unit/level/distribution')
                    values = {}
                    for x in e:
                        if x.tag.rsplit('}', 1)[-1] != 'Obs':
                            continue
                        day = dt.date.fromisoformat(x.get('TIME_PERIOD'))
                        if x.get('OBS_STATUS') != 'A' or day > today:
                            continue
                        val = Decimal(x.get('OBS_VALUE'))
                        if not val.is_finite() or val < 0 or day.weekday() != 2:
                            raise ValueError('H41 invalid Wednesday observation')
                        if day in values and values[day] != val:
                            raise ValueError('H41 contradictory observation')
                        values[day] = val
                    if not values:
                        raise ValueError('H41 empty selected series')
                    out[name] = {'metadata': dict(e.attrib), 'values': values}
                e.clear()
    if set(out) != set(NAMES):
        raise ValueError('H41 required series absent')
    return out


def normal_rrp(day, raw, calendar):
    if not holiday.open_day(day, calendar):
        raise ValueError('normal RRP requires an open day')
    ops = list(holiday.unique(holiday.operations(raw)).values())
    if any(o['operationDate'] != day.isoformat() for o in ops):
        raise ValueError('NYFed daily response outside requested day')
    selected = [o for o in ops if
                (o.get('operationType'), o.get('term'), o.get('auctionStatus')) ==
                ('Reverse Repo', 'Overnight', 'Results')]
    if not selected:
        raise ValueError('No confirmed Treasury ON RRP result; empty is not zero')
    total = Decimal(0)
    for o in selected:
        if (o.get('settlementDate') != day.isoformat() or
                o.get('maturityDate') != holiday.next_open(day, calendar).isoformat()):
            raise ValueError('NYFed ON RRP settlement/maturity mismatch')
        details = o['details']
        if len(details) != 1 or details[0]['securityType'] != 'Treasury':
            raise ValueError('Treasury-only RRP identity required')
        amount = Decimal(str(details[0]['amtAccepted']))
        if not amount.is_finite() or amount < 0 or amount != Decimal(str(o['totalAmtAccepted'])):
            raise ValueError('RRP amount mismatch')
        total += amount
    return total / Decimal(10)**9


def netliq(f, today=None):
    now = dt.datetime.now(dt.timezone.utc)
    today = today or now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    receipts = {}
    def get(url):
        r = f.s.get(url, timeout=(5, f.timeout))
        r.raise_for_status()
        actual = urlparse(getattr(r, 'url', None) or url)
        requested = urlparse(url)
        if actual.scheme != 'https' or actual.hostname != requested.hostname or actual.path != requested.path:
            raise ValueError('Official response redirected away from selected resource')
        raw = r.content
        receipts[url] = {'url': url, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                         'response_sha256': hashlib.sha256(raw).hexdigest(), 'response_bytes': len(raw)}
        return raw
    weekly = parsed_h41(get(H41), today)
    ends = [max(weekly[n]['values']) for n in NAMES]
    if len(set(ends)) != 1:
        raise ValueError('H41 weekly series not current on same Wednesday')
    end = ends[0]
    begin = end - dt.timedelta(days=91)
    if (today - end).days > 12:
        raise ValueError('H41 latest Wednesday older than original 12-day limit')
    calendar = get(holiday.HOLIDAYS)
    endpoints = {}
    derived = {}
    for day in (begin, end):
        if any(day not in weekly[n]['values'] for n in NAMES):
            raise ValueError('H41 exact 91-day endpoint missing')
        if holiday.open_day(day, calendar):
            raw = get(holiday.query_url(day, day))
            rrp = normal_rrp(day, raw, calendar)
        else:
            # Preserve the original holiday contract completeness and maturity rules.
            d = holiday.fetch_holiday(f, day)
            derived[day.isoformat()] = d
            rrp = Decimal(str(d['value_usd_bn']))
        parts = {n: float(weekly[n]['values'][day]) for n in NAMES}
        parts['RRPONTSYD'] = float(rrp)
        endpoints[day.isoformat()] = parts
    def level(k):
        p = endpoints[k]
        return Decimal(str(p['WALCL']))/1000 - Decimal(str(p['WDTGAL']))/1000 - Decimal(str(p['RRPONTSYD']))
    value = float(level(end.isoformat()) - level(begin.isoformat()))
    if not math.isfinite(value):
        raise ValueError('Nonfinite official netliq')
    evidence = {'schema': 'V70.3/netliq-official-publishers-v1',
                'formula': '(WALCL/1000-WDTGAL/1000-RRPONTSYD)[end] minus [begin]',
                'begin': begin.isoformat(), 'end': end.isoformat(), 'endpoints': endpoints,
                'weekly_metadata': {n: weekly[n]['metadata'] for n in NAMES},
                'sources': list(receipts.values()), 'holiday_outstanding': derived,
                'rule_version': holiday.RULE, 'provider': 'FED_NYFED_DIRECT'}
    diagnostics = {'schema': 'V70.3/netliq-date-intersection-v1',
                   'policy': 'SAME_WEDNESDAY_EXACT_91_DAYS_HOLIDAY_OUTSTANDING',
                   'status': 'ALIGNED', 'source_units': {'WALCL': 'USD million', 'WDTGAL': 'USD million', 'RRPONTSYD': 'USD billion'},
                   'selected_begin': begin.isoformat(), 'selected_end': end.isoformat(),
                   'holiday_outstanding_dates': sorted(derived), 'values_at_required_dates': endpoints}
    f.netliq_diagnostics = diagnostics
    return value, end.isoformat(), evidence
