"""C Work2 — B benchmark reader + Data Quality Gate.

This module is an integration/read layer only. It must not calculate Work3 risk/performance
metrics or Work4 portfolio look-through. B remains the benchmark truth owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from .xlsx_minimal_reader import WorkbookData, read_xlsx, json_safe
except ImportError:  # direct execution
    from xlsx_minimal_reader import WorkbookData, read_xlsx, json_safe

WORK2_VERSION = "C-W2-v1.0.1"
WORK1_CONTRACT_VERSION = "C-W1-v1.0.1"
FORMAL_WORKBOOK_NAME = "標的績效基準資料.xlsx"
FORMAL_DRIVE_FILE_ID = "1vbaPznrzrDwZ17AeLXSLJErMrXwxPl1-"
CURRENT_CLOSEOUT_SHA256 = "f639f5b46b7ff0c7ab2884a0ce01739d852c94f8e383f1966463d48178a77b02"
SOURCE_ID = "SRC_B_WORKBOOK"

SHEET_ROLES = {
    "Sheet1_標的績效基準資料": "PERFORMANCE_RISK_BASELINE",
    "Sheet2_來源計算代理規則": "SOURCE_CALC_PROXY_RULES",
    "Sheet3_曝險度項目定義": "EXPOSURE_TAXONOMY",
    "Sheet4_標的曝險基準資料": "EXPOSURE_PRIMITIVES",
}

ALLOWED_QUALITY_FLAGS = {
    "OFFICIAL_DIRECT", "OFFICIAL_DERIVED", "RECONCILED_THIRD_PARTY",
    "FALLBACK_USED", "PROXY_USED", "SHORT_HISTORY", "STALE", "INSUFFICIENT",
    "TAX_CLASSIFICATION_UNKNOWN", "PERSONAL_TAX_NOT_MODELED", "UNKNOWN",
}
NATIVE_SENTINELS = {"KNOWN", "UNKNOWN", "NOT_APPLICABLE", "PENDING_DERIVATION", "NOT_RECOVERED"}
C_VALUE_STATES = {"KNOWN", "NONE", "UNKNOWN", "NOT_APPLICABLE"}
DATA_QUALITY_STATES = {"OK", "FALLBACK_USED", "INSUFFICIENT", "UNKNOWN"}
FRESHNESS_STATES = {"FRESH", "STALE", "UNKNOWN", "NOT_APPLICABLE"}

CORE_RULE_IDS = {
    "W2-MET-010",
    "W2-PRX-001", "W2-PRX-002", "W2-PRX-003",
    "W2-DQ-001", "W2-DQ-002", "W2-DQ-003", "W2-DQ-004", "W2-DQ-005", "W2-DQ-007",
}

EXPOSURE_ID_RE = re.compile(r"^[A-Z0-9_]+(?:\.[A-Z0-9_]+)*$")

# Canonical aliases only; no calculations occur here.
SHEET1_METRICS: Dict[str, Tuple[str, str, str]] = {
    "官方5Y年化報酬": ("official_5y_annualized_return", "ratio", "OFFICIAL"),
    "官方10Y年化報酬": ("official_10y_annualized_return", "ratio", "OFFICIAL"),
    "官方成立以來年化報酬": ("official_inception_annualized_return", "ratio", "OFFICIAL"),
    "官方績效截至": ("official_performance_as_of", "date", "OFFICIAL_DATE"),
    "稅後含息長期中央CAGR": ("tax_after_total_return_central_cagr", "ratio", "RISK"),
    "近7年最大回撤": ("max_drawdown_7y", "ratio", "RISK"),
    "近10年最大回撤": ("max_drawdown_10y", "ratio", "RISK"),
    "近15年最大回撤": ("max_drawdown_15y", "ratio", "RISK"),
    "成立以來最大回撤": ("max_drawdown_inception", "ratio", "RISK"),
    "最嚴重回撤回復期": ("worst_drawdown_recovery_period", "duration_text", "RISK"),
    "Sharpe成立以來": ("sharpe_inception", "ratio", "RISK"),
    "Sortino成立以來": ("sortino_inception", "ratio", "RISK"),
    "Calmar成立以來": ("calmar_inception", "ratio", "RISK"),
    "最嚴重回撤高點日": ("worst_drawdown_peak_date", "date", "RISK_DATE"),
    "最嚴重回撤谷底日": ("worst_drawdown_trough_date", "date", "RISK_DATE"),
    "最嚴重回撤回復日": ("worst_drawdown_recovery_date", "date", "RISK_DATE"),
    "Sharpe近7年": ("sharpe_7y", "ratio", "RISK"),
    "Sharpe近10年": ("sharpe_10y", "ratio", "RISK"),
    "Sharpe近15年": ("sharpe_15y", "ratio", "RISK"),
    "Sortino近7年": ("sortino_7y", "ratio", "RISK"),
    "Sortino近10年": ("sortino_10y", "ratio", "RISK"),
    "Sortino近15年": ("sortino_15y", "ratio", "RISK"),
    "Calmar近7年": ("calmar_7y", "ratio", "RISK"),
    "Calmar近10年": ("calmar_10y", "ratio", "RISK"),
    "Calmar近15年": ("calmar_15y", "ratio", "RISK"),
}

NUMERIC_METRIC_KEYS = {v[0] for v in SHEET1_METRICS.values() if v[1] == "ratio"}
DATE_METRIC_KEYS = {v[0] for v in SHEET1_METRICS.values() if v[1] == "date"}


@dataclass(frozen=True)
class SourceBinding:
    drive_file_id: str
    expected_sha256: str
    drive_modified_utc: str
    retrieved_at: str
    expected_headers: Dict[str, List[str]]
    workbook_name: str = FORMAL_WORKBOOK_NAME


class BenchmarkReadError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    h = sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def header_fingerprint(headers: Sequence[str]) -> str:
    return sha256("\t".join(headers).encode("utf-8")).hexdigest()


def issue(code: str, severity: str, field_path: str, message: str, *, blocking: bool = False,
          source_reference_ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "field_path": field_path,
        "message": message,
        "owner": "C_INTEGRATION",
        "blocking": bool(blocking),
        "source_reference_ids": [SOURCE_ID] if source_reference_ids is None else list(source_reference_ids),
    }


def parse_quality_flags(raw: Any) -> Tuple[List[str], List[str]]:
    if raw is None or str(raw).strip() == "":
        return [], []
    flags = list(dict.fromkeys(p.strip() for p in str(raw).split("|") if p.strip()))
    invalid = sorted(set(flags) - ALLOWED_QUALITY_FLAGS)
    return flags, invalid


def map_native_value(value: Any) -> Tuple[str, Any, str]:
    """Map B native sentinel/value to C four-state and preserve native status."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return "UNKNOWN", None, "BLANK"
    if isinstance(value, str):
        s = value.strip()
        u = s.upper()
        if u == "UNKNOWN":
            return "UNKNOWN", None, "UNKNOWN"
        if u == "NOT_APPLICABLE":
            return "NOT_APPLICABLE", None, "NOT_APPLICABLE"
        if u == "PENDING_DERIVATION":
            return "UNKNOWN", None, "PENDING_DERIVATION"
        if u == "NOT_RECOVERED":
            return "NONE", None, "NOT_RECOVERED"
        if u == "KNOWN":
            # A standalone KNOWN is a status, not a value; callers must pair it with a value.
            return "KNOWN", None, "KNOWN"
        return "KNOWN", value, "KNOWN"
    return "KNOWN", value, "KNOWN"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s or s.upper() in NATIVE_SENTINELS:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _business_day_lag(as_of: date, eval_date: date) -> int:
    if as_of >= eval_date:
        return 0
    d = as_of
    count = 0
    while d < eval_date:
        d = d.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            count += 1
    return count


