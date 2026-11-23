"""Bounded source intake for the 20 V82 auxiliary fields; no new V70 judgments."""
from __future__ import annotations
import concurrent.futures,copy,csv,datetime as dt,hashlib,io,json,re,threading,time
from pathlib import Path
from urllib.parse import urlparse,urljoin
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

UTC=dt.timezone.utc
NY=ZoneInfo('America/New_York')
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/v70_family_sources.json'
EXPECTED={'fed_policy_bias','treasury_2y','treasury_10y','treasury_30y','cpi','pce','core_pce','gdp','liquidity_regime','material_macro_events','ig_oas','bbb_oas','a_oas','treasury_market_liquidity','repo','sofr','sofr_ois','fra_ois','srf','rrp'}

def stamp(value):
    t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return t.astimezone(UTC)

def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def text(data):return BeautifulSoup(data,'html.parser').get_text(' ',strip=True)

class Fetcher:
    """One request per distinct URL; only permissioned primary evidence is persisted."""
    def __init__(self,evidence=None):
        self.evidence=Path(evidence) if evidence else None
        if self.evidence:self.evidence.mkdir(parents=True,exist_ok=True)
        self.cache={};self.records={};self.locks={};self.host_locks={};self.last_request={};self.guard=threading.Lock()

    def get(self,url):
        with self.guard:lock=self.locks.setdefault(url,threading.Lock())
        with lock:
            if url in self.cache:return self.cache[url]
            record={'url':url,'retrieved_at':dt.datetime.now(UTC).isoformat()}
            try:
                host=urlparse(url).hostname or ''
                with self.guard:host_lock=self.host_locks.setdefault(host,threading.Lock())
                with host_lock:
                    wait=.65-(time.monotonic()-self.last_request.get(host,0))
                    if wait>0:time.sleep(wait)
                    response=requests.get(url,timeout=(7,20),headers={'User-Agent':'LivingWaterAI V70 bounded source verification'})
                    self.last_request[host]=time.monotonic()
                data=response.content
                if len(data)>12*1024*1024:raise ValueError('SOURCE_TOO_LARGE')
                record.update(http_status=response.status_code,bytes=len(data),sha256=sha(data),final_url=response.url)
                host=urlparse(url).hostname or ''
                if self.evidence and response.status_code==200 and (host.endswith('.gov') or host.endswith('newyorkfed.org')):
                    name=sha(url.encode())+'.raw';(self.evidence/name).write_bytes(data);record['evidence_file']=name
                # Third-party material is inspected only in memory; never archived here.
                result=(response.status_code,data,record)
            except Exception as exc:
                record.update(error=type(exc).__name__);result=(0,b'',record)
            self.cache[url]=result;self.records[url]=record
            return result

def release_time(raw):
    s=text(raw);start=s.find('EMBARGOED')
    if start<0:start=s.lower().find('embargoed')
    match=re.search(r'(\d{1,2}):(\d{2})\s*a\.m\..*?([A-Z][a-z]+ \d{1,2},\s*\d{4})',s[max(0,start):max(0,start)+500])
    if not match:raise ValueError('OFFICIAL_RELEASE_TIME_NOT_FOUND')
    day=dt.datetime.strptime(re.sub(r'\s+',' ',match[3]),'%B %d, %Y')
    return day.replace(hour=int(match[1]),minute=int(match[2]),tzinfo=NY).astimezone(UTC)

def observation(value,unit,day,published,url,method,record,**extra):
    return dict(value=value,unit=unit,as_of=day,published_at=published,source=url,method=method,
                source_sha256=record['sha256'],retrieved_at=record['retrieved_at'],**extra)

