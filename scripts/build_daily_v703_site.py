# 最後修改日期時間（台灣時間）：2026/10/16 03:37:43｜版本：V70.3.12 build adapter｜檔案名稱：build_daily_v703_site.py
"""LivingWaterAI V70.3 11:00 site builder: verified 18+5 -> family feed v1."""
import argparse
import datetime as dt
import json
import math
import shutil
from pathlib import Path

SUPPLEMENT_IDS = frozenset(("s05", "m06", "m03_qqq", "m03_spy", "m03_vt"))
DUPLICATE_ID = "s03"
EXPECTED_INDEPENDENT = 23
EXPECTED_TRANSPORT = 24
MONTHLY = frozenset(("m04", "m05", "m15", "m18", "m19", "m20"))
SLOW_MONTHLY = frozenset(("m16",))
WEEKLY = frozenset(("m14",))
VALUATION_REFERENCE = frozenset(("m03_qqq", "m03_spy", "m03_vt"))
ACCEPTED_STATUS = frozenset(("OK", "USABLE"))


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _days_old(observation, today):
    d = dt.date.fromisoformat(observation)
    return (today - d).days, d


def _validate(key, item, today):
    problems = []
    if not isinstance(item, dict):
        return [f"{key}: record not object"]
    if item.get("status") not in ACCEPTED_STATUS:
        problems.append(f"{key}: status {item.get('status')}")
    v = item.get("value")
    if isinstance(v, bool) or v is None:
        problems.append(f"{key}: no numeric value")
    else:
        try:
            if not math.isfinite(float(v)):
                problems.append(f"{key}: nonfinite value")
        except (TypeError, ValueError):
            problems.append(f"{key}: invalid numeric value")
    date = item.get("observation_date")
    if not isinstance(date, str):
        problems.append(f"{key}: missing observation_date")
    else:
        try:
            age, obs = _days_old(date, today)
            if age < 0:
                problems.append(f"{key}: future observation")
            elif key in MONTHLY:
                if age > 46:
                    problems.append(f"{key}: monthly data over 46 days")
            elif key in SLOW_MONTHLY:
                if age > 90:
                    problems.append(f"{key}: slow monthly data over 90 days")
            elif key in WEEKLY:
                if age > 14:
                    problems.append(f"{key}: weekly data over 14 days")
            elif key in VALUATION_REFERENCE:
                if age > 90:
                    problems.append(f"{key}: valuation reference over 90 days")
            else:
                workdays = sum((obs + dt.timedelta(days=n)).weekday() < 5 for n in range(1, age + 1))
                if workdays > 4:
                    problems.append(f"{key}: market data over 4 weekdays")
        except ValueError:
            problems.append(f"{key}: invalid observation_date")
    if not str(item.get("source_url") or "").startswith("https://"):
        problems.append(f"{key}: missing HTTPS source")
    if not str(item.get("method") or "").strip():
        problems.append(f"{key}: missing method")
    if item.get("status") == "USABLE" and not str(item.get("detail") or "").strip():
        problems.append(f"{key}: USABLE requires methodology detail")
    return problems


def _lei_history(src, latest):
    records = src.get('lei_history', [])
    if not isinstance(records, list) or len(records) != 3:
        raise ValueError('LEI_HISTORY_BLOCKED: need three explicitly sourced monthly YoY observations')
    records = sorted(records, key=lambda r: r.get('observation_date', ''))
    periods = []
    for r in records:
        date = dt.date.fromisoformat(r['observation_date'])
        if (date.day != 1 or r.get('status') not in ACCEPTED_STATUS
                or isinstance(r.get('value'), bool) or not isinstance(r.get('value'), (int, float))
                or not math.isfinite(r['value']) or not -50 <= r['value'] <= 50
                or not str(r.get('source_url', '')).startswith('https://')
                or not r.get('method')):
            raise ValueError('LEI_HISTORY_BLOCKED: invalid date/value/source/method/status')
        periods.append(date.year * 12 + date.month)
    if periods[1] != periods[0] + 1 or periods[2] != periods[1] + 1:
        raise ValueError('LEI_HISTORY_BLOCKED: months must be consecutive and unique')
    if records[-1]['observation_date'] != latest['observation_date'] or abs(records[-1]['value'] - float(latest['value'])) > 0.000001:
        raise ValueError('LEI_HISTORY_BLOCKED: latest history must agree with m16')
    return records


