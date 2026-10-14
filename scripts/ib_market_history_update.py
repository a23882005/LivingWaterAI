"""LivingWaterAI market history: batched, throttled, incremental, fail-safe.
Universe files: config/ib_global_symbols.txt or config/ib_taiwan_symbols.txt.
Only listed symbols are fetched. This is market data, not a direct IBKR account export.
"""
import argparse,csv,io,json,random,time,datetime as dt
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT=Path("data/market_history")
REQUIRED=["Open","High","Low","Close","Volume"]
def symbols(path):
    return list(dict.fromkeys(s.strip().split("#")[0].strip() for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip() and not s.lstrip().startswith("#")))
def valid(frame):
    if frame is None or frame.empty or any(c not in frame for c in REQUIRED): return False
    a=frame[REQUIRED].copy()
    if a[["Open","High","Low","Close"]].isna().all(axis=1).any(): return False
    if (a["High"] < a["Low"]).any() or (a["Close"] <= 0).any(): return False
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates: return False
    return True
def get_batch(batch, start, tries=3):
    for attempt in range(tries):
        try:
            data=yf.download(batch,start=start,auto_adjust=False,actions=True,progress=False,threads=False,group_by="ticker",timeout=25)
            if data is not None and not data.empty: return data,None
            err="empty response"
        except Exception as exc:
            err=f"{type(exc).__name__}: {str(exc)[:120]}"
        if attempt<tries-1: time.sleep(min(18,2**attempt*3)+random.random()*2)
    return None,err
def one(data,sym,n):
    if n==1 and not isinstance(data.columns,pd.MultiIndex): return data
    if isinstance(data.columns,pd.MultiIndex):
        if sym in data.columns.get_level_values(0): return data[sym]
        if sym in data.columns.get_level_values(1): return data.xs(sym,axis=1,level=1)
    return pd.DataFrame()
def run(region, batch_size):
    config=Path("config")/f"ib_{region}_symbols.txt"
    names=symbols(config); out=ROOT/region;out.mkdir(parents=True,exist_ok=True)
    prior=out/"manifest.json"
    previous=json.loads(prior.read_text(encoding="utf-8")) if prior.exists() else {}
    report={"region":region,"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"universe_source":str(config),"data_source":"Yahoo Finance via yfinance","items":{}}
    for k in range(0,len(names),batch_size):
        group=names[k:k+batch_size]
        starts=[]
        for sym in group:
            old=out/f"{sym.replace('/','_')}.csv"
            if old.exists():
                try:
                    p=pd.read_csv(old,index_col=0,parse_dates=True)
                    starts.append((p.index.max()-pd.Timedelta(days=10)).strftime("%Y-%m-%d") if len(p)>0 else "2000-01-01")
                except Exception: starts.append("2000-01-01")
            else: starts.append("2000-01-01")
        start=min(starts)
        data,error=get_batch(group,start)
        for sym in group:
            dest=out/f"{sym.replace('/','_')}.csv"
            olddata=None
            if dest.exists():
                try: olddata=pd.read_csv(dest,index_col=0,parse_dates=True)
                except Exception: pass
            incoming=one(data,sym,len(group)) if data is not None else pd.DataFrame()
            if not incoming.empty:
                incoming.index=pd.to_datetime(incoming.index).tz_localize(None) if getattr(incoming.index,"tz",None) else pd.to_datetime(incoming.index)
                incoming=incoming.dropna(subset=["Close"])
            combined=pd.concat([olddata,incoming]) if olddata is not None else incoming
            combined=combined[~combined.index.duplicated(keep="last")].sort_index() if not combined.empty else combined
            prior_item=previous.get("items",{}).get(sym,{})
            if valid(combined) and not incoming.empty:
                combined.to_csv(dest)
                report["items"][sym]={"status":"OK","latest_observation":combined.index[-1].strftime("%Y-%m-%d"),"rows":len(combined),"last_verified_utc":report["generated_utc"]}
            else:
                report["items"][sym]={**prior_item,"status":"STALE" if dest.exists() else "MISSING","error":error or "invalid/empty download"}
        time.sleep(1.5+random.random()*2.0)
    prior.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"region":region,"count":len(names),"ok":sum(x["status"]=="OK" for x in report["items"].values()),"stale_or_missing":[s for s,x in report["items"].items() if x["status"]!="OK"]},ensure_ascii=False))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--region",choices=["global","taiwan"],required=True);p.add_argument("--batch-size",type=int,default=5);a=p.parse_args();run(a.region,max(1,min(10,a.batch_size)))
