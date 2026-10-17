#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NYSE $MMFI four-source ordered probe; only dated/identified data may be approved."""
import datetime as dt
import html
import json
import re
import time
from pathlib import Path
SOURCES=[
 ('Barchart','https://www.barchart.com/stocks/quotes/%24MMFI/comparison'),
 ('StockCharts','https://stockcharts.com/h-sc/ui?s=%24MMFI'),
 ('Market-In-Out','https://www.marketinout.com/stock-screener/above-50-day-moving-average'),
 ('TradingView','https://www.tradingview.com/symbols/INDEX-MMFI/'),
]
def parse(name,raw,today=None):
    today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    raw=re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>',' ',raw)
    text=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',raw)))
    if name=='Barchart':
        if not re.search(r'(?i)(\$MMFI|Percent of Stocks Above 50.Day Average)',text):
            raise ValueError('MMFI identity unverified')
        m=re.search(r'(?i)\bPrice Information\b.{0,300}?\bLast\s+([0-9]+(?:\.[0-9]+)?)\b',text)
    elif name=='StockCharts':
        m=re.search(r'(?i)\$MMFI\b[^\d]{0,90}([0-9]+(?:\.[0-9]+)?)\b',text)
    else:raise ValueError('NYSE MMFI identical coverage & authorized structured feed not verified')
    if not m:raise ValueError('Dated close field absent; dynamic quote likely')
    value=float(m.group(1))
    if not 0<=value<=100:raise ValueError('MMFI outside 0..100')
    d=re.search(r'(?i)(?:as of|quote overview for|last updated)\s+(20\d{2}-\d{2}-\d{2})',text)
    if not d:raise ValueError('Observation date missing; do not use retrieval date')
    day=dt.date.fromisoformat(d.group(1))
    if not 0<=(today-day).days<=5:raise ValueError('Quote stale or future-dated')
    return value,day.isoformat()
def collect():
    import requests
    attempts=[]
    with requests.Session() as session:
        for name,url in SOURCES:
            try:
                if name in ('Market-In-Out','TradingView'):
                    raise ValueError('No verified NYSE MMFI-matching machine-readable endpoint')
                r=session.get(url,timeout=(6,15),headers={'User-Agent':'LivingWaterAI-Research/1.0'})
                if r.status_code==429:raise ValueError('429; do not retry this source')
                r.raise_for_status()
                if len(r.content)>2000000:raise ValueError('Oversize response')
                val,day=parse(name,r.text)
                return {'id':'s05','value':val,'status':'OK','unit':'%',
                        'observation_date':day,'source_url':url,'attempts':attempts}
            except Exception as e:attempts.append({'name':name,'error':str(e)[:180]})
            time.sleep(.25)
    return {'id':'s05','value':None,'status':'MISSING','observation_date':None,
            'source_url':None,'attempts':attempts}
def selftest():
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    fixture='$MMFI Quote Overview for '+str(now)+' Price Information Open 30 High 32 Low 29 Last 29.17 Change -1'
    assert parse('Barchart',fixture)[0]==29.17
    for bad in ('$MMFI Price Information Last 29.17',
                '$MMFI Quote Overview for 2020-01-01 Price Information Last 29.17'):
        try:parse('Barchart',bad)
        except ValueError:pass
        else:raise AssertionError('Bad quote passed')
    print('s05 parser unit QA PASS (synthetic fixtures, not real market fetch)')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');p.add_argument('--out',default='s05_mmfi.json')
    a=p.parse_args()
    if a.self_test:selftest()
    else:
        v=collect()
        Path(a.out).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(v,ensure_ascii=False))
