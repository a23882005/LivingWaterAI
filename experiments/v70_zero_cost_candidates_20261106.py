#!/usr/bin/env python3
"""V70 zero-subscription candidate research only. No production writes, no model changes."""
import csv
import datetime as dt
import hashlib
import html
import io
import json
import math
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("build/v70_zero_cost_candidate_20261106")
OUT.mkdir(parents=True, exist_ok=True)
UTC = dt.datetime.now(dt.timezone.utc)
HEADERS = {
    "User-Agent": "LivingWaterAI-V70-Education-Research/20261106 (one-off evidence)",
    "Accept": "text/csv,application/json,application/vnd.ms-excel,text/html,*/*",
}
RESULTS = []

def grab(url, limit=6_000_000):
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=24) as res:
        data = res.read(limit + 1)
        if len(data) > limit:
            raise ValueError("response-size-limit")
        return data, {
            "http_status": res.status,
            "content_type": res.headers.get("Content-Type", ""),
            "response_sha256": hashlib.sha256(data).hexdigest(),
            "bytes_received": len(data),
        }

def valid_date(d, max_days):
    age = (UTC.date() - d).days
    if age < -1 or age > max_days:
        raise ValueError("observation-stale-or-future:" + str(d) + ":age=" + str(age))
    return age

def add(name, original, candidate, equivalence, url, reader, license_note):
    result = {
        "id": name, "original_v70": original, "candidate": candidate,
        "equivalence": equivalence, "source_url": url,
        "license_note": license_note, "fetched_at_utc": UTC.isoformat(),
        "status": "NOT_RUN",
    }
    try:
        payload = reader(url)
        result.update(payload)
        result.setdefault("status", "NUMERIC_VERIFIED")
    except Exception as exc:
        result.update(status="FAIL", error=type(exc).__name__ + ": " + str(exc)[:250])
    RESULTS.append(result)
    print("V70_ZERO_COST_ROW", json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)

def cboe_vix(url):
    b, meta = grab(url)
    rows = csv.DictReader(io.StringIO(b.decode("utf-8-sig")))
    samples = []
    for r in rows:
        try:
            day = dt.datetime.strptime(r["DATE"].strip(), "%m/%d/%Y").date()
            val = float(r["CLOSE"])
            if math.isfinite(val) and 0 < val < 200:
                samples.append((day, val))
        except (ValueError, TypeError, KeyError):
            continue
    if not samples:
        raise ValueError("VIX-date-close-parser-no-numeric")
    day, value = max(samples)
    age = valid_date(day, 7)
    return dict(meta, value=value, unit="VIX index", observation_date=day.isoformat(),
                age_days=age, sample_count=len(samples))

def eia_wti(url):
    import xlrd
    b, meta = grab(url, 4_000_000)
    book = xlrd.open_workbook(file_contents=b)
    samples = []
    for sheet in book.sheets():
        for i in range(max(0, sheet.nrows - 400), sheet.nrows):
            row = sheet.row_values(i)
            if len(row) < 2:
                continue
            try:
                if isinstance(row[0], float):
                    d = xlrd.xldate_as_datetime(row[0], book.datemode).date()
                else:
                    d = dt.datetime.strptime(str(row[0]).strip(), "%Y-%m-%d").date()
                val = float(row[1])
                if d.year >= 2025 and 1 < val < 500 and math.isfinite(val):
                    samples.append((d, val))
            except (ValueError, TypeError, OverflowError):
                pass
    if not samples:
        raise ValueError("eia-xls-no-price-date")
    d, val = max(samples)
    age = valid_date(d, 16)
    return dict(meta, value=val, unit="USD per barrel / WTI Cushing spot",
                observation_date=d.isoformat(), age_days=age, sample_count=len(samples))

def treasury_realized_vol(url):
    b, meta = grab(url)
    rows = list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("empty-treasury-csv")
    def find(columns):
        for key in rows[0]:
            name = key.lower().strip().replace("_", "").replace("-", "").replace(" ", "")
            if name in columns:
                return key
        raise ValueError("missing-treasury-column:" + str(columns))
    key_date = find(("date", "recorddate"))
    labels = [find(x) for x in (("2year", "2yr"), ("10year", "10yr"), ("30year", "30yr"))]
    samples = []
    for row in rows:
        try:
            d = dt.datetime.strptime(row[key_date].strip(), "%m/%d/%Y").date()
            v = [float(row[k]) for k in labels]
            if all(math.isfinite(x) and 0 < x < 30 for x in v):
                samples.append((d, v))
        except (ValueError, TypeError, KeyError):
            continue
    samples.sort(key=lambda z: z[0])
    if len(samples) < 22:
        raise ValueError("treasury-requires-22-days")
    sample = samples[-22:]
    day = sample[-1][0]
    age = valid_date(day, 7)
    changes = [[(sample[i][1][k] - sample[i-1][1][k]) * 100
                for i in range(1, len(sample))] for k in range(3)]
    sd = [statistics.stdev(c) * math.sqrt(252) for c in changes]
    return dict(meta, observation_date=day.isoformat(), age_days=age,
                value=round(sd[1], 4),
                unit="10Y yield 21-day daily-change realized volatility, bp annualized",
                realized_vol_2y_10y_30y_bp=[round(z, 4) for z in sd],
                sample_count=len(sample), not_move_index=True)

