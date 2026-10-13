#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第一部分：Python 自動蒐集 16 欄，另 8 欄保留 MISSING 交由 ChatGPT 查證。

保留24欄完整輸出契約，避免下游JSON漏欄；不代表24欄已全部自動取得。
此檔獨立、唯讀，不修改既有程式或 GitHub。

安裝: pip install requests pandas yfinance
執行: python '總經爬蟲16項.py'
可選: python '總經爬蟲16項.py' --overrides verified_overrides.json --out results
測試: python '總經爬蟲16項.py' --self-test

資料紀律:
* 對於只有動態網頁、無穩定免費機器介面的資料，輸出 MISSING，絕不填入 HTML 預設值。
* overrides 只能收錄已人工查證的 values，需有來源 URL、實際觀測日期和明確口徑。
* 快取只保留上次取得的有證據資料；舊資料會顯示 STALE，而非冒充今日數字。
* m06 的值是未來約 12 個月預期利率變化「碼」(0.25pp/碼)，不是利率水準。
* m14 是 13 周變化，單位為 10 億美元 ($bn)。
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
from pathlib import Path

try:
    import requests
    import pandas as pd
except ImportError as e:
    raise SystemExit("缺套件，請執行：pip install requests pandas yfinance") from e

FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id='
LABELS = {
 'm07':'VIX','m01':'10Y−2Y 殖利率曲線','m06':'未來12個月 Fed 升降息預期（碼）',
 'm08':'10Y 實質殖利率','m03_qqq':'QQQ TTM P/E','m03_spy':'SPY TTM P/E',
 'm03_vt':'VT TTM P/E','m02':'HY OAS','m04':'ISM 製造業 PMI',
 'm05':'Core CPI YoY','m09':'DXY','m10':'WTI','m12':'MOVE',
 'm13':'5Y Breakeven','m17':'5Y Breakeven 近1月變化（pp）','m14':'淨流動性 13週變化（$bn）',
 'm15':'ISM 服務業 PMI','m16':'LEI YoY','m18':'Sahm Rule','m19':'U3 失業率',
 'm20':'3個月平均非農新增就業（千人）','s03':'VIX 短期','s04':'CNN Fear & Greed','s05':'MMFI 廣度'
}
BOUNDS = {'m07':(0,150),'s03':(0,150),'m01':(-10,15),'m08':(-10,20),
          'm02':(0,60),'m04':(0,100),'m15':(0,100),'m05':(-10,25),
          'm09':(30,250),'m10':(-50,400),'m12':(0,400),'m13':(-10,20),
          'm17':(-10,10),'m18':(-5,15),'m19':(0,40),'s04':(0,100),'s05':(0,100)}
# BOUNDS are broad sanity limits, not economic grading thresholds.
UNITS = {'m01':'%','m06':'碼','m08':'%','m02':'%','m05':'%','m10':'USD/bbl',
         'm13':'%','m17':'pp','m14':'USD bn','m16':'%','m19':'%','m20':'千人','s05':'%'}
