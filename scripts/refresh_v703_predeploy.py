#!/usr/bin/env python3
"""Refresh V70.3 official evidence before deployment; preserve stale rows' real dates."""
import datetime as dt
import argparse
import base64
import copy
import gzip
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TPE = dt.timezone(dt.timedelta(hours=8))
P8 = ROOT/'data/8_macro_supplement_verified.json'
P18 = ROOT/'data/18_macro_verification.json'
PCAL = ROOT/'data/v703_official_monthly_release_calendar.json'
FED = 'https://www.federalreserve.gov/monetarypolicy/openmarket.htm'
ISM = 'https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/october/'
ISM_CAL = 'https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/'
ISM_MANUFACTURING_PDF = 'https://www.ismworld.org/globalassets/pub/research-and-surveys/rob/pmi/r4in202610pmi.pdf'
BLS_EMP_CAL = 'https://www.bls.gov/schedule/news_release/empsit.htm'
CALENDAR_TARGETS = ('m15', 'm18', 'm19', 'm20')
# ISM's own named release on its existing public distribution channel. The
# canonical ISM calendar remains the schedule reference; the evidence records
# the actual delivery URL, without representing it as an ISM HTTP response.
ISM_SERVICES_RELEASES = {
    '2026-10': 'https://www.prnewswire.com/news-releases/services-pmi-at-54-5-october-2026-ism-services-pmi-report-302928112.html',
}


def _next_month(month):
    day = dt.date.fromisoformat(month + '-01')
    return (day.replace(day=28) + dt.timedelta(days=4)).strftime('%Y-%m')


def _utc_time(value):
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('calendar verification time requires a timezone')
    return stamp.astimezone(dt.timezone.utc)


def _eastern_time(value):
    return value.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(dt.timezone.utc)