def _freshness_for_metric(state: str, category: str, as_of_value: Any, eval_date: date,
                          row_flags: Sequence[str]) -> str:
    if state in {"NONE", "NOT_APPLICABLE"}:
        return "NOT_APPLICABLE"
    if state == "UNKNOWN":
        return "UNKNOWN"
    as_of = _to_date(as_of_value)
    if as_of is None:
        return "UNKNOWN"
    if category in {"OFFICIAL", "OFFICIAL_DATE"}:
        return "STALE" if (eval_date - as_of).days > 45 else "FRESH"
    # B W2-DQ-005 says daily price/NAV should not lag >5 trading days.
    if _business_day_lag(as_of, eval_date) > 5:
        return "STALE"
    if "STALE" in row_flags:
        # Row-level STALE is preserved as a warning, but does not blindly poison unrelated fields.
        # For risk data, only apply it when its own as-of is also beyond the threshold above.
        return "FRESH"
    return "FRESH"


def _field_quality(state: str, category: str, row_flags: Sequence[str]) -> str:
    if state == "UNKNOWN":
        return "INSUFFICIENT" if "INSUFFICIENT" in row_flags else "UNKNOWN"
    if state in {"NONE", "NOT_APPLICABLE"}:
        return "OK"
    if category in {"RISK", "RISK_DATE"} and "FALLBACK_USED" in row_flags:
        return "FALLBACK_USED"
    return "OK"


def _metric_formal_gate(state: str, data_quality: str, freshness: str, traceable: bool,
                        extra_blocking: bool = False) -> Dict[str, Any]:
    reasons: List[str] = []
    if state == "UNKNOWN": reasons.append("VALUE_UNKNOWN")
    if data_quality in {"INSUFFICIENT", "UNKNOWN"}: reasons.append(f"DATA_QUALITY_{data_quality}")
    if freshness in {"STALE", "UNKNOWN"}: reasons.append(f"FRESHNESS_{freshness}")
    if not traceable: reasons.append("SOURCE_NOT_TRACEABLE")
    if extra_blocking: reasons.append("EXTRA_BLOCKING_CONDITION")
    eligible = not reasons and state in {"KNOWN", "NONE", "NOT_APPLICABLE"}
    return {"eligible": eligible, "scope": "FULL" if eligible else "NONE", "blocking_reasons": reasons}


