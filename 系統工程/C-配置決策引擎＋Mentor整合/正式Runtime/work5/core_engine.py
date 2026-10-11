"""C Work5 — configuration decision engine core integration.

Scope:
- Validate the Work1 Canonical Input contract.
- Read the formal B benchmark through the Work2 Benchmark Reader.
- Invoke the locked Work3 performance/risk sub-engine.
- Invoke the locked Work4 look-through exposure sub-engine.
- Assemble one Work1 Canonical Output object with fail-closed DQ, eligibility,
  issues, lineage and a deterministic C snapshot identity.

This module intentionally does NOT implement Work6 adjustment-loop logic,
Work7 V70 adapter logic, or Work8 V82/V75 deployment integration.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from work2.benchmark_reader import (
    WORK2_VERSION,
    SourceBinding,
    load_binding,
    read_benchmark,
)
from work3.engine import WORK3_VERSION, evaluate_performance_risk
from work4.engine import WORK4_VERSION, evaluate_lookthrough_exposure

WORK5_VERSION = "C-W5-v1.0.0"
WORK1_CONTRACT_VERSION = "C-W1-v1.0.1"
MODULE_RULES = [
    "C-W5-CORE-001",  # Canonical Input validation before execution.
    "C-W5-CORE-002",  # Formal B data only through Work2 reader.
    "C-W5-CORE-003",  # Work3/Work4 invoked without method override.
    "C-W5-CORE-004",  # UNKNOWN / DQ / Formal Eligibility fail-closed propagation.
    "C-W5-CORE-005",  # Output self-contained source lineage.
    "C-W5-CORE-006",  # Deterministic snapshot identity and rerun.
]
ALLOWED_ALLOCATION_SLOTS = {
    "current_allocation": "CURRENT",
    "proposed_allocation": "PROPOSED",
    "final_target": "FINAL_TARGET",
}
B_SOURCE_ID = "SRC_B_WORKBOOK"


class ConfigurationEngineValidationError(ValueError):
    """Raised when the Work5 invocation is structurally invalid.

    This covers Canonical Input schema failures plus structurally invalid explicit Work5
    arguments such as an unknown allocation slot or a non-object scenario assumption.
    Work5 never fabricates missing required fields or silently normalizes these failures.
    """

    def __init__(self, issues: Sequence[Mapping[str, Any]]):
        self.issues = [dict(x) for x in issues]
        super().__init__("Canonical Input schema validation failed")


def _uniq(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and v))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


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


def _trace(field_path: str, *, source_reference_ids: Sequence[str], as_of: Optional[str],
           data_quality: str, issue_codes: Sequence[str] = (),
           rules: Sequence[str] = MODULE_RULES) -> Dict[str, Any]:
    return {
        "field_path": field_path,
        "owner": "C_INTEGRATION",
        "rule_references": _uniq(rules),
        "source_reference_ids": _uniq(source_reference_ids),
        "as_of": as_of,
        "data_quality": data_quality,
        "issue_codes": _uniq(issue_codes),
    }


def _gate(eligible: bool, scope: str, *, evaluated_at: str,
          blocking_reasons: Sequence[str] = (), warning_reasons: Sequence[str] = ()) -> Dict[str, Any]:
    return {
        "eligible": bool(eligible),
        "scope": scope,
        "blocking_reasons": _uniq(blocking_reasons),
        "warning_reasons": _uniq(warning_reasons),
        "evaluated_at": evaluated_at,
        "rule_references": MODULE_RULES.copy(),
    }


def _schema_issue(error: Any) -> Dict[str, Any]:
    path = ".".join(str(p) for p in error.absolute_path) or None
    validator = getattr(error, "validator", None)
    if validator == "required":
        code = "C_SCHEMA_REQUIRED_MISSING"
    elif validator == "enum":
        code = "C_SCHEMA_ENUM_INVALID"
    else:
        code = "C_SCHEMA_TYPE_INVALID"
    return _issue(code, "BLOCKING", path, error.message, blocking=True)


def _load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_reference_ids(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k == "source_reference_ids" and isinstance(v, list):
                out.extend(x for x in v if isinstance(x, str))
            else:
                out.extend(_find_reference_ids(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_find_reference_ids(v))
    return out


def validate_canonical_input(canonical_input: Mapping[str, Any], *,
                             input_schema: Mapping[str, Any],
                             allocation_slot: str,
                             scenario_assumptions: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """Validate Work1 schema plus Work5 cross-object integration invariants.

    Schema violations are returned as blocking issues. Cross-object semantic issues are
    also blocking but leave the input object intact for audit/debug use.
    """
    issues: List[Dict[str, Any]] = []
    if not isinstance(canonical_input, Mapping):
        return [_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", None,
                       "Canonical Input must be an object.", blocking=True)]

    validator = Draft202012Validator(input_schema)
    schema_errors = sorted(validator.iter_errors(canonical_input), key=lambda e: list(e.absolute_path))
    issues.extend(_schema_issue(e) for e in schema_errors)
    if schema_errors:
        return issues

    if allocation_slot not in ALLOWED_ALLOCATION_SLOTS:
        issues.append(_issue("C_SCHEMA_ENUM_INVALID", "BLOCKING", "allocation_slot",
                             f"allocation_slot must be one of {sorted(ALLOWED_ALLOCATION_SLOTS)}.", blocking=True))
    else:
        slot = canonical_input["allocations"][allocation_slot]
        if slot.get("value_state") != "KNOWN" or not isinstance(slot.get("snapshot"), Mapping):
            issues.append(_issue("C_DATA_UNKNOWN_REQUIRED", "BLOCKING",
                                 f"allocations.{allocation_slot}",
                                 "Selected allocation slot must be KNOWN and carry a snapshot for Work5 execution.",
                                 blocking=True,
                                 source_reference_ids=_find_reference_ids(slot)))
        elif slot["snapshot"].get("stage") != ALLOWED_ALLOCATION_SLOTS[allocation_slot]:
            issues.append(_issue("C_ALLOCATION_STAGE_MISMATCH", "BLOCKING",
                                 f"allocations.{allocation_slot}.snapshot.stage",
                                 "Selected allocation slot stage does not match the slot identity.", blocking=True,
                                 source_reference_ids=slot["snapshot"].get("source_reference_ids", [])))

    sources = canonical_input.get("source_references", [])
    source_ids = [s.get("source_id") for s in sources if isinstance(s, Mapping)]
    if len(source_ids) != len(set(source_ids)):
        issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", "source_references",
                             "source_id values must be unique inside one Canonical object.", blocking=True))
    unresolved = sorted(set(_find_reference_ids(canonical_input)) - set(source_ids))
    if unresolved:
        issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", "source_references",
                             f"Unresolved source_reference_ids: {unresolved}", blocking=True))

    run_id = canonical_input.get("identity", {}).get("run_id")
    v70 = canonical_input.get("v70_asset_framework", {})
    if v70.get("value_state") == "KNOWN" and v70.get("run_id") != run_id:
        issues.append(_issue("C_IDENTITY_RUN_ID_MISMATCH", "BLOCKING", "v70_asset_framework.run_id",
                             "V70 run_id must equal C identity.run_id for the same decision run.", blocking=True,
                             source_reference_ids=v70.get("source_reference_ids", [])))

    if scenario_assumptions is not None:
        if not isinstance(scenario_assumptions, Mapping):
            issues.append(_issue("C_SCHEMA_TYPE_INVALID", "BLOCKING", "scenario_assumptions",
                                 "scenario_assumptions must be an object when supplied.", blocking=True))
        else:
            scenario_refs = sorted(set(_find_reference_ids(scenario_assumptions)) - set(source_ids))
            if scenario_refs:
                issues.append(_issue("C_TRACE_SOURCE_REFERENCE_MISSING", "BLOCKING", "scenario_assumptions",
                                     f"Scenario assumptions reference unknown source IDs: {scenario_refs}", blocking=True))
    return issues


def _normalize_work2_source_reference(src: Mapping[str, Any]) -> Dict[str, Any]:
    algo = src.get("source_fingerprint_algorithm")
    if algo == "SHA-256":
        algo = "SHA256"
    if algo not in {"SHA256", "ETAG", "REVISION_ID", "CONTENT_HASH_OTHER", "NOT_APPLICABLE", "UNKNOWN"}:
        algo = "CONTENT_HASH_OTHER" if src.get("source_fingerprint") else "UNKNOWN"
    return {
        "source_id": src.get("source_id") or B_SOURCE_ID,
        "source_kind": "B_BENCHMARK_SOT",
        "owner": "B_BENCHMARK",
        "source_reference": str(src.get("source_reference") or "UNKNOWN"),
        "source_fingerprint": src.get("source_fingerprint"),
        "as_of": src.get("as_of"),
        "retrieved_at": src.get("retrieved_at"),
        "data_quality": src.get("data_quality") if src.get("data_quality") in {"OK", "FALLBACK_USED", "INSUFFICIENT", "UNKNOWN"} else "UNKNOWN",
        "freshness": src.get("freshness") if src.get("freshness") in {"FRESH", "STALE", "UNKNOWN", "NOT_APPLICABLE"} else "UNKNOWN",
        "issue_codes": _uniq(src.get("issue_codes", [])),
        "source_native_status": src.get("source_native_status"),
        "notes": "Read by the locked C Work2 Benchmark Reader; Work5 does not substitute or recalculate B benchmark truth.",
        "source_version": src.get("source_version"),
        "source_fingerprint_algorithm": algo,
    }


def _benchmark_reference_for_output(benchmark: Mapping[str, Any]) -> Dict[str, Any]:
    ref = benchmark.get("benchmark_reference", {})
    sheets: Dict[str, Any] = {}
    for s in ref.get("sheets", []) if isinstance(ref.get("sheets"), list) else []:
        if not isinstance(s, Mapping) or not isinstance(s.get("sheet_name"), str):
            continue
        sheets[s["sheet_name"]] = {
            "role": s.get("role"),
            "header_fingerprint_sha256": s.get("header_fingerprint_sha256"),
        }
    return {
        "workbook_name": ref.get("workbook_name"),
        "drive_file_id": ref.get("drive_file_id"),
        "file_fingerprint_sha256": ref.get("file_fingerprint_sha256"),
        "sheets": sheets,
        "data_quality": ref.get("data_quality", "UNKNOWN"),
        "freshness": ref.get("freshness", "UNKNOWN"),
        "issue_codes": _uniq(ref.get("issue_codes", [])),
        "source_reference_ids": _uniq(ref.get("source_reference_ids", [B_SOURCE_ID])),
    }


def _compare_input_benchmark_reference(canonical_input: Mapping[str, Any],
                                       benchmark_output_ref: Mapping[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    expected = canonical_input.get("benchmark_reference", {})
    for key in ("workbook_name", "drive_file_id", "file_fingerprint_sha256"):
        if expected.get(key) != benchmark_output_ref.get(key):
            issues.append(_issue(
                "C_SOURCE_SOT_MISMATCH" if key != "file_fingerprint_sha256" else "C_SOURCE_FINGERPRINT_MISMATCH",
                "BLOCKING", f"benchmark_reference.{key}",
                f"Canonical Input B reference {key} does not match the Work2 reader snapshot.",
                blocking=True, source_reference_ids=benchmark_output_ref.get("source_reference_ids", [])))
    es = expected.get("sheets", {})
    bs = benchmark_output_ref.get("sheets", {})
    if set(es) != set(bs):
        issues.append(_issue("C_SOURCE_SOT_MISMATCH", "BLOCKING", "benchmark_reference.sheets",
                             "Canonical Input and Work2 reader do not reference the same four B sheets.", blocking=True,
                             source_reference_ids=benchmark_output_ref.get("source_reference_ids", [])))
    else:
        for name in sorted(bs):
            for key in ("role", "header_fingerprint_sha256"):
                if es[name].get(key) != bs[name].get(key):
                    issues.append(_issue("C_SOURCE_SOT_MISMATCH", "BLOCKING",
                                         f"benchmark_reference.sheets.{name}.{key}",
                                         f"B sheet {name} {key} mismatch between Canonical Input and Work2 reader.",
                                         blocking=True, source_reference_ids=benchmark_output_ref.get("source_reference_ids", [])))
    return issues


def _merge_source_references(input_sources: Sequence[Mapping[str, Any]],
                             benchmark_sources: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    issues: List[Dict[str, Any]] = []
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for raw in input_sources:
        if not isinstance(raw, Mapping):
            continue
        src = deepcopy(dict(raw))
        sid = src.get("source_id")
        if not isinstance(sid, str) or not sid:
            continue
        if sid not in merged:
            merged[sid] = src
            order.append(sid)
        elif merged[sid] != src:
            issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", "source_references",
                                 f"Conflicting SourceReference payloads for {sid}.", blocking=True,
                                 source_reference_ids=[sid]))
    for raw in benchmark_sources:
        if not isinstance(raw, Mapping):
            continue
        src = _normalize_work2_source_reference(raw)
        sid = src["source_id"]
        if sid not in merged:
            merged[sid] = src
            order.append(sid)
        elif merged[sid] != src:
            # The Work2 reader is authoritative for the B source. Preserve the source ID,
            # use the reader payload, and make the conflict visible/fail-closed.
            merged[sid] = src
            issues.append(_issue("C_CROSS_MODULE_CONFLICT", "BLOCKING", "source_references",
                                 f"Input SourceReference {sid} conflicts with Work2 reader source metadata.",
                                 blocking=True, source_reference_ids=[sid]))
    return [merged[s] for s in order], issues


def _v70_reference(v70: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": v70.get("run_id"),
        "upstream_v70_snapshot_id": v70.get("upstream_v70_snapshot_id"),
        "snapshot_as_of": v70.get("snapshot_as_of"),
        "data_quality": v70.get("data_quality", "UNKNOWN"),
        "freshness": v70.get("freshness", "UNKNOWN"),
        "issue_codes": _uniq(v70.get("issue_codes", [])),
        "source_reference_ids": _uniq(v70.get("source_reference_ids", [])),
    }


def _blocked_module(module_name: str, evaluated_at: str, issues: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    reasons = _uniq(i.get("code") for i in issues if i.get("blocking")) or ["C_FORMAL_OUTPUT_BLOCKED"]
    return {
        "module_name": module_name,
        "status": "BLOCKED",
        "formal_output_eligibility": _gate(False, "NONE", evaluated_at=evaluated_at,
                                            blocking_reasons=reasons),
        "payload": None,
        "issues": [deepcopy(dict(x)) for x in issues],
        "traceability": [],
    }


def _failed_module(module_name: str, evaluated_at: str, message: str,
                   source_reference_ids: Sequence[str] = ()) -> Dict[str, Any]:
    i = _issue("C_INTERNAL_ERROR", "ERROR", module_name, message, blocking=True,
               source_reference_ids=source_reference_ids)
    return {
        "module_name": module_name,
        "status": "FAILED",
        "formal_output_eligibility": _gate(False, "NONE", evaluated_at=evaluated_at,
                                            blocking_reasons=["C_INTERNAL_ERROR"]),
        "payload": None,
        "issues": [i],
        "traceability": [],
    }


def _module_summary(perf: Mapping[str, Any], look: Mapping[str, Any], evaluated_at: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    modules = [perf, look]
    eligible = [m for m in modules if (m.get("formal_output_eligibility") or {}).get("eligible") is True]
    failed = [m for m in modules if m.get("status") == "FAILED"]
    warning_codes: List[str] = []
    blocking_codes: List[str] = []
    for m in modules:
        g = m.get("formal_output_eligibility") or {}
        warning_codes.extend(g.get("warning_reasons") or [])
        if not g.get("eligible"):
            blocking_codes.extend(g.get("blocking_reasons") or [])
    root_issues: List[Dict[str, Any]] = []
    if len(eligible) == 2 and all((m.get("formal_output_eligibility") or {}).get("scope") == "FULL" for m in modules):
        return "SUCCESS", _gate(True, "FULL", evaluated_at=evaluated_at), root_issues
    if eligible:
        root_issues.append(_issue("C_PARTIAL_OUTPUT", "WARNING", "formal_output_eligibility",
                                  "Work5 produced formally eligible output for part of the requested integrated result; unavailable module outputs remain fail-closed.",
                                  blocking=False, source_reference_ids=[B_SOURCE_ID]))
        return "PARTIAL", _gate(True, "PARTIAL", evaluated_at=evaluated_at,
                                blocking_reasons=blocking_codes,
                                warning_reasons=_uniq(warning_codes + ["C_PARTIAL_OUTPUT"])), root_issues
    if failed:
        root_issues.append(_issue("C_INTERNAL_ERROR", "ERROR", "result_status",
                                  "Work5 has no formally eligible module output because an integration/runtime error occurred.",
                                  blocking=True, source_reference_ids=[B_SOURCE_ID]))
        return "FAILED", _gate(False, "NONE", evaluated_at=evaluated_at,
                               blocking_reasons=_uniq(blocking_codes + ["C_INTERNAL_ERROR"]),
                               warning_reasons=warning_codes), root_issues
    root_issues.append(_issue("C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "formal_output_eligibility",
                              "Work5 completed fail-closed: no integrated module currently has formally eligible output.",
                              blocking=True, source_reference_ids=[B_SOURCE_ID]))
    return "BLOCKED", _gate(False, "NONE", evaluated_at=evaluated_at,
                            blocking_reasons=_uniq(blocking_codes + ["C_FORMAL_OUTPUT_BLOCKED"]),
                            warning_reasons=warning_codes), root_issues


def _snapshot_id(*, canonical_input: Mapping[str, Any], allocation_slot: str,
                 benchmark: Mapping[str, Any], scenario_assumptions: Optional[Mapping[str, Any]],
                 evaluated_at: str, parent_c_snapshot_id: Optional[str]) -> str:
    basis = {
        "work5_version": WORK5_VERSION,
        "work1_contract_version": WORK1_CONTRACT_VERSION,
        "work2_version": WORK2_VERSION,
        "work3_version": WORK3_VERSION,
        "work4_version": WORK4_VERSION,
        "canonical_input": canonical_input,
        "allocation_slot": allocation_slot,
        "benchmark_fingerprint": (benchmark.get("benchmark_reference") or {}).get("file_fingerprint_sha256"),
        "benchmark_evaluation_date": benchmark.get("evaluation_date"),
        "scenario_assumptions": scenario_assumptions,
        "evaluated_at": evaluated_at,
        "parent_c_snapshot_id": parent_c_snapshot_id,
    }
    return "C-W5-" + sha256(_canonical_json(basis).encode("utf-8")).hexdigest()[:32]


def _validate_datetime_for_determinism(evaluated_at: str) -> date:
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise ValueError("evaluated_at is required for deterministic Work5 execution")
    try:
        dt = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("evaluated_at must be ISO-8601 parseable") from e
    return dt.date()


def _validate_output_or_raise(output: Mapping[str, Any], output_schema: Mapping[str, Any]) -> None:
    errors = sorted(Draft202012Validator(output_schema).iter_errors(output), key=lambda e: list(e.absolute_path))
    if errors:
        detail = "; ".join(f"{'.'.join(map(str,e.absolute_path))}: {e.message}" for e in errors[:10])
        raise RuntimeError(f"Work5 assembled an invalid Canonical Output: {detail}")


def run_configuration_engine(canonical_input: Mapping[str, Any], *,
                             allocation_slot: str,
                             benchmark_path: str | Path,
                             binding_path: str | Path,
                             input_schema_path: str | Path,
                             output_schema_path: str | Path,
                             evaluated_at: str,
                             scenario_assumptions: Optional[Mapping[str, Any]] = None,
                             parent_c_snapshot_id: Optional[str] = None) -> Dict[str, Any]:
    """Run the Work5 integrated C core engine.

    Determinism contract:
    - ``evaluated_at`` is mandatory and treated as execution-context input.
    - Same Canonical Input, allocation slot, scenario assumptions, B SOT fingerprint,
      versions, evaluated_at and parent snapshot produce the same output and snapshot ID.
    - The function deep-copies inputs and must not mutate caller objects.
    """
    eval_date = _validate_datetime_for_determinism(evaluated_at)
    input_schema = _load_json(input_schema_path)
    output_schema = _load_json(output_schema_path)

    validation_issues = validate_canonical_input(
        canonical_input,
        input_schema=input_schema,
        allocation_slot=allocation_slot,
        scenario_assumptions=scenario_assumptions,
    )
    structural_reject_codes = {
        "C_SCHEMA_REQUIRED_MISSING", "C_SCHEMA_TYPE_INVALID", "C_SCHEMA_ENUM_INVALID",
        # A Canonical object / invocation with dangling lineage cannot be copied into a
        # self-contained Canonical Output without either preserving an unresolved ID or
        # fabricating a SourceReference.  Reject it explicitly instead.
        "C_TRACE_SOURCE_REFERENCE_MISSING",
    }
    if any(i["code"] in structural_reject_codes for i in validation_issues):
        raise ConfigurationEngineValidationError(validation_issues)

    # Work2 is the only B reader/adapter. Work5 does not parse B itself.
    try:
        binding: SourceBinding = load_binding(binding_path)
        benchmark = read_benchmark(benchmark_path, binding, evaluation_date=eval_date)
    except Exception as e:  # reader/runtime failure: fail closed but preserve valid Canonical Input shell
        benchmark = None
        validation_issues.append(_issue("C_INTERNAL_ERROR", "ERROR", "benchmark_reference",
                                        f"Work2 Benchmark Reader failed: {type(e).__name__}: {e}",
                                        blocking=True))

    if benchmark is not None:
        benchmark_output_ref = _benchmark_reference_for_output(benchmark)
        validation_issues.extend(_compare_input_benchmark_reference(canonical_input, benchmark_output_ref))
        benchmark_sources = benchmark.get("source_references", [])
        # Work2 owns the B data-quality gate.  If its canonical benchmark snapshot is
        # globally ineligible, Work5 must not allow either downstream engine to revive
        # a formal result from individually present fields.  PARTIAL is allowed; NONE is not.
        b_gate = benchmark.get("formal_output_eligibility") or {}
        if b_gate.get("eligible") is not True or b_gate.get("scope") == "NONE":
            validation_issues.append(_issue(
                "C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "benchmark.formal_output_eligibility",
                "Work2 Benchmark Reader marked the B snapshot globally ineligible; Work5 blocks integrated formal output.",
                blocking=True, source_reference_ids=benchmark_output_ref.get("source_reference_ids", [])))
    else:
        benchmark_output_ref = deepcopy(canonical_input["benchmark_reference"])
        # Input B reference may be placeholder-quality, but remains the only safe provenance when reader failed.
        benchmark_output_ref["data_quality"] = "UNKNOWN"
        benchmark_output_ref["freshness"] = "UNKNOWN"
        benchmark_output_ref["issue_codes"] = _uniq(benchmark_output_ref.get("issue_codes", []) + ["C_INTERNAL_ERROR"])
        benchmark_sources = []

    output_sources, source_merge_issues = _merge_source_references(
        canonical_input.get("source_references", []), benchmark_sources)
    validation_issues.extend(source_merge_issues)

    blocking_validation = [i for i in validation_issues if i.get("blocking")]
    allocation = None
    if allocation_slot in ALLOWED_ALLOCATION_SLOTS:
        slot = canonical_input["allocations"][allocation_slot]
        if slot.get("value_state") == "KNOWN" and isinstance(slot.get("snapshot"), Mapping):
            allocation = deepcopy(slot["snapshot"])

    if blocking_validation or benchmark is None or allocation is None:
        perf = _blocked_module("C_WORK3_PERFORMANCE_RISK", evaluated_at, blocking_validation or validation_issues)
        look = _blocked_module("lookthrough_exposure_result", evaluated_at, blocking_validation or validation_issues)
    else:
        try:
            perf = evaluate_performance_risk(allocation, benchmark,
                                             scenario_assumptions=deepcopy(scenario_assumptions),
                                             evaluated_at=evaluated_at)
        except Exception as e:
            perf = _failed_module("C_WORK3_PERFORMANCE_RISK", evaluated_at,
                                  f"Work3 sub-engine raised {type(e).__name__}: {e}", [B_SOURCE_ID])
        try:
            look = evaluate_lookthrough_exposure(allocation, benchmark, evaluated_at=evaluated_at)
        except Exception as e:
            look = _failed_module("lookthrough_exposure_result", evaluated_at,
                                  f"Work4 sub-engine raised {type(e).__name__}: {e}", [B_SOURCE_ID])

    result_status, root_gate, root_issues = _module_summary(perf, look, evaluated_at)
    if blocking_validation:
        # Integration validation outranks otherwise-eligible downstream calculations.
        result_status = "BLOCKED"
        root_gate = _gate(False, "NONE", evaluated_at=evaluated_at,
                          blocking_reasons=_uniq(i["code"] for i in blocking_validation),
                          warning_reasons=_uniq(i["code"] for i in validation_issues if not i.get("blocking")))
        root_issues = [_issue("C_FORMAL_OUTPUT_BLOCKED", "BLOCKING", "formal_output_eligibility",
                              "Work5 integration validation failed; formal output is blocked.", blocking=True,
                              source_reference_ids=benchmark_output_ref.get("source_reference_ids", []))]

    combined_issues: List[Dict[str, Any]] = []
    combined_issues.extend(deepcopy(canonical_input.get("issues", [])))
    if benchmark is not None:
        combined_issues.extend(deepcopy(benchmark.get("issues", [])))
    combined_issues.extend(deepcopy(validation_issues))
    combined_issues.extend(deepcopy(perf.get("issues", [])))
    combined_issues.extend(deepcopy(look.get("issues", [])))
    combined_issues.extend(root_issues)

    benchmark_ref_ids = benchmark_output_ref.get("source_reference_ids", [])
    traceability: List[Dict[str, Any]] = []
    traceability.extend(deepcopy(canonical_input.get("traceability", [])))
    traceability.extend(deepcopy(perf.get("traceability", [])))
    traceability.extend(deepcopy(look.get("traceability", [])))
    traceability.extend([
        _trace("benchmark_reference", source_reference_ids=benchmark_ref_ids,
               as_of=(benchmark or {}).get("evaluation_date") if benchmark is not None else evaluated_at,
               data_quality=benchmark_output_ref.get("data_quality", "UNKNOWN"),
               issue_codes=benchmark_output_ref.get("issue_codes", []),
               rules=["C-W5-CORE-002", "C-W2-v1.0.1"]),
        _trace(f"allocations.{allocation_slot}",
               source_reference_ids=(allocation or {}).get("source_reference_ids", []),
               as_of=(allocation or {}).get("as_of"),
               data_quality="OK" if allocation is not None and not blocking_validation else "INSUFFICIENT",
               issue_codes=_uniq(i["code"] for i in blocking_validation),
               rules=["C-W5-CORE-001", "C-W5-CORE-003"]),
        _trace("performance_risk_result", source_reference_ids=benchmark_ref_ids,
               as_of=evaluated_at,
               data_quality="OK" if perf.get("formal_output_eligibility", {}).get("eligible") else "INSUFFICIENT",
               issue_codes=_uniq(i["code"] for i in perf.get("issues", [])),
               rules=["C-W5-CORE-003", "C-W3-v1.0.1"]),
        _trace("lookthrough_exposure_result", source_reference_ids=benchmark_ref_ids,
               as_of=evaluated_at,
               data_quality="OK" if look.get("formal_output_eligibility", {}).get("eligible") else "INSUFFICIENT",
               issue_codes=_uniq(i["code"] for i in look.get("issues", [])),
               rules=["C-W5-CORE-003", "C-W4-v1.0.0"]),
    ])

    output = {
        "contract_name": "LivingWaterAI.C.CanonicalOutput",
        "contract_version": WORK1_CONTRACT_VERSION,
        "identity": deepcopy(canonical_input["identity"]),
        "c_snapshot_id": _snapshot_id(
            canonical_input=canonical_input,
            allocation_slot=allocation_slot,
            benchmark=benchmark or {"benchmark_reference": benchmark_output_ref, "evaluation_date": eval_date.isoformat()},
            scenario_assumptions=scenario_assumptions,
            evaluated_at=evaluated_at,
            parent_c_snapshot_id=parent_c_snapshot_id,
        ),
        "parent_c_snapshot_id": parent_c_snapshot_id,
        "result_status": result_status,
        "decision_phase": canonical_input["decision_phase"],
        "allocations": deepcopy(canonical_input["allocations"]),
        "v70_asset_framework_reference": _v70_reference(canonical_input["v70_asset_framework"]),
        "benchmark_reference": benchmark_output_ref,
        "performance_risk_result": perf,
        "lookthrough_exposure_result": look,
        "deployment_integration_reference": {
            "status": "NOT_RUN",
            "run_id": canonical_input["identity"]["run_id"],
            "v82_snapshot_id": None,
            "v75_snapshot_id": None,
            "source_reference_ids": [],
            "notes": "Deferred by governance to C Work8 after ABC PM Runtime Readiness Gate RELEASE; Work5 does not perform deployment integration.",
        },
        "formal_output_eligibility": root_gate,
        "issues": combined_issues,
        "traceability": traceability,
        "created_at": evaluated_at,
        "source_references": output_sources,
    }

    # Cross-object traceability: every source_reference_id in the result must resolve locally.
    source_ids = {s.get("source_id") for s in output_sources}
    unresolved = sorted(set(_find_reference_ids(output)) - source_ids)
    if unresolved:
        raise RuntimeError(f"Work5 assembled unresolved source_reference_ids: {unresolved}")

    _validate_output_or_raise(output, output_schema)
    return output
