"""C8C9 Work16 - Protected Holding + Drift + Radar E2E verification harness.

QA-only harness. It consumes frozen C Work6/Work7 canonical logic and the
already CLOSED C8C9 Work8/Work9 integration seam. It verifies:
- protected holdings are not turned into allocation-driven sell/reduce actions;
- non-protected rows retain true Final Target / Drift semantics;
- Drift Universe is instrument-complete (Current union Final Target; no OTHER bucket);
- four Radar views expose the same six axis ids / Chinese labels / order;
- client-facing projection is a lossless rendering of machine-readable canonicals.

It does not patch V82/V75/V70/C1-7, create a Report Runtime, create Family F2,
or establish a second investment/business-rule engine.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import zipfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
HARNESS_ID = "C8C9-W16-PROTECTED-DRIFT-RADAR-E2E-v1.0.0"
TAG = "2026-09-29_2229"
RADAR_VIEW_IDS = ["CURRENT_ATTACK", "TARGET_ATTACK", "CURRENT_DEFENSE", "TARGET_DEFENSE"]
RADAR_AXES = [
    ("BULL_EARLY", "牛市初期", 1),
    ("BULL_MID", "牛市中期", 2),
    ("BULL_LATE", "牛市末期", 3),
    ("BEAR_NON_RECESSION_VALUATION", "非衰退熊市／估值壓縮", 4),
    ("BEAR_RECESSION", "景氣衰退熊市", 5),
    ("FINANCIAL_LIQUIDITY_CRISIS", "金融／流動性危機", 6),
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _set_position_weight(snapshot: dict[str, Any], instrument_id: str, weight: float) -> None:
    for row in snapshot["positions"]:
        if row.get("instrument_id") == instrument_id:
            row["weight"]["value_state"] = "KNOWN"
            row["weight"]["value"] = weight
            row["portfolio_amount"]["value_state"] = "KNOWN"
            row["portfolio_amount"]["amount"] = float(snapshot["denominator"]["amount"]) * weight
            return
    raise KeyError(instrument_id)


def _client_projection(c7: Mapping[str, Any]) -> dict[str, Any]:
    drift_rows = []
    for row in c7["drift_snapshot"]["items"]:
        drift_rows.append({
            "instrument_id": row["instrument_id"],
            "ticker": row.get("ticker"),
            "current": deepcopy(row["current_weight"]),
            "final_target": deepcopy(row["final_target_weight"]),
            "drift": deepcopy(row["drift"]),
            "protected": row["protected"],
            "status": row["client_facing_action"],
        })
    radar_views = []
    for view in c7["radar_snapshot"]["views"]:
        radar_views.append({
            "view_id": view["view_id"],
            "axes": [{
                "axis_id": axis["axis_id"],
                "name": axis["label_zh"],
                "order": axis["order"],
                "status": axis["score"]["value_state"],
                "value": axis["score"]["value"],
            } for axis in view["axes"]],
        })
    return {
        "final_target_id": c7["work6_final_target_reference"]["allocation_id"],
        "drift": drift_rows,
        "radar": {
            "as_of": c7["radar_snapshot"]["as_of"],
            "views": radar_views,
        },
    }


def validate_machine(work6: Mapping[str, Any], c7: Mapping[str, Any], w7_module: Any) -> list[str]:
    errors: list[str] = []
    errors += ["PROTECTED:" + e for e in w7_module.validate_protected_holding_contract(work6)]
    errors += ["DRIFT:" + e for e in w7_module.validate_drift_contract(work6)]
    errors += ["RADAR:" + e for e in w7_module.validate_radar_contract(work6)]
    hc = c7.get("hard_checks", {})
    for key in ("protected_existing_holding_contract", "portfolio_drift_snapshot_contract", "radar_axis_label_order_contract"):
        if hc.get(key) != "PASS": errors.append(f"HARD_CHECK:{key}")
    if c7.get("drift_snapshot") != work6.get("drift_snapshot"):
        errors.append("DRIFT_NOT_EXACT_WORK6_COPY")
    if c7.get("radar_snapshot") != work6.get("radar_snapshot"):
        errors.append("RADAR_NOT_EXACT_WORK6_COPY")
    report = c7.get("report_contract", {})
    for key in ("renderer_must_not_recompute_final_target", "renderer_must_use_work6_drift_snapshot", "renderer_must_use_work6_radar_snapshot"):
        if report.get(key) is not True: errors.append(f"REPORT_CONTRACT:{key}")
    # No catch-all/OTHER replacement is allowed in the instrument-level Drift Universe.
    ids = [r.get("instrument_id") for r in c7.get("drift_snapshot", {}).get("items", [])]
    if any(str(i).strip().upper() in {"OTHER", "OTHERS", "其他"} for i in ids):
        errors.append("DRIFT_OTHER_BUCKET_FORBIDDEN")
    if len(ids) != len(set(ids)): errors.append("DRIFT_DUPLICATE_INSTRUMENT")
    # Exact fixed Radar root definition and four-view parity.
    root_axes = [(a.get("axis_id"), a.get("label_zh"), a.get("order")) for a in c7.get("radar_snapshot", {}).get("axes", [])]
    if root_axes != RADAR_AXES: errors.append("RADAR_ROOT_AXES_MISMATCH")
    views = c7.get("radar_snapshot", {}).get("views", [])
    if [v.get("view_id") for v in views] != RADAR_VIEW_IDS: errors.append("RADAR_VIEW_ORDER_MISMATCH")
    for v in views:
        axes = [(a.get("axis_id"), a.get("label_zh"), a.get("order")) for a in v.get("axes", [])]
        if axes != RADAR_AXES: errors.append(f"RADAR_AXES_MISMATCH:{v.get('view_id')}")
        for a in v.get("axes", []):
            score = a.get("score", {})
            if score.get("value_state") == "UNKNOWN" and score.get("value") is not None:
                errors.append(f"RADAR_UNKNOWN_COERCED:{v.get('view_id')}:{a.get('axis_id')}")
    return errors


def validate_client_parity(c7: Mapping[str, Any], client: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if client.get("final_target_id") != c7.get("work6_final_target_reference", {}).get("allocation_id"):
        errors.append("CLIENT_FINAL_TARGET_ID_MISMATCH")
    machine_drift = c7.get("drift_snapshot", {}).get("items", [])
    client_drift = client.get("drift", [])
    if len(machine_drift) != len(client_drift): errors.append("CLIENT_DRIFT_LENGTH_MISMATCH")
    for m, c in zip(machine_drift, client_drift):
        expected = {
            "instrument_id": m.get("instrument_id"), "ticker": m.get("ticker"),
            "current": m.get("current_weight"), "final_target": m.get("final_target_weight"),
            "drift": m.get("drift"), "protected": m.get("protected"), "status": m.get("client_facing_action"),
        }
        if c != expected: errors.append(f"CLIENT_DRIFT_PARITY:{m.get('instrument_id')}")
    mr = c7.get("radar_snapshot", {})
    cr = client.get("radar", {})
    if cr.get("as_of") != mr.get("as_of"): errors.append("CLIENT_RADAR_ASOF_MISMATCH")
    mviews = mr.get("views", []); cviews = cr.get("views", [])
    if len(mviews) != len(cviews): errors.append("CLIENT_RADAR_VIEW_LENGTH_MISMATCH")
    for mv, cv in zip(mviews, cviews):
        if cv.get("view_id") != mv.get("view_id"):
            errors.append("CLIENT_RADAR_VIEW_ID_MISMATCH"); continue
        maxes = mv.get("axes", []); caxes = cv.get("axes", [])
        if len(maxes) != len(caxes): errors.append(f"CLIENT_RADAR_AXIS_LENGTH:{mv.get('view_id')}")
        for ma, ca in zip(maxes, caxes):
            exp = {"axis_id": ma.get("axis_id"), "name": ma.get("label_zh"), "order": ma.get("order"),
                   "status": ma.get("score", {}).get("value_state"), "value": ma.get("score", {}).get("value")}
            if ca != exp: errors.append(f"CLIENT_RADAR_PARITY:{mv.get('view_id')}:{ma.get('axis_id')}")
    return errors


def validate_protected_deployment(work9: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    items = work9.get("canonical_deployment_result", {}).get("items", [])
    tsm = [x for x in items if x.get("asset_id") == "TSM.US"]
    if len(tsm) != 1: return ["WORK9_TSM_CARDINALITY"]
    row = tsm[0]
    if row.get("source_action") != "REDUCE_RISK": errors.append("WORK9_RAW_RISK_NOT_VISIBLE")
    if row.get("client_preference_action") != "HOLD_PROTECTED": errors.append("WORK9_PROTECTED_PREFERENCE_LOST")
    if row.get("canonical_action") != "HOLD": errors.append("WORK9_CLIENT_CANONICAL_NOT_HOLD")
    mr = work9.get("mentor_return", {})
    if mr.get("mentor_may_explain_but_not_mutate_actions") is not True: errors.append("MENTOR_MUTATION_NOT_FORBIDDEN")
    if mr.get("risk_signal_and_client_preference_must_remain_separate") is not True: errors.append("RISK_PREFERENCE_NOT_SEPARATE")
    return errors


def execute() -> dict[str, Any]:
    c7zip = ROOT / "SOURCE_PACKAGE/UPSTREAM_C7/C_Work07_V70AssetFramework_LockedResidual_RadarSnapshot_RECHECK6_PASS_2026-09-24_Checkpoint.zip"
    with tempfile.TemporaryDirectory(prefix="w16_c7_") as td:
        c7root = Path(td)
        with zipfile.ZipFile(c7zip) as z: z.extractall(c7root)
        sys.path.insert(0, str(c7root))
        try:
            w6mod = _load_module("c7_w6_w16", c7root / "work6/adjustment_loop.py")
            w7mod = _load_module("c7_w7_w16", c7root / "work7/asset_framework.py")
            w6 = json.loads((c7root / "examples/work6/Work6_ProtectedStock_FinalTarget_CONFIRMED.json").read_text(encoding="utf-8"))
            # Produce a real non-protected Drift using the frozen Work6 drift algorithm:
            # Current 60/5/35 -> confirmed Final Target 55/5/40.
            cur = w6["final_target_engine_result"]["allocations"]["current_allocation"]["snapshot"]
            _set_position_weight(cur, "0050.TW", 0.60)
            _set_position_weight(cur, "TSM.US", 0.05)
            _set_position_weight(cur, "SGOV.US", 0.35)
            states = {r["instrument_id"]: r for r in w6["preference_locks"]}
            final = w6["final_target"]["snapshot"]
            w6["drift_snapshot"] = w6mod._drift_snapshot(cur, final, states, "2026-09-29T22:29:00+08:00")
            radar_request = {"radar_scores": [{
                "view_id": "CURRENT_ATTACK",
                "scores": [
                    {"axis_id": "BULL_EARLY", "value_state": "KNOWN", "value": 0.8, "source_reference_ids": ["SRC_CLIENT"]},
                    {"axis_id": "BULL_MID", "value_state": "UNKNOWN", "value": None, "source_reference_ids": ["SRC_CLIENT"]},
                ],
                "source_reference_ids": ["SRC_CLIENT"],
            }]}
            w6["radar_snapshot"] = w6mod._radar_snapshot(radar_request, "2026-09-29T22:29:00+08:00")
            ci = json.loads((c7root / "examples/canonical_input_valid.json").read_text(encoding="utf-8"))
            for field, value in (("stock_tactical_weight", .60), ("bond_tactical_weight", .40), ("v70_original_dry_powder_weight", 0.0)):
                ci["v70_asset_framework"][field]["value"] = value
            ci["v70_asset_framework"]["stock_tactical_amount"]["amount"] = 600000.0
            ci["v70_asset_framework"]["bond_tactical_amount"]["amount"] = 400000.0
            ci["v70_asset_framework"]["v70_original_dry_powder_amount"]["amount"] = 0.0
            funding = json.loads((c7root / "examples/work7/Work7_FundingContext_VALID.json").read_text(encoding="utf-8"))
            c7 = w7mod.run_asset_framework_integration(
                ci, work6_result=w6,
                canonical_input_schema_path=c7root / "05_C_Canonical_Input.schema.json",
                work6_output_schema_path=c7root / "57_C_Work6_Mentor_Adjustment_Result.schema.json",
                work7_output_schema_path=c7root / "68_C_Work7_V70_Asset_Framework_Result.schema.json",
                funding_context=funding, funding_context_schema_path=c7root / "80_C_Work7_Funding_Context.schema.json",
                evaluated_at="2026-09-29T22:29:00+08:00",
            )
            machine_errors = validate_machine(w6, c7, w7mod)
            client = _client_projection(c7)
            parity_errors = validate_client_parity(c7, client)
        finally:
            if sys.path and sys.path[0] == str(c7root): sys.path.pop(0)

    w9 = _load_module("w9_w16", ROOT / "WORK9_OUTPUT/C8C9_Work9_Unified_Deployment_Mentor_Return.py")
    w9req = json.loads((ROOT / "WORK11_OUTPUT/FIXTURES/W15_W16_W18_WORK9_INPUT_HAPPY.json").read_text(encoding="utf-8"))
    w9out = w9.build_unified_deployment(w9req)
    protected_errors = validate_protected_deployment(w9out)
    result = {
        "harness_id": HARNESS_ID,
        "machine_readable": {"work6": w6, "c_work7": c7},
        "client_facing": client,
        "protected_deployment": w9out,
        "validation": {
            "machine_errors": machine_errors,
            "client_parity_errors": parity_errors,
            "protected_deployment_errors": protected_errors,
        },
    }
    result["canonical_result_sha256"] = digest({
        "c_work7": c7, "client_facing": client,
        "protected_canonical_deployment": w9out["canonical_deployment_result"],
        "mentor_return": w9out["mentor_return"],
    })
    return result


if __name__ == "__main__":
    print(json.dumps(execute(), ensure_ascii=False, indent=2, sort_keys=True))
