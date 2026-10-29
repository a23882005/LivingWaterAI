"""Source-owned publication dates and release periods for V75 freshness."""
from datetime import date,datetime,timedelta
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
import json,re
from v75_remaining_inputs import time

URLS={'BEA_PCE':'https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026',
    'BEA_CURRENT':'https://www.bea.gov/data/income-saving/personal-income',
    'BLS_CPI':'https://www.bls.gov/news.release/cpi.nr0.htm',
    'BLS_PPI':'https://www.bls.gov/news.release/ppi.nr0.htm',
    'FOMC_CAL':'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'}


class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0;self.links=[];self.html_links=[];self.anchor=None
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag=='a' and dict(attrs).get('href'):
            self.anchor=(dict(attrs)['href'],[]);self.links.append(self.anchor[0])
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip-=1
        if tag=='a' and self.anchor:
            if ' '.join(self.anchor[1]).strip()=='HTML':self.html_links.append(self.anchor[0])
            self.anchor=None
    def handle_data(self,value):
        if not self.skip and value.strip():self.parts.append(' '.join(value.split()))
        if self.anchor and value.strip():self.anchor[1].append(' '.join(value.split()))


def _match(pattern,text):
    result=re.search(pattern,text)
    if result is None:raise ValueError('V75_RELEASE_FORMAT_REQUIRED:'+pattern)
    return result


def _publication(day,clock='08:30'):
    return datetime.strptime(day+' '+clock,'%B %d, %Y %H:%M').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()


def monthly_release(text,key):
    if key=='BEA_PCE':
        period=_match(r'Personal Income and Outlays, ([A-Za-z]+ \d{4})',text)[1]
        published=_match(r'EMBARGOED UNTIL RELEASE AT (\d{1,2}:\d{2}) a\.m\. (?:EDT|EST), \w+, (\w+ \d{1,2}, \d{4})',text)
        release=_publication(published[2],published[1])
        next_date=_match(r'Next release: (\w+ \d{1,2}, \d{4}), at (\d{1,2}:\d{2}) a\.m\. (?:EDT|EST)',text)
        following=_publication(next_date[1],next_date[2])
    else:
        title='CONSUMER PRICE INDEX' if key=='BLS_CPI' else 'PRODUCER PRICE INDEXES'
        period=_match(title+r' - ([A-Z]+ \d{4})',text)[1].title()
        release=_publication(_match(r'8:30 a\.m\. \(ET\) \w+, (\w+ \d{1,2}, \d{4})',text)[1])
        following=_publication(_match(r'news release for \w+ \d{4} is scheduled to be published on \w+, (\w+ \d{1,2}, \d{4}), at 8:30 a\.m\.',text)[1])
    period=datetime.strptime(period,'%B %Y').date().replace(day=1).isoformat()
    return {'observation_period':period,'release_at':release,'next_release_at':following,
        'release_date_basis':'EXPLICIT_OFFICIAL_EMBARGO_PUBLICATION_AND_NEXT_RELEASE_TEXT',
        'observation_period_is_publication_date':False}


def read(sources,evaluation_at):
    at=time(evaluation_at);out={}
    for key,source in (sources or {}).items():
        if key not in URLS:raise PermissionError('V75_RELEASE_PROVIDER_NOT_SUPPORTED')
        raw=Path(source['local_path']).read_bytes();receipt_raw=Path(source['receipt_path']).read_bytes()
        if sha256(raw).hexdigest()!=source['sha256'] or sha256(receipt_raw).hexdigest()!=source['receipt_sha256']:
            raise PermissionError('V75_RELEASE_SOURCE_BYTES_CHANGED')
        receipt=json.loads(receipt_raw)
        url=receipt.get('url','')
        allowed=bool(re.fullmatch(r'https://www\.bea\.gov/news/\d{4}/personal-income-and-outlays-[a-z]+-\d{4}',url)) if key=='BEA_PCE' else url==URLS[key]
        if (not allowed or receipt.get('final_url',url)!=url
            or receipt.get('http_status')!=200 or receipt.get('sha256')!=source['sha256']
            or not time(receipt['requested_at'])<=time(receipt['available_at'])<=at):
            raise PermissionError('V75_RELEASE_SOURCE_RECEIPT')
        parser=Text();parser.feed(raw.decode('utf-8-sig'));text=' '.join(parser.parts)
        record={'source_reference':receipt['url'],'source_sha256':source['sha256'],
            'receipt_sha256':source['receipt_sha256'],'available_at':receipt['available_at']}
        if key in ('BEA_PCE','BLS_CPI','BLS_PPI'):
            record.update(monthly_release(text,key))
            if time(record['release_at'])>time(receipt['available_at']):raise PermissionError('V75_RELEASE_EMBARGO_NOT_PASSED')
        elif key=='BEA_CURRENT':
            record['current_release_date']=_match(r'Current release: (\w+ \d{1,2}, \d{4})',text)[1]
            record['current_period']=datetime.strptime(_match(r'Personal Income and Outlays, ([A-Za-z]+ \d{4})',text)[1],'%B %Y').date().replace(day=1).isoformat()
        elif key=='FOMC_CAL':
            dates=lambda pattern,links:sorted({datetime.strptime(m,'%Y%m%d').date().isoformat()
                for href in links for m in re.findall(pattern,href) if datetime.strptime(m,'%Y%m%d').date()<=at.date()})
            record['published_projection_dates']=dates(r'fomcprojtabl(\d{8})\.htm',parser.html_links)
            record['published_policy_statement_dates']=dates(r'/pressreleases/monetary(\d{8})a\.htm',parser.html_links)
        out[key]=record
    return out


