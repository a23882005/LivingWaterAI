#!/usr/bin/env python3
"""GitHub Actions non-interactive adapter for the owner's p128.py / V70_Live.html.
Source files remain unchanged. Update only when all core inputs are trustworthy.
"""
import csv
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import re
import runpy
from unittest.mock import patch
import requests

BASE = Path(__file__).resolve().parent.parent
HTML = BASE / "V70_Live.html"
CORE = ("vix", "yield_curve", "hy", "real_y_fred", "fed_val", "pmi", "cpi")

def manual_snapshot(raw: str, today=None) -> dict:
    if not raw:
        raise ValueError("V70_MANUAL_SNAPSHOT absent: publish held for safety")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("V70_MANUAL_SNAPSHOT must be a JSON object")
    asof = dt.date.fromisoformat(obj["as_of"])
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    age = (today-asof).days
    if not 0 <= age <= 45:
        raise ValueError(f"Manual macro snapshot date out of range: {asof}, age={age}")
    limits = {
        "fed_current": (0, 20), "fed_target": (0, 20),
        "pmi": (20, 80), "cpi": (-1, 15),
    }
    clean = {"as_of": str(asof)}
    for key, (lo,hi) in limits.items():
        v = float(obj[key])
        if not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"Invalid manual input {key}: {v}")
        clean[key]=v
    if "mmfi" in obj and obj["mmfi"] is not None:
        v=float(obj["mmfi"])
        if not math.isfinite(v) or not 0 <= v <= 100:
            raise ValueError("Invalid mmfi")
        clean["mmfi"]=v
    return clean

def fred_last(url, **_):
    """Use FRED dated CSV instead of fragile HTML; fail if latest observation stale."""
    series=url.rstrip("/").split("/")[-1]
    if not re.fullmatch(r"[A-Za-z0-9_]+",series):
        return None
    try:
        r=requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                       params={"id":series},timeout=25)
        r.raise_for_status()
        rows=list(csv.DictReader(io.StringIO(r.text)))
        if not rows: return None
        for row in reversed(rows):
            s=row.get(series)
            d=row.get("observation_date") or row.get("DATE")
            if not s or s=="." or not d: continue
            date=dt.date.fromisoformat(d)
            age=(dt.datetime.now(dt.timezone.utc).date()-date).days
            if not 0 <= age <= 21: return None
            v=float(s)
            return v if math.isfinite(v) else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    return None

def replace_value(html, metric_id, val):
    if val is None: return html, False
    if isinstance(val,(int,float)):
        if not math.isfinite(float(val)): raise ValueError(metric_id)
        literal=str(round(float(val),4))
    else:
        raise ValueError(f"Non-numeric {metric_id}")
    rx=re.compile(r"(\{ id: '"+re.escape(metric_id)+r"',[^\\n]*?\\bval: )('[^']*'|\"[^\"]*\"|-?\\d+(?:\\.\\d+)?)")
    # Use actual regex escapes (not double-escaped) for this raw regex.
    rx=re.compile(r"(\{ id: '"+re.escape(metric_id)+r"',[\s\S]*?\bval: )('[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)")
    # Limit to a single config line: prevent accidental replacement across unrelated declarations.
    rx=re.compile(r"(\{ id: '"+re.escape(metric_id)+r"',[^\n]*?\bval: )('[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)")
    new,count=rx.subn(lambda m:m.group(1)+literal,html)
    if count != 1:
        raise RuntimeError(f"Expected exactly one config value for {metric_id}, got {count}")
    return new, True

def apply_updates(html, data):
    ids={
        "m07":"vix", "s03":"vix", "m01":"yield_curve", "m02":"hy",
        "m08":"real_y_fred", "m06":"fed_val",
        "m09":"dxy", "m10":"oil", "m04":"pmi", "m05":"cpi",
        "m03_spy":"pe", "m03_qqq":"pe_qqq", "m03_vt":"pe_vt",
        "s04":"fear", "s05":"mmfi",
    }
    changed=[]
    for metric,key in ids.items():
        if data.get(key) is None: continue
        html,_=replace_value(html,metric,data[key])
        changed.append(metric)
    return html,changed

def main():
    snap=manual_snapshot(os.environ.get("V70_MANUAL_SNAPSHOT",""))
    if not HTML.exists(): raise FileNotFoundError(HTML)
    original=HTML.read_text(encoding="utf-8")
    if "投資戰情室 V70.2" not in original or "</html>" not in original:
        raise RuntimeError("Unexpected V70 template")
    with patch("os.system",return_value=0), patch("time.sleep",return_value=None):
        ns=runpy.run_path(str(BASE/"p128.py"),run_name="livingwater_data_provider")
    fn=ns["get_all_data"]
    g=fn.__globals__
    def noninteractive():
        fed=round((snap["fed_target"]-snap["fed_current"])/0.25,1)
        return {"fed":(fed,"Manual validated snapshot"),
                "mmfi":snap.get("mmfi"),"pmi":snap["pmi"],"cpi":snap["cpi"]}
    g["get_selenium_data"]=noninteractive
    g["get_fred_value"]=fred_last
    data=fn()
    missing=[key for key in CORE if data.get(key) is None]
    if missing:
        raise RuntimeError("Essential real-world data missing; kept prior HTML: "+", ".join(missing))
    result,changed=apply_updates(original,data)
    if len(changed)<10:
        raise RuntimeError(f"Only {len(changed)} validated fields. Publish withheld.")
    if result.count("投資戰情室 V70.2") < 1 or result.count("</html>")!=1:
        raise RuntimeError("Output format check failed")
    if result != original:
        temp=HTML.with_suffix(".html.tmp")
        temp.write_text(result,encoding="utf-8")
        temp.replace(HTML)
    print(json.dumps({"status":"UPDATED" if result!=original else "UNCHANGED",
                      "fields":changed,"manual_as_of":snap["as_of"]},
                      ensure_ascii=False))
if __name__=="__main__":
    main()
