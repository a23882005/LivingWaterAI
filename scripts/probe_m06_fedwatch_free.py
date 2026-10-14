#!/usr/bin/env python3
"""Diagnostic-only m06 market-implied 12-month rate change; never publish automatically.

Data: unofficial cme-fedwatch 0.2.1 calculation using CME daily futures
settlements + FRED target rate. This is NOT an official CME FedWatch API feed.
Fail closed on missing/stale/estimated data.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path

OUTPUT = Path("build/m06/fedwatch_free_probe.json")

def calculate(feed, today):
    if feed.get("target_source") != "fred":
        raise ValueError("Target range not directly corroborated by FRED")
    trade_date = dt.date.fromisoformat(feed["trade_date"])
    age = (today - trade_date).days
    if age < 0 or age > 5:
        raise ValueError(f"Settlement is stale or in future: {trade_date}, age={age}d")
    current = feed.get("current_target")
    if not isinstance(current,str) or "-" not in current:
        raise ValueError("Missing current target rate range")
    import re
    nums = re.findall(r"\d+(?:\.\d+)?",current)
    if len(nums) != 2:
        raise ValueError("Unexpected current target")
    current_mid = (float(nums[0])+float(nums[1]))/2
    if not 0 <= current_mid <= 25:
        raise ValueError("Current target out of range")
    candidates=[]
    horizon=today + dt.timedelta(days=365)
    for m in feed.get("meetings", []):
        d=dt.date.fromisoformat(m["date"])
        if abs((d-horizon).days)>45:
            continue
        probs=m.get("probabilities",{})
        weighted=0.0
        total=0.0
        for rate,p in probs.items():
            r=re.findall(r"\d+(?:\.\d+)?",str(rate))
            if len(r)!=2: raise ValueError("Malformed target range: "+str(rate))
            low,high=map(float,r)
            if not (0<=low<high<=25 and abs((high-low)-0.25)<0.00001):
                raise ValueError("Unexpected interval width")
            p=float(p)
            if not math.isfinite(p) or not 0<=p<=100: raise ValueError("Invalid probability")
            total+=p
            weighted+=((low+high)/2)*p
        # Rounded public probabilities can sum to 99.9% or 100.1%.
        if not 99.5<=total<=100.5:
            raise ValueError(f"Probability mass not ~100%: {total}")
        mid=weighted/total
        candidates.append((abs((d-horizon).days),d,mid,total,probs))
    if not candidates:
        raise ValueError("No known FOMC meeting near 12-month horizon")
    _,meeting,expected,total,probs=min(candidates)
    return {
        "status":"CANDIDATE_NEEDS_REVIEW",
        "source":"Unofficial cme-fedwatch 0.2.1 / CME public settlement + FRED target",
        "as_of_settlement":trade_date.isoformat(),
        "reference_date":today.isoformat(),
        "meeting_date":meeting.isoformat(),
        "current_target":current,
        "expected_target_mid_pct":round(expected,5),
        "current_target_mid_pct":round(current_mid,5),
        "m06_expected_rate_change_quarters":round((expected-current_mid)/0.25,4),
        "probability_total_pct":round(total,2),
        "probabilities_pct":probs,
        "note":"Diagnostic only. Compare to matching CME official FedWatch date and confirm terms before release."
    }

def main():
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    try:
        from cme_fedwatch import get_probabilities
        data=get_probabilities()
        result=calculate(data,today)
    except Exception as exc:
        result={"status":"MISSING","error_type":type(exc).__name__,
                "error":str(exc)[:400],"reference_date":today.isoformat()}
    OUTPUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="probabilities_pct"},ensure_ascii=False))
    # Keep probe job green even when the source is unavailable; status remains MISSING.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
