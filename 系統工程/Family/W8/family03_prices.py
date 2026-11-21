"""On-demand public adjusted-price archive, independent of all family accounts."""
from datetime import date, datetime, timezone, timedelta
from functools import lru_cache
import argparse
import json
import math
from pathlib import Path
import random
import time
from zipfile import ZIP_DEFLATED, ZipFile

ARCHIVE="家人03_行情.zip"
US="VT VOO VTI VXUS QQQ SOXX SMH PPH DYNF CPAI VDC XLV XLI XLF PAWZ ZTS ADBE AVGO GOOG IBKR MDT MSFT NVDA DRAM BRK.B".split()
LISTINGS={s:(s.replace(".","-"),"USD") for s in US}
LISTINGS.update({s:(s+".TW","TWD") for s in ("0050","00956","2454","2330")})
LISTINGS.update({s:(s+".L","USD") for s in ("VWRA","NATO","VALU")})
LISTINGS["USDTWD"]=("TWD=X","TWD_PER_USD")


def checked(currency, rows):
    vals={}
    previous=""
    for d,value in rows:
        date.fromisoformat(d)
        if d<=previous or d>date.today().isoformat() or not math.isfinite(value) or value<=0:
            raise ValueError("異常行情日期或價格")
        vals[d]=float(value)
        previous=d
    if len(vals)<2:
        raise ValueError("歷史樣本不足")
    return currency,vals


def reader(path):
    @lru_cache(maxsize=64)
    def load(symbol, mtime):
        with ZipFile(path) as z:
            listing=LISTINGS.get(symbol)
            if not listing or symbol+".json" not in z.namelist():
                return None
            obj=json.loads(z.read(symbol+".json"))
            if (obj["symbol"],obj["listing"],obj["currency"],obj["field"])!=(
                    symbol,*listing,"Adj Close" if symbol!="USDTWD" else "Close"):
                raise ValueError("行情商品或幣別不符")
            return checked(listing[1],obj["rows"])
    def read(symbols):
        if not path.is_file():return {}
        return {s:v for s in symbols if (v:=load(s,path.stat().st_mtime_ns))}
    return read


def download(out):
    import yfinance as yf
    # One small batch at a time. Verify reported listing currency independently.
    report={}
    end=datetime.now(timezone.utc).date()
    start=end-timedelta(days=365*10+3)
    symbols=list(LISTINGS)
    with ZipFile(out,"w",ZIP_DEFLATED) as z:
        for j in range(0,len(symbols),4):
            group=symbols[j:j+4]
            tickers=[LISTINGS[s][0] for s in group]
            unresolved=set(group)
            for attempt in range(3):
                try:
                    frame=yf.download([LISTINGS[s][0] for s in sorted(unresolved)],start=start,end=end,
                                      interval="1d",auto_adjust=False,threads=False,group_by="ticker",
                                      progress=False,timeout=12,multi_level_index=True)
                except Exception as exc:
                    for s in unresolved: report[s]=type(exc).__name__
                    frame=None
                for s in sorted(unresolved):
                    code,cur=LISTINGS[s]
                    field="Close" if s=="USDTWD" else "Adj Close"
                    try:
                        if frame is None or code not in frame.columns.get_level_values(0):
                            raise ValueError("無此掛牌行情")
                        fx=s=="USDTWD"
                        ticker=yf.Ticker(code)
                        metadata=ticker.get_history_metadata() or {}
                        if metadata.get("currency")!=("TWD" if fx else cur):
                            raise ValueError("供應商掛牌幣別待核")
                        data=frame[code][field].dropna()
                        series=[(str(d.date()),float(v)) for d,v in data.items()]
                        checked(cur,series)
                        obj=dict(symbol=s,listing=code,currency=cur,field=field,rows=series)
                        z.writestr(s+".json",json.dumps(obj,separators=(",",":")))
                        report[s]=dict(rows=len(series),start=series[0][0],end=series[-1][0])
                        unresolved.remove(s)
                    except Exception as exc:
                        report[s]=str(exc)[:150]
                if not unresolved: break
                if attempt<2: time.sleep(3*2**attempt+random.random())
            time.sleep(1.5+random.random())
        z.writestr("manifest.json",json.dumps({"source":"Yahoo Finance via yfinance","generated":end.isoformat(),
                                               "items":report},ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False))
    if not any(isinstance(v,dict) for v in report.values()):
        raise RuntimeError("供應端沒有回傳已驗證行情")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",default=ARCHIVE)
    download(Path(p.parse_args().output))
