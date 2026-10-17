# 最後修改日期時間（台灣時間）：2026/10/17 13:56｜版本：V70-3-27 build adapter v3.4（HTML五機構SSR）｜檔案名稱：build_daily_v703_site.py
"""Build the V70-3-27 feed from 18 core records and 8 supplement inputs."""
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import re
import shutil
from pathlib import Path

SUPPLEMENT_IDS = frozenset((
    "s05", "m06_rate", "m06_inf", "m06_rstar",
    "m06_output_gap", "m03_qqq", "m03_spy", "m03_vt",
))
DUPLICATE_ID = "s03"
MACRO_CONFIG_IDS = (
    "m07", "m01", "m06", "m06_rate", "m06_inf", "m06_rstar",
    "m06_output_gap", "m08", "m03_qqq", "m03_spy",
    "m03_vt", "m02", "m04", "m05", "m09", "m10", "s05", "m12",
    "m13", "m17", "m14", "m15", "m16", "m18", "m19", "m20",
)
M06_COMPONENTS = ("m06_rate", "m06_inf", "m06_rstar", "m06_output_gap")
M06_SUPPORT_ONLY = frozenset(M06_COMPONENTS)
SCORING_IDS = frozenset(set(MACRO_CONFIG_IDS) - M06_SUPPORT_ONLY)
MONTHLY = frozenset(("m04", "m05", "m15", "m18", "m19", "m20", "m06_inf"))
QUARTERLY = frozenset(("m06_rstar", "m06_output_gap", "m06"))
SLOW_MONTHLY = frozenset(("m16",))
WEEKLY = frozenset(("m14",))
VALUATION_REFERENCE = frozenset(("m03_qqq", "m03_spy", "m03_vt"))
ACCEPTED_STATUS = frozenset(("OK", "USABLE"))
CANDIDATE_STATUSES = frozenset(("FOUND", "NOT_FOUND", "BLOCKED", "METRIC_MISMATCH"))


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
            elif key in QUARTERLY:
                if obs.month not in (3, 6, 9, 12) or obs != dt.date(obs.year, obs.month, (dt.date(obs.year + (obs.month == 12), obs.month % 12 + 1, 1) - dt.timedelta(days=1)).day):
                    problems.append(f"{key}: quarterly observation must use quarter-end date")
                if age > 150:
                    problems.append(f"{key}: quarterly data over 150 days")
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


def _validate_candidate_checks(key, item):
    """Require four completed candidate-source checks on every 10:00 supplement row."""
    problems = []
    checks = item.get("candidate_checks") if isinstance(item, dict) else None
    if not isinstance(checks, list) or len(checks) != 4:
        return [f"{key}: candidate_checks must contain exactly four source checks"]
    for index, check in enumerate(checks, start=1):
        prefix = f"{key}: candidate_checks[{index}]"
        if not isinstance(check, dict):
            problems.append(f"{prefix} must be an object")
            continue
        if not str(check.get("site") or "").strip():
            problems.append(f"{prefix} missing site")
        if not str(check.get("url") or "").startswith("https://"):
            problems.append(f"{prefix} missing HTTPS URL")
        if not str(check.get("metric_or_horizon") or "").strip():
            problems.append(f"{prefix} missing metric_or_horizon")
        if check.get("status") not in CANDIDATE_STATUSES:
            problems.append(f"{prefix} status must be a completed candidate check")
        if not str(check.get("checked_at") or "").strip():
            problems.append(f"{prefix} missing checked_at")
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


def _normalize(item, indicator_id=None):
    normalized = {
        "value": item.get("value"), "dataDate": item.get("observation_date"),
        "source": item.get("source_url", ""), "unit": item.get("unit", ""),
        "method": item.get("method", ""), "status": item.get("status", "MISSING"),
        "detail": item.get("detail", ""),
    }
    if isinstance(item.get("candidate_checks"), list):
        normalized["candidateChecks"] = [dict(check) if isinstance(check, dict) else check
                                         for check in item["candidate_checks"]]
    if indicator_id in VALUATION_REFERENCE:
        # Carry independently checked quoted Forward/FY1 evidence from the eight-item
        # audit into the public feed. Keep the original check timestamp; do not
        # invent a new "verified now" time merely because a page was rebuilt.
        hits = []
        for check in item.get("candidate_checks", []):
            if (not isinstance(check, dict) or check.get("status") != "FOUND"
                    or check.get("url") != item.get("source_url")):
                continue
            label = str(check.get("metric_or_horizon") or "")
            if not re.search(r"forward|fy\s?1|next\s?12\s?months|未來12m|預估本益比", label, re.I):
                continue
            if re.search(r"\bTTM\b", label, re.I):
                continue
            try:
                same_value = math.isfinite(float(check["value"])) and abs(
                    float(check["value"]) - float(item["value"])) < 1e-9
                dt.datetime.fromisoformat(str(check["checked_at"]))
            except (KeyError, ValueError, TypeError):
                continue
            if same_value:
                hits.append(check)
        if hits:
            selected = max(hits, key=lambda r: r["checked_at"])
            normalized["lastVerifiedAt"] = selected["checked_at"]
            normalized["sourceEvidence"] = {
                "label": selected["metric_or_horizon"],
                "value": selected["value"],
                "source_url": selected["url"],
            }
    if item.get("retrieval_time") is not None:
        normalized["retrievalTime"] = item["retrieval_time"]
    if item.get("publication_date") is not None:
        normalized["publicationDate"] = item["publication_date"]
    if item.get("vintage") is not None:
        normalized["vintage"] = item["vintage"]
    return normalized