def parse_employment_schedule(raw):
    """Bind each reference month to its BLS release date and local clock."""
    text = clean(raw)
    if 'Schedule of Releases for the Employment Situation' not in text:
        raise ValueError('BLS Employment Situation calendar identity missing')
    rows = {}
    for row in re.findall(rb'<tr\b[^>]*>(.*?)</tr>', raw, re.S | re.I):
        cells = [clean(cell) for cell in re.findall(rb'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        if len(cells) != 3:
            continue
        try:
            period = dt.datetime.strptime(cells[0], '%B %Y').strftime('%Y-%m')
            release = dt.datetime.strptime(cells[1].replace('.', '') + ' ' + cells[2], '%b %d, %Y %I:%M %p')
        except ValueError:
            continue
        if period in rows:
            raise ValueError('duplicate BLS reference month')
        rows[period] = _eastern_time(release)
    if not rows:
        raise ValueError('BLS reference month/date/time rows missing')
    return rows


def parse_ism_services_schedule(raw, period):
    """Read dated ISM release prose, or the actual Services calendar column."""
    text = clean(raw)
    observed = dt.datetime.strptime(period, '%Y-%m')
    following = dt.datetime.strptime(_next_month(period), '%Y-%m')
    if ('News provided by Institute for Supply Management' in text
            and 'SOURCE Institute for Supply Management' in text):
        if not re.search(re.escape(observed.strftime('%B %Y')) + r' ISM\s*®? Services PMI', text):
            raise ValueError('ISM Services reference month/report identity mismatch')
        pub = re.search(r'News provided by Institute for Supply Management\s+([A-Z][a-z]{2} \d{1,2}, \d{4}),\s*(\d{1,2}:\d{2}) ET', text)
        upcoming = re.search(r'The next ISM\s*®? Services PMI\s*®? Report featuring '
            + re.escape(following.strftime('%B %Y'))
            + r' data will be released at (\d{1,2}:\d{2})\s*(a\.m\.|p\.m\.) ET on [A-Z][a-z]+, ([A-Z][a-z]+ \d{1,2}, \d{4})', text)
        if not pub or not upcoming:
            raise ValueError('ISM published release or next-report timestamp missing')
        published = dt.datetime.strptime(pub[1] + ' ' + pub[2], '%b %d, %Y %H:%M')
        next_at = dt.datetime.strptime(upcoming[3] + ' ' + upcoming[1] + ' ' + upcoming[2].replace('.', ''), '%B %d, %Y %I:%M %p')
        return _eastern_time(published), _eastern_time(next_at), 'ISM_PUBLISHER_DISTRIBUTED_RELEASE'
    if 'Release Dates for the ISM Manufacturing and Services' not in text:
        raise ValueError('ISM calendar identity missing or login/challenge response')
    if not re.search(r'Services.*?10:00\s*a\.m\..*?\(EST\)', text):
        raise ValueError('ISM Services official release clock missing')
    schedule = {}
    for row in re.findall(rb'<tr\b[^>]*>(.*?)</tr>', raw, re.S | re.I):
        cells = [clean(c) for c in re.findall(rb'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        if len(cells) == 3 and re.fullmatch(r'[A-Z][a-z]+ 20\d{2}', cells[0]):
            match = re.fullmatch(r'(\d{1,2})(?:\*+)?', cells[2])
            if match:
                month = dt.datetime.strptime(cells[0], '%B %Y')
                schedule[month.strftime('%Y-%m')] = _eastern_time(month.replace(day=int(match[1]), hour=10))
    current_month, next_month = _next_month(period), _next_month(_next_month(period))
    if current_month not in schedule or next_month not in schedule:
        raise ValueError('ISM Services current/next calendar row missing')
    return schedule[current_month], schedule[next_month], 'ISM_OFFICIAL_CALENDAR'


def parse_sahm_release_dates(raw):
    if 'Sahm Rule Recession Indicator' not in clean(raw):
        raise ValueError('FRED Sahm release identity missing')
    dates = set()
    for row in re.finditer(rb'<tr\b[^>]*>\s*<td[^>]*>\s*<span[^>]*>(.*?)</span>.*?</tr>\s*<tr[^>]*>(.*?)</tr>', raw, re.S | re.I):
        if not re.search(rb'href=[\"\']/release\?rid=456[\"\']', row[2]):
            continue
        dates.add(dt.datetime.strptime(clean(row[1]), '%A %B %d, %Y').date())
    if not dates:
        raise ValueError('FRED release 456 dated rows missing')
    return dates


def _calendar_evidence(source, expected_url, now):
    if source['url'] != expected_url or source.get('final_url') != expected_url:
        raise ValueError('calendar evidence URL/redirect mismatch')
    raw = source['raw']
    if (source.get('http_status') != 200 or len(raw) != source['response_bytes']
            or hashlib.sha256(raw).hexdigest() != source['response_sha256']):
        raise ValueError('calendar evidence HTTP/hash/size mismatch')
    if _utc_time(source['fetched_at_utc']) > now:
        raise ValueError('calendar evidence verification time is in the future')
    return {key: value for key, value in source.items() if key != 'raw'}


def apply_monthly_calendar_updates(calendar, core, sources, now):
    """Update independently evidenced rows; a failed row retains its full state."""
    if not isinstance(now, str) and now.tzinfo is None:
        raise ValueError('calendar verification clock requires a timezone')
    now = _utc_time(now) if isinstance(now, str) else now.astimezone(dt.timezone.utc)
    result = copy.deepcopy(calendar)
    outcomes = {}
    for key in CALENDAR_TARGETS:
        try:
            period = core['items'][key]['observation_date'][:7]
            dt.date.fromisoformat(period + '-01')
            if key == 'm15':
                source = sources['ism']
                expected = ISM_SERVICES_RELEASES.get(period, ISM_CAL)
                evidence = [_calendar_evidence(source, expected, now)]
                published, upcoming, basis = parse_ism_services_schedule(source['raw'], period)
                canonical = ISM_CAL
            else:
                bls = sources['bls']
                evidence = [_calendar_evidence(bls, BLS_EMP_CAL, now)]
                rows = parse_employment_schedule(bls['raw'])
                published, upcoming = rows[period], rows[_next_month(period)]
                zone_url = f'https://www.bls.gov/schedule/{upcoming.year}/{upcoming.month:02d}_sched.htm'
                zone = sources.get('bls_timezones', {}).get(zone_url) or sources['bls_timezone']
                evidence.append(_calendar_evidence(zone, zone_url, now))
                if 'All times on calendar are Eastern Time' not in clean(zone['raw']):
                    raise ValueError('BLS official timezone evidence missing')
                canonical, basis = BLS_EMP_CAL, 'BLS_EMPLOYMENT_SITUATION_EASTERN_TIME'
                if key == 'm18':
                    fred = sources['fred']
                    canonical = f'https://fred.stlouisfed.org/releases/calendar?rid=456&y={published.year}'
                    evidence.append(_calendar_evidence(fred, canonical, now))
                    dates = parse_sahm_release_dates(fred['raw'])
                    if published.date() not in dates or upcoming.date() not in dates:
                        raise ValueError('FRED Sahm dates disagree with BLS release dates')
                    # FRED publishes release dates, not an availability promise.
                    # Expire at the verified upstream BLS release time, never
                    # extend yesterday's Sahm value while waiting for FRED.
                    basis = 'FRED_RELEASE_DATE_WITH_CONSERVATIVE_UPSTREAM_BLS_CUTOFF'
            if not dt.date.fromisoformat(period + '-01') <= published.date() or not published <= now < upcoming:
                raise ValueError('observation not yet released or next release already reached')
            row = {'observation_month':period, 'publication_date':published.date().isoformat(),
                'publication_at_utc':published.isoformat().replace('+00:00','Z'),
                'next_release_at_utc':upcoming.isoformat().replace('+00:00','Z'),
                'release_timezone':'America/New_York', 'calendar_source_url':canonical,
                'release_time_basis':basis, 'source_evidence':evidence,
                'last_verified_at_utc':max(e['fetched_at_utc'] for e in evidence)}
            if key == 'm18':
                row['fred_posting_time_claimed'] = False
            result['items'][key] = row
            outcomes[key] = {'status':'VERIFIED','observation_month':period,'next_release_at_utc':row['next_release_at_utc']}
        except (ValueError, KeyError, TypeError) as exc:
            outcomes[key] = {'status':'RETAINED_UNVERIFIED','error':type(exc).__name__+': '+str(exc)}
    verified = [row['last_verified_at_utc'] for key,row in result['items'].items()
                if key in CALENDAR_TARGETS and outcomes[key]['status']=='VERIFIED']
    if verified:
        result['checked_at_utc'] = max(verified)
    result['target_refresh_results'] = outcomes
    return result, outcomes


def refresh_monthly_release_calendars(session, core, calendar):
    """Fetch each source once; archive evidence and continue other targets on failure."""
    sources = {}
    def obtain(name, url):
        try:
            response = session.get(url, timeout=(6,18))
            response.raise_for_status()
            raw = response.content
            if len(raw) < 100:
                raise ValueError('short calendar response')
            digest = hashlib.sha256(raw).hexdigest()
            fetched = dt.datetime.now(dt.timezone.utc).isoformat()
            path = ROOT/'data/audit'/('monthly_calendar_'+digest+'.html.gz')
            path.parent.mkdir(parents=True, exist_ok=True)
            archive_kind = 'ORIGINAL_HTTP_GZIP'
            if name == 'ism':
                # Keep the calendar facts and full-response fingerprint, not a
                # republication of the publisher's entire PMI news report.
                published, upcoming, basis = parse_ism_services_schedule(raw, period)
                facts = {'schema':'V703_ISM_CALENDAR_FACTS_1','url':url,
                    'publisher':'Institute for Supply Management','observation_month':period,
                    'publication_at_utc':published.isoformat().replace('+00:00','Z'),
                    'next_release_at_utc':upcoming.isoformat().replace('+00:00','Z'),
                    'release_time_basis':basis,'fetched_at_utc':fetched,
                    'original_response_sha256':digest,'original_response_bytes':len(raw)}
                fact_bytes = (json.dumps(facts,ensure_ascii=False,indent=2)+'\n').encode('utf8')
                # The acquisition clock changes even when the HTTP body does
                # not. Address these facts by their own bytes so another refresh
                # cannot overwrite the original used by a frozen acceptance test.
                path = path.parent/('monthly_calendar_facts_'+hashlib.sha256(fact_bytes).hexdigest()+'.json')
                path.write_bytes(fact_bytes)
                archive_kind = 'EXTRACTED_CALENDAR_FACTS_JSON'
            else:
                path.write_bytes(gzip.compress(raw, mtime=0))
            sources[name] = {'url':url,'final_url':response.url,'http_status':response.status_code,
                'fetched_at_utc':fetched,
                'response_sha256':digest,'response_bytes':len(raw),
                'archive_path':str(path.relative_to(ROOT)), 'archive_kind':archive_kind,
                'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'raw':raw}
        except (OSError, ValueError) as exc:
            print('CALENDAR_SOURCE_UNAVAILABLE',name,type(exc).__name__,flush=True)
    period = core['items']['m15']['observation_date'][:7]
    obtain('ism', ISM_SERVICES_RELEASES.get(period, ISM_CAL))
    obtain('bls', BLS_EMP_CAL)
    try:
        rows = parse_employment_schedule(sources['bls']['raw'])
    except (ValueError, KeyError):
        rows = {}
    sources['bls_timezones'] = {}
    for key in ('m18','m19','m20'):
        try:
            upcoming = rows[_next_month(core['items'][key]['observation_date'][:7])]
            url = f'https://www.bls.gov/schedule/{upcoming.year}/{upcoming.month:02d}_sched.htm'
            if url in sources['bls_timezones']:
                continue
            obtain('bls_timezone',url)
            if 'bls_timezone' in sources:
                sources['bls_timezones'][url] = sources.pop('bls_timezone')
        except (ValueError, KeyError):
            continue
    try:
        published = rows[core['items']['m18']['observation_date'][:7]]
        obtain('fred',f'https://fred.stlouisfed.org/releases/calendar?rid=456&y={published.year}')
    except (ValueError, KeyError):
        pass
    result, outcomes = apply_monthly_calendar_updates(calendar, core, sources, dt.datetime.now(dt.timezone.utc))
    # The original deployment workflow already commits PCAL. Carry the small
    # referenced archives inside that file too, so a future HTTP-body change
    # cannot leave a committed calendar pointing only at an untracked CI file.
    archives = dict(calendar.get('source_archives', {}))
    for row in result['items'].values():
        for evidence in row.get('source_evidence', []):
            digest = evidence['archive_sha256']
            if digest in archives:
                continue
            raw = (ROOT/evidence['archive_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('calendar archive fingerprint mismatch')
            archives[digest] = {'kind':evidence['archive_kind'],'bytes':len(raw),
                'base64':base64.b64encode(raw).decode('ascii')}
    needed = {e['archive_sha256'] for row in result['items'].values() for e in row.get('source_evidence', [])}
    result['source_archives'] = {key:archives[key] for key in sorted(needed)}
    print('MONTHLY_CALENDAR_RESULTS',json.dumps(outcomes,ensure_ascii=False),flush=True)
    return result


def clean(b):
    s=b.decode('utf8','replace')
    s=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>',' ',s,flags=re.I|re.S)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',s)))


def fetch(session,url):
    r=session.get(url,timeout=(6,18))
    r.raise_for_status()
    if len(r.content)<100: raise ValueError('short response '+url)
    return r.content


# Match the existing official macro collector's successful transport settings.
CPI_OFFICIAL_HEADERS = {
    'User-Agent':'LivingWaterAI-MacroCollector/1.3 (+GitHub Actions; official data research)',
    'Accept':'application/json,text/csv,text/plain,*/*',
    'Accept-Language':'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding':'gzip, deflate',
    'Connection':'keep-alive',
}


def fetch_cpi_official_evidence(session, url):
    """Retry transient official-source failures only; never substitute cached evidence."""
    import requests

    for attempt in range(3):
        try:
            response = session.get(url, timeout=(10, 60), headers=CPI_OFFICIAL_HEADERS)
            response.raise_for_status()
            raw = response.content
            if len(raw) < 100:
                raise ValueError('short response ' + url)
            return raw
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            transient = (isinstance(exc, (requests.Timeout, requests.ConnectionError))
                         or status == 429 or (status is not None and 500 <= status <= 599))
            # Certificate/access failures are not transient availability failures.
            if isinstance(exc, requests.exceptions.SSLError) or not transient or attempt == 2:
                raise
            time.sleep(attempt + 1)


def revise_candidate(row,site,stamp,value,date,note):
    for c in row['candidate_checks']:
        if c['site']==site:
            c.update(status='FOUND',checked_at=stamp,value=value,observation_date=date,notes=note)
            return
    raise ValueError('candidate site missing '+site)



def parse_mmfi_eod(raw, today, market_now=None):
    """Pick the last completed NYSE daily close; ignore current US intraday rows."""
    page=clean(raw)
    if not re.search(r'INDEX\s*,\s*MMFI\s*:\s*Percent of Stocks Above 50-Day Average',page,re.I):
        raise ValueError('EOD source is not exact INDEX/MMFI 50-day breadth')
    if 'RECENT END OF DAY PRICES' not in page:
        raise ValueError('EOD latest daily table missing')
    rows=page.split('RECENT END OF DAY PRICES',1)[1].split('SYMBOL HISTORY',1)[0][:1300]
    dated=list(re.finditer(r'\b\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\b',rows))
    if not dated:
        raise ValueError('EOD dated table has no observation dates')
    market_now=market_now or dt.datetime.now(ZoneInfo('America/New_York'))
    if market_now.tzinfo is None:
        raise ValueError('market clock must be timezone aware')
    local=market_now.astimezone(ZoneInfo('America/New_York'))
    first_date=dt.datetime.strptime(dated[0].group(0),'%d %b %y').date()
    # EODData can populate "daily" rows during an active NY session.
    # Keep the last *completed* session: require 17:00 ET for same-day close.
    is_intraday=first_date==local.date() and local.time()<dt.time(17,0)
    chosen=1 if is_intraday else 0
    if chosen>=len(dated):
        raise ValueError('EOD latest NY session still open and last closed row missing')
    fragment=rows[dated[chosen].start():(dated[chosen+1].start() if chosen+1<len(dated) else len(rows))]
    found=re.match(
        r'\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s+'
        r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+'
        r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+\d+\b',
        fragment)
    if not found:
        raise ValueError('EOD latest closed row lacks complete OHLC close')
    observed=dt.datetime.strptime(found.group(1),'%d %b %y').date()
    if observed>today or observed>local.date():
        raise ValueError('EOD quote has future date')
    value=float(found.group(5))
    if not 0<=value<=100:
        raise ValueError('EOD MMFI close must be percent in 0..100')
    if not (float(found.group(4))<=value<=float(found.group(3))):
        raise ValueError('EOD close outside daily high/low')
    return value,observed.isoformat()



def manufacturing_headline_from_official_pdf(raw):
    """Read only the dated headline table, not a same-valued component index."""
    import io,logging
    from pypdf import PdfReader
    if not raw.startswith(b'%PDF-') or len(raw)>2*1024*1024:raise ValueError('ISM official PDF format/size invalid')
    reader=PdfReader(io.BytesIO(raw))
    if not 1<=len(reader.pages)<=6:raise ValueError('ISM official PDF page limit exceeded')
    logger=logging.getLogger('pypdf');level=logger.level
    try:
        logger.setLevel(logging.ERROR)
        content=re.sub(r'\s+',' ',' '.join(page.extract_text() or '' for page in reader.pages))
    finally:logger.setLevel(level)
    if not re.search(r'October\s+2026',content,re.I) or 'Institute for Supply Management' not in content:raise ValueError('ISM official PDF period/publisher missing')
    headline=re.search(r'\bManufacturing\s+PMI[®\s]*(\d{1,2}(?:\.\d+)?)\s+(\d{1,2}(?:\.\d+)?)\s+[+-]\d',content)
    if not headline or tuple(map(float,headline.groups()))!=(55.5,54.5):raise ValueError('ISM official PDF headline table mismatch')
    return float(headline[1])

def refresh_manufacturing_headline(session):
    """Use the publisher release, then its public PDF on distributor HTTP failure.

    Exact October headline and source identity remain mandatory. No login bypass,
    cached success, freshness extension or new indicator definition is introduced.
    A fetched distributor content mismatch still blocks; it is not masked by PDF.
    """
    import requests
    distributed='https://www.prnewswire.com/news-releases/manufacturing-pmi-at-55-5-october-2026-ism-manufacturing-pmi-report-302925617.html'
    def verified_headline(content):
        if 'October 2026' not in content:return None
        for pattern in (r'Manufacturing\s+PMI\s*®?\s*(?:at|registered)\s+(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)',
                        r'Manufacturing\s+PMI.{0,30}?(?:at|registered)\s+(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)'):
            hit=re.search(pattern,content,re.I)
            if hit and float(hit.group(1))==55.5:return 55.5
        return None
    try:
        raw=fetch(session,ISM)
    except requests.RequestException as exc:
        print('ISM_PRIMARY_HTTP_UNAVAILABLE',type(exc).__name__,flush=True)
        raw=b''
    value=verified_headline(clean(raw))
    if value is not None:return value,ISM
    print('ISM_OFFICIAL_DIRECT_NOT_PARSED_OR_HTTP_FAILED',flush=True)
    try:raw=fetch(session,distributed)
    except requests.RequestException as exc:
        print('ISM_DISTRIBUTED_HTTP_UNAVAILABLE',type(exc).__name__,flush=True)
        raw=fetch(session,ISM_MANUFACTURING_PDF)
        value=manufacturing_headline_from_official_pdf(raw)
        print('ISM_OFFICIAL_PDF_HEADLINE_PASS',hashlib.sha256(raw).hexdigest(),flush=True)
        return value,ISM_MANUFACTURING_PDF
    content=clean(raw)
    if ('News provided by Institute for Supply Management' not in content
            or 'SOURCE Institute for Supply Management' not in content):
        raise ValueError('ISM distributed publisher identity missing')
    value=verified_headline(content)
    if value is None:raise ValueError('ISM October headline not independently verified')
    print('ISM_DISTRIBUTED_HEADLINE_PASS',hashlib.sha256(raw).hexdigest(),flush=True)
    return value,distributed


def main(calendar_only=False):
    import requests

    session=requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0 (compatible; LivingWaterAI-V703/1.0)',
                            'Accept':'text/html,text/csv,*/*'})
    a=json.loads(P8.read_text(encoding='utf8'))
    b=json.loads(P18.read_text(encoding='utf8'))
    cal=json.loads(PCAL.read_text(encoding='utf8'))
    if calendar_only:
        refreshed=refresh_monthly_release_calendars(session,b,cal)
        PCAL.write_text(json.dumps(refreshed,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        if any(row['status']!='VERIFIED' for row in refreshed['target_refresh_results'].values()):
            raise ValueError('MONTHLY_CALENDAR_INCOMPLETE: original dates retained for failed targets')
        return
    stamp=dt.datetime.now(TPE).isoformat(timespec='seconds')
    fed=fetch(session,FED)
    content=clean(fed)
    m=re.search(r'\b2026\s+Date\s+Increase\s+Decrease\s+Level\s*\(?%\)?\s+'
                r'([A-Z][a-z]+)\s+(\d{1,2})\s+\d+\s+\d+\s+'
                r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)',content)
    if not m: raise ValueError('Fed current-year target row not found')
    month,day,lo,hi=m.groups()
    lower,upper=float(lo),float(hi)
    effective=dt.datetime.strptime(f'{month} {day} 2026','%B %d %Y').date().isoformat()
    row=a['items']['m06_rate']
    if (effective!=row['effective_date'] or lower!=row['lower_bound']['value'] or
            upper!=row['upper_bound']['value']):
        raise ValueError('Fed policy changed; require new dated official publication evidence')
    now=dt.datetime.now(TPE).isoformat(timespec='seconds')
    audit=ROOT/'data/audit'/('fed_target_evidence_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.html.gz')
    audit.parent.mkdir(parents=True,exist_ok=True)
    audit.write_bytes(gzip.compress(fed,mtime=0))
    sha=hashlib.sha256(fed).hexdigest()
    row.update(value=(lower+upper)/2,retrieval_time=now,last_verified_at=now,
               detail=f'Fed官方當期目標{lo}–{hi}%，真實HTTP原文SHA256={sha}，稽核檔{audit.relative_to(ROOT)}')
    row['source_evidence'].update(url=FED,checked_at=now,result='CURRENT_CONFIRMED',
        excerpt=f'2026 official current target: {month} {day} {lo}-{hi}; original response archived',
        response_sha256=sha,effective_date=effective,publication_date=row['publication_date'],
        lower_bound=row['lower_bound'],upper_bound=row['upper_bound'],value=row['value'])
    revise_candidate(row,'Federal Reserve',now,f'{lo}-{hi}',effective,'原始官方HTTP已保存並實算SHA256')
    print('FED_SOURCE_PASS',sha,flush=True)

    # Newly released October PMI is necessary after the Nov 2 official publication.
    if dt.datetime.now(TPE).date()>=dt.date(2026,11,3) and dt.datetime.now(TPE).date()<dt.date(2026,12,1):
        pmi,report_url=refresh_manufacturing_headline(session)
        cal_text=clean(fetch(session,ISM_CAL))
        if pmi!=55.5:
            raise ValueError('ISM October headline not independently verified at both official and distributed releases')
        if not re.search(r'December\s+2026\s+1\s+3',cal_text):
            raise ValueError('Official December ISM release calendar cannot be verified')
        b['items']['m04'].update(value=55.5,observation_date='2026-10-01',source_url=report_url,
            method='2026-11-02公布ISM官方10月製造業PMI',status='OK',
            detail='2026-10官方製造業PMI 55.5；前月54.5',attempted_at=now,
            last_verified_at=now,attempt_result='SUCCESS',cache_used=False,error='',retrieval_error='')
        b['items']['m04'].setdefault('source_attempts',{}).setdefault('ISM_m04',[]).append({
            'provider':'ISM_OFFICIAL','result':'OK','verified_at':now,'observation_date':'2026-10-01'})
        cal['items']['m04'].update(observation_month='2026-10',publication_date='2026-11-02',
                                  next_release_at_utc='2026-12-01T15:00:00Z')
        cal['checked_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        print('ISM_OCTOBER_PASS',flush=True)

    # Refresh NYSE MMFI only with actual dated source evidence.
    try:
        url='https://www.macroaxis.com/index/MMFI.INDX/Percent-Of-Stocks'
        source=clean(fetch(session,url))
        m=re.search(r'MMFI\s+Index\s+Updated\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\s+([0-9]+(?:\.[0-9]+)?)',source)
        if not m: raise ValueError('MMFI value/date missing')
        mon,day,year,num=m.groups()
        try: observed=dt.datetime.strptime(f'{mon} {day} {year}','%b %d %Y').date().isoformat()
        except ValueError: observed=dt.datetime.strptime(f'{mon} {day} {year}','%B %d %Y').date().isoformat()
        value=float(num)
        if not 0<=value<=100: raise ValueError('MMFI outside 0-100')
        row=a['items']['s05']
        row.update(value=value,observation_date=observed,status='USABLE',source_url=url,
            retrieval_time=now,publication_date=observed,
            detail=f'NYSE MMFI {value}%：Macroaxis頁面直接驗證觀測日{observed}')
        revise_candidate(row,'Macroaxis',now,value,observed,'頁面明示NYSE市場50日廣度')
        print('MMFI_PASS',value,observed,flush=True)
    except (requests.RequestException,ValueError) as exc:
        # Exact INDEX/MMFI EOD table is an authorized same-symbol fallback;
        # all-US or S&P500 breadth would be a different population.
        print('MMFI_MACROAXIS_UNAVAILABLE',str(exc)[:100],flush=True)
        try:
            url='https://www.eoddata.com/stockquote/INDEX/MMFI.htm'
            raw=fetch(session,url)
            ny_now=dt.datetime.now(ZoneInfo('America/New_York'))
            value,observed=parse_mmfi_eod(raw,dt.datetime.now(TPE).date(),ny_now)
            original=a['items']['s05']
            prior_date=dt.date.fromisoformat(original['observation_date'])
            # Correct any prematurely marked current-day close written before NY 17:00.
            provisional=(prior_date==ny_now.date() and ny_now.time()<dt.time(17,0)
                         and original.get('source_url','').startswith('https://www.eoddata.com/'))
            if dt.date.fromisoformat(observed)<prior_date and not provisional:
                raise ValueError('EOD observation predates last verified MMFI')
            raw_sha=hashlib.sha256(raw).hexdigest()
            row=a['items']['s05']
            row.update(value=value,observation_date=observed,status='USABLE',
                source_url=url,method='EODData INDEX/MMFI：NYSE 50日廣度之最近完整交易日收盤',
                retrieval_time=now,publication_date=observed,
                detail=f'INDEX/MMFI 日期{observed}收盤{value}%，採EOD收盤非盤中LAST；來源SHA256={raw_sha}')
            revise_candidate(row,'EODData',now,value,observed,
                'INDEX/MMFI End-of-Day OHLC 的 Close，非盤中Last；SHA256='+raw_sha)
            for candidate in row['candidate_checks']:
                if candidate['site']=='EODData':
                    candidate['url']=url
            print('MMFI_EOD_FALLBACK_PASS',value,observed,raw_sha,flush=True)
        except (requests.RequestException,ValueError) as second:
            print('MMFI_RETAIN_ORIGINAL_DATED_VALUE',str(second)[:150],flush=True)

    # Update direct, explicitly Forward (not TTM) multiples where accessible.
    for ticker in ('qqq','spy','vt'):
        item=a['items']['m03_'+ticker]
        url=f'https://stockanalysis.com/etf/{ticker}/'
        try:
            source=clean(fetch(session,url))
            val=re.search(r'Forward\s+PE\s+([0-9]+(?:\.[0-9]+)?)',source,re.I)
            date=re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2})',source)
            if not val or not date: raise ValueError('Forward PE/date missing')
            date=dt.datetime.strptime(date.group(1),'%b %d, %Y').date().isoformat()
            value=float(val.group(1))
            if not 0<value<200: raise ValueError('out of bound')
            item.update(value=value,observation_date=date,source_url=url,status='OK',
                publication_date=date,retrieval_time=now,
                method='StockAnalysis明示Forward PE，採未來預估口徑',detail=f'{ticker.upper()} Forward PE {value}，頁面資料日{date}')
            revise_candidate(item,'StockAnalysis',now,value,date,'真實網頁明示Forward PE；TTM未採用')
            print('FORWARD_PASS',ticker,value,date,flush=True)
        except (requests.RequestException,ValueError) as exc:
            print('FORWARD_RETAIN_ORIGINAL_DATED_VALUE',ticker,str(exc)[:100],flush=True)

    # Retain original observation/check dates for any source unavailable this run.
    # Owner 2026-11-16: builder uses the prior complete YoY with its original date; raw October remains missing.
    from v703_cpi_availability import FRED_CPI, verify_official_gap, load_archived_official_release, add_archived_notice_provenance
    cpi_csv = fetch_cpi_official_evidence(session, FRED_CPI)
    # The BLS notice is immutable dated evidence already obtained before HTTP 403.
    # Never retry or bypass that denial; re-fetch only the FRED observations.
    notice_manifest = json.loads((ROOT/'data/cpi_official_release_20261110.json').read_text())
    cpi_now = dt.datetime.now(dt.timezone.utc)
    cpi_release = load_archived_official_release(
        (ROOT/'data/audit/cpi_official_release_20261110.html.gz').read_bytes(), notice_manifest, cpi_now)
    cpi_evidence = add_archived_notice_provenance(
        verify_official_gap(cpi_csv, cpi_release, cpi_now), notice_manifest)
    print('CPI_DATED_BLS_EVIDENCE',notice_manifest['publicationDate'],notice_manifest['sourceVerifiedAtUtc'],notice_manifest['sourceSha256'],flush=True)
    b['items']['m05'].pop('official_unavailable', None)
    if cpi_evidence:
        b['items']['m05']['official_unavailable'] = cpi_evidence
        for suffix, raw in (('series.csv.gz', cpi_csv), ('release.html.gz', cpi_release)):
            (ROOT/'data/audit'/('cpi_unavailable_20261110_'+suffix)).write_bytes(gzip.compress(raw,mtime=0))
        print('CPI_OFFICIAL_GAP_PREVIOUS_YOY_AUTHORIZED', cpi_evidence['observationMonth'], flush=True)

    cal=refresh_monthly_release_calendars(session,b,cal)
    a['generated_at']=now
    a['as_of_taipei']=now
    a['refresh_method']='Official Fed full raw HTTP reverified; other values retain dated observations unless independently refreshed'
    sys.path.insert(0,str(ROOT/'scripts'))
    from validate_macro_supplement import validate
    issues=validate(a,dt.datetime.now(dt.timezone.utc))
    if issues: raise ValueError('V703_REFRESH_QA_BLOCKED: '+'; '.join(issues))
    P8.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    P18.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    PCAL.write_text(json.dumps(cal,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('V703_EVIDENCE_REFRESH_PASS',now,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calendar-only',action='store_true',help='Refresh the four monthly calendars without changing observations or other sources')
    main(parser.parse_args().calendar_only)