def _value_envelope(raw_value: Any, *, category: str, as_of_value: Any, eval_date: date,
                    row_flags: Sequence[str], traceable: bool = True) -> Dict[str, Any]:
    state, value, native = map_native_value(raw_value)
    dq = _field_quality(state, category, row_flags)
    freshness = _freshness_for_metric(state, category, as_of_value, eval_date, row_flags)
    issue_codes: List[str] = []
    if state == "UNKNOWN": issue_codes.append("C_OPTIONAL_DATA_UNKNOWN")
    if freshness == "STALE": issue_codes.append("C_DATA_STALE")
    if dq == "FALLBACK_USED": issue_codes.append("C_FALLBACK_USED")
    return {
        "value_state": state,
        "value": json_safe(value) if state == "KNOWN" else None,
        "data_quality": dq,
        "freshness": freshness,
        "as_of": json_safe(as_of_value) if _to_date(as_of_value) else None,
        "source_reference_ids": [SOURCE_ID],
        "issue_codes": issue_codes,
        "source_native_status": native,
        "formal_output_eligibility": _metric_formal_gate(state, dq, freshness, traceable),
    }


def _invalidate_metric(env: Dict[str, Any], code: str) -> None:
    """Fail closed while preserving the upstream native status for traceability."""
    env["value_state"] = "UNKNOWN"
    env["value"] = None
    env["data_quality"] = "INSUFFICIENT"
    env["freshness"] = "UNKNOWN"
    if code not in env["issue_codes"]:
        env["issue_codes"].append(code)
    env["formal_output_eligibility"] = _metric_formal_gate("UNKNOWN", "INSUFFICIENT", "UNKNOWN", True, True)


def _validate_metric_type(env: Dict[str, Any], expected_type: str, field_path: str, issues: List[Dict[str, Any]]) -> None:
    if env["value_state"] != "KNOWN":
        return
    value = env["value"]
    if value is None:
        issues.append(issue("C_STATE_VALUE_INCONSISTENT", "ERROR", field_path,
                            "KNOWN metric must carry a concrete value; a standalone KNOWN sentinel is not a value.", blocking=True))
        _invalidate_metric(env, "C_STATE_VALUE_INCONSISTENT")
    elif expected_type == "ratio" and not _is_number(value):
        issues.append(issue("C_SCHEMA_TYPE_INVALID", "ERROR", field_path,
                            "Formal numeric metric must be a number; percent/text strings are not accepted.", blocking=True))
        _invalidate_metric(env, "C_SCHEMA_TYPE_INVALID")
    elif expected_type == "date" and _to_date(value) is None:
        issues.append(issue("C_SCHEMA_TYPE_INVALID", "ERROR", field_path,
                            "Date metric is not a valid date.", blocking=True))
        _invalidate_metric(env, "C_SCHEMA_TYPE_INVALID")


def _parse_proxy_policy(rule_rows: Sequence[Dict[str, Any]], issues: List[Dict[str, Any]]) -> Tuple[Dict[str, Set[str]], Set[str], Dict[str, Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    seen: Set[str] = set()
    for idx, row in enumerate(rule_rows, start=2):
        rid = str(row.get("Rule_ID") or "").strip()
        if not rid:
            continue
        if rid in seen:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet2[{idx}].Rule_ID",
                                f"Duplicate Rule_ID: {rid}", blocking=True))
        seen.add(rid)
        by_id[rid] = row

    missing = sorted(CORE_RULE_IDS - set(by_id))
    for rid in missing:
        issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", "Sheet2.Rule_ID",
                            f"Required Work2 canonical rule is missing: {rid}", blocking=True))

    authorized: Dict[str, Set[str]] = {}
    forbidden: Set[str] = set()
    r2 = by_id.get("W2-PRX-002")
    if r2:
        scope = str(r2.get("適用範圍") or "")
        fmt = str(r2.get("資料型別/格式") or "")
        m = re.search(r"PROXY\s*=\s*([A-Za-z0-9._-]+)", fmt, re.I)
        if m:
            proxy = m.group(1).upper()
            for t in re.split(r"[/,;\s]+", scope):
                t = t.strip().upper()
                if t:
                    authorized.setdefault(t, set()).add(proxy)
    r3 = by_id.get("W2-PRX-003")
    if r3 and "NO_PROXY" in str(r3.get("資料型別/格式") or "").upper():
        for t in re.split(r"[/,;\s]+", str(r3.get("適用範圍") or "")):
            t = t.strip().upper()
            if t:
                forbidden.add(t)
    return authorized, forbidden, by_id


