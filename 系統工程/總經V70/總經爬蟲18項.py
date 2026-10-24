#!/usr/bin/env python3
# 最後修改：2026/10/19 18:14（台灣時間）｜版本：D009-v3｜檔案：總經爬蟲18項.py
# -*- coding: utf-8 -*-
"""LivingWaterAI V70.3: 18 independently sourced/calculated indicators.
Eight supplementary raw inputs (four m06 components, three Forward P/E fields, and s05) are supplied by the 10:00 Task; m06 is derived downstream. They are EXCLUDED from this 18-item crawler.
17 series use the prior official/live sourcing and verified overrides; m16 reads
published LEI YoY and carries three-month auxiliary history, refreshed monthly.
The s03 VIX transport duplicate is included but excluded from independent count.
Existing runner and source modules preserved; output is 18_macro_verification.
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import os
import sys
import time
import tempfile
import hashlib
from pathlib import Path

D009_RUN_STARTED=time.monotonic()
D009_FETCH_DEADLINE_SECONDS=18*60

try:
    import requests
    import pandas as pd
except ImportError as e:
    raise SystemExit("缺套件，請執行：pip install requests pandas yfinance") from e

FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id='
LABELS = {
 'm07':'VIX','m01':'10Y−2Y 殖利率曲線',
 'm08':'10Y 實質殖利率',
 'm02':'HY OAS','m04':'ISM 製造業 PMI',
 'm05':'Core CPI YoY','m09':'DXY','m10':'WTI','m12':'MOVE',
 'm13':'5Y Breakeven','m17':'5Y Breakeven 近1月變化（pp）','m14':'淨流動性 13週變化（$bn）',
 'm15':'ISM 服務業 PMI','m16':'LEI YoY','m18':'Sahm Rule','m19':'U3 失業率',
 'm20':'3個月平均非農新增就業（千人）','s03':'VIX 短期','s04':'CNN Fear & Greed',
}
BOUNDS = {'m07':(0,150),'s03':(0,150),'m01':(-10,15),'m08':(-10,20),
          'm02':(0,60),'m04':(0,100),'m15':(0,100),'m05':(-10,25),
          'm09':(30,250),'m10':(-50,400),'m12':(0,400),'m13':(-10,20),
          'm17':(-10,10),'m18':(-5,15),'m19':(0,40),'s04':(0,100),'s05':(0,100)}
# BOUNDS are broad sanity limits, not economic grading thresholds.
UNITS = {'m01':'%','m08':'%','m02':'%','m05':'%','m10':'USD/bbl',
         'm13':'%','m17':'pp','m14':'USD bn','m16':'%','m19':'%','m20':'千人','s05':'%'}
SOURCES = {
 'm04':['https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'],
 'm15':['https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'],
 'm16':['https://www.conference-board.org/topics/us-leading-indicators'],
 's04':['https://edition.cnn.com/markets/fear-and-greed'],
 'm12':['https://finance.yahoo.com/quote/%5EMOVE/'],
}
for k, series in {'m07':'VIXCLS','m01':'T10Y2Y','m08':'DFII10',
                  'm02':'BAMLH0A0HYM2','m13':'T5YIE','m18':'SAHMCURRENT',
                  'm19':'UNRATE'}.items():
    SOURCES[k]=['https://fred.stlouisfed.org/series/'+series]
for k in ('m17',): SOURCES[k]=['https://fred.stlouisfed.org/series/T5YIE']
SOURCES['m14']=['https://fred.stlouisfed.org/series/'+s for s in ('WALCL','WDTGAL','RRPONTSYD')]
SOURCES['m20']=['https://fred.stlouisfed.org/series/PAYEMS']
SOURCES['m05']=['https://fred.stlouisfed.org/series/CPILFESL']
SOURCES['m09']=['https://finance.yahoo.com/quote/DX-Y.NYB/']
SOURCES['m10']=['https://finance.yahoo.com/quote/CL=F/']

def load_source_config():
    """Fail closed on incomplete D009 source configuration."""
    path=Path(__file__).resolve().with_name('macro_source_config.json')
    config=json.loads(path.read_text(encoding='utf-8'))
    if config.get('schema')!='LivingWaterAI-D009-source-config-v1':
        raise ValueError('D009 config schema mismatch')
    indicators=config.get('indicators')
    expected=set(LABELS)-{'s03'}
    if not isinstance(indicators,dict) or set(indicators)!=expected:
        raise ValueError('D009 config must contain exactly 18 independent indicators')
    for key,entry in indicators.items():
        if not isinstance(entry,dict) or not isinstance(entry.get('primary_source'),str) or not entry['primary_source']:
            raise ValueError('D009 missing primary source: '+key)
        if not isinstance(entry.get('backup_sources'),list) or not all(isinstance(x,str) and x for x in entry['backup_sources']):
            raise ValueError('D009 invalid backup sources: '+key)
        if type(entry.get('max_age_days')) is not int or not 1<=entry['max_age_days']<=366:
            raise ValueError('D009 invalid freshness limit: '+key)
        tolerance=entry.get('tolerance')
        if not isinstance(tolerance,dict) or type(tolerance.get('absolute')) not in (int,float) or not 0<float(tolerance['absolute'])<100:
            raise ValueError('D009 invalid tolerance: '+key)
    return config


def atomic_write_text(path, content):
    """Replace validated UTF-8 output atomically, leaving prior file intact on failure."""
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class Fetcher:
    def __init__(self, timeout=40):
        self.s=requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry=Retry(total=1, connect=1, read=1, backoff_factor=1.0,
                    status_forcelist=[502,503,504],
                    allowed_methods=frozenset(['GET']), respect_retry_after_header=True)
        adapter=HTTPAdapter(max_retries=retry)
        self.s.mount('https://',adapter)
        self.s.headers.update({
            'User-Agent':'LivingWaterAI-MacroCollector/1.3 (+GitHub Actions; official data research)',
            'Accept':'application/json,text/csv,text/plain,*/*',
            'Accept-Language':'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding':'gzip, deflate',
            'Connection':'keep-alive',
        })
        self.timeout=timeout
        self.fredcache={}
        # D009: one-run HTTP cache; keep cached responses only after success.
        self._http_cache={}
        self._host_last_request={}
        original_get=self.s.get
        def cached_get(url, **kwargs):
            if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
                raise TimeoutError('D009 request budget exhausted; no new GET')
            from urllib.parse import urlencode
            params=kwargs.get('params') or {}
            kwargs.setdefault('timeout',(5,self.timeout))
            # Never share cached responses across authenticated requests.
            sensitive=bool(kwargs.get('auth') or kwargs.get('cookies') or
                           any(str(k).lower() in ('authorization','cookie','x-api-key')
                               for k in (kwargs.get('headers') or {})))
            key=(url,tuple(sorted((str(k),str(v)) for k,v in params.items())))
            if not sensitive and key in self._http_cache:
                return self._http_cache[key]
            from urllib.parse import urlsplit
            host=urlsplit(url).netloc.lower()
            previous=self._host_last_request.get(host)
            if previous is not None:
                wait=max(0.0, 1.0-(time.monotonic()-previous))
                if wait:
                    time.sleep(wait)
            if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
                raise TimeoutError('D009 fetch deadline reached during provider throttle')
            self._host_last_request[host]=time.monotonic()
            response=original_get(url, **kwargs)
            response.raise_for_status()
            if not sensitive:
                self._http_cache[key]=response
            return response
        self.s.get=cached_get
        self.frederrors={}
        self.fredsources={}
        self.fredattempts={}

    def fred(self, series):
        if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
            raise TimeoutError('D009 fetch deadline: FRED request refused')
        if hasattr(self,'job_series'): self.job_series.add(series)
        if series in self.fredcache: return self.fredcache[series]
        if series in self.frederrors: raise RuntimeError(self.frederrors[series])
        from io import StringIO
        errors=[]
        # DBnomics series API requires provider/dataset/series; the former
        # FRED/<series> URL was invalid (HTTP 404), not a genuine fallback.
        providers=[('FRED_CSV', FRED+series)]
        if series=='VIXCLS':
            providers.insert(0,('CBOE_OFFICIAL_VIX','https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'))
            providers.append(('YAHOO_VIX_CHART','https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=1mo&interval=1d'))
        bls_map={'UNRATE':'LNS14000000','CPILFESL':'CUSR0000SA0L1E','PAYEMS':'CES0000000001'}
        if series in bls_map:
            providers.insert(0,('BLS_OFFICIAL_API','https://api.bls.gov/publicAPI/v1/timeseries/data/'+bls_map[series]))
        if series in bls_map:
            providers.insert(0,('BLS_HISTORY_V2','https://api.bls.gov/publicAPI/v2/timeseries/data/'))
        if series in bls_map:
            providers.insert(1,('BLS_HISTORY_V1','https://api.bls.gov/publicAPI/v1/timeseries/data/'))
        # Optional official FRED API when a GitHub Actions secret is configured.
        api_key=os.environ.get('FRED_API_KEY','').strip()
        if api_key:
            from urllib.parse import urlencode
            # Bounded official queries: enough history for 13-week liquidity,
            # 12-month CPI YoY, Sahm lookback, and 1-month breakeven change.
            lookback_days=900 if series in ('UNRATE','CPILFESL','PAYEMS') else 210
            earliest=(dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=lookback_days)).isoformat()
            params=urlencode({'series_id':series,'api_key':api_key,'file_type':'json',
                              'observation_start':earliest})
            providers.insert(0,('FRED_OFFICIAL_API','https://api.stlouisfed.org/fred/series/observations?'+params))
        retried=set()
        self.fredattempts[series]=[]
        for provider,url in providers:
            if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
                errors.append('D009 fetch deadline reached')
                break
            response=None
            try:
                if provider in ('BLS_HISTORY_V2','BLS_HISTORY_V1'):
                    current_year=dt.datetime.now().year
                    payload={'seriesid':[bls_map[series]],'startyear':str(current_year-3),'endyear':str(current_year)}
                    response=self.s.post(url,json=payload,timeout=(5,self.timeout))
                else:
                    response=self.s.get(url,timeout=(5,self.timeout))
                response.raise_for_status()
                if provider in ('BLS_OFFICIAL_API','BLS_HISTORY_V2','BLS_HISTORY_V1'):
                    obj=response.json()
                    if obj.get('status')!='REQUEST_SUCCEEDED':
                        raise ValueError('BLS response: '+str(obj.get('message'))[:130])
                    data_series=obj['Results']['series']
                    if len(data_series)!=1 or data_series[0].get('seriesID')!=bls_map[series]:
                        raise ValueError('BLS_RESPONSE_SERIES mismatch')
                    dataset=data_series[0]['data']
                    monthly=[x for x in dataset if x.get('period','').startswith('M') and x['period']!='M13']
                    dates=pd.to_datetime([x['year']+'-'+x['period'][1:]+'-01' for x in monthly],errors='coerce')
                    values=pd.to_numeric([x['value'].replace(',','') for x in monthly],errors='coerce')
                elif provider=='YAHOO_VIX_CHART':
                    chart=response.json()['chart']['result'][0]
                    stamps=chart['timestamp']
                    closes=chart['indicators']['quote'][0]['close']
                    dates=pd.to_datetime(stamps,unit='s',utc=True).tz_convert(None)
                    values=pd.to_numeric(closes,errors='coerce')
                elif provider=='CBOE_OFFICIAL_VIX':
                    frame=pd.read_csv(StringIO(response.text))
                    frame.columns=[str(x).strip().upper() for x in frame.columns]
                    if 'DATE' not in frame.columns or 'CLOSE' not in frame.columns:
                        raise ValueError('CBOE CSV schema mismatch')
                    dates=pd.to_datetime(frame['DATE'],errors='coerce')
                    values=pd.to_numeric(frame['CLOSE'],errors='coerce')
                elif provider=='FRED_OFFICIAL_API':
                    obs=response.json()['observations']
                    dates=pd.to_datetime([x['date'] for x in obs],errors='coerce')
                    values=pd.to_numeric([x['value'] for x in obs],errors='coerce')
                elif provider=='FRED_CSV':
                    frame=pd.read_csv(StringIO(response.text))
                    datecol='DATE' if 'DATE' in frame.columns else 'observation_date'
                    if datecol not in frame or series not in frame: raise ValueError('CSV schema mismatch')
                    dates=pd.to_datetime(frame[datecol],errors='coerce')
                    values=pd.to_numeric(frame[series],errors='coerce')
                else:
                    datasets=response.json()['series']['docs']
                    doc=next(d for d in datasets if d.get('series_code')==series)
                    dates=pd.to_datetime(doc['period'],errors='coerce')
                    values=pd.to_numeric(doc['value'],errors='coerce')
                data=pd.DataFrame({'date':dates,'value':values}).dropna()
                data=data.sort_values('date').drop_duplicates('date',keep='last')
                if data.empty: raise ValueError('No numeric observations')
                out=pd.Series(data['value'].to_numpy(),index=pd.DatetimeIndex(data['date']),name=series)
                # Reject truncated BLS histories before caching: allow the next
                # provider to supply sufficient data for the actual calculation.
                if series in bls_map:
                    monthly=out.groupby(out.index.to_period('M')).last().sort_index()
                    period=monthly.index[-1]
                    if series=='UNRATE':
                        required=pd.PeriodIndex([period],freq='M')  # current U3; Sahm enforces 15 months
                    elif series=='PAYEMS':
                        required=pd.period_range(period-3,period,freq='M')
                    else:
                        required=pd.PeriodIndex([period-12,period],freq='M')
                    missing=[str(p) for p in required if p not in monthly.index]
                    if missing:
                        raise ValueError('Insufficient '+series+' history; missing '+','.join(missing))
                self.fredcache[series]=out
                self.fredsources[series]=(provider,url.split('?')[0] if provider=='FRED_OFFICIAL_API' else url)
                self.fredattempts[series].append({'provider':provider,'result':'OK',
                    'verified_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'observation_date':str(out.index[-1].date())})
                print('FRED_PROVIDER',series,provider,str(out.index[-1].date()),flush=True)
                return out
            except Exception as exc:
                detail=str(exc)
                if api_key: detail=detail.replace(api_key,'[REDACTED]')
                diagnostic=provider+': '+type(exc).__name__+': '+detail[:220]
                # HTTP 200 is not proof of valid provider data. Preserve safe
                # response metadata, not response bodies or API credentials.
                attempt={'provider':provider,'result':'FAILED','error':diagnostic,
                         'attempted_at':dt.datetime.now(dt.timezone.utc).isoformat()}
                if response is not None:
                    body=getattr(response,'content',b'')
                    attempt.update(http_status=getattr(response,'status_code',None),
                        content_type=getattr(response,'headers',{}).get('Content-Type',''),
                        response_sha256=hashlib.sha256(body).hexdigest())
                self.fredattempts[series].append(attempt)
                errors.append(diagnostic)
                print('DATA_SOURCE_FAILED',series,diagnostic,flush=True)
                # A malformed successful FRED response used to be cached and
                # immediately abandoned. Retry it once with the HTTP cache
                # cleared; normal provider throttling/deadline still apply.
                malformed=isinstance(exc,(ValueError,pd.errors.ParserError))
                if (provider in ('FRED_OFFICIAL_API','FRED_CSV') and malformed
                        and response is not None and getattr(response,'status_code',0)==200
                        and provider not in retried):
                    retried.add(provider)
                    self._http_cache.pop((url,()),None)
                    providers.insert(providers.index((provider,url))+1,(provider,url))
        message='All FRED sources failed for '+series+' | '+' | '.join(errors)
        self.frederrors[series]=message
        raise RuntimeError(message)

    def yahoo(self,ticker,info_key=None):
        if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
            raise TimeoutError('D009 fetch deadline: Yahoo request refused')
        if info_key:
            raise ValueError('ETF valuation requires verified as-of date; use official source overrides')
        errors=[]
        try:
            import yfinance as yf
            h=yf.Ticker(ticker).history(period='1mo',auto_adjust=False,timeout=self.timeout)
            if not h.empty:
                valid=h.dropna(subset=['Close'])
                if not valid.empty:
                    return float(valid.iloc[-1]['Close']),str(valid.index[-1].date())
            errors.append('yfinance: empty')
        except Exception as exc:
            errors.append('yfinance: '+type(exc).__name__+': '+str(exc)[:110])
        # Yahoo public chart JSON fallback: actual timestamp from quote data.
        try:
            from urllib.parse import quote
            url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')
            r=self.s.get(url,params={'range':'1mo','interval':'1d'},timeout=(5,self.timeout))
            r.raise_for_status()
            v=r.json()['chart']['result'][0]
            closes=v['indicators']['quote'][0]['close']
            points=[(stamp,price) for stamp,price in zip(v['timestamp'],closes) if price is not None and math.isfinite(float(price))]
            if not points: raise ValueError('empty chart prices')
            ts,price=points[-1]
            return float(price),dt.datetime.fromtimestamp(ts,dt.timezone.utc).date().isoformat()
        except Exception as exc:
            errors.append('yahoo chart: '+type(exc).__name__+': '+str(exc)[:110])
        raise RuntimeError(' | '.join(errors))

def row(key, value=None, date=None, src=None, method=None, error=None, status=None, detail=None):
    if status is None: status='OK' if (value is not None and date and src) else 'MISSING'
    if value is not None:
        if not math.isfinite(float(value)):
            raise ValueError(f'{key} 回傳非有限數值，拒絕 NaN/Infinity')
        bounds=BOUNDS.get(key)
        if bounds and not bounds[0]<=float(value)<=bounds[1]:
            raise ValueError(f'{key} 超出寬鬆合理範圍 {bounds}: {value}')
    if date:
        observed=dt.date.fromisoformat(str(date))
        if observed>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
            raise ValueError(f'{key} 觀測日期在未來: {date}')
    return {'id':key,'label':LABELS[key],'value':round(float(value),6) if value is not None else None,
            'unit':UNITS.get(key,''),'observation_date':date,'source_url':src,
            'method':method or '', 'status':status,'detail':detail or '', 'error':error or ''}

def treasury_breakeven(f, key):
    """5Y market breakeven from matching Treasury nominal and real yield dates."""
    from io import StringIO
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    for year in (today.year, today.year-1):
        def load(kind):
            url=('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/'
                 +f'daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv')
            resp=f.s.get(url,timeout=(5,f.timeout));resp.raise_for_status()
            df=pd.read_csv(StringIO(resp.text))
            df.columns=[str(x).strip().lower() for x in df.columns]
            if 'date' not in df.columns: raise ValueError('Treasury missing Date')
            col=next((x for x in ('5-year','5 year','5 yr') if x in df.columns),None)
            if col is None: raise ValueError('Treasury missing 5Y yield')
            df['date']=pd.to_datetime(df['date'],errors='coerce')
            df['yield']=pd.to_numeric(df[col],errors='coerce')
            return df[['date','yield']].dropna().drop_duplicates('date'),url
        try:
            nominal,u1=load('daily_treasury_yield_curve')
            real,u2=load('daily_treasury_real_yield_curve')
            both=nominal.merge(real,on='date',suffixes=('_nominal','_real')).sort_values('date')
            if both.empty: raise ValueError('Treasury nominal/real dates do not overlap')
            both['be']=both['yield_nominal']-both['yield_real']
            end=both.iloc[-1];asof=end['date']
            if key=='m13': val=float(end['be']);detail='5Y nominal minus 5Y TIPS real yield on same day'
            else:
                target=asof-pd.DateOffset(months=1)
                prior=both.loc[both['date']<=target]
                if prior.empty or (target-prior.iloc[-1]['date']).days>7:
                    raise ValueError('One-month breakeven reference unavailable or too old')
                val=float(end['be']-prior.iloc[-1]['be'])
                detail='5Y breakeven change from '+prior.iloc[-1]['date'].date().isoformat()
            return row(key,val,asof.date().isoformat(),u1+' | '+u2,
                       'Treasury derived five-year breakeven; not direct FRED T5YIE',detail=detail)
        except (ValueError,KeyError,requests.RequestException):
            if year==today.year-1: raise
    raise ValueError('Treasury breakeven unavailable')

def treasury_latest(f, key):
    """Treasury official daily CSV fallback for nominal 10Y-2Y and real 10Y."""
    from io import StringIO
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    kind='daily_treasury_yield_curve' if key=='m01' else 'daily_treasury_real_yield_curve'
    last_error=None
    for year in (today.year,today.year-1):
        url=('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/'
             +f'daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv')
        try:
            resp=f.s.get(url,timeout=(5,f.timeout))
            resp.raise_for_status()
            data=pd.read_csv(StringIO(resp.text))
            data.columns=[str(x).strip().lower() for x in data.columns]
            if 'date' not in data.columns: raise ValueError('Treasury CSV missing Date')
            data['date']=pd.to_datetime(data['date'],errors='coerce')
            def col(years):
                for s in (f'{years}-year',f'{years} year',f'{years} yr'):
                    if s in data.columns: return s
                raise ValueError(f'Treasury missing {years} year column; found {list(data.columns)}')
            y10=pd.to_numeric(data[col(10)],errors='coerce')
            if key=='m01':
                y2=pd.to_numeric(data[col(2)],errors='coerce')
                data['computed']=y10-y2
            else:
                data['computed']=y10
            data=data.dropna(subset=['date','computed']).sort_values('date')
            if data.empty: raise ValueError('Treasury CSV no numeric dated rows')
            last=data.iloc[-1]
            return row(key,float(last['computed']),last['date'].date().isoformat(),
                       url,'Treasury official '+kind+' daily CSV',
                       detail='Matched observation date for nominal 10Y minus 2Y' if key=='m01' else '10Y TIPS real yield')
        except Exception as exc: last_error=str(exc)[:230]
    raise RuntimeError('Treasury direct fallback failed: '+str(last_error))

def latest(f, key, name):
    if key in ('m01','m08'):
        try: return treasury_latest(f,key)
        except Exception as exc: print('TREASURY_FALLBACK',key,str(exc)[:220],flush=True)
    s=f.fred(name);d=s.index[-1].strftime('%Y-%m-%d')
    provider,source=f.fredsources.get(name,('FRED','https://fred.stlouisfed.org/series/'+name))
    return row(key,s.iloc[-1],d,source,provider+' 官方或鏡像時間序列')

def core_cpi(f):
    s=f.fred('CPILFESL');last=s.iloc[-1]
    # Compare calendar months, not identical day-of-month (FRED normally uses the first).
    last_period=s.index[-1].to_period('M')
    prior_period=last_period-12
    prior_series=s[s.index.to_period('M')==prior_period]
    current_series=s[s.index.to_period('M')==last_period]
    if len(prior_series)!=1 or len(current_series)!=1:
        raise ValueError(f'CPILFESL 缺唯一的去年同期基期 {prior_period} 或本期 {last_period}')
    prior_date=prior_series.index[0]
    prior=float(prior_series.iloc[0])
    if prior<=0 or float(last)<=0: raise ValueError('CPILFESL 指數必須大於0')
    val=(last/prior-1)*100
    return row('m05',val,s.index[-1].strftime('%Y-%m-%d'),getattr(f,'fredsources',{}).get('CPILFESL',('FRED',SOURCES['m05'][0]))[1],
               'FRED CPILFESL 同一數列 YoY','',detail=f'比較基期 {prior_date.date()}')

def breakeven_5y(f):
    try: return treasury_breakeven(f,'m13')
    except Exception as exc: print('TREASURY_BREAKEVEN_FALLBACK',str(exc)[:180],flush=True)
    return latest(f,'m13','T5YIE')

def month_delta(f):
    try: return treasury_breakeven(f,'m17')
    except Exception as exc: print('TREASURY_BREAKEVEN_FALLBACK',str(exc)[:180],flush=True)
    s=f.fred('T5YIE'); latest_date=s.index[-1]
    target=latest_date-pd.DateOffset(months=1)
    hist=s.loc[:target]
    if hist.empty: raise ValueError('5YBE 無 1 個月以前資料')
    # Never silently use a very old observation as the one-month baseline.
    if (target-hist.index[-1]).days>7:
        raise ValueError(f'5YBE 近1月基期過舊：目標 {target.date()}，實際 {hist.index[-1].date()}')
    return row('m17',float(s.iloc[-1]-hist.iloc[-1]),str(latest_date.date()),SOURCES['m17'][0],
               '近1個月前最近交易日差值（百分點）',detail=f'起點 {hist.index[-1].date()}')

def sahm_from_unrate(f):
    try:
        s=f.fred('UNRATE').sort_index()
        x=s.groupby(s.index.to_period('M')).last().sort_index()
        # The latest reported 15 calendar months must be consecutive; never bridge gaps.
        end=x.index[-1]
        expected=pd.period_range(end-14,end,freq='M')
        absent=[str(m) for m in expected if m not in x.index]
        if absent:
            # Official BLS CPS data for October 2025 do not exist due to the
            # federal shutdown. Do not interpolate or invent unemployment.
            official_gap='2025-10' in absent
            note=('; 2025-10 CPS not collected per BLS: '
                  'https://www.bls.gov/cps/methods/2025-federal-government-shutdown-impact-cps.htm') if official_gap else ''
            raise ValueError('Sahm missing recent monthly observations: '+','.join(absent)+note)
        x=x.reindex(expected)
        if x.isna().any(): raise ValueError('Sahm has null monthly observations')
        means=x.rolling(3).mean().dropna()
        value=float(means.iloc[-1]-means.tail(13).min())
        return row('m18',value,x.index[-1].to_timestamp().date().isoformat(),
                   getattr(f,'fredsources',{}).get('UNRATE',('BLS','https://api.bls.gov'))[1],
                   'Sahm computed from 3-month unemployment average versus minimum over preceding 12 months')
    except Exception as exc:
        # A confirmed missing survey month is not a network failure. Never
        # infer the missing U3 value or waste a FRED request on this condition.
        if isinstance(exc, ValueError) and '2025-10 CPS not collected per BLS' in str(exc):
            raise ValueError('Sahm not calculable from official U3 history: '+str(exc)) from exc
        print('SAHM_FALLBACK',type(exc).__name__,str(exc)[:450],flush=True)
        try:
            return latest(f,'m18','SAHMCURRENT')
        except Exception as fallback_error:
            raise RuntimeError('Sahm U3 calculation failed: '+str(exc)[:240]+' | SAHMCURRENT fallback failed: '+str(fallback_error)[:240]) from fallback_error

def nfp(f):
    s=f.fred('PAYEMS')
    recent=s.tail(4)
    if len(recent)!=4 or any((recent.index[i].to_period('M')-recent.index[i-1].to_period('M')).n!=1 for i in range(1,4)):
        raise ValueError('PAYEMS 最近四個月不連續，拒絕錯算月增')
    changes=recent.diff().dropna()
    return row('m20',changes.tail(3).mean(),str(s.index[-1].date()),getattr(f,'fredsources',{}).get('PAYEMS',('FRED',SOURCES['m20'][0]))[1],
               'BLS/FRED 非農就業存量，近3個月月增平均，單位千人',detail='注意歷史值可能修訂')

def netliq(f):
    # Units: WALCL, WDTGAL millions USD; RRPONTSYD billions USD.
    fed=f.fred('WALCL')/1000.0
    tga=f.fred('WDTGAL')/1000.0
    rrp=f.fred('RRPONTSYD')
    df=pd.concat([fed.rename('fed'),tga.rename('tga'),rrp.rename('rrp')],axis=1,join='inner').dropna()
    # same observation Wednesday and exactly 91 days (13 weeks) prior
    df=df[df.index.dayofweek==2]
    if df.empty: raise ValueError('缺少同日週三 TGA/Fed/RRP')
    end=df.index[-1];begin=end-pd.Timedelta(weeks=13)
    if begin not in df.index: raise ValueError(f'缺少 13 週前同日值: {begin.date()}')
    now=df.loc[end];before=df.loc[begin]
    d=(now-before);ans=d['fed']-d['tga']-d['rrp']
    detail=(f"開始={begin.date()}, 結束={end.date()}, 單位十億美元; "
            f"Fed Δ={d['fed']:.6f}, TGA Δ={d['tga']:.6f}, RRP Δ={d['rrp']:.6f}; "
            f"淨流動性 Δ={ans:.6f}")
    return row('m14',ans,str(end.date()),' | '.join(SOURCES['m14']),
               'FRED 三數列同週三觀測；WALCL/WDTGAL 百萬美元÷1000，RRP 十億美元',detail=detail)

def cnn(f):
    # Unofficial endpoint: keep timestamp validation and reject absence of asof.
    url='https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
    r=f.s.get(url,timeout=f.timeout,headers={'Referer':'https://edition.cnn.com/'})
    r.raise_for_status(); data=r.json()
    current=data.get('fear_and_greed',{})
    score=current.get('score');stamp=current.get('timestamp')
    if score is None or not stamp: raise ValueError('CNN API 缺 score 或 timestamp')
    date=pd.to_datetime(stamp,utc=True).date().isoformat()
    return row('s04',float(score),date,url,'CNN 非官方可讀 JSON（可能變動）',detail='來源為 CNN 非公開保證 API')

def yahoo_price(f,k,ticker):
    v,date=f.yahoo(ticker)
    detail=('CL=F 是 Yahoo WTI 近月期貨連續代號，非 WTI 現貨；換月與實際合約月份須另行核對'
            if k=='m10' else 'Yahoo 指數或債券波動資料；日期為報價日；標的口徑須另行核對')
    return row(k,v,date,SOURCES[k][0],f'yfinance Yahoo Finance {ticker} 日K Close',detail=detail)

def validate_manual(k,v):
    if not isinstance(v,dict): raise ValueError('覆寫資料必須為物件')
    for field in ('value','observation_date','source_url','method'):
        if field not in v or v[field] in ('',None): raise ValueError('缺必要欄位 '+field)
    d=dt.date.fromisoformat(v['observation_date'])
    if d>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date(): raise ValueError('資料日期在未來')
    if not str(v['source_url']).startswith('https://'): raise ValueError('來源須有 https URL')
    value=float(v['value'])
    expected_unit=UNITS.get(k,'')
    if expected_unit and v.get('unit')!=expected_unit:
        raise ValueError(f'{k} 單位必須為 {expected_unit}，收到 {v.get("unit")}')
    if not math.isfinite(value):raise ValueError('數值不可無限大或NaN')
    if k in ('m07','s03') and value<0:raise ValueError('VIX 不可為負')
    if k in ('m03_qqq','m03_spy','m03_vt') and value<=0:raise ValueError('本益比必須為正數；虧損/無意義時須標示缺值')
    if k in ('m04','m15') and not 0<=value<=100:raise ValueError('PMI 必須介於0與100')
    if k in ('s04','s05') and not 0<=value<=100:raise ValueError('指數/廣度必須介於0與100')
    if k=='m06': raise ValueError('m06 is derived from five V70-3-27 inputs; do not enter Fed rate-change codes')
    if k=='m14' and v.get('unit')!='USD bn': raise ValueError('m14 必須填 USD bn，不得用億美元')
    if k=='m10' and not v.get('detail'):
        raise ValueError('m10 必須註明現貨/近月期貨及合約月份等價格口徑')
    return row(k,value,v['observation_date'],v['source_url'],
               '人工查證輸入：'+v['method'],detail=v.get('detail',''))

def freshen(r,today):
    if r['status'] not in ('OK','USABLE'):return r
    if r['observation_date'] is None:return r
    age=(today-dt.date.fromisoformat(r['observation_date'])).days
    # Frequency-aware staleness: monthly releases have longer valid windows.
    monthly={'m04','m05','m15','m16','m18','m19','m20'}
    # Core CPI is a release-based monthly series. The observation date labels
    # the measured month (usually day 1), NOT the BLS publication date.
    # A successful live official time-series retrieval is the freshness evidence:
    # do not expire its latest available observation by an arbitrary day count.
    # Historical cache fallback remains STALE upstream in run().
    if r['id']=='m16':
        # August's published annual growth must refresh after the next release.
        if r['observation_date']=='2026-08-01' and today > dt.date(2026,10,22):
            r['status']='STALE'; r['detail']+='; 2026-10-22 release deadline passed'
        elif age<0 or age>90:
            r['status']='STALE'; r['detail']+='; LEI monthly observation outside 90-day window'
        return r
    if r['id']=='m05':
        if age<0:
            r['status']='MISSING';r['error']='觀測日期在未來，拒絕使用';r['value']=None
        return r
    limit=65 if r['id'] in monthly else 12
    if age<0:
        r['status']='MISSING';r['error']='觀測日期在未來，拒絕使用';r['value']=None
    elif age>limit:
        r['status']='STALE';r['detail']+=(f'; 距今 {age} 天 > {limit} 天')
    return r

# Legacy research-only helper. The active run() never calls this old rate-change method;
# V70-3-27 m06 is derived from five separately sourced inputs by the 10:00 Task.
def fetch_m06_from_authorized_cme():
    """FRED + CME futures data via independently authorized data channel.
    Fail closed when access/use rights are not configured or data is unavailable.
    """
    if os.getenv('CME_DATA_AUTOMATION_AUTHORIZED','').lower()!='true':
        raise ValueError('CME automated-data authorization not confirmed; m06 cannot be promoted')
    from cme_fedwatch import get_probabilities
    import importlib.util
    module_file=Path(__file__).resolve().parents[2]/'scripts'/'probe_m06_fedwatch_free.py'
    if not module_file.exists():
        raise FileNotFoundError('m06 engine not present in repository; missing vetted calculator')
    spec=importlib.util.spec_from_file_location('livingwater_m06',module_file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.calculate(get_probabilities(),dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date())
    if result['status']!='CANDIDATE_NEEDS_REVIEW':
        raise ValueError('Unverified m06 response')
    value=result['m06_expected_rate_change_quarters']
    return row('m06',value,result['as_of_settlement'],
        'https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html',
        'CME authorized futures settlement/FRED weighted FOMC probability calculator',
        detail='Meeting '+result['meeting_date']+'; current midpoint '+str(result['current_target_mid_pct'])+
            '; expected midpoint '+str(result['expected_target_mid_pct'])+
            '; permission gate enabled; source parity remains independently reviewable')

def fetch_pe_portfolio_visualizer(ticker):
    """Portfolio Visualizer first; keep a numeric candidate and its provenance.
    HTTP retrieval time is NOT asserted to be holdings P/E valuation date.
    """
    import re
    from html import unescape
    if ticker not in ('QQQ','SPY','VT'): raise ValueError('Unapproved ticker')
    url='https://www.portfoliovisualizer.com/fund-performance?s=y&symbol='+ticker
    response=requests.get(url,timeout=(7,17),headers={'User-Agent':'Mozilla/5.0'})
    if response.status_code==429: raise ValueError('Portfolio Visualizer HTTP 429; stopped')
    response.raise_for_status()
    if len(response.content)>4_000_000: raise ValueError('Oversize page')
    text=unescape(re.sub(r'<[^>]*>',' ',response.text))
    text=re.sub(r'\\s+',' ',text)
    # Verify the selected primary fund; SPY/QQQ/VT as benchmark is insufficient.
    if not re.search(r'(?i)Fund Information.{0,2500}\\b'+ticker+r'\\b',text):
        raise ValueError('Portfolio Visualizer primary fund identity unverified')
    matches=re.findall(r'(?i)Price\\s*/\\s*Earnings\\s*\\(\\s*TTM\\s*\\)\\s*([0-9]+(?:\\.[0-9]+)?)',text)
    if len(matches)!=1: raise ValueError('P/E (TTM) field ambiguous or unavailable')
    pe=float(matches[0])
    if not 1<pe<200: raise ValueError('P/E out of bounds')
    retrieved=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    return row('m03_'+ticker.lower(),pe,retrieved,url,
               'Portfolio Visualizer Fund Information Price/Earnings (TTM)',
               status='UNVERIFIED',
               detail='Date is retrieval date, NOT issuer valuation as-of; primary fund verified')

LEI_PNC_ROOT='https://www.pnc.com/content/dam/pnc-com/pdf/aboutpnc/EconomicReports/EconomicUpdates/2026/'
LEI_PUBLISHED_HISTORY=[
    ('2026-06-01',-1.4,'2026-07-20','PNC_Economics_Research_Leading_Economic_Index_20_July_2026.pdf'),
    ('2026-07-01',-1.1,'2026-08-20','PNC_Economics_Research_LEI_20_August_2026.pdf'),
    ('2026-08-01',-0.7,'2026-09-18','PNC_Economics_Research_CB_LEI_September_182026.pdf'),
]

def parse_lei_pnc(text, source):
    """Read explicitly stated annual growth; never derive it from mixed index vintages."""
    text=re.sub(r'\s+',' ',text).replace('−','-').replace('–','-')
    release=re.search(r'\b(\d{1,2} [A-Z][a-z]+ 20\d{2})\b',text)
    observed=re.search(r'\(LEI\)\s+(?:slipped|slid|rose|fell|increased|decreased|was unchanged)\b.{0,100}?\bin ([A-Z][a-z]+)\b',text)
    growth=re.search(r'\byear(?:[- ]earlier| ago) growth rate\b.{0,80}?\bto\s+([+-]?\d+(?:\.\d+)?)\s*%',text,re.I)
    if not release or not observed or not growth:
        missing=[name for name,match in [('observation month',observed),('annual growth',growth),('release date',release)] if not match]
        raise ValueError('PNC LEI PDF lacks explicit '+', '.join(missing))
    published=dt.datetime.strptime(release.group(1),'%d %B %Y').date()
    month=dt.datetime.strptime(observed.group(1),'%B').month
    year=published.year-(month>published.month)
    observation=dt.date(year,month,1)
    value=float(growth.group(1))
    if observation>published or not -50<=value<=50:
        raise ValueError('PNC LEI date or annual growth invalid')
    return {'observation_date':observation.isoformat(),'value':value,'unit':'%',
            'source_url':source,'publication_date':published.isoformat(),'status':'OK',
            'method':'Read explicitly stated LEI year-over-year growth from PNC research PDF',
            'detail':'As-published monthly YoY; monthly reports have different release vintages, not a same-vintage historical series',
            'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat()}

def lei_verified_history(f, cache_path=None):
    """Existing m16 producer also carries three-month auxiliary history (no extra indicator)."""
    history={d:{'observation_date':d,'value':v,'unit':'%','source_url':LEI_PNC_ROOT+name,
                'publication_date':published,'status':'OK',
                'method':'Work-verified explicitly stated LEI YoY; retained published reference',
                'detail':'Verified 2026-10-15; as-published YoY, not mixed-vintage index division or daily retrieval'}
             for d,v,published,name in LEI_PUBLISHED_HISTORY}
    if cache_path and Path(cache_path).exists():
        for r in json.loads(Path(cache_path).read_text(encoding='utf-8')).get('lei_history',[]):
            if (isinstance(r,dict) and r.get('status')=='OK' and isinstance(r.get('value'),(int,float))
                    and math.isfinite(r['value']) and str(r.get('source_url','')).startswith('https://www.pnc.com/')
                    and re.fullmatch(r'20\d{2}-\d{2}-01',str(r.get('observation_date','')))):
                history[r['observation_date']]=r
    urls=[r['source_url'] for r in history.values()][-3:]
    try:
        listing=f.s.get('https://www.pnc.com/en/about-pnc/media/economic-reports.html',timeout=(5,f.timeout))
        listing.raise_for_status()
        from urllib.parse import urljoin
        links=re.findall(r'href=["\']([^"\']+\.pdf)["\']',listing.text,re.I)
        urls += [urljoin('https://www.pnc.com',u) for u in links
                 if re.search(r'(?:[_-]LEI[_-]|Leading[_-]Economic[_-]Index)',u,re.I)]
    except Exception as exc:
        print('LEI_DISCOVERY_FAILED',str(exc)[:180],flush=True)
    for url in list(dict.fromkeys(urls))[-6:]:
        try:
            from io import BytesIO
            from pypdf import PdfReader
            response=f.s.get(url,timeout=(5,f.timeout));response.raise_for_status()
            if not response.content.startswith(b'%PDF'):
                raise ValueError('LEI source is not PDF')
            record=parse_lei_pnc(PdfReader(BytesIO(response.content)).pages[0].extract_text(),url)
            if record['observation_date']>dt.datetime.now(dt.timezone.utc).date().isoformat():
                raise ValueError('Future LEI observation rejected')
            previous=history.get(record['observation_date'])
            if not previous or record['publication_date']>=previous['publication_date']:
                history[record['observation_date']]=record
            print('LEI_PNC_VERIFIED',record['observation_date'],record['value'],flush=True)
        except Exception as exc:
            print('LEI_SOURCE_FAILED',url,str(exc)[:180],flush=True)
    f.lei_history=sorted(history.values(),key=lambda r:r['observation_date'])[-3:]
    latest=f.lei_history[-1]
    return row('m16',latest['value'],latest['observation_date'],latest['source_url'],latest['method'],
               detail=latest['detail']+'; supersedes mixed-vintage 99.5/98.5 baseline')

def run(outdir,overrides_path=None,cache_path=None):
    config=load_source_config()
    f=Fetcher()
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    jobs={
      'm07':lambda:latest(f,'m07','VIXCLS'),
      'm01':lambda:latest(f,'m01','T10Y2Y'),
      'm08':lambda:latest(f,'m08','DFII10'),
      'm02':lambda:latest(f,'m02','BAMLH0A0HYM2'),
      'm13':lambda:breakeven_5y(f),
      'm17':lambda:month_delta(f),
      'm14':lambda:netliq(f),
      'm18':lambda:sahm_from_unrate(f),
      'm19':lambda:latest(f,'m19','UNRATE'),
      'm20':lambda:nfp(f),
      'm05':lambda:core_cpi(f),
      'm09':lambda:yahoo_price(f,'m09','DX-Y.NYB'),
      'm10':lambda:yahoo_price(f,'m10','CL=F'),
      'm12':lambda:yahoo_price(f,'m12','^MOVE'),
      's04':lambda:cnn(f),
      'm16':lambda:lei_verified_history(f,cache_path),
    }
    # Must not invent an HTTP scraper for a dynamic or terms-protected source.
    reasons={
      'm04':'ISM 官方製造業發布頁需依版本核對，不能無來源抓任意網頁數字',
      'm15':'ISM 官方服務業發布頁需依版本核對，不能無來源抓任意網頁數字',
      'm16':'Conference Board LEI YoY 需要同一次發布修訂口徑的上年同月值',
    }
    results={}
    for k in LABELS:
        started_at=dt.datetime.now(dt.timezone.utc).isoformat()
        f.job_series=set()
        try:
            # Reserve final two minutes of the 20-minute job for validation and publishing.
            if time.monotonic()-D009_RUN_STARTED>=D009_FETCH_DEADLINE_SECONDS:
                raise TimeoutError('D009 18-minute fetch deadline reached; no new provider requests')
            if k=='s03':
                orig=results.get('m07')
                if not orig or orig['value'] is None: raise ValueError('m07 尚無有效值')
                r=row('s03',orig['value'],orig['observation_date'],orig['source_url'],'同一 VIXCLS 數列，複用 m07')
            elif k in jobs:r=jobs[k]()
            else:r=row(k,src=(SOURCES.get(k) or [''])[0],method='須人工核實或授權 API',error=reasons.get(k,'無穩定來源'))
        except Exception as ex:
            r=row(k,src=(SOURCES.get(k) or [''])[0],method='抓取失敗',error=str(ex)[:220])
        attempts={series:list(f.fredattempts.get(series,[])) for series in sorted(f.job_series)}
        r.update(attempted_at=started_at, attempt_result='SUCCESS' if r.get('value') is not None else 'FAILED',
                 source_attempts=attempts, cache_used=False, cache_source=None,
                 last_verified_at=None, source_evidence=None)
        # Only record successful provider evidence, never infer it from output time.
        successes=[a for entries in attempts.values() for a in entries if a.get('result')=='OK']
        if r.get('value') is not None and attempts and all(any(a.get('result')=='OK' for a in entries) for entries in attempts.values()):
            r['last_verified_at']=min(a['verified_at'] for a in successes)
            r['source_evidence']={'series':attempts}
        results[k]=r
        print(f"{k:9s} {r['status']:7s} {str(r['value']):>12s} {r['observation_date'] or '---'}",flush=True)
    # Optional dated and source-backed records; never overwrite the results automatically via HTML defaults.
    if overrides_path:
        manual=json.loads(Path(overrides_path).read_text(encoding='utf-8'))
        if not isinstance(manual,dict):raise ValueError('overrides 必須為 JSON 物件')
        for k,v in manual.items():
            if k not in LABELS:raise ValueError('未知 id: '+k)
            if k=='s03': raise ValueError('s03 是 m07 的複用欄位，請只覆寫 m07')
            verified=validate_manual(k,v)
            original=results[k]
            if original['status']=='OK' and verified['observation_date']<original['observation_date']:
                print('SKIP 舊覆寫:',k)
            else:
                for field in ('attempted_at','attempt_result','source_attempts'):
                    verified[field]=original.get(field)
                verified['retrieval_error']=original.get('error','')
                verified['cache_used']=False
                verified['last_verified_at']=v.get('last_verified_at')
                verified['source_evidence']=v.get('source_evidence')
                results[k]=verified
                if k=='m07': results['s03']=row('s03',verified['value'],verified['observation_date'],verified['source_url'],'同步複用 m07 人工驗證值')
    # Cached source-backed values are historical fallback, never silently treated as current.
    if cache_path and Path(cache_path).exists():
        try:
            old=json.loads(Path(cache_path).read_text(encoding='utf-8'))
            for k in LABELS:
                if k=='s03':
                    continue  # s03 僅由 m07 複製，不得從快取獨立還原
                prior=old.get('items',{}).get(k,{})
                if results[k]['value'] is None and prior.get('value') is not None:
                    try:
                        # 快取只讀入先前 OK/STALE 且有來源的紀錄；重新驗日期、數值、單位。
                        if prior.get('status') not in ('OK','USABLE','STALE'):
                            continue
                        checked=validate_manual(k, {'value':prior['value'],
                            'observation_date':prior['observation_date'],
                            'source_url':prior['source_url'],
                            'method':'既有快取再驗證',
                            'unit':prior.get('unit',''),
                            'detail':prior.get('detail','')})
                        # A still-current published monthly observation is usable
                        # as a retained reference, never a new live-source retrieval.
                        checked['status']='USABLE' if k in ('m04','m15','m18') else 'STALE'
                        checked['detail']='歷史快取備援；本次未重新取得來源；僅在觀測日期有效期限內保留使用'
                        failed=results[k]
                        checked.update(error=failed.get('error',''), retrieval_error=failed.get('error',''),
                            attempted_at=failed.get('attempted_at'), attempt_result=failed.get('attempt_result','FAILED'),
                            source_attempts=failed.get('source_attempts',{}), cache_used=True,
                            cache_source={'file':Path(cache_path).name,'sha256':hashlib.sha256(Path(cache_path).read_bytes()).hexdigest(),
                                          'generated_at':old.get('generated_at'),'observation_date':prior.get('observation_date')},
                            last_verified_at=prior.get('last_verified_at'), source_evidence=prior.get('source_evidence'))
                        results[k]=checked
                    except (ValueError,TypeError,KeyError,OverflowError) as e:
                        print('拒絕不合格快取',k,str(e),file=sys.stderr)
        except (OSError,ValueError,TypeError) as e:print('忽略損壞快取',e,file=sys.stderr)
    for k in results: freshen(results[k],today)
    # Preserve actual source observation dates and mark cached/old observations.
    for k,r in results.items():
        if k=='s03' or not r.get('observation_date'): continue
        age=(today-dt.date.fromisoformat(r['observation_date'])).days
        limit=config['indicators'][k]['max_age_days']
        if age>limit and r['status'] in ('OK','USABLE'):
            r['status']='STALE'
            r['detail']+=(f'; D009 source config age {age} > {limit} days')
    # m07 和 s03 必須一致，不允許歷史快取、人工覆寫造成互相矛盾。
    a=results['m07']
    if a['value'] is not None:
        results['s03']=row('s03',a['value'],a['observation_date'],a['source_url'],'與 m07 同步',status=a['status'],detail='同一 VIX 數列')
    else:
        results['s03']=row('s03',src=SOURCES['m07'][0],method='與 m07 同步',error='m07 沒有可信值；禁止使用獨立 s03 備援')
    for field in ('attempted_at','attempt_result','source_attempts','cache_used','cache_source','last_verified_at','source_evidence','retrieval_error'):
        if field in a: results['s03'][field]=a[field]
    for record in results.values():
        record.setdefault('retrieval_error',record.get('error',''))
    summary={s:sum(x['status']==s for x in results.values()) for s in ('OK','USABLE','STALE','MISSING')}
    independent_ids=[key for key in LABELS if key!='s03']
    independent_summary={status:sum(results[key]['status']==status for key in independent_ids)
                         for status in ('OK','USABLE','STALE','MISSING')}
    report={'schema':'V70.3/18-macro-collector-v1','generated_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
            'note':'僅供研究與人工審核，非V70_live自動更新payload；未驗證項目不得進入風控計算',
            'summary':summary,'independent_indicators':{'total':len(independent_ids), 'excluded_duplicate':'s03 (same VIX as m07)', 'summary':independent_summary},'items':results,
            'lei_history':getattr(f,'lei_history',[])}
    out=Path(outdir);out.mkdir(exist_ok=True,parents=True)
    atomic_write_text(out/'18_macro_verification.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with (out/'18_macro_verification.csv').open('w',newline='',encoding='utf-8-sig') as w:
        fieldnames=list(dict.fromkeys(field for record in results.values() for field in record))
        wr=csv.DictWriter(w,fieldnames=fieldnames)
        wr.writeheader()
        for record in results.values():
            wr.writerow({key:json.dumps(value,ensure_ascii=False,sort_keys=True) if isinstance(value,(dict,list)) else value
                         for key,value in record.items()})
    with (out/'18_macro_report.md').open('w',encoding='utf-8') as w:
        w.write('# 18 項獨立總經指標查核報告（19欄含s03重複VIX）\n\n')
        w.write(f"產出時間：{report['generated_at']}；OK={summary['OK']}／USABLE={summary['USABLE']}／STALE={summary['STALE']}／MISSING={summary['MISSING']}\n\n")
        w.write('| ID | 指標 | 值 | 真正觀測日 | 狀態 | 來源或卡點 |\n|---|---|---:|---|---|---|\n')
        for v in results.values():
            val=('-' if v['value'] is None else f"{v['value']:g} {v['unit']}")
            desc='來源: '+(v['source_url'] or '無')+'；方式: '+v['method']+'；問題: '+v['error']+'；備註: '+v['detail']+'；取得結果: '+str(v.get('attempt_result'))+'；快取: '+str(v.get('cache_used',False))+'；最後核實: '+str(v.get('last_verified_at'))+'；診斷: '+json.dumps(v.get('source_attempts',{}),ensure_ascii=False)
            desc=desc.replace('|',';').replace('\n',' ') 
            w.write(f"| {v['id']} | {v['label']} | {val} | {v['observation_date'] or '-'} | {v['status']} | {desc} |\n")
        w.write('\n未驗證項目請查看 CSV/JSON 的 error/detail；不得將 MISSING 或 STALE 冒充最新正式值。\n')
    print('完成輸出:',out.resolve(),'獨立指標統計 18 項:',independent_summary,'交換欄位統計:',summary)
    return report

def fedwatch_expected_codes(distribution, current_mid):
    """Weighted 12-month target-rate midpoint change, in 25bp units.

    distribution: list of {"lower": percent, "upper": percent,
    "probability": fraction from 0 to 1}. Caller must supply a verified
    dated distribution for the last scheduled FOMC within 12 months.
    No futures quotes, inferred dates or made-up probabilities are accepted.
    """
    if not distribution or not math.isfinite(float(current_mid)):
        raise ValueError('Missing verified FedWatch inputs')
    total=0.0
    expectation=0.0
    for item in distribution:
        lo, hi, p=(float(item[k]) for k in ('lower','upper','probability'))
        if not all(math.isfinite(x) for x in (lo,hi,p)):
            raise ValueError('Non-finite probability or interest rate')
        if lo>=hi or hi-lo>0.5 or lo<0 or hi>30 or p<0 or p>1:
            raise ValueError('Invalid target range/probability')
        total+=p
        expectation+=p*(lo+hi)/2
    if abs(total-1.0)>0.001:
        raise ValueError('Probabilities do not sum to 1')
    return (expectation/total-float(current_mid))/0.25


# Legacy helper retained for history only. It is not part of the active 18-item run.
def fetch_m06_cme(f):
    """Use CME's authenticated FedWatch EOD REST API; fail closed without access."""
    from urllib.parse import urlparse
    token=os.environ.get('CME_FEDWATCH_BEARER','').strip()
    if not token:
        raise ValueError('CME_FEDWATCH_BEARER not configured; official CME FedWatch API requires subscription')
    endpoint='https://markets.api.cmegroup.com/fedwatch/v1/forecasts'
    response=f.s.get(endpoint,headers={'Authorization':'Bearer '+token,
                     'Accept':'application/json'},timeout=(5,30))
    response.raise_for_status()
    body=response.json()
    forecasts=body.get('payload')
    if not isinstance(forecasts,list) or not forecasts:
        raise ValueError('CME forecast payload absent')
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    horizon=today+dt.timedelta(days=365)
    eligible=[]
    for entry in forecasts:
        meeting=dt.date.fromisoformat(entry['meetingDt'])
        reported=dt.date.fromisoformat(entry['reportingDt'])
        if today<=meeting<=horizon and 0<=(today-reported).days<=7:
            eligible.append((meeting,reported,entry))
    if not eligible:
        raise ValueError('No timely FOMC forecast for next 12 months')
    meeting,reported,last=max(eligible,key=lambda x:x[0])
    # Actual current TARGET range must be sourced, not assumed from EFFR.
    lower=f.fred('DFEDTARL')
    upper=f.fred('DFEDTARU')
    rates=pd.concat([lower.rename('lower'),upper.rename('upper')],axis=1,join='inner').dropna()
    if rates.empty or (today-rates.index[-1].date()).days>14:
        raise ValueError('Current Fed target range not independently verified')
    cur_lo=float(rates.iloc[-1]['lower'])
    cur_hi=float(rates.iloc[-1]['upper'])
    if cur_lo>=cur_hi: raise ValueError('Invalid official current Fed range')
    ranges=last.get('rateRange')
    if not isinstance(ranges,list): raise ValueError('CME rateRange absent')
    distribution=[{'lower':float(x['lowerRt'])/100,
                   'upper':float(x['upperRt'])/100,
                   'probability':float(x['probability'])} for x in ranges]
    current_mid=(cur_lo+cur_hi)/2
    codes=fedwatch_expected_codes(distribution,current_mid)
    return row('m06',codes,str(reported),
               endpoint,'CME FedWatch EOD: final meeting '+meeting.isoformat()+
               '; probability-weighted target midpoint vs official FRED target midpoint',
               detail='FOMC '+meeting.isoformat()+'; current target '+str(cur_lo)+'-'+str(cur_hi)+'%; units=25bp')

