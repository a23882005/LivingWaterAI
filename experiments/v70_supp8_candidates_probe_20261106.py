#!/usr/bin/env python3
"""Read-only 10:00 V70 8x4 candidate HTTP reachability and numeric evidence.
No main changes, no commercial rights assertion, no cache, no paid credentials.
"""
from pathlib import Path
import datetime as dt, io, csv, json, re, time, urllib.request, urllib.error, zipfile

IN=Path("data/8_macro_supplement_verified.json")
OUT=Path("build/v70_supp8_probe_20261106")
OUT.mkdir(parents=True,exist_ok=True)
now=dt.datetime.now(dt.timezone.utc)
payload=json.loads(IN.read_text(encoding="utf-8-sig"))
ids=("m06_rate","m06_inf","m06_rstar","m06_output_gap","s05","m03_qqq","m03_spy","m03_vt")
assert set(payload["items"])==set(ids)
UA="Mozilla/5.0 (compatible; V70-readonly-validation/1.0)"
def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,text/csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"})
    last=None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=12) as r:
                code=r.status
                raw=r.read(4500000)
                ct=r.headers.get("Content-Type","")
                return code,ct,raw
        except urllib.error.HTTPError as e:
            last=e
            if e.code in (401,403,404,429):
                break
        except Exception as e:last=e
        if attempt==0:time.sleep(1.2)
    raise last

def parse_fred(series):
    url="https://fred.stlouisfed.org/graph/fredgraph.csv?id="+series
    status,ct,blob=download(url)
    rows=list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    if not rows or series not in rows[0]:raise ValueError("missing series in CSV")
    obs=[(r.get("DATE") or r.get("observation_date"),r.get(series)) for r in rows]
    valid=[]
    for day,val in obs:
        try: valid.append((day,float(val)))
        except (TypeError,ValueError): pass
    if not valid:raise ValueError("no numeric records")
    day,value=valid[-1]
    return {"source":"FRED_CSV","http":status,"date":day,"value":value,"unit":"source unit"}

out=[]
for idx,key in enumerate(ids):
    item=payload["items"][key]
    checks=item["candidate_checks"]
    assert len(checks)==4,(key,len(checks))
    for ci,ch in enumerate(checks,1):
        url=ch["url"]
        row={"key":key,"candidate":ci,"site":ch["site"],"url":url,
             "checked_utc":now.isoformat(),"http":None,"status":"NOT_TESTED",
             "numeric":None,"numeric_source":None,"observation_date":None,
             "previous_claim":ch.get("status"),"error":None}
        try:
            code,ct,blob=download(url)
            row.update(http=code,content_type=ct,bytes=len(blob),status=("HTTP_200" if code==200 else "HTTP_"+str(code)))
            if code==200:
                low=blob[:300000].decode("utf-8",errors="ignore").lower()
                if "access denied" in low[:1000] or "verify you are human" in low[:1000]:
                    row["status"]="HTTP_200_BLOCK_PAGE"
                if key=="m06_rate" and ch["site"] in ("FRED DFEDTARL","FRED DFEDTARU"):
                    sid="DFEDTARL" if "DFEDTARL" in url else "DFEDTARU"
                    r=parse_fred(sid)
                    row.update(numeric=r["value"],numeric_source=r["source"],observation_date=r["date"],status="HTTP_200_NUMERIC_CROSSCHECK")
                if key=="m06_output_gap" and ch["site"]=="FRED GDPC1":
                    r=parse_fred("GDPC1")
                    row.update(numeric=r["value"],numeric_source=r["source"],observation_date=r["date"],status="HTTP_200_NUMERIC_CROSSCHECK")
                if key=="m06_rstar" and url.lower().endswith(".xlsx"):
                    if blob[:2]==b"PK" and zipfile.is_zipfile(io.BytesIO(blob)):
                        row["status"]="HTTP_200_VALID_XLSX_FILE"
                if key.startswith("m03_") and "stockanalysis.com" in url:
                    if "forward" in low and ("pe" in low or "p/e" in low):
                        row["status"]="HTTP_200_FORWARD_TEXT_PRESENT_NOT_PARSED"
                if key=="s05" and ("MMFI" in low.upper()):
                    row["status"]="HTTP_200_MMFI_MENTION_NOT_PARSED"
        except Exception as e:
            row.update(status="FAIL_HTTP_OR_READ",error=type(e).__name__+": "+str(e)[:180])
        print("SUPP_CHECK",json.dumps(row,ensure_ascii=False,sort_keys=True),flush=True)
        out.append(row)
        time.sleep(.3)
summary={"schema":"V70_Supplement8_x4_HTTP_Probe_v1","run_utc":now.isoformat(),
         "scope":"32 candidate URLs HTTP access; numeric only where actually parsed",
         "expected_candidates":32,"checked":len(out),
         "http_200":sum(x["http"]==200 for x in out),
         "numeric_crosschecks":sum(x["numeric"] is not None for x in out),
         "verified_xlsx":sum(x["status"]=="HTTP_200_VALID_XLSX_FILE" for x in out),
         "results":out}
(OUT/"results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
(OUT/"summary.txt").write_text("checked={checked} http_200={http_200} numeric={numeric_crosschecks} xlsx={verified_xlsx}\n".format(**summary),encoding="utf-8")
print("SUPP_SUMMARY",json.dumps({k:v for k,v in summary.items() if k!="results"},ensure_ascii=False),flush=True)
