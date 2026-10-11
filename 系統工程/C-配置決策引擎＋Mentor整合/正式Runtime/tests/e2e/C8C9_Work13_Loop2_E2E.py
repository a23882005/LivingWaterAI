"""C8C9 Work13 - Loop2 End-to-End executor.

This executor runs the already-frozen Work13 certified full chain:
Final Target + Client State + Funding Context -> Work3/V70 handoff ->
Work4 actual V82 runtime -> Work5 actual V75 runtime -> Work6/7/8 ->
Work9 unified deployment + Mentor return.

It intentionally reuses the RERELEASE2 certified preflight implementation and
its frozen QA-only dependency profiles.  It does not patch V70/V82/V75 business
logic, does not mutate Final Target, and does not promote observed runtime output
into golden expected data.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import contextlib
import io
from pathlib import Path
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True

WORK13_EXECUTOR_ID = "C8C9-W13-LOOP2-E2E-v1.0.0"
SCENARIO_ID = "C8C9-W13-GS-LOOP2_HAPPY"
RUN_ID = "qa-run-3"


class Work13Error(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_fixture_bundle(fixtures: Mapping[str, Any], checkpoint_root: Path) -> None:
    expected = {
        "work3_input": checkpoint_root / "WORK11_OUTPUT/FIXTURES/W13_LOOP2_WORK3_INPUT_US_HAPPY.json",
        "c7_funding_context": checkpoint_root / "WORK11_OUTPUT/FIXTURES/W13_LOOP2_C7_FUNDING_CONTEXT_US_HAPPY.json",
        "v82_asset_context": checkpoint_root / "WORK11_OUTPUT/FIXTURES/W13_LOOP2_V82_ASSET_CONTEXT_US_HAPPY.json",
        "v75_source_context": checkpoint_root / "WORK11_OUTPUT/FIXTURES/W13_LOOP2_V75_SOURCE_CONTEXT_US_HAPPY.json",
    }
    if set(fixtures) != set(expected):
        raise Work13Error("C8C9.W13.FIXTURE_ROLES", f"got={sorted(fixtures)}")
    for role, path in expected.items():
        if fixtures[role] != _load_json(path):
            raise Work13Error("C8C9.W13.FIXTURE_MUTATION", role)


def _cleanup_dynamic_modules(before: set[str], old_path: list[str]) -> None:
    sys.path[:] = old_path
    for name in list(sys.modules):
        if name in before:
            continue
        mod = sys.modules.get(name)
        f = str(getattr(mod, "__file__", "") or "")
        if (
            name.startswith("w13_exec_preflight_")
            or name.startswith("w13fc_")
            or name == "work7" or name.startswith("work7.")
            or name == "v75_runtime" or name.startswith("v75_runtime.")
            or name == "livingwater_v82_runtime" or name.startswith("livingwater_v82_runtime.")
            or "w13_fullchain_" in f
        ):
            sys.modules.pop(name, None)


def run_certified_fullchain(checkpoint_root: Path) -> dict[str, Any]:
    """Execute the frozen RERELEASE2 Work3->Work9 chain and return observed outputs."""
    script = checkpoint_root / "tools/qa_work13_fullchain_preflight.py"
    if not script.is_file():
        raise Work13Error("C8C9.W13.PREFLIGHT_MISSING", str(script))

    before = set(sys.modules)
    old_path = list(sys.path)
    old_argv = list(sys.argv)
    mod_name = f"w13_exec_preflight_{id(script)}_{len(before)}"
    spec = importlib.util.spec_from_file_location(mod_name, script)
    if spec is None or spec.loader is None:
        raise Work13Error("C8C9.W13.PREFLIGHT_LOAD", str(script))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    exit_code = None
    try:
        sys.argv = [str(script)]  # never --write frozen Work11 evidence
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                spec.loader.exec_module(mod)
        except SystemExit as exc:
            exit_code = 0 if exc.code is None else int(exc.code)
        if exit_code not in (None, 0):
            result = getattr(mod, "result", {})
            raise Work13Error("C8C9.W13.FULLCHAIN_PREFLIGHT", json.dumps(result.get("blockers", [])))
        result = deepcopy(getattr(mod, "result", None))
        if not isinstance(result, dict) or result.get("ready") is not True or result.get("status") != "PASS":
            raise Work13Error("C8C9.W13.FULLCHAIN_NOT_READY", repr(result))

        names = ("w3", "w4b", "w4", "w5b", "w5", "w6", "w7", "w8", "w9", "c7_actual")
        missing = [n for n in names if not hasattr(mod, n)]
        if missing:
            raise Work13Error("C8C9.W13.OBSERVED_OUTPUT_MISSING", repr(missing))
        observed = {n: deepcopy(getattr(mod, n)) for n in names}
        observed["preflight"] = result
        return observed
    finally:
        sys.argv = old_argv
        _cleanup_dynamic_modules(before, old_path)


def executor(fixtures: dict[str, Any], spec: Mapping[str, Any], checkpoint_root: Path) -> dict[str, Any]:
    if spec.get("scenario_id") != SCENARIO_ID or spec.get("target_work") != 13 or spec.get("run_id") != RUN_ID:
        raise Work13Error("C8C9.W13.SCENARIO", f"{spec.get('scenario_id')}/{spec.get('target_work')}/{spec.get('run_id')}")
    _assert_fixture_bundle(fixtures, checkpoint_root)

    observed = run_certified_fullchain(checkpoint_root)
    # Prove the neutral-harness fixtures are exactly the source bundle used by the fullchain.
    if observed["w3"] .get("run_id") != RUN_ID:
        raise Work13Error("C8C9.W13.RUN_ID", repr(observed["w3"].get("run_id")))

    w4b = observed["w4b"]
    w5b = observed["w5b"]
    w9 = observed["w9"]
    c7 = observed["c7_actual"]

    actual = {
        "contract_name": "LivingWaterAI.C8C9.Work13.Loop2E2EResult",
        "contract_version": "C8C9-W13-L2E2E-v1.0.0",
        "scenario_id": SCENARIO_ID,
        "run_id": RUN_ID,
        "work3_handoff": observed["w3"],
        "work4_binding": w4b["integration_binding"],
        "work5_binding": w5b["integration_binding"],
        "work4_v82_integration_result": observed["w4"],
        "work5_v75_integration_result": observed["w5"],
        "work6_funding_account_isolation_result": observed["w6"],
        "work7_sgov_runtime_role_result": observed["w7"],
        "work8_protected_holding_result": observed["w8"],
        "work9_unified_deployment_result": w9,
        "canonical_deployment_result": deepcopy(w9["canonical_deployment_result"]),
        "mentor_return": deepcopy(w9["mentor_return"]),
        "c_work7_same_run_asset_framework": c7,
        "fullchain_gate": {
            "gate": observed["preflight"]["gate"],
            "ready": observed["preflight"]["ready"],
            "passed": observed["preflight"]["passed"],
            "total": observed["preflight"]["total"],
            "output_digests": deepcopy(observed["preflight"]["output_digests"]),
        },
        "loop2_policy": {
            "final_target_mutation_forbidden": True,
            "today_deployment_only": True,
            "family_f2_released": False,
            "production_cutover_activated": False,
        },
    }
    return actual


__all__ = [
    "WORK13_EXECUTOR_ID", "SCENARIO_ID", "RUN_ID", "Work13Error",
    "run_certified_fullchain", "executor",
]