def fetch_mmfi_barchart_history(f):
    """Barchart licensed exact $MMFI daily index history, if credential exists.

    Values come from the original index (not a S&P500 breadth proxy);
    require matching identifier and explicit provider trading date.
    """
    import requests
    key=os.environ.get('BARCHART_ONDEMAND_API_KEY','').strip()
    if not key:
        raise ValueError('BARCHART_ONDEMAND_API_KEY absent; $MMFI history requires approved Barchart access')
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    url='https://ondemand.websol.barchart.com/getHistory.json'
    resp=f.s.get(url,params={'apikey':key,'symbol':'$MMFI','type':'daily',
                              'startDate':(now-dt.timedelta(days=15)).strftime('%Y%m%d'),
                              'endDate':now.strftime('%Y%m%d')},
                 timeout=(5,f.timeout))
    resp.raise_for_status()
    obj=resp.json()
    if obj.get('status',{}).get('code') not in (None,200):
        raise ValueError('Barchart history response non-success')
    readings=[]
    for entry in obj.get('results') or []:
        if str(entry.get('symbol','')).upper()!='$MMFI':
            continue
        stamp=entry.get('tradingDay') or entry.get('timestamp')
        if not stamp: continue
        date=dt.date.fromisoformat(str(stamp)[:10])
        value=float(entry['close'])
        if 0<=value<=100 and math.isfinite(value) and date<=now:
            readings.append((date,value))
    if not readings:
        raise ValueError('No dated $MMFI observation in Barchart response')
    observed,value=max(readings,key=lambda pair:pair[0])
    return row('s05',value,observed.isoformat(),
               'https://www.barchart.com/stocks/quotes/%24MMFI/price-history',
               'Barchart OnDemand original $MMFI daily closing breadth percent',
               detail='Official $MMFI instrument, tradingDay validated')


