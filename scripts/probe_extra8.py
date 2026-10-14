#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe official sources for the eight not-yet-automated macro readings.
Never substitute proxies, stale webpage templates, ETF EPS, or invented observations.
This is a diagnostic artifact, not verified_overrides.json.
"""
import datetime as dt
import json
import pathlib
import re
import requests
from bs4 import BeautifulSoup

TARGETS = {
    "m06": ("CME FedWatch", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"),
    "m03_qqq": ("Invesco QQQ", "https://www.invesco.com/qqq-etf/en/about.html"),
    "m03_spy": ("SPDR SPY", "https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy"),
    "m03_vt": ("Vanguard VT", "https://investor.vanguard.com/investment-products/etfs/profile/vt"),
    "m04": ("ISM Manufacturing", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "m15": ("ISM Services", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "m16": ("Conference Board LEI", "https://www.conference-board.org/topics/us-leading-indicators"),
    "s05": ("TradingView MMFI", "https://www.tradingview.com/symbols/INDEX-MMFI/"),
}
def probe_yahoo_crumb(session, ticker):
    """Check Yahoo authentication and valuation JSON; diagnostics only."""
    record = {"ticker": ticker, "status": "UNVERIFIED"}
    try:
        home = session.get("https://finance.yahoo.com/quote/" + ticker + "/", timeout=(5, 15))
        record["homepage_http"] = home.status_code
        crumb = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=(5, 15))
        record["crumb_http"] = crumb.status_code
        token = crumb.text.strip()
        if not crumb.ok or len(token) > 200 or "<" in token:
            record["status"] = "CRUMB_UNAVAILABLE"
            return record
        url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/" + ticker
        response = session.get(url, params={"modules": "summaryDetail", "crumb": token}, timeout=(5, 20))
        record["quote_http"] = response.status_code
        if response.ok:
            data = response.json()
            result = (data.get("quoteSummary", {}).get("result") or [None])[0] or {}
            fields = result.get("summaryDetail", {})
            record["trailing_pe_present"] = bool(fields.get("trailingPE", {}).get("raw"))
            record["forward_pe_present"] = bool(fields.get("forwardPE", {}).get("raw"))
            record["status"] = "SCHEMA_CHECKED_UNVERIFIED"
        else:
            record["status"] = "QUOTE_HTTP_ERROR"
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        record["status"] = "UNREACHABLE"
        record["error"] = type(exc).__name__
    return record


def probe_issuer(session, key, url):
    record = {"source": url, "status": "UNVERIFIED"}
    try:
        response = session.get(url, timeout=(5, 20))
        record["http_status"] = response.status_code
        record["content_type"] = response.headers.get("content-type", "")[:100]
        record["bytes"] = len(response.content)
        record["status"] = "REACHABLE_UNVERIFIED" if response.ok else "HTTP_ERROR"
    except requests.RequestException as exc:
        record["status"] = "UNREACHABLE"
        record["error"] = type(exc).__name__
    return record


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "LivingWaterAI-Macro-Audit/1.0 (source verification only)"
    records = {}
    # Conference Board LEI must not be confused with discontinued FRED
    # USSLIND (Philadelphia Fed leading index, last observation 2020).
    lei_probe = {"status": "MISSING", "series": "Conference Board US LEI",
                 "reason": "No verified same-vintage current and prior-year index observations"}
    print("LEI_OFFICIAL_SOURCE", lei_probe["status"], lei_probe["reason"], flush=True)
    valuation_diagnostics = {}
    for ticker, key in (("QQQ", "m03_qqq"), ("SPY", "m03_spy"), ("VT", "m03_vt")):
        valuation_diagnostics[key] = {"yahoo": probe_yahoo_crumb(s, ticker), "issuer": probe_issuer(s, key, TARGETS[key][1])}
        print("VALUATION_DIAGNOSTIC", key, valuation_diagnostics[key]["yahoo"]["status"], valuation_diagnostics[key]["issuer"]["status"], flush=True)
    # Inspect structured JSON availability without promoting values to verified OK.
    for ticker in ("QQQ", "SPY", "VT"):
        try:
            url = "https://query1.finance.yahoo.com/v7/finance/quote"
            response = s.get(url, params={"symbols": ticker}, timeout=(5, 20))
            print("ETF_JSON_PROBE", ticker, "HTTP", response.status_code, "JSON", "json" in response.headers.get("content-type", "").lower(), flush=True)
        except requests.RequestException as exc:
            print("ETF_JSON_PROBE", ticker, type(exc).__name__, flush=True)
    for key, (label, url) in TARGETS.items():
        item = {"label": label, "source": url, "status": "UNVERIFIED", "candidate": None}
        try:
            r = s.get(url, timeout=(5, 9), allow_redirects=True)
            item["http_status"] = r.status_code
            item["resolved_url"] = r.url
            item["bytes"] = len(r.content)
            r.raise_for_status()
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            item["visible_text_chars"] = len(text)
            # A working webpage does NOT establish correct value, as-of date or data definition.
            item["status"] = "PAGE_REACHABLE_UNVERIFIED"
        except requests.RequestException as exc:
            item["status"] = "UNREACHABLE"
            item["error"] = f"{type(exc).__name__}: {exc}"[:280]
        records[key] = item
        print(key, item["status"], item.get("http_status", ""), flush=True)
    result = {"schema": "LivingWaterAI/probe-extra8-v1",
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "note": "Source connectivity only; no source has yet passed indicator value/date/unit QA.",
              "indicators": records, "valuation_diagnostics": valuation_diagnostics, "lei_fred_diagnostic": lei_probe}
    out = pathlib.Path("build/macro24/extra8_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def collect_market_history(symbols=("VOO", "SPY", "VT", "QQQ"), directory="data/market_history"):
    """Incremental verified OHLCV, dividends and adjusted close; never fabricate MMFI.

    yfinance is an unofficial upstream. Retain verified cached files when down.
    All daily bars are trading-session dates, not the download date.
    """
    import time
    import random
    import pandas as pd
    import yfinance as yf
    root = pathlib.Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).date()
    report = {"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
              "source":"yfinance (unofficial Yahoo Finance wrapper)",
              "price_basis":"Close=unadjusted; Adj Close=provider-adjusted; dividend cashflows separate",
              "warning":"Adjusted Close is not a tax-adjusted, investor-specific total return",
              "items":{}}
    for i in range(0,len(symbols),4):
        group = symbols[i:i+4]
        cache_by_symbol={}
        earliest=now
        for symbol in group:
            file=root/(symbol+".csv")
            if file.is_file():
                try:
                    prior=pd.read_csv(file)
                    if len(prior) and {'Date','Close','Adj Close','Volume'}.issubset(prior.columns):
                        prior['Date']=pd.to_datetime(prior['Date'],errors='coerce').dt.date
                        if prior['Date'].notna().all() and prior['Date'].is_unique:
                            cache_by_symbol[symbol]=prior
                            earliest=min(earliest,prior['Date'].max()-dt.timedelta(days=7))
                except Exception as exc:
                    print("CACHE_REJECTED",symbol,type(exc).__name__,flush=True)
        if any(symbol not in cache_by_symbol for symbol in group):
            earliest=min(earliest,now-dt.timedelta(days=365*17))
        time.sleep(random.uniform(.5,1.5))
        last_error=""
        downloaded=None
        for attempt in range(3):
            try:
                downloaded=yf.download(list(group),start=earliest.isoformat(),
                     end=(now+dt.timedelta(days=1)).isoformat(),
                     auto_adjust=False,actions=True,group_by="ticker",threads=False,
                     progress=False,timeout=20)
                if downloaded is None or downloaded.empty:
                    raise ValueError("Yahoo returned no daily bars")
                break
            except Exception as exc:
                last_error=str(exc)[:180]
                if "429" in last_error or "Too Many Requests" in last_error:
                    print("RATE_LIMIT_STOP",last_error,flush=True)
                    break
                time.sleep(min(2**attempt+random.uniform(0,.5),5))
        for symbol in group:
            file=root/(symbol+".csv")
            record={"status":"MISSING","observation_date":None,"error":last_error}
            try:
                if downloaded is None or downloaded.empty:
                    raise ValueError(last_error or "No download data")
                frame=downloaded[symbol].copy() if isinstance(downloaded.columns,pd.MultiIndex) else downloaded.copy()
                frame=frame.reset_index()
                if 'Date' not in frame: raise ValueError("Daily Date column missing")
                frame['Date']=pd.to_datetime(frame['Date'],utc=True).dt.date
                wanted=['Date','Open','High','Low','Close','Adj Close','Volume','Dividends','Stock Splits']
                for col in ('Dividends','Stock Splits'):
                    if col not in frame: frame[col]=0.0
                frame=frame[wanted].dropna(subset=['Close','Adj Close'])
                for col in ['Open','High','Low','Close','Adj Close','Volume','Dividends','Stock Splits']:
                    frame[col]=pd.to_numeric(frame[col],errors='coerce')
                if frame.empty or frame['Date'].isna().any() or frame['Date'].duplicated().any():
                    raise ValueError("Invalid or duplicate trading dates")
                if not frame['Date'].is_monotonic_increasing or frame['Date'].max()>now:
                    raise ValueError("Nonmonotonic or future dates")
                if (frame[['Close','Adj Close']]<=0).any().any() or (frame['Volume']<0).any():
                    raise ValueError("Nonpositive prices or negative volumes")
                if frame[['Open','High','Low','Close','Adj Close','Volume']].isna().any().any():
                    raise ValueError("Missing OHLCV values")
                prior=cache_by_symbol.get(symbol)
                if prior is not None:
                    frame=pd.concat([prior,frame],ignore_index=True)
                    frame=frame.drop_duplicates(subset=['Date'],keep='last').sort_values('Date')
                # The rolling price signal is for this *one ETF*; never MMFI market breadth.
                frame['MA50_Close']=frame['Close'].rolling(50,min_periods=50).mean()
                frame['Above_MA50_Individual']=frame['Close']>frame['MA50_Close']
                frame['Adjusted_Price_Drawdown']=frame['Adj Close']/frame['Adj Close'].cummax()-1
                tmp=file.with_suffix(".tmp")
                frame.assign(Date=frame['Date'].astype(str)).to_csv(tmp,index=False)
                tmp.replace(file)
                record={"status":"OK","observation_date":str(frame['Date'].iloc[-1]),
                        "rows":int(len(frame)),"cache_file":str(file),
                        "adjusted_price_max_drawdown":float(frame['Adjusted_Price_Drawdown'].min())}
            except Exception as exc:
                record["error"]=str(exc)[:200]
                if file.is_file():
                    record["status"]="STALE"
                    record["cache_file"]=str(file)
                    if symbol in cache_by_symbol:
                        record["observation_date"]=str(cache_by_symbol[symbol]['Date'].max())
            report["items"][symbol]=record
            print("MARKET_DOWNLOAD",symbol,record["status"],record.get("observation_date"),flush=True)
    (root/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

if __name__ == "__main__":
    main()
