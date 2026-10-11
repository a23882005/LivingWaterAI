"""LivingWaterAI C Work4 Look-through exposure engine.

Checkpoint-only implementation. It consumes Work1 canonical allocation snapshots and the
Work2 canonical B benchmark snapshot. It never substitutes exposure primitives with a
performance proxy and never infers missing theme/style/market-cap/currency exposures.
"""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

WORK4_VERSION = "C-W4-v1.0.0"
WORK3_VERSION = "C-W3-v1.0.1"
WORK2_VERSION = "C-W2-v1.0.1"
WORK1_CONTRACT_VERSION = "C-W1-v1.0.1"
MODULE_NAME = "lookthrough_exposure_result"
CURRENT_B_DRIVE_FILE_ID = "1vbaPznrzrDwZ17AeLXSLJErMrXwxPl1-"
CURRENT_B_SOT_SHA256 = "f639f5b46b7ff0c7ab2884a0ce01739d852c94f8e383f1966463d48178a77b02"
B_SOURCE_ID = "SRC_B_WORKBOOK"
WEIGHT_TOLERANCE = 1e-9
CONSERVATION_TOLERANCE = 0.005  # 50bp; accommodates official rounded buckets such as 100.04%.

# A complete additive root must conserve to 100% when all represented primitives are formally eligible.
COMPLETE_ROOTS = {
    "SECTOR", "GEO.COUNTRY", "GEO.REGION", "GEO.DEV_STATUS", "GEO.US_FOREIGN",
    "FI.ISSUER_TYPE", "FI.CREDIT", "FI.MATURITY", "FI.UNDERLYING_FUND",
}
PARTIAL_BY_DESIGN_ROOTS = {"HOLDING"}

REQUIRED_VIEWS = {
    "SINGLE_COMPANY": ["HOLDING"],
    "COUNTRY_REGION": ["GEO.COUNTRY", "GEO.REGION", "GEO.DEV_STATUS", "GEO.US_FOREIGN"],
    "INDUSTRY": ["SECTOR"],
    "THEME": [],
    "STYLE_FACTOR": [],
    "MARKET_CAP": [],
    "CURRENCY": [],
}

RULE_IDS = [
    "C-W4-LT-001", "C-W4-LT-002", "C-W4-LT-003", "C-W4-LT-004",
    "C-W4-LT-005", "C-W4-LT-006", "C-W4-LT-007", "C-W4-LT-008",
    "W2-PRX-001", "W2-TAX-001", "W2-DQ-005",
]


def _uniq(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(str(x) for x in values if x))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _issue(code: str, severity: str, field_path: Optional[str], message: str, *,
           blocking: bool = False, owner: str = "C_INTEGRATION",
           source_reference_ids: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "field_path": field_path,
        "message": message,
        "owner": owner,
        "blocking": bool(blocking),
        "source_reference_ids": _uniq(source_reference_ids),
    }


def _gate(eligible: bool, scope: str, *, evaluated_at: str,
          blocking_reasons: Sequence[str] = (), warning_reasons: Sequence[str] = (),
          rules: Sequence[str] = RULE_IDS) -> Dict[str, Any]:
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


