# 最後修改日期時間（台灣時間）：2026/10/17 10:31｜版本：V70-3-27 build adapter v2｜檔案名稱：build_daily_v703_site.py
"""Build the V70-3-27 feed from 18 core records and 9 supplement inputs."""
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

SUPPLEMENT_IDS = frozenset((
    "s05", "m06_rate", "m06_inf", "m06_rstar", "m06_taylor_infl",
    "m06_output_gap", "m03_qqq", "m03_spy", "m03_vt",
))
DUPLICATE_ID = "s03"
MACRO_CONFIG_IDS = (
    "m07", "m01", "m06", "m06_rate", "m06_inf", "m06_rstar",
    "m06_taylor_infl", "m06_output_gap", "m08", "m03_qqq", "m03_spy",
    "m03_vt", "m02", "m04", "m05", "m09", "m10", "s05", "m12",
    "m13", "m17", "m14", "m15", "m16", "m18", "m19", "m20",
)
M06_COMPONENTS = ("m06_rate", "m06_inf", "m06_rstar", "m06_taylor_infl", "m06_output_gap")
M06_SUPPORT_ONLY = frozenset(M06_COMPONENTS)
SCORING_IDS = frozenset(set(MACRO_CONFIG_IDS) - M06_SUPPORT_ONLY)
MONTHLY = frozenset(("m04", "m05", "m15", "m18", "m19", "m20", "m06_inf", "m06_taylor_infl", "m06_output_gap"))
SLOW_MONTHLY = frozenset(("m16", "m06_rstar"))
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
    value = item.get("value")
    if isinstance(value, bool) or value is None:
        problems.append(f"{key}: no numeric value")
    else:
        try:
            if not math.isfinite(float(value)):
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
    records = src.get("lei_history", [])
    if not isinstance(records, list) or len(records) != 3:
        raise ValueError("LEI_HISTORY_BLOCKED: need three explicitly sourced monthly YoY observations")
    records = sorted(records, key=lambda row: row.get("observation_date", ""))
    periods = []
    for row in records:
        date = dt.date.fromisoformat(row["observation_date"])
        if (date.day != 1 or row.get("status") not in ACCEPTED_STATUS
                or isinstance(row.get("value"), bool) or not isinstance(row.get("value"), (int, float))
                or not math.isfinite(row["value"]) or not -50 <= row["value"] <= 50
                or not str(row.get("source_url", "")).startswith("https://") or not row.get("method")):
            raise ValueError("LEI_HISTORY_BLOCKED: invalid date/value/source/method/status")
        periods.append(date.year * 12 + date.month)
    if periods[1] != periods[0] + 1 or periods[2] != periods[1] + 1:
        raise ValueError("LEI_HISTORY_BLOCKED: months must be consecutive and unique")
    if records[-1]["observation_date"] != latest["observation_date"] or abs(records[-1]["value"] - float(latest["value"])) > 1e-6:
        raise ValueError("LEI_HISTORY_BLOCKED: latest history must agree with m16")
    return records


def _git_blob_sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _normalize(item):
    return {
        "value": item.get("value"), "dataDate": item.get("observation_date"),
        "source": item.get("source_url", ""), "unit": item.get("unit", ""),
        "method": item.get("method", ""), "status": item.get("status", "MISSING"),
        "detail": item.get("detail", ""),
    }


