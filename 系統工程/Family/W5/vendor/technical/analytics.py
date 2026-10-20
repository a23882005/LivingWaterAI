"""Performance and technical analytics, using adjusted prices only for performance."""
import math
import numpy as np
import pandas as pd

def nfloat(x):
    try:
        x=float(x)
        return round(x,6) if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def tail(s):
    return nfloat(s.iloc[-1]) if len(s) else None

def td9(s):
    hi=lo=0
    for i in range(4,len(s)):
        if s.iloc[i]>s.iloc[i-4]: hi,lo=min(9,hi+1),0
        elif s.iloc[i]<s.iloc[i-4]: lo,hi=min(9,lo+1),0
        else: hi=lo=0
    return hi,lo

def technical(df):
    c=df["Close"].astype(float);h=df["High"].astype(float)
    l=df["Low"].astype(float);v=df["Volume"].astype(float)
    hi,lo=td9(c);res={"high_td9_setup":hi,"low_td9_setup":lo}
    raw=100*(c-l.rolling(9,min_periods=9).min())/(h.rolling(9,min_periods=9).max()-l.rolling(9,min_periods=9).min()).replace(0,np.nan)
    k=raw.rolling(3,min_periods=3).mean();d=k.rolling(3,min_periods=3).mean()
    res["kd_k_9_3"]=tail(k);res["kd_d_9_3_3"]=tail(d)
    macd=c.ewm(span=12,adjust=False,min_periods=12).mean()-c.ewm(span=26,adjust=False,min_periods=26).mean()
    signal=macd.ewm(span=9,adjust=False,min_periods=9).mean()
    res["macd_12_26"]=tail(macd);res["macd_signal_9"]=tail(signal);res["macd_histogram"]=tail(macd-signal)
    for period in [5,10,20,50,60,200]:
        res["ma"+str(period)]=tail(c.rolling(period,min_periods=period).mean())
    mid=(h+l)/2;emv=mid.diff()*(h-l)/(v/1_000_000).replace(0,np.nan)
    res["emv_14"]=tail(emv.rolling(14,min_periods=14).mean())
    change=c.diff();up=change.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    down=(-change.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+up/down.replace(0,np.nan))
    rsi=rsi.mask((down==0)&(up>0),100).mask((up==0)&(down>0),0).mask((up==0)&(down==0),50)
    res["rsi14"]=tail(rsi)
    prior=c.shift();tr=pd.concat([h-l,(h-prior).abs(),(l-prior).abs()],axis=1).max(axis=1)
    res["atr14"]=tail(tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean())
    for period in [5,20,50]:
        avg=v.rolling(period,min_periods=period).mean().iloc[-1]
        res["volume_ratio_"+str(period)]=nfloat(v.iloc[-1]/avg) if avg>0 else None
    return res

def monthly_cagr(series,months):
    m=series.resample("ME").last().dropna()
    if len(m) and m.index[-1].date()>series.index[-1].date():m=m.iloc[:-1]
    if len(m)<months+1:return None
    window=m.iloc[-months-1:]
    if not window.index.equals(pd.date_range(window.index[0],window.index[-1],freq="ME")):return None
    changes=window.pct_change().iloc[1:]
    return nfloat((1+changes).prod()**(12/months)-1)

def daily_cagr(series,years):
    end=series.index[-1]; target=end-pd.DateOffset(years=years)
    candidates=series.loc[(series.index>=target-pd.Timedelta(days=7))&(series.index<=target+pd.Timedelta(days=7))]
    if candidates.empty:return None
    start=min(candidates.index,key=lambda d:abs((d-target).days));days=(end-start).days
    return nfloat((series.iloc[-1]/series.loc[start])**(365.25/days)-1) if days>0 else None

def performance(df):
    s=df["Adj Close"].astype(float).dropna();s=s[s>0]
    if len(s)<2:return {"error":"insufficient adjusted-price history"}
    peak=s.cummax();drawdown=s/peak-1;trough=drawdown.idxmin();before=s.loc[:trough];p=before.idxmax()
    recovery=s.loc[trough:];recovery=recovery[recovery>=s.loc[p]]
    r={"history_start":str(s.index[0].date()),"history_end":str(s.index[-1].date()),
       "observations":len(s),"total_return_basis":"Yahoo Adj Close, pre-tax approximation",
       "max_drawdown":nfloat(drawdown.min()),"peak_date":str(p.date()),
       "trough_date":str(trough.date()),"recovery_date":str(recovery.index[0].date()) if len(recovery) else None}
    for years in [1,5,10,20]:r["cagr_"+str(years)+"y"]=daily_cagr(s,years)
    r["cagr_3y_monthly"]=monthly_cagr(s,36);r["cagr_15y_monthly"]=monthly_cagr(s,180)
    return r