def _top_root(exposure_id: str, taxonomy: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    if exposure_id not in taxonomy:
        return None
    cur = exposure_id
    seen = set()
    while cur in taxonomy:
        if cur in seen:
            return None
        seen.add(cur)
        parent = taxonomy[cur].get("parent_id")
        if not parent:
            return cur
        cur = parent
    return None


def _benchmark_maps(benchmark: Mapping[str, Any]) -> Tuple[Dict[str, Mapping[str, Any]], Dict[str, Mapping[str, Any]], Dict[str, List[Mapping[str, Any]]]]:
    if not isinstance(benchmark, Mapping):
        return {}, {}, {}
    raw_assets = benchmark.get("assets", [])
    raw_taxonomy = benchmark.get("exposure_taxonomy", [])
    raw_primitives = benchmark.get("exposure_primitives", [])
    if not isinstance(raw_assets, list):
        raw_assets = []
    if not isinstance(raw_taxonomy, list):
        raw_taxonomy = []
    if not isinstance(raw_primitives, list):
        raw_primitives = []
    assets = {str(a.get("ticker") or "").upper(): a for a in raw_assets if isinstance(a, Mapping) and a.get("ticker")}
    taxonomy = {str(t.get("exposure_id")): t for t in raw_taxonomy if isinstance(t, Mapping) and t.get("exposure_id")}
    by_ticker: Dict[str, List[Mapping[str, Any]]] = {}
    for primitive in raw_primitives:
        if not isinstance(primitive, Mapping):
            continue
        ticker = str(primitive.get("ticker") or "").upper()
        by_ticker.setdefault(ticker, []).append(primitive)
    return assets, taxonomy, by_ticker


def _validate_benchmark(benchmark: Mapping[str, Any], issues: List[Dict[str, Any]]) -> bool:
    if not isinstance(benchmark, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "benchmark",
                             "Benchmark must be an object.", blocking=True))
        return False
    ok = True
    if benchmark.get("work2_version") != WORK2_VERSION:
        issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", "benchmark.work2_version",
                             f"Work4 requires {WORK2_VERSION}.", blocking=True, source_reference_ids=[B_SOURCE_ID]))
        ok = False
    ref = benchmark.get("benchmark_reference") or {}
    if not isinstance(ref, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "benchmark.benchmark_reference",
                             "Benchmark reference must be an object.", blocking=True))
        return False
    if ref.get("drive_file_id") != CURRENT_B_DRIVE_FILE_ID or ref.get("file_fingerprint_sha256") != CURRENT_B_SOT_SHA256:
        issues.append(_issue("C_BENCHMARK_REFERENCE_MISMATCH", "BLOCKING", "benchmark.benchmark_reference",
                             "B benchmark File ID/fingerprint does not match the Work4 bound formal SOT.",
                             blocking=True, source_reference_ids=ref.get("source_reference_ids", [])))
        ok = False
    raw_assets = benchmark.get("assets")
    raw_taxonomy = benchmark.get("exposure_taxonomy")
    raw_primitives = benchmark.get("exposure_primitives")
    if not isinstance(raw_assets, list) or not isinstance(raw_taxonomy, list) or not isinstance(raw_primitives, list):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "benchmark.exposure_*",
                             "Benchmark assets, exposure_taxonomy and exposure_primitives must be arrays.", blocking=True,
                             source_reference_ids=[B_SOURCE_ID]))
        return False
    for label, rows in (("assets", raw_assets), ("exposure_taxonomy", raw_taxonomy), ("exposure_primitives", raw_primitives)):
        if any(not isinstance(row, Mapping) for row in rows):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", f"benchmark.{label}",
                                 f"Every benchmark {label} row must be an object.", blocking=True,
                                 source_reference_ids=[B_SOURCE_ID]))
            return False
    assets, taxonomy, by_ticker = _benchmark_maps(benchmark)
    if not assets or not taxonomy or not raw_primitives:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "benchmark.exposure_*",
                             "Work4 requires non-empty assets, exposure taxonomy and exposure primitives.", blocking=True,
                             source_reference_ids=[B_SOURCE_ID]))
        return False
    asset_keys = [str(a.get("ticker") or "").upper() for a in raw_assets if a.get("ticker")]
    if len(asset_keys) != len(set(asset_keys)):
        issues.append(_issue("C_DUPLICATE_CANONICAL_KEY", "BLOCKING", "benchmark.assets",
                             "Duplicate asset ticker rows are prohibited.", blocking=True, source_reference_ids=[B_SOURCE_ID]))
        ok = False
    taxonomy_keys = [str(t.get("exposure_id")) for t in raw_taxonomy if t.get("exposure_id")]
    if len(taxonomy_keys) != len(set(taxonomy_keys)):
        issues.append(_issue("C_DUPLICATE_CANONICAL_KEY", "BLOCKING", "benchmark.exposure_taxonomy",
                             "Duplicate exposure taxonomy IDs are prohibited.", blocking=True, source_reference_ids=[B_SOURCE_ID]))
        ok = False
    primitive_keys = [(str(p.get("ticker") or "").upper(), str(p.get("exposure_id") or "")) for p in raw_primitives]
    if len(primitive_keys) != len(set(primitive_keys)):
        issues.append(_issue("C_DUPLICATE_EXPOSURE_PRIMITIVE", "BLOCKING", "benchmark.exposure_primitives",
                             "Duplicate (ticker, exposure_id) primitives are prohibited to prevent double counting.",
                             blocking=True, source_reference_ids=[B_SOURCE_ID]))
        ok = False
    for i, p in enumerate(raw_primitives):
        path = f"benchmark.exposure_primitives[{i}]"
        ticker = str(p.get("ticker") or "").upper()
        eid = p.get("exposure_id")
        if ticker not in assets:
            issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", path + ".ticker",
                                 f"Primitive ticker {ticker!r} is absent from benchmark assets.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        if eid not in taxonomy or _top_root(str(eid), taxonomy) is None:
            issues.append(_issue("C_EXPOSURE_TAXONOMY_INVALID", "BLOCKING", path + ".exposure_id",
                                 f"Exposure_ID {eid!r} is missing or has invalid taxonomy ancestry.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        state = p.get("value_state")
        value = p.get("value")
        if state not in {"KNOWN", "UNKNOWN"}:
            issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", path + ".value_state",
                                 "Exposure primitive value_state must be KNOWN or UNKNOWN.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        if state == "KNOWN" and not _is_number(value):
            issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", path + ".value",
                                 "KNOWN exposure primitive must contain a finite numeric value.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        if state != "KNOWN" and value is not None:
            issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", path + ".value",
                                 "Non-KNOWN exposure primitive must not contain a numeric value.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        # Work2 already forbids Look-through proxy substitution; Work4 re-enforces it fail-closed.
        if p.get("proxy_ticker") not in (None, "") or str(p.get("proxy_status_native") or "").upper() not in {"NOT_USED", "NO_PROXY", "", "NONE"}:
            issues.append(_issue("C_LOOKTHROUGH_PROXY_PROHIBITED", "BLOCKING", path + ".proxy_ticker",
                                 "Look-through exposure primitives may not use a performance proxy.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
        primitive_gate = p.get("formal_output_eligibility") or {}
        if not isinstance(primitive_gate, Mapping):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", path + ".formal_output_eligibility",
                                 "Primitive formal_output_eligibility must be an object.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
            primitive_gate = {}
        elig = primitive_gate.get("eligible") is True
        if elig and (state != "KNOWN" or p.get("freshness") == "STALE"):
            issues.append(_issue("C_FORMAL_ELIGIBILITY_INCONSISTENT", "BLOCKING", path + ".formal_output_eligibility",
                                 "Primitive cannot be formally eligible when value is not KNOWN or freshness is STALE.",
                                 blocking=True, source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
    return ok


def _aggregate_positions(allocation: Mapping[str, Any], assets: Mapping[str, Mapping[str, Any]],
                         issues: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]], float, float, str]:
    """Validate formal Work4 allocation and aggregate duplicate ticker lines."""
    ok = True
    if not isinstance(allocation, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation", "Allocation must be an object.", blocking=True))
        return False, [], 0.0, 0.0, ""
    denom = allocation.get("denominator")
    declared = allocation.get("declared_total_weight")
    positions = allocation.get("positions")
    if denom is None:
        denom = {}
    if declared is None:
        declared = {}
    if positions is None:
        positions = []
    if not isinstance(denom, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.denominator",
                             "Portfolio denominator must be an object.", blocking=True))
        return False, [], 0.0, 0.0, ""
    if not isinstance(declared, Mapping):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.declared_total_weight",
                             "Declared total weight must be an object.", blocking=True))
        return False, [], 0.0, 0.0, ""
    if not isinstance(positions, list):
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.positions",
                             "Allocation positions must be an array.", blocking=True))
        return False, [], 0.0, 0.0, ""
    if denom.get("value_state") != "KNOWN" or not _is_number(denom.get("amount")) or float(denom.get("amount")) < 0:
        issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", "allocation.denominator",
                             "Work4 requires a KNOWN non-negative portfolio denominator.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    currency = denom.get("currency")
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "allocation.denominator.currency",
                             "Portfolio denominator currency must be an uppercase three-letter code.", blocking=True))
        ok = False
        currency = ""
    if denom.get("data_quality") not in {"OK", "FALLBACK_USED"} or denom.get("freshness") not in {"FRESH", "NOT_APPLICABLE"}:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.denominator",
                             "Portfolio denominator is not eligible by Data Quality/Freshness gate.", blocking=True,
                             source_reference_ids=denom.get("source_reference_ids", [])))
        ok = False
    if not denom.get("source_reference_ids"):
        issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", "allocation.denominator.source_reference_ids",
                             "Portfolio denominator requires a source reference.", blocking=True))
        ok = False
    if declared.get("value_state") != "KNOWN" or not _is_number(declared.get("value")) or declared.get("unit") != "portfolio_weight":
        issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", "allocation.declared_total_weight",
                             "Declared total weight must be KNOWN numeric portfolio_weight.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    total = 0.0
    for i, p in enumerate(positions):
        path = f"allocation.positions[{i}]"
        if not isinstance(p, Mapping):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", path,
                                 "Allocation position must be an object.", blocking=True))
            ok = False
            continue
        if p.get("value_state") != "KNOWN":
            issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", path + ".value_state",
                                 "Allocation position must be KNOWN.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
            continue
        w = p.get("weight") or {}
        if not isinstance(w, Mapping):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", path + ".weight",
                                 "Position weight must be an object.", blocking=True))
            ok = False
            continue
        if w.get("value_state") != "KNOWN" or not _is_number(w.get("value")) or w.get("unit") != "portfolio_weight":
            issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING", path + ".weight",
                                 "Position weight must be KNOWN finite portfolio_weight.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
            continue
        weight = float(w.get("value"))
        if weight < -WEIGHT_TOLERANCE:
            issues.append(_issue("C_UNSUPPORTED_BY_BASELINE", "BLOCKING", path + ".weight",
                                 "Negative/short allocation weights are not supported by Work4.", blocking=True,
                                 source_reference_ids=w.get("source_reference_ids", [])))
            ok = False
        total += weight
        if weight <= WEIGHT_TOLERANCE:
            continue
        ticker = str(p.get("ticker") or "").upper()
        if ticker not in assets:
            issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", path + ".ticker",
                                 f"Ticker {ticker or '<blank>'} is not in Work2 benchmark universe.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            ok = False
            continue
        if p.get("base_currency") != assets[ticker].get("base_currency"):
            issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", path + ".base_currency",
                                 f"Allocation base_currency conflicts with Work2 {ticker} base_currency.", blocking=True,
                                 source_reference_ids=_uniq(list(p.get("source_reference_ids", [])) + [B_SOURCE_ID])))
            ok = False
        # If an explicit position amount is present, require it to agree with denominator*weight.
        pa = p.get("portfolio_amount") or {}
        if not isinstance(pa, Mapping):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", path + ".portfolio_amount",
                                 "Position portfolio_amount must be an object when present.", blocking=True))
            ok = False
            pa = {}
        if pa.get("value_state") == "KNOWN" and _is_number(pa.get("amount")) and _is_number(denom.get("amount")):
            expected = float(denom.get("amount")) * weight
            if pa.get("currency") != currency or abs(float(pa.get("amount")) - expected) > max(0.01, abs(expected) * 1e-8):
                issues.append(_issue("C_POSITION_AMOUNT_WEIGHT_CONFLICT", "BLOCKING", path + ".portfolio_amount",
                                     "Explicit portfolio_amount conflicts with denominator × allocation weight.", blocking=True,
                                     source_reference_ids=_uniq(list(pa.get("source_reference_ids", [])) + list(w.get("source_reference_ids", [])))))
                ok = False
        if ticker not in grouped:
            grouped[ticker] = {"ticker": ticker, "weight": 0.0, "source_reference_ids": []}
            order.append(ticker)
        grouped[ticker]["weight"] += weight
        grouped[ticker]["source_reference_ids"] = _uniq(
            grouped[ticker]["source_reference_ids"] + list(p.get("source_reference_ids", [])) + list(w.get("source_reference_ids", []))
        )
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.positions[*].weight",
                             f"Allocation weights sum to {total:.12f}, not 1.0; Work4 never silently renormalizes.", blocking=True,
                             source_reference_ids=allocation.get("source_reference_ids", [])))
        ok = False
    if _is_number(declared.get("value")) and (abs(float(declared.get("value")) - total) > WEIGHT_TOLERANCE or abs(float(declared.get("value")) - 1.0) > WEIGHT_TOLERANCE):
        issues.append(_issue("C_STATE_VALUE_INCONSISTENT", "BLOCKING", "allocation.declared_total_weight.value",
                             "Declared total weight must agree with positions and equal 1.0.", blocking=True,
                             source_reference_ids=declared.get("source_reference_ids", [])))
        ok = False
    if not grouped:
        issues.append(_issue("C_DATA_INSUFFICIENT", "BLOCKING", "allocation.positions",
                             "No positive-weight effective positions remain for Work4.", blocking=True))
        ok = False
    return ok, [grouped[t] for t in order], total, float(denom.get("amount") or 0.0), currency


