from __future__ import annotations

"""C Work7: V70 asset-framework integration with locked-first residual allocation.

Scope
-----
* Consume (never recompute) the V70 strategic/tactical asset framework already carried
  by the C Canonical Input.
* Preserve Work6 client-confirmed Final Target semantics and Preference Locks.
* Lock protected existing individual-stock weights first; allocate only residual weight
  inside the same V70 asset bucket.
* Preserve Work6 Drift and Radar snapshots byte-for-structure (deep copy; no renderer
  recomputation contract is retained).
* Enforce same-run lineage and fail closed on stale/insufficient/cross-run V70 input.
* Stop at ABC PM Contract/Schema Gate.  No V82/V75 runtime deployment is performed.

Non-scope
---------
* No V70 Macro Score / mSafe / CAP / Strategic Risk Budget calculations.
* No V82/V75 deployment rules.
* No Report Engine drawing or target/drift recomputation.
* No writes to formal B/V70/V82/V75/Mentor/ABC SOT files.
"""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from work6.adjustment_loop import RADAR_AXES, RADAR_VIEW_IDS, validate_radar_display_contract

WORK7_VERSION = "C-W7-v1.2.0"
FUNDING_CONTEXT_VERSION = "C-W7-FUND-v1.0.0"
FUNDING_DOMAINS = ("TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER")
EPS = 1e-9
WEIGHT_TOLERANCE = 5e-7

V70_BUCKET_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("STOCK", "stock_tactical_weight"),
    ("BOND", "bond_tactical_weight"),
    ("V70_ORIGINAL_DRY_POWDER", "v70_original_dry_powder_weight"),
)


class Work7ValidationError(ValueError):
    def __init__(self, issues: Sequence[Mapping[str, Any]]):
        self.issues = [dict(x) for x in issues]
        super().__init__("Work7 input/contract validation failed")


@lru_cache(maxsize=16)
def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _uniq(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in values:
        if isinstance(x, str) and x and x not in seen:
            out.append(x)
            seen.add(x)
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


def _schema_issues(obj: Any, schema: Mapping[str, Any], root: str, code: str) -> List[Dict[str, Any]]:
    errs = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path))
    out: List[Dict[str, Any]] = []
    for e in errs:
        suffix = ".".join(str(x) for x in e.absolute_path)
        path = root + (("." + suffix) if suffix else "")
        out.append(_issue(code, "BLOCKING", path, e.message, blocking=True))
    return out


def _validate_dt(value: str, field_path: str) -> None:
    if not isinstance(value, str) or not value:
        raise Work7ValidationError([_issue("C_W7_DATETIME_REQUIRED", "BLOCKING", field_path,
                                           "ISO-8601 datetime is required.", blocking=True)])
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise Work7ValidationError([_issue("C_W7_DATETIME_INVALID", "BLOCKING", field_path,
                                           "Datetime must be ISO-8601 parseable.", blocking=True)]) from e


def _metric_value(metric: Mapping[str, Any]) -> Optional[float]:
    if not isinstance(metric, Mapping) or metric.get("value_state") != "KNOWN":
        return None
    v = metric.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    fv = float(v)
    if not math.isfinite(fv):
        return None
    return fv


def _weight(line: Mapping[str, Any]) -> Optional[float]:
    return _metric_value(line.get("weight") or {})


def _bucket(line: Mapping[str, Any]) -> str:
    s = str(line.get("asset_type") or "").strip().lower()
    # Functional dry-powder role must outrank security wrapper.  A future SGOV dry
    # sub-account can therefore carry an asset_type containing "dry powder" even if
    # the underlying instrument is a bond ETF.
    if any(x in s for x in ("dry powder", "dry_powder", "等待資金", "子彈", "現金", "cash")):
        return "V70_ORIGINAL_DRY_POWDER"
    if any(x in s for x in ("債券", "bond", "fixed income", "fixed_income")):
        return "BOND"
    if any(x in s for x in ("股票", "stock", "equity")):
        return "STOCK"
    return "UNKNOWN"