def _canonical_proxy_declaration(ticker: str, raw_proxy: Any, raw_status: Any,
                                 authorized: Dict[str, Set[str]], forbidden: Set[str],
                                 issues: List[Dict[str, Any]], row_num: int) -> Dict[str, Any]:
    raw = str(raw_proxy or "").strip()
    status = str(raw_status or "").strip()
    if not raw:
        return {"proxy_ticker": None, "usage": "NOT_USED", "authorization": "NOT_APPLICABLE",
                "source_native_status": status or None}
    if raw.upper() in {"禁止代理", "NO_PROXY", "NOT_APPLICABLE"} or ticker in forbidden:
        if ticker in forbidden and raw.upper() not in {"禁止代理", "NO_PROXY", "NOT_APPLICABLE"}:
            issues.append(issue("C_PROXY_UNAUTHORIZED", "BLOCKING", f"Sheet1[{row_num}].代理標的",
                                f"{ticker} is explicitly NO_PROXY but declares {raw}.", blocking=True))
        return {"proxy_ticker": None, "usage": "NOT_APPLICABLE", "authorization": "NOT_APPLICABLE",
                "source_native_status": status or "NO_PROXY"}
    proxy = raw.upper()
    auth = "AUTHORIZED" if proxy in authorized.get(ticker, set()) else "UNAUTHORIZED"
    if auth == "UNAUTHORIZED":
        issues.append(issue("C_PROXY_UNAUTHORIZED", "BLOCKING", f"Sheet1[{row_num}].代理標的",
                            f"Proxy {proxy} is not authorized for {ticker} by B Sheet2.", blocking=True))
    else:
        issues.append(issue("C_PROXY_USED", "WARNING", f"Sheet1[{row_num}].代理標的",
                            f"Authorized proxy declaration preserved: {ticker} -> {proxy}."))
    return {"proxy_ticker": proxy, "usage": "USED", "authorization": auth, "source_native_status": status or None}


def _normalize_assets(rows: Sequence[Dict[str, Any]], authorized: Dict[str, Set[str]], forbidden: Set[str],
                      eval_date: date, issues: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Set[str]]:
    assets: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    tickers: Set[str] = set()
    for idx, row in enumerate(rows, start=2):
        ticker = str(row.get("Ticker") or "").strip().upper()
        if not ticker:
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", f"Sheet1[{idx}].Ticker",
                                "Ticker is required.", blocking=True))
            continue
        if ticker in seen:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet1[{idx}].Ticker",
                                f"Duplicate Ticker: {ticker}", blocking=True))
        seen.add(ticker); tickers.add(ticker)
        flags, invalid_flags = parse_quality_flags(row.get("資料品質(Quality Flag)"))
        for flag in invalid_flags:
            issues.append(issue("C_SCHEMA_ENUM_INVALID", "BLOCKING", f"Sheet1[{idx}].資料品質(Quality Flag)",
                                f"Invalid B Quality Flag: {flag}", blocking=True))

        primary_url = str(row.get("主要來源URL") or "").strip()
        if not primary_url:
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "ERROR", f"Sheet1[{idx}].主要來源URL",
                                "Primary source URL is required for traceability.", blocking=True))
        proxy = _canonical_proxy_declaration(ticker, row.get("代理標的"), row.get("Proxy狀態"), authorized, forbidden, issues, idx)

        metrics: Dict[str, Any] = {}
        official_as_of = row.get("官方績效截至")
        risk_as_of = row.get("資料截至日(As-of Date)")
        for source_col, (key, unit, category) in SHEET1_METRICS.items():
            as_of = official_as_of if category.startswith("OFFICIAL") else risk_as_of
            # The as-of field itself is evaluated against its own date value.
            if category == "OFFICIAL_DATE": as_of = row.get(source_col)
            if category == "RISK_DATE": as_of = risk_as_of
            env = _value_envelope(row.get(source_col), category=category, as_of_value=as_of,
                                  eval_date=eval_date, row_flags=flags, traceable=bool(primary_url))
            env["unit"] = unit
            env["source_column"] = source_col
            _validate_metric_type(env, unit, f"Sheet1[{idx}].{source_col}", issues)
            if env["value_state"] == "KNOWN":
                parsed_as_of = _to_date(as_of)
                if parsed_as_of is None:
                    issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "ERROR", f"Sheet1[{idx}].{source_col}",
                                        "KNOWN metric requires a valid As-of date for freshness evaluation.", blocking=False))
                    _invalidate_metric(env, "C_SCHEMA_REQUIRED_MISSING")
                elif parsed_as_of > eval_date:
                    issues.append(issue("C_STATE_VALUE_INCONSISTENT", "ERROR", f"Sheet1[{idx}].{source_col}",
                                        f"As-of date {parsed_as_of.isoformat()} is later than evaluation date {eval_date.isoformat()}.", blocking=True))
                    _invalidate_metric(env, "C_STATE_VALUE_INCONSISTENT")
            metrics[key] = env

        metric_eligible = [m["formal_output_eligibility"]["eligible"] for m in metrics.values()]
        if metric_eligible and all(metric_eligible): scope = "FULL"
        elif any(metric_eligible): scope = "PARTIAL"
        else: scope = "NONE"
        assets.append({
            "ticker": ticker,
            "priority": row.get("優先序"),
            "formal_name": row.get("正式名稱"),
            "asset_type": row.get("資產類型"),
            "listing_market": row.get("主要掛牌/市場"),
            "base_currency": row.get("基礎幣別"),
            "inception_date": json_safe(row.get("成立日")),
            "ter_native": row.get("費用率/TER"),
            "long_history_basis": row.get("長期歷史口徑"),
            "proxy": proxy,
            "primary_source_url": row.get("主要來源URL"),
            "supplemental_source_url": row.get("補充來源URL"),
            "source_type": row.get("來源類型"),
            "quality_flags": flags,
            "last_updated_native": row.get("最後更新時間"),
            "data_as_of": json_safe(risk_as_of),
            "notes": row.get("備註"),
            "unknown_reason": row.get("UNKNOWN/缺資料說明"),
            "metrics": metrics,
            "source_reference_ids": [SOURCE_ID],
            "formal_output_eligibility": {
                "eligible": scope != "NONE",
                "scope": scope,
                "blocking_reasons": [] if scope != "NONE" else ["NO_ELIGIBLE_METRICS"],
            },
        })
    return assets, tickers