def fetch_mmfi_market_breadth(f):
    """Read actual daily MMFI index close from Yahoo Chart if published.

    Require dated observation AND instrument identity explicitly identifying
    the NYSE percent-above-50-day breadth index; no proxy or arbitrary quote.
    """
    import requests
    import datetime as datetime_module
    failures=[]
    try:
        return fetch_mmfi_barchart_history(f)
    except Exception as exc:
        failures.append('BARCHART: '+str(exc)[:160])
    for symbol in ('$MMFI','^MMFI','MMFI'):
        try:
            url='https://query1.finance.yahoo.com/v8/finance/chart/'+requests.utils.quote(symbol,safe='')
            resp=f.s.get(url,params={'range':'10d','interval':'1d'},timeout=(5,f.timeout),
                         headers={'User-Agent':'Mozilla/5.0'})
            resp.raise_for_status()
            data=resp.json()['chart']
            if data.get('error') or not data.get('result'):
                raise ValueError('Yahoo Chart has no result')
            entry=data['result'][0];meta=entry.get('meta',{})
            identity=' '.join(str(meta.get(k,'')) for k in ('shortName','longName','symbol'))
            norm=identity.lower()
            # A bare matching ticker is not proof of index identity.
            if not (('nyse' in norm or 'new york stock exchange' in norm)
                    and ('50' in norm or 'fifty' in norm)
                    and ('percent' in norm or 'percentage' in norm or '%' in norm)):
                raise ValueError('unverified instrument identity: '+identity[:100])
            timestamps=entry.get('timestamp') or []
            values=entry['indicators']['quote'][0]['close']
            dated=[(datetime_module.datetime.fromtimestamp(int(t),datetime_module.timezone.utc).date(),
                    float(v)) for t,v in zip(timestamps,values)
                   if v is not None and math.isfinite(float(v))]
            if not dated: raise ValueError('no dated close')
            observed,value=dated[-1]
            if value<0 or value>100: raise ValueError('MMFI not in percent range')
            return row('s05',value,observed.isoformat(),
                       'https://finance.yahoo.com/quote/'+requests.utils.quote(symbol,safe='')+'/',
                       'Yahoo Chart NYSE percentage of stocks above 50-day moving average',
                       detail='Provider confirmed instrument identity: '+identity[:140])
        except Exception as exc:
            failures.append(symbol+': '+str(exc)[:110])
    raise ValueError('MMFI live source unavailable: '+' | '.join(failures))