def monthly_freshness(releases,key,observed_date,evaluation_at):
    at=time(evaluation_at);record=releases.get(key)
    if record is None:return {'state':'UNKNOWN','reason':'OFFICIAL_RELEASE_METADATA_REQUIRED'}
    current=True
    if key=='BEA_PCE':
        page=releases.get('BEA_CURRENT',{})
        current=(page.get('current_period')==record['observation_period'] and
            bool(page.get('current_release_date')) and
            datetime.strptime(page['current_release_date'],'%B %d, %Y').date()==time(record['release_at']).date())
    if not current or observed_date!=record['observation_period']:
        state='UNKNOWN';reason='OFFICIAL_LATEST_RELEASE_PERIOD_OR_CURRENT_PAGE_MISMATCH'
    elif at>=time(record['next_release_at']) or (at-time(record['release_at'])).total_seconds()>45*86400:
        state='STALE';reason='NEXT_RELEASE_DUE_OR_45_DAY_LIMIT'
    else:state='FRESH';reason='LATEST_OFFICIAL_RELEASE_STILL_CURRENT'
    return {'state':state,'reason':reason,'observed_period':observed_date,
        'release_at':record['release_at'],'next_release_at':record['next_release_at'],
        'source_sha256':record['source_sha256'],'basis':'ORIGINAL_WORK1_MONTHLY_FRESHNESS_RULE'}


def qualify(pool,evaluation_at):
    if not pool.get('formal_parameters'):return pool
    from v75_etf_quality_inputs import daily_freshness
    from urllib.parse import urlparse
    records=pool.get('official_release_observations',{});calculations=pool['calculations']
    qualified=pool.setdefault('qualified_shared_predicate_inputs',{})
    pce=monthly_freshness(records,'BEA_PCE',calculations['PRED-001']['core_pce_yoy']['observed_date'],evaluation_at)
    projections=records.get('FOMC_CAL',{}).get('published_projection_dates',[])
    current_projection=max(projections) if projections else None
    url=pool['source_proofs']['SEP']['source_reference'];match=re.search(r'fomcprojtabl(\d{8})\.htm',url)
    consumed=datetime.strptime(match[1],'%Y%m%d').date().isoformat() if match else None
    sep_check={'state':'FRESH' if consumed is not None and consumed==current_projection else 'UNKNOWN',
        'consumed_projection_date':consumed,'latest_published_projection_date':current_projection,
        'basis':'LATEST_PROJECTION_LINK_ON_OFFICIAL_FOMC_CALENDAR'}
    effr=daily_freshness(calculations['PRED-001']['effr_observed_date'],evaluation_at)
    checks=[effr,pce,sep_check]
    qualified['PRED-001']={'input_freshness_verified':all(c['state']=='FRESH' for c in checks),'checks':checks,
        'basis':'EFFR_DAILY_LATEST_RELEASED_CORE_PCE_AND_LATEST_SEP'}
    future=calculations['PRED-002']
    statements=records.get('FOMC_CAL',{}).get('published_policy_statement_dates',[])
    crossed=[d for d in statements if future['comparison_date']<d<=future['observed_date']]
    future_check=daily_freshness(future['observed_date'],evaluation_at)
    qualified['PRED-002']={'input_freshness_verified':False,
        'checks':[future_check],'meeting_roll_dates':crossed,
        'meeting_specific_delta_status':'NOT_APPLICABLE_MEETING_ROLL' if crossed else 'NOT_ATTESTED',
        'fallback':'FIXED_SIX_MONTH_OIS_OR_SOFR_IMPLIED_RATE_REQUIRED' if crossed else None,
        'basis':'ORIGINAL_PRED_002_MEETING_ROLL_RULE__NO_DIFFERENT_MEETING_IDS_COMPARED',
        'sofr_ois_tenor_inferred':False}
    pool['unprovided_inputs']['PRED-002']=[
        'fixed 6-month OIS/SOFR implied-rate comparison after confirmed meeting roll' if crossed else
        'comparable meeting-specific source coverage or formally applicable fixed-horizon fallback']
    inflation=calculations['PRED-006'];checks=[]
    for label,key in (('core_pce','BEA_PCE'),('core_cpi','BLS_CPI'),('core_ppi','BLS_PPI')):
        point=inflation.get(label+'_ann3_pct')
        checks.append(monthly_freshness(records,key,point['observed_date'],evaluation_at) if point else
            {'state':'UNKNOWN','reason':label+'_index_required'})
    for label in ('breakeven','oil'):
        point=inflation.get(label)
        checks.append(daily_freshness(point['observed_date'],evaluation_at) if point else
            {'state':'UNKNOWN','reason':label+'_source_required'})
    complete=not pool['unprovided_inputs'].get('PRED-006')
    qualified['PRED-006']={'input_freshness_verified':complete and all(c['state']=='FRESH' for c in checks),
        'checks':checks,'basis':'ALL_THREE_CORE_REALIZED_INFLATION_SERIES_PLUS_BREAKEVEN_AND_OIL'}
    return pool