def _normalize_taxonomy(rows: Sequence[Dict[str, Any]], issues: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Set[str]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    parents: Dict[str, Optional[str]] = {}
    for idx, row in enumerate(rows, start=2):
        eid = str(row.get("Exposure_ID") or "").strip()
        if not eid:
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", f"Sheet3[{idx}].Exposure_ID",
                                "Exposure_ID is required.", blocking=True)); continue
        if eid in seen:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet3[{idx}].Exposure_ID",
                                f"Duplicate Exposure_ID: {eid}", blocking=True))
        seen.add(eid)
        if not EXPOSURE_ID_RE.fullmatch(eid):
            issues.append(issue("C_SCHEMA_ENUM_INVALID", "BLOCKING", f"Sheet3[{idx}].Exposure_ID",
                                f"Illegal Exposure_ID syntax: {eid}", blocking=True))
        parent = str(row.get("Parent_ID") or "").strip() or None
        parents[eid] = parent
        out.append({
            "exposure_id": eid, "category": row.get("大類"), "name": row.get("曝險項目"),
            "definition": row.get("定義"), "calculation_native": row.get("計算方式"),
            "unit": row.get("單位"), "value_type": row.get("值類型"), "parent_id": parent,
            "additive": row.get("可加總(Y/N)"), "unknown_handling": row.get("UNKNOWN處理"),
            "source_requirement": row.get("Source要求"), "quality_rule": row.get("Quality Flag規則"),
            "notes": row.get("備註"), "source_reference_ids": [SOURCE_ID],
        })
    for eid, parent in parents.items():
        if parent and parent not in seen:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet3[{eid}].Parent_ID",
                                f"Parent_ID does not resolve: {parent}", blocking=True))
        if parent == eid:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet3[{eid}].Parent_ID",
                                "Exposure taxonomy self-cycle.", blocking=True))
    # Detect longer parent cycles.
    for start in seen:
        path: Set[str] = set()
        cur: Optional[str] = start
        while cur and cur in parents:
            if cur in path:
                issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet3[{start}].Parent_ID",
                                    f"Exposure taxonomy parent cycle involving {cur}.", blocking=True)); break
            path.add(cur); cur = parents.get(cur)
    return out, seen