def probe_spy_issuer_index_pe(f):
    """Fetch dated S&P 500 *index* P/E from SPY issuer site for comparison.

    Do not promote this index-level statistic to SPY holdings TTM P/E:
    the provider does not explicitly establish that equivalence.
    """
    import re
    from bs4 import BeautifulSoup
    url='https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy'
    resp=f.s.get(url,timeout=(5,f.timeout),
                 headers={'User-Agent':'Mozilla/5.0'})
    resp.raise_for_status()
    text=' '.join(BeautifulSoup(resp.text,'html.parser').stripped_strings)
    m=re.search(r'Index Characteristics as of\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})',text,re.I)
    if not m: raise ValueError('State Street dated Index Characteristics absent')
    date=dt.datetime.strptime(m.group(1),'%b %d %Y').date()
    segment=text[m.end():m.end()+1800]
    pe=re.search(r'Price/Earnings(?!\s+Ratio\s+FY1)\s+(\d+(?:\.\d+)?)',segment,re.I)
    if not pe: raise ValueError('State Street index PE field absent')
    value=float(pe.group(1))
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    if date>now or date<(now-dt.timedelta(days=75)) or not 1<value<200:
        raise ValueError('SPY issuer index P/E date/value outside bounds')
    return {'candidate_index_pe':value,'issuer_index_asof':date.isoformat(),
            'source':url,'method':'SSGA Index Characteristics Price/Earnings',
            'validation':'INDEX_PROXY_ONLY: not approved SPY holdings TTM PE'}