def parse_bea(raw,url,record,kind,cutoff):
    released=release_time(raw)
    if released>cutoff:raise ValueError('RELEASE_AFTER_CUTOFF')
    s=text(raw)
    if kind=='gdp':
        m=re.search(r'Real gross domestic product \(GDP\) (increased|decreased) at an annual rate of ([\d.]+) percent',s,re.I)
        q=re.search(r'(1st|2nd|3rd|4th) Quarter (20\d{2})',s,re.I)
        if not m or not q:raise ValueError('GDP_DEFINITION_OR_QUARTER_MISSING')
        return observation(float(m[2])*(-1 if m[1].lower()=='decreased' else 1),'% SAAR',q[2]+'-Q'+q[1][0],released.isoformat(),url,
            'BEA real GDP quarter-on-quarter seasonally adjusted annual rate',record,growth_basis='QoQ_SAAR',estimate_vintage='advance' if 'advance estimate' in s.lower() else 'official release; see source')
    m=re.search(r'From the same month one year ago, the PCE price index for ([A-Za-z]+) (increased|decreased) ([\d.]+) percent.{0,150}?Excluding food and energy, the PCE price index (increased|decreased) ([\d.]+) percent',s,re.I)
    if not m:raise ValueError('PCE_YOY_NOT_EXPLICIT')
    month=dt.datetime.strptime(m[1],'%B').month;year=released.year-(month>released.month)
    n,verb=(m[3],m[2]) if kind=='pce' else (m[5],m[4])
    return observation(float(n)*(-1 if verb.lower()=='decreased' else 1),'%',f'{year}-{month:02d}-01',released.isoformat(),url,
        'BEA published PCE price index '+('excluding food and energy ' if kind=='core_pce' else '')+'year-on-year percent change',record,change_basis='YoY',observation_month=f'{year}-{month:02d}')

def parse_cpi(raw,url,record,cutoff):
    released=release_time(raw)
    if released>cutoff:raise ValueError('RELEASE_AFTER_CUTOFF')
    s=text(raw);m=re.search(r'CONSUMER PRICE INDEX\s*[-–—]\s*([A-Z]+)\s*(20\d{2})',s)
    if not m:raise ValueError('CPI_MONTH_MISSING')
    month=dt.datetime.strptime(m[1].title(),'%B').month;day=f'{m[2]}-{month:02d}-01'
    if 'cannot publish 12-month percent changes' in s or 'cannot publish 12 -month percent changes' in s:
        supporting={}
        mom=re.search(r'CPI-U\) increased ([\d.]+) percent on a seasonally adjusted basis',s)
        level=re.search(r'CPI-U\) increased to an index level of (\d+(?:\.\d+)?)',s)
        if mom:supporting['published_mom_sa']={'value':float(mom[1]),'unit':'%','basis':'MoM_SA'}
        if level:supporting['published_index_nsa']={'value':float(level[1]),'unit':'1982-84=100','basis':'index_NSA'}
        return {'value':None,'reason':'OFFICIAL_UNAVAILABLE_YOY_BASE_MISSING','published_at':released.isoformat(),'as_of':day,'source':url,'supporting_observations':supporting,'source_sha256':record['sha256']}
    yoy=re.search(r'Over the last 12 months, the all items index (increased|decreased) ([\d.]+) percent',s,re.I)
    if not yoy:raise ValueError('CPI_YOY_NOT_EXPLICIT')
    return observation(float(yoy[2])*(-1 if yoy[1].lower()=='decreased' else 1),'%',day,released.isoformat(),url,'BLS CPI-U All items published YoY',record,change_basis='YoY')

def parse_treasury(raw,url,record,cutoff,tenor,baseline):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));eligible=[]
    for row in rows:
        day=dt.datetime.strptime(row['Date'],'%m/%d/%Y').date()
        # Treasury publishes indicative closing quotations later on the observation day.
        # The precise per-row posting time is not supplied; never label the quote time a release time.
        upper=dt.datetime.combine(day,dt.time.max,NY).astimezone(UTC)
        if upper<=cutoff and row.get(tenor) not in (None,'','N/A'):
            eligible.append((day,row,upper))
    if not eligible:raise ValueError('NO_PRE_CUTOFF_TREASURY_OBSERVATION')
    day,row,upper=max(eligible,key=lambda v:v[0]);legacy=baseline.get('v70_indicators',{}).get('m01',{})
    if day.isoformat()==legacy.get('as_of') and abs(float(row['10 Yr'])-float(row['2 Yr'])-float(legacy['value']))>1e-8:
        raise ValueError('TREASURY_CONFLICT_WITH_ACCEPTED_SPREAD')
    return observation(float(row[tenor]),'%',day.isoformat(),day.isoformat(),url,
        'U.S. Treasury official daily nominal par yield curve '+tenor,record,
        tenor_years=int(tenor.split()[0]),instrument='nominal Treasury par/CMT',
        publication_time_precision='DATE_ONLY',publication_time_basis='Daily Treasury closing-quote release cycle; exact posting time not supplied. Conservative NY day-end bound; accepted same-date 10Y-2Y spread cross-check.',publication_eligibility_bound=upper.isoformat())

