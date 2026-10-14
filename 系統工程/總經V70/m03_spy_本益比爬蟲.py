#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPY TTM P/E probe. Portfolio Visualizer first; fail closed on fund mismatch."""
import argparse, datetime as dt, json, random, re, time
from pathlib import Path
from html import unescape

SOURCES = {
  "Portfolio Visualizer":"https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=SPY",
  "Stock Analysis":"https://stockanalysis.com/etf/spy/"
}
ISSUER="https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy"

def parse_pe(name, html):
    text=unescape(re.sub(r'<[^>]+>',' ',re.sub(r'<(script|style)\\b[^>]*>.*?</\\1>',' ',html,flags=re.I|re.S)))
    text=re.sub(r'\\s+',' ',text).strip()
    if name=="Portfolio Visualizer":
        # SPY must be the fund, not just a selected benchmark.
        if not re.search(r'\\bName\\s+State Street\\s*SPDR\\s*S&P\\s*500\\s*ETF',text,re.I):
            raise ValueError("Primary fund not confirmed as SPY")
        pattern=r'Price\\s*/\\s*Earnings\\s*\\(\\s*TTM\\s*\\)\\s*(\\d+(?:\\.\\d+)?)'
    elif name=="Stock Analysis":
        pattern=r'\\bPE\\s+Ratio\\s*(\\d+(?:\\.\\d+)?)'
    else:raise ValueError("Unrecognized source")
    match=re.search(pattern,text,re.I)
    if not match:raise ValueError("SPY P/E named field unavailable")
    value=float(match.group(1))
    if not 1<value<200:raise ValueError("P/E out of range")
    return value

def collect():
    import requests
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    result={}
    with requests.Session() as s:
        for name,url in SOURCES.items():
            record={"source_url":url,"retrieved_at":now,"value":None,"status":"MISSING","valuation_asof":None}
            try:
                time.sleep(random.uniform(.7,1.5))
                r=s.get(url,timeout=(8,18),headers={"User-Agent":"Mozilla/5.0"})
                if r.status_code==429:raise ValueError("HTTP 429; no further retry")
                r.raise_for_status()
                if len(r.content)>4_000_000:raise ValueError("Document too large")
                record["value"]=parse_pe(name,r.text)
                record["status"]="CANDIDATE_NEEDS_VALUATION_DATE"
            except Exception as exc:record["error"]=str(exc)[:200]
            result[name]=record
    return {"id":"m03_spy","value":None,"status":"UNVERIFIED" if any(v["value"] for v in result.values()) else "MISSING",
            "sources":result,"issuer_methodology_reference":ISSUER,
            "note":"Portfolio Visualizer primary; never mistake a benchmark's P/E for SPY's or a retrieval date for valuation date."}

def selftest():
    sample="<td>Name</td><td>State Street SPDR S&P 500 ETF (SPY)</td><td>Price/Earnings (TTM)</td><td>24.20</td>"
    assert parse_pe("Portfolio Visualizer",sample)==24.20
    bad="<td>Name</td><td>Invesco S&P 500 Equal Weight ETF (RSP)</td><td>Selected Benchmark</td><td>SPY</td><td>Price/Earnings (TTM)</td><td>20.26</td>"
    try:parse_pe("Portfolio Visualizer",bad)
    except ValueError:pass
    else:raise AssertionError("Benchmark-only SPY accepted")
    assert parse_pe("Stock Analysis","<span>PE Ratio</span><span>25.00</span>")==25.
    print("SELFTEST PASS: SPY identity and TTM field checked; benchmark misidentification rejected")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--out",default="m03_spy_candidates.json")
    a=p.parse_args()
    if a.self_test:selftest()
    else:
        result=collect()
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
