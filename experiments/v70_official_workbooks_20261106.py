#!/usr/bin/env python3
"""Read-only inspect official Census/BEA XLSX structures; no assumptions or data publishing."""
import datetime as dt
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path
import openpyxl

OUT=Path("build/v70_official_workbook_verification_20261106")
OUT.mkdir(parents=True,exist_ok=True)
targets=[
 ("m04_census_new_orders","https://www.census.gov/manufacturing/m3/prel/historical_data/histshts/naics/naicsnop.xlsx"),
 ("m15_bea_services","https://apps.bea.gov/national/Release/XLS/Survey/Section2All_xls.xlsx")
]
results=[]
for name,url in targets:
 row={"name":name,"url":url,"retrieved_at":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"PENDING"}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"LivingWaterAI-V70-OneOff-Research/20261106","Accept":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"})
  with urllib.request.urlopen(req,timeout=45) as resp:
   payload=resp.read(35_000_001)
   if len(payload)>35_000_000:raise ValueError("workbook-larger-than-35MB")
   row.update(http_status=resp.status,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),content_type=resp.headers.get("content-type"))
  wb=openpyxl.load_workbook(io.BytesIO(payload),data_only=True,read_only=True)
  row["sheet_count"]=len(wb.sheetnames)
  row["sheet_names"]=wb.sheetnames[:100]
  row["sheets"]=[]
  for ws in wb.worksheets[:10]:
   summary={"sheet":ws.title,"max_row":ws.max_row,"max_column":ws.max_column,"head":[],"matching_rows":[]}
   for ix,values in enumerate(ws.iter_rows(min_row=1,max_row=min(ws.max_row or 100,180),values_only=True),start=1):
    cells=[str(v)[:85] if v is not None else "" for v in values[:12]]
    if ix<=8:summary["head"].append([ix]+cells)
    matched=" ".join(cells).lower()
    if any(k in matched for k in ("manufacturing","new orders","services","2.8.6","nipa table 2.8.6")):
     if len(summary["matching_rows"])<12:summary["matching_rows"].append([ix]+cells)
   row["sheets"].append(summary)
  row["status"]="XLSX_STRUCTURAL_PASS_NUMERIC_PENDING"

  # Read exact documented table codes; do not confuse these with ISM PMI.
  if name=="m04_census_new_orders":
   ws=wb["m3-outp-nop"]
   observations=[]
   for values in ws.iter_rows(values_only=True):
    if str(values[0]).strip()!="AMTMNO":continue
    try:year=int(values[1])
    except (ValueError,TypeError):continue
    for month,val in enumerate(values[2:14],start=1):
     if isinstance(val,(int,float)) and val>0 and 1900<=year<=2030:
      observations.append((dt.date(year,month,1),float(val)))
   if observations:
    d,v=max(observations)
    row.update(status="OFFICIAL_NUMERIC_PASS",series="AMTMNO",unit="millions of USD, seasonally adjusted",
      latest_observation=d.isoformat(),value=v,sample_count=len(observations),
      recent_observations=[{"date":x.isoformat(),"value":y} for x,y in sorted(observations)[-4:]],
      note="US Census total manufacturing new orders, NOT ISM manufacturing PMI")
  if name=="m15_bea_services":
   ws=wb["T20806-M"]
   header=next(ws.iter_rows(min_row=8,max_row=8,values_only=True))
   row["service_header_tail"]=[str(x) for x in header[-18:]]
   row["service_metadata"]=[str(x[0]) for x in ws.iter_rows(min_row=1,max_row=5,values_only=True)]
   observations=[]
   for values in ws.iter_rows(min_row=9,max_row=min(ws.max_row,100),values_only=True):
    if str(values[1]).strip().lower()!="services" or str(values[2]).strip()!="DSERRX":
     continue
    for i in range(3,min(len(values),len(header))):
     val=values[i]
     if not isinstance(val,(int,float)) or val<=0:continue
     stamp=str(header[i]).strip()
     m=re.search(r"(20\d\d)[-]?M?(0?[1-9]|1[012])$",stamp,re.I) if stamp else None
     if not m:
      m=re.search(r"^(20\d\d)[-/](0?[1-9]|1[012])$",stamp)
     if m:
      d=dt.date(int(m.group(1)),int(m.group(2)),1)
      observations.append((d,float(val)))
    break
   if observations:
    observations.sort()
    d,v=observations[-1]
    prior=observations[-2][1] if len(observations)>=2 else None
    row.update(status="OFFICIAL_NUMERIC_PASS",series="DSERRX",unit="millions of chained 2017 USD, SAAR",
      latest_observation=d.isoformat(),value=v,sample_count=len(observations),
      monthly_change_pct=round((v/prior-1)*100,6) if prior else None,
      recent_observations=[{"date":x.isoformat(),"value":y} for x,y in observations[-4:]],
      note="BEA Table 2.8.6 real PCE services, NOT ISM services PMI")

 except Exception as e:
  row.update(status="ERROR",error=type(e).__name__+": "+str(e)[:330])
 results.append(row)
 print("V70_OFFICIAL_XLSX",json.dumps(row,ensure_ascii=False)[:14000],flush=True)
(OUT/"results.json").write_text(json.dumps({"schema":"V70_OFFICIAL_XLSX_DISCOVERY_v1","results":results},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("V70_OFFICIAL_XLSX_SUMMARY",json.dumps({r["name"]:r["status"] for r in results}),flush=True)