def next_business_day(day):
    # Only NYFed full non-business days relevant to the selected year; supplied
    # exchange calendar is used instead of assuming every weekday is open.
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS')
    d=day+dt.timedelta(days=1)
    from pandas.tseries.holiday import USFederalHolidayCalendar
    holidays={x.date() for x in USFederalHolidayCalendar().holidays(start=str(day.year)+'-01-01',end=str(day.year+1)+'-12-31')}
    while not cal.is_session(d.isoformat()) or d in holidays:d+=dt.timedelta(days=1)
    return d

def parse_sofr(raw,url,record,cutoff):
    rates=json.loads(raw).get('refRates');eligible=[]
    if not isinstance(rates,list):raise ValueError('SOFR_RESPONSE_INVALID')
    for r in rates:
        if r.get('type')!='SOFR':continue
        day=dt.date.fromisoformat(r['effectiveDate']);pub=dt.datetime.combine(next_business_day(day),dt.time(8),NY).astimezone(UTC)
        if pub<=cutoff:eligible.append((day,pub,r))
    if not eligible:raise ValueError('SOFR_NEXT_BUSINESS_PUBLICATION_AFTER_CUTOFF')
    day,pub,r=max(eligible,key=lambda x:x[0])
    return observation(float(r['percentRate']),'%',day.isoformat(),pub.isoformat(),url,'NYFed overnight SOFR, volume-weighted median; next business day approximately 08:00 New York',record,
                       publication_time_precision='SCHEDULED_APPROXIMATE',series_id='SOFR',revision_indicator=r.get('revisionIndicator',''),attribution='Source: Federal Reserve Bank of New York. Subject to its Terms of Use; the New York Fed does not endorse this republication and has no liability for this use.',terms_url='https://www.newyorkfed.org/privacy/termsofuse')