def _normalize_exposures(rows: Sequence[Dict[str, Any]], tickers: Set[str], exposure_ids: Set[str],
                         eval_date: date, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_keys: Set[Tuple[str, str]] = set()
    for idx, row in enumerate(rows, start=2):
        ticker = str(row.get("Ticker") or "").strip().upper()
        eid = str(row.get("Exposure_ID") or "").strip()
        key = (ticker, eid)
        if key in seen_keys:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet4[{idx}]",
                                f"Duplicate current exposure primitive: {ticker}/{eid}", blocking=True))
        seen_keys.add(key)
        if ticker not in tickers:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet4[{idx}].Ticker",
                                f"Exposure ticker does not resolve to Sheet1: {ticker}", blocking=True))
        if eid not in exposure_ids:
            issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", f"Sheet4[{idx}].Exposure_ID",
                                f"Exposure_ID does not resolve to Sheet3 taxonomy: {eid}", blocking=True))

        flags, invalid_flags = parse_quality_flags(row.get("Quality_Flag"))
        for flag in invalid_flags:
            issues.append(issue("C_SCHEMA_ENUM_INVALID", "BLOCKING", f"Sheet4[{idx}].Quality_Flag",
                                f"Invalid B Quality Flag: {flag}", blocking=True))

        native_status = str(row.get("Data_Status") or "").strip().upper()
        if native_status not in NATIVE_SENTINELS:
            issues.append(issue("C_SOURCE_NATIVE_STATUS_UNMAPPED", "BLOCKING", f"Sheet4[{idx}].Data_Status",
                                f"Unmapped B native status: {native_status or '<blank>'}", blocking=True))
            c_state = "UNKNOWN"; source_native_status = native_status or "BLANK"
        else:
            c_state, _, source_native_status = map_native_value(native_status)
        weight = row.get("Exposure_Weight")
        state_conflict = False
        if c_state == "KNOWN":
            if not _is_number(weight):
                state_conflict = True
                issues.append(issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", f"Sheet4[{idx}].Exposure_Weight",
                                    "KNOWN exposure requires numeric Exposure_Weight.", blocking=True))
        else:
            if weight is not None and weight != "":
                state_conflict = True
                issues.append(issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", f"Sheet4[{idx}].Exposure_Weight",
                                    f"{native_status} must not be encoded as 0/False/Neutral or any numeric value.", blocking=True))

        as_of_raw = row.get("As_of_Date")
        as_of_date = _to_date(as_of_raw)
        if c_state == "KNOWN" and as_of_date is None:
            state_conflict = True
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", f"Sheet4[{idx}].As_of_Date",
                                "KNOWN exposure requires a valid As_of_Date.", blocking=True))
        elif c_state == "KNOWN" and as_of_date > eval_date:
            state_conflict = True
            issues.append(issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", f"Sheet4[{idx}].As_of_Date",
                                f"As_of_Date {as_of_date.isoformat()} is later than evaluation date {eval_date.isoformat()}.", blocking=True))
        source_url = str(row.get("Source_URL") or "").strip()
        if c_state == "KNOWN" and not source_url:
            state_conflict = True
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", f"Sheet4[{idx}].Source_URL",
                                "KNOWN exposure requires Source_URL.", blocking=True))

        proxy_ticker = str(row.get("Proxy_Ticker") or "").strip().upper() or None
        proxy_status = str(row.get("Proxy_Status") or "").strip().upper()
        proxy_used = bool(proxy_ticker) or proxy_status in {"USED", "PROXY_USED"}
        if proxy_used:
            state_conflict = True
            issues.append(issue("C_PROXY_UNAUTHORIZED", "BLOCKING", f"Sheet4[{idx}].Proxy_Ticker",
                                "B W2-PRX-001 forbids proxy substitution for holdings/look-through exposure primitives.", blocking=True))

        if c_state == "UNKNOWN": dq = "INSUFFICIENT" if "INSUFFICIENT" in flags else "UNKNOWN"
        elif "FALLBACK_USED" in flags: dq = "FALLBACK_USED"
        else: dq = "OK"
        if c_state in {"NONE", "NOT_APPLICABLE"}: freshness = "NOT_APPLICABLE"
        elif c_state == "UNKNOWN": freshness = "UNKNOWN"
        elif "STALE" in flags: freshness = "STALE"
        else: freshness = "FRESH" if as_of_date else "UNKNOWN"
        gate = _metric_formal_gate(c_state, dq, freshness, bool(source_url), state_conflict)
        issue_codes: List[str] = []
        if c_state == "UNKNOWN": issue_codes.append("C_OPTIONAL_DATA_UNKNOWN")
        if freshness == "STALE": issue_codes.append("C_DATA_STALE")
        if dq == "FALLBACK_USED": issue_codes.append("C_FALLBACK_USED")
        if proxy_used: issue_codes.append("C_PROXY_UNAUTHORIZED")

        canonical_state = c_state
        canonical_value = weight if c_state == "KNOWN" and _is_number(weight) else None
        canonical_dq = dq
        canonical_freshness = freshness
        if state_conflict and c_state == "KNOWN":
            canonical_state = "UNKNOWN"
            canonical_value = None
            canonical_dq = "INSUFFICIENT"
            canonical_freshness = "UNKNOWN"
            gate = _metric_formal_gate(canonical_state, canonical_dq, canonical_freshness, bool(source_url), True)
            if "C_STATE_VALUE_INCONSISTENT" not in issue_codes:
                issue_codes.append("C_STATE_VALUE_INCONSISTENT")

        out.append({
            "ticker": ticker,
            "exposure_id": eid,
            "exposure_name": row.get("Exposure_Name"),
            "value": canonical_value,
            "value_state": canonical_state,
            "weight_unit": row.get("Weight_Unit"),
            "as_of": json_safe(as_of_raw) if as_of_date else None,
            "source_url": row.get("Source_URL"),
            "source_type": row.get("Source_Type"),
            "quality_flags": flags,
            "data_quality": canonical_dq,
            "freshness": canonical_freshness,
            "proxy_ticker": proxy_ticker,
            "proxy_status_native": row.get("Proxy_Status"),
            "source_native_status": source_native_status,
            "notes": row.get("Notes"),
            "source_reference_ids": [SOURCE_ID],
            "issue_codes": issue_codes,
            "formal_output_eligibility": gate,
        })
    return out


