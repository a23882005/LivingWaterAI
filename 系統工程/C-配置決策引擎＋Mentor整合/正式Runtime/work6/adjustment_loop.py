from __future__ import annotations

"""C Work6: Mentor Adjustment Loop + Final Target staging implementation.

Scope:
- client adjustment loop and proposal lineage;
- protected existing individual-stock preference lock;
- confirmed Final Target construction;
- Current / Final Target / Drift snapshot contract;
- fixed six-axis / four-view Radar display contract;
- routing decision: C-only recalculation vs RETURN_TO_V70.

Explicit non-scope:
- no V70 business-rule implementation;
- no V82/V75 deployment logic;
- no Report Engine rendering/recalculation;
- no writes to formal Mentor/B/V70/V82/V75 SOT files.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from work5.core_engine import run_configuration_engine

WORK6_VERSION = "C-W6-v1.0.0"
WORK1_CONTRACT_VERSION = "C-W1-v1.0.1"
EPS = 1e-9
WEIGHT_TOLERANCE = 5e-7

RADAR_AXES: Tuple[Dict[str, Any], ...] = (
    {"axis_id": "BULL_EARLY", "label_zh": "牛市初期", "order": 1},
    {"axis_id": "BULL_MID", "label_zh": "牛市中期", "order": 2},
    {"axis_id": "BULL_LATE", "label_zh": "牛市末期", "order": 3},
    {"axis_id": "BEAR_NON_RECESSION_VALUATION", "label_zh": "非衰退熊市／估值壓縮", "order": 4},
    {"axis_id": "BEAR_RECESSION", "label_zh": "景氣衰退熊市", "order": 5},
    {"axis_id": "FINANCIAL_LIQUIDITY_CRISIS", "label_zh": "金融／流動性危機", "order": 6},
)
RADAR_VIEW_IDS: Tuple[str, ...] = (
    "CURRENT_ATTACK", "TARGET_ATTACK", "CURRENT_DEFENSE", "TARGET_DEFENSE"
)
V70_CHANGE_TYPES = {
    "ASSET_CLASS_FRAMEWORK_CHANGE",
    "FUNDING_HORIZON_CHANGE",
    "WITHDRAWAL_REQUIREMENT_CHANGE",
    "LIFE_STAGE_OR_RISK_CAPACITY_CHANGE",
}


class AdjustmentLoopValidationError(ValueError):
    def __init__(self, issues: Sequence[Mapping[str, Any]]):
        self.issues = [dict(x) for x in issues]
        super().__init__("Work6 request/contract validation failed")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _uniq(seq: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in seq:
        if isinstance(x, str) and x and x not in seen:
            out.append(x); seen.add(x)
    return out


def _issue(code: str, severity: str, field_path: Optional[str], message: str, *,
           blocking: bool = False, source_reference_ids: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "field_path": field_path,
        "message": message,
        "blocking": bool(blocking),
        "source_reference_ids": _uniq(source_reference_ids),
    }


def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _schema_issues(obj: Any, schema: Mapping[str, Any], root: str) -> List[Dict[str, Any]]:
    errors = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path))
    issues: List[Dict[str, Any]] = []
    for e in errors:
        suffix = ".".join(str(x) for x in e.absolute_path)
        path = root + (("." + suffix) if suffix else "")
        issues.append(_issue("C_W6_SCHEMA_INVALID", "BLOCKING", path, e.message, blocking=True))
    return issues


def _validate_dt(value: str, field_path: str) -> None:
    if not isinstance(value, str) or not value:
        raise AdjustmentLoopValidationError([_issue("C_W6_DATETIME_REQUIRED", "BLOCKING", field_path,
                                                    "ISO-8601 datetime is required.", blocking=True)])
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise AdjustmentLoopValidationError([_issue("C_W6_DATETIME_INVALID", "BLOCKING", field_path,
                                                    "Datetime must be ISO-8601 parseable.", blocking=True)]) from e


def _weight(line: Mapping[str, Any]) -> Optional[float]:
    metric = line.get("weight") or {}
    if metric.get("value_state") != "KNOWN":
        return None
    v = metric.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _money_amount(snapshot: Mapping[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    d = snapshot.get("denominator") or {}
    if d.get("value_state") != "KNOWN":
        return None, None
    a = d.get("amount")
    c = d.get("currency")
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not isinstance(c, str):
        return None, None
    return float(a), c


def _bucket(line: Mapping[str, Any]) -> str:
    s = str(line.get("asset_type") or "").strip().lower()
    if any(x in s for x in ("債券", "bond", "fixed income", "fixed_income")):
        return "BOND"
    if any(x in s for x in ("現金", "cash", "dry powder", "dry_powder")):
        return "DRY_POWDER"
    if any(x in s for x in ("股票", "stock", "equity")):
        return "STOCK"
    return "OTHER"


def _is_individual_company_stock(line: Mapping[str, Any]) -> bool:
    s = str(line.get("asset_type") or "").strip().lower()
    if "etf" in s or "基金" in s or "fund" in s:
        return False
    return _bucket(line) == "STOCK"


def _index_positions(snapshot: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in snapshot.get("positions", []):
        if isinstance(p, Mapping) and isinstance(p.get("instrument_id"), str):
            out[p["instrument_id"]] = deepcopy(dict(p))
    return out


def _same_denominator(current: Mapping[str, Any], proposed: Mapping[str, Any]) -> bool:
    ca, cc = _money_amount(current); pa, pc = _money_amount(proposed)
    return ca is not None and pa is not None and cc == pc and abs(ca - pa) <= max(0.01, abs(ca) * 1e-10)


def _append_sources(canonical_input: Dict[str, Any], request_sources: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    existing = {x.get("source_id"): x for x in canonical_input.get("source_references", []) if isinstance(x, Mapping)}
    for raw in request_sources:
        src = deepcopy(dict(raw))
        sid = src.get("source_id")
        if sid in existing and existing[sid] != src:
            issues.append(_issue("C_W6_SOURCE_CONFLICT", "BLOCKING", "adjustment_request.source_references",
                                 f"SourceReference {sid} conflicts with an existing Canonical Input source.", blocking=True,
                                 source_reference_ids=[sid] if isinstance(sid, str) else []))
        elif sid not in existing:
            canonical_input.setdefault("source_references", []).append(src)
            existing[sid] = src
    return issues


def _decision_evidence_ok(decision: Mapping[str, Any], source_ids: set[str]) -> bool:
    refs = decision.get("source_reference_ids") or []
    confirmed_at = decision.get("confirmed_at")
    dt_ok = False
    if isinstance(confirmed_at, str) and confirmed_at:
        try:
            datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
            dt_ok = True
        except ValueError:
            dt_ok = False
    return (
        decision.get("client_explicit_decision") == "TRUE"
        and dt_ok
        and bool(refs) and set(refs).issubset(source_ids)
    )


def _collect_request_source_ids(value: Any) -> List[str]:
    """Collect every explicit source_reference_ids edge in a Work6 request.

    This intentionally does not inspect source_references[*].source_id; those are declarations,
    while this function validates references made by decisions/overrides/radar/confirmation.
    """
    out: List[str] = []
    if isinstance(value, Mapping):
        refs = value.get("source_reference_ids")
        if isinstance(refs, list):
            out.extend(x for x in refs if isinstance(x, str) and x)
        for key, child in value.items():
            if key not in {"source_reference_ids", "source_references"}:
                out.extend(_collect_request_source_ids(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_collect_request_source_ids(child))
    return _uniq(out)


def _request_semantic_issues(request: Mapping[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for field, code in (("weight_overrides", "C_W6_DUPLICATE_WEIGHT_OVERRIDE"),
                        ("preference_decisions", "C_W6_DUPLICATE_PREFERENCE_DECISION")):
        seen: set[str] = set()
        for idx, item in enumerate(request.get(field, [])):
            iid = item.get("instrument_id")
            if iid in seen:
                issues.append(_issue(code, "BLOCKING", f"adjustment_request.{field}.{idx}.instrument_id",
                                     f"Duplicate instrument_id {iid} in one Work6 request is ambiguous and is not applied sequentially.",
                                     blocking=True, source_reference_ids=item.get("source_reference_ids", [])))
            seen.add(iid)

    seen_views: set[str] = set()
    for vi, view in enumerate(request.get("radar_scores", [])):
        vid = view.get("view_id")
        if vid in seen_views:
            issues.append(_issue("C_W6_RADAR_DUPLICATE_VIEW", "BLOCKING",
                                 f"adjustment_request.radar_scores.{vi}.view_id",
                                 f"Duplicate Radar view_id {vid}; Work6 will not silently overwrite one view with another.",
                                 blocking=True, source_reference_ids=view.get("source_reference_ids", [])))
        seen_views.add(vid)
        seen_axes: set[str] = set()
        for ai, score in enumerate(view.get("scores", [])):
            axis_id = score.get("axis_id")
            if axis_id in seen_axes:
                issues.append(_issue("C_W6_RADAR_DUPLICATE_AXIS", "BLOCKING",
                                     f"adjustment_request.radar_scores.{vi}.scores.{ai}.axis_id",
                                     f"Duplicate Radar axis_id {axis_id} inside {vid}; Work6 will not silently overwrite it.",
                                     blocking=True, source_reference_ids=score.get("source_reference_ids", [])))
            seen_axes.add(axis_id)
    return issues


def _extract_previous_preference_state(previous_loop_result: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not previous_loop_result:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for x in previous_loop_result.get("preference_locks", []) if isinstance(previous_loop_result, Mapping) else []:
        if isinstance(x, Mapping) and isinstance(x.get("instrument_id"), str):
            out[x["instrument_id"]] = deepcopy(dict(x))
    return out


def _apply_preference_decisions(current: Mapping[str, Any], request: Mapping[str, Any],
                                previous_loop_result: Optional[Mapping[str, Any]],
                                source_ids: set[str]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    states = _extract_previous_preference_state(previous_loop_result)
    cur = _index_positions(current)
    issues: List[Dict[str, Any]] = []
    for idx, decision in enumerate(request.get("preference_decisions", [])):
        iid = decision.get("instrument_id")
        action = decision.get("action")
        path = f"adjustment_request.preference_decisions.{idx}"
        if iid not in cur:
            issues.append(_issue("C_W6_PREFERENCE_NOT_EXISTING_HOLDING", "BLOCKING", path,
                                 f"Preference Lock may only apply to an existing current holding: {iid}.", blocking=True,
                                 source_reference_ids=decision.get("source_reference_ids", [])))
            continue
        if decision.get("holding_kind") != "INDIVIDUAL_COMPANY_STOCK" or not _is_individual_company_stock(cur[iid]):
            issues.append(_issue("C_W6_PREFERENCE_NOT_INDIVIDUAL_STOCK", "BLOCKING", path,
                                 f"Preference Lock is restricted to an existing individual company stock: {iid}.", blocking=True,
                                 source_reference_ids=decision.get("source_reference_ids", [])))
            continue
        if action in {"LOCK", "UNLOCK"} and not _decision_evidence_ok(decision, source_ids):
            issues.append(_issue("C_W6_CLIENT_EXPLICIT_DECISION_REQUIRED", "BLOCKING", path,
                                 f"{action} requires explicit client decision evidence; UNKNOWN is not treated as False/approval.",
                                 blocking=True, source_reference_ids=decision.get("source_reference_ids", [])))
            continue
        if action == "LOCK":
            cw = _weight(cur[iid])
            if cw is None:
                issues.append(_issue("C_W6_UNKNOWN_CURRENT_WEIGHT", "BLOCKING", path,
                                     f"Current weight for protected holding {iid} is UNKNOWN and cannot be coerced to zero.",
                                     blocking=True, source_reference_ids=decision.get("source_reference_ids", [])))
                continue
            states[iid] = {
                "instrument_id": iid,
                "ticker": cur[iid].get("ticker"),
                "protected_existing_holding": True,
                "client_preference_locked": True,
                "final_target_locked_to_current": True,
                "current_weight": cw,
                "preference_confirmed_at": decision.get("confirmed_at"),
                "preference_source_ids": _uniq(decision.get("source_reference_ids", [])),
                "unlock_confirmed_at": None,
                "unlock_source_ids": [],
            }
        elif action == "UNLOCK":
            old = states.get(iid)
            if not old or old.get("client_preference_locked") is not True:
                issues.append(_issue("C_W6_UNLOCK_WITHOUT_ACTIVE_LOCK", "BLOCKING", path,
                                     f"Cannot unlock {iid}: no active prior Preference Lock exists.", blocking=True,
                                     source_reference_ids=decision.get("source_reference_ids", [])))
                continue
            new = deepcopy(old)
            new["protected_existing_holding"] = False
            new["client_preference_locked"] = False
            new["final_target_locked_to_current"] = False
            new["unlock_confirmed_at"] = decision.get("confirmed_at")
            new["unlock_source_ids"] = _uniq(decision.get("source_reference_ids", []))
            states[iid] = new
        elif action == "NO_CHANGE":
            pass
    return states, issues


def _active_locks(states: Mapping[str, Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    return {k: v for k, v in states.items()
            if v.get("protected_existing_holding") is True
            and v.get("client_preference_locked") is True
            and v.get("final_target_locked_to_current") is True}


def _validate_snapshot_weights(snapshot: Mapping[str, Any], field: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    vals: List[float] = []
    ids = set()
    for idx, p in enumerate(snapshot.get("positions", [])):
        iid = p.get("instrument_id")
        if iid in ids:
            issues.append(_issue("C_W6_DUPLICATE_INSTRUMENT", "BLOCKING", f"{field}.positions.{idx}",
                                 f"Duplicate instrument_id {iid}.", blocking=True))
        ids.add(iid)
        w = _weight(p)
        if w is None:
            issues.append(_issue("C_W6_UNKNOWN_ALLOCATION_WEIGHT", "BLOCKING", f"{field}.positions.{idx}.weight",
                                 f"Weight for {iid} is not KNOWN; Work6 will not coerce UNKNOWN/NONE to zero.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
        elif w < -EPS or w > 1 + EPS:
            issues.append(_issue("C_W6_WEIGHT_OUT_OF_RANGE", "BLOCKING", f"{field}.positions.{idx}.weight",
                                 f"Weight for {iid} must be in [0,1].", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
        else:
            vals.append(w)
    if vals and len(vals) == len(snapshot.get("positions", [])) and abs(sum(vals) - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W6_ALLOCATION_NOT_100_PERCENT", "BLOCKING", field,
                             f"Allocation weights must sum to 1.0; got {sum(vals):.12f}.", blocking=True,
                             source_reference_ids=snapshot.get("source_reference_ids", [])))
    return issues


def _metric_from_template(template: Mapping[str, Any], value: float, evaluated_at: str,
                          source_ids: Sequence[str]) -> Dict[str, Any]:
    x = deepcopy(dict(template))
    x["value_state"] = "KNOWN"
    x["value"] = float(value)
    x["unit"] = x.get("unit") or "portfolio_weight"
    x["as_of"] = evaluated_at
    x["data_quality"] = "OK"
    x["freshness"] = "FRESH"
    x["issue_codes"] = []
    x["source_reference_ids"] = _uniq(list(x.get("source_reference_ids", [])) + list(source_ids))
    x["source_native_status"] = "KNOWN"
    return x


def _money_from_template(template: Mapping[str, Any], amount: float, currency: str, evaluated_at: str,
                         source_ids: Sequence[str]) -> Dict[str, Any]:
    x = deepcopy(dict(template))
    x["value_state"] = "KNOWN"
    x["amount"] = float(amount)
    x["currency"] = currency
    x["as_of"] = evaluated_at
    x["data_quality"] = "OK"
    x["freshness"] = "FRESH"
    x["issue_codes"] = []
    x["source_reference_ids"] = _uniq(list(x.get("source_reference_ids", [])) + list(source_ids))
    return x


def _proposal_id(run_id: str, weights: Mapping[str, float], evaluated_at: str) -> str:
    basis = {"run_id": run_id, "weights": dict(sorted(weights.items())), "evaluated_at": evaluated_at,
             "version": WORK6_VERSION}
    return "C-W6-PROP-" + sha256(_canonical_json(basis).encode()).hexdigest()[:24]


def _final_id(run_id: str, weights: Mapping[str, float], confirmed_at: str) -> str:
    basis = {"run_id": run_id, "weights": dict(sorted(weights.items())), "confirmed_at": confirmed_at,
             "version": WORK6_VERSION}
    return "C-W6-FINAL-" + sha256(_canonical_json(basis).encode()).hexdigest()[:24]


def _build_adjusted_proposal(canonical_input: Mapping[str, Any], request: Mapping[str, Any],
                             preference_states: Mapping[str, Mapping[str, Any]], evaluated_at: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Return adjusted proposal, issues, requires_v70_reconciliation.

    Bucket totals are frozen to the incoming proposal (Work6 never changes V70's large-asset
    framework). Protected stocks are fixed to Current inside their bucket. Explicit overrides
    are exact inside-bucket weights; the remaining unlocked/unoverridden lines absorb the
    residual proportionally. If a lock cannot fit inside the frozen bucket, Work6 routes back
    to V70 instead of silently changing the framework.
    """
    issues: List[Dict[str, Any]] = []
    current_slot = canonical_input["allocations"]["current_allocation"]
    proposed_slot = canonical_input["allocations"]["proposed_allocation"]
    if current_slot.get("value_state") != "KNOWN" or proposed_slot.get("value_state") != "KNOWN":
        issues.append(_issue("C_W6_ALLOCATION_REQUIRED", "BLOCKING", "allocations",
                             "Current and Proposed allocations must both be KNOWN for the adjustment loop.", blocking=True))
        return None, issues, False
    current = current_slot.get("snapshot") or {}; proposed = proposed_slot.get("snapshot") or {}
    issues += _validate_snapshot_weights(current, "allocations.current_allocation.snapshot")
    issues += _validate_snapshot_weights(proposed, "allocations.proposed_allocation.snapshot")
    if not _same_denominator(current, proposed):
        issues.append(_issue("C_W6_DENOMINATOR_MISMATCH", "BLOCKING", "allocations",
                             "Current and Proposed must use the same known portfolio denominator in Work6.", blocking=True))
    if any(i["blocking"] for i in issues):
        return None, issues, False

    cur = _index_positions(current); ref = _index_positions(proposed)
    active = _active_locks(preference_states)
    for iid in active:
        if iid not in cur:
            issues.append(_issue("C_W6_PROTECTED_CURRENT_MISSING", "BLOCKING", "preference_locks",
                                 f"Protected holding {iid} is missing from Current Allocation.", blocking=True))
        elif iid not in ref:
            # Keep the exact instrument metadata from Current; reference proposal weight is zero.
            p = deepcopy(cur[iid])
            p["weight"] = _metric_from_template(p["weight"], 0.0, evaluated_at, p.get("source_reference_ids", []))
            amount, currency = _money_amount(current)
            if amount is not None and currency:
                p["portfolio_amount"] = _money_from_template(p["portfolio_amount"], 0.0, currency, evaluated_at,
                                                              p.get("source_reference_ids", []))
            ref[iid] = p
    if any(i["blocking"] for i in issues):
        return None, issues, False

    bucket_total: Dict[str, float] = {}
    for p in proposed.get("positions", []):
        w = _weight(p)
        if w is None:
            continue
        bucket_total[_bucket(p)] = bucket_total.get(_bucket(p), 0.0) + w

    overrides: Dict[str, float] = {}
    override_sources: Dict[str, List[str]] = {}
    for idx, ov in enumerate(request.get("weight_overrides", [])):
        iid = ov.get("instrument_id"); state = ov.get("value_state")
        if iid not in ref and iid not in cur:
            issues.append(_issue("C_W6_OVERRIDE_INSTRUMENT_UNKNOWN", "BLOCKING", f"adjustment_request.weight_overrides.{idx}",
                                 f"Work6 does not create a new instrument without Canonical allocation metadata: {iid}.", blocking=True,
                                 source_reference_ids=ov.get("source_reference_ids", [])))
            continue
        if state != "KNOWN":
            issues.append(_issue("C_W6_UNKNOWN_ADJUSTMENT_VALUE", "BLOCKING", f"adjustment_request.weight_overrides.{idx}.value_state",
                                 f"Weight override for {iid} is {state}; it will not be coerced to zero/False/Neutral.", blocking=True,
                                 source_reference_ids=ov.get("source_reference_ids", [])))
            continue
        v = ov.get("weight")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < -EPS or v > 1 + EPS:
            issues.append(_issue("C_W6_WEIGHT_OUT_OF_RANGE", "BLOCKING", f"adjustment_request.weight_overrides.{idx}.weight",
                                 f"Weight override for {iid} must be numeric in [0,1].", blocking=True,
                                 source_reference_ids=ov.get("source_reference_ids", [])))
            continue
        if iid in active:
            cw = _weight(cur[iid])
            if cw is not None and abs(float(v) - cw) > WEIGHT_TOLERANCE:
                issues.append(_issue("C_W6_PROTECTED_OVERRIDE_IGNORED", "WARNING", f"adjustment_request.weight_overrides.{idx}",
                                     f"Override for protected {iid} is ignored; Current weight remains the target until explicit unlock.",
                                     source_reference_ids=ov.get("source_reference_ids", [])))
            continue
        overrides[iid] = float(v)
        override_sources[iid] = _uniq(ov.get("source_reference_ids", []))
    if any(i["blocking"] for i in issues):
        return None, issues, False

    all_ids = list(ref)
    by_bucket: Dict[str, List[str]] = {}
    for iid in all_ids:
        by_bucket.setdefault(_bucket(ref[iid]), []).append(iid)

    new_weights: Dict[str, float] = {}
    requires_v70 = False
    for b, ids in by_bucket.items():
        target = bucket_total.get(b, 0.0)
        locked_ids = [iid for iid in ids if iid in active]
        locked_sum = sum(float(active[iid]["current_weight"]) for iid in locked_ids)
        if locked_sum > target + WEIGHT_TOLERANCE:
            requires_v70 = True
            issues.append(_issue("C_W6_PROTECTED_EXCEEDS_V70_BUCKET", "WARNING", "preference_locks",
                                 f"Protected Current weight {locked_sum:.6f} exceeds frozen {b} proposal bucket {target:.6f}; V70 reconciliation is required.",
                                 source_reference_ids=_uniq(x for iid in locked_ids for x in active[iid].get("preference_source_ids", []))))
            continue
        for iid in locked_ids:
            new_weights[iid] = float(active[iid]["current_weight"])
        explicit_ids = [iid for iid in ids if iid not in active and iid in overrides]
        explicit_sum = sum(overrides[iid] for iid in explicit_ids)
        residual = target - locked_sum - explicit_sum
        if residual < -WEIGHT_TOLERANCE:
            issues.append(_issue("C_W6_BUCKET_OVERALLOCATED", "BLOCKING", "adjustment_request.weight_overrides",
                                 f"Explicit weights plus protected weights exceed frozen {b} bucket by {-residual:.6f}.", blocking=True))
            continue
        residual = max(0.0, residual)
        for iid in explicit_ids:
            new_weights[iid] = overrides[iid]
        free_ids = [iid for iid in ids if iid not in active and iid not in overrides]
        raw_sum = sum(max(0.0, _weight(ref[iid]) or 0.0) for iid in free_ids)
        if residual > WEIGHT_TOLERANCE and raw_sum <= EPS:
            issues.append(_issue("C_W6_RESIDUAL_ALLOCATION_UNRESOLVED", "BLOCKING", "allocations.proposed_allocation",
                                 f"Frozen {b} bucket has residual {residual:.6f} but no unlocked reference weight can absorb it.", blocking=True))
            continue
        if free_ids:
            if residual <= WEIGHT_TOLERANCE:
                for iid in free_ids: new_weights[iid] = 0.0
            else:
                factor = residual / raw_sum
                for iid in free_ids:
                    new_weights[iid] = max(0.0, (_weight(ref[iid]) or 0.0) * factor)
    if requires_v70 or any(i["blocking"] for i in issues):
        return None, issues, requires_v70

    total = sum(new_weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W6_FINAL_MATH_NOT_100_PERCENT", "BLOCKING", "draft_allocation",
                             f"Adjusted proposal must sum to 1.0; got {total:.12f}.", blocking=True))
        return None, issues, False

    denom_amount, denom_currency = _money_amount(current)
    assert denom_amount is not None and denom_currency is not None
    req_source_ids = _uniq(x for ov in request.get("weight_overrides", []) for x in ov.get("source_reference_ids", []))
    req_source_ids += _uniq(x for d in request.get("preference_decisions", []) for x in d.get("source_reference_ids", []))
    req_source_ids = _uniq(req_source_ids)
    positions: List[Dict[str, Any]] = []
    for iid in all_ids:
        p = deepcopy(ref[iid]); w = new_weights[iid]
        line_sources = _uniq(list(p.get("source_reference_ids", [])) + req_source_ids + override_sources.get(iid, []))
        if iid in active:
            line_sources = _uniq(line_sources + active[iid].get("preference_source_ids", []))
        p["weight"] = _metric_from_template(p["weight"], w, evaluated_at, line_sources)
        p["portfolio_amount"] = _money_from_template(p["portfolio_amount"], denom_amount * w, denom_currency,
                                                      evaluated_at, line_sources)
        p["source_reference_ids"] = line_sources
        positions.append(p)
    snap = deepcopy(proposed)
    snap["allocation_id"] = _proposal_id(canonical_input["identity"]["run_id"], new_weights, evaluated_at)
    snap["stage"] = "PROPOSED"
    snap["as_of"] = evaluated_at
    snap["denominator"] = deepcopy(current["denominator"])
    snap["denominator"]["as_of"] = evaluated_at
    snap["positions"] = positions
    snap["declared_total_weight"] = _metric_from_template(snap["declared_total_weight"], 1.0, evaluated_at, req_source_ids)
    snap["confirmation_status"] = "PENDING"
    snap["confirmed_at"] = None; snap["confirmed_by"] = None
    snap["source_reference_ids"] = _uniq(list(snap.get("source_reference_ids", [])) + req_source_ids)
    return snap, issues, False