def parse_operations(raw,url,record,cutoff,kind):
    body=json.loads(raw);container=body.get('repo',{})
    operations=container.get('operations')
    if not isinstance(operations,list):raise ValueError('OPERATION_LIST_MISSING')
    if any(container.get(k) for k in ('nextPage','nextPageToken','hasMore')):raise ValueError('INCOMPLETE_OPERATION_QUERY')
    seen={};eligible=[];required='Reverse Repo' if kind=='rrp' else 'Repo'
    for op in operations:
        if op.get('operationType')!=required or op.get('term')!='Overnight' or op.get('auctionStatus')!='Results':continue
        published=dt.datetime.strptime(op['lastUpdated'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=NY).astimezone(UTC)
        if published>cutoff:continue
        ident=op['operationId']
        if ident in seen:
            if seen[ident]!=op:raise ValueError('CONFLICTING_DUPLICATE_OPERATION')
            continue
        seen[ident]=op
        details=op.get('details',[])
        if not details or sum(float(v['amtAccepted']) for v in details)!=float(op['totalAmtAccepted']):raise ValueError('OPERATION_TOTAL_MISMATCH')
        if kind=='rrp' and any(v.get('securityType')!='Treasury' for v in details):continue
        if kind=='srf' and op.get('operationMethod')!='Full Allotment':continue
        eligible.append((op['operationDate'],published,op))
    if not eligible:raise ValueError('NO_QUALIFIED_OPERATION_BEFORE_CUTOFF')
    day=max(v[0] for v in eligible);selected=[v for v in eligible if v[0]==day]
    total=sum(float(v[2]['totalAmtAccepted']) for v in selected)/1e9;pub=max(v[1] for v in selected)
    return observation(total,'USD bn',day,pub.isoformat(),url,'NYFed '+('Treasury ON RRP' if kind=='rrp' else 'domestic standing overnight repo, full-allotment')+' daily accepted principal; flow, not current outstanding balance or risk classification',record,
                       series_id='NYFED_ON_RRP_ACCEPTED' if kind=='rrp' else 'NYFED_STANDING_REPO_ACCEPTED',operation_ids=[v[2]['operationId'] for v in selected],publication_time_basis='Official lastUpdated in America/New_York; conservative version availability',attribution='Source: Federal Reserve Bank of New York; no endorsement. Subject to NYFed Terms of Use.',terms_url='https://www.newyorkfed.org/privacy/termsofuse')

def resolve_url(url,cutoff):
    end=cutoff.date();start=end-dt.timedelta(days=10)
    url=re.sub(r'startDate=\d{4}-\d{2}-\d{2}', 'startDate='+start.isoformat(),url)
    url=re.sub(r'endDate=\d{4}-\d{2}-\d{2}', 'endDate='+end.isoformat(),url)
    if 'daily-treasury-rates.csv/' in url:url=re.sub(r'2026',str(end.year),url)
    return url

def discover_release(source,kind,cutoff,fetcher):
    """Refresh official monthly/quarterly releases after the frozen first snapshot.

    Never infer a publication time from the current-release index. Each linked
    release must supply its own dated embargo header and pass the cutoff.
    """
    original=resolve_url(source['url'],cutoff)
    if cutoff<=stamp('2026-11-17T14:43:12+08:00') or kind not in ('cpi','pce','core_pce','gdp'):return original
    candidates=[original]
    if kind=='cpi':candidates.insert(0,'https://www.bls.gov/news.release/cpi.nr0.htm')
    else:
        index='https://www.bea.gov/news/current-releases';status,raw,_=fetcher.get(index)
        if status==200:
            for a in BeautifulSoup(raw,'html.parser').select('a[href]'):
                href=urljoin(index,a['href']);path=urlparse(href).path
                allowed=urlparse(href).hostname=='www.bea.gov' and re.match(r'/news/20\d{2}/',path)
                matches=('/personal-income-and-outlays-' in path) if kind!='gdp' else bool(re.search(r'/gdp-.*quarter-',path))
                if allowed and matches:candidates.append(href)
    eligible=[]
    for url in list(dict.fromkeys(candidates))[:6]:
        status,raw,_=fetcher.get(url)
        if status!=200:continue
        try:released=release_time(raw)
        except ValueError:continue
        if released<=cutoff:eligible.append((released,url))
    return max(eligible)[1] if eligible else original

def backup_qualification(source,key,http):
    status=http.get('http_status',0)
    if status!=200:return 'HTTP_NOT_USABLE: '+str(status)+'; '+http.get('error','response unavailable/challenge/not found')
    host=source['website']
    if 'fred.' in host:
        return 'MIRROR_NOT_SELECTED: original publisher identified; exact historical vintage and FRED service/storage permission not established for new adoption'
    if key in ('ig_oas','bbb_oas','a_oas'):
        return 'RIGHTS_UNCLEARED: ICE series/provider page checked; new four-household storage/distribution permission not established'
    if 'govinfo.gov' in host:return 'ARCHIVED_REPORT_ONLY: monthly report has not established this observation and publication-time vintage; no numeric fallback adopted'
    if 'cmegroup.com' in host:return 'BASIS_MISMATCH: term SOFR/product methodology is not overnight SOFR or a same-tenor SOFR-OIS spread'
    if key=='material_macro_events':return 'PARTIAL_CALENDAR: reviewed official calendar; materiality and complete event coverage not established'
    if key in UNKNOWN_REASONS:return 'CHECKED_NOT_EQUIVALENT: '+UNKNOWN_REASONS[key]
    if key in ('srf','rrp'):return 'BASIS_MISMATCH: weekly stock/aggregate market statistic is not the selected NYFed daily facility accepted principal'
    return 'NOT_ADOPTED: this page did not establish a dated, same-definition, permissioned numeric fallback'

UNKNOWN_REASONS={
 'fed_policy_bias':'METHODOLOGY_UNAVAILABLE: original V70 supplies policy range/deviation, not an adopted policy-bias classifier.',
 'liquidity_regime':'METHODOLOGY_UNAVAILABLE: retain original liquidity group judgment; no standalone regime mapping.',
 'material_macro_events':'COVERAGE_INCOMPLETE: three official calendars do not establish complete material-event review; empty events is not no-events.',
 'ig_oas':'RIGHTS_UNCLEARED: ICE/FRED third-party and service restrictions; no approved new storage/four-household redistribution permission.',
 'bbb_oas':'RIGHTS_UNCLEARED: ICE/FRED third-party and service restrictions; no approved new storage/four-household redistribution permission.',
 'a_oas':'RIGHTS_UNCLEARED: ICE/FRED third-party and service restrictions; no approved new storage/four-household redistribution permission.',
 'treasury_market_liquidity':'METRIC_UNSPECIFIED: no adopted metric/tenor/threshold; historical research or FSI/MOVE is not an equivalent value.',
 'repo':'METRIC_UNSPECIFIED: repo rate, volume and facility usage differ; SRF principal is separately reported.',
 'sofr_ois':'TENOR_BASIS_UNSPECIFIED: need two comparable legs and tenor; spot SOFR, term SOFR or CP-OIS is not the requested spread.',
 'fra_ois':'BENCHMARK_TENOR_UNSPECIFIED: no eligible same-basis FRA/OIS pair; discontinued TED/LIBOR or OTC aggregates are not substitutes.'}

def collect(baseline,cutoff_string,fetcher=None):
    cutoff=stamp(cutoff_string);fetcher=fetcher or Fetcher();config=json.loads(CONFIG.read_text());registry=config['signals']
    for variable in registry:
        primary=variable['sources'][0]
        primary['url']=discover_release(primary,variable['signal'],cutoff,fetcher)
    if {r['signal'] for r in registry}!=EXPECTED:raise ValueError('REGISTRY_MUST_COVER_EXACT_20')
    urls=sorted({resolve_url(s['url'],cutoff) for r in registry for s in r['sources']})
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(fetcher.get,urls))
    supplements={};table=[]
    for variable in registry:
        key=variable['signal'];primary=variable['sources'][0];url=resolve_url(primary['url'],cutoff);status,raw,record=fetcher.get(url)
        try:
            if key in UNKNOWN_REASONS:raise ValueError(UNKNOWN_REASONS[key])
            if status!=200:raise ValueError('PRIMARY_HTTP_'+str(status))
            if key.startswith('treasury_'):row=parse_treasury(raw,url,record,cutoff,{'treasury_2y':'2 Yr','treasury_10y':'10 Yr','treasury_30y':'30 Yr'}[key],baseline)
            elif key in ('pce','core_pce','gdp'):row=parse_bea(raw,url,record,key,cutoff)
            elif key=='cpi':row=parse_cpi(raw,url,record,cutoff)
            elif key=='sofr':row=parse_sofr(raw,url,record,cutoff)
            else:row=parse_operations(raw,url,record,cutoff,key)
        except Exception as exc:row={'value':None,'reason':str(exc)[:450]}
        supplements[key]=row
        for source in variable['sources']:
            effective=resolve_url(source['url'],cutoff);http=fetcher.records[effective]
            if http.get('http_status')!=200:qualification=backup_qualification(source,key,http)
            elif source['rank']=='primary' and row.get('value') is not None:qualification='SELECTED_NUMERIC_SOURCE'
            elif source['rank']=='primary':qualification='CHECKED_NOT_ADOPTED: '+row.get('reason','UNKNOWN')
            else:qualification=backup_qualification(source,key,http)
            table.append(dict(signal=key,label=variable['label'],rank=source['rank'],website=source['website'],url=effective,original_publisher=source['original_publisher'],same_publisher_republication=source['same_publisher_republication'],definition=variable['definition'],rights=source['rights'],qualification=qualification,selected=source['rank']=='primary' and row.get('value') is not None,http_status=http.get('http_status',0),retrieved_at=http['retrieved_at'],response_sha256=http.get('sha256',''),observed_at=row.get('as_of','') if source['rank']=='primary' else '',published_at=row.get('published_at','') if source['rank']=='primary' else '',unit=row.get('unit','') if source['rank']=='primary' else '',value=row.get('value') if source['rank']=='primary' else None,publication_time_precision=row.get('publication_time_precision','exact official release time' if row.get('published_at') else 'UNKNOWN'),publication_time_basis=row.get('publication_time_basis','official release header' if row.get('published_at') else 'not adopted / unavailable'),missing_reason=row.get('reason','') if source['rank']=='primary' else qualification))
    return {'schema':'V70.3/family-source-intake-v1','cutoff':cutoff_string,'baseline_sha256':sha(canonical(baseline)),'registry_version':config['version'],'supplements':supplements,'source_registry':table,'http_records':list(fetcher.records.values()),'created_at':dt.datetime.now(UTC).isoformat()}

