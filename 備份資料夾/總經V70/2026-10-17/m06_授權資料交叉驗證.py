#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""m06 independent authorized-snapshot calculator, not a website scraper.
No automatic Investing.com access; no m06 promotion to formal 18-item feed.
"""
import argparse,datetime as dt,json,math,re
from pathlib import Path
PAT=re.compile(r'^\s*(\d+(?:\.\d+)?)\s*%?\s*[-–]\s*(\d+(?:\.\d+)?)\s*%?\s*$')
def midpoint(band):
    m=PAT.fullmatch(str(band))
    if not m:raise ValueError("Invalid target rate band")
    lo,hi=map(float,m.groups())
    if not (0<=lo<hi<=25 and abs(hi-lo-.25)<1e-7):raise ValueError("Rate band must span 25bp")
    return (lo+hi)/2
def calculate(data,today=None):
    today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    date=dt.date.fromisoformat(data["observation_date"])
    if not 0<=(today-date).days<=5:raise ValueError("Snapshot is future or stale")
    if data.get("permission_status")!="authorized":raise ValueError("Automated source use not authorized")
    if not str(data.get("source_url","")).startswith("https://"):raise ValueError("Source missing")
    base=midpoint(data["current_target_range"]);horizon=date+dt.timedelta(days=365)
    eligible=[];seen=set()
    for m in data["meetings"]:
        day=dt.date.fromisoformat(m["date"])
        if day in seen:raise ValueError("Duplicate meeting")
        seen.add(day)
        if abs((day-horizon).days)>45:continue
        ps=m["probabilities"]
        if not isinstance(ps,dict) or not ps:raise ValueError("No probability data")
        mass=0.;weighted=0.
        for band,p in ps.items():
            if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=100:raise ValueError("Invalid probability")
            weighted+=midpoint(band)*p;mass+=p
        if not 99.5<=mass<=100.5:raise ValueError("Probability sum invalid")
        eligible.append((abs((day-horizon).days),day,weighted/mass,mass))
    if not eligible:raise ValueError("No meeting near 12 months")
    _,meeting,expect,total=min(eligible)
    return {"id":"m06","value":round((expect-base)/.25,4),"observation_date":str(date),"meeting_date":str(meeting),
            "current_mid_pct":base,"expected_mid_pct":round(expect,5),"probability_total_pct":round(total,2),
            "source_url":data["source_url"],"status":"CANDIDATE_NEEDS_CROSSCHECK","unit":"25bp",
            "method":"weighted FOMC target rate, 365 days from snapshot"}
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="m06_candidate.json")
    a=ap.parse_args()
    try:result=calculate(json.loads(Path(a.input).read_text(encoding="utf-8")))
    except (ValueError,KeyError,TypeError) as e:result={"id":"m06","value":None,"status":"MISSING","error":str(e)}
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
