"""C8C9 Work12 - Loop1 Allocation E2E executor.

This Work12 executor is intentionally narrow. It re-runs the frozen C Work7
asset-framework happy-path from the exact upstream C7 checkpoint already frozen
by Work11, then returns the observed C7 runtime output to the Work11 neutral E2E
harness. It does not run or import V82/V75 deployment and does not modify any
upstream artifact.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping
import zipfile

sys.dont_write_bytecode = True

WORK12_EXECUTOR_ID = "C8C9-W12-LOOP1-E2E-v1.0.0"
C7_EXPECTED_SHA256 = "620f790e24f0aa8edd3add20b5c3f21d889a28d181e451286053ad81cd3917a5"
C7_EVALUATED_AT = "2026-09-24T16:10:00+08:00"


class Work12Error(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_c7_zip(checkpoint_root: Path) -> Path:
    root = checkpoint_root / "SOURCE_PACKAGE" / "UPSTREAM_C7"
    zips = sorted(root.glob("*.zip"))
    if len(zips) != 1:
        raise Work12Error("C8C9.W12.C7_PACKAGE_COUNT", f"expected 1 C7 zip, found {len(zips)}")
    if file_sha256(zips[0]) != C7_EXPECTED_SHA256:
        raise Work12Error("C8C9.W12.C7_PACKAGE_HASH", file_sha256(zips[0]))
    return zips[0]


def _clear_c7_modules() -> None:
    prefixes = ("work6", "work7")
    for name in list(sys.modules):
        if name in prefixes or name.startswith("work6.") or name.startswith("work7."):
            sys.modules.pop(name, None)


def rerun_frozen_c7_work7(checkpoint_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-run the exact frozen C7 Work7 happy-path without V82/V75 deployment."""
    c7_zip = _find_c7_zip(checkpoint_root)
    with tempfile.TemporaryDirectory(prefix="c8c9_w12_c7_") as td:
        troot = Path(td)
        with zipfile.ZipFile(c7_zip, "r") as zf:
            zf.extractall(troot)

        ci = _load_json(troot / "examples/canonical_input_valid.json")
        # Frozen official C Work7 happy-path alignment from qa_work7_asset_framework.py.
        for field, value in (
            ("stock_tactical_weight", 0.60),
            ("bond_tactical_weight", 0.40),
            ("v70_original_dry_powder_weight", 0.00),
        ):
            ci["v70_asset_framework"][field]["value"] = value
        ci["v70_asset_framework"]["stock_tactical_amount"]["amount"] = 600000.0
        ci["v70_asset_framework"]["bond_tactical_amount"]["amount"] = 400000.0
        ci["v70_asset_framework"]["v70_original_dry_powder_amount"]["amount"] = 0.0

        w6 = _load_json(troot / "examples/work6/Work6_ProtectedStock_FinalTarget_CONFIRMED.json")
        funding = _load_json(troot / "examples/work7/Work7_FundingContext_VALID.json")
        c7_golden = _load_json(troot / "examples/work7/Work7_Aligned_Protected_READY_FOR_PM_GATE.json")

        old_path = list(sys.path)
        _clear_c7_modules()
        try:
            sys.path.insert(0, str(troot))
            mod = importlib.import_module("work7.asset_framework")
            actual = mod.run_asset_framework_integration(
                deepcopy(ci),
                work6_result=deepcopy(w6),
                canonical_input_schema_path=troot / "05_C_Canonical_Input.schema.json",
                work6_output_schema_path=troot / "57_C_Work6_Mentor_Adjustment_Result.schema.json",
                work7_output_schema_path=troot / "68_C_Work7_V70_Asset_Framework_Result.schema.json",
                funding_context=deepcopy(funding),
                funding_context_schema_path=troot / "80_C_Work7_Funding_Context.schema.json",
                evaluated_at=C7_EVALUATED_AT,
            )
        finally:
            sys.path[:] = old_path
            _clear_c7_modules()

        evidence = {
            "c7_package_sha256": file_sha256(c7_zip),
            "c7_golden_example_sha256": file_sha256(troot / "examples/work7/Work7_Aligned_Protected_READY_FOR_PM_GATE.json"),
            "canonical_input": ci,
            "work6_result": w6,
            "funding_context": funding,
            "c7_golden": c7_golden,
        }
        return actual, evidence


def executor(fixtures: dict[str, Any], spec: Mapping[str, Any], checkpoint_root: Path) -> dict[str, Any]:
    # Work11 fixture is deliberately not used to construct the runtime output.
    if "c7_loop1_result" not in fixtures:
        raise Work12Error("C8C9.W12.FIXTURE_ROLE", "missing c7_loop1_result")
    if spec.get("scenario_id") != "C8C9-W12-GS-LOOP1_BOUNDARY":
        raise Work12Error("C8C9.W12.SCENARIO", str(spec.get("scenario_id")))
    actual, _ = rerun_frozen_c7_work7(checkpoint_root)
    return actual