def oecd_cli(url):
    b, meta = grab(url)
    t = b.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(t)))
    if not rows or "OBS_VALUE" not in rows[0] or "TIME_PERIOD" not in rows[0]:
        raise ValueError("OECD-CSV-expected-OBS_VALUE-TIME_PERIOD-not-found:" + str(list(rows[0]) if rows else "none"))
    matches = []
    for row in rows:
        try:
            if row.get("REF_AREA", row.get("Reference area", "USA")) not in ("USA", "United States"):
                continue
            period = str(row["TIME_PERIOD"]).strip()
            if not re.fullmatch(r"20\d\d-(0[1-9]|1[012])", period):
                continue
            val = float(row["OBS_VALUE"])
            if math.isfinite(val) and 10 <= val <= 200:
                matches.append((dt.date.fromisoformat(period + "-01"), val, row))
        except (KeyError, ValueError, TypeError):
            pass
    if not matches:
        raise ValueError("OECD-monthly-CLI-USA-numeric-not-found")
    d, value, row = max(matches, key=lambda z: z[0])
    age = valid_date(d, 110)
    return dict(meta, value=value, observation_date=d.isoformat(), age_days=age,
                unit="OECD CLI index (not US LEI YoY)", sample_count=len(matches),
                series_metadata={k:row[k] for k in ("REF_AREA","FREQ","MEASURE","UNIT_MEASURE") if k in row})

def discover_html(url):
    b, meta = grab(url, 3_000_000)
    t = b.decode("utf-8", errors="replace")
    if len(t) < 800 or "<html" not in t.lower():
        raise ValueError("no-official-html-page")
    links = re.findall(r"""href\s*=\s*["']([^"']+)["']""", t, re.I)
    hrefs = [urllib.parse.urljoin(url, html.unescape(s)) for s in links]
    downloads = sorted(set(s for s in hrefs
                           if re.search(r"\.(csv|xlsx|xls)(?:\?|$)", s, re.I)
                           and (("cmdi" in s.lower()) or ("manufactur" in s.lower())
                                or ("m3" in s.lower()) or ("pce" in s.lower()))))
    return dict(meta, status="SOURCE_PAGE_VERIFIED_NUMERIC_PENDING",
                downloadable_links=downloads[:10], page_title=(re.search(r"<title>(.*?)</title>",t,re.I|re.S).group(1)[:100]
                    if re.search(r"<title>(.*?)</title>",t,re.I|re.S) else "unknown"),
                note="Official source page accessible; exact numeric series not extracted.")

def run_all():
    add("m07", "VIX", "Cboe VIX EOD CSV", "same indicator (licence pending)",
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        cboe_vix, "Free numerical access; Cboe commercial redistribution permission unverified.")
    add("m10", "WTI futures CL=F", "EIA WTI Cushing spot", "different metric",
        "https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls", eia_wti,
        "EIA original government data public-domain style, attribution.")
    add("m12", "MOVE implied bond volatility", "Treasury 10Y realized yield volatility", "different metric",
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
        treasury_realized_vol, "US Treasury own data; no commercial index license for self-calculation.")
    add("m16", "Conference Board LEI YoY", "OECD USA monthly CLI", "different metric",
        "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI/USA.M.LI...AA...H?startPeriod=2025-01&format=csvfilewithlabels",
        oecd_cli, "OECD API free; attribution and source-specific third-party rights check.")
    add("m02", "ICE HY OAS", "New York Fed CMDI", "different metric",
        "https://www.newyorkfed.org/research/policy/cmdi", discover_html,
        "NY Fed own published content, confirm index-specific rights and downloadable raw data.")
    add("m04", "ISM manufacturing PMI", "Census M3 manufacturing order series", "different metric",
        "https://www.census.gov/manufacturing/m3/data/index.html", discover_html,
        "Census government own data, candidate page; numeric pipeline not yet extracted.")
    add("m15", "ISM services PMI", "BEA real services consumer expenditure", "different metric",
        "https://www.bea.gov/data/consumer-spending/main", discover_html,
        "BEA government own data, candidate page; numeric pipeline not yet extracted.")
    (OUT/"results.json").write_text(json.dumps({"schema":"V70_ZEROCOST_CANDIDATE_TEST_v1",
      "run_utc":UTC.isoformat(),"test_only":True,"no_api_keys":True,
      "candidates":RESULTS,
      "numeric_pass":sum(r["status"]=="NUMERIC_VERIFIED" for r in RESULTS),
      "source_only":sum(r["status"]=="SOURCE_PAGE_VERIFIED_NUMERIC_PENDING" for r in RESULTS)
      },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V70_ZERO_COST_SUMMARY",json.dumps({
      "total":len(RESULTS),
      "numeric_pass":sum(r["status"]=="NUMERIC_VERIFIED" for r in RESULTS),
      "source_only":sum(r["status"]=="SOURCE_PAGE_VERIFIED_NUMERIC_PENDING" for r in RESULTS),
      "fail":sum(r["status"]=="FAIL" for r in RESULTS)
    },ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(run_all())