def _confirm_final(proposal: Mapping[str, Any], confirmation: Mapping[str, Any], run_id: str,
                   source_ids: set[str], evaluated_at: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    issues: List[Dict[str, Any]] = []
    if confirmation.get("action") != "CONFIRM":
        return None, issues
    if not _decision_evidence_ok(confirmation, source_ids) or not confirmation.get("confirmed_by"):
        issues.append(_issue("C_W6_FINAL_CONFIRMATION_EVIDENCE_REQUIRED", "BLOCKING", "adjustment_request.confirmation",
                             "Final Target confirmation requires explicit client evidence, confirmed_at, confirmed_by, and a resolvable source.",
                             blocking=True, source_reference_ids=confirmation.get("source_reference_ids", [])))
        return None, issues
    weights = {p["instrument_id"]: _weight(p) for p in proposal.get("positions", [])}
    if any(v is None for v in weights.values()):
        issues.append(_issue("C_W6_UNKNOWN_ALLOCATION_WEIGHT", "BLOCKING", "draft_allocation.positions",
                             "Cannot confirm Final Target while any proposal weight is UNKNOWN.", blocking=True))
        return None, issues
    final = deepcopy(dict(proposal))
    final["allocation_id"] = _final_id(run_id, {k: float(v) for k, v in weights.items()}, confirmation["confirmed_at"])
    final["stage"] = "FINAL_TARGET"
    final["as_of"] = evaluated_at
    final["confirmation_status"] = "CONFIRMED"
    final["confirmed_at"] = confirmation["confirmed_at"]
    final["confirmed_by"] = confirmation["confirmed_by"]
    final["source_reference_ids"] = _uniq(list(final.get("source_reference_ids", [])) + confirmation.get("source_reference_ids", []))
    return final, issues


def _none_slot(reason: str) -> Dict[str, Any]:
    return {"value_state": "NONE", "snapshot": None, "reason": reason}


def _slot(snapshot: Optional[Mapping[str, Any]], reason: Optional[str] = None) -> Dict[str, Any]:
    return {"value_state": "KNOWN", "snapshot": deepcopy(dict(snapshot)), "reason": reason} if snapshot else _none_slot(reason or "Not available")


def _drift_snapshot(current: Mapping[str, Any], final: Optional[Mapping[str, Any]],
                    preference_states: Mapping[str, Mapping[str, Any]], evaluated_at: str) -> Dict[str, Any]:
    if final is None:
        return {
            "value_state": "NONE", "as_of": evaluated_at,
            "denominator": deepcopy(current.get("denominator")), "items": [],
            "renderer_must_not_recompute_final_target": True,
            "reason": "Final Target is not confirmed; formal drift remains NONE rather than substituting Proposed.",
        }
    cur = _index_positions(current); tar = _index_positions(final)
    universe = list(dict.fromkeys(list(cur) + list(tar)))
    items: List[Dict[str, Any]] = []
    active = _active_locks(preference_states)
    for iid in universe:
        cw = _weight(cur[iid]) if iid in cur else 0.0
        tw = _weight(tar[iid]) if iid in tar else 0.0
        # Universe absence is a real zero only for a KNOWN complete allocation, not an UNKNOWN sentinel.
        if cw is None or tw is None:
            items.append({"instrument_id": iid, "ticker": (cur.get(iid) or tar.get(iid) or {}).get("ticker"),
                          "current_weight": {"value_state": "UNKNOWN", "value": None},
                          "final_target_weight": {"value_state": "UNKNOWN", "value": None},
                          "drift": {"value_state": "UNKNOWN", "value": None},
                          "protected": iid in active, "client_facing_action": "UNKNOWN"})
            continue
        drift = float(tw) - float(cw)
        if iid in active:
            # Hard invariant; do not hide a violation.
            if abs(drift) > WEIGHT_TOLERANCE:
                raise RuntimeError(f"Protected holding invariant broken for {iid}: drift={drift}")
            drift = 0.0
            action = "HOLD_PROTECTED"
        elif abs(drift) <= WEIGHT_TOLERANCE:
            drift = 0.0; action = "HOLD"
        elif drift > 0:
            action = "INCREASE_TARGET_WEIGHT"
        else:
            action = "DECREASE_TARGET_WEIGHT"
        items.append({
            "instrument_id": iid,
            "ticker": (cur.get(iid) or tar.get(iid) or {}).get("ticker"),
            "current_weight": {"value_state": "KNOWN", "value": float(cw)},
            "final_target_weight": {"value_state": "KNOWN", "value": float(tw)},
            "drift": {"value_state": "KNOWN", "value": drift},
            "protected": iid in active,
            "client_facing_action": action,
        })
    return {
        "value_state": "KNOWN", "as_of": evaluated_at,
        # Formal Drift uses the exact Final Target denominator object once confirmed,
        # so Current / Final Target / Drift are not merely numerically equivalent.
        "denominator": deepcopy(final.get("denominator")), "items": items,
        "renderer_must_not_recompute_final_target": True,
        "reason": None,
    }


def _radar_snapshot(request: Mapping[str, Any], evaluated_at: str) -> Dict[str, Any]:
    provided: Dict[str, Dict[str, Mapping[str, Any]]] = {}
    for view in request.get("radar_scores", []):
        vid = view.get("view_id")
        provided[vid] = {x.get("axis_id"): x for x in view.get("scores", []) if isinstance(x, Mapping)}
    views: List[Dict[str, Any]] = []
    for vid in RADAR_VIEW_IDS:
        scores: List[Dict[str, Any]] = []
        srcs: List[str] = []
        for ax in RADAR_AXES:
            raw = provided.get(vid, {}).get(ax["axis_id"])
            if raw and raw.get("value_state") == "KNOWN" and isinstance(raw.get("value"), (int, float)) and not isinstance(raw.get("value"), bool):
                score = {"value_state": "KNOWN", "value": float(raw["value"]),
                         "source_reference_ids": _uniq(raw.get("source_reference_ids", []))}
            else:
                # Missing/UNKNOWN stays UNKNOWN; never becomes zero.
                score = {"value_state": "UNKNOWN", "value": None,
                         "source_reference_ids": _uniq((raw or {}).get("source_reference_ids", []))}
            srcs += score["source_reference_ids"]
            scores.append({**ax, "score": score})
        views.append({"view_id": vid, "axes": scores, "source_reference_ids": _uniq(srcs)})
    return {
        "as_of": evaluated_at,
        "axes": [deepcopy(x) for x in RADAR_AXES],
        "views": views,
        "display_requirements": {
            "same_six_axes_for_all_four_views": True,
            "same_axis_order_for_all_four_views": True,
            "six_chinese_labels_directly_visible": True,
            "missing_overlapped_or_unreadable_label_is_formal_report_qa_fail": True,
        },
    }


def validate_radar_display_contract(snapshot: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    expected_axes = [(x["axis_id"], x["label_zh"], x["order"]) for x in RADAR_AXES]
    root_axes = [(x.get("axis_id"), x.get("label_zh"), x.get("order")) for x in snapshot.get("axes", [])]
    if root_axes != expected_axes:
        errors.append("root axes id/label/order mismatch")
    views = snapshot.get("views", [])
    if [x.get("view_id") for x in views] != list(RADAR_VIEW_IDS):
        errors.append("four radar view ids/order mismatch")
    for v in views:
        axes = [(x.get("axis_id"), x.get("label_zh"), x.get("order")) for x in v.get("axes", [])]
        if axes != expected_axes:
            errors.append(f"{v.get('view_id')} axes id/label/order mismatch")
        if any(not isinstance(x.get("label_zh"), str) or not x.get("label_zh").strip() for x in v.get("axes", [])):
            errors.append(f"{v.get('view_id')} label missing/unreadable")
    req = snapshot.get("display_requirements") or {}
    for key in (
        "same_six_axes_for_all_four_views",
        "same_axis_order_for_all_four_views",
        "six_chinese_labels_directly_visible",
        "missing_overlapped_or_unreadable_label_is_formal_report_qa_fail",
    ):
        if req.get(key) is not True:
            errors.append(f"display requirement not enforced: {key}")
    return errors


def _build_history(previous_loop_result: Optional[Mapping[str, Any]], request: Mapping[str, Any],
                   route: str, previous_proposal: Optional[Mapping[str, Any]], current_proposal: Optional[Mapping[str, Any]],
                   evaluated_at: str, status: str) -> List[Dict[str, Any]]:
    hist = deepcopy(previous_loop_result.get("adjustment_history", [])) if previous_loop_result else []
    hist.append({
        "adjustment_id": request["adjustment_id"],
        "evaluated_at": evaluated_at,
        "requested_change_types": list(request.get("requested_change_types", [])),
        "route": route,
        "previous_proposal_id": (previous_proposal or {}).get("allocation_id"),
        "current_proposal_id": (current_proposal or {}).get("allocation_id"),
        "confirmation_action": (request.get("confirmation") or {}).get("action", "KEEP_PENDING"),
        "preference_actions": [{"instrument_id": x.get("instrument_id"), "action": x.get("action")}
                               for x in request.get("preference_decisions", [])],
        "source_reference_ids": _uniq(request.get("source_reference_ids", [])),
        "status": status,
    })
    return hist


def _work6_snapshot_id(canonical_input: Mapping[str, Any], request: Mapping[str, Any],
                       preference_states: Mapping[str, Mapping[str, Any]], current_proposal: Optional[Mapping[str, Any]],
                       final_target: Optional[Mapping[str, Any]], route: str, evaluated_at: str,
                       parent_work6_snapshot_id: Optional[str]) -> str:
    basis = {
        "version": WORK6_VERSION,
        "run_id": canonical_input["identity"]["run_id"],
        "request": request,
        "preference_states": preference_states,
        "current_proposal_id": (current_proposal or {}).get("allocation_id"),
        "final_target_id": (final_target or {}).get("allocation_id"),
        "route": route,
        "evaluated_at": evaluated_at,
        "parent": parent_work6_snapshot_id,
    }
    return "C-W6-" + sha256(_canonical_json(basis).encode()).hexdigest()[:32]


def _validate_output_or_raise(output: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    issues = _schema_issues(output, schema, "work6_output")
    if issues:
        raise RuntimeError("Work6 produced schema-invalid output: " + "; ".join(x["message"] for x in issues[:8]))


def run_mentor_adjustment_loop(canonical_input: Mapping[str, Any], *, adjustment_request: Mapping[str, Any],
                               benchmark_path: str | Path, binding_path: str | Path,
                               input_schema_path: str | Path, output_schema_path: str | Path,
                               work6_request_schema_path: str | Path, work6_output_schema_path: str | Path,
                               evaluated_at: str,
                               previous_loop_result: Optional[Mapping[str, Any]] = None,
                               scenario_assumptions: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Run one deterministic Work6 adjustment iteration.

    The function never edits its callers' objects. V70-impacting requests are routed back to V70
    and do not pretend to recalculate or confirm a Final Target under a stale framework.
    """
    _validate_dt(evaluated_at, "evaluated_at")
    request_schema = _load_json(work6_request_schema_path)
    output_schema = _load_json(work6_output_schema_path)
    req_issues = _schema_issues(adjustment_request, request_schema, "adjustment_request")
    if req_issues:
        raise AdjustmentLoopValidationError(req_issues)
    if previous_loop_result is not None:
        prev_issues = _schema_issues(previous_loop_result, output_schema, "previous_loop_result")
        if prev_issues:
            raise AdjustmentLoopValidationError(prev_issues)

    ci = deepcopy(dict(canonical_input)); req = deepcopy(dict(adjustment_request))
    issues: List[Dict[str, Any]] = []
    issues += _append_sources(ci, req.get("source_references", []))
    source_ids = {x.get("source_id") for x in ci.get("source_references", []) if isinstance(x, Mapping)}
    unresolved_req = set(_collect_request_source_ids(req)) - source_ids
    if unresolved_req:
        issues.append(_issue("C_W6_SOURCE_REFERENCE_MISSING", "BLOCKING", "adjustment_request",
                             f"Unresolved request source ids: {sorted(unresolved_req)}", blocking=True))
    issues += _request_semantic_issues(req)

    current_slot = ci.get("allocations", {}).get("current_allocation", {})
    proposed_slot = ci.get("allocations", {}).get("proposed_allocation", {})
    current = deepcopy(current_slot.get("snapshot")) if current_slot.get("value_state") == "KNOWN" else None
    incoming_proposal = deepcopy(proposed_slot.get("snapshot")) if proposed_slot.get("value_state") == "KNOWN" else None
    if current is None or incoming_proposal is None:
        issues.append(_issue("C_W6_ALLOCATION_REQUIRED", "BLOCKING", "allocations",
                             "Work6 requires KNOWN Current and Proposed snapshots.", blocking=True))

    pref_states: Dict[str, Dict[str, Any]] = {}
    if current is not None:
        pref_states, pref_issues = _apply_preference_decisions(current, req, previous_loop_result, source_ids)
        issues += pref_issues

    requested_types = set(req.get("requested_change_types", []))
    requires_v70 = bool(requested_types & V70_CHANGE_TYPES)
    route_reasons = sorted(requested_types & V70_CHANGE_TYPES)
    previous_proposal = None
    if previous_loop_result and previous_loop_result.get("current_proposal", {}).get("value_state") == "KNOWN":
        previous_proposal = deepcopy(previous_loop_result["current_proposal"]["snapshot"])
    elif incoming_proposal is not None:
        previous_proposal = deepcopy(incoming_proposal)

    blocking = any(x.get("blocking") for x in issues)
    adjusted_proposal: Optional[Dict[str, Any]] = None
    proposal_engine_result: Optional[Dict[str, Any]] = None
    final_target: Optional[Dict[str, Any]] = None
    final_engine_result: Optional[Dict[str, Any]] = None
    route = "RETURN_TO_V70" if requires_v70 else "C_ONLY"

    if not blocking and not requires_v70:
        adjusted_proposal, proposal_issues, pref_requires_v70 = _build_adjusted_proposal(ci, req, pref_states, evaluated_at)
        issues += proposal_issues
        if pref_requires_v70:
            requires_v70 = True; route = "RETURN_TO_V70"; route_reasons.append("PROTECTED_HOLDING_EXCEEDS_FROZEN_ASSET_BUCKET")
            adjusted_proposal = None
        blocking = any(x.get("blocking") for x in issues)

    confirmation = req.get("confirmation") or {"action": "KEEP_PENDING"}
    if requires_v70 and confirmation.get("action") == "CONFIRM":
        issues.append(_issue("C_W6_FINAL_CONFIRMATION_DEFERRED_TO_V70", "WARNING", "adjustment_request.confirmation",
                             "Final Target is not confirmed while a V70 framework refresh is required.",
                             source_reference_ids=confirmation.get("source_reference_ids", [])))

    if not blocking and not requires_v70 and adjusted_proposal is not None:
        # Final confirmation is derived only after protected locks/residual math are applied.
        final_target, final_issues = _confirm_final(adjusted_proposal, confirmation, ci["identity"]["run_id"], source_ids, evaluated_at)
        issues += final_issues
        blocking = any(x.get("blocking") for x in issues)

    if not blocking and not requires_v70 and adjusted_proposal is not None:
        ci["allocations"]["proposed_allocation"] = _slot(adjusted_proposal)
        if final_target is not None:
            ci["allocations"]["final_target"] = _slot(final_target)
            ci["decision_phase"] = "FINAL_TARGET_CONFIRMED"
        else:
            if confirmation.get("action") == "REVOKE":
                if not _decision_evidence_ok(confirmation, source_ids):
                    issues.append(_issue("C_W6_FINAL_REVOCATION_EVIDENCE_REQUIRED", "BLOCKING", "adjustment_request.confirmation",
                                         "Revoking Final Target requires explicit client evidence.", blocking=True,
                                         source_reference_ids=confirmation.get("source_reference_ids", [])))
                ci["allocations"]["final_target"] = _none_slot("Final Target revoked or superseded; client confirmation is required again.")
            elif req.get("requested_change_types") and ci["allocations"]["final_target"].get("value_state") == "KNOWN":
                ci["allocations"]["final_target"] = _none_slot("Prior Final Target superseded by a new proposal; reconfirmation required.")
            ci["decision_phase"] = "PROPOSAL_REVIEW"
        blocking = any(x.get("blocking") for x in issues)

    if not blocking and not requires_v70 and adjusted_proposal is not None:
        parent_c = None
        if previous_loop_result:
            parent_c = (previous_loop_result.get("proposal_engine_result") or {}).get("c_snapshot_id")
        proposal_engine_result = run_configuration_engine(
            ci, allocation_slot="proposed_allocation", benchmark_path=benchmark_path, binding_path=binding_path,
            input_schema_path=input_schema_path, output_schema_path=output_schema_path, evaluated_at=evaluated_at,
            scenario_assumptions=scenario_assumptions, parent_c_snapshot_id=parent_c)
        if final_target is not None:
            final_engine_result = run_configuration_engine(
                ci, allocation_slot="final_target", benchmark_path=benchmark_path, binding_path=binding_path,
                input_schema_path=input_schema_path, output_schema_path=output_schema_path, evaluated_at=evaluated_at,
                scenario_assumptions=scenario_assumptions, parent_c_snapshot_id=proposal_engine_result["c_snapshot_id"])

    if blocking:
        status = "BLOCKED"; route = "BLOCKED"
        current_proposal = None
    elif requires_v70:
        status = "V70_REROUTE_REQUIRED"; current_proposal = previous_proposal
    elif final_target is not None:
        status = "FINAL_TARGET_CONFIRMED"; current_proposal = adjusted_proposal
    else:
        status = "PROPOSAL_READY"; current_proposal = adjusted_proposal

    radar = _radar_snapshot(req, evaluated_at)
    radar_errors = validate_radar_display_contract(radar)
    if radar_errors:
        raise RuntimeError("Work6 internal Radar contract failure: " + "; ".join(radar_errors))

    if current is not None:
        drift = _drift_snapshot(current, final_target, pref_states, evaluated_at)
    else:
        drift = {"value_state": "NONE", "as_of": evaluated_at, "denominator": None, "items": [],
                 "renderer_must_not_recompute_final_target": True, "reason": "Current Allocation unavailable."}

    parent_work6 = previous_loop_result.get("work6_snapshot_id") if previous_loop_result else None
    work6_id = _work6_snapshot_id(ci, req, pref_states, current_proposal, final_target, route, evaluated_at, parent_work6)
    history = _build_history(previous_loop_result, req, route, previous_proposal, current_proposal, evaluated_at, status)
    active = _active_locks(pref_states)
    protected_actions = [{
        "instrument_id": iid,
        "action": "HOLD_PROTECTED",
        "risk_disclosure_separate_from_sell_action": True,
        "note": "Risk/valuation/fundamental warnings may still be shown; Preference Lock itself does not authorize sell/reduce-to-zero.",
    } for iid in sorted(active)]

    mentor_contract = {
        "display_status": status,
        "next_route": route,
        "human_readable_summary": (
            "需先回 V70 更新大類資產框架，再回 C 重新提案。" if route == "RETURN_TO_V70" else
            "Final Target 已由客戶明確確認；報表只能呈現 C Engine 的 Final Target 與 Drift Snapshot。" if status == "FINAL_TARGET_CONFIRMED" else
            "已完成本輪配置重算，等待客戶確認 Final Target。" if status == "PROPOSAL_READY" else
            "本輪存在阻擋條件，未產生新的可用 Final Target。"
        ),
        "report_engine_must_not_recompute_final_target": True,
        "risk_warning_is_not_sell_instruction": True,
        "protected_holding_actions": protected_actions,
        "route_reason_codes": _uniq(route_reasons),
    }

    output = {
        "contract_name": "LivingWaterAI.C.Work6.MentorAdjustmentResult",
        "contract_version": WORK6_VERSION,
        "identity": deepcopy(ci.get("identity", {})),
        "work6_snapshot_id": work6_id,
        "parent_work6_snapshot_id": parent_work6,
        "loop_status": status,
        "route": {"decision": route, "reason_codes": _uniq(route_reasons)},
        "draft_allocation": _slot(adjusted_proposal if status in {"PROPOSAL_READY", "FINAL_TARGET_CONFIRMED"} else None,
                                  "No new draft while blocked/rerouted."),
        "previous_proposal": _slot(previous_proposal, "No previous proposal available."),
        "current_proposal": _slot(current_proposal, "No current proposal available."),
        "final_target": _slot(final_target, "Final Target is not confirmed."),
        "confirmation_status": "CONFIRMED" if final_target is not None else "PENDING",
        "preference_locks": [pref_states[k] for k in sorted(pref_states)],
        "drift_snapshot": drift,
        "radar_snapshot": radar,
        "adjustment_history": history,
        "proposal_engine_result": proposal_engine_result,
        "final_target_engine_result": final_engine_result,
        "mentor_result_contract": mentor_contract,
        "issues": issues,
        "created_at": evaluated_at,
    }
    _validate_output_or_raise(output, output_schema)
    return output