def _validate_headers(wb: WorkbookData, binding: SourceBinding, issues: List[Dict[str, Any]]) -> Dict[str, str]:
    fps: Dict[str, str] = {}
    actual_names = set(wb.sheets)
    expected_names = set(binding.expected_headers)
    for missing in sorted(expected_names - actual_names):
        issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", missing,
                            f"Required B sheet is missing: {missing}", blocking=True))
    for extra in sorted(actual_names - expected_names):
        issues.append(issue("C_SCHEMA_ENUM_INVALID", "ERROR", extra,
                            f"Unexpected B sheet present: {extra}", blocking=True))
    for name, expected in binding.expected_headers.items():
        if name not in wb.sheets:
            continue
        actual = wb.sheets[name].headers
        fps[name] = header_fingerprint(actual)
        if actual != expected:
            issues.append(issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", f"{name}.headers",
                                "Sheet header sequence differs from the Work1 canonical contract.", blocking=True))
    return fps


def _trace_integrity(snapshot: Dict[str, Any], issues: List[Dict[str, Any]]) -> None:
    src_ids = {s["source_id"] for s in snapshot.get("source_references", [])}
    if len(src_ids) != len(snapshot.get("source_references", [])):
        issues.append(issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", "source_references",
                            "Duplicate source_id.", blocking=True, source_reference_ids=[]))
    refs: List[Tuple[str, str]] = []
    for a in snapshot.get("assets", []):
        for s in a.get("source_reference_ids", []): refs.append((f"assets.{a['ticker']}", s))
        for key, m in a.get("metrics", {}).items():
            for s in m.get("source_reference_ids", []): refs.append((f"assets.{a['ticker']}.metrics.{key}", s))
    for e in snapshot.get("exposure_taxonomy", []):
        for s in e.get("source_reference_ids", []): refs.append((f"taxonomy.{e['exposure_id']}", s))
    for e in snapshot.get("exposure_primitives", []):
        for s in e.get("source_reference_ids", []): refs.append((f"exposures.{e['ticker']}.{e['exposure_id']}", s))
    for p, s in refs:
        if s not in src_ids:
            issues.append(issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", p,
                                f"Unresolvable source_reference_id: {s}", blocking=True, source_reference_ids=[]))