def _wallstreet_five_verified(path, today):
    """Validate same-horizon, source-traced factual forecasts; not a scoring input."""
    forecast = _read(path)
    if forecast.get("schema") != "V70.3/wallstreet-five-forecast-v1":
        raise ValueError("WALLSTREET5: wrong source schema")
    ids = ("goldman", "jpm", "morgan", "bofa", "ubs")
    rows = forecast.get("forecasts")
    if not isinstance(rows, list) or [r.get("firm_id") for r in rows] != list(ids):
        raise ValueError("WALLSTREET5: must have exactly five fixed, ordered firms")
    checked = dt.date.fromisoformat(forecast["as_of_date"])
    if checked > today or checked < dt.date(2026, 1, 1):
        raise ValueError("WALLSTREET5: invalid verification date")
    cross = dt.date.fromisoformat(forecast["cross_check_date"])
    if cross > checked or not str(forecast.get("cross_check_source", "")).startswith("https://"):
        raise ValueError("WALLSTREET5: cross-check source/date invalid")
    for row in rows:
        if not isinstance(row.get("target"), int) or isinstance(row["target"], bool) or not 1000 <= row["target"] <= 20000:
            raise ValueError("WALLSTREET5: nonnumeric or implausible target " + row["firm_id"])
        when = dt.date.fromisoformat(row["publication_date"])
        horizon = dt.date.fromisoformat(row["horizon_end_date"])
        if when > checked or horizon < when or row["horizon_end_date"] != forecast["horizon_end_date"]:
            raise ValueError("WALLSTREET5: date/horizon mismatch " + row["firm_id"])
        if not str(row.get("source_url", "")).startswith("https://"):
            raise ValueError("WALLSTREET5: missing public source " + row["firm_id"])
        if not 10 <= len(str(row.get("summary") or "")) <= 280:
            raise ValueError("WALLSTREET5: requires original concise summary " + row["firm_id"])
    return forecast


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
        raise ValueError("10h contract requires precisely eight raw supplement keys: " + ",".join(sorted(SUPPLEMENT_IDS)))
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
        fed, inflation, rstar, output_gap = (float(row["value"]) for row in m06_children)
        actual_gap = (fed - inflation) - rstar
        taylor_gap = 0.5 * (inflation - 2.0) + 0.5 * output_gap
        m06_value = actual_gap - taylor_gap
        m06_status = "USABLE" if any(row.get("status") == "USABLE" for row in m06_children) else "OK"
        m06_date = min(row["observation_date"] for row in m06_children)
        m06_source = " | ".join(dict.fromkeys(row["source_url"] for row in m06_children))
        m06_detail = "V3=(Fed中點−未來12M通膨預期−HLW r*)−[0.5×(同一未來12M通膨預期−2)+0.5×實際GDP/潛在GDP缺口]；" + "; ".join(
            f"{key}={inputs[key]['value']}@{inputs[key]['observation_date']}" for key in M06_COMPONENTS
        )
    else:
        m06_value, m06_status, m06_date = None, "MISSING", None
        m06_source = " | ".join(dict.fromkeys(str(row.get("source_url", "")) for row in m06_children if isinstance(row, dict)))
        m06_detail = "m06 requires all four verified raw inputs; missing/invalid component"
    inputs["m06"] = {
        "value": m06_value, "observation_date": m06_date, "source_url": m06_source,
        "unit": "%pt", "method": "V70-3-27 m06 V3 derived from four dated inputs",
        "status": m06_status, "detail": m06_detail,
    }

    if inputs["m16"].get("status") not in ACCEPTED_STATUS:
        raise ValueError("LEI_HISTORY_BLOCKED: m16 must be verified before deriving m21")
    lei_history = _lei_history(src, inputs["m16"])
    calc_problems = []
    for key in SUPPLEMENT_IDS:
        calc_problems.extend(_validate_candidate_checks(key, inputs[key]))
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

    indicators = {key: _normalize(row, key) for key, row in inputs.items()}
    for key in VALUATION_REFERENCE:
        row = indicators.get(key, {})
        if not row.get("lastVerifiedAt") or not row.get("sourceEvidence"):
            calc_problems.append(key + ": Forward/FY1 evidence does not match verified candidate source/value")
    feed = {
        "schema": "V70.3/family-macro-feed-v3",
        "asOf": now.isoformat().replace("+00:00", "Z"),
        "verification": {
            "ready": not calc_problems and not missing and len(valid_config) == 26 and len(scoring_valid) == 22,
            "valid": len(valid_config), "totalRequired": 26,
            "independentIndicators": 25,
            "sources": ["09:00/18", "10:00/8"],
            "usableWithCaveat": sorted(key for key, row in inputs.items() if row.get("status") == "USABLE"),
            "transportFields": 26, "requiredScoringIndicators": 22,
            "requiredScoringIndicatorsValidated": len(scoring_valid),
            "missing": sorted(missing), "problems": calc_problems,
            "transportIndicators": len(indicators),
        },
        "indicators": indicators, "news": [], "leiHistory": lei_history,
        "wallStreetFive": _wallstreet_five_verified("data/wallstreet5_forecasts.json", today),
        "derived": {"m21": {
            "value": int(all(row["value"] < 0 for row in lei_history)),
            "method": "All three consecutive published monthly LEI YoY values < 0",
            "independentIndicator": False,
        }},
        "dataUpdatedAt": now.astimezone(taipei).isoformat(timespec="seconds"),
        "sourceSnapshot": {
            "macro18": _git_blob_sha(macro_path), "macro8": _git_blob_sha(supplement_path),
            "wallstreet5": _git_blob_sha("data/wallstreet5_forecasts.json"),
            "macro18GeneratedAt": src.get("generated_at"), "macro8GeneratedAt": extra.get("generated_at"),
        },
    }
    if len(feed["wallStreetFive"]["forecasts"]) != 5:
        raise ValueError("WALLSTREET5: five firms absent before HTML build")
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
    # Render forecast facts server-side so even mobile browsers with no JavaScript
    # show the same five audited year-end values as the JSON build artifact.
    bank_rows = feed["wallStreetFive"]["forecasts"]
    lines = []
    for row in bank_rows:
        def cell(value):
            return '<td class="border border-slate-600 p-2 align-top">' + html.escape(str(value)) + '</td>'
        source_url = html.escape(row["source_url"], quote=True)
        source = (
            '<td class="border border-slate-600 p-2 align-top"><a rel="noopener noreferrer" '
            'target="_blank" class="text-cyan-200 underline" href="' + source_url + '">'
            + html.escape(row["source_type"]) + '</a></td>'
        )
        lines.append('<tr>' + ''.join([
            cell(row["firm_name"]), cell(row["publication_date"]),
            cell(row["horizon"]), cell(f'{row["target"]:,}'),
            cell(row["summary"]), source,
            cell('公開數字／自寫摘要／來源連結；全文未授權'),
        ]) + '</tr>')
    updated_html, bank_count = re.subn(
        r'(<tbody id="v703-wallstreet-rows">).*?(</tbody>)',
        lambda m: m.group(1) + '\n' + '\n'.join(lines) + '\n' + m.group(2),
        updated_html, count=1, flags=re.S,
    )
    if bank_count != 1 or updated_html.count('公開數字／自寫摘要／來源連結；全文未授權') != 5:
        raise ValueError("WALLSTREET5: HTML table render failed")
    updated_html = updated_html.replace(
        "資料查核日：等待建置｜統一比較 2026 年底目標；各機構原始發布日不同。",
        "資料查核日：" + html.escape(feed["wallStreetFive"]["as_of_date"])
        + "｜路透社彙整交叉核對：" + html.escape(feed["wallStreetFive"]["cross_check_date"])
        + "｜統一比較 2026 年底目標（不同機構原始發布日不同）。",
    )
    if "資料查核日：等待建置" in updated_html or 'id="v703-wallstreet-rows"' not in updated_html:
        raise ValueError("WALLSTREET5: placeholder still present after build")
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    (out / "V70_macro_latest.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(updated_html, encoding="utf-8")
    qa = {"ready": feed["verification"]["ready"], "independent": 25, "transport": 28,
          "requiredScoring": 22, "requiredScoringValidated": len(scoring_valid),
          "asOf": feed["asOf"], "missing": sorted(missing), "problems": calc_problems}
    (out / "QA.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("QUALITY_GATE_" + ("PASS" if qa["ready"] else "BLOCKED") + ": " + json.dumps(qa, ensure_ascii=False))
    return qa["ready"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--macro", default="data/18_macro_verification.json")
    parser.add_argument("--supplement", default="data/8_macro_supplement_verified.json")
    parser.add_argument("--html", default="系統工程/總經V70/V70-3-27.html")
    parser.add_argument("--out", default="build/site")
    args = parser.parse_args()
    try:
        build(args.macro, args.supplement, args.html, args.out)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc) + " | preserve existing published site")