SOURCES = {
 'm06':['https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html'],
 'm03_qqq':['https://finance.yahoo.com/quote/QQQ/'],
 'm03_spy':['https://finance.yahoo.com/quote/SPY/'],
 'm03_vt':['https://finance.yahoo.com/quote/VT/'],
 'm04':['https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'],
 'm15':['https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'],
 'm16':['https://www.conference-board.org/topics/us-leading-indicators'],
 's05':['https://www.tradingview.com/symbols/INDEX-MMFI/','https://www.macroaxis.com/index/MMFI.INDX/Percent-Of-Stocks'],
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

class Fetcher:
    def __init__(self, timeout=8):
        self.s=requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        retry=Retry(total=1, connect=1, read=1, backoff_factor=0.3,
                    status_forcelist=[429,500,502,503,504],
                    allowed_methods=frozenset(['GET']), respect_retry_after_header=True)
        adapter=HTTPAdapter(max_retries=retry)
        self.s.mount('https://',adapter)
        self.s.headers.update({'User-Agent':'Mozilla/5.0 (compatible; macro-data-research/1.2)'})
        self.timeout=timeout
        self.fredcache={}
        self.frederrors={}

    def fred(self, series):
        if series in self.fredcache: return self.fredcache[series]
        if series in self.frederrors: raise RuntimeError(self.frederrors[series])
        from io import StringIO
        errors=[]
        providers=[
            ('FRED_CSV', FRED+series),
            ('DBNOMICS_FRED_MIRROR','https://api.db.nomics.world/v22/series/FRED/'+series+'?observations=1')
        ]
        for provider,url in providers:
            try:
                response=self.s.get(url,timeout=(5,self.timeout))
                response.raise_for_status()
                if provider=='FRED_CSV':
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
                self.fredcache[series]=out
                print('FRED_PROVIDER',series,provider,str(out.index[-1].date()),flush=True)
                return out
            except Exception as exc:
                errors.append(provider+': '+type(exc).__name__+': '+str(exc)[:100])
        message='All FRED sources failed for '+series+' | '+' | '.join(errors)
        self.frederrors[series]=message
        raise RuntimeError(message)

    def yahoo(self,ticker,info_key=None):
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

def latest(f, key, name):
    s=f.fred(name);d=s.index[-1].strftime('%Y-%m-%d')
    return row(key,s.iloc[-1],d,'https://fred.stlouisfed.org/series/'+name,'FRED CSV')

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
    return row('m05',val,s.index[-1].strftime('%Y-%m-%d'),SOURCES['m05'][0],
               'FRED CPILFESL 同一數列 YoY','',detail=f'比較基期 {prior_date.date()}')

def month_delta(f):
    s=f.fred('T5YIE'); latest_date=s.index[-1]
    target=latest_date-pd.DateOffset(months=1)
    hist=s.loc[:target]
    if hist.empty: raise ValueError('5YBE 無 1 個月以前資料')
    # Never silently use a very old observation as the one-month baseline.
    if (target-hist.index[-1]).days>7:
        raise ValueError(f'5YBE 近1月基期過舊：目標 {target.date()}，實際 {hist.index[-1].date()}')
    return row('m17',float(s.iloc[-1]-hist.iloc[-1]),str(latest_date.date()),SOURCES['m17'][0],
               '近1個月前最近交易日差值（百分點）',detail=f'起點 {hist.index[-1].date()}')

def nfp(f):
    s=f.fred('PAYEMS')
    recent=s.tail(4)
    if len(recent)!=4 or any((recent.index[i].to_period('M')-recent.index[i-1].to_period('M')).n!=1 for i in range(1,4)):
        raise ValueError('PAYEMS 最近四個月不連續，拒絕錯算月增')
    changes=recent.diff().dropna()
    return row('m20',changes.tail(3).mean(),str(s.index[-1].date()),SOURCES['m20'][0],
               'FRED 非農就業存量，近3個月月增平均，單位千人',detail='注意歷史值可能修訂')

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
    if k=='m06' and v.get('unit')!='碼': raise ValueError('m06 必須填碼，例如 −3 = 預期降息三碼')
    if k=='m14' and v.get('unit')!='USD bn': raise ValueError('m14 必須填 USD bn，不得用億美元')
    if k=='m10' and not v.get('detail'):
        raise ValueError('m10 必須註明現貨/近月期貨及合約月份等價格口徑')
    return row(k,value,v['observation_date'],v['source_url'],
               '人工查證輸入：'+v['method'],detail=v.get('detail',''))

def freshen(r,today):
    if r['status']!='OK':return r
    if r['observation_date'] is None:return r
    age=(today-dt.date.fromisoformat(r['observation_date'])).days
    # Frequency-aware staleness: monthly releases have longer valid windows.
    monthly={'m04','m05','m15','m16','m18','m19','m20'}
    limit=65 if r['id'] in monthly else 12
    if age<0:
        r['status']='MISSING';r['error']='觀測日期在未來，拒絕使用';r['value']=None
    elif age>limit:
        r['status']='STALE';r['detail']+=(f'; 距今 {age} 天 > {limit} 天')
    return r

def run(outdir,overrides_path=None,cache_path=None):
    f=Fetcher()
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    jobs={
      'm07':lambda:latest(f,'m07','VIXCLS'),
      'm01':lambda:latest(f,'m01','T10Y2Y'),
      'm08':lambda:latest(f,'m08','DFII10'),
      'm02':lambda:latest(f,'m02','BAMLH0A0HYM2'),
      'm13':lambda:latest(f,'m13','T5YIE'),
      'm17':lambda:month_delta(f),
      'm14':lambda:netliq(f),
      'm18':lambda:latest(f,'m18','SAHMCURRENT'),
      'm19':lambda:latest(f,'m19','UNRATE'),
      'm20':lambda:nfp(f),
      'm05':lambda:core_cpi(f),
      'm09':lambda:yahoo_price(f,'m09','DX-Y.NYB'),
      'm10':lambda:yahoo_price(f,'m10','CL=F'),
      'm12':lambda:yahoo_price(f,'m12','^MOVE'),
      's04':lambda:cnn(f),
    }
    # Must not invent an HTTP scraper for a dynamic or terms-protected source.
    reasons={
      'm06':'CME/Investing 機率分布未有穩定公開介面；需每個會議利率機率換算12個月預期碼數',
      'm03_qqq':'估值數值可能可讀取，但 Yahoo ETF TTM P/E 快照沒有可靠 observation date/統一口徑',
      'm03_spy':'估值數值可能可讀取，但 Yahoo ETF TTM P/E 快照沒有可靠 observation date/統一口徑',
      'm03_vt':'估值數值可能可讀取，但 Yahoo ETF TTM P/E 快照沒有可靠 observation date/統一口徑',
      'm04':'ISM 官方製造業發布頁需依版本核對，不能無來源抓任意網頁數字',
      'm15':'ISM 官方服務業發布頁需依版本核對，不能無來源抓任意網頁數字',
      'm16':'Conference Board LEI YoY 需要同一次發布修訂口徑的上年同月值',
      's05':'TradingView MMFI 為動態圖，Macroaxis 第三方數值需要日期和同定義證據',
    }
    results={}
    for k in LABELS:
        try:
            if k=='s03':
                orig=results.get('m07')
                if not orig or orig['value'] is None: raise ValueError('m07 尚無有效值')
                r=row('s03',orig['value'],orig['observation_date'],orig['source_url'],'同一 VIXCLS 數列，複用 m07')
            elif k in jobs:r=jobs[k]()
            else:r=row(k,src=(SOURCES.get(k) or [''])[0],method='須人工核實或授權 API',error=reasons.get(k,'無穩定來源'))
        except Exception as ex:
            r=row(k,src=(SOURCES.get(k) or [''])[0],method='抓取失敗',error=str(ex)[:220])
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
                        if prior.get('status') not in ('OK','STALE'):
                            continue
                        checked=validate_manual(k, {'value':prior['value'],
                            'observation_date':prior['observation_date'],
                            'source_url':prior['source_url'],
                            'method':'既有快取再驗證',
                            'unit':prior.get('unit',''),
                            'detail':prior.get('detail','')})
                        checked['status']='STALE'
                        checked['detail']='歷史快取備援；不代表目前已重新查證來源'
                        results[k]=checked
                    except (ValueError,TypeError,KeyError,OverflowError) as e:
                        print('拒絕不合格快取',k,str(e),file=sys.stderr)
        except (OSError,ValueError,TypeError) as e:print('忽略損壞快取',e,file=sys.stderr)
    for k in results: freshen(results[k],today)
    # m07 和 s03 必須一致，不允許歷史快取、人工覆寫造成互相矛盾。
    a=results['m07']
    if a['value'] is not None:
        results['s03']=row('s03',a['value'],a['observation_date'],a['source_url'],'與 m07 同步',status=a['status'],detail='同一 VIX 數列')
    else:
        results['s03']=row('s03',src=SOURCES['m07'][0],method='與 m07 同步',error='m07 沒有可信值；禁止使用獨立 s03 備援')
    summary={s:sum(x['status']==s for x in results.values()) for s in ('OK','STALE','MISSING')}
    report={'schema':'V70.2/24-macro-research-v1','generated_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
            'note':'僅供研究與人工審核，非V70_live自動更新payload；未驗證項目不得進入風控計算',
            'summary':summary,'items':results}
    out=Path(outdir);out.mkdir(exist_ok=True,parents=True)
    (out/'24_macro_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'24_macro_verification.csv').open('w',newline='',encoding='utf-8-sig') as w:
        fieldnames=list(next(iter(results.values())).keys());wr=csv.DictWriter(w,fieldnames=fieldnames)
        wr.writeheader();wr.writerows(results.values())
    with (out/'24_macro_report.md').open('w',encoding='utf-8') as w:
        w.write('# 24 項總經資料查核報告\n\n')
        w.write(f"產出時間：{report['generated_at']}；OK={summary['OK']}／STALE={summary['STALE']}／MISSING={summary['MISSING']}\n\n")
        w.write('| ID | 指標 | 值 | 真正觀測日 | 狀態 | 來源或卡點 |\n|---|---|---:|---|---|---|\n')
        for v in results.values():
            val=('-' if v['value'] is None else f"{v['value']:g} {v['unit']}")
            desc='來源: '+(v['source_url'] or '無')+'；方式: '+v['method']+'；問題: '+v['error']+'；備註: '+v['detail']
            desc=desc.replace('|',';').replace('\n',' ') 
            w.write(f"| {v['id']} | {v['label']} | {val} | {v['observation_date'] or '-'} | {v['status']} | {desc} |\n")
        w.write('\n未驗證項目請查看 CSV/JSON 的 error/detail；不得將 MISSING 或 STALE 冒充最新正式值。\n')
    print('完成輸出:',out.resolve(),'統計:',summary)
    return report

def selftest():
    # No network; formula and unit conversions check independently.
    assert abs((119.51-1365.39+10.09)-(-1235.79))<1e-8
    assert abs((-1235.79/10)-(-123.579))<1e-8
    x=validate_manual('m14',{'value':-123.579,'unit':'USD bn','observation_date':'2026-10-07',
                             'source_url':'https://fred.stlouisfed.org/series/WDTGAL','method':'測試範例'})
    assert x['value']==-123.579
    try:validate_manual('m06',{'value':4.75,'unit':'%','observation_date':'2026-10-13',
                              'source_url':'https://www.cmegroup.com','method':'測試'})
    except ValueError: pass
    else:raise AssertionError('m06 防呆無效')
    # 測試真正以三組 Series 輸入 netliq()：檢驗日期對齊及來源單位。
    class MockF:
        def fred(self, key):
            dates=pd.to_datetime(['2026-07-08','2026-10-07'])
            values={'WALCL':[6735609,6747560], 'WDTGAL':[749244,885783],
                    'RRPONTSYD':[3.347,2.338]}
            return pd.Series(values[key],index=dates)
    nl=netliq(MockF())
    assert nl['value']==-123.579, nl
    # 缺月的 CPI 不得用更早月份偷代替；欠缺連續就業月份不得算三月均值。
    class MockCPI:
        def fred(self,key):
            return pd.Series([300.,310.],index=pd.to_datetime(['2025-09-01','2026-10-01']))
    try: core_cpi(MockCPI())
    except ValueError: pass
    else: raise AssertionError('CPI 缺精確同月基期未攔截')
    class MockNFP:
        def fred(self,key):
            return pd.Series([100.,110.,120.,130.],index=pd.to_datetime(['2026-06-01','2026-07-01','2026-09-01','2026-10-01']))
    try: nfp(MockNFP())
    except ValueError: pass
    else: raise AssertionError('NFP 缺月未攔截')
    # 產生錯誤報告的缺值也必須可以清楚記錄。
    assert row('m16',error='找不到歷史年增率')['status']=='MISSING'
    try: row('m07',float('nan'),'2026-10-12','https://fred.stlouisfed.org','test')
    except ValueError: pass
    else: raise AssertionError('自動來源 NaN 未攔截')
    for k,bad in [('m07',-5),('s05',120),('m10',600)]:
        try: row(k,bad,'2026-10-12','https://example.com','故障注入')
        except ValueError: pass
        else: raise AssertionError(f'{k} 不合理數值未攔截')
    tomorrow=(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()+dt.timedelta(days=1)).isoformat()
    try: row('m07',15,tomorrow,'https://example.com','故障注入')
    except ValueError: pass
    else: raise AssertionError('未來觀測日期未攔截')
    # 快取中的原始 WTI 口徑必須保留下來，不能被 validate_manual 錯誤剔除。
    cache_wti=validate_manual('m10',{'value':74.2,'unit':'USD/bbl',
           'observation_date':'2026-10-09','source_url':SOURCES['m10'][0],
           'method':'歷史快取','detail':'CL=F 近月連續期貨；合約月份待進一步核對'})
    assert cache_wti['value']==74.2
    # Same calendar month with a different recording day should work.
    class MockShiftedCPI:
        def fred(self,key):
            return pd.Series([300.,315.],index=pd.to_datetime(['2025-09-01','2026-09-15']))
    assert core_cpi(MockShiftedCPI())['value']==5.0
    # One-month delta is calendar-month aligned, not an unexplained fixed 21-day window.
    class MockBE:
        def fred(self,key):
            return pd.Series([2.0,2.2,2.4],index=pd.to_datetime(['2026-02-27','2026-03-02','2026-03-31']))
    assert month_delta(MockBE())['value']==0.4
    class MockGapBE:
        def fred(self,key):
            return pd.Series([2.0,2.4],index=pd.to_datetime(['2026-01-01','2026-03-31']))
    try: month_delta(MockGapBE())
    except ValueError: pass
    else: raise AssertionError('5YBE 過舊月基期未攔截')
    assert len(LABELS)==24 and len(set(LABELS))==24
    print('SELF-TEST PASS: 24 欄位、m06/m14 單位、防呆、同日期三組數列淨流動性計算')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='V70.2 24 項總經資料來源、日期、可信度驗證工具')
    ap.add_argument('--out',default='24_macro_output')
    ap.add_argument('--overrides',help='人工已驗證 JSON，須含 value/observation_date/source_url/method')
    ap.add_argument('--cache',help='先前同程式的 24_macro_verification.json，作為註明 STALE 的備援')
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:selftest()
    else:run(a.out,a.overrides,a.cache)