def fetch_etf_valuation_candidate(f, ticker, key):
    """Try live yfinance ETF TTM PE and require provider-stamped valuation date.

    A quote retrieval timestamp, last trade time, or today's clock time is
    NOT the underlying holdings P/E valuation as-of date.
    """
    import yfinance as yf
    info=yf.Ticker(ticker).get_info()
    if not isinstance(info,dict):
        raise ValueError('Yahoo ETF metadata unavailable')
    pe=info.get('trailingPE')
    if pe is not None:
        if not isinstance(getattr(f,'etf_candidates',None),dict): f.etf_candidates={}
        f.etf_candidates[ticker]={
            'candidate_trailing_pe':pe,
            'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'source':'https://finance.yahoo.com/quote/'+ticker+'/',
            'fund_holdings_pe_asof':info.get('trailingPEAsOfDate'),
            'methodology':info.get('trailingPEMethodology'),
            'validation':'UNVERIFIED: retrieval time is not valuation date'}
    if pe is None or not math.isfinite(float(pe)) or float(pe)<=0:
        raise ValueError('Yahoo trailingPE absent for '+ticker)
    # ETF P/E must have an explicit dated holdings valuation and a compatible
    # provider methodology; Yahoo quote time is insufficient evidence.
    date=info.get('trailingPEAsOfDate')
    methodology=info.get('trailingPEMethodology')
    if not date or methodology!='holdings_weighted_ttm':
        raise ValueError(ticker+' Yahoo trailingPE candidate obtained but ETF valuation date/methodology unverified')
    observed=dt.date.fromisoformat(str(date))
    if observed>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
        raise ValueError('ETF valuation date in future')
    return row(key,float(pe),observed.isoformat(),'https://finance.yahoo.com/quote/'+ticker+'/',
               'Yahoo fund holdings weighted trailing 12 months P/E, explicitly dated')