def build(macro_path, supplement_path, html_path, dest):
    src = _read(macro_path)
    base = src.get("items")
    if not isinstance(base, dict) or len(base) != 19 or DUPLICATE_ID not in base:
        raise ValueError("09h contract requires exactly 18 core indicators plus duplicate s03 = 19 fields")
    if set(base).intersection(SUPPLEMENT_IDS) or "m06" in base:
        raise ValueError("09h core data contains a supplement/derived key")
    extra = _read(supplement_path)
    records = extra.get("items", extra)
    if not isinstance(records, dict) or set(records) != SUPPLEMENT_IDS:
        raise ValueError("10h contract requires precisely nine raw supplement keys: " + ",".join(sorted(SUPPLEMENT_IDS)))
    if base["s03"].get("value") != base["m07"].get("value") or base["s03"].get("observation_date") != base["m07"].get("observation_date"):
        raise ValueError("s03 and m07 VIX value/date mismatch")

    now = dt.datetime.now(dt.timezone.utc)
    taipei = dt.timezone(dt.timedelta(hours=8))
    today = now.astimezone(taipei).date()
    inputs = dict(base)
    inputs.update(records)
    m06_children = [inputs[key] for key in M06_COMPONENTS]
    m06_ready = all(
        isinstance(row, dict) and row.get("status") in ACCEPTED_STATUS
        and row.get("value") is not None and math.isfinite(float(row["value"]))
        and isinstance(row.get("observation_date"), str)
        and str(row.get("source_url") or "").startswith("https://")
        for row in m06_children
    )
    if m06_ready:
        fed, inflation, rstar, taylor_inflation, output_gap = (float(row["value"]) for row in m06_children)
        actual_gap = (fed - inflation) - rstar
        taylor_gap = 0.5 * (taylor_inflation - 2.0) + 0.5 * output_gap
        m06_value = actual_gap - taylor_gap
        m06_status = "USABLE" if any(row.get("status") == "USABLE" for row in m06_children) else "OK"
        m06_date = min(row["observation_date"] for row in m06_children)
        m06_source = " | ".join(dict.fromkeys(row["source_url"] for row in m06_children))
        m06_detail = "V2=(Fed中點−未來12M通膨預期−HLW r*)−[0.5×(Taylor通膨−2)+0.5×實際GDP/潛在GDP缺口]；" + "; ".join(
            f"{key}={inputs[key]['value']}@{inputs[key]['observation_date']}" for key in M06_COMPONENTS
        )
    else:
        m06_value, m06_status, m06_date = None, "MISSING", None
        m06_source = " | ".join(dict.fromkeys(str(row.get("source_url", "")) for row in m06_children if isinstance(row, dict)))
        m06_detail = "m06 requires all five verified raw inputs; missing/invalid component"
    inputs["m06"] = {
        "value": m06_value, "observation_date": m06_date, "source_url": m06_source,
        "unit": "%pt", "method": "V70-3-27 m06 V2 derived from five dated inputs",
        "status": m06_status, "detail": m06_detail,
    }

    if inputs["m16"].get("status") not in ACCEPTED_STATUS:
        raise ValueError("LEI_HISTORY_BLOCKED: m16 must be verified before deriving m21")
    lei_history = _lei_history(src, inputs["m16"])
    calc_problems = []
    missing = []
    valid_config = set()
    scoring_valid = set()
    for key in MACRO_CONFIG_IDS:
        row = inputs.get(key)
        if key in VALUATION_REFERENCE and isinstance(row, dict) and row.get("status") == "MISSING" and row.get("value") is None:
            missing.append(key)
            continue
        issues = _validate(key, row, today)
        if issues:
            calc_problems.extend(issues)
            continue
        valid_config.add(key)
        if key in SCORING_IDS:
            scoring_valid.add(key)
    # The non-scoring transport rows still need provenance and freshness QA.
    for key, row in inputs.items():
        if key in MACRO_CONFIG_IDS:
            continue
        issues = _validate(key, row, today)
        if issues:
            calc_problems.extend(issues)
    s05_value = inputs["s05"].get("value")
    if s05_value is None or not 0 <= float(s05_value) <= 100:
        calc_problems.append("s05: outside 0-100 or missing percentage")

    indicators = {key: _normalize(row) for key, row in inputs.items()}
    feed = {
        "schema": "V70.3/family-macro-feed-v2",
        "asOf": now.isoformat().replace("+00:00", "Z"),
        "verification": {
            "ready": not calc_problems and not missing and len(valid_config) == 27 and len(scoring_valid) == 22,
            "valid": len(valid_config), "totalRequired": 27,
            "independentIndicators": 26,
            "sources": ["09:00/18", "10:00/9"],
            "usableWithCaveat": sorted(key for key, row in inputs.items() if row.get("status") == "USABLE"),
            "transportFields": 27, "requiredScoringIndicators": 22,
            "requiredScoringIndicatorsValidated": len(scoring_valid),
            "missing": sorted(missing), "problems": calc_problems,
            "transportIndicators": len(indicators),
        },
        "indicators": indicators, "news": [], "leiHistory": lei_history,
        "derived": {"m21": {
            "value": int(all(row["value"] < 0 for row in lei_history)),
            "method": "All three consecutive published monthly LEI YoY values < 0",
            "independentIndicator": False,
        }},
        "dataUpdatedAt": now.astimezone(taipei).isoformat(timespec="seconds"),
        "sourceSnapshot": {
            "macro18": _git_blob_sha(macro_path), "macro9": _git_blob_sha(supplement_path),
            "macro18GeneratedAt": src.get("generated_at"), "macro9GeneratedAt": extra.get("generated_at"),
        },
    }
    template = Path(html_path).read_text(encoding="utf-8")
    if "V70-3-27" not in template or "v70-embedded-feed" not in template:
        raise ValueError("HTML is not the canonical V70-3-27 template")
    embedded = json.dumps(feed, ensure_ascii=False, indent=2)
    updated_html, count = re.subn(
        r'(<script id="v70-embedded-feed" type="application/json">\s*)\{.*?\}(\s*</script>)',
        lambda match: match.group(1) + embedded + match.group(2), template, count=1, flags=re.S,
    )
    if count != 1:
        raise ValueError("Could not replace the embedded feed")
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    (out / "V70_macro_latest.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(updated_html, encoding="utf-8")
    qa = {"ready": feed["verification"]["ready"], "independent": 26, "transport": 29,
          "requiredScoring": 22, "requiredScoringValidated": len(scoring_valid),
          "asOf": feed["asOf"], "missing": sorted(missing), "problems": calc_problems}
    (out / "QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("QUALITY_GATE_" + ("PASS" if qa["ready"] else "BLOCKED") + ": " + json.dumps(qa, ensure_ascii=False))
    return qa["ready"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro", default="data/18_macro_verification.json")
    parser.add_argument("--supplement", default="data/9_macro_supplement_verified.json")
    parser.add_argument("--html", default="系統工程/總經V70/V70-3-27.html")
    parser.add_argument("--out", default="build/site")
    args = parser.parse_args()
    try:
        build(args.macro, args.supplement, args.html, args.out)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc) + " | preserve existing published site")
