"""C Work3 — Performance / Risk Projection Engine.

This module consumes:
1) a Work1 AllocationSnapshot; and
2) the Work2 Canonical Benchmark Snapshot.

Hard method boundary:
- Work2 currently provides per-asset summary metrics, not aligned portfolio total-return
  wealth-index histories. Therefore a mixed portfolio's historical CAGR/MDD/recovery/
  Sharpe/Sortino/Calmar MUST NOT be synthesized from weighted component summaries.
- Single effective-asset allocations may safely pass through eligible Work2 asset metrics.
- Planning projections are permitted only from an eligible single-asset B central CAGR in
  the same currency basis, or from explicit, traceable portfolio-currency assumptions.

No V70/V82/V75 business rule is implemented here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

WORK3_VERSION = "C-W3-v1.0.1"
WORK2_VERSION = "C-W2-v1.0.1"
WORK1_CONTRACT_VERSION = "C-W1-v1.0.1"
CURRENT_B_SOT_SHA256 = "f639f5b46b7ff0c7ab2884a0ce01739d852c94f8e383f1966463d48178a77b02"
CURRENT_B_DRIVE_FILE_ID = "1vbaPznrzrDwZ17AeLXSLJErMrXwxPl1-"
B_SOURCE_ID = "SRC_B_WORKBOOK"
MODULE_NAME = "C_WORK3_PERFORMANCE_RISK"
WEIGHT_TOLERANCE = 1e-6
HORIZONS = (1, 3, 5, 7, 10, 20, 30)
WINDOWS = ("7y", "10y", "15y", "inception")
RATIO_FAMILIES = ("sharpe", "sortino", "calmar")
SCENARIOS = ("conservative", "central", "better")

REQUIRED_WORK3_RULE_IDS = {
    "W2-SRC-004", "W2-SRC-007",
    "W2-TR-001", "W2-TR-004",
    "W2-PER-001", "W2-PER-002", "W2-PER-003",
    "W2-MET-001", "W2-MET-002", "W2-MET-003", "W2-MET-004", "W2-MET-005",
    "W2-MET-006", "W2-MET-007", "W2-MET-008", "W2-MET-009", "W2-MET-010",
    "W2-PRX-001", "W2-PRX-002", "W2-PRX-003",
    "W2-DQ-001", "W2-DQ-002", "W2-DQ-003", "W2-DQ-004", "W2-DQ-005",
    "W2-DQ-006", "W2-DQ-007",
}

HISTORICAL_METHOD_RULES = [
    "W2-SRC-004", "W2-TR-001", "W2-PER-001", "W2-PER-002", "W2-PER-003",
    "W2-MET-001", "W2-MET-002", "W2-MET-003", "W2-MET-004", "W2-MET-005",
    "W2-MET-006", "W2-MET-007", "W2-MET-008", "W2-MET-009", "W2-MET-010",
    "W2-PRX-001", "W2-PRX-002", "W2-PRX-003",
    "W2-DQ-001", "W2-DQ-002", "W2-DQ-003", "W2-DQ-004", "W2-DQ-005",
    "W2-DQ-006", "W2-DQ-007",
]


def _uniq(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(v for v in values if v))


def _safe_refs(value: Any) -> List[str]:
    """Return only non-empty string source IDs from an arbitrary input value."""
    if not isinstance(value, (list, tuple)):
        return []
    return _uniq(x for x in value if isinstance(x, str) and x)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_number(v: Any) -> bool:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(float(v))
    except (OverflowError, ValueError, TypeError):
        return False


def _issue(code: str, severity: str, field_path: Optional[str], message: str, *,
           blocking: bool = False, source_reference_ids: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "field_path": field_path,
        "message": message,
        "owner": "C_INTEGRATION",
        "blocking": bool(blocking),
        "source_reference_ids": _uniq(source_reference_ids),
    }


def _gate(eligible: bool, scope: str, *, blocking_reasons: Sequence[str] = (),
          warning_reasons: Sequence[str] = (), evaluated_at: Optional[str] = None,
          rules: Sequence[str] = ()) -> Dict[str, Any]:
    if not eligible:
        scope = "NONE"
    return {
        "eligible": bool(eligible),
        "scope": scope,
        "blocking_reasons": _uniq(blocking_reasons),
        "warning_reasons": _uniq(warning_reasons),
        "evaluated_at": evaluated_at,
        "rule_references": _uniq(rules),
    }


def _metric(*, support_status: str, value_state: str, value: Any, unit: Optional[str],
            as_of: Optional[str], data_quality: str, freshness: str,
            source_reference_ids: Sequence[str], issue_codes: Sequence[str],
            source_native_status: Optional[str], source_metric_key: Optional[str],
            method: str, rule_references: Sequence[str], proxy: Optional[Mapping[str, Any]],
            formal_eligible: bool, formal_scope: str = "FULL",
            blocking_reasons: Sequence[str] = (), warning_reasons: Sequence[str] = (),
            evaluated_at: Optional[str] = None) -> Dict[str, Any]:
    if value_state != "KNOWN":
        value = None
    return {
        "support_status": support_status,
        "value_state": value_state,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "data_quality": data_quality,
        "freshness": freshness,
        "source_reference_ids": _uniq(source_reference_ids),
        "issue_codes": _uniq(issue_codes),
        "source_native_status": source_native_status,
        "source_metric_key": source_metric_key,
        "method": method,
        "rule_references": _uniq(rule_references),
        "proxy": deepcopy(proxy) if proxy is not None else {
            "usage": "NOT_APPLICABLE", "authorization": "NOT_APPLICABLE",
            "proxy_ticker": None, "source_native_status": None,
        },
        "formal_output_eligibility": _gate(
            formal_eligible,
            formal_scope if formal_eligible else "NONE",
            blocking_reasons=blocking_reasons,
            warning_reasons=warning_reasons,
            evaluated_at=evaluated_at,
            rules=rule_references,
        ),
    }


def _unsupported_metric(unit: Optional[str], *, source_metric_key: Optional[str],
                        method: str, rule_references: Sequence[str],
                        evaluated_at: str, code: str = "C_UNSUPPORTED_BY_BASELINE") -> Dict[str, Any]:
    return _metric(
        support_status="UNSUPPORTED_BY_BASELINE",
        value_state="UNKNOWN", value=None, unit=unit, as_of=None,
        data_quality="INSUFFICIENT", freshness="UNKNOWN",
        source_reference_ids=[B_SOURCE_ID], issue_codes=[code],
        source_native_status="UNSUPPORTED_BY_CURRENT_WORK2_SUMMARY_BASELINE",
        source_metric_key=source_metric_key, method=method,
        rule_references=rule_references, proxy=None, formal_eligible=False,
        blocking_reasons=[code], evaluated_at=evaluated_at,
    )


def _no_assumption_metric(*, evaluated_at: str, scenario: str) -> Dict[str, Any]:
    return _metric(
        support_status="UNSUPPORTED_BY_BASELINE",
        value_state="UNKNOWN", value=None, unit="annual_return_ratio", as_of=None,
        data_quality="INSUFFICIENT", freshness="UNKNOWN", source_reference_ids=[],
        issue_codes=["C_UNSUPPORTED_BY_BASELINE"], source_native_status="NO_FORMAL_SCENARIO_ASSUMPTION",
        source_metric_key=None, method=f"NO_{scenario.upper()}_ASSUMPTION",
        rule_references=["W2-DQ-007"], proxy=None, formal_eligible=False,
        blocking_reasons=["C_UNSUPPORTED_BY_BASELINE"], evaluated_at=evaluated_at,
    )


def _not_applicable_metric(unit: Optional[str], *, method: str,
                           source_reference_ids: Sequence[str], rules: Sequence[str],
                           evaluated_at: str, reason: str) -> Dict[str, Any]:
    return _metric(
        support_status="NOT_APPLICABLE", value_state="NOT_APPLICABLE", value=None,
        unit=unit, as_of=None, data_quality="OK", freshness="NOT_APPLICABLE",
        source_reference_ids=source_reference_ids, issue_codes=[],
        source_native_status=reason, source_metric_key=None, method=method,
        rule_references=rules, proxy=None, formal_eligible=True, formal_scope="FULL",
        evaluated_at=evaluated_at,
    )


def _proxy_for_metric(asset: Mapping[str, Any], key: str) -> Dict[str, Any]:
    """Resolve asset-level B proxy metadata to the specific metric window.

    Work2 intentionally preserves B's row-level proxy scope in ``source_native_status``
    (for example VWRA SELF:7Y/INCEPTION; VT_PROXY:10Y/15Y). Work3 must not label
    self-history metrics as proxy merely because another window uses an approved proxy.
    """
    base = deepcopy(asset.get("proxy") or {
        "usage": "UNKNOWN", "authorization": "UNKNOWN", "proxy_ticker": None,
        "source_native_status": None,
    })
    if base.get("usage") != "USED":
        return base
    status = str(base.get("source_native_status") or "").upper()
    proxy_ticker = str(base.get("proxy_ticker") or "").upper()
    if key == "tax_after_total_return_central_cagr":
        basis = str(asset.get("long_history_basis") or "").upper()
        if proxy_ticker and (proxy_ticker in basis or "代理" in basis):
            return base
        return {"usage": "UNKNOWN", "authorization": "UNKNOWN", "proxy_ticker": base.get("proxy_ticker"),
                "source_native_status": status or "LONG_HISTORY_PROXY_SCOPE_AMBIGUOUS"}
    if key.startswith("worst_drawdown_") or key.endswith("_inception"):
        window = "INCEPTION"
    elif key.endswith("_7y"):
        window = "7Y"
    elif key.endswith("_10y"):
        window = "10Y"
    elif key.endswith("_15y"):
        window = "15Y"
    else:
        return base
    proxy_tokens = []
    self_tokens = []
    for segment in status.split(";"):
        seg = segment.strip()
        if ":" in seg:
            label, raw = seg.split(":", 1)
            tokens = [x.strip() for x in raw.replace(",", "/").split("/") if x.strip()]
            if "PROXY" in label:
                proxy_tokens.extend(tokens)
            if "SELF" in label:
                self_tokens.extend(tokens)
        elif "SELF_INCEPTION" in seg:
            self_tokens.append("INCEPTION")
    if window in proxy_tokens:
        return base
    if window in self_tokens:
        return {"usage": "NOT_USED", "authorization": "NOT_APPLICABLE", "proxy_ticker": None,
                "source_native_status": f"SELF_BY_B_PROXY_SCOPE:{window}"}
    return {"usage": "UNKNOWN", "authorization": "UNKNOWN", "proxy_ticker": base.get("proxy_ticker"),
            "source_native_status": f"B_PROXY_SCOPE_AMBIGUOUS_FOR:{window};{status}"}


def _source_metric(asset: Mapping[str, Any], key: str, *, evaluated_at: str,
                   method: str, rules: Sequence[str]) -> Dict[str, Any]:
    src = asset.get("metrics", {}).get(key)
    proxy = _proxy_for_metric(asset, key)
    if src is None:
        return _unsupported_metric(None, source_metric_key=key, method=method,
                                   rule_references=rules, evaluated_at=evaluated_at)
    src_gate = src.get("formal_output_eligibility") or {}
    eligible = bool(src_gate.get("eligible"))
    state = src.get("value_state", "UNKNOWN")
    proxy_ambiguous = (asset.get("proxy") or {}).get("usage") == "USED" and proxy.get("usage") == "UNKNOWN"
    if proxy_ambiguous:
        eligible = False

    issue_codes = list(src.get("issue_codes", []))
    blocking_reasons = list(src_gate.get("blocking_reasons", []))

    # Work3 semantic safety gate. Work2 guarantees canonical typing/traceability, but its
    # current reader does not encode every metric-domain bound. Work3 must therefore
    # fail closed before deriving money/projections from impossible numeric values.
    value = src.get("value")
    numeric_metric = (
        key == "tax_after_total_return_central_cagr"
        or key.startswith("max_drawdown_")
        or key.startswith("sharpe_")
        or key.startswith("sortino_")
        or key.startswith("calmar_")
    )
    if state == "KNOWN" and numeric_metric and not _is_number(value):
        eligible = False
        issue_codes = _uniq(issue_codes + ["C_SCHEMA_TYPE_INVALID"])
        blocking_reasons = _uniq(blocking_reasons + ["NUMERIC_METRIC_TYPE_INVALID"])
    if state == "KNOWN" and _is_number(value):
        fv = float(value)
        if key.startswith("max_drawdown_") and not (-1.0 <= fv <= 0.0):
            eligible = False
            issue_codes = _uniq(issue_codes + ["C_STATE_VALUE_INCONSISTENT"])
            blocking_reasons = _uniq(blocking_reasons + ["MDD_OUTSIDE_NEGATIVE_ONE_TO_ZERO"])
        if key == "tax_after_total_return_central_cagr" and fv < -1.0:
            eligible = False
            issue_codes = _uniq(issue_codes + ["C_STATE_VALUE_INCONSISTENT"])
            blocking_reasons = _uniq(blocking_reasons + ["CAGR_BELOW_NEGATIVE_ONE"])

    if proxy_ambiguous:
        issue_codes = _uniq(issue_codes + ["C_DATA_INSUFFICIENT"])
        blocking_reasons = _uniq(blocking_reasons + ["PROXY_SCOPE_AMBIGUOUS"])

    if state == "NOT_APPLICABLE":
        support = "NOT_APPLICABLE"
    elif eligible:
        support = "SUPPORTED_BY_BASELINE"
    else:
        support = "SOURCE_INELIGIBLE"

    if proxy.get("usage") == "USED":
        issue_codes = _uniq(issue_codes + ["C_PROXY_USED"])

    return _metric(
        support_status=support,
        value_state=state,
        value=value,
        unit=src.get("unit"),
        as_of=src.get("as_of"),
        data_quality=src.get("data_quality", "UNKNOWN"),
        freshness=src.get("freshness", "UNKNOWN"),
        source_reference_ids=src.get("source_reference_ids", [B_SOURCE_ID]),
        issue_codes=issue_codes,
        source_native_status=src.get("source_native_status"),
        source_metric_key=key,
        method=method,
        rule_references=rules,
        proxy=proxy,
        formal_eligible=eligible,
        formal_scope=src_gate.get("scope", "FULL") if eligible else "NONE",
        blocking_reasons=blocking_reasons,
        warning_reasons=src_gate.get("warning_reasons", []),
        evaluated_at=evaluated_at,
    )

def _derived_metric(value: Any, unit: str, *, as_of: Optional[str], source_reference_ids: Sequence[str],
                    issue_codes: Sequence[str], data_quality: str, freshness: str,
                    method: str, rules: Sequence[str], evaluated_at: str,
                    source_metric_key: Optional[str] = None,
                    proxy: Optional[Mapping[str, Any]] = None,
                    source_native_status: str = "DERIVED_BY_C_WORK3") -> Dict[str, Any]:
    return _metric(
        support_status="SUPPORTED_BY_BASELINE", value_state="KNOWN", value=value, unit=unit,
        as_of=as_of, data_quality=data_quality, freshness=freshness,
        source_reference_ids=source_reference_ids, issue_codes=issue_codes,
        source_native_status=source_native_status, source_metric_key=source_metric_key,
        method=method, rule_references=rules, proxy=proxy, formal_eligible=True,
        evaluated_at=evaluated_at,
    )


def _parse_date(s: Any) -> Optional[date]:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _asset_map(benchmark: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {str(a.get("ticker", "")).upper(): a for a in benchmark.get("assets", [])}


def _validate_benchmark(benchmark: Mapping[str, Any], issues: List[Dict[str, Any]]) -> bool:
    ok = True
    def fail(code: str, path: str, msg: str) -> None:
        nonlocal ok
        ok = False
        issues.append(_issue(code, "BLOCKING", path, msg, blocking=True, source_reference_ids=[B_SOURCE_ID]))

    if benchmark.get("work2_version") != WORK2_VERSION:
        fail("C_CROSS_MODULE_CONFLICT", "benchmark.work2_version", f"Work3 requires {WORK2_VERSION}.")
    if benchmark.get("work1_contract_version") != WORK1_CONTRACT_VERSION:
        fail("C_CROSS_MODULE_CONFLICT", "benchmark.work1_contract_version", f"Work3 requires {WORK1_CONTRACT_VERSION}.")
    br = benchmark.get("benchmark_reference") or {}
    if br.get("drive_file_id") != CURRENT_B_DRIVE_FILE_ID:
        fail("C_SOURCE_SOT_MISMATCH", "benchmark.benchmark_reference.drive_file_id", "B formal Drive SOT identity mismatch.")
    if br.get("file_fingerprint_sha256") != CURRENT_B_SOT_SHA256:
        fail("C_SOURCE_FINGERPRINT_MISMATCH", "benchmark.benchmark_reference.file_fingerprint_sha256", "B formal SOT fingerprint mismatch.")
    if (benchmark.get("formal_output_eligibility") or {}).get("scope") == "NONE":
        fail("C_FORMAL_OUTPUT_BLOCKED", "benchmark.formal_output_eligibility", "Work2 benchmark snapshot has no formal output eligibility.")
    rule_ids = set((benchmark.get("proxy_policy") or {}).get("canonical_rule_ids") or [])
    missing = sorted(REQUIRED_WORK3_RULE_IDS - rule_ids)
    if missing:
        fail("C_SCHEMA_REQUIRED_MISSING", "benchmark.proxy_policy.canonical_rule_ids", "Missing Work3-required B canonical rules: " + ", ".join(missing))
    authorized = (benchmark.get("proxy_policy") or {}).get("authorized") or {}
    no_proxy = set((benchmark.get("proxy_policy") or {}).get("no_proxy") or [])
    for a in benchmark.get("assets", []):
        ticker = str(a.get("ticker", "")).upper()
        p = a.get("proxy") or {}
        if p.get("usage") == "USED":
            proxy = p.get("proxy_ticker")
            if p.get("authorization") != "AUTHORIZED" or proxy not in authorized.get(ticker, []):
                fail("C_PROXY_UNAUTHORIZED", f"benchmark.assets[{ticker}].proxy", f"Unauthorized proxy {proxy!r} for {ticker}.")
        if ticker in no_proxy and p.get("usage") == "USED":
            fail("C_PROXY_UNAUTHORIZED", f"benchmark.assets[{ticker}].proxy", f"{ticker} is NO_PROXY but proxy usage was supplied.")
    return ok


def _validate_allocation(allocation: Mapping[str, Any], benchmark: Mapping[str, Any],
                         issues: List[Dict[str, Any]]) -> Tuple[bool, List[Mapping[str, Any]], float]:
    ok = True
    assets = _asset_map(benchmark)
    if not isinstance(allocation.get("allocation_id"), str) or not allocation.get("allocation_id"):
        issues.append(_issue("C_SCHEMA_REQUIRED_MISSING", "BLOCKING", "allocation.allocation_id",
                             "Allocation ID is required for auditable Work3 output.", blocking=True))
        ok = False
    if allocation.get("stage") not in {"CURRENT", "PROPOSED", "FINAL_TARGET"}:
        issues.append(_issue("C_SCHEMA_ENUM_INVALID", "BLOCKING", "allocation.stage",
                             "Allocation stage must be CURRENT, PROPOSED, or FINAL_TARGET.", blocking=True))
        ok = False
    positions = allocation.get("positions")
    if not isinstance(positions, list) or not positions:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.positions",
                             "At least one allocation position is required.", blocking=True))
        return False, [], 0.0
    declared = allocation.get("declared_total_weight") or {}
    if declared.get("value_state") != "KNOWN" or not _is_number(declared.get("value")):
        issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", "allocation.declared_total_weight",
                             "Declared total weight must be KNOWN numeric.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    denom = allocation.get("denominator") or {}
    if denom.get("value_state") != "KNOWN" or not _is_number(denom.get("amount")):
        issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", "allocation.denominator",
                             "Portfolio denominator must be KNOWN numeric.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    elif float(denom.get("amount")) < 0:
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.denominator.amount",
                             "Portfolio denominator cannot be negative.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    currency = denom.get("currency")
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.denominator.currency",
                             "Portfolio denominator currency must be an uppercase three-letter currency code.", blocking=True))
        ok = False
    if denom.get("data_quality") not in {"OK", "FALLBACK_USED"}:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.denominator.data_quality",
                             "Portfolio denominator data quality is not eligible for formal Work3 use.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    if denom.get("freshness") not in {"FRESH", "NOT_APPLICABLE"}:
        issues.append(_issue("C_DATA_STALE", "BLOCKING", "allocation.denominator.freshness",
                             "Portfolio denominator freshness is not eligible for formal Work3 use.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    if not denom.get("source_reference_ids"):
        issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", "allocation.denominator.source_reference_ids",
                             "Portfolio denominator requires at least one source reference for formal Work3 traceability.", blocking=True))
        ok = False
    if declared.get("unit") != "portfolio_weight":
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.declared_total_weight.unit",
                             "Declared total weight unit must be portfolio_weight.", blocking=True))
        ok = False
    if declared.get("data_quality") not in {"OK", "FALLBACK_USED"}:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.declared_total_weight.data_quality",
                             "Declared total weight data quality is not eligible for formal Work3 use.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    if declared.get("freshness") not in {"FRESH", "NOT_APPLICABLE"}:
        issues.append(_issue("C_DATA_STALE", "BLOCKING", "allocation.declared_total_weight.freshness",
                             "Declared total weight freshness is not eligible for formal Work3 use.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    if not declared.get("source_reference_ids"):
        issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", "allocation.declared_total_weight.source_reference_ids",
                             "Declared total weight requires a source reference.", blocking=True))
        ok = False

    effective: List[Mapping[str, Any]] = []
    total = 0.0
    for i, p in enumerate(positions):
        path = f"allocation.positions[{i}]"
        if p.get("value_state") != "KNOWN":
            issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", path + ".value_state",
                                 "Allocation position required by Work3 must be KNOWN.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
            continue
        w = p.get("weight") or {}
        if w.get("value_state") != "KNOWN" or not _is_number(w.get("value")):
            issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", path + ".weight",
                                 "Position weight must be KNOWN numeric.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
            continue
        if w.get("unit") != "portfolio_weight":
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", path + ".weight.unit",
                                 "Position weight unit must be portfolio_weight.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
        if w.get("data_quality") not in {"OK", "FALLBACK_USED"}:
            issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", path + ".weight.data_quality",
                                 "Position weight data quality is not eligible for formal Work3 use.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
        if w.get("freshness") not in {"FRESH", "NOT_APPLICABLE"}:
            issues.append(_issue("C_DATA_STALE", "BLOCKING", path + ".weight.freshness",
                                 "Position weight freshness is not eligible for formal Work3 use.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
        if not w.get("source_reference_ids"):
            issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", path + ".weight.source_reference_ids",
                                 "Position weight requires a source reference.", blocking=True))
            ok = False
        weight = float(w["value"])
        if weight < -WEIGHT_TOLERANCE:
            issues.append(_issue("C_UNSUPPORTED_BY_BASELINE", "BLOCKING", path + ".weight",
                                 "Negative/short allocation weights are not supported by the current Work3 baseline interface.",
                                 blocking=True, source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
        total += weight
        if weight > WEIGHT_TOLERANCE:
            ticker = str(p.get("ticker") or "").upper()
            if not ticker or ticker not in assets:
                issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", path + ".ticker",
                                     f"Ticker {ticker or '<blank>'} is not available in the Work2 benchmark universe.",
                                     blocking=True, source_reference_ids=p.get("source_reference_ids", [])))
                ok = False
            else:
                canonical_currency = assets[ticker].get("base_currency")
                if p.get("base_currency") != canonical_currency:
                    issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", path + ".base_currency",
                                         f"Allocation base_currency {p.get('base_currency')!r} conflicts with Work2 {ticker} base_currency {canonical_currency!r}.",
                                         blocking=True, source_reference_ids=_uniq(p.get("source_reference_ids", []) + [B_SOURCE_ID])))
                    ok = False
            effective.append(p)
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.positions[*].weight",
                             f"Effective allocation weights sum to {total:.12f}, not 1.0; Work3 will not renormalize silently.",
                             blocking=True, source_reference_ids=allocation.get("source_reference_ids", [])))
        ok = False
    if _is_number(declared.get("value")) and abs(float(declared["value"]) - total) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.declared_total_weight.value",
                             f"Declared total weight {float(declared['value']):.12f} disagrees with position sum {total:.12f}.",
                             blocking=True, source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    if _is_number(declared.get("value")) and abs(float(declared["value"]) - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.declared_total_weight.value",
                             "Declared total weight must equal 1.0 for formal portfolio calculations.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    if not effective:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.positions",
                             "No positive-weight effective positions remain for Work3.", blocking=True))
        ok = False
    return ok, effective, total


def _aggregate_effective_positions(effective: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate duplicate allocation lines of the same canonical ticker.

    Multiple tax lots/lines of one instrument are still one return stream and therefore
    must not be misclassified as a mixed-asset portfolio.
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for p in effective:
        ticker = str(p.get("ticker") or "").upper()
        if ticker not in grouped:
            order.append(ticker)
            grouped[ticker] = {
                "ticker": ticker,
                "weight": 0.0,
                "source_reference_ids": [],
            }
        grouped[ticker]["weight"] += float(p["weight"]["value"])
        grouped[ticker]["source_reference_ids"] = _uniq(
            grouped[ticker]["source_reference_ids"] + list(p.get("source_reference_ids", []))
            + list((p.get("weight") or {}).get("source_reference_ids", []))
        )
    return [grouped[t] for t in order]


def _empty_historical(evaluated_at: str) -> Dict[str, Any]:
    m = lambda unit, key, method: _unsupported_metric(unit, source_metric_key=key, method=method,
                                                       rule_references=HISTORICAL_METHOD_RULES,
                                                       evaluated_at=evaluated_at)
    return {
        "long_term_cagr": m("ratio", "tax_after_total_return_central_cagr", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
        "max_drawdown": {w: m("ratio", f"max_drawdown_{w}", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES") for w in WINDOWS},
        "worst_drawdown": {
            "peak_date": m("date", "worst_drawdown_peak_date", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
            "trough_date": m("date", "worst_drawdown_trough_date", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
            "peak_to_trough_calendar_days": m("calendar_days", None, "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
            "recovery_date": m("date", "worst_drawdown_recovery_date", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
            "recovery_period": m("duration_text", "worst_drawdown_recovery_period", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES"),
        },
        **{family: {w: m("ratio", f"{family}_{w}", "MIXED_PORTFOLIO_REQUIRES_ALIGNED_WEALTH_SERIES") for w in WINDOWS}
           for family in RATIO_FAMILIES},
    }


def _single_asset_historical(asset: Mapping[str, Any], evaluated_at: str) -> Dict[str, Any]:
    rules = HISTORICAL_METHOD_RULES
    out: Dict[str, Any] = {
        "long_term_cagr": _source_metric(asset, "tax_after_total_return_central_cagr", evaluated_at=evaluated_at,
                                         method="SINGLE_ASSET_B_CENTRAL_CAGR_PASS_THROUGH", rules=rules),
        "max_drawdown": {}, "worst_drawdown": {}, "sharpe": {}, "sortino": {}, "calmar": {},
    }
    for w in WINDOWS:
        out["max_drawdown"][w] = _source_metric(asset, f"max_drawdown_{w}", evaluated_at=evaluated_at,
                                                  method="SINGLE_ASSET_B_MDD_PASS_THROUGH", rules=rules)
    peak = _source_metric(asset, "worst_drawdown_peak_date", evaluated_at=evaluated_at,
                          method="SINGLE_ASSET_B_DRAWDOWN_DATE_PASS_THROUGH", rules=rules)
    trough = _source_metric(asset, "worst_drawdown_trough_date", evaluated_at=evaluated_at,
                            method="SINGLE_ASSET_B_DRAWDOWN_DATE_PASS_THROUGH", rules=rules)
    recovery_date = _source_metric(asset, "worst_drawdown_recovery_date", evaluated_at=evaluated_at,
                                   method="SINGLE_ASSET_B_DRAWDOWN_DATE_PASS_THROUGH", rules=rules)
    recovery_period = _source_metric(asset, "worst_drawdown_recovery_period", evaluated_at=evaluated_at,
                                     method="SINGLE_ASSET_B_RECOVERY_PASS_THROUGH", rules=rules)
    if (peak["formal_output_eligibility"]["eligible"] and trough["formal_output_eligibility"]["eligible"]
            and peak["value_state"] == trough["value_state"] == "KNOWN"):
        p, t = _parse_date(peak["value"]), _parse_date(trough["value"])
        if p is not None and t is not None and t >= p:
            pt = _derived_metric((t - p).days, "calendar_days", as_of=trough.get("as_of"),
                                 source_reference_ids=_uniq(peak["source_reference_ids"] + trough["source_reference_ids"]),
                                 issue_codes=_uniq(peak["issue_codes"] + trough["issue_codes"]),
                                 data_quality="FALLBACK_USED" if "FALLBACK_USED" in {peak["data_quality"], trough["data_quality"]} else "OK",
                                 freshness="FRESH", method="PEAK_TO_TROUGH_CALENDAR_DAY_DIFFERENCE",
                                 rules=["W2-MET-003", "W2-MET-010"], evaluated_at=evaluated_at,
                                 source_native_status="DERIVED_FROM_B_WORST_DRAWDOWN_DATES")
        else:
            pt = _unsupported_metric("calendar_days", source_metric_key=None, method="PEAK_TO_TROUGH_DATE_VALIDATION_FAILED",
                                     rule_references=["W2-MET-003"], evaluated_at=evaluated_at,
                                     code="C_DATA_INSUFFICIENT")
    else:
        pt = _unsupported_metric("calendar_days", source_metric_key=None, method="PEAK_TO_TROUGH_REQUIRES_ELIGIBLE_B_DATES",
                                 rule_references=["W2-MET-003", "W2-DQ-003"], evaluated_at=evaluated_at,
                                 code="C_DATA_INSUFFICIENT")
    out["worst_drawdown"] = {
        "peak_date": peak, "trough_date": trough, "peak_to_trough_calendar_days": pt,
        "recovery_date": recovery_date, "recovery_period": recovery_period,
    }
    for family in RATIO_FAMILIES:
        for w in WINDOWS:
            out[family][w] = _source_metric(asset, f"{family}_{w}", evaluated_at=evaluated_at,
                                             method=f"SINGLE_ASSET_B_{family.upper()}_PASS_THROUGH", rules=rules)
    return out


def _monetary_drawdown(historical: Mapping[str, Any], *, denominator: Mapping[str, Any],
                       asset: Optional[Mapping[str, Any]], mixed: bool, evaluated_at: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    denom_currency = denominator.get("currency")
    denom_amount = float(denominator.get("amount", 0.0)) if _is_number(denominator.get("amount")) else None
    asset_currency = asset.get("base_currency") if asset is not None else None
    for w in WINDOWS:
        mdd = historical["max_drawdown"][w]
        if mixed:
            out[w] = {
                "loss_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                   method="MIXED_PORTFOLIO_MONETARY_MDD_REQUIRES_PORTFOLIO_MDD",
                                                   rule_references=["W2-MET-002", "W2-TR-004"], evaluated_at=evaluated_at),
                "trough_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                     method="MIXED_PORTFOLIO_MONETARY_MDD_REQUIRES_PORTFOLIO_MDD",
                                                     rule_references=["W2-MET-002", "W2-TR-004"], evaluated_at=evaluated_at),
            }
            continue
        if denom_amount is None:
            out[w] = {
                "loss_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                   method="DENOMINATOR_REQUIRED", rule_references=["W2-MET-002"],
                                                   evaluated_at=evaluated_at, code="C_DATA_UNKNOWN_REQUIRED"),
                "trough_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                     method="DENOMINATOR_REQUIRED", rule_references=["W2-MET-002"],
                                                     evaluated_at=evaluated_at, code="C_DATA_UNKNOWN_REQUIRED"),
            }
            continue
        if denom_currency != asset_currency:
            out[w] = {
                "loss_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                   method="CLIENT_CURRENCY_MDD_REQUIRES_FX_PATH",
                                                   rule_references=["W2-TR-004"], evaluated_at=evaluated_at,
                                                   code="C_FX_REQUIRED_NOT_AVAILABLE"),
                "trough_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                     method="CLIENT_CURRENCY_MDD_REQUIRES_FX_PATH",
                                                     rule_references=["W2-TR-004"], evaluated_at=evaluated_at,
                                                     code="C_FX_REQUIRED_NOT_AVAILABLE"),
            }
            continue
        if mdd["value_state"] == "NOT_APPLICABLE" and mdd["formal_output_eligibility"]["eligible"]:
            out[w] = {
                "loss_amount": _not_applicable_metric(denom_currency, method="MDD_WINDOW_NOT_APPLICABLE",
                                                       source_reference_ids=mdd["source_reference_ids"], rules=["W2-MET-002"],
                                                       evaluated_at=evaluated_at, reason="SOURCE_MDD_NOT_APPLICABLE"),
                "trough_amount": _not_applicable_metric(denom_currency, method="MDD_WINDOW_NOT_APPLICABLE",
                                                         source_reference_ids=mdd["source_reference_ids"], rules=["W2-MET-002"],
                                                         evaluated_at=evaluated_at, reason="SOURCE_MDD_NOT_APPLICABLE"),
            }
            continue
        if not (mdd["formal_output_eligibility"]["eligible"] and mdd["value_state"] == "KNOWN" and _is_number(mdd["value"])):
            out[w] = {
                "loss_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                   method="MONETARY_MDD_REQUIRES_ELIGIBLE_MDD",
                                                   rule_references=["W2-MET-002", "W2-DQ-003"], evaluated_at=evaluated_at,
                                                   code="C_DATA_INSUFFICIENT"),
                "trough_amount": _unsupported_metric(denom_currency, source_metric_key=f"max_drawdown_{w}",
                                                     method="MONETARY_MDD_REQUIRES_ELIGIBLE_MDD",
                                                     rule_references=["W2-MET-002", "W2-DQ-003"], evaluated_at=evaluated_at,
                                                     code="C_DATA_INSUFFICIENT"),
            }
            continue
        dd = float(mdd["value"])
        loss = round(denom_amount * abs(dd), 8)
        trough = round(denom_amount * (1.0 + dd), 8)
        refs = _uniq(list(denominator.get("source_reference_ids", [])) + mdd["source_reference_ids"])
        dq = mdd["data_quality"]
        fresh = mdd["freshness"]
        proxy = mdd["proxy"]
        out[w] = {
            "loss_amount": _derived_metric(loss, denom_currency, as_of=mdd.get("as_of"), source_reference_ids=refs,
                                           issue_codes=mdd["issue_codes"], data_quality=dq, freshness=fresh,
                                           method="PORTFOLIO_DENOMINATOR_X_ABS_SINGLE_ASSET_MDD",
                                           rules=["W2-MET-002", "W2-TR-004"], evaluated_at=evaluated_at,
                                           source_metric_key=f"max_drawdown_{w}", proxy=proxy),
            "trough_amount": _derived_metric(trough, denom_currency, as_of=mdd.get("as_of"), source_reference_ids=refs,
                                             issue_codes=mdd["issue_codes"], data_quality=dq, freshness=fresh,
                                             method="PORTFOLIO_DENOMINATOR_X_ONE_PLUS_SINGLE_ASSET_MDD",
                                             rules=["W2-MET-002", "W2-TR-004"], evaluated_at=evaluated_at,
                                             source_metric_key=f"max_drawdown_{w}", proxy=proxy),
        }
    return out


def _validate_assumption_rate(rate: Mapping[str, Any], scenario: str) -> Tuple[bool, Optional[float], List[str]]:
    errors: List[str] = []
    if not isinstance(rate, Mapping):
        return False, None, ["RATE_OBJECT_REQUIRED"]
    if rate.get("value_state") != "KNOWN" or not _is_number(rate.get("value")):
        errors.append("RATE_NOT_KNOWN_NUMERIC")
        return False, None, errors
    value = float(rate["value"])
    if value < -1.0:
        errors.append("RATE_BELOW_NEGATIVE_100_PERCENT")
    if rate.get("unit") != "annual_return_ratio":
        errors.append("UNIT_MUST_BE_ANNUAL_RETURN_RATIO")
    dq = rate.get("data_quality")
    if not isinstance(dq, str) or dq not in {"OK", "FALLBACK_USED"}:
        errors.append("DATA_QUALITY_INELIGIBLE")
    fresh = rate.get("freshness")
    if not isinstance(fresh, str) or fresh not in {"FRESH", "NOT_APPLICABLE"}:
        errors.append("FRESHNESS_INELIGIBLE")
    if _parse_date(rate.get("as_of")) is None:
        errors.append("AS_OF_VALID_DATE_REQUIRED")
    refs = rate.get("source_reference_ids")
    if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or not x for x in refs):
        errors.append("SOURCE_REFERENCE_REQUIRED")
    return not errors, value, errors


def _assumption_metric(rate: Mapping[str, Any], scenario: str, *, evaluated_at: str,
                       force_ineligible_reasons: Sequence[str] = (),
                       top_source_reference_ids: Sequence[str] = ()) -> Dict[str, Any]:
    rate = rate if isinstance(rate, Mapping) else {}
    ok, value, errors = _validate_assumption_rate(rate, scenario)
    rate_as_of = rate.get("as_of") if _parse_date(rate.get("as_of")) is not None else None
    errors = _uniq(list(errors) + list(force_ineligible_reasons))
    refs = _uniq(_safe_refs(top_source_reference_ids) + _safe_refs(rate.get("source_reference_ids")))
    if (not ok) or force_ineligible_reasons:
        return _metric(
            support_status="SOURCE_INELIGIBLE", value_state="UNKNOWN", value=None,
            unit="annual_return_ratio", as_of=rate_as_of, data_quality="INSUFFICIENT",
            freshness="UNKNOWN", source_reference_ids=refs,
            issue_codes=["C_DATA_INSUFFICIENT"], source_native_status=";".join(errors) or "EXPLICIT_ASSUMPTION_SET_INVALID",
            source_metric_key=None, method="EXPLICIT_PORTFOLIO_SCENARIO_ASSUMPTION",
            rule_references=["W2-DQ-003", "W2-DQ-007"], proxy=None, formal_eligible=False,
            blocking_reasons=["C_DATA_INSUFFICIENT"], evaluated_at=evaluated_at,
        )
    return _metric(
        support_status="SUPPORTED_BY_EXPLICIT_ASSUMPTION", value_state="KNOWN", value=value,
        unit="annual_return_ratio", as_of=rate_as_of, data_quality=rate.get("data_quality", "OK"),
        freshness=rate.get("freshness", "FRESH"), source_reference_ids=refs,
        issue_codes=_safe_refs(rate.get("issue_codes")), source_native_status=(rate.get("source_native_status") if isinstance(rate.get("source_native_status"), str) else "EXPLICIT_ASSUMPTION"),
        source_metric_key=None, method="EXPLICIT_PORTFOLIO_SCENARIO_ASSUMPTION",
        rule_references=["W2-DQ-003", "W2-DQ-007"], proxy=None, formal_eligible=True,
        warning_reasons=_safe_refs(rate.get("issue_codes")), evaluated_at=evaluated_at,
    )


def _validate_assumption_set(assumptions: Mapping[str, Any], currency: str,
                             evaluated_at: str, issues: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """Validate explicit scenario assumptions as one atomic three-rate set.

    The formal interface requires conservative + central + better together. A partially
    valid set must not leak formal projections for only the surviving rates.
    """
    if not isinstance(assumptions, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "ERROR", "scenario_assumptions",
                             "Scenario assumptions must be an object.", blocking=False))
        assumptions = {}

    set_errors: List[str] = []
    assumption_id = assumptions.get("assumption_id")
    if not isinstance(assumption_id, str) or not assumption_id:
        set_errors.append("ASSUMPTION_ID_REQUIRED")
        issues.append(_issue("C_SCHEMA_REQUIRED_MISSING", "ERROR", "scenario_assumptions.assumption_id",
                             "Explicit scenario assumption_id is required.", blocking=False))

    if assumptions.get("currency_basis") != currency:
        set_errors.append("CURRENCY_BASIS_MISMATCH")
        issues.append(_issue("C_FX_REQUIRED_NOT_AVAILABLE", "ERROR", "scenario_assumptions.currency_basis",
                             "Explicit scenario assumptions must be expressed in the portfolio denominator currency basis; Work3 will not invent FX assumptions.",
                             blocking=False, source_reference_ids=_safe_refs(assumptions.get("source_reference_ids"))))

    if _parse_date(assumptions.get("as_of")) is None:
        set_errors.append("ASSUMPTION_AS_OF_REQUIRED")
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "ERROR", "scenario_assumptions.as_of",
                             "Explicit scenario assumptions require a valid ISO date/time as_of.", blocking=False,
                             source_reference_ids=_safe_refs(assumptions.get("source_reference_ids"))))

    top_refs = assumptions.get("source_reference_ids")
    if not isinstance(top_refs, list) or not top_refs or any(not isinstance(x, str) or not x for x in top_refs):
        set_errors.append("ASSUMPTION_SOURCE_REFERENCE_REQUIRED")
        issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "ERROR", "scenario_assumptions.source_reference_ids",
                             "Explicit scenario assumptions require at least one valid top-level source reference.", blocking=False))
        top_refs = []

    raw_rates = assumptions.get("rates")
    if not isinstance(raw_rates, Mapping):
        set_errors.append("RATES_OBJECT_REQUIRED")
        issues.append(_issue("C_SCHEMA_REQUIRED_MISSING", "ERROR", "scenario_assumptions.rates",
                             "Explicit scenario assumptions require conservative, central, and better rates.", blocking=False,
                             source_reference_ids=top_refs))
        raw_rates = {}

    rate_validation: Dict[str, Tuple[bool, Optional[float], List[str]]] = {}
    for scenario in SCENARIOS:
        if scenario not in raw_rates:
            set_errors.append(f"MISSING_RATE:{scenario}")
            issues.append(_issue("C_SCHEMA_REQUIRED_MISSING", "ERROR", f"scenario_assumptions.rates.{scenario}",
                                 f"Explicit scenario assumptions require the {scenario} rate.", blocking=False,
                                 source_reference_ids=top_refs))
            rate_validation[scenario] = (False, None, ["RATE_REQUIRED"])
            continue
        result = _validate_assumption_rate(raw_rates.get(scenario, {}), scenario)
        rate_validation[scenario] = result
        if not result[0]:
            set_errors.append(f"INVALID_RATE:{scenario}")
            issues.append(_issue("C_DATA_INSUFFICIENT", "ERROR", f"scenario_assumptions.rates.{scenario}",
                                 f"Explicit {scenario} rate failed formal validation: {', '.join(result[2])}.", blocking=False,
                                 source_reference_ids=_uniq(_safe_refs(top_refs) + _safe_refs((raw_rates.get(scenario) or {}).get("source_reference_ids"))
                                                           if isinstance(raw_rates.get(scenario), Mapping) else _safe_refs(top_refs))))

    if all(rate_validation.get(s, (False, None, []))[0] for s in SCENARIOS):
        values = [float(rate_validation[s][1]) for s in SCENARIOS]
        if not (values[0] <= values[1] <= values[2]):
            set_errors.append("SCENARIO_ORDER_INVALID")
            issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "ERROR", "scenario_assumptions.rates",
                                 "Scenario ordering must satisfy conservative <= central <= better.", blocking=False,
                                 source_reference_ids=top_refs))

    set_ok = not set_errors
    force = [] if set_ok else ["EXPLICIT_ASSUMPTION_SET_INVALID"] + set_errors
    metrics = {
        s: _assumption_metric(raw_rates.get(s, {}) if isinstance(raw_rates, Mapping) else {}, s,
                              evaluated_at=evaluated_at, force_ineligible_reasons=force,
                              top_source_reference_ids=top_refs)
        for s in SCENARIOS
    }
    return set_ok, metrics

def _projection_metric(initial: float, rate_metric: Mapping[str, Any], years: int, currency: str,
                       denominator_refs: Sequence[str], evaluated_at: str) -> Dict[str, Any]:
    if not (rate_metric["formal_output_eligibility"]["eligible"] and rate_metric["value_state"] == "KNOWN"):
        return _unsupported_metric(currency, source_metric_key=None, method="SCENARIO_PROJECTION_REQUIRES_ELIGIBLE_RATE",
                                   rule_references=["W2-DQ-003", "W2-DQ-007"], evaluated_at=evaluated_at,
                                   code="C_DATA_INSUFFICIENT")
    r = float(rate_metric["value"])
    refs = _uniq(list(denominator_refs) + rate_metric["source_reference_ids"])
    try:
        fv = initial * ((1.0 + r) ** years)
    except (OverflowError, ValueError):
        fv = math.inf
    if not math.isfinite(fv):
        return _metric(
            support_status="SOURCE_INELIGIBLE", value_state="UNKNOWN", value=None, unit=currency,
            as_of=rate_metric.get("as_of"), data_quality="INSUFFICIENT", freshness="UNKNOWN",
            source_reference_ids=refs, issue_codes=["C_STATE_VALUE_INCONSISTENT"],
            source_native_status="NON_FINITE_SCENARIO_PROJECTION", source_metric_key=rate_metric.get("source_metric_key"),
            method="SCENARIO_PROJECTION_NUMERIC_DOMAIN_INVALID",
            rule_references=_uniq(rate_metric.get("rule_references", []) + ["W2-MET-001", "W2-MET-010"]),
            proxy=rate_metric.get("proxy"), formal_eligible=False,
            blocking_reasons=["NON_FINITE_SCENARIO_PROJECTION"], evaluated_at=evaluated_at,
        )
    fv = round(fv, 8)
    return _metric(
        support_status=rate_metric["support_status"], value_state="KNOWN", value=fv, unit=currency,
        as_of=rate_metric.get("as_of"), data_quality=rate_metric.get("data_quality", "OK"),
        freshness=rate_metric.get("freshness", "FRESH"), source_reference_ids=refs,
        issue_codes=rate_metric.get("issue_codes", []), source_native_status="COMPOUNDED_ANNUAL_RETURN_ASSUMPTION",
        source_metric_key=rate_metric.get("source_metric_key"), method="FV_EQUALS_INITIAL_X_ONE_PLUS_R_POWER_N",
        rule_references=_uniq(rate_metric.get("rule_references", []) + ["W2-MET-001", "W2-MET-010"]),
        proxy=rate_metric.get("proxy"), formal_eligible=True, evaluated_at=evaluated_at,
    )

def _planning_scenarios(*, historical: Mapping[str, Any], denominator: Mapping[str, Any],
                        single_asset: Optional[Mapping[str, Any]], assumptions: Optional[Mapping[str, Any]],
                        evaluated_at: str, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    currency = denominator.get("currency")
    initial = float(denominator.get("amount", 0.0)) if _is_number(denominator.get("amount")) else 0.0
    denom_refs = denominator.get("source_reference_ids", [])
    result: Dict[str, Any] = {
        "horizons_years": list(HORIZONS),
        "basis": "NO_FORMAL_ASSUMPTION",
        "assumption_id": None,
        "currency_basis": currency,
        "scenarios": {},
    }
    explicit_usable = False
    explicit_rates: Dict[str, Dict[str, Any]] = {}
    if assumptions is not None:
        set_ok, explicit_rates = _validate_assumption_set(assumptions, currency, evaluated_at, issues)
        explicit_usable = set_ok and all(
            explicit_rates[s]["formal_output_eligibility"]["eligible"] for s in SCENARIOS
        )
        result["basis"] = "EXPLICIT_PORTFOLIO_CURRENCY_ASSUMPTIONS" if explicit_usable else "EXPLICIT_ASSUMPTIONS_INVALID"
        raw_assumption_id = assumptions.get("assumption_id") if isinstance(assumptions, Mapping) else None
        result["assumption_id"] = raw_assumption_id if isinstance(raw_assumption_id, str) and raw_assumption_id else None
        # Output always stays in the portfolio denominator currency. A mismatched or malformed
        # supplied currency_basis is disclosed through issues and never copied into formal output.
        result["currency_basis"] = currency

    if assumptions is None:
        for s in SCENARIOS:
            if s == "central" and single_asset is not None:
                central = deepcopy(historical["long_term_cagr"])
                if central["formal_output_eligibility"]["eligible"] and central["value_state"] == "KNOWN":
                    if single_asset.get("base_currency") == currency:
                        central["method"] = "SINGLE_ASSET_B_CENTRAL_CAGR_AS_PLANNING_RATE"
                        central["unit"] = "annual_return_ratio"
                        result["basis"] = "SINGLE_ASSET_B_CENTRAL_CAGR"
                        rate_metric = central
                    else:
                        rate_metric = _unsupported_metric("annual_return_ratio", source_metric_key="tax_after_total_return_central_cagr",
                                                          method="CLIENT_CURRENCY_PROJECTION_REQUIRES_FX_PATH",
                                                          rule_references=["W2-TR-004"], evaluated_at=evaluated_at,
                                                          code="C_FX_REQUIRED_NOT_AVAILABLE")
                else:
                    rate_metric = central
            else:
                rate_metric = _no_assumption_metric(evaluated_at=evaluated_at, scenario=s)
            result["scenarios"][s] = {
                "annual_return": rate_metric,
                "projections": {str(y): _projection_metric(initial, rate_metric, y, currency, denom_refs, evaluated_at)
                                for y in HORIZONS},
            }
    else:
        for s in SCENARIOS:
            rate_metric = explicit_rates.get(s) or _no_assumption_metric(evaluated_at=evaluated_at, scenario=s)
            result["scenarios"][s] = {
                "annual_return": rate_metric,
                "projections": {str(y): _projection_metric(initial, rate_metric, y, currency, denom_refs, evaluated_at)
                                for y in HORIZONS},
            }
    result["explicit_assumption_formally_usable"] = explicit_usable
    return result

def _component_diagnostics(effective: Sequence[Mapping[str, Any]], assets: Mapping[str, Mapping[str, Any]],
                           evaluated_at: str) -> List[Dict[str, Any]]:
    out = []
    for p in effective:
        ticker = str(p.get("ticker") or "").upper()
        a = assets[ticker]
        weight = float(p["weight"]["value"]) if isinstance(p.get("weight"), Mapping) else float(p.get("weight", 0.0))
        out.append({
            "ticker": ticker,
            "weight": weight,
            "base_currency": a.get("base_currency"),
            "proxy": deepcopy(a.get("proxy")),
            "long_term_cagr": _source_metric(a, "tax_after_total_return_central_cagr", evaluated_at=evaluated_at,
                                              method="COMPONENT_DIAGNOSTIC_ONLY_NOT_PORTFOLIO_AGGREGATION",
                                              rules=HISTORICAL_METHOD_RULES),
            "max_drawdown_inception": _source_metric(a, "max_drawdown_inception", evaluated_at=evaluated_at,
                                                       method="COMPONENT_DIAGNOSTIC_ONLY_NOT_PORTFOLIO_AGGREGATION",
                                                       rules=HISTORICAL_METHOD_RULES),
            "calmar_inception": _source_metric(a, "calmar_inception", evaluated_at=evaluated_at,
                                                method="COMPONENT_DIAGNOSTIC_ONLY_NOT_PORTFOLIO_AGGREGATION",
                                                rules=HISTORICAL_METHOD_RULES),
        })
    return out


def _collect_metric_leaves(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        if {"support_status", "value_state", "formal_output_eligibility"}.issubset(obj.keys()):
            yield obj
        else:
            for v in obj.values():
                yield from _collect_metric_leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _collect_metric_leaves(v)


def evaluate_performance_risk(allocation: Mapping[str, Any], benchmark: Mapping[str, Any], *,
                              scenario_assumptions: Optional[Mapping[str, Any]] = None,
                              evaluated_at: Optional[str] = None) -> Dict[str, Any]:
    """Calculate a Work1-compatible ModuleResult for Work3.

    The function is deterministic except for ``evaluated_at``; callers should supply it for
    auditable checkpoints. It never mutates ``allocation`` or ``benchmark``.
    """
    evaluated_at = evaluated_at or _now_iso()
    issues: List[Dict[str, Any]] = []
    traceability: List[Dict[str, Any]] = []

    benchmark_ok = _validate_benchmark(benchmark, issues)
    allocation_ok, effective, weight_sum = _validate_allocation(allocation, benchmark, issues)
    if not (benchmark_ok and allocation_ok):
        reasons = _uniq(i["code"] for i in issues if i["blocking"])
        issues.append(_issue("C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "performance_risk_result",
                             "Work3 input gate failed; no formal performance/risk result was produced.",
                             blocking=True, source_reference_ids=[B_SOURCE_ID]))
        return {
            "module_name": MODULE_NAME,
            "status": "BLOCKED",
            "formal_output_eligibility": _gate(False, "NONE", blocking_reasons=reasons + ["C_FORMAL_OUTPUT_BLOCKED"],
                                                 evaluated_at=evaluated_at, rules=HISTORICAL_METHOD_RULES),
            "payload": None,
            "issues": issues,
            "traceability": traceability,
        }

    assets = _asset_map(benchmark)
    effective_assets = _aggregate_effective_positions(effective)
    mixed = len(effective_assets) != 1
    single_asset = None if mixed else assets[effective_assets[0]["ticker"]]
    denom = allocation["denominator"]

    if mixed:
        historical = _empty_historical(evaluated_at)
        issues.append(_issue("C_UNSUPPORTED_BY_BASELINE", "ERROR", "payload.historical_performance_risk",
                             "Current Work2 baseline contains per-asset summary metrics but no aligned portfolio total-return wealth series; mixed-portfolio historical CAGR/MDD/recovery/Sharpe/Sortino/Calmar are returned UNKNOWN instead of weighted approximations.",
                             blocking=False, source_reference_ids=[B_SOURCE_ID]))
    else:
        historical = _single_asset_historical(single_asset, evaluated_at)
        p = single_asset.get("proxy") or {}
        if p.get("usage") == "USED":
            issues.append(_issue("C_PROXY_USED", "WARNING", "payload.proxy_disclosures",
                                 f"{single_asset.get('ticker')} uses authorized proxy {p.get('proxy_ticker')} for the B-approved historical scope; proxy results are not represented as target ETF actual history.",
                                 blocking=False, source_reference_ids=single_asset.get("source_reference_ids", [B_SOURCE_ID])))

    monetary = _monetary_drawdown(historical, denominator=denom, asset=single_asset, mixed=mixed,
                                  evaluated_at=evaluated_at)
    if not mixed and single_asset is not None and denom.get("currency") != single_asset.get("base_currency"):
        issues.append(_issue("C_FX_REQUIRED_NOT_AVAILABLE", "ERROR", "payload.monetary_drawdown",
                             "Client-currency historical drawdown amount requires an aligned FX path; Work3 does not assume FX is unchanged.",
                             blocking=False, source_reference_ids=_uniq(denom.get("source_reference_ids", []) + [B_SOURCE_ID])))

    planning = _planning_scenarios(historical=historical, denominator=denom, single_asset=single_asset,
                                   assumptions=scenario_assumptions, evaluated_at=evaluated_at, issues=issues)
    if scenario_assumptions is None and not any(
        m["formal_output_eligibility"]["eligible"] and m["value_state"] == "KNOWN"
        for s in planning["scenarios"].values() for m in [s["annual_return"]]
    ):
        issues.append(_issue("C_UNSUPPORTED_BY_BASELINE", "ERROR", "payload.planning_scenarios",
                             "No formal portfolio-currency conservative/central/better return assumptions are available from the current baseline; Work3 will not invent scenario rates.",
                             blocking=False, source_reference_ids=[B_SOURCE_ID]))

    components = _component_diagnostics(effective_assets, assets, evaluated_at)
    proxy_disclosures = []
    for p in effective_assets:
        ticker = p["ticker"]
        a = assets[ticker]
        pr = deepcopy(a.get("proxy"))
        if pr and pr.get("usage") == "USED":
            proxy_disclosures.append({"ticker": ticker, "weight": float(p["weight"]), "proxy": pr})

    payload = {
        "work3_version": WORK3_VERSION,
        "work2_version": WORK2_VERSION,
        "work1_contract_version": WORK1_CONTRACT_VERSION,
        "allocation_id": allocation.get("allocation_id"),
        "allocation_stage": allocation.get("stage"),
        "allocation_as_of": allocation.get("as_of"),
        "evaluated_at": evaluated_at,
        "methodology": {
            "baseline_capability": "PER_ASSET_SUMMARY_METRICS_NO_ALIGNED_PORTFOLIO_WEALTH_SERIES",
            "historical_portfolio_method": "SINGLE_ASSET_PASS_THROUGH" if not mixed else "UNSUPPORTED_FOR_MIXED_PORTFOLIO",
            "mixed_portfolio_requirement": "ALIGNED_TOTAL_RETURN_WEALTH_SERIES_REQUIRED",
            "weight_renormalization": "PROHIBITED",
            "fx_assumption": "NONE",
            "component_metrics_are_not_portfolio_metrics": True,
            "rule_references": HISTORICAL_METHOD_RULES,
        },
        "portfolio_definition": {
            "denominator": deepcopy(denom),
            "effective_position_count": len(effective_assets),
            "weight_sum": weight_sum,
            "is_single_effective_asset": not mixed,
            "positions": [
                {"ticker": p["ticker"], "weight": float(p["weight"]),
                 "base_currency": assets[p["ticker"]].get("base_currency"),
                 "source_reference_ids": deepcopy(p.get("source_reference_ids", []))}
                for p in effective_assets
            ],
        },
        "historical_performance_risk": historical,
        "monetary_drawdown": monetary,
        "planning_scenarios": planning,
        "component_diagnostics": components,
        "proxy_disclosures": proxy_disclosures,
        "formal_data_gaps": [],
    }
    if mixed:
        payload["formal_data_gaps"].append({
            "code": "C_UNSUPPORTED_BY_BASELINE",
            "scope": "MIXED_PORTFOLIO_HISTORICAL_PERFORMANCE_RISK",
            "required_input": "aligned total-return wealth-index history for all effective positions with a defined rebalance policy",
            "current_behavior": "UNKNOWN_FAIL_CLOSED",
        })
    if scenario_assumptions is None:
        payload["formal_data_gaps"].append({
            "code": "C_UNSUPPORTED_BY_BASELINE",
            "scope": "CONSERVATIVE_CENTRAL_BETTER_PLANNING_RATES",
            "required_input": "traceable portfolio-currency scenario assumptions; B central CAGR may supply central only for an eligible same-currency single asset",
            "current_behavior": "UNKNOWN_FAIL_CLOSED_WHERE_UNSUPPORTED",
        })

    traceability.extend([
        {
            "field_path": "performance_risk_result.payload.historical_performance_risk",
            "owner": "C_INTEGRATION",
            "rule_references": HISTORICAL_METHOD_RULES,
            "source_reference_ids": [B_SOURCE_ID],
            "as_of": benchmark.get("evaluation_date"),
            "data_quality": "OK" if not mixed else "INSUFFICIENT",
            "issue_codes": [] if not mixed else ["C_UNSUPPORTED_BY_BASELINE"],
        },
        {
            "field_path": "performance_risk_result.payload.portfolio_definition",
            "owner": "C_INTEGRATION",
            "rule_references": ["C-W1-v1.0.1", "W2-DQ-007"],
            "source_reference_ids": _uniq(allocation.get("source_reference_ids", [])),
            "as_of": allocation.get("as_of"),
            "data_quality": "OK",
            "issue_codes": [],
        },
    ])
    scenario_refs: List[str] = []
    if isinstance(scenario_assumptions, Mapping):
        scenario_refs.extend(_safe_refs(scenario_assumptions.get("source_reference_ids")))
        raw_rates_for_trace = scenario_assumptions.get("rates")
        if isinstance(raw_rates_for_trace, Mapping):
            for r in raw_rates_for_trace.values():
                if isinstance(r, Mapping):
                    scenario_refs.extend(_safe_refs(r.get("source_reference_ids")))
    scenario_refs = _uniq(scenario_refs)
    traceability.append({
        "field_path": "performance_risk_result.payload.planning_scenarios",
        "owner": "C_INTEGRATION",
        "rule_references": ["W2-MET-001", "W2-DQ-003", "W2-DQ-007", "W2-TR-004"],
        "source_reference_ids": _uniq(scenario_refs + ([B_SOURCE_ID] if not scenario_refs else [])),
        "as_of": (scenario_assumptions.get("as_of") if isinstance(scenario_assumptions, Mapping)
                  and _parse_date(scenario_assumptions.get("as_of")) is not None else
                  (benchmark.get("evaluation_date") if scenario_assumptions is None else None)),
        "data_quality": "OK" if planning.get("explicit_assumption_formally_usable") else "INSUFFICIENT",
        "issue_codes": [] if planning.get("explicit_assumption_formally_usable") else ["C_UNSUPPORTED_BY_BASELINE"],
    })

    formal_leaves = list(_collect_metric_leaves({
        "historical_performance_risk": historical,
        "monetary_drawdown": monetary,
        "planning_scenarios": planning,
    }))
    known_formal = [m for m in formal_leaves
                    if m["formal_output_eligibility"]["eligible"] and m["value_state"] == "KNOWN"]
    ineligible = [m for m in formal_leaves if not m["formal_output_eligibility"]["eligible"]]
    if not known_formal:
        issues.append(_issue("C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "performance_risk_result",
                             "Work3 completed correctly but no numeric formal portfolio result is currently supported by the supplied baseline/assumptions.",
                             blocking=True, source_reference_ids=[B_SOURCE_ID]))
        gate = _gate(False, "NONE", blocking_reasons=["C_FORMAL_OUTPUT_BLOCKED"],
                     warning_reasons=_uniq(i["code"] for i in issues if not i["blocking"]),
                     evaluated_at=evaluated_at, rules=HISTORICAL_METHOD_RULES)
        status = "BLOCKED"
    elif ineligible:
        issues.append(_issue("C_PARTIAL_OUTPUT", "WARNING", "performance_risk_result",
                             "Work3 has formal numeric results, but one or more requested fields are unavailable/ineligible and remain explicitly UNKNOWN/unsupported.",
                             blocking=False, source_reference_ids=[B_SOURCE_ID]))
        gate = _gate(True, "PARTIAL", warning_reasons=_uniq(i["code"] for i in issues),
                     evaluated_at=evaluated_at, rules=HISTORICAL_METHOD_RULES)
        status = "PARTIAL"
    else:
        gate = _gate(True, "FULL", evaluated_at=evaluated_at, rules=HISTORICAL_METHOD_RULES)
        status = "SUCCESS"

    return {
        "module_name": MODULE_NAME,
        "status": status,
        "formal_output_eligibility": gate,
        "payload": payload,
        "issues": issues,
        "traceability": traceability,
    }