def _asset_class_flags(ticker: str, asset: Mapping[str, Any], primitives: Sequence[Mapping[str, Any]], taxonomy: Mapping[str, Mapping[str, Any]]) -> Tuple[bool, bool]:
    roots = {_top_root(str(p.get("exposure_id")), taxonomy) for p in primitives}
    typ = str(asset.get("asset_type") or "")
    equity = any(r in {"SECTOR", "GEO.COUNTRY", "GEO.DEV_STATUS", "GEO.US_FOREIGN", "HOLDING"} for r in roots) or "股票" in typ
    bond = any((r or "").startswith("FI.") for r in roots) or "債券" in typ or "公債" in typ
    return equity, bond


def _root_applicable(root: str, root_tax: Mapping[str, Any], equity: bool, bond: bool) -> bool:
    category = str(root_tax.get("category") or "")
    if "股票" in category:
        return equity
    if "債券" in category:
        return bond
    if "跨資產" in category:
        return equity or bond
    return True


def _primitive_formal_ok(p: Mapping[str, Any]) -> bool:
    gate = p.get("formal_output_eligibility") or {}
    if not isinstance(gate, Mapping):
        return False
    return (
        p.get("value_state") == "KNOWN"
        and _is_number(p.get("value"))
        and p.get("freshness") != "STALE"
        and gate.get("eligible") is True
        and p.get("proxy_ticker") in (None, "")
        and str(p.get("proxy_status_native") or "").upper() in {"NOT_USED", "NO_PROXY", "", "NONE"}
    )