def _active_locks(work6_result: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for x in work6_result.get("preference_locks", []):
        if not isinstance(x, Mapping):
            continue
        if (x.get("protected_existing_holding") is True
                and x.get("client_preference_locked") is True
                and x.get("final_target_locked_to_current") is True
                and isinstance(x.get("instrument_id"), str)):
            out[x["instrument_id"]] = x
    return out


def _index_positions(snapshot: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    out: Dict[str, Mapping[str, Any]] = {}
    for p in snapshot.get("positions", []):
        if isinstance(p, Mapping) and isinstance(p.get("instrument_id"), str):
            out[p["instrument_id"]] = p
    return out


def _source_ids(canonical_input: Mapping[str, Any]) -> set[str]:
    return {
        x.get("source_id") for x in canonical_input.get("source_references", [])
        if isinstance(x, Mapping) and isinstance(x.get("source_id"), str)
    }


def _snapshot_id(canonical_input: Mapping[str, Any], work6_result: Mapping[str, Any], *,
                 evaluated_at: str, status: str, route: str,
                 integrated_asset_framework: Mapping[str, Any],
                 funding_context_snapshot: Mapping[str, Any]) -> str:
    basis = {
        "version": WORK7_VERSION,
        "identity": canonical_input.get("identity"),
        "work6_snapshot_id": work6_result.get("work6_snapshot_id"),
        "v70_snapshot_id": canonical_input.get("v70_asset_framework", {}).get("upstream_v70_snapshot_id"),
        "evaluated_at": evaluated_at,
        "status": status,
        "route": route,
        "framework": integrated_asset_framework,
        "funding_context_snapshot": funding_context_snapshot,
    }
    return "C-W7-" + sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:32]


def _current_allocation_snapshot(work6_result: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Return the Work6 engine-lineage Current Allocation only when it is KNOWN.

    Work7 must independently tie Preference Lock / Drift Current values back to the
    actual Current Allocation snapshot instead of trusting duplicated numeric fields.
    """
    engine = work6_result.get("final_target_engine_result") or {}
    slot = (engine.get("allocations") or {}).get("current_allocation") if isinstance(engine, Mapping) else None
    if not isinstance(slot, Mapping) or slot.get("value_state") != "KNOWN":
        return None
    snap = slot.get("snapshot")
    return snap if isinstance(snap, Mapping) else None


def _is_existing_individual_stock(line: Mapping[str, Any]) -> bool:
    asset_type = str(line.get("asset_type") or "").strip().lower()
    is_stock = any(x in asset_type for x in ("股票", "stock", "equity"))
    is_fund = any(x in asset_type for x in ("etf", "基金", "fund"))
    return is_stock and not is_fund


def validate_protected_holding_contract(work6_result: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    final_slot = work6_result.get("final_target") or {}
    drift = work6_result.get("drift_snapshot") or {}
    if work6_result.get("confirmation_status") != "CONFIRMED" or final_slot.get("value_state") != "KNOWN":
        return ["Final Target is not confirmed/KNOWN"]
    final = final_slot.get("snapshot") or {}
    current = _current_allocation_snapshot(work6_result)
    if current is None:
        return ["Current Allocation engine lineage is missing/UNKNOWN"]
    cur = _index_positions(current)
    fin = _index_positions(final)
    drift_items = {x.get("instrument_id"): x for x in drift.get("items", []) if isinstance(x, Mapping)}
    for iid, lock in _active_locks(work6_result).items():
        if iid not in cur:
            errors.append(f"protected {iid} missing from Current Allocation")
            continue
        if not _is_existing_individual_stock(cur[iid]):
            errors.append(f"protected {iid} is not an existing individual company stock")
        actual_cw = _weight(cur[iid])
        lock_cw = lock.get("current_weight")
        if (actual_cw is None or isinstance(lock_cw, bool)
                or not isinstance(lock_cw, (int, float)) or not math.isfinite(float(lock_cw))):
            errors.append(f"protected {iid} actual/lock Current weight is not KNOWN finite numeric")
            continue
        if abs(float(lock_cw) - actual_cw) > WEIGHT_TOLERANCE:
            errors.append(f"protected {iid} Preference Lock Current != actual Current Allocation")
        if iid not in fin:
            errors.append(f"protected {iid} missing from Final Target")
            continue
        fw = _weight(fin[iid])
        if fw is None:
            errors.append(f"protected {iid} Final Target is not KNOWN finite numeric")
            continue
        if abs(actual_cw - fw) > WEIGHT_TOLERANCE:
            errors.append(f"protected {iid} Final Target != actual Current Allocation")
        di = drift_items.get(iid)
        if not di:
            errors.append(f"protected {iid} missing from Drift Snapshot")
            continue
        if di.get("protected") is not True:
            errors.append(f"protected {iid} drift protected flag != true")
        dcw = _metric_value(di.get("current_weight") or {})
        dtw = _metric_value(di.get("final_target_weight") or {})
        dv = _metric_value(di.get("drift") or {})
        if dcw is None or abs(dcw - actual_cw) > WEIGHT_TOLERANCE:
            errors.append(f"protected {iid} Drift Current != actual Current Allocation")
        if dtw is None or abs(dtw - fw) > WEIGHT_TOLERANCE:
            errors.append(f"protected {iid} Drift Final Target != Work6 Final Target")
        if dv is None or abs(dv) > WEIGHT_TOLERANCE:
            errors.append(f"protected {iid} Drift != 0")
        if di.get("client_facing_action") != "HOLD_PROTECTED":
            errors.append(f"protected {iid} client-facing action != HOLD_PROTECTED")
    return errors


def validate_drift_contract(work6_result: Mapping[str, Any]) -> List[str]:
    """Independently verify every Work6 Drift row against Current + Final snapshots.

    This is intentionally stronger than merely checking the universe.  Work7 is the
    PM Contract/Schema Gate predecessor, so a renderer/downstream must not be able to
    pass a numerically altered Drift row even when its shape remains valid.
    """
    errors: List[str] = []
    drift = work6_result.get("drift_snapshot") or {}
    if drift.get("value_state") != "KNOWN":
        return ["Drift Snapshot must be KNOWN after Final Target confirmation"]
    if drift.get("renderer_must_not_recompute_final_target") is not True:
        errors.append("renderer_must_not_recompute_final_target != true")
    final_slot = work6_result.get("final_target") or {}
    final = final_slot.get("snapshot") if final_slot.get("value_state") == "KNOWN" else None
    current = _current_allocation_snapshot(work6_result)
    if final is None:
        errors.append("Final Target missing")
        return errors
    if current is None:
        errors.append("Current Allocation engine lineage missing/UNKNOWN")
        return errors
    if drift.get("denominator") != final.get("denominator"):
        errors.append("Drift denominator is not exact Final Target denominator object")

    cur = _index_positions(current)
    fin = _index_positions(final)
    expected = set(cur) | set(fin)
    rows = [x for x in drift.get("items", []) if isinstance(x, Mapping)]
    actual_ids = [x.get("instrument_id") for x in rows]
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("Drift Snapshot contains duplicate instruments")
    if set(actual_ids) != expected:
        errors.append("Drift universe != Current union Final Target")

    row_map = {x.get("instrument_id"): x for x in rows if isinstance(x.get("instrument_id"), str)}
    active = _active_locks(work6_result)
    for iid in sorted(expected):
        row = row_map.get(iid)
        if row is None:
            continue
        # Absence from a KNOWN complete allocation is a real zero, matching Work6 semantics.
        cw = _weight(cur[iid]) if iid in cur else 0.0
        tw = _weight(fin[iid]) if iid in fin else 0.0
        if cw is None or tw is None:
            # Work6 would emit UNKNOWN for all three numeric fields in this case.
            for field in ("current_weight", "final_target_weight", "drift"):
                if (row.get(field) or {}).get("value_state") != "UNKNOWN":
                    errors.append(f"Drift {iid} {field} must remain UNKNOWN when source weight is UNKNOWN")
            if row.get("client_facing_action") != "UNKNOWN":
                errors.append(f"Drift {iid} action must be UNKNOWN when source weight is UNKNOWN")
            continue
        rcw = _metric_value(row.get("current_weight") or {})
        rtw = _metric_value(row.get("final_target_weight") or {})
        rd = _metric_value(row.get("drift") or {})
        expected_drift = float(tw) - float(cw)
        if abs(expected_drift) <= WEIGHT_TOLERANCE:
            expected_drift = 0.0
        if rcw is None or abs(rcw - float(cw)) > WEIGHT_TOLERANCE:
            errors.append(f"Drift {iid} Current does not match actual Current Allocation")
        if rtw is None or abs(rtw - float(tw)) > WEIGHT_TOLERANCE:
            errors.append(f"Drift {iid} Final Target does not match Work6 Final Target")
        if rd is None or abs(rd - expected_drift) > WEIGHT_TOLERANCE:
            errors.append(f"Drift {iid} value != Final Target - Current")
        protected = iid in active
        if row.get("protected") is not protected:
            errors.append(f"Drift {iid} protected flag inconsistent with active Preference Lock")
        expected_action = (
            "HOLD_PROTECTED" if protected else
            "HOLD" if expected_drift == 0.0 else
            "INCREASE_TARGET_WEIGHT" if expected_drift > 0 else
            "DECREASE_TARGET_WEIGHT"
        )
        if row.get("client_facing_action") != expected_action:
            errors.append(f"Drift {iid} client-facing action inconsistent with drift direction/protection")
    return errors

def validate_radar_contract(work6_result: Mapping[str, Any]) -> List[str]:
    radar = work6_result.get("radar_snapshot") or {}
    return validate_radar_display_contract(radar)


def _v70_framework_issues(canonical_input: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    issues: List[Dict[str, Any]] = []
    v70 = canonical_input.get("v70_asset_framework") or {}
    refs = v70.get("source_reference_ids", []) if isinstance(v70, Mapping) else []
    if v70.get("value_state") != "KNOWN":
        issues.append(_issue("C_W7_V70_FRAMEWORK_REQUIRED", "BLOCKING", "v70_asset_framework",
                             "Work7 requires a KNOWN V70 asset framework; UNKNOWN/NONE is not coerced to neutral/zero.",
                             blocking=True, source_reference_ids=refs))
        return issues, {}
    if v70.get("run_id") != canonical_input.get("identity", {}).get("run_id"):
        issues.append(_issue("C_W7_RUN_ID_MISMATCH", "BLOCKING", "v70_asset_framework.run_id",
                             "V70 run_id must equal the C/Work6 run_id.", blocking=True,
                             source_reference_ids=refs))
    if not isinstance(v70.get("upstream_v70_snapshot_id"), str) or not v70.get("upstream_v70_snapshot_id"):
        issues.append(_issue("C_W7_V70_SNAPSHOT_ID_REQUIRED", "BLOCKING", "v70_asset_framework.upstream_v70_snapshot_id",
                             "V70 snapshot lineage id is required.", blocking=True, source_reference_ids=refs))
    if v70.get("data_quality") not in {"OK", "FALLBACK_USED"}:
        issues.append(_issue("C_W7_V70_DATA_QUALITY_INSUFFICIENT", "BLOCKING", "v70_asset_framework.data_quality",
                             "V70 data quality is insufficient/unknown; Work7 fails closed.", blocking=True,
                             source_reference_ids=refs))
    if v70.get("freshness") == "STALE":
        issues.append(_issue("C_W7_V70_SNAPSHOT_STALE", "WARNING", "v70_asset_framework.freshness",
                             "V70 Macro/asset framework snapshot is stale and must be refreshed upstream.",
                             source_reference_ids=refs))
    elif v70.get("freshness") != "FRESH":
        issues.append(_issue("C_W7_V70_FRESHNESS_UNKNOWN", "BLOCKING", "v70_asset_framework.freshness",
                             "V70 freshness must be FRESH for Work7 integration; UNKNOWN is not treated as fresh.",
                             blocking=True, source_reference_ids=refs))
    if not isinstance(v70.get("snapshot_as_of"), str) or not v70.get("snapshot_as_of"):
        issues.append(_issue("C_W7_V70_ASOF_REQUIRED", "BLOCKING", "v70_asset_framework.snapshot_as_of",
                             "V70 snapshot_as_of is required.", blocking=True, source_reference_ids=refs))
    else:
        try:
            datetime.fromisoformat(v70["snapshot_as_of"].replace("Z", "+00:00"))
        except ValueError:
            issues.append(_issue("C_W7_V70_ASOF_INVALID", "BLOCKING", "v70_asset_framework.snapshot_as_of",
                                 "V70 snapshot_as_of must be ISO-8601 parseable.", blocking=True, source_reference_ids=refs))

    # S0/B0/T are V70-owned values. Work7 consumes and validates completeness only; it never
    # derives or recomputes the Strategic Risk Budget / tactical tilt formula.
    strategic: Dict[str, float] = {}
    for field in ("strategic_stock_weight", "strategic_bond_weight"):
        val = _metric_value(v70.get(field) or {})
        if val is None:
            issues.append(_issue("C_W7_V70_STRATEGIC_WEIGHT_REQUIRED", "BLOCKING", f"v70_asset_framework.{field}",
                                 f"{field} must be KNOWN finite numeric from V70; Work7 does not infer it.",
                                 blocking=True, source_reference_ids=refs))
        elif val < -WEIGHT_TOLERANCE or val > 1 + WEIGHT_TOLERANCE:
            issues.append(_issue("C_W7_V70_STRATEGIC_WEIGHT_OUT_OF_RANGE", "BLOCKING", f"v70_asset_framework.{field}",
                                 f"{field} must be in [0,1].", blocking=True, source_reference_ids=refs))
        else:
            strategic[field] = max(0.0, min(1.0, val))
    if len(strategic) == 2 and abs(sum(strategic.values()) - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W7_V70_STRATEGIC_NOT_100_PERCENT", "BLOCKING", "v70_asset_framework",
                             f"V70 S0+B0 must sum to 1.0; got {sum(strategic.values()):.12f}.",
                             blocking=True, source_reference_ids=refs))
    if _metric_value(v70.get("tactical_tilt_t") or {}) is None:
        issues.append(_issue("C_W7_V70_TACTICAL_TILT_REQUIRED", "BLOCKING", "v70_asset_framework.tactical_tilt_t",
                             "V70 tactical_tilt_t must be KNOWN finite numeric; Work7 does not infer it.",
                             blocking=True, source_reference_ids=refs))

    weights: Dict[str, float] = {}
    for bucket, field in V70_BUCKET_FIELDS:
        val = _metric_value(v70.get(field) or {})
        if val is None:
            issues.append(_issue("C_W7_V70_WEIGHT_REQUIRED", "BLOCKING", f"v70_asset_framework.{field}",
                                 f"{field} must be KNOWN numeric; Work7 does not infer it.", blocking=True,
                                 source_reference_ids=refs))
        elif val < -WEIGHT_TOLERANCE or val > 1 + WEIGHT_TOLERANCE:
            issues.append(_issue("C_W7_V70_WEIGHT_OUT_OF_RANGE", "BLOCKING", f"v70_asset_framework.{field}",
                                 f"{field} must be in [0,1].", blocking=True, source_reference_ids=refs))
        else:
            weights[bucket] = max(0.0, min(1.0, val))
    if len(weights) == 3 and abs(sum(weights.values()) - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W7_V70_FRAMEWORK_NOT_100_PERCENT", "BLOCKING", "v70_asset_framework",
                             f"V70 stock+bond+dry-powder tactical weights must sum to 1.0; got {sum(weights.values()):.12f}.",
                             blocking=True, source_reference_ids=refs))
    return issues, weights



def _known_context_text(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return value.strip().upper() not in {"UNKNOWN", "N/A", "NA", "NONE", "NULL", "TBD", "UNSPECIFIED"}


def _finite_nonnegative(value: Any) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)) and float(value) >= -EPS)


def _validate_funding_context(funding_context: Mapping[str, Any], funding_schema: Mapping[str, Any],
                              canonical_input: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str], List[str], List[str]]:
    """Validate upstream Funding Context without creating a second Funding Domain Engine.

    Work7 only validates/isolates already supplied account budgets. It never moves money
    across accounts, never derives funding from bank cash, and never reallocates executable
    budgets from one broker/account to another.
    """
    raw = deepcopy(dict(funding_context or {}))
    issues: List[Dict[str, Any]] = []
    funding_errors: List[str] = []
    account_errors: List[str] = []
    cross_errors: List[str] = []
    schema_errors = _schema_issues(raw, funding_schema, "funding_context", "C_W7_FUNDING_CONTEXT_SCHEMA_INVALID")
    issues += schema_errors
    if schema_errors:
        funding_errors.append("Funding Context schema invalid")

    # Semantic checks are defensive and tolerate malformed objects so all three PM hard checks
    # can fail closed rather than relying only on JSON-Schema rejection.
    if raw.get("run_id") != canonical_input.get("identity", {}).get("run_id"):
        funding_errors.append("Funding Context run_id != Canonical Input run_id")
        issues.append(_issue("C_W7_FUNDING_RUN_ID_MISMATCH", "BLOCKING", "funding_context.run_id",
                             "Funding Context must belong to the same run_id as C/Work6.", blocking=True))
    if raw.get("bank_cash_scope") != "OUT_OF_SCOPE":
        funding_errors.append("bank_cash_scope must remain OUT_OF_SCOPE")
        issues.append(_issue("C_W7_BANK_CASH_SCOPE_VIOLATION", "BLOCKING", "funding_context.bank_cash_scope",
                             "Bank cash is Out of Scope and cannot fund Work7 executable budgets.", blocking=True))

    contexts = raw.get("contexts") if isinstance(raw.get("contexts"), list) else []
    domains = [c.get("domain") for c in contexts if isinstance(c, Mapping)]
    if len(contexts) != 3 or set(domains) != set(FUNDING_DOMAINS) or len(domains) != len(set(domains)):
        funding_errors.append("Funding Context must contain each of the three domains exactly once")
        account_errors.append("missing/unknown/duplicated funding domain")
        issues.append(_issue("C_W7_FUNDING_DOMAIN_SET_INVALID", "BLOCKING", "funding_context.contexts",
                             "Exactly one TW_LOCAL_BROKER, TW_SUB_BROKERAGE, and US_BROKER context is required.", blocking=True))

    total = raw.get("total_new_investment_amount")
    bucket_sum = 0.0
    bucket_sum_known = _finite_nonnegative(total)
    if not bucket_sum_known:
        funding_errors.append("total_new_investment_amount must be finite nonnegative")
        issues.append(_issue("C_W7_FUNDING_TOTAL_INVALID", "BLOCKING", "funding_context.total_new_investment_amount",
                             "total_new_investment_amount must be a finite nonnegative amount.", blocking=True))
    owner_pairs: set[Tuple[str, str]] = set()
    for idx, c in enumerate(contexts):
        if not isinstance(c, Mapping):
            funding_errors.append(f"context[{idx}] is not an object")
            continue
        domain = c.get("domain")
        broker = c.get("broker")
        account = c.get("account")
        if domain not in FUNDING_DOMAINS or not _known_context_text(broker) or not _known_context_text(account):
            account_errors.append(f"context[{idx}] missing/unknown broker/account/domain")
            issues.append(_issue("C_W7_ACCOUNT_CONTEXT_UNKNOWN", "BLOCKING", f"funding_context.contexts.{idx}",
                                 "broker/account/domain must be explicit and known.", blocking=True))
        if _known_context_text(broker) and _known_context_text(account):
            pair=(broker.strip(), account.strip())
            if pair in owner_pairs:
                account_errors.append(f"duplicated broker/account context {pair[0]}/{pair[1]}")
                issues.append(_issue("C_W7_DUPLICATED_BROKER_ACCOUNT_CONTEXT", "BLOCKING", f"funding_context.contexts.{idx}",
                                     "The same broker/account context cannot be duplicated across funding domains.", blocking=True))
            owner_pairs.add(pair)

        bucket = c.get("bucket_new_investment_amount")
        if _finite_nonnegative(bucket):
            bucket_sum += float(bucket)
        else:
            bucket_sum_known = False
            funding_errors.append(f"context[{idx}] bucket_new_investment_amount invalid")
            issues.append(_issue("C_W7_FUNDING_BUCKET_AMOUNT_INVALID", "BLOCKING", f"funding_context.contexts.{idx}.bucket_new_investment_amount",
                                 "bucket_new_investment_amount must be a finite nonnegative amount.", blocking=True))

        cash = c.get("brokerage_cash_state") if isinstance(c.get("brokerage_cash_state"), Mapping) else {}
        vals={k:cash.get(k) for k in ("total","available","unsettled","reserved")}
        if not all(_finite_nonnegative(v) for v in vals.values()):
            funding_errors.append(f"context[{idx}] brokerage cash state must be finite nonnegative")
            issues.append(_issue("C_W7_BROKERAGE_CASH_STATE_INVALID", "BLOCKING", f"funding_context.contexts.{idx}.brokerage_cash_state",
                                 "total/available/unsettled/reserved must be finite nonnegative amounts.", blocking=True))
        elif any(float(vals[k]) > float(vals["total"]) + EPS for k in ("available","unsettled","reserved")):
            funding_errors.append(f"context[{idx}] cash substate exceeds total")
            issues.append(_issue("C_W7_BROKERAGE_CASH_STATE_INCONSISTENT", "BLOCKING", f"funding_context.contexts.{idx}.brokerage_cash_state",
                                 "available/unsettled/reserved cannot individually exceed total brokerage cash.", blocking=True))

        ex = c.get("executable_budget") if isinstance(c.get("executable_budget"), Mapping) else {}
        ex_sum=0.0; ex_known=True
        for leg_name in ("equity","bond"):
            leg=ex.get(leg_name) if isinstance(ex.get(leg_name), Mapping) else {}
            amt=leg.get("amount")
            if _finite_nonnegative(amt):
                ex_sum += float(amt)
            else:
                ex_known=False
                funding_errors.append(f"context[{idx}] {leg_name} executable budget amount invalid")
                cross_errors.append(f"context[{idx}] {leg_name} executable budget amount invalid")
                issues.append(_issue("C_W7_EXECUTABLE_BUDGET_AMOUNT_INVALID", "BLOCKING", f"funding_context.contexts.{idx}.executable_budget.{leg_name}.amount",
                                     "Executable budget amount must be a finite nonnegative amount.", blocking=True))
            if leg.get("cash_basis") != "AVAILABLE":
                cross_errors.append(f"context[{idx}] {leg_name} executable budget does not use AVAILABLE cash")
                issues.append(_issue("C_W7_EXECUTABLE_BUDGET_NOT_AVAILABLE_CASH", "BLOCKING", f"funding_context.contexts.{idx}.executable_budget.{leg_name}",
                                     "Only available brokerage cash may become executable budget; unsettled/reserved/bank cash may not.", blocking=True))
            if (leg.get("source_domain") != domain or leg.get("source_broker") != broker or leg.get("source_account") != account):
                cross_errors.append(f"context[{idx}] {leg_name} executable budget source is cross-account/cross-broker")
                issues.append(_issue("C_W7_CROSS_ACCOUNT_FUNDING_FORBIDDEN", "BLOCKING", f"funding_context.contexts.{idx}.executable_budget.{leg_name}",
                                     "Executable budget must be funded only by its own broker/account/domain.", blocking=True))
        avail=vals.get("available")
        if ex_known and _finite_nonnegative(avail) and ex_sum > float(avail) + EPS:
            cross_errors.append(f"context[{idx}] executable budget exceeds available cash")
            issues.append(_issue("C_W7_EXECUTABLE_BUDGET_EXCEEDS_AVAILABLE", "BLOCKING", f"funding_context.contexts.{idx}.executable_budget",
                                 "Equity+bond executable budget cannot exceed this account's available brokerage cash.", blocking=True))
        if ex_known and _finite_nonnegative(bucket) and ex_sum > float(bucket) + EPS:
            cross_errors.append(f"context[{idx}] executable budget exceeds this account funding bucket")
            issues.append(_issue("C_W7_EXECUTABLE_BUDGET_EXCEEDS_ACCOUNT_BUCKET", "BLOCKING", f"funding_context.contexts.{idx}.executable_budget",
                                 "Equity+bond executable budget cannot exceed this account's own new-investment bucket.", blocking=True))

    if bucket_sum_known and abs(bucket_sum - float(total)) > 1e-6:
        funding_errors.append("sum of three funding buckets != total_new_investment_amount")
        issues.append(_issue("C_W7_FUNDING_BUCKET_TOTAL_MISMATCH", "BLOCKING", "funding_context.total_new_investment_amount",
                             f"Three funding buckets must sum to total new investment; buckets={bucket_sum:.6f}, total={float(total):.6f}.", blocking=True))

    all_ok = not funding_errors and not account_errors and not cross_errors and not schema_errors
    snapshot = {
        "value_state": "KNOWN" if all_ok else "NONE",
        "boundary_contract": "UPSTREAM_FUNDING_CONTEXT_VALIDATE_AND_ROUTE_ONLY_NO_SECOND_FUNDING_DOMAIN_ENGINE",
        "bank_cash_scope": raw.get("bank_cash_scope") if all_ok else "OUT_OF_SCOPE",
        "base_currency": raw.get("base_currency") if all_ok else None,
        "total_new_investment_amount": float(total) if all_ok else None,
        "contexts": deepcopy(contexts) if all_ok else [],
        "source_reference_ids": _uniq(raw.get("source_reference_ids", [])) if all_ok else [],
        "reason": None if all_ok else "Funding Context / account isolation / executable budget validation failed.",
    }
    return snapshot, issues, funding_errors, account_errors, cross_errors

def _final_target_engine_lineage_issues(work6_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if work6_result.get("confirmation_status") != "CONFIRMED":
        issues.append(_issue("C_W7_FINAL_TARGET_REQUIRED", "BLOCKING", "work6_result.confirmation_status",
                             "Work7 asset-framework integration requires a client-confirmed Final Target.", blocking=True))
        return issues
    ft = work6_result.get("final_target") or {}
    if ft.get("value_state") != "KNOWN" or not isinstance(ft.get("snapshot"), Mapping):
        issues.append(_issue("C_W7_FINAL_TARGET_REQUIRED", "BLOCKING", "work6_result.final_target",
                             "Confirmed Work6 must carry a KNOWN Final Target snapshot.", blocking=True))
        return issues
    eng = work6_result.get("final_target_engine_result")
    if not isinstance(eng, Mapping):
        issues.append(_issue("C_W7_FINAL_ENGINE_RESULT_REQUIRED", "BLOCKING", "work6_result.final_target_engine_result",
                             "Confirmed Final Target must have Work5 engine lineage from Work6.", blocking=True))
        return issues
    eng_slot = (eng.get("allocations") or {}).get("final_target") or {}
    eng_snap = eng_slot.get("snapshot") if eng_slot.get("value_state") == "KNOWN" else None
    if not isinstance(eng_snap, Mapping) or eng_snap.get("allocation_id") != ft["snapshot"].get("allocation_id"):
        issues.append(_issue("C_W7_FINAL_TARGET_LINEAGE_MISMATCH", "BLOCKING", "work6_result.final_target_engine_result",
                             "Work6 Final Target and its Work5 engine result do not reference the same allocation_id.",
                             blocking=True, source_reference_ids=ft["snapshot"].get("source_reference_ids", [])))
    return issues


def _framework_summary(canonical_input: Mapping[str, Any], weights: Mapping[str, float]) -> Dict[str, Any]:
    v70 = canonical_input.get("v70_asset_framework") or {}
    def metric(name: str) -> Optional[float]:
        return _metric_value(v70.get(name) or {})
    return {
        "owner_contract": "V70 owns Strategic Risk Budget/S0-B0/Macro math; C Work7 is consumer/adapter only.",
        "run_id": v70.get("run_id"),
        "upstream_v70_snapshot_id": v70.get("upstream_v70_snapshot_id"),
        "snapshot_as_of": v70.get("snapshot_as_of"),
        "strategic_stock_weight": metric("strategic_stock_weight"),
        "strategic_bond_weight": metric("strategic_bond_weight"),
        "tactical_tilt_t": metric("tactical_tilt_t"),
        "stock_tactical_weight": weights.get("STOCK"),
        "bond_tactical_weight": weights.get("BOND"),
        "v70_original_dry_powder_weight": weights.get("V70_ORIGINAL_DRY_POWDER"),
        "data_quality": v70.get("data_quality"),
        "freshness": v70.get("freshness"),
        "source_reference_ids": _uniq(v70.get("source_reference_ids", [])),
    }


def _build_residual_allocation(work6_result: Mapping[str, Any], v70_weights: Mapping[str, float]) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], bool]:
    """Return residual contract, integrated framework, issues, needs_v70_reroute.

    A confirmed Work6 Final Target is client-approved.  Work7 therefore never silently
    changes its asset-class totals.  Residual allocation may only reconstruct the same
    target inside V70 buckets.  Any V70/Final-Target bucket mismatch is a framework
    change and routes upstream for V70 -> C -> client reconfirmation.
    """
    issues: List[Dict[str, Any]] = []
    final = work6_result["final_target"]["snapshot"]
    positions = final.get("positions", [])
    active = _active_locks(work6_result)

    seen: set[str] = set()
    bucket_positions: Dict[str, List[Mapping[str, Any]]] = {k: [] for k, _ in V70_BUCKET_FIELDS}
    bucket_totals: Dict[str, float] = {k: 0.0 for k, _ in V70_BUCKET_FIELDS}
    for idx, p in enumerate(positions):
        iid = p.get("instrument_id")
        if iid in seen:
            issues.append(_issue("C_W7_DUPLICATE_INSTRUMENT", "BLOCKING", f"final_target.positions.{idx}.instrument_id",
                                 f"Duplicate Final Target instrument_id {iid}.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            continue
        seen.add(iid)
        w = _weight(p)
        if w is None:
            issues.append(_issue("C_W7_FINAL_TARGET_WEIGHT_UNKNOWN", "BLOCKING", f"final_target.positions.{idx}.weight",
                                 f"Final Target weight for {iid} must be KNOWN; UNKNOWN is not zero.", blocking=True,
                                 source_reference_ids=p.get("source_reference_ids", [])))
            continue
        b = _bucket(p)
        if b == "UNKNOWN":
            issues.append(_issue("C_W7_ASSET_BUCKET_UNKNOWN", "BLOCKING", f"final_target.positions.{idx}.asset_type",
                                 f"Cannot map asset_type={p.get('asset_type')!r} for {iid} into a V70 bucket; Work7 will not guess.",
                                 blocking=True, source_reference_ids=p.get("source_reference_ids", [])))
            continue
        bucket_positions[b].append(p)
        bucket_totals[b] += w

    if abs(sum(bucket_totals.values()) - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W7_FINAL_TARGET_NOT_100_PERCENT", "BLOCKING", "work6_result.final_target",
                             f"Final Target classified portfolio weight must sum to 1.0; got {sum(bucket_totals.values()):.12f}.",
                             blocking=True, source_reference_ids=final.get("source_reference_ids", [])))

    reroute = False
    for b in bucket_totals:
        if b in v70_weights and abs(bucket_totals[b] - v70_weights[b]) > WEIGHT_TOLERANCE:
            reroute = True
            issues.append(_issue("C_W7_V70_FINAL_TARGET_BUCKET_MISMATCH", "WARNING", f"asset_framework.{b}",
                                 f"Client-confirmed Final Target {b}={bucket_totals[b]:.6f} differs from same-run V70 bucket={v70_weights[b]:.6f}; Work7 will not silently rewrite Final Target. RETURN_TO_V70/reconfirmation required.",
                                 source_reference_ids=final.get("source_reference_ids", [])))

    residual_buckets: List[Dict[str, Any]] = []
    instrument_targets: List[Dict[str, Any]] = []
    if reroute or any(x.get("blocking") for x in issues):
        for b, _ in V70_BUCKET_FIELDS:
            residual_buckets.append({
                "bucket": b,
                "target_weight": v70_weights.get(b),
                "work6_final_target_bucket_weight": bucket_totals.get(b, 0.0),
                "locked_weight": None,
                "residual_budget": None,
                "unlocked_reference_weight": None,
                "allocated_residual_weight": None,
                "items": [],
            })
        residual = {
            "method": "LOCKED_FIRST_THEN_PROPORTIONAL_RESIDUAL_WITHIN_V70_BUCKET",
            "buckets": residual_buckets,
        }
        framework = {
            "value_state": "NONE",
            "stock_weight": None,
            "bond_weight": None,
            "v70_original_dry_powder_weight": None,
            "total_weight": None,
            "instrument_targets": [],
            "work6_final_target_preserved": True,
            "reason": "V70 / confirmed Final Target framework mismatch or blocking input; no integrated target was emitted.",
        }
        return residual, framework, issues, reroute

    integrated_total = 0.0
    for b, _ in V70_BUCKET_FIELDS:
        target = float(v70_weights[b])
        ps = bucket_positions[b]
        locked_ps = [p for p in ps if p.get("instrument_id") in active]
        free_ps = [p for p in ps if p.get("instrument_id") not in active]
        locked_sum = sum(float(active[p["instrument_id"]]["current_weight"]) for p in locked_ps)
        if locked_sum > target + WEIGHT_TOLERANCE:
            reroute = True
            issues.append(_issue("C_W7_PROTECTED_EXCEEDS_V70_BUCKET", "WARNING", f"asset_framework.{b}",
                                 f"Protected locked weight {locked_sum:.6f} exceeds V70 {b} bucket {target:.6f}; RETURN_TO_V70 required.",
                                 source_reference_ids=_uniq(s for p in locked_ps for s in active[p["instrument_id"]].get("preference_source_ids", []))))
            continue
        residual_budget = max(0.0, target - locked_sum)
        free_ref_sum = sum(_weight(p) or 0.0 for p in free_ps)
        if residual_budget > WEIGHT_TOLERANCE and free_ref_sum <= EPS:
            issues.append(_issue("C_W7_RESIDUAL_ALLOCATION_UNRESOLVED", "BLOCKING", f"asset_framework.{b}",
                                 f"V70 {b} residual budget {residual_budget:.6f} has no unlocked Final Target reference weight.",
                                 blocking=True))
            continue
        items: List[Dict[str, Any]] = []
        allocated_residual = 0.0
        for p in ps:
            iid = p["instrument_id"]
            ref_w = float(_weight(p) or 0.0)
            if iid in active:
                iw = float(active[iid]["current_weight"])
                protected = True
                rule = "LOCKED_CURRENT_WEIGHT"
            else:
                iw = 0.0 if residual_budget <= WEIGHT_TOLERANCE else residual_budget * (ref_w / free_ref_sum)
                protected = False
                rule = "PROPORTIONAL_RESIDUAL_FROM_CONFIRMED_FINAL_TARGET"
                allocated_residual += iw
            if abs(iw - ref_w) > WEIGHT_TOLERANCE:
                issues.append(_issue("C_W7_CONFIRMED_TARGET_WOULD_CHANGE", "BLOCKING", f"instrument_targets.{iid}",
                                     f"Residual integration would change client-confirmed Final Target for {iid} from {ref_w:.12f} to {iw:.12f}; Work7 refuses silent rewrite.",
                                     blocking=True, source_reference_ids=p.get("source_reference_ids", [])))
            row = {
                "instrument_id": iid,
                "ticker": p.get("ticker"),
                "asset_type": p.get("asset_type"),
                "bucket": b,
                "protected": protected,
                "work6_final_target_weight": ref_w,
                "integrated_weight": iw,
                "allocation_rule": rule,
                "source_reference_ids": _uniq(p.get("source_reference_ids", [])),
            }
            items.append(row)
            instrument_targets.append(deepcopy(row))
            integrated_total += iw
        residual_buckets.append({
            "bucket": b,
            "target_weight": target,
            "work6_final_target_bucket_weight": bucket_totals[b],
            "locked_weight": locked_sum,
            "residual_budget": residual_budget,
            "unlocked_reference_weight": free_ref_sum,
            "allocated_residual_weight": allocated_residual,
            "items": items,
        })

    if reroute:
        return (
            {"method": "LOCKED_FIRST_THEN_PROPORTIONAL_RESIDUAL_WITHIN_V70_BUCKET", "buckets": residual_buckets},
            {"value_state": "NONE", "stock_weight": None, "bond_weight": None,
             "v70_original_dry_powder_weight": None, "total_weight": None,
             "instrument_targets": [], "work6_final_target_preserved": True,
             "reason": "Protected locked weight exceeds V70 bucket; no integrated target emitted."},
            issues, True
        )

    if abs(integrated_total - 1.0) > WEIGHT_TOLERANCE:
        issues.append(_issue("C_W7_PORTFOLIO_MATH_NOT_100_PERCENT", "BLOCKING", "integrated_asset_framework.total_weight",
                             f"Integrated portfolio must sum to 1.0; got {integrated_total:.12f}.", blocking=True))

    residual = {
        "method": "LOCKED_FIRST_THEN_PROPORTIONAL_RESIDUAL_WITHIN_V70_BUCKET",
        "buckets": residual_buckets,
    }
    framework = {
        "value_state": "KNOWN" if not any(x.get("blocking") for x in issues) else "NONE",
        "stock_weight": v70_weights.get("STOCK") if not any(x.get("blocking") for x in issues) else None,
        "bond_weight": v70_weights.get("BOND") if not any(x.get("blocking") for x in issues) else None,
        "v70_original_dry_powder_weight": v70_weights.get("V70_ORIGINAL_DRY_POWDER") if not any(x.get("blocking") for x in issues) else None,
        "total_weight": integrated_total if not any(x.get("blocking") for x in issues) else None,
        "instrument_targets": instrument_targets if not any(x.get("blocking") for x in issues) else [],
        "work6_final_target_preserved": True,
        "reason": None if not any(x.get("blocking") for x in issues) else "Blocking residual-allocation invariant failed.",
    }
    return residual, framework, issues, False


def run_asset_framework_integration(canonical_input: Mapping[str, Any], *,
                                    work6_result: Mapping[str, Any],
                                    canonical_input_schema_path: str | Path,
                                    work6_output_schema_path: str | Path,
                                    work7_output_schema_path: str | Path,
                                    funding_context: Mapping[str, Any],
                                    funding_context_schema_path: str | Path,
                                    evaluated_at: str) -> Dict[str, Any]:
    """Integrate a confirmed Work6 target with the same-run V70 asset framework.

    The function is deterministic for the same inputs and ``evaluated_at``.  It deep-copies
    caller data and never mutates upstream objects.
    """
    _validate_dt(evaluated_at, "evaluated_at")
    ci_schema = _load_json(canonical_input_schema_path)
    w6_schema = _load_json(work6_output_schema_path)
    w7_schema = _load_json(work7_output_schema_path)
    funding_schema = _load_json(funding_context_schema_path)

    ci = deepcopy(dict(canonical_input))
    w6 = deepcopy(dict(work6_result))
    issues: List[Dict[str, Any]] = []
    issues += _schema_issues(ci, ci_schema, "canonical_input", "C_W7_CANONICAL_INPUT_SCHEMA_INVALID")
    issues += _schema_issues(w6, w6_schema, "work6_result", "C_W7_WORK6_SCHEMA_INVALID")
    if issues:
        raise Work7ValidationError(issues)

    # Identity and local provenance.
    if w6.get("identity") != ci.get("identity"):
        issues.append(_issue("C_W7_IDENTITY_MISMATCH", "BLOCKING", "work6_result.identity",
                             "Work6 identity must exactly match the Canonical Input identity.", blocking=True))
    source_ids = _source_ids(ci)
    unresolved = set((ci.get("v70_asset_framework") or {}).get("source_reference_ids", [])) - source_ids
    if unresolved:
        issues.append(_issue("C_W7_V70_SOURCE_REFERENCE_MISSING", "BLOCKING", "v70_asset_framework.source_reference_ids",
                             f"Unresolved V70 source_reference_ids: {sorted(unresolved)}", blocking=True))

    funding_snapshot, funding_issues, funding_errors, account_errors, cross_funding_errors = _validate_funding_context(
        funding_context, funding_schema, ci
    )
    issues += funding_issues

    upstream_work6_blocked = (
        w6.get("route", {}).get("decision") == "BLOCKED"
        or w6.get("loop_status") == "BLOCKED"
    )
    upstream_work6_return_v70 = (
        w6.get("route", {}).get("decision") == "RETURN_TO_V70"
        or w6.get("loop_status") == "V70_REROUTE_REQUIRED"
    )
    if upstream_work6_blocked:
        issues.append(_issue("C_W7_UPSTREAM_WORK6_BLOCKED", "BLOCKING", "work6_result",
                             "Work6 is blocked; Work7 cannot create an asset-framework integration target.", blocking=True))
    if upstream_work6_return_v70:
        issues.append(_issue("C_W7_UPSTREAM_RETURN_TO_V70", "WARNING", "work6_result.route",
                             "Work6 already requires V70 refresh; Work7 preserves that route and does not integrate."))

    v70_issues, v70_weights = _v70_framework_issues(ci)
    issues += v70_issues

    # Work6 can legitimately stop before Final Target confirmation when it has already
    # determined that V70 must be rerun.  Work7 must preserve that upstream route, not
    # misclassify the absence of a Final Target/Drift as a new Work7 hard failure.
    if upstream_work6_return_v70:
        protected_errors: List[str] = []
        drift_errors: List[str] = []
    else:
        issues += _final_target_engine_lineage_issues(w6)
        protected_errors = validate_protected_holding_contract(w6)
        drift_errors = validate_drift_contract(w6)

    radar_errors = validate_radar_contract(w6)
    for msg in protected_errors:
        issues.append(_issue("C_W7_PROTECTED_HOLDING_CONTRACT_FAIL", "BLOCKING", "work6_result.preference_locks",
                             msg, blocking=True))
    for msg in drift_errors:
        issues.append(_issue("C_W7_DRIFT_CONTRACT_FAIL", "BLOCKING", "work6_result.drift_snapshot",
                             msg, blocking=True))
    for msg in radar_errors:
        issues.append(_issue("C_W7_RADAR_CONTRACT_FAIL", "BLOCKING", "work6_result.radar_snapshot",
                             msg, blocking=True))

    pre_route_v70 = (
        upstream_work6_return_v70
        or any(x.get("code") == "C_W7_V70_SNAPSHOT_STALE" for x in issues)
    )
    hard_block = any(x.get("blocking") for x in issues)

    if not hard_block and not pre_route_v70:
        residual, integrated, residual_issues, residual_reroute = _build_residual_allocation(w6, v70_weights)
        issues += residual_issues
    else:
        residual_reroute = pre_route_v70
        residual = {"method": "LOCKED_FIRST_THEN_PROPORTIONAL_RESIDUAL_WITHIN_V70_BUCKET", "buckets": []}
        integrated = {"value_state": "NONE", "stock_weight": None, "bond_weight": None,
                      "v70_original_dry_powder_weight": None, "total_weight": None,
                      "instrument_targets": [], "work6_final_target_preserved": True,
                      "reason": "Upstream/blocking gate prevents Work7 integration."}

    hard_block = any(x.get("blocking") for x in issues)
    needs_v70 = pre_route_v70 or residual_reroute or any(
        x.get("code") in {"C_W7_V70_FINAL_TARGET_BUCKET_MISMATCH", "C_W7_PROTECTED_EXCEEDS_V70_BUCKET"}
        for x in issues
    )

    if hard_block:
        status = "BLOCKED"
        route = "BLOCKED"
    elif needs_v70:
        status = "RETURN_TO_V70"
        route = "RETURN_TO_V70"
        # A reroute never emits an integrated target even if diagnostics computed one.
        integrated = {"value_state": "NONE", "stock_weight": None, "bond_weight": None,
                      "v70_original_dry_powder_weight": None, "total_weight": None,
                      "instrument_targets": [], "work6_final_target_preserved": True,
                      "reason": "V70 refresh/reconfirmation is required; Work7 emitted no replacement target."}
    else:
        status = "READY_FOR_PM_GATE"
        route = "PM_CONTRACT_SCHEMA_GATE"

    active = _active_locks(w6)
    protected_rows = []
    final = (w6.get("final_target") or {}).get("snapshot") or {}
    fin_idx = _index_positions(final)
    drift_idx = {x.get("instrument_id"): x for x in (w6.get("drift_snapshot") or {}).get("items", []) if isinstance(x, Mapping)}
    for iid in sorted(active):
        p = fin_idx.get(iid) or {}
        di = drift_idx.get(iid) or {}
        protected_rows.append({
            "instrument_id": iid,
            "ticker": p.get("ticker") or active[iid].get("ticker"),
            "bucket": _bucket(p),
            "current_weight": float(active[iid]["current_weight"]),
            "final_target_weight": _weight(p),
            "drift": ((di.get("drift") or {}).get("value") if (di.get("drift") or {}).get("value_state") == "KNOWN" else None),
            "protected": True,
            "source_reference_ids": _uniq(active[iid].get("preference_source_ids", [])),
        })

    hard_checks = {
        "protected_existing_holding_contract": (
            "NOT_APPLICABLE" if upstream_work6_return_v70 else "PASS" if not protected_errors else "FAIL"
        ),
        "portfolio_drift_snapshot_contract": (
            "NOT_APPLICABLE" if upstream_work6_return_v70 else "PASS" if not drift_errors else "FAIL"
        ),
        "radar_axis_label_order_contract": "PASS" if not radar_errors else "FAIL",
        "same_run_snapshot_lineage": "PASS" if not any(x.get("code") in {"C_W7_IDENTITY_MISMATCH", "C_W7_RUN_ID_MISMATCH"} for x in issues) else "FAIL",
        "portfolio_math_100_percent": (
            "PASS" if status == "READY_FOR_PM_GATE" and integrated.get("value_state") == "KNOWN"
            and abs(float(integrated.get("total_weight") or 0.0) - 1.0) <= WEIGHT_TOLERANCE
            else "NOT_APPLICABLE" if status == "RETURN_TO_V70" else "FAIL"
        ),
        "v70_owner_boundary": "PASS",  # Work7 code consumes fields only; no Macro/mSafe/CAP formula exists here.
        "funding_context_schema_validation": "PASS" if not funding_errors else "FAIL",
        "account_isolation": "PASS" if not account_errors else "FAIL",
        "no_cross_account_funding_executable_budget_isolation": "PASS" if not cross_funding_errors else "FAIL",
    }

    reason_codes = _uniq(x["code"] for x in issues)
    final_ref = {
        "allocation_id": final.get("allocation_id") if final else None,
        "confirmed_at": final.get("confirmed_at") if final else None,
        "confirmed_by": final.get("confirmed_by") if final else None,
        "source_reference_ids": _uniq(final.get("source_reference_ids", []) if final else []),
    }
    v70_summary = _framework_summary(ci, v70_weights)
    lineage = {
        "run_id": ci.get("identity", {}).get("run_id"),
        "canonical_request_id": ci.get("identity", {}).get("request_id"),
        "work6_snapshot_id": w6.get("work6_snapshot_id"),
        "v70_snapshot_id": (ci.get("v70_asset_framework") or {}).get("upstream_v70_snapshot_id"),
        "lineage_status": "SAME_RUN" if hard_checks["same_run_snapshot_lineage"] == "PASS" else "MISMATCH",
    }

    out = {
        "contract_name": "LivingWaterAI.C.Work7.AssetFrameworkIntegrationResult",
        "contract_version": WORK7_VERSION,
        "identity": deepcopy(ci.get("identity", {})),
        "work7_snapshot_id": "PENDING",
        "parent_work6_snapshot_id": w6.get("work6_snapshot_id"),
        "status": status,
        "route": {"decision": route, "reason_codes": reason_codes},
        "v70_framework_snapshot": v70_summary,
        "funding_context_snapshot": funding_snapshot,
        "work6_final_target_reference": final_ref,
        "protected_locked_weights": protected_rows,
        "residual_allocation": residual,
        "integrated_asset_framework": integrated,
        "drift_snapshot": deepcopy(w6.get("drift_snapshot")),
        "radar_snapshot": deepcopy(w6.get("radar_snapshot")),
        "snapshot_lineage": lineage,
        "hard_checks": hard_checks,
        "report_contract": {
            "renderer_must_not_recompute_final_target": True,
            "renderer_must_use_work6_drift_snapshot": True,
            "renderer_must_use_work6_radar_snapshot": True,
            "risk_warning_is_not_sell_instruction": True,
            "funding_context_must_remain_account_isolated": True,
            "funding_domain_engine_must_not_be_reimplemented_in_c7": True,
        },
        "pm_gate": {
            "required": True,
            "status": "PENDING_ABC_PM_CONTRACT_SCHEMA_GATE",
            "a78_a79_released": False,
            "work8_released": False,
            "required_hard_checks": [
                "Protected Existing Holding Contract",
                "Portfolio Drift Snapshot Contract",
                "Radar Axis Label/Order Contract",
                "Funding Context Schema/Validation",
                "Account Isolation",
                "No Cross-Account Funding/Executable Budget Isolation",
            ],
        },
        "source_reference_ids": _uniq(
            list((ci.get("v70_asset_framework") or {}).get("source_reference_ids", []))
            + list(final_ref.get("source_reference_ids", []))
            + list(funding_snapshot.get("source_reference_ids", []))
            + [s for x in protected_rows for s in x.get("source_reference_ids", [])]
        ),
        "issues": issues,
        "created_at": evaluated_at,
    }
    out["work7_snapshot_id"] = _snapshot_id(ci, w6, evaluated_at=evaluated_at,
                                             status=status, route=route,
                                             integrated_asset_framework=integrated,
                                             funding_context_snapshot=funding_snapshot)

    schema_errors = _schema_issues(out, w7_schema, "work7_output", "C_W7_OUTPUT_SCHEMA_INVALID")
    if schema_errors:
        detail = "; ".join(x["message"] for x in schema_errors[:10])
        raise RuntimeError(f"Work7 produced schema-invalid output: {detail}")
    return out