def build(macro, supplement, html, dest):
    src = _read(macro)
    base = src.get("items")
    if not isinstance(base, dict):
        raise ValueError("18-item collector JSON missing items")
    if len(base) != 19 or set(base).intersection(SUPPLEMENT_IDS) or DUPLICATE_ID not in base:
        raise ValueError("09h contract requires exactly 18 independent + s03 = 19 transport fields")
    extra = _read(supplement)
    records = extra.get("items", extra)
    if not isinstance(records, dict) or set(records) != SUPPLEMENT_IDS:
        raise ValueError("10h supplement requires precisely five keys: " + ",".join(sorted(SUPPLEMENT_IDS)))
    items = dict(base)
    items.update(records)
    if len(items) != EXPECTED_TRANSPORT or len(set(items) - {DUPLICATE_ID}) != EXPECTED_INDEPENDENT:
        raise ValueError("23 independent / 24 transport contract mismatch")
    if items["s03"].get("value") != items["m07"].get("value"):
        raise ValueError("s03 and m07 VIX values mismatch")
    if items["s03"].get("observation_date") != items["m07"].get("observation_date"):
        raise ValueError("s03 and m07 VIX dates mismatch")
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    problems = [problem for key, item in items.items() for problem in _validate(key, item, today)]
    try:
        if not 0 <= float(items["s05"]["value"]) <= 100:
            problems.append("s05: outside 0-100")
    except (ValueError, TypeError, KeyError):
        problems.append("s05: no percentage")
    if problems:
        raise ValueError("QUALITY_GATE_BLOCKED: " + "; ".join(problems))
    lei_history = _lei_history(src, items['m16'])
    template = Path(html).read_text(encoding="utf-8")
    if "V70_macro_latest.json" not in template or "V70.3/family-macro-feed-v1" not in template:
        raise ValueError("V70-3-12.html does not support the expected family feed contract")
    indicators = {
        k: {"value": float(v["value"]), "dataDate": v["observation_date"],
            "source": v["source_url"], "unit": v.get("unit", ""),
            "method": v.get("method", ""), "status": v.get("status", "OK"),
            "detail": v.get("detail", "")}
        for k, v in items.items()
    }
    feed = {"schema": "V70.3/family-macro-feed-v1",
            "asOf": now.isoformat().replace("+00:00", "Z"),
            "verification": {"ready": True, "valid": EXPECTED_TRANSPORT,
                             "totalRequired": EXPECTED_TRANSPORT,
                             "independentIndicators": EXPECTED_INDEPENDENT,
                             "sources": ["09:00/18", "10:00/5"],
                             "usableWithCaveat": sorted(k for k,v in items.items() if v.get("status") == "USABLE")},
            "indicators": indicators, "news": [],
            "leiHistory": lei_history,
            "derived": {"m21": {"value": int(all(r['value'] < 0 for r in lei_history)),
                                "method": "All three consecutive published monthly LEI YoY values < 0",
                                "independentIndicator": False}}}
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    (out / "V70_macro_latest.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(html, out / "index.html")
    (out / "QA.json").write_text(json.dumps({"ready": True, "independent": 23, "transport": 24, "asOf": feed["asOf"], "usableWithCaveat": feed["verification"]["usableWithCaveat"], "leiHistoryReady": True, "leiHistory": lei_history, "m21": feed['derived']['m21']['value']}, indent=2) + "\n", encoding="utf-8")
    print("QUALITY_GATE_PASS: 18+5, independent=23 transport=24, family feed v1")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--macro", default="data/18_macro_verification.json")
    p.add_argument("--supplement", default="data/5_macro_verified.json")
    p.add_argument("--html", default="系統工程/總經V70/V70-3-12.html")
    p.add_argument("--out", default="build/site")
    args = p.parse_args()
    try:
        build(args.macro, args.supplement, args.html, args.out)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc) + " | preserve existing published site")