def read_benchmark(path: str | Path, binding: SourceBinding, *, evaluation_date: Optional[date] = None) -> Dict[str, Any]:
    path = Path(path)
    eval_date = evaluation_date or date.today()
    issues: List[Dict[str, Any]] = []
    fingerprint = sha256_file(path)

    if binding.workbook_name != FORMAL_WORKBOOK_NAME or path.name != FORMAL_WORKBOOK_NAME:
        issues.append(issue("C_SOURCE_SOT_MISMATCH", "BLOCKING", "benchmark_reference.workbook_name",
                            f"Expected formal workbook {FORMAL_WORKBOOK_NAME}; received {path.name}.", blocking=True))
    if binding.drive_file_id != FORMAL_DRIVE_FILE_ID:
        issues.append(issue("C_SOURCE_SOT_MISMATCH", "BLOCKING", "benchmark_reference.drive_file_id",
                            "Drive File ID is not the formal B SOT File ID.", blocking=True))
    if fingerprint != binding.expected_sha256:
        issues.append(issue("C_SOURCE_FINGERPRINT_MISMATCH", "BLOCKING", "benchmark_reference.file_fingerprint_sha256",
                            f"Fingerprint mismatch: {fingerprint} != {binding.expected_sha256}.", blocking=True))

    wb = read_xlsx(path)
    header_fps = _validate_headers(wb, binding, issues)

    required_names = set(binding.expected_headers)
    structurally_readable = required_names.issubset(wb.sheets)
    if structurally_readable:
        rule_rows = wb.sheets["Sheet2_來源計算代理規則"].rows
        authorized, forbidden, rules_by_id = _parse_proxy_policy(rule_rows, issues)
        assets, tickers = _normalize_assets(wb.sheets["Sheet1_標的績效基準資料"].rows,
                                             authorized, forbidden, eval_date, issues)
        taxonomy, exposure_ids = _normalize_taxonomy(wb.sheets["Sheet3_曝險度項目定義"].rows, issues)
        exposures = _normalize_exposures(wb.sheets["Sheet4_標的曝險基準資料"].rows,
                                          tickers, exposure_ids, eval_date, issues)
    else:
        authorized, forbidden, rules_by_id, assets, taxonomy, exposures = {}, set(), {}, [], [], []

    sheet_refs = []
    for name, role in SHEET_ROLES.items():
        if name in wb.sheets:
            sheet_refs.append({"sheet_name": name, "role": role,
                               "header_fingerprint_sha256": header_fps.get(name)})

    blocking_structural = any(i["blocking"] for i in issues)
    source_ref = {
        "source_id": SOURCE_ID,
        "source_kind": "B_BENCHMARK_SOT",
        "owner": "B_BENCHMARK",
        "source_reference": binding.drive_file_id,
        "source_version": f"drive-modified:{binding.drive_modified_utc}",
        "source_fingerprint": fingerprint,
        "source_fingerprint_algorithm": "SHA-256",
        "as_of": binding.drive_modified_utc,
        "retrieved_at": binding.retrieved_at,
        "data_quality": "OK" if not blocking_structural else "UNKNOWN",
        "freshness": "FRESH" if not blocking_structural else "UNKNOWN",
        "issue_codes": sorted({i["code"] for i in issues if i["blocking"]}),
        "source_native_status": "FORMAL_B_SOT",
    }

    snapshot: Dict[str, Any] = {
        "work2_version": WORK2_VERSION,
        "work1_contract_version": WORK1_CONTRACT_VERSION,
        "generated_at": binding.retrieved_at,
        "evaluation_date": eval_date.isoformat(),
        "benchmark_reference": {
            "workbook_name": FORMAL_WORKBOOK_NAME,
            "drive_file_id": binding.drive_file_id,
            "file_fingerprint_sha256": fingerprint,
            "source_version": source_ref["source_version"],
            "sheets": sheet_refs,
            "source_reference_ids": [SOURCE_ID],
            "data_quality": source_ref["data_quality"],
            "freshness": source_ref["freshness"],
            "issue_codes": source_ref["issue_codes"],
        },
        "source_references": [source_ref],
        "proxy_policy": {
            "authorized": {k: sorted(v) for k, v in sorted(authorized.items())},
            "no_proxy": sorted(forbidden),
            "canonical_rule_ids": sorted(rules_by_id),
        },
        "assets": assets,
        "exposure_taxonomy": taxonomy,
        "exposure_primitives": exposures,
        "workbook_stats": {
            "formula_cell_count": wb.formula_cell_count,
            "asset_count": len(assets),
            "rule_row_count": len(wb.sheets.get("Sheet2_來源計算代理規則").rows) if "Sheet2_來源計算代理規則" in wb.sheets else 0,
            "taxonomy_count": len(taxonomy),
            "exposure_primitive_count": len(exposures),
        },
        "issues": issues,
        "formal_output_eligibility": {"eligible": False, "scope": "NONE", "blocking_reasons": []},
    }

    _trace_integrity(snapshot, issues)
    hard_blockers = [i for i in issues if i["blocking"]]
    if hard_blockers:
        snapshot["formal_output_eligibility"] = {
            "eligible": False, "scope": "NONE",
            "blocking_reasons": sorted({i["code"] for i in hard_blockers}),
        }
    else:
        child_eligibility: List[bool] = []
        for a in assets:
            child_eligibility.extend(m["formal_output_eligibility"]["eligible"] for m in a["metrics"].values())
        child_eligibility.extend(e["formal_output_eligibility"]["eligible"] for e in exposures)
        if child_eligibility and all(child_eligibility): scope = "FULL"
        elif any(child_eligibility): scope = "PARTIAL"
        else: scope = "NONE"
        snapshot["formal_output_eligibility"] = {
            "eligible": scope != "NONE", "scope": scope,
            "blocking_reasons": [] if scope != "NONE" else ["NO_FORMALLY_ELIGIBLE_CHILD_DATA"],
        }
        if scope == "PARTIAL":
            issues.append(issue("C_PARTIAL_OUTPUT", "WARNING", "formal_output_eligibility",
                                "B workbook is structurally valid, but some fields are UNKNOWN/STALE and remain blocked field-by-field."))
    return json_safe(snapshot)


def load_binding(config_path: str | Path) -> SourceBinding:
    with open(config_path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return SourceBinding(
        drive_file_id=obj["drive_file_id"],
        expected_sha256=obj["expected_sha256"],
        drive_modified_utc=obj["drive_modified_utc"],
        retrieved_at=obj["retrieved_at"],
        expected_headers=obj["expected_headers"],
        workbook_name=obj.get("workbook_name", FORMAL_WORKBOOK_NAME),
    )


def write_snapshot(path: str | Path, snapshot: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="C Work2 B benchmark read-only adapter")
    p.add_argument("xlsx")
    p.add_argument("config")
    p.add_argument("--output", required=True)
    p.add_argument("--evaluation-date", default=None)
    args = p.parse_args()
    ed = date.fromisoformat(args.evaluation_date) if args.evaluation_date else None
    snap = read_benchmark(args.xlsx, load_binding(args.config), evaluation_date=ed)
    write_snapshot(args.output, snap)
    print(json.dumps({
        "formal_output_eligibility": snap["formal_output_eligibility"],
        "workbook_stats": snap["workbook_stats"],
        "blocking_issue_count": sum(1 for i in snap["issues"] if i["blocking"]),
        "issue_count": len(snap["issues"]),
    }, ensure_ascii=False, indent=2))
