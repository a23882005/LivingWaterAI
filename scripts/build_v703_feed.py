#!/usr/bin/env python3
"""Fail-closed adapter: 24-item audit -> V70.3 family display JSON."""
import argparse, datetime as dt, json, math
from pathlib import Path
NEEDED=('m07','m01','m06','m08','m03_qqq','m03_spy','m03_vt','m02','m04','m05','m09','m10','m12','m13','m17','m14','m15','m16','m18','m19','m20')
def convert(source):
    rows=source.get('items',{})
    if not isinstance(rows,dict): raise ValueError('items object required')
    indicators={}; gaps=[]
    for k in NEEDED:
        r=rows.get(k,{})
        if not isinstance(r,dict): gaps.append(k+': invalid record'); continue
        value,obs,url,status=r.get('value'),r.get('observation_date'),r.get('source_url'),r.get('status')
        try:
            if status!='OK' or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value): raise ValueError('not verified OK')
            day=dt.date.fromisoformat(obs)
            if day>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date(): raise ValueError('future date')
            if not isinstance(url,str) or not url.startswith('https://'): raise ValueError('source URL missing')
            indicators[k]={'value':value,'dataDate':obs,'source':url,'unit':r.get('unit',''),'method':r.get('method','')}
        except (ValueError,TypeError) as e: gaps.append(f'{k}: {status or "MISSING"} ({e})')
    return {'schema':'V70.3/macro-feed-v1','asOf':source.get('generated_at',''),'indicators':indicators,'news':[],'verification':{'ready':len(indicators)==len(NEEDED),'valid':len(indicators),'totalRequired':len(NEEDED),'missing':gaps}}
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True);ap.add_argument('--output',required=True)
    a=ap.parse_args();result=convert(json.loads(Path(a.input).read_text(encoding='utf-8')))
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"V70.3 feed {result['verification']['valid']}/{len(NEEDED)}; ready={result['verification']['ready']}")
