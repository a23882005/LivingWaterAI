#!/usr/bin/env python3
"""Read-only V70 official/free-data availability probe. Does not publish data.
No credentials, no repository writes, no source/model changes. 2026-11-06.
"""
import csv
import datetime as dt
import io
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("build/v70_free_source_probe")
ROOT.mkdir(parents=True, exist_ok=True)
TODAY = dt.datetime.now(dt.timezone.utc)
TARGETS = [
    ("NFCICREDIT", "Chicago Fed credit conditions/FRED download",
     "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCICREDIT", "fred", 28),
    ("NFCIRISK", "Chicago Fed risk conditions/FRED download",
     "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCIRISK", "fred", 28),
    ("CFNAI", "Chicago Fed national activity/FRED download",
     "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CFNAI", "fred", 90),
    ("DTWEXBGS", "Federal Reserve broad USD/FRED download",
     "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS", "fred", 21),
    ("TREASURY_2Y_10Y", "US Treasury 2026 daily nominal yields",
     "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv", "treasury", 21),
    ("EIA_WTI_SPOT", "EIA Cushing WTI daily spot price XLS",
     "https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls", "eia_xls", 30),
    ("BLS_UNEMPLOYMENT", "BLS LNS14000000 unemployment rate, seasonally adjusted",
     "https://api.bls.gov/publicAPI/v2/timeseries/data/LNS14000000?startyear=2025&endyear=2026", "bls", 90),
]

def parse_date(s):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError("date not recognized: " + repr(s)[:45])

def parse_fred(blob, name):
    s=blob.decode("utf-8-sig")
    rows=list(csv.DictReader(io.StringIO(s)))
    if not rows:
        raise ValueError("Empty FRED series")
    col=name if name in rows[0] else None
    date_col="DATE" if "DATE" in rows[0] else "observation_date"
    if not col or date_col not in rows[0]:
        raise ValueError("FRED missing headers " + str(list(rows[0]))[:120])
    vals=[]
    for r in rows:
        try:
            value=float(r[col])
            if math.isfinite(value):
                vals.append((parse_date(r[date_col]),value))
        except (ValueError,TypeError,KeyError):
            continue
    if not vals:
        raise ValueError("No numeric FRED observations")
    day,value=max(vals)
    return day, {"value":value,"unit":"index","sample_count":len(vals),"last_five":[{"date":d.isoformat(),"value":v} for d,v in vals[-5:]]}

def parse_treasury(blob, name):
    rows=list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("Empty Treasury CSV")
    sample=rows[0]
    date_key=next((k for k in sample if k.strip().lower() in ("date","record_date")),None)
    ten=next((k for k in sample if k.strip().lower() in ("10-year","10 year","10-year treasury","10 yr")),None)
    two=next((k for k in sample if k.strip().lower() in ("2-year","2 year","2-year treasury","2 yr")),None)
    if not date_key or not ten or not two:
        raise ValueError("Missing date/2-year/10-year columns: "+repr(list(sample)))
    obs=[]
    for r in rows:
        try:
            d=parse_date(r[date_key]); y2=float(r[two]); y10=float(r[ten])
            if 0<y2<30 and 0<y10<30:
                obs.append((d,y2,y10))
        except (ValueError,TypeError,KeyError):
            continue
    if not obs:
        raise ValueError("No valid Treasury yields")
    day,y2,y10=max(obs)
    return day,{"yield_2Y_pct":y2,"yield_10Y_pct":y10,"curve_10Y_minus_2Y_pp":round(y10-y2,4),"sample_count":len(obs)}

def parse_eia(blob, name):
    import xlrd
    book=xlrd.open_workbook(file_contents=blob)
    samples=[]
    for sheet in book.sheets():
        for idx in range(max(0,sheet.nrows-120),sheet.nrows):
            r=sheet.row_values(idx)
            if len(r)<2:
                continue
            try:
                if isinstance(r[0],float):
                    d=xlrd.xldate_as_datetime(r[0],book.datemode).date()
                else:
                    d=parse_date(r[0])
                price=float(r[1])
                if 2000<=d.year<=2030 and 1<=price<=1000 and math.isfinite(price):
                    samples.append((d,price))
            except (ValueError,TypeError,OverflowError):
                continue
    if not samples:
        raise ValueError("Downloaded XLS but numeric date/price not parsed; sheets "+repr([(s.name,s.nrows) for s in book.sheets()]))
    d,p=max(samples)
    return d,{"wti_spot_usd_per_bbl":p,"sample_count_last_120_rows":len(samples),"sheet_names":[s.name for s in book.sheets()]}

