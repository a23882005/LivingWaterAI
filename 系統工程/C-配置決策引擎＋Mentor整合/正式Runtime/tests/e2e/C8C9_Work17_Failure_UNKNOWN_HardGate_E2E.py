"""C8C9 Work17 - Failure / UNKNOWN / Hard-Gate E2E.

QA-only failure-injection harness. It consumes frozen Work9 and the frozen
Work11 happy fixture, injects explicitly authorized negative states, and proves
fail-closed behavior without patching V82/V75/V70 business logic, closed
predecessors, shared governance, Family F2, persistence, or production cutover.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HARNESS_ID = "C8C9-W17-FAILURE-UNKNOWN-HARDGATE-E2E-v1.0.0"
BASE_FIXTURE = ROOT / "WORK11_OUTPUT/FIXTURES/W15_W16_W18_WORK9_INPUT_HAPPY.json"
WORK9_PATH = ROOT / "WORK9_OUTPUT/C8C9_Work9_Unified_Deployment_Mentor_Return.py"
SAFE_ACTIONS = {"BLOCK", "UNKNOWN", "NEEDS_REVIEW"}


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(_canon(value)).hexdigest()


def _base() -> dict[str, Any]:
    return json.loads(BASE_FIXTURE.read_text(encoding="utf-8"))


def _resync_work8_work4(req: dict[str, Any]) -> None:
    w4 = req["work4_v82_integration_result"]
    req["work8_protected_holding_result"]["source_binding"]["work4_v82_integration_sha256"] = digest(w4)


def _resync_work7_work5(req: dict[str, Any]) -> None:
    w5 = req["work5_v75_integration_result"]
    req["work7_sgov_runtime_role_result"]["source_digests"]["work5_v75_integration_sha256"] = digest(w5)


def _set_v75_envelope(req: dict[str, Any], *, evaluation: str, gate: str, classification: str) -> None:
    w5 = req["work5_v75_integration_result"]
    v75 = w5["canonical_v75_output"]
    ready = w5["canonical_v75_runtime_ready_snapshot"]
    v75["evaluation_state"] = evaluation
    v75["formal_output_eligible"] = False
    v75["per_asset_decisions"] = []
    ready["evaluation_state"] = evaluation
    ready["final_classification"] = classification
    ready["runtime_ready"] = False
    ready["cutover_state"] = "BLOCKED"
    ready["gate_state"] = gate
    ready["output"] = deepcopy(v75)
    _resync_work7_work5(req)


def _case_exception(case_id: str, expected_code: str, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    w9 = _load(f"w9_{case_id}", WORK9_PATH)
    req = _base()
    mutate(req)
    try:
        out = w9.build_unified_deployment(req)
        return {
            "case_id": case_id, "kind": "FAIL_CLOSED_EXCEPTION", "pass": False,
            "expected_error_code": expected_code, "observed_error_code": None,
            "gate_status": None, "continued": True,
            "detail": f"unexpected accepted output sha256={digest(out)}",
        }
    except Exception as exc:
        code = getattr(exc, "code", None)
        return {
            "case_id": case_id, "kind": "FAIL_CLOSED_EXCEPTION",
            "pass": code == expected_code,
            "expected_error_code": expected_code, "observed_error_code": code,
            "gate_status": "BLOCK", "continued": False,
            "detail": getattr(exc, "detail", str(exc)),
        }


def _case_canonical(case_id: str, expected_action: str, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    w9 = _load(f"w9_{case_id}", WORK9_PATH)
    req = _base()
    mutate(req)
    try:
        out = w9.build_unified_deployment(req)
        items = out["canonical_deployment_result"]["items"]
        guards = [x for x in items if x.get("item_id") == "V75:__ACCOUNT_SCOPE__"]
        action = guards[0]["canonical_action"] if len(guards) == 1 else None
        return {
            "case_id": case_id, "kind": "CANONICAL_GUARD_STATUS",
            "pass": action == expected_action and expected_action in SAFE_ACTIONS,
            "expected_action": expected_action, "observed_action": action,
            "gate_status": action, "continued": action not in SAFE_ACTIONS,
            "item_ids": [x.get("item_id") for x in items],
            "canonical_result_sha256": out.get("canonical_deployment_result_sha256"),
        }
    except Exception as exc:
        return {
            "case_id": case_id, "kind": "CANONICAL_GUARD_STATUS", "pass": False,
            "expected_action": expected_action, "observed_action": None,
            "gate_status": None, "continued": False,
            "detail": f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'detail', str(exc))}",
        }


def execute() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    cases.append(_case_exception(
        "MISSING_OWNER", "C8C9.W9.WORK6_SCHEMA",
        lambda q: q["work6_funding_account_isolation_result"].pop("owner"),
    ))
    cases.append(_case_exception(
        "WRONG_ACCOUNT", "C8C9.W9.OWNER_MISMATCH",
        lambda q: q["work4_v82_integration_result"]["owner"].__setitem__("account", "WRONG_ACCOUNT"),
    ))
    cases.append(_case_exception(
        "SCHEMA_MISMATCH", "C8C9.W9.WORK6_SCHEMA",
        lambda q: q["work6_funding_account_isolation_result"].__setitem__("cash_eligibility", "INVALID_OBJECT"),
    ))
    cases.append(_case_exception(
        "STALE_INCOMPATIBLE_DATA", "C8C9.W9.SHARED_CONTEXT_LINEAGE",
        lambda q: q["work5_v75_integration_result"].__setitem__("shared_context_id", "stale-incompatible-context"),
    ))

    def unknown_mut(q: dict[str, Any]) -> None:
        _set_v75_envelope(q, evaluation="INSUFFICIENT_DATA", gate="INSUFFICIENT_DATA", classification="INSUFFICIENT_DATA")
    cases.append(_case_canonical("UNKNOWN", "UNKNOWN", unknown_mut))

    cases.append(_case_exception(
        "UNSETTLED_FUNDING", "C8C9.W9.WORK6_SCHEMA",
        lambda q: q["work6_funding_account_isolation_result"]["cash_eligibility"].__setitem__("unsettled_reserved_consumed", True),
    ))

    def cross_account(q: dict[str, Any]) -> None:
        q["work4_v82_integration_result"]["consumed_equity_executable_budget"]["owner"]["account"] = "OTHER_ACCOUNT"
        _resync_work8_work4(q)
    cases.append(_case_exception("CROSS_ACCOUNT_MONEY", "C8C9.W9.FUNDING_BINDING", cross_account))

    def upstream_block(q: dict[str, Any]) -> None:
        _set_v75_envelope(q, evaluation="INVALID_INPUT", gate="NOT_APPLICABLE", classification="INVALID_INPUT")
    cases.append(_case_canonical("UPSTREAM_BLOCK", "BLOCK", upstream_block))

    cases.append(_case_exception(
        "INVALID_VERSION", "C8C9.W9.INPUT_SCHEMA",
        lambda q: q.__setitem__("contract_version", "C8C9-W9-UDI-v0.0.0-INVALID"),
    ))

    # Explicitly exercise NEEDS_REVIEW as the third safe non-guessing status.
    def review_mut(q: dict[str, Any]) -> None:
        _set_v75_envelope(q, evaluation="REVIEW_REQUIRED", gate="RESTRICT", classification="REVIEW_REQUIRED")
    cases.append(_case_canonical("REVIEW_REQUIRED_CONTROL", "NEEDS_REVIEW", review_mut))

    required = {
        "MISSING_OWNER", "WRONG_ACCOUNT", "SCHEMA_MISMATCH", "STALE_INCOMPATIBLE_DATA",
        "UNKNOWN", "UNSETTLED_FUNDING", "CROSS_ACCOUNT_MONEY", "UPSTREAM_BLOCK", "INVALID_VERSION",
    }
    ids = {x["case_id"] for x in cases}
    passed = all(x.get("pass") is True for x in cases) and required.issubset(ids)
    return {
        "harness_id": HARNESS_ID,
        "status": "PASS" if passed else "FAIL",
        "required_injections": sorted(required),
        "safe_terminal_statuses": sorted(SAFE_ACTIONS),
        "cases": cases,
        "summary": {
            "passed": sum(1 for x in cases if x.get("pass") is True),
            "total": len(cases),
            "required_injections_present": sorted(required.intersection(ids)),
            "all_required_present": required.issubset(ids),
            "any_guess_continue": any(x.get("continued") is True for x in cases),
        },
        "scope": {
            "qa_only": True,
            "runtime_patch": False,
            "closed_predecessor_modified": False,
            "shared_governance_modified": False,
            "family_f2_released": False,
            "production_cutover_activated": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(execute(), ensure_ascii=False, indent=2, sort_keys=True))