def selftest():
    assert len(load_source_config()['indicators'])==18
    assert len(LABELS)==19
    assert len([k for k in LABELS if k!='s03'])==18
    assert all(k not in LABELS for k in ["s05"])
    r=parse_lei_pnc('18 September 2026 The Conference Board Leading Economic Index (LEI) slipped 0.1% in August to 99.5. The year earlier growth rate improved to -0.7%.',LEI_PNC_ROOT+LEI_PUBLISHED_HISTORY[-1][3])
    assert r['status']=='OK' and r['value']==-0.7
    assert r['observation_date']=='2026-08-01'
    r['id']='m16'
    assert freshen(dict(r),dt.date(2026,10,14))['status']=='OK'
    assert freshen(dict(r),dt.date(2026,10,23))['status']=='STALE'
    try:
        parse_lei_pnc('18 September 2026 (LEI) slipped 0.1% in August. Six-month growth rate to -0.7%.',LEI_PNC_ROOT)
        raise AssertionError('Must not mistake six-month growth for annual growth')
    except ValueError:
        pass
    # Exact excerpts from the 22 October report: monthly level and six-month
    # growth must not displace its explicitly stated annual growth.
    october='22 October 2026 The Conference Board Leading Economic Index (LEI) was unchanged in September at 99.6 (2016=100). The LEI’s six-month growth rate improved to 0.6% between March and September. The year earlier growth rate improved for the ninth straight month to -0.5%.'
    r=parse_lei_pnc(october,LEI_PNC_ROOT+'PNC_Economics_Research_LEI_22_October_2026.pdf')
    assert (r['publication_date'],r['observation_date'],r['value'])==('2026-10-22','2026-09-01',-0.5)
    try:
        parse_lei_pnc(october.split('The year earlier')[0],LEI_PNC_ROOT)
        raise AssertionError('Monthly level and six-month growth are not YoY')
    except ValueError:
        pass
    assert all(k not in LABELS for k in ('m06','m03_qqq','m03_spy','m03_vt'))
    print('SELF-TEST PASS: 18 core indicators + s03 duplicate; eight V70-3-27 supplement inputs delegated')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='V70.3 18 項自動抓取與已核定LEI基準')
    ap.add_argument('--out',default='18_macro_output')
    ap.add_argument('--overrides',help='人工已驗證 JSON，須含 value/observation_date/source_url/method')
    ap.add_argument('--cache',help='先前同程式的 18_macro_verification.json，作為註明 STALE 的備援')
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:selftest()
    else:
        default_overrides=Path(__file__).resolve().parents[2]/'data'/'verified_overrides.json'
        overrides=a.overrides or (str(default_overrides) if default_overrides.is_file() else None)
        run(a.out,overrides,a.cache)