def parse_bls(blob, name):
    obj=json.loads(blob.decode("utf-8-sig"))
    if obj.get("status")!="REQUEST_SUCCEEDED":
        raise ValueError("BLS status "+repr(obj.get("status"))+" "+repr(obj.get("message")))
    series=obj.get("Results",{}).get("series",[])
    if not series:
        raise ValueError("BLS has no series")
    observations=[]
    for row in series[0].get("data",[]):
        period=row.get("period","")
        if len(period)!=3 or not period.startswith("M") or period=="M13":
            continue
        try:
            day=dt.date(int(row["year"]),int(period[1:]),1)
            val=float(row["value"])
            if 0<=val<=30:
                observations.append((day,val))
        except (ValueError,TypeError,KeyError):
            continue
    if not observations:
        raise ValueError("BLS series has no numeric monthly values")
    d,v=max(observations)
    return d,{"unemployment_rate_pct":v,"series":"LNS14000000","seasonal_adjustment":"SA"}

PARSERS={"fred":parse_fred,"treasury":parse_treasury,"eia_xls":parse_eia,"bls":parse_bls}

def fetch(url):
    headers={"User-Agent":"LivingWaterAI-V70-ReadOnly-Test/2026-11-06 (research probe)","Accept":"text/csv,application/vnd.ms-excel,application/json,*/*"}
    last=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers=headers,method="GET")
            with urllib.request.urlopen(req,timeout=22) as resp:
                code=resp.getcode()
                data=resp.read(9000000)
                if len(data)>=9000000:
                    raise ValueError("Response exceeded 9MB safety bound")
                return code,resp.headers.get("Content-Type",""),data
        except urllib.error.HTTPError as e:
            last=e
            if e.code in (403,404,401,429):
                break
        except (urllib.error.URLError,TimeoutError,ValueError) as e:
            last=e
        if attempt<1:
            time.sleep(2)
    raise last

def main():
    out=[]
    for name,label,url,kind,max_age in TARGETS:
        record={"name":name,"description":label,"url":url,"checked_utc":TODAY.isoformat(),"status":"NOT_TESTED","last_observation":None}
        try:
            status,mime,blob=fetch(url)
            day,details=PARSERS[kind](blob,name)
            age=(TODAY.date()-day).days
            record.update({"status":"PASS_NUMERIC" if -1<=age<=max_age else "PASS_OLD_DATE",
                           "http_status":status,"mime_type":mime,"bytes":len(blob),
                           "last_observation":day.isoformat(),"age_days":age,"values":details})
        except Exception as e:
            record.update({"status":"FAIL","reason":type(e).__name__+": "+str(e)[:350]})
        print("PROBE",json.dumps(record,ensure_ascii=False,sort_keys=True),flush=True)
        out.append(record)
        time.sleep(0.4)
    passed=sum(x["status"]=="PASS_NUMERIC" for x in out)
    result={"schema":"V70_Official_Free_Data_Probe_v1","run_utc":TODAY.isoformat(),
            "real_http_probe":True,"scope":"data access only, not licensing or V70 model substitution",
            "pass_numeric_count":passed,"total_tested":len(out),"results":out}
    (ROOT/"results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary=["# V70 official/free numerical download probe",f"Run UTC: {TODAY.isoformat()}",
             f"PASS_NUMERIC: {passed}/{len(out)}", "",
             "| Source | HTTP / parsing status | Last numeric date | Value |", "|---|---|---|---|"]
    for x in out:
        val=next(iter(x.get("values",{}).items()),("",""))[1]
        summary.append(f"| {x['name']} | {x['status']} | {x['last_observation'] or 'NA'} | {val} |")
    (ROOT/"README.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("PROBE_SUMMARY",json.dumps({"passed":passed,"total":len(out),"out":str(ROOT)},ensure_ascii=False),flush=True)
    return 0 if passed>=2 else 1

if __name__=="__main__":
    raise SystemExit(main())
