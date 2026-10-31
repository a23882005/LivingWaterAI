"""C8C9 Work8 - Protected Holding + Client-action Protection.

C8C9-owned integration protection seam only.

This module binds the existing C Work7 protected-holding preference contract to
an already-integrated frozen V82 result. It preserves the complete canonical V82
output without rewriting risk/fundamental/technical/Hard-Gate evidence while
preventing an allocation-layer protected holding from being silently translated
into a client-facing sell-all/reduce-to-zero or an implicit Final Target change.

It does NOT patch V82/V75, recompute Final Target or Drift, classify a V82 risk
action as an allocation action, create a second investment/funding engine, or
perform Family/Production work.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import math
import importlib.util
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work8.ProtectedHoldingProtectionInput"
INPUT_CONTRACT_VERSION = "C8C9-W8-PHPI-v1.0.1"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work8.ProtectedHoldingProtectionResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W8-PHPO-v1.0.1"
C_WORK7_CONTRACT_NAME = "LivingWaterAI.C.Work7.AssetFrameworkIntegrationResult"
C_WORK7_CONTRACT_VERSION = "C-W7-v1.2.0"
WORK4_CONTRACT_NAME = "LivingWaterAI.C8C9.Work4.V82IntegrationResult"
WORK4_CONTRACT_VERSION = "C8C9-W4-V82AO-v1.0.0"
V82_OUTPUT_NAME = "LivingWaterAI.V82.RuntimeOutput"
V82_OUTPUT_VERSION = "V82-OUTPUT-v1.0.1-W2-RECHECK2"
V82_RULE_VERSION = "V82-v1.21.0"

FORMAL_MAPPING_META = (
    (1,"今日特殊分類","#40 `primary_special_classification`"),
    (2,"目前部署階段","#39 `normal_deployment_mode`＋#41 Context"),
    (3,"目標與完成率","#36 `project_target_position`＋#37 `confirmed_position`＋#38 `actual_completion_rate`"),
    (4,"今日動作","#41 `execution_action`"),
    (5,"執行比例","#42 `canonical_deployment_target_rate`"),
    (6,"執行金額","#43 `execution_amount`"),
    (7,"執行股數","#44 `execution_quantity`"),
    (8,"執行價格","#45 `execution_price`"),
    (9,"成交後完成率","#46 `projected_post_fill_completion_rate`"),
    (10,"是否掛單","#47 `order_submission_plan.should_place_order`"),
    (11,"掛單方式","#47 `order_submission_plan.{order_type,time_in_force,scheduling_mode}`"),
    (12,"取消條件","#48 `cancel_conditions`"),
    (13,"下一次重新評估條件","#49 `reevaluation_conditions`"),
)

_ROOT = Path(__file__).resolve().parents[1]
_INPUT_SCHEMA = _ROOT / "WORK8_OUTPUT/C8C9_Work8_Protected_Holding_Input.schema_RECHECK2_2026-09-28_0157.json"
_OUTPUT_SCHEMA = _ROOT / "WORK8_OUTPUT/C8C9_Work8_Protected_Holding_Output.schema_RECHECK2_2026-09-28_0157.json"
_WORK4_SCHEMA = _ROOT / "WORK4_OUTPUT/C8C9_Work4_V82_Integration_Output.schema_2026-09-26_1429.json"
_C7_SCHEMA = _ROOT / "WORK8_OUTPUT/C8C9_Work8_Frozen_C7_AssetFrameworkResult.schema_RECHECK2_2026-09-28_0157.json"


class ProtectedHoldingProtectionError(ValueError):
    """Fail-closed Work8 integration error."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise ProtectedHoldingProtectionError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W8.SHAPE", f"{field} must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W8.SHAPE", f"{field} must be a non-empty string")
    return value


