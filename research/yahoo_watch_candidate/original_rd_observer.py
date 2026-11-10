"""Original approved daily RD formula, source-observation scope only.
No valuation dependency, financial eligibility, buy recommendation or trading.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib,json,subprocess,sys,tempfile,urllib.request,urllib.parse

COMMIT='3f7ea0dcd2963ae55598ffa90b36893ed47cc9bb'

def observed_rd(symbol,root,now=None):
    now=now or datetime.now(timezone.utc);root=Path(root).resolve()
    result=dict(symbol=symbol,status='UNKNOWN',runaway_down='UNKNOWN',scope='OBSERVED_APPROVED_DAILY_FORMULA_NOT_BUY',formal_v82_executed=False)
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        return {**result,'reason':'ORIGINAL_COMMIT_MISMATCH'}
    if subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD']).returncode:
        return {**result,'reason':'ORIGINAL_SOURCE_MODIFIED'}
    sys.path[:0]=[str(root/'系統工程/Family/W8'),str(root/'系統工程/Family/W5')]
    from member_market_source import read_market
    if Path(read_market.__code__.co_filename).resolve()!=root/'系統工程/Family/W8/member_market_source.py':
        return {**result,'reason':'ORIGINAL_MODULE_SHADOWED'}
    from approved_v04_technical import load_profile
    import exchange_calendars as xc
    query=urllib.parse.urlencode(dict(range='1y',interval='1d',events='div,splits'))
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?'+query
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as response:raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:return {**result,'reason':'RESPONSE_TOO_LARGE'}
    acquired=datetime.now(timezone.utc);data=json.loads(raw)['chart']['result'][0];meta=data['meta']
    if meta.get('symbol')!=symbol:return {**result,'reason':'SOURCE_IDENTITY_MISMATCH'}
    if data.get('events',{}).get('splits'):return {**result,'reason':'SPLIT_IN_WINDOW_REQUIRES_SOURCE_QUALIFICATION'}
    if meta.get('instrumentType') not in ('ETF','EQUITY'):return {**result,'reason':'UNSUPPORTED_PRODUCT_TYPE'}
    tz=meta.get('exchangeTimezoneName')
    if tz=='America/New_York' and meta.get('currency')=='USD':cal_id='XNYS';exchange=meta['exchangeName']
    elif tz=='Asia/Taipei' and meta.get('currency')=='TWD' and symbol.endswith('.TW'):cal_id='XTAI';exchange='TWSE'
    else:return {**result,'reason':'UNSUPPORTED_MARKET_CALENDAR'}
    # Known fixed-income products retain their separate original V75 route.
    if symbol in {'SGOV','SPSB'}:return {**result,'reason':'FIXED_INCOME_NOT_V82_EQUITY_ROUTE'}
    start=datetime.fromtimestamp(data['timestamp'][0],ZoneInfo(tz)).date().isoformat()
    evaluation=max(now,acquired);cal=xc.get_calendar(cal_id,start=start,end=evaluation.date()+timedelta(days=7))
    sessions=[dict(session_id=str(d.date()),open_at=cal.session_open(d).isoformat(),close_at=cal.session_close(d).isoformat())
              for d in cal.sessions_in_range(start,str(evaluation.astimezone(ZoneInfo(tz)).date()))]
    calendar=dict(exchange=exchange,timezone=tz,provider='exchange_calendars',version=xc.__version__,
                  coverage_cutoff=evaluation.isoformat(),sessions=sessions,scope='IDENTIFIED_CALENDAR_OBSERVATION_NOT_OFFICIAL_PIT')
    def desc(p):return dict(local_path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'raw.json';p.write_bytes(raw);c=Path(tmp)/'calendar.json';c.write_text(json.dumps(calendar))
        source={**desc(p),'provider':'YAHOO_CHART','symbol':symbol,'provider_symbol':symbol,'currency':meta['currency'],
                'timezone':tz,'exchange':exchange,'provider_exchange':meta['exchangeName'],'source_reference':url,
                'retrieved_at':acquired.isoformat(),'calendar_source':desc(c)}
        observed=read_market(source,symbol=symbol,evaluation_at=evaluation.isoformat(),repo_root=root,
            profile=load_profile(root/'系統工程/Family/W8/owner_approved_v10.json'),is_etf=meta['instrumentType']=='ETF')
    fresh=observed['observed_date']==observed['latest_expected_completed_session']
    # The original boundary explicitly flags provider OHLC as observations,
    # not canonical financial input. Preserve that distinction downstream.
    aggregate=observed['v82_original_aggregation']
    return {**result,'status':'OBSERVED_DAILY_FORMULA' if fresh else 'UNKNOWN','last_session':observed['observed_date'],
            'rows':observed['rows'],'source_sha256':source['sha256'],'calendar':cal_id,
            'reason':'ORIGINAL_RD_FORMULA_ON_PROVIDER_OBSERVATIONS' if fresh else 'LATEST_COMPLETED_SESSION_MISSING',
            'runaway_down':aggregate.get('runaway_down','UNKNOWN') if fresh else 'UNKNOWN',
            'last_observed_runaway_down':aggregate.get('runaway_down','UNKNOWN'),
            'expected_session':observed['latest_expected_completed_session']}