def _money(amount: Optional[float], currency: str, *, eligible: bool, scope: str, evaluated_at: str,
           refs: Sequence[str], blocking: Sequence[str] = (), warnings: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "value_state": "KNOWN" if amount is not None else "UNKNOWN",
        "amount": round(float(amount), 8) if amount is not None else None,
        "currency": currency if amount is not None else currency or None,
        "source_reference_ids": _uniq(refs),
        "formal_output_eligibility": _gate(eligible, scope, evaluated_at=evaluated_at, blocking_reasons=blocking, warning_reasons=warnings),
    }


def _portfolio_metric(value: Optional[float], *, eligible: bool, scope: str, evaluated_at: str,
                      refs: Sequence[str], state: str = "KNOWN", blocking: Sequence[str] = (), warnings: Sequence[str] = ()) -> Dict[str, Any]:
    if value is None:
        state = "UNKNOWN"
    return {
        "value_state": state,
        "value": round(float(value), 12) if value is not None else None,
        "unit": "portfolio_weight",
        "source_reference_ids": _uniq(refs),
        "formal_output_eligibility": _gate(eligible, scope, evaluated_at=evaluated_at, blocking_reasons=blocking, warning_reasons=warnings),
    }


def _dimension_result(root: str, positions: Sequence[Mapping[str, Any]], assets: Mapping[str, Mapping[str, Any]],
                      taxonomy: Mapping[str, Mapping[str, Any]], by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
                      denominator: float, currency: str, evaluated_at: str, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    root_tax = taxonomy[root]
    aggregated: Dict[str, Dict[str, Any]] = {}
    applicable_weight = represented_weight = formal_complete_weight = blocked_weight = missing_weight = 0.0
    per_position: List[Dict[str, Any]] = []
    root_warning_codes: List[str] = []
    root_blocking_codes: List[str] = []

    for pos in positions:
        ticker = pos["ticker"]
        w = float(pos["weight"])
        tprims = list(by_ticker.get(ticker, []))
        root_prims = [p for p in tprims if _top_root(str(p.get("exposure_id")), taxonomy) == root]
        # Applicability is declared by B Sheet4 presence, including explicit UNKNOWN sentinels.
        # Work4 must not infer that every equity ETF needs every alternative GEO taxonomy or
        # that every bond ETF is a fund-of-funds. Absence therefore means NOT_APPLICABLE
        # to this specific B-declared root, not silently MISSING.
        if not root_prims:
            per_position.append({"ticker": ticker, "allocation_weight": w, "coverage_status": "NOT_APPLICABLE", "primitive_count": 0, "primitive_sum": None, "conservation_status": "NOT_APPLICABLE"})
            continue
        applicable_weight += w
        represented_weight += w
        numeric_sum = 0.0
        all_formal = True
        any_numeric = False
        for p in root_prims:
            eid = str(p.get("exposure_id"))
            formal = _primitive_formal_ok(p)
            if p.get("value_state") == "KNOWN" and _is_number(p.get("value")):
                val = float(p.get("value"))
                numeric_sum += val
                any_numeric = True
                contribution = w * val
                ag = aggregated.setdefault(eid, {
                    "exposure_id": eid,
                    "name": (taxonomy.get(eid) or {}).get("name") or p.get("exposure_name") or eid,
                    "portfolio_weight": 0.0,
                    "contributors": [],
                    "source_reference_ids": [],
                    "all_formal": True,
                    "any_numeric": False,
                    "issue_codes": [],
                    "as_of_values": [],
                })
                ag["portfolio_weight"] += contribution
                ag["any_numeric"] = True
                ag["all_formal"] = ag["all_formal"] and formal
                ag["source_reference_ids"] = _uniq(ag["source_reference_ids"] + list(pos.get("source_reference_ids", [])) + list(p.get("source_reference_ids", [])))
                ag["issue_codes"] = _uniq(ag["issue_codes"] + list(p.get("issue_codes", [])))
                if p.get("as_of"):
                    ag["as_of_values"].append(str(p.get("as_of")))
                ag["contributors"].append({
                    "ticker": ticker,
                    "allocation_weight": round(w, 12),
                    "primitive_weight": round(val, 12),
                    "portfolio_contribution_weight": round(contribution, 12),
                    "primitive_formal_eligible": formal,
                })
            else:
                ag = aggregated.setdefault(eid, {
                    "exposure_id": eid,
                    "name": (taxonomy.get(eid) or {}).get("name") or p.get("exposure_name") or eid,
                    "portfolio_weight": 0.0,
                    "contributors": [],
                    "source_reference_ids": _uniq(list(pos.get("source_reference_ids", [])) + list(p.get("source_reference_ids", []))),
                    "all_formal": False,
                    "any_numeric": False,
                    "issue_codes": _uniq(list(p.get("issue_codes", [])) + ["C_DATA_UNKNOWN_REQUIRED"]),
                    "as_of_values": [str(p.get("as_of"))] if p.get("as_of") else [],
                })
                ag["all_formal"] = False
                ag["contributors"].append({
                    "ticker": ticker, "allocation_weight": round(w, 12), "primitive_weight": None,
                    "portfolio_contribution_weight": None, "primitive_formal_eligible": False,
                })
            if not formal:
                all_formal = False
        conservation_status = "PARTIAL_BY_DESIGN" if root in PARTIAL_BY_DESIGN_ROOTS else "NOT_CHECKED"
        if root in COMPLETE_ROOTS:
            if all_formal and any_numeric:
                if abs(numeric_sum - 1.0) <= CONSERVATION_TOLERANCE:
                    conservation_status = "PASS"
                else:
                    conservation_status = "FAIL"
                    all_formal = False
                    code = "C_EXPOSURE_CONSERVATION_FAILED"
                    root_blocking_codes.append(code)
                    issues.append(_issue(code, "ERROR", f"{root}.{ticker}",
                                         f"{ticker} {root} formally eligible primitives sum to {numeric_sum:.6f}, outside 1±{CONSERVATION_TOLERANCE:.3f}.",
                                         source_reference_ids=[B_SOURCE_ID]))
            else:
                conservation_status = "UNKNOWN"
        if all_formal:
            formal_complete_weight += w
        else:
            blocked_weight += w
            root_warning_codes.append("C_EXPOSURE_PARTIAL_OR_BLOCKED")
        per_position.append({
            "ticker": ticker,
            "allocation_weight": round(w, 12),
            "coverage_status": "FORMAL" if all_formal else "BLOCKED_OR_UNKNOWN",
            "primitive_count": len(root_prims),
            "primitive_sum": round(numeric_sum, 12) if any_numeric else None,
            "conservation_status": conservation_status,
        })

    items: List[Dict[str, Any]] = []
    for eid in sorted(aggregated):
        ag = aggregated[eid]
        numeric = ag["any_numeric"]
        formal = bool(numeric and ag["all_formal"])
        val = ag["portfolio_weight"] if numeric else None
        item_scope = "FULL" if formal else "NONE"
        blocking = [] if formal else ["C_EXPOSURE_PRIMITIVE_INELIGIBLE_OR_UNKNOWN"]
        refs = ag["source_reference_ids"] or [B_SOURCE_ID]
        items.append({
            "exposure_id": eid,
            "name": ag["name"],
            "portfolio_weight": _portfolio_metric(val, eligible=formal, scope=item_scope, evaluated_at=evaluated_at, refs=refs, blocking=blocking),
            "portfolio_amount": _money(denominator * val if val is not None else None, currency, eligible=formal, scope=item_scope, evaluated_at=evaluated_at, refs=refs, blocking=blocking),
            "contributors": ag["contributors"],
            "as_of_min": min(ag["as_of_values"]) if ag["as_of_values"] else None,
            "as_of_max": max(ag["as_of_values"]) if ag["as_of_values"] else None,
            "source_reference_ids": refs,
            "issue_codes": _uniq(ag["issue_codes"] + blocking),
            "formal_output_eligibility": _gate(formal, item_scope, evaluated_at=evaluated_at, blocking_reasons=blocking),
        })

    # A complete-root conservation failure invalidates the root as a formal coherent view.
    # Raw numeric contributions remain in payload for trace/debug, but must not leak as formal output.
    if root_blocking_codes:
        for x in items:
            if x["portfolio_weight"]["value"] is not None:
                x["portfolio_weight"]["formal_output_eligibility"] = _gate(False, "NONE", evaluated_at=evaluated_at, blocking_reasons=root_blocking_codes)
                x["portfolio_amount"]["formal_output_eligibility"] = _gate(False, "NONE", evaluated_at=evaluated_at, blocking_reasons=root_blocking_codes)
                x["formal_output_eligibility"] = _gate(False, "NONE", evaluated_at=evaluated_at, blocking_reasons=root_blocking_codes)
                x["issue_codes"] = _uniq(x["issue_codes"] + root_blocking_codes)
    formal_items = [x for x in items if x["formal_output_eligibility"]["eligible"]]
    has_formal = bool(formal_items)
    if applicable_weight <= WEIGHT_TOLERANCE:
        dimension_scope = "NONE"
        dimension_eligible = False
        dimension_block = ["C_DIMENSION_NOT_APPLICABLE_TO_PORTFOLIO"]
    elif has_formal:
        is_full = (
            root not in PARTIAL_BY_DESIGN_ROOTS
            and missing_weight <= WEIGHT_TOLERANCE
            and blocked_weight <= WEIGHT_TOLERANCE
            and abs(formal_complete_weight - applicable_weight) <= WEIGHT_TOLERANCE
        )
        dimension_scope = "FULL" if is_full else "PARTIAL"
        dimension_eligible = True
        dimension_block = []
    else:
        dimension_scope = "NONE"
        dimension_eligible = False
        dimension_block = ["C_NO_FORMALLY_ELIGIBLE_EXPOSURE_PRIMITIVE"]
    warnings = list(root_warning_codes)
    if root in PARTIAL_BY_DESIGN_ROOTS and has_formal:
        warnings.append("C_PARTIAL_TOP_HOLDINGS_ONLY")
    return {
        "dimension_root": root,
        "dimension_name": root_tax.get("name"),
        "taxonomy_category": root_tax.get("category"),
        "coverage": {
            "applicable_portfolio_weight": round(applicable_weight, 12),
            "represented_portfolio_weight": round(represented_weight, 12),
            "formal_complete_portfolio_weight": round(formal_complete_weight, 12),
            "blocked_or_unknown_portfolio_weight": round(blocked_weight, 12),
            "missing_primitive_portfolio_weight": round(missing_weight, 12),
        },
        "conservation_policy": "PARTIAL_BY_DESIGN" if root in PARTIAL_BY_DESIGN_ROOTS else "COMPLETE_ROOT_SUM_1_WITH_ROUNDING_TOLERANCE" if root in COMPLETE_ROOTS else "NO_FORMAL_CONSERVATION_RULE",
        "conservation_tolerance": CONSERVATION_TOLERANCE if root in COMPLETE_ROOTS else None,
        "per_position_diagnostics": per_position,
        "items": items,
        "formal_output_eligibility": _gate(dimension_eligible, dimension_scope, evaluated_at=evaluated_at,
                                           blocking_reasons=dimension_block, warning_reasons=warnings),
    }


def _concentration(holding_dim: Optional[Mapping[str, Any]], denominator: float, currency: str, evaluated_at: str) -> Dict[str, Any]:
    if not holding_dim:
        return {"basis": "KNOWN_ELIGIBLE_HOLDING_PRIMITIVES_ONLY", "known_holding_coverage_weight": 0.0,
                "top1": None, "top5": [], "top5_known_weight": 0.0,
                "formal_output_eligibility": _gate(False, "NONE", evaluated_at=evaluated_at, blocking_reasons=["C_HOLDING_DIMENSION_UNAVAILABLE"])}
    items = [x for x in holding_dim.get("items", [])
             if x.get("exposure_id") != "HOLDING.UNKNOWN" and x.get("formal_output_eligibility", {}).get("eligible")]
    items.sort(key=lambda x: float(x["portfolio_weight"]["value"]), reverse=True)
    coverage = sum(float(x["portfolio_weight"]["value"]) for x in items)
    def summary(x: Mapping[str, Any]) -> Dict[str, Any]:
        v = float(x["portfolio_weight"]["value"])
        return {"exposure_id": x["exposure_id"], "name": x["name"], "portfolio_weight": round(v,12),
                "portfolio_amount": round(denominator*v,8), "currency": currency}
    top5 = [summary(x) for x in items[:5]]
    has = bool(top5)
    return {
        "basis": "KNOWN_ELIGIBLE_HOLDING_PRIMITIVES_ONLY",
        "interpretation": "Top-holdings concentration is a lower-information view because B HOLDING is intentionally partial, not a full holdings database.",
        "known_holding_coverage_weight": round(coverage, 12),
        "known_holding_coverage_amount": round(denominator*coverage,8),
        "currency": currency,
        "top1": top5[0] if top5 else None,
        "top5": top5,
        "top5_known_weight": round(sum(x["portfolio_weight"] for x in top5),12),
        "formal_output_eligibility": _gate(has, "PARTIAL" if has else "NONE", evaluated_at=evaluated_at,
                                           blocking_reasons=[] if has else ["C_NO_ELIGIBLE_HOLDING_PRIMITIVES"],
                                           warning_reasons=["C_PARTIAL_TOP_HOLDINGS_ONLY"] if has else []),
    }


def _overlap(positions: Sequence[Mapping[str, Any]], by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
             taxonomy: Mapping[str, Mapping[str, Any]], denominator: float, currency: str, evaluated_at: str) -> Dict[str, Any]:
    holdings: Dict[str, Dict[str, float]] = {}
    holding_input_clean: Dict[str, bool] = {}
    for pos in positions:
        ticker = pos["ticker"]
        ps = [p for p in by_ticker.get(ticker, []) if _top_root(str(p.get("exposure_id")), taxonomy) == "HOLDING"]
        h: Dict[str, float] = {}
        clean = bool(ps)
        for p in ps:
            if p.get("exposure_id") == "HOLDING.UNKNOWN":
                clean = False
                continue
            if _primitive_formal_ok(p) and _is_number(p.get("value")):
                if float(p["value"]) < 0:
                    clean = False
                    continue
                h[str(p["exposure_id"])] = float(p["value"])
            else:
                clean = False
        holdings[ticker] = h
        holding_input_clean[ticker] = clean
    pairs: List[Dict[str, Any]] = []
    for a, b in combinations(positions, 2):
        ta, tb = a["ticker"], b["ticker"]
        raw_a = [p for p in by_ticker.get(ta, []) if _top_root(str(p.get("exposure_id")), taxonomy) == "HOLDING"]
        raw_b = [p for p in by_ticker.get(tb, []) if _top_root(str(p.get("exposure_id")), taxonomy) == "HOLDING"]
        if not raw_a or not raw_b:
            continue
        ha, hb = holdings.get(ta, {}), holdings.get(tb, {})
        shared = sorted(set(ha) & set(hb))
        details = []
        duplicate = 0.0
        for eid in shared:
            ca = float(a["weight"]) * ha[eid]
            cb = float(b["weight"]) * hb[eid]
            ov = min(ca, cb)
            duplicate += ov
            details.append({
                "exposure_id": eid,
                "name": (taxonomy.get(eid) or {}).get("name") or eid,
                "portfolio_contribution_a": round(ca,12),
                "portfolio_contribution_b": round(cb,12),
                "duplicated_portfolio_weight_lower_bound": round(ov,12),
                "duplicated_portfolio_amount_lower_bound": round(denominator*ov,8),
            })
        formal = bool(ha and hb and holding_input_clean.get(ta) and holding_input_clean.get(tb))
        pairs.append({
            "ticker_a": ta, "ticker_b": tb,
            "shared_holding_count": len(shared),
            "shared_holdings": details,
            "duplicated_portfolio_weight_lower_bound": round(duplicate,12),
            "duplicated_portfolio_amount_lower_bound": round(denominator*duplicate,8),
            "currency": currency,
            "formal_output_eligibility": _gate(formal, "PARTIAL" if formal else "NONE", evaluated_at=evaluated_at,
                                               blocking_reasons=[] if formal else ["C_HOLDING_INPUT_INCOMPLETE_OR_INELIGIBLE"],
                                               warning_reasons=["C_PARTIAL_TOP_HOLDINGS_ONLY"] if formal else []),
        })
    eligible_pairs = [p for p in pairs if p["formal_output_eligibility"]["eligible"]]
    return {
        "basis": "PAIRWISE_MIN_OF_PORTFOLIO_WEIGHTED_SHARED_CANONICAL_HOLDINGS",
        "interpretation": "Because B stores verified top holdings rather than complete holdings, pairwise overlap is a known-holdings lower bound, not total fund overlap.",
        "pairs": pairs,
        "formal_output_eligibility": _gate(bool(eligible_pairs), "PARTIAL" if eligible_pairs else "NONE", evaluated_at=evaluated_at,
                                           blocking_reasons=[] if eligible_pairs else ["C_NO_ELIGIBLE_PAIRWISE_HOLDING_OVERLAP"],
                                           warning_reasons=["C_PARTIAL_TOP_HOLDINGS_ONLY"] if eligible_pairs else []),
    }


def evaluate_lookthrough_exposure(allocation: Mapping[str, Any], benchmark: Mapping[str, Any], *,
                                  evaluated_at: Optional[str] = None) -> Dict[str, Any]:
    evaluated_at = evaluated_at or _now_iso()
    issues: List[Dict[str, Any]] = []
    bench_ok = _validate_benchmark(benchmark, issues)
    assets, taxonomy, by_ticker = _benchmark_maps(benchmark)
    alloc_ok, positions, total_weight, denominator, currency = _aggregate_positions(allocation, assets, issues)
    if not bench_ok or not alloc_ok:
        return {
            "module_name": MODULE_NAME,
            "status": "BLOCKED",
            "formal_output_eligibility": _gate(False, "NONE", evaluated_at=evaluated_at,
                                               blocking_reasons=[x["code"] for x in issues if x.get("blocking")]),
            "payload": None,
            "issues": issues,
            "traceability": [],
        }

    roots = [t["exposure_id"] for t in benchmark.get("exposure_taxonomy", []) if not t.get("parent_id")]
    dims = [_dimension_result(r, positions, assets, taxonomy, by_ticker, denominator, currency, evaluated_at, issues) for r in roots]
    dim_map = {d["dimension_root"]: d for d in dims}

    required_views = []
    unsupported = []
    for view, view_roots in REQUIRED_VIEWS.items():
        present = [r for r in view_roots if r in dim_map]
        if not view_roots or not present:
            unsupported.append({
                "view": view,
                "reason": "UNSUPPORTED_BY_BASELINE",
                "value_state": "UNKNOWN",
                "source_reference_ids": [B_SOURCE_ID],
                "formal_output_eligibility": _gate(False, "NONE", evaluated_at=evaluated_at,
                                                   blocking_reasons=["C_UNSUPPORTED_BY_BASELINE"]),
            })
            required_views.append({"view": view, "roots": view_roots, "status": "UNSUPPORTED_BY_BASELINE", "formal_output_eligibility": _gate(False,"NONE",evaluated_at=evaluated_at,blocking_reasons=["C_UNSUPPORTED_BY_BASELINE"])})
            issues.append(_issue("C_UNSUPPORTED_BY_BASELINE", "WARNING", f"required_views.{view}",
                                 f"B Sheet3/4 has no formal taxonomy/primitives for {view}; Work4 will not infer it.",
                                 source_reference_ids=[B_SOURCE_ID]))
        else:
            eligible_roots = [r for r in present if dim_map[r]["formal_output_eligibility"]["eligible"]]
            scope = "PARTIAL" if eligible_roots else "NONE"
            required_views.append({
                "view": view, "roots": present,
                "status": "SUPPORTED" if eligible_roots else "NO_FORMAL_ELIGIBLE_DATA",
                "formal_output_eligibility": _gate(bool(eligible_roots), scope, evaluated_at=evaluated_at,
                                                   blocking_reasons=[] if eligible_roots else ["C_NO_FORMALLY_ELIGIBLE_EXPOSURE_PRIMITIVE"]),
            })

    concentration = _concentration(dim_map.get("HOLDING"), denominator, currency, evaluated_at)
    overlap = _overlap(positions, by_ticker, taxonomy, denominator, currency, evaluated_at)

    formal_dims = [d for d in dims if d["formal_output_eligibility"]["eligible"]]
    has_formal = bool(formal_dims)
    formal_data_gaps = []
    for u in unsupported:
        formal_data_gaps.append({"scope": u["view"], "reason": u["reason"], "owner": "B_BENCHMARK"})
    for d in dims:
        if d["formal_output_eligibility"]["scope"] != "FULL" and d["coverage"]["applicable_portfolio_weight"] > WEIGHT_TOLERANCE:
            formal_data_gaps.append({"scope": d["dimension_root"], "reason": "PARTIAL_OR_INELIGIBLE_EXPOSURE_COVERAGE", "owner": "B_BENCHMARK"})

    overall_scope = "PARTIAL" if has_formal else "NONE"
    status = "PARTIAL" if has_formal else "BLOCKED"
    if has_formal:
        issues.append(_issue("C_PARTIAL_OUTPUT", "WARNING", "formal_output_eligibility",
                             "Work4 has formally eligible exposure outputs, but B baseline does not support every required view and/or some dimensions are partial.",
                             source_reference_ids=[B_SOURCE_ID]))
    else:
        issues.append(_issue("C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "formal_output_eligibility",
                             "No formally eligible Look-through exposure output remains for this allocation.", blocking=True,
                             source_reference_ids=[B_SOURCE_ID]))

    allocation_refs = _uniq(allocation.get("source_reference_ids", []) + (allocation.get("denominator") or {}).get("source_reference_ids", []))
    traceability = [
        {"field_path": "payload.taxonomy_dimensions", "owner": "C_INTEGRATION", "rule_references": ["C-W4-LT-001","C-W4-LT-002","W2-TAX-001","W2-PRX-001"],
         "source_reference_ids": _uniq([B_SOURCE_ID] + allocation_refs), "as_of": evaluated_at, "data_quality": "OK" if has_formal else "INSUFFICIENT", "issue_codes": [] if has_formal else ["C_FORMAL_OUTPUT_BLOCKED"]},
        {"field_path": "payload.concentration", "owner": "C_INTEGRATION", "rule_references": ["C-W4-LT-006"],
         "source_reference_ids": _uniq([B_SOURCE_ID] + allocation_refs), "as_of": evaluated_at, "data_quality": "OK" if concentration["formal_output_eligibility"]["eligible"] else "INSUFFICIENT", "issue_codes": concentration["formal_output_eligibility"]["warning_reasons"]},
        {"field_path": "payload.overlap", "owner": "C_INTEGRATION", "rule_references": ["C-W4-LT-007"],
         "source_reference_ids": _uniq([B_SOURCE_ID] + allocation_refs), "as_of": evaluated_at, "data_quality": "OK" if overlap["formal_output_eligibility"]["eligible"] else "INSUFFICIENT", "issue_codes": overlap["formal_output_eligibility"]["warning_reasons"]},
    ]

    payload = {
        "work4_version": WORK4_VERSION,
        "work3_version_inherited": WORK3_VERSION,
        "work2_version": WORK2_VERSION,
        "work1_contract_version": WORK1_CONTRACT_VERSION,
        "allocation_id": allocation.get("allocation_id"),
        "stage": allocation.get("stage"),
        "evaluated_at": evaluated_at,
        "portfolio_denominator": {"amount": round(denominator,8), "currency": currency},
        "portfolio_total_weight": round(total_weight,12),
        "methodology": {
            "canonical_formula": "portfolio_exposure = sum(allocation_weight * B_exposure_primitive)",
            "amount_formula": "portfolio_exposure_amount = portfolio_denominator * portfolio_exposure",
            "weight_renormalization": "PROHIBITED",
            "lookthrough_proxy_substitution": "PROHIBITED",
            "legal_negative_or_over_100_primitive": "PRESERVE_IF_B_FORMALLY_ELIGIBLE_AND_COMPLETE_ROOT_CONSERVES",
            "complete_root_conservation": f"sum primitives = 1 ± {CONSERVATION_TOLERANCE}",
            "holding_scope": "VERIFIED_TOP_HOLDINGS_PARTIAL_DIMENSION",
            "overlap_scope": "KNOWN_HOLDINGS_LOWER_BOUND_ONLY",
            "unsupported_required_views": "RETURN_UNKNOWN_UNSUPPORTED_BY_BASELINE_NEVER_INFER",
        },
        "required_views": required_views,
        "taxonomy_dimensions": dims,
        "concentration": concentration,
        "overlap": overlap,
        "unsupported_required_views": unsupported,
        "formal_data_gaps": formal_data_gaps,
    }
    return {
        "module_name": MODULE_NAME,
        "status": status,
        "formal_output_eligibility": _gate(has_formal, overall_scope, evaluated_at=evaluated_at,
                                           blocking_reasons=[] if has_formal else ["C_FORMAL_OUTPUT_BLOCKED"],
                                           warning_reasons=["C_PARTIAL_OUTPUT"] if has_formal else []),
        "payload": payload,
        "issues": issues,
        "traceability": traceability,
    }
