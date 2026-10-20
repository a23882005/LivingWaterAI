"""Actual Yahoo Finance downloads with validation and preserved status."""
import json,logging,os,re,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from .analytics import performance,technical,nfloat
FIELDS=["Open","High","Low","Close","Adj Close","Volume","Dividends","Stock Splits"]
log=logging.getLogger(__name__)

def clean(df):
    if df is None or df.empty:raise ValueError("no Yahoo history returned")
    if not isinstance(df.index,pd.DatetimeIndex):raise ValueError("missing DatetimeIndex")
    if isinstance(df.columns,pd.MultiIndex):raise ValueError("unexpected multi-index")
    df=df.copy();df.index=df.index.tz_localize(None).normalize()
    df=df[~df.index.duplicated(keep="last")].sort_index()
    required=["Open","High","Low","Close","Adj Close","Volume"]
    if any(k not in df for k in required):raise ValueError("missing OHLCV/Adj Close")
    for field in FIELDS:
        if field not in df:df[field]=0.
        df[field]=pd.to_numeric(df[field],errors="coerce")
    df=df[FIELDS].dropna(subset=["Close","Adj Close","Low","High"])
    if df.empty or (df[["Close","Adj Close","Low","High"]]<=0).any().any():raise ValueError("invalid prices")
    if (df["High"]<df["Low"]).any():raise ValueError("High below Low")
    if (df["Volume"].fillna(0)<0).any():raise ValueError("negative volume")
    df.index.name="Date";return df

def fetch(symbol):
    import yfinance as yf
    last_error=None
    for i in range(3):
        try:
            df=yf.Ticker(symbol).history(period="max",interval="1d",auto_adjust=False,
                                         actions=True,repair=False,timeout=25)
            return clean(df)
        except Exception as exc:
            last_error=exc;log.warning("%s retry %s: %s",symbol,i+1,exc)
            if i<2:time.sleep(2*(2**i))
    raise RuntimeError(str(last_error))

def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf8",dir=path.parent,delete=False) as tmp:
        json.dump(obj,tmp,ensure_ascii=False,indent=2,allow_nan=False);tmp.write("\n");name=tmp.name
    os.replace(name,path)

def save_history(path,df):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("wb",dir=path.parent,delete=False) as tmp:name=tmp.name
    try:df.to_csv(name,compression="gzip",float_format="%.10g");os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def run(folder,selected=None,loader=fetch):
    folder=Path(folder)
    config=json.loads((folder/"config/symbols.json").read_text(encoding="utf8"))["symbols"]
    if selected:
        wanted=set(selected);config=[x for x in config if x["ticker"] in wanted]
        if wanted!={x["ticker"] for x in config}:raise ValueError("unknown ticker")
    if not config:raise ValueError("no tickers")
    now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    status={"generated_at_utc":now,"source":"yfinance / Yahoo Finance (unofficial)","real_time":False,"symbols":{}}
    quotes={};tech={};perf=[]
    for item in config:
        sym=item["ticker"];path=folder/"data/history"/(re.sub(r"[^A-Za-z0-9_-]","_",sym)+".csv.gz")
        try:
            df=clean(loader(sym))
            save_history(path,df)
            date=str(df.index[-1].date())
            status["symbols"][sym]={"status":"ok","market_date":date,"rows":len(df)}
            quotes[sym]={"market_date":date,"name":item.get("name"),"close":nfloat(df["Close"].iloc[-1]),
                         "adj_close":nfloat(df["Adj Close"].iloc[-1]),"volume":nfloat(df["Volume"].iloc[-1])}
            tech[sym]={"market_date":date,**technical(df)}
            perf.append({"ticker":sym,"market_date":date,**performance(df)})
            time.sleep(1.2)
        except Exception as exc:
            status["symbols"][sym]={"status":"error","error":str(exc)[:250],"old_history_preserved":path.exists()}
    out=folder/"outputs";out.mkdir(parents=True,exist_ok=True)
    if not quotes:
        save_json(out/"data_status.json",status)
        raise RuntimeError("All downloads failed; previous valid summaries preserved")
    save_json(out/"latest_snapshot.json",{"generated_at_utc":now,"source":status["source"],"records":quotes})
    save_json(out/"technical_summary.json",{"generated_at_utc":now,"records":tech})
    with tempfile.NamedTemporaryFile("w",encoding="utf8",dir=out,delete=False) as tmp:
        pd.DataFrame(perf).to_csv(tmp,index=False);tmpname=tmp.name
    os.replace(tmpname,out/"performance_summary.csv")
    save_json(out/"data_status.json",status)
    if any(v["status"]=="error" for v in status["symbols"].values()):
        raise RuntimeError("Some tickers failed; see status for exact errors")
    return status