def _canon(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W8.NON_JSON", f"value is not canonical JSON serializable: {exc}")


def _digest(value: Any) -> str:
    raw = json.dumps(_canon(value), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


@lru_cache(maxsize=None)
def _load_schema(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(obj)
        return obj
    except Exception as exc:  # pragma: no cover - package corruption
        _fail("C8C9.W8.SCHEMA_LOAD", f"cannot load {path.name}: {exc}")


@lru_cache(maxsize=None)
def _validator(path: Path) -> Draft202012Validator:
    return Draft202012Validator(_load_schema(path))


def _absence_contract():
    import importlib.util
    path=Path(__file__).resolve().parents[4]/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/funding_absence.py'
    spec=importlib.util.spec_from_file_location('c7_confirmed_absence_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _schema(value: Any, path: Path, code: str) -> None:
    validator=_validator(path);absence=_absence_contract()
    if absence.is_extended(value):validator=Draft202012Validator(absence.extend_schema(validator.schema))
    errors = sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        e = errors[0]
        loc = "/".join(str(x) for x in e.absolute_path) or "$"
        _fail(code, f"{loc}: {e.message}")


def _known_number(slot: Any, field: str) -> float:
    obj = _mapping(slot, field)
    if obj.get("value_state") != "KNOWN":
        _fail("C8C9.W8.PROTECTED_CONTRACT", f"{field} must be KNOWN")
    v = obj.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        _fail("C8C9.W8.PROTECTED_CONTRACT", f"{field}.value must be finite number")
    return float(v)


def _single(rows: Any, asset_id: str, field: str, *, required: bool = True) -> Mapping[str, Any] | None:
    if not isinstance(rows, list):
        _fail("C8C9.W8.SHAPE", f"{field} must be an array")
    matches = [r for r in rows if isinstance(r, Mapping) and r.get("instrument_id") == asset_id]
    if len(matches) > 1:
        _fail("C8C9.W8.DUPLICATE_ASSET", f"{field} contains duplicate {asset_id}")
    if required and not matches:
        _fail("C8C9.W8.ASSET_LINEAGE", f"{asset_id} missing from {field}")
    return matches[0] if matches else None


def _canonical_value(canonical: Mapping[str, Any], name: str) -> Any:
    env = _mapping(canonical.get(name), f"canonical_v82_output.canonical_analysis.{name}")
    if env.get("field_name") != name or "value" not in env:
        _fail("C8C9.W8.V82_SIGNAL", f"canonical V82 field envelope invalid: {name}")
    return deepcopy(env.get("value"))


def _collect_issue_codes(canonical: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for name, env in canonical.items():
        obj = _mapping(env, f"canonical_v82_output.canonical_analysis.{name}")
        codes = obj.get("issue_codes")
        if not isinstance(codes, list) or any(not isinstance(x, str) for x in codes):
            _fail("C8C9.W8.V82_SIGNAL", f"issue_codes invalid for {name}")
        for code in codes:
            if code not in out:
                out.append(code)
    return out


def _verify_formal_13_projection(v82: Mapping[str, Any], canonical: Mapping[str, Any]) -> None:
    rows = v82.get("fields_1_to_13")
    if not isinstance(rows, list) or len(rows) != 13:
        _fail("C8C9.W8.V82_13_VIEW_CONFLICT", "V82 fields_1_to_13 must contain exactly 13 rows")
    order = _canonical_value(canonical, "order_submission_plan")
    if order == "UNKNOWN":
        place = "UNKNOWN"
        order_view = "UNKNOWN"
    else:
        om = _mapping(order, "canonical_v82_output.canonical_analysis.order_submission_plan.value")
        place = om.get("should_place_order")
        order_view = {k: om.get(k) for k in ("order_type", "time_in_force", "scheduling_mode")}
    expected = (
        _canonical_value(canonical, "primary_special_classification"),
        {"mode": _canonical_value(canonical, "normal_deployment_mode"),
         "execution_context": _canonical_value(canonical, "execution_action")},
        {"project_target_position": _canonical_value(canonical, "project_target_position"),
         "confirmed_position": _canonical_value(canonical, "confirmed_position"),
         "actual_completion_rate": _canonical_value(canonical, "actual_completion_rate")},
        _canonical_value(canonical, "execution_action"),
        _canonical_value(canonical, "canonical_deployment_target_rate"),
        _canonical_value(canonical, "execution_amount"),
        _canonical_value(canonical, "execution_quantity"),
        _canonical_value(canonical, "execution_price"),
        _canonical_value(canonical, "projected_post_fill_completion_rate"),
        place, order_view,
        _canonical_value(canonical, "cancel_conditions"),
        _canonical_value(canonical, "reevaluation_conditions"),
    )
    for i, (row, meta, exp) in enumerate(zip(rows, FORMAL_MAPPING_META, expected), 1):
        obj = _mapping(row, f"canonical_v82_output.fields_1_to_13[{i-1}]")
        ordinal, label, mapping = meta
        if obj.get("ordinal") != ordinal or obj.get("display_label") != label or obj.get("canonical_mapping") != mapping:
            _fail("C8C9.W8.V82_13_VIEW_CONFLICT", f"V82 formal row {i} metadata drift")
        if obj.get("value") != exp:
            _fail("C8C9.W8.V82_13_VIEW_CONFLICT", f"V82 formal row {i} differs from canonical projection")


def protect_client_action(request: Mapping[str, Any]) -> dict[str, Any]:
    """Apply Work8 protection without changing either upstream source contract.

    Protected preference and V82 risk output are deliberately parallel facts:
    the first controls client preference/target mutation; the second remains
    visible as source-owned risk/execution evidence. Work8 never decides that a
    V82 REDUCE/SELL signal is "just optimization", and never converts it to HOLD.
    """
    req = _canon(_mapping(request, "request"))
    _schema(req, _INPUT_SCHEMA, "C8C9.W8.INPUT_SCHEMA")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W8.CONTRACT", "Work8 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W8.BASELINE", "Frozen Baseline mismatch")
    run_id = _nonempty(req.get("run_id"), "run_id")

    c7 = _mapping(req.get("c_work7_asset_framework_result"), "c_work7_asset_framework_result")
    # RECHECK2 hardening: Work8 consumes a serialized C Work7 result directly, so
    # validate the exact frozen C7 schema before relying on a selected subset.
    family_version = c7.get("contract_version") == "C-W7-FAMILY-LT-v1.0.0"
    if family_version:
        # Explicit PM-approved profile; the frozen legacy schema remains exact.
        spec=importlib.util.spec_from_file_location("c7_family_serialized_contract",_ROOT/"work7/family_long_term.py")
        family=importlib.util.module_from_spec(spec);spec.loader.exec_module(family)
        try:family.validate_result(c7)
        except ValueError as exc:_fail("C8C9.W8.C_WORK7_FAMILY_SOURCE",str(exc))
        if any(value != "PASS" for value in c7.get("hard_checks",{}).values()):
            _fail("C8C9.W8.C_WORK7_FAMILY_HARD_CHECKS","All original C7 hard checks must pass")
    else:
        _schema(c7, _C7_SCHEMA, "C8C9.W8.C_WORK7_SCHEMA")
    if c7.get("contract_name") != C_WORK7_CONTRACT_NAME or (not family_version and c7.get("contract_version") != C_WORK7_CONTRACT_VERSION):
        _fail("C8C9.W8.C_WORK7_CONTRACT", "C Work7 contract/version mismatch")
    identity = _mapping(c7.get("identity"), "c_work7.identity")
    if identity.get("run_id") != run_id:
        _fail("C8C9.W8.RUN_MISMATCH", "C Work7 identity.run_id differs")
    if c7.get("status") != "READY_FOR_PM_GATE":
        _fail("C8C9.W8.C_WORK7_STATUS", "C Work7 must be READY_FOR_PM_GATE")
    lineage = _mapping(c7.get("snapshot_lineage"), "c_work7.snapshot_lineage")
    if lineage.get("run_id") != run_id or lineage.get("lineage_status") != "SAME_RUN":
        _fail("C8C9.W8.RUN_MISMATCH", "C Work7 snapshot lineage is not SAME_RUN")
    c7_snapshot_id = _nonempty(c7.get("work7_snapshot_id"), "c_work7.work7_snapshot_id")
    c6_snapshot_id = _nonempty(c7.get("parent_work6_snapshot_id"), "c_work7.parent_work6_snapshot_id")
    if lineage.get("work6_snapshot_id") != c6_snapshot_id:
        _fail("C8C9.W8.C7_LINEAGE", "C Work7 parent_work6_snapshot_id differs from snapshot_lineage.work6_snapshot_id")
    request_id = _nonempty(identity.get("request_id"), "c_work7.identity.request_id")
    if lineage.get("canonical_request_id") != request_id:
        _fail("C8C9.W8.C7_LINEAGE", "C Work7 identity.request_id differs from snapshot_lineage.canonical_request_id")
    final_ref = _mapping(c7.get("work6_final_target_reference"), "c_work7.work6_final_target_reference")
    final_target_allocation_id = _nonempty(final_ref.get("allocation_id"), "c_work7.work6_final_target_reference.allocation_id")
    final_target_confirmed_at = _nonempty(final_ref.get("confirmed_at"), "c_work7.work6_final_target_reference.confirmed_at")
    final_target_confirmed_by = _nonempty(final_ref.get("confirmed_by"), "c_work7.work6_final_target_reference.confirmed_by")

    hard = _mapping(c7.get("hard_checks"), "c_work7.hard_checks")
    if hard.get("protected_existing_holding_contract") != "PASS":
        _fail("C8C9.W8.PROTECTED_CONTRACT", "C protected-existing-holding contract is not PASS")
    if hard.get("portfolio_drift_snapshot_contract") != "PASS":
        _fail("C8C9.W8.PROTECTED_CONTRACT", "C drift snapshot contract is not PASS")
    if hard.get("same_run_snapshot_lineage") != "PASS":
        _fail("C8C9.W8.RUN_MISMATCH", "C same-run hard check is not PASS")
    report = _mapping(c7.get("report_contract"), "c_work7.report_contract")
    if report.get("renderer_must_not_recompute_final_target") is not True:
        _fail("C8C9.W8.FINAL_TARGET_OWNER", "renderer_must_not_recompute_final_target must remain true")
    if report.get("renderer_must_use_work6_drift_snapshot") is not True:
        _fail("C8C9.W8.DRIFT_OWNER", "renderer_must_use_work6_drift_snapshot must remain true")
    if report.get("risk_warning_is_not_sell_instruction") is not True:
        _fail("C8C9.W8.RISK_ACTION_BOUNDARY", "risk warning must remain separate from sell instruction")

    w4 = _mapping(req.get("work4_v82_integration_result"), "work4_v82_integration_result")
    _schema(w4, _WORK4_SCHEMA, "C8C9.W8.WORK4_SCHEMA")
    if w4.get("contract_name") != WORK4_CONTRACT_NAME or w4.get("contract_version") != WORK4_CONTRACT_VERSION:
        _fail("C8C9.W8.WORK4_CONTRACT", "Work4 V82 integration contract/version mismatch")
    if w4.get("baseline_id") != BASELINE_ID or w4.get("run_id") != run_id:
        _fail("C8C9.W8.RUN_MISMATCH", "Work4 run/baseline mismatch")
    if w4.get("source_semantics_policy") != "PRESERVE_V82_CANONICAL_OUTPUT_NO_LOSSY_TRANSLATION":
        _fail("C8C9.W8.V82_SOURCE_SEMANTICS", "Work4 V82 preserve-source policy drift")
    if w4.get("integration_diagnostics") != []:
        _fail("C8C9.W8.V82_SOURCE_SEMANTICS", "Work4 integration diagnostics must be empty for Work8")
    asset_id = _nonempty(w4.get("asset_id"), "work4.asset_id")
    work4_handoff_id = _nonempty(w4.get("work3_context_handoff_id"), "work4.work3_context_handoff_id")
    work4_authorization = _nonempty(w4.get("authorization_reference"), "work4.authorization_reference")
    if work4_authorization != final_target_allocation_id:
        _fail("C8C9.W8.FINAL_TARGET_BINDING", "Work4 authorization_reference differs from C7 confirmed Final Target allocation_id")

    v82 = _mapping(w4.get("canonical_v82_output"), "work4.canonical_v82_output")
    if v82.get("contract_name") != V82_OUTPUT_NAME or v82.get("contract_version") != V82_OUTPUT_VERSION:
        _fail("C8C9.W8.V82_CONTRACT", "canonical V82 output contract/version mismatch")
    if v82.get("run_id") != run_id or v82.get("asset_id") != asset_id:
        _fail("C8C9.W8.V82_LINEAGE", "canonical V82 output run/asset mismatch")
    if v82.get("rule_version") != V82_RULE_VERSION:
        _fail("C8C9.W8.V82_RULE_VERSION", "canonical V82 rule version mismatch")
    if v82.get("upstream_v70_snapshot_id") != w4.get("upstream_v70_snapshot_id"):
        _fail("C8C9.W8.V82_LINEAGE", "V82 upstream V70 snapshot mismatch")
    canonical = _mapping(v82.get("canonical_analysis"), "canonical_v82_output.canonical_analysis")
    if len(canonical) != 49:
        _fail("C8C9.W8.V82_SIGNAL", "V82 canonical analysis must remain exact 49-field contract")
    for name, env in canonical.items():
        obj = _mapping(env, f"canonical_v82_output.canonical_analysis.{name}")
        if obj.get("run_id") != run_id:
            _fail("C8C9.W8.V82_LINEAGE", f"canonical V82 field {name} run_id mismatch")
    # RECHECK1 hardening: a serialized Work4/V82 payload must not keep a valid
    # 49-field canonical analysis while mutating only the 13-field formal view.
    # That would let a presentation consumer hide/relabel the source-owned risk
    # action without changing the canonical fields. Validate the full projection.
    _verify_formal_13_projection(v82, canonical)

    # C Work7 must contain the exact asset being protected/evaluated.
    framework = _mapping(c7.get("integrated_asset_framework"), "c_work7.integrated_asset_framework")
    target = _single(framework.get("instrument_targets"), asset_id,
                     "c_work7.integrated_asset_framework.instrument_targets")
    drift_snapshot = _mapping(c7.get("drift_snapshot"), "c_work7.drift_snapshot")
    drift = _single(drift_snapshot.get("items"), asset_id, "c_work7.drift_snapshot.items")
    protected_row = _single(c7.get("protected_locked_weights"), asset_id,
                            "c_work7.protected_locked_weights", required=False)
    integrated_target = target.get("integrated_weight")
    if isinstance(integrated_target, bool) or not isinstance(integrated_target, (int, float)) or not math.isfinite(float(integrated_target)):
        _fail("C8C9.W8.FINAL_TARGET_BINDING", "C7 integrated target must be a finite number")
    v82_project_target = _canonical_value(canonical, "project_target_position")
    if isinstance(v82_project_target, bool) or not isinstance(v82_project_target, (int, float)) or not math.isfinite(float(v82_project_target)):
        _fail("C8C9.W8.FINAL_TARGET_BINDING", "V82 project_target_position must be a finite number")
    if abs(float(v82_project_target) - float(integrated_target)) > 1e-12:
        _fail("C8C9.W8.FINAL_TARGET_BINDING", "V82 project_target_position differs from C7 integrated target")

    is_protected = bool(target.get("protected") is True or drift.get("protected") is True or protected_row is not None)
    if is_protected:
        if not (target.get("protected") is True and drift.get("protected") is True and protected_row is not None):
            _fail("C8C9.W8.PROTECTED_CONTRACT", "protected flags/lock row must agree across C Work7 snapshots")
        if target.get("allocation_rule") != "LOCKED_CURRENT_WEIGHT":
            _fail("C8C9.W8.PROTECTED_CONTRACT", "protected allocation_rule must remain LOCKED_CURRENT_WEIGHT")
        current = protected_row.get("current_weight")
        final_locked = protected_row.get("final_target_weight")
        locked_drift = protected_row.get("drift")
        vals = (current, final_locked, locked_drift, target.get("work6_final_target_weight"), target.get("integrated_weight"))
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in vals):
            _fail("C8C9.W8.PROTECTED_CONTRACT", "protected numeric contract values must be finite")
        current_f = float(current)
        if abs(float(final_locked) - current_f) > 1e-12 or abs(float(locked_drift)) > 1e-12:
            _fail("C8C9.W8.PROTECTED_CONTRACT", "protected Final Target must equal Current and Drift must equal zero")
        if abs(float(target.get("work6_final_target_weight")) - current_f) > 1e-12 or abs(float(target.get("integrated_weight")) - current_f) > 1e-12:
            _fail("C8C9.W8.PROTECTED_CONTRACT", "integrated target must preserve protected current weight")
        drift_current = _known_number(drift.get("current_weight"), "drift.current_weight")
        drift_final = _known_number(drift.get("final_target_weight"), "drift.final_target_weight")
        drift_value = _known_number(drift.get("drift"), "drift.drift")
        if abs(drift_current-current_f) > 1e-12 or abs(drift_final-current_f) > 1e-12 or abs(drift_value) > 1e-12:
            _fail("C8C9.W8.PROTECTED_CONTRACT", "C Work6/7 drift does not preserve protected lock")
        if drift.get("client_facing_action") != "HOLD_PROTECTED":
            _fail("C8C9.W8.CLIENT_ACTION", "protected client-facing action must remain HOLD_PROTECTED")
        client_action = "HOLD_PROTECTED"
        allocation_rule = "LOCKED_CURRENT_WEIGHT"
        current_weight: float | None = current_f
        final_target_weight: float | None = current_f
        drift_weight: float | None = 0.0
    else:
        if target.get("protected") is not False or drift.get("protected") is not False:
            _fail("C8C9.W8.PROTECTED_CONTRACT", "non-protected asset flags must agree")
        client_action = _nonempty(drift.get("client_facing_action"), "drift.client_facing_action")
        allocation_rule = _nonempty(target.get("allocation_rule"), "target.allocation_rule")
        current_weight = _known_number(drift.get("current_weight"), "drift.current_weight")
        final_target_weight = _known_number(drift.get("final_target_weight"), "drift.final_target_weight")
        drift_weight = _known_number(drift.get("drift"), "drift.drift")

    raw_action = _canonical_value(canonical, "execution_action")
    fundamental = _canonical_value(canonical, "fundamental_state")
    valuation = _canonical_value(canonical, "valuation_state")
    classification = _canonical_value(canonical, "primary_special_classification")
    technical_names = [
        "td9_high_state", "td9_low_state", "kd_state", "macd_state", "ma_state",
        "emv_state", "rsi_state", "volume_price_state", "daily_timeframe_state",
        "weekly_timeframe_state", "monthly_timeframe_state", "runaway_state",
        "macro_state", "credit_liquidity_state", "material_news_policy_state",
    ]
    technical = {name: _canonical_value(canonical, name) for name in technical_names}
    issue_codes = _collect_issue_codes(canonical)
    v82_digest = _digest(v82)

    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "run_id": run_id,
        "asset_id": asset_id,
        "source_binding": {
            "c_work7_snapshot_id": c7_snapshot_id,
            "c_work6_snapshot_id": c6_snapshot_id,
            "final_target_allocation_id": final_target_allocation_id,
            "final_target_confirmed_at": final_target_confirmed_at,
            "final_target_confirmed_by": final_target_confirmed_by,
            "work4_context_handoff_id": work4_handoff_id,
            "work4_v82_snapshot_id": _nonempty(v82.get("v82_snapshot_id"), "v82_snapshot_id"),
            "c_work7_sha256": _digest(c7),
            "work4_v82_integration_sha256": _digest(w4),
            "canonical_v82_output_sha256": v82_digest,
        },
        "protected_holding": {
            "protection_applied": is_protected,
            "current_weight": current_weight,
            "final_target_weight": final_target_weight,
            "drift": drift_weight,
            "allocation_rule": allocation_rule,
            "client_facing_action": client_action,
            "target_change_authorized": False if is_protected else None,
            "explicit_client_unlock_required_before_target_change": True if is_protected else False,
        },
        "v82_signal_visibility": {
            "raw_execution_action": raw_action,
            "fundamental_state": fundamental,
            "valuation_state": valuation,
            "primary_special_classification": classification,
            "technical_macro_signal_values": technical,
            "source_issue_codes": issue_codes,
            "canonical_v82_output_preserved": True,
            "canonical_v82_output_sha256": v82_digest,
            "hard_gate_signal_recomputed": False,
            "risk_signal_rewritten": False,
        },
        "client_action_protection": {
            "client_facing_action": client_action,
            "client_action_source": "C_WORK6_7_DRIFT_CONTRACT",
            "risk_disclosure_channel_available": True,
            "risk_warning_is_not_sell_instruction": True,
            "v82_risk_signal_exposed_without_rewrite": True,
            "silent_preference_mutation_forbidden": True,
            "sell_all_reduce_to_zero_from_allocation_optimization_forbidden": True,
            "v82_risk_action_not_reclassified_as_allocation_action": True,
        },
        "canonical_v82_output": deepcopy(v82),
        "source_semantics_policy": "PRESERVE_V82_RISK_SIGNAL_AND_C_PROTECTED_PREFERENCE_AS_PARALLEL_SOURCE_OWNED_FACTS",
        "integration_diagnostics": [],
    }
    _schema(result, _OUTPUT_SCHEMA, "C8C9.W8.OUTPUT_SCHEMA")
    return result


__all__ = [
    "BASELINE_ID", "INPUT_CONTRACT_NAME", "INPUT_CONTRACT_VERSION",
    "OUTPUT_CONTRACT_NAME", "OUTPUT_CONTRACT_VERSION", "ProtectedHoldingProtectionError",
    "protect_client_action",
]