def merge_candidate(baseline,intake):
    if intake['baseline_sha256']!=sha(canonical(baseline)):raise ValueError('BASELINE_HASH_MISMATCH')
    if stamp(intake['cutoff'])!=stamp(baseline['data_cutoff']):raise ValueError('CUTOFF_MISMATCH')
    out=copy.deepcopy(baseline);changes=[]
    for key in EXPECTED:
        original=baseline['signals'][key];sup=intake['supplements'][key];target=out['signals'][key]
        if original.get('value') is not None and original.get('data_quality') in ('OK','FALLBACK_USED'):
            newer=bool(sup.get('value') is not None and str(sup.get('as_of',''))>str(original.get('as_of','')))
            if not newer:
                changes.append({'signal':key,'disposition':'沿用','reason':'qualified existing value retained; no later comparable qualified observation'});continue
        if sup.get('value') is not None:
            target.update(sup);target.update(data_quality='OK',issue_codes=[],judgment_issue_codes=['METHODOLOGY_UNAVAILABLE'],level=None,direction=None,speed=None)
            target.pop('issue_detail',None);changes.append({'signal':key,'disposition':'新補','value':sup['value'],'as_of':sup.get('as_of'),'published_at':sup.get('published_at')})
        else:
            target.update(data_quality='UNKNOWN',issue_codes=['MISSING',sup.get('reason','UNKNOWN').split(':')[0]],issue_detail=sup.get('reason','UNKNOWN'))
            for n in ('supporting_observations','as_of','published_at','source','source_sha256'):
                if n in sup:target[n]=sup[n]
            if key=='material_macro_events':target['coverage'].update(status='PARTIAL_OFFICIAL_CALENDARS_ONLY',reviewed_sources=[r['url'] for r in intake['source_registry'] if r['signal']==key])
            changes.append({'signal':key,'disposition':'仍缺','reason':sup.get('reason','UNKNOWN')})
    for key in baseline['signals']:
        if key not in EXPECTED:changes.append({'signal':key,'disposition':'沿用','reason':'unchanged approved original signal'})
    # The previous PM approval covers its original scope only; never manufacture an approval of new fields.
    out['extension_approval']={'status':'PENDING_HIGHEST_PM_ACCEPTANCE','scope':'round1 auxiliary values and automation candidate'}
    out['round1_extension']={'cutoff':intake['cutoff'],'source_registry_version':intake['registry_version'],'source_intake_created_at':intake['created_at'],'changes':changes,'judgment_policy':'original V70 judgments unchanged; no new level/direction/speed inference'}
    identity={'feed_sha256':out['feed_sha256'],'data_cutoff':out['data_cutoff'],'signals':out['signals'],'registry_version':intake['registry_version']}
    out['publication_identity']=sha(canonical(identity))
    if out['v70_indicators']!=baseline['v70_indicators'] or out['v70_judgments']!=baseline['v70_judgments']:raise ValueError('ORIGINAL_V70_CHANGED')
    if len(out['signals'])!=28 or len(out['v70_indicators'])!=29:raise ValueError('CONTRACT_COUNTS_CHANGED')
    return out

def write_registry(rows,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    wide=[]
    for key in dict.fromkeys(r['signal'] for r in rows):
        sources=[r for r in rows if r['signal']==key]
        first=sources[0];out={k:first[k] for k in ('signal','label','definition','value','observed_at','published_at','unit','publication_time_precision','publication_time_basis','missing_reason')}
        for s in sources:
            prefix={'primary':'主來源','backup_1':'備援一','backup_2':'備援二'}[s['rank']]
            for k in ('website','url','original_publisher','same_publisher_republication','rights','qualification','http_status','retrieved_at','response_sha256'):out[prefix+'_'+k]=s[k]
        out['第三來源不足說明']=sources[2]['qualification'] if not sources[2]['selected'] else ''
        wide.append(out)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(wide[0]));writer.writeheader();writer.writerows(wide)
