"""Official snapshots -> dated USD liquidity candidates -> explicit native map.

The frozen model transports the base version plus mandatory amendment lineage.
The outer assessment and cache identity retain the full amendment ID/hash.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo
import csv,io,json
from v75_pred007_policy import (AMENDMENT_ID,AMENDMENT_VERSION,BASE_VERSION,RULESET_SHA256,
    EFFECTIVE_VERSION,EFFECTIVE_AT,FIELDS,InvalidInput,ReviewRequired,exact,spread,unique,
    calibrated,level,aggregate,start_date)

CALENDAR_ID='US_FEDERAL_RESERVE_BANKS_BRANCHES_K8'
CALENDAR_VERSION='K8_2026_2030_BANKS_RULES_v1'


def time(value):
    try:out=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError,TypeError) as error:raise InvalidInput('TIMESTAMP_FORMAT') from error
    if out.utcoffset() is None:raise InvalidInput('TIMEZONE_REQUIRED')
    return out


def identity():
    return {'base_predicate_version':BASE_VERSION,'amendment_id':AMENDMENT_ID,
        'amendment_version':AMENDMENT_VERSION,'ruleset_sha256':RULESET_SHA256,
        'effective_predicate_version':EFFECTIVE_VERSION}


def load_rules(source,evaluation_at):
    raw=Path(source['local_path']).read_bytes()
    if source.get('sha256')!=RULESET_SHA256 or sha256(raw).hexdigest()!=RULESET_SHA256:
        raise ReviewRequired('RULESET_BYTES_OR_VERSION_MISMATCH')
    rules=json.loads(raw)
    if (rules.get('amendment_id'),rules.get('amendment_version'),rules.get('base_predicate_version'))!=(AMENDMENT_ID,AMENDMENT_VERSION,BASE_VERSION):
        raise ReviewRequired('AMENDMENT_VERSION_MISMATCH')
    if time(EFFECTIVE_AT)>time(evaluation_at) or time(source['ingested_at'])>time(evaluation_at):
        raise ReviewRequired('AMENDMENT_NOT_YET_AVAILABLE')
    return rules


def read_official(source,key,evaluation_at):
    raw=Path(source['local_path']).read_bytes();receipt_raw=Path(source['receipt_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256'] or sha256(receipt_raw).hexdigest()!=source['receipt_sha256']:
        raise ReviewRequired('OFFICIAL_SOURCE_BYTES_CHANGED:'+key)
    receipt=json.loads(receipt_raw);url=urlparse(receipt['url'])
    valid=(url.scheme=='https' and url.netloc=='www.federalreserve.gov' and url.path=='/aboutthefed/k8.htm') if key=='FED_K8' else (
        url.scheme=='https' and url.netloc=='fred.stlouisfed.org' and url.path=='/graph/fredgraph.csv'
        and parse_qs(url.query).get('id')==[key])
    if not valid or receipt.get('http_status')!=200 or receipt.get('sha256')!=source['sha256']:
        raise ReviewRequired('OFFICIAL_SOURCE_IDENTITY:'+key)
    retrieved=receipt.get('retrieved_at')
    if time(receipt['requested_at'])>time(retrieved) or time(retrieved)>time(evaluation_at):
        raise ReviewRequired('SOURCE_NOT_AVAILABLE_AT_EVALUATION:'+key)
    return raw,receipt


class CalendarHTML(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,value):
        if self.cell is not None:self.cell.append(value)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None


def holiday_dates(year):
    def nth(month,weekday,n):
        first=date(year,month,1);return first+timedelta(days=(weekday-first.weekday())%7+7*(n-1))
    may=nth(5,0,4)
    if (may+timedelta(days=7)).month==5:may+=timedelta(days=7)
    return [date(year,1,1),nth(1,0,3),nth(2,0,3),may,date(year,6,19),date(year,7,4),
        nth(9,0,1),nth(10,0,2),date(year,11,11),nth(11,3,4),date(year,12,25)]


def is_fed_business(day):
    holidays=holiday_dates(day.year)
    closed=set(holidays)|{h+timedelta(days=1) for h in holidays if h.weekday()==6}
    return day.weekday()<5 and day not in closed


def calendar(raw):
    text=raw.decode('utf-8-sig')
    required=('Federal Reserve Banks and Branches will be open the preceding Friday',
        'For holidays falling on Sunday','2026-2030')
    if not all(s in text for s in required):raise ReviewRequired('K8_BANKS_CALENDAR_CONTRACT')
    parser=CalendarHTML();parser.feed(text)
    headers=[i for i,r in enumerate(parser.rows) if r==['','2026','2027','2028','2029','2030']]
    if len(headers)!=1:raise ReviewRequired('K8_PUBLISHED_YEAR_HEADERS')
    rows=parser.rows[headers[0]+1:headers[0]+12]
    if len(rows)!=11 or any(len(r)!=6 for r in rows):raise ReviewRequired('K8_HOLIDAY_TABLE')
    for y in range(2026,2031):
        for expected,row in zip(holiday_dates(y),rows):
            try:actual=datetime.strptime(str(y)+' '+row[y-2025].replace('*',''),'%Y %B %d').date()
            except ValueError as error:raise InvalidInput('K8_DATE_FORMAT') from error
            if actual!=expected:raise ReviewRequired('K8_PUBLISHED_HOLIDAY_MISMATCH')
    return {'calendar_id':CALENDAR_ID,'calendar_version':CALENDAR_VERSION,
        'source_sha256':sha256(raw).hexdigest(),'published_holiday_dates_validated':55,
        'saturday_prior_friday_open':True,'sunday_following_monday_closed':True}


def age(observed,evaluated):
    if observed>=evaluated:raise InvalidInput('OBSERVATION_MUST_PRECEDE_NY_EVALUATION_DATE')
    return sum(is_fed_business(observed+timedelta(days=i)) for i in range(1,(evaluated-observed).days+1))


def points(raw,key):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or set(rows[0])!={'observation_date',key}:raise ReviewRequired('FRED_SERIES_COLUMNS:'+key)
    try:return unique((date.fromisoformat(r['observation_date']),None if r[key] in ('','.') else r[key]) for r in rows)
    except (ValueError,TypeError) as error:
        if isinstance(error,(InvalidInput,ReviewRequired)):raise
        raise InvalidInput('FRED_OBSERVATION_FORMAT:'+key) from error


def unavailable(kind,reason=None):
    return {'candidate':kind,'field':FIELDS[kind],'source_ids':[],
        'units':'bps' if kind in ('R','C') else 'USD' if kind=='S' else 'percentile_0_100',
        'observation_date':None,'retrieved_at':None,'age_business_days':None,'value':None,
        'history_n':None,'history_span_days':None,'Q95':None,'Q99':None,'A':None,'S':None,
        'state':None,'available':False,'reason':reason,'abnormal':None,'severe':None}


def rate_inputs(kind,source,evaluation_at):
    a,b=('SOFR','IORB') if kind=='R' else ('DCPF3M','DTB3')
    series={};receipts={};errors=[]
    for key in (a,b):
        item=source.get('series',{}).get(key)
        if item is None:continue
        try:
            if item.get('unit')!='PERCENT' or (kind=='C' and item.get('basis')!='DISCOUNT_360'):
                raise InvalidInput('RATE_UNIT_OR_DISCOUNT_BASIS:'+key)
            raw,receipt=read_official(item,key,evaluation_at);series[key]=points(raw,key);receipts[key]=receipt
        except (InvalidInput,ReviewRequired) as error:errors.append(error)
    if errors:raise next((e for e in errors if isinstance(e,InvalidInput)),errors[0])
    return series,receipts


def candidate(kind,source,rules,evaluation_at,calendar_info,loaded=None):
    result=unavailable(kind);a,b=(rules['signals'][kind][x] for x in ('left','right'))
    series,receipts=loaded if loaded is not None else rate_inputs(kind,source,evaluation_at)
    if len(series)<2:return {**result,'reason':'SOURCE_NOT_ACQUIRED:'+','.join(k for k in (a,b) if k not in series)}
    result.update(source_ids=[rules['signals'][kind]['left_source'],rules['signals'][kind]['right_source']],
        retrieved_at={k:v['retrieved_at'] for k,v in receipts.items()},calendar=deepcopy(calendar_info),
        vintage_basis='RESTATED_CURRENT_VINTAGE__NOT_HISTORICAL_PIT')
    if a=='IORB' or b=='IORB':
        if any(d<date(2021,7,29) and v is not None for d,v in series['IORB'].items()):
            raise ReviewRequired('IORB_BEFORE_INCEPTION__NO_IOER_IORR_SPLICE')
    paired=[(d,spread(v,series[b].get(d))) for d,v in series[a].items()]
    evaluated=time(evaluation_at).astimezone(ZoneInfo('America/New_York')).date()
    valid=[(d,v) for d,v in paired if d<evaluated and v is not None]
    if not valid:return {**result,'reason':'NO_SAME_DATE_PAIR'}
    observed,value=max(valid);business_age=age(observed,evaluated)
    result.update(observation_date=observed.isoformat(),value=str(value),age_business_days=business_age,
        held_recent_cp_pair=kind=='C' and business_age>1,
        legs={k:{'value':str(series[k][observed]),'unit':'PERCENT','observation_date':str(observed)} for k in (a,b)})
    if business_age>rules['signals'][kind]['age_max_fed_business_days']:return {**result,'reason':'STALE'}
    for key in (a,b):
        q=parse_qs(urlparse(receipts[key]['url']).query)
        try:start=date.fromisoformat(q['cosd'][0]);end=date.fromisoformat(q['coed'][0])
        except (KeyError,ValueError,TypeError) as error:raise ReviewRequired('SOURCE_REQUEST_WINDOW_REQUIRED') from error
        if start>start_date(observed) or end<observed:
            return {**result,'reason':'SOURCE_REQUEST_WINDOW_NOT_COVERED'}
    history=calibrated(kind,paired,observed,rules);result.update(history)
    if result['A'] is None:return {**result,'reason':'INSUFFICIENT_HISTORY'}
    state=level(value,result['A'],result['S'])
    return {**result,'state':state,'available':True,'reason':None,
        'abnormal':state in ('ABNORMAL','SEVERE'),'severe':state=='SEVERE'}


def legacy_candidate(kind,item,evaluation_at):
    result={**unavailable(kind),'source_ids':deepcopy(item.get('source_ids',[])),
        'observation_date':item.get('observation_date'),'retrieved_at':item.get('retrieved_at')}
    if 'units' in item and item['units']!=result['units']:raise InvalidInput('LEGACY_CANDIDATE_UNIT:'+kind)
    if result['observation_date'] is not None:
        try:date.fromisoformat(result['observation_date'])
        except (ValueError,TypeError) as error:raise InvalidInput('LEGACY_OBSERVATION_DATE:'+kind) from error
    if result['retrieved_at'] is not None and time(result['retrieved_at'])>time(evaluation_at):
        raise ReviewRequired('FUTURE_LEGACY_SOURCE:'+kind)
    value=item.get('value')
    if value is None:return {**result,'reason':item.get('reason','DATA_NOT_ACQUIRED')}
    if item.get('units')!=result['units']:raise InvalidInput('LEGACY_CANDIDATE_UNIT:'+kind)
    value=exact(value)
    if value<0 or (kind=='D' and value>100):raise InvalidInput('LEGACY_CANDIDATE_DOMAIN:'+kind)
    if not result['source_ids'] or not result['observation_date'] or not result['retrieved_at']:
        raise ReviewRequired('LEGACY_SOURCE_PROVENANCE:'+kind)
    if time(result['retrieved_at'])>time(evaluation_at):raise ReviewRequired('FUTURE_LEGACY_SOURCE:'+kind)
    result['value']=str(value)
    try:observed=date.fromisoformat(result['observation_date'])
    except (ValueError,TypeError) as error:raise InvalidInput('LEGACY_OBSERVATION_DATE:'+kind) from error
    evaluated=time(evaluation_at).astimezone(ZoneInfo('America/New_York')).date()
    if observed>evaluated:raise InvalidInput('FUTURE_LEGACY_OBSERVATION:'+kind)
    result['age_business_days']=age(observed,evaluated) if observed<evaluated else 0
    if item.get('freshness_verified') is not True:return {**result,'reason':'FRESHNESS_NOT_VERIFIED'}
    if kind=='S':state=level(value,'5000000000','20000000000')
    else:state='SEVERE' if value<=5 else 'ABNORMAL' if value<=20 else 'NORMAL'
    return {**result,'state':state,'available':True,'reason':None,
        'abnormal':state in ('ABNORMAL','SEVERE'),'severe':state=='SEVERE'}


def assess(source,evaluation_at,legacy_candidates):
    signals={k:unavailable(k) for k in FIELDS};quality=[];rules=None;cal=None
    try:
        if source.get('schema_version')!='Family.W5.Pred007AmendmentSource.v1':raise ReviewRequired('AMENDMENT_SOURCE_SCHEMA')
        rules=load_rules(source['ruleset'],evaluation_at)
        raw,receipt=read_official(source['calendar'],'FED_K8',evaluation_at)
        cal={**calendar(raw),'source_reference':receipt['url'],'retrieved_at':receipt['retrieved_at']}
    except (ValueError,KeyError,TypeError,OSError,UnicodeError) as error:
        if not isinstance(error,(InvalidInput,ReviewRequired)):
            error=ReviewRequired('SOURCE_FILE_UNAVAILABLE') if isinstance(error,OSError) else InvalidInput('SOURCE_STRUCTURE_INVALID')
        quality.append('INVALID_INPUT' if isinstance(error,InvalidInput) else 'REVIEW_REQUIRED')
        for k in ('R','C'):signals[k]['reason']=str(error)
    for kind in FIELDS:
        try:
            if kind in ('R','C'):
                # Input quality is checked even when a separate version or
                # calendar veto prevents threshold evaluation.
                loaded=rate_inputs(kind,source,evaluation_at)
                if rules is not None and cal is not None:signals[kind]=candidate(kind,source,rules,evaluation_at,cal,loaded)
            else:signals[kind]=legacy_candidate(kind,legacy_candidates.get(kind,{}),evaluation_at)
        except (ValueError,KeyError,TypeError,OSError,UnicodeError) as error:
            if not isinstance(error,(InvalidInput,ReviewRequired)):
                error=ReviewRequired('SOURCE_FILE_UNAVAILABLE') if isinstance(error,OSError) else InvalidInput('SOURCE_STRUCTURE_INVALID')
            quality.append('INVALID_INPUT' if isinstance(error,InvalidInput) else 'REVIEW_REQUIRED')
            signals[kind]['reason']=str(error)
    return {**identity(),**aggregate(signals,quality),'eval_at_utc':time(evaluation_at).astimezone(timezone.utc).isoformat(),
        'eval_date_ny':str(time(evaluation_at).astimezone(ZoneInfo('America/New_York')).date()),
        'signals':signals,'quality_vetoes':quality,'calendar':cal,
        'normalized_fields':{FIELDS[k]:signals[k]['value'] for k in FIELDS},
        'composite_basis':'LATEST_AVAILABLE_OBSERVATIONS_WITH_PER_CANDIDATE_DATES',
        'risk_disclosure':'NEW_DELEGATED_POLICY_FLOORS; NO_CRISIS_BACKTEST_OR_PERFORMANCE_VALIDATION; CORRELATED_VOTES_NOT_CONFIDENCE',
        'execution':'ON_DEMAND_NO_NEW_SCHEDULE','trade_action':'NO_TRADE'}


def evaluate(metrics,evaluation_at,currency='USD'):
    if currency!='USD':raise InvalidInput('AMENDMENT_SCOPE_USD_ONLY')
    if set(metrics)!={'amendment_source','legacy_candidates'}:raise InvalidInput('AMENDMENT_FIELDS__NO_RETIRED_ALIASES')
    assessment=assess(metrics['amendment_source'],evaluation_at,metrics['legacy_candidates'])
    from v75_runtime.models import PredicateResult
    marker='AMENDMENT:'+AMENDMENT_ID+'@'+AMENDMENT_VERSION+';RULESET_SHA256:'+RULESET_SHA256
    refs=[marker]+list(dict.fromkeys(s for row in assessment['signals'].values() for s in row['source_ids']))
    model=PredicateResult(predicate_id='PRED-007',predicate_version=BASE_VERSION,
        assessment_status=assessment['assessment_status'],aggregate_state=assessment['aggregate_state'],
        sub_states=assessment['sub_states'],as_of=time(evaluation_at),source_lineage=refs,
        input_freshness_state='FRESH' if assessment['assessment_status']=='VALID' else 'UNKNOWN',
        reason_codes=[*assessment['warnings'],'EXPLICIT_BASE_MODEL_AMENDMENT_VERSION_MAPPING'],
        required_input_missing=[] if assessment['assessment_status']=='VALID' else
            [r['candidate']+':'+str(r['reason']) for r in assessment['missing_candidates']])
    return model,assessment


def bind(request,context):
    """Operator-bound source/version is revalidated before replay or dispatch."""
    from family_boundary import require
    from family_input import digest
    source=context.get('v75_pred007_source');legacy=context.get('v75_pred007_legacy_candidates')
    facts=request.get('native_bundle',{}).get('bond_evidence',{})
    amended=[v for v in facts.values() if 'amendment_source' in v.get('metrics',{}).get('PRED-007',{})]
    if source is None:
        require(not amended and not request.get('v75_pred007_source_digest'),
            'PRED007_AMENDMENT_SOURCE_REQUIRED','trusted_context.v75_pred007_source')
        return None
    require(request['expected_versions'].get('v75_pred007')==EFFECTIVE_VERSION,
        'PRED007_AMENDMENT_VERSION_MISMATCH','expected_versions.v75_pred007')
    if context.get('native_binding'):
        require(source.get('data_provenance')==context['native_binding']['data_provenance'],
            'PRED007_SOURCE_PROVENANCE_MISMATCH','v75_pred007_source.data_provenance')
    require(request.get('v75_pred007_source_digest')==digest({'source':source,'legacy_candidates':legacy}),
        'PRED007_AMENDMENT_SOURCE_DIGEST_MISMATCH','v75_pred007_source_digest')
    expected={'amendment_source':source,'legacy_candidates':legacy}
    for asset,row in facts.items():
        if row.get('currency')=='USD':
            require(row['metrics'].get('PRED-007')==expected,'PRED007_AMENDMENT_INPUT_MISMATCH','bond_evidence.'+asset+'.PRED-007')
    return assess(source,request['evaluation_at'],legacy or {})


def describe(assessment):
    r=assessment['signals']['R'];c=assessment['signals']['C']
    return ('流動性採新正式裁定 '+assessment['amendment_id']+' v'+assessment['amendment_version']+
        '：SOFR−IORB '+str(r['value'])+' bps（'+str(r['observation_date'])+'）；AA金融90日CP−3月國庫券discount利差 '+
        str(c['value'])+' bps（'+str(c['observation_date'])+'）。可用訊號 '+assessment['coverage_count']+
        '，判斷 '+str(assessment['aggregate_state'] or assessment['assessment_status'])+
        ('；市場深度尚未取得，保留部分涵蓋註記' if any(x['candidate']=='D' for x in assessment['missing_candidates']) else '')+
        ('；CP採近期同日配對值，未以今日國庫券利率混減' if 'HELD_RECENT_CP_PAIR' in assessment['warnings'] else '')+
        '。NORMAL僅描述可用訊號，不表示四項齊備；涵蓋率不是可信度。新門檻未經危機PIT回測或績效驗證。')
