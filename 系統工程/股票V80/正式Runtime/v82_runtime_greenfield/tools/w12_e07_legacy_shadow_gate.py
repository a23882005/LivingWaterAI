#!/usr/bin/env python3
from __future__ import annotations

import csv
import dataclasses
import hashlib
import importlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT.parent
EVIDENCE = LATEST / "E07_Evidence"
LEGACY_DIR = EVIDENCE / "legacy_baseline_readonly"
QA = LATEST / "QA_Results"
FROZEN_INPUTS = EVIDENCE / "A78_W12_E07_Frozen_Semantic_Inputs.json"
ADAPTER_MAP = EVIDENCE / "A78_W12_E07_Adapter_Mapping.tsv"

sys.path.insert(0, str(ROOT / "src"))

from livingwater_v82_runtime.validation import (  # noqa: E402
    C7_CONTRACT_NAME,
    C7_CONTRACT_VERSION,
    INPUT_CONTRACT_NAME,
    INPUT_CONTRACT_VERSION,
    validate_and_bind_funding,
)
from livingwater_v82_runtime.enums import (  # noqa: E402
    DataQuality,
    Freshness,
    OrderLifecycleState,
    PitStatus,
    PredicateTruth,
    RequirementLevel,
)
from livingwater_v82_runtime.core_rules import (  # noqa: E402
    EvidenceFact,
    arbitrate_primary_special_classification,
    evaluate_core_rule_state,
)
from livingwater_v82_runtime.deployment import (  # noqa: E402
    build_buy_execution_plan,
    calculate_position_gap,
    resolve_deployment_stage,
    select_deployment_mode,
    validate_order_transition,
)
from livingwater_v82_runtime.canonical_output import (  # noqa: E402
    CANONICAL_FIELD_NAMES,
    FORMAL_OUTPUT_NAMES,
    assemble_canonical_analysis,
    project_formal_execution_view,
)

RULE_VERSION = "V82-v1.21.0"
ALLOWED_DIFF_CLASSIFICATIONS = {
    "EXPECTED_RULE_CHANGE",
    "LEGACY_DEFECT",
    "NEW_RUNTIME_DEFECT",
    "DATA/CONTRACT_MISMATCH",
    "UNKNOWN_NEEDS_REVIEW",
}
EXPECTED_LEGACY_SHA = {
    "v82_engine.py": "a8b6f302489ada28c637685fb0aba4cb8251c2df38db562b6fdbedb11d95a1fb",
    "v82_models.py": "64f24120a20a4a2ca04df03a58812b6e358a6d56d64bda3a43036ae3e3ef10f4",
    "v82_deployment.py": "4b68774322b20a756e34f95846a1869f4c30fbd644c8e16872e6d3dfd42e9ea0",
    "test_v82_engine.py": "4a52c5bf404cf632fb6162ef4d637cc23786eb4ee0ff3b627304fd52abb6c7d0",
}
SOURCE_REFS = {
    "account_binding": "A78_W02_Funding_Account_Isolation_Contract.md",
    "funding_source": "A78_W02_Funding_Account_Isolation_Contract.md",
    "UNKNOWN": "A78_W03_Priority_Preemption_UNKNOWN_FailClosed_Contract.md",
    "Target/Gap/Completion": "A78_W03_Canonical_Formula_Rounding_Trading_Unit_Contract.md",
    "classification/priority": "A78_W03_Priority_Preemption_UNKNOWN_FailClosed_Contract.md",
    "order_lifecycle": "A78_W03_State_Machine_Execution_Lifecycle_Contract.md",
    "49_fields": "A78_W02_49_to_13_Output_Mapping.tsv",
    "13_fields": "A78_W02_49_to_13_Output_Mapping.tsv",
    "diagnostics": "A78_W03_Priority_Preemption_UNKNOWN_FailClosed_Contract.md",
    "determinism": "A78_W04_Cutover_Migration_Shadow_DualRun_Rollback_Blueprint.md",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def primitive(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: primitive(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def stable_digest(value: Any) -> str:
    raw = json.dumps(primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dstr(value: Any) -> str | None:
    if value is None:
        return None
    d = Decimal(str(value))
    return format(d.normalize(), "f") if d != 0 else "0"


def validate_e07_evidence_contract() -> dict[str, Any]:
    frozen = json.loads(FROZEN_INPUTS.read_text(encoding="utf-8"))
    expected_context = {
        "current": "V82-v1.21.0",
        "legacy": "v1.10.0",
        "funding_contract": "C-W7-FUND-v1.0.0",
    }
    if frozen.get("schema_version") != "W12-E07-FROZEN-SEMANTIC-v1":
        raise AssertionError("E07_FROZEN_SCHEMA_VERSION_MISMATCH")
    if frozen.get("rule_context") != expected_context:
        raise AssertionError("E07_FROZEN_RULE_CONTEXT_MISMATCH")

    with ADAPTER_MAP.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    required_cols = {
        "invariant", "frozen_semantic_fact", "legacy_adapter", "new_adapter",
        "business_rule_added", "difference_resolution_basis",
    }
    if not rows or set(rows[0]) != required_cols:
        raise AssertionError("E07_ADAPTER_COLUMNS_MISMATCH")
    invariants = [r["invariant"] for r in rows]
    expected_invariants = [
        "account_binding", "funding_source", "UNKNOWN", "Target/Gap/Completion",
        "classification/priority", "order_lifecycle", "49_fields", "13_fields",
        "diagnostics", "determinism",
    ]
    if len(rows) != len(expected_invariants) or len(set(invariants)) != len(invariants) or set(invariants) != set(expected_invariants):
        raise AssertionError("E07_ADAPTER_INVARIANT_COVERAGE_MISMATCH")
    bad_rule_rows = [r["invariant"] for r in rows if r["business_rule_added"].strip().upper() != "NO"]
    if bad_rule_rows:
        raise AssertionError("E07_ADAPTER_BUSINESS_RULE_ADDED:" + ",".join(bad_rule_rows))
    missing_basis = []
    for r in rows:
        basis = r["difference_resolution_basis"].strip()
        if not basis:
            missing_basis.append(r["invariant"] + ":EMPTY")
            continue
        # Adapter map must point to an existing formal W2/W3/W4 contract/blueprint artifact.
        if not (LATEST / basis).is_file():
            missing_basis.append(r["invariant"] + ":" + basis)
    if missing_basis:
        raise AssertionError("E07_ADAPTER_RESOLUTION_BASIS_MISSING:" + ",".join(missing_basis))
    return {
        "frozen_schema_version": frozen["schema_version"],
        "rule_context": frozen["rule_context"],
        "adapter_rows": len(rows),
        "adapter_invariants": invariants,
        "adapter_business_rule_rows": bad_rule_rows,
        "adapter_resolution_basis_verified": True,
    }


def verify_authorized_baseline() -> dict[str, str]:
    actual = {}
    for name, expected in EXPECTED_LEGACY_SHA.items():
        p = LEGACY_DIR / name
        if not p.is_file():
            raise AssertionError(f"LEGACY_BASELINE_MISSING:{name}")
        actual[name] = sha256(p)
        if actual[name] != expected:
            raise AssertionError(f"LEGACY_BASELINE_SHA_MISMATCH:{name}")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(LEGACY_DIR)
    compile_run = subprocess.run(
        [sys.executable, "-m", "py_compile", "v82_engine.py", "v82_models.py", "v82_deployment.py", "test_v82_engine.py"],
        cwd=str(LEGACY_DIR), env=env, capture_output=True, text=True,
    )
    if compile_run.returncode != 0:
        raise AssertionError("LEGACY_COMPILE_FAIL:" + (compile_run.stderr or compile_run.stdout)[-500:])
    test_run = subprocess.run(
        [sys.executable, "-m", "unittest", "-q", "test_v82_engine.py"],
        cwd=str(LEGACY_DIR), env=env, capture_output=True, text=True,
    )
    if test_run.returncode != 0 or "Ran 34 tests" not in ((test_run.stdout or "") + (test_run.stderr or "")):
        raise AssertionError("LEGACY_34_TEST_HEALTH_FAIL:" + ((test_run.stdout or "") + (test_run.stderr or ""))[-700:])
    return actual


def import_legacy():
    sys.path.insert(0, str(LEGACY_DIR))
    try:
        engine = importlib.import_module("v82_engine")
        models = importlib.import_module("v82_models")
        deployment = importlib.import_module("v82_deployment")
        return engine, models, deployment
    finally:
        try:
            sys.path.remove(str(LEGACY_DIR))
        except ValueError:
            pass


def runtime_input(case_id: str, common: dict[str, Any]) -> dict[str, Any]:
    identities = [
        ("TW_LOCAL_BROKER", "tw", "A"),
        ("TW_SUB_BROKERAGE", "sub", "B"),
        (common["domain"], common["broker"], common["account"]),
    ]
    contexts = []
    for domain, broker, account in identities:
        is_exec = (domain, broker, account) == (common["domain"], common["broker"], common["account"])
        eq = float(common["equity_executable_budget"]) if is_exec else 60.0
        contexts.append({
            "domain": domain,
            "broker": broker,
            "account": account,
            "bucket_new_investment_amount": 100,
            "brokerage_cash_state": {"total": 150, "available": 100, "unsettled": 20, "reserved": 10},
            "executable_budget": {
                "equity": {"amount": eq, "cash_basis": "AVAILABLE", "source_domain": domain, "source_broker": broker, "source_account": account},
                "bond": {"amount": 40, "cash_basis": "AVAILABLE", "source_domain": domain, "source_broker": broker, "source_account": account},
            },
            "source_reference_ids": [f"{case_id}:{domain}:{broker}:{account}"],
        })
    return {
        "contract_name": INPUT_CONTRACT_NAME,
        "contract_version": INPUT_CONTRACT_VERSION,
        "run_id": case_id,
        "client_project_version": "E07-FROZEN",
        "asset": {"asset_id": common["asset_id"], "asset_type": "BROAD_ETF", "asset_grade": "A", "portfolio_role": "CORE"},
        "execution_account": {"domain": common["domain"], "broker": common["broker"], "account": common["account"]},
        "client_target": {"project_target_position": float(common["project_target_position_amount"]), "authorization_reference": "E07-AUTH"},
        "upstream_v70_snapshot": {
            "run_id": case_id,
            "upstream_v70_snapshot_id": f"V70-{case_id}",
            "v70_stock_tactical_budget_amount": float(common["equity_executable_budget"]),
            "v70_stock_tactical_budget_currency": common["currency"],
            "v70_stock_tactical_budget_status": "KNOWN",
            "v70_stock_tactical_budget_data_as_of": "2026-09-26",
            "v70_original_dry_powder_amount": float(common["equity_executable_budget"]),
            "v70_original_dry_powder_currency": common["currency"],
            "v70_budget_source_reference": "E07-V70",
            "v70_budget_data_quality": "OK",
            "v70_budget_issue_codes": [],
        },
        "confirmed_position_snapshot": {},
        "source_lineage": [case_id, common["asset_id"], "ABC-E07-AUTH"],
        "market_data_bundle": {},
        "event_context": {},
        "c7_funding_context": {
            "contract_name": C7_CONTRACT_NAME,
            "contract_version": C7_CONTRACT_VERSION,
            "run_id": case_id,
            "base_currency": common["currency"],
            "bank_cash_scope": "OUT_OF_SCOPE",
            "total_new_investment_amount": 300,
            "contexts": contexts,
            "source_reference_ids": ["ABC-E07-C7"],
        },
    }


def legacy_technical(engine, technical: str):
    kw: dict[str, bool] = {}
    if technical in {"RIGHT_ADD", "RUNAWAY_UP_AND_RIGHT"}:
        kw.update(higher_low=True, kd_golden_cross=True, macd_bear_hist_shrinking_or_positive=True)
    if technical in {"RUNAWAY_UP", "RUNAWAY_UP_AND_RIGHT"}:
        kw.update(new_20d_close_high=True, kd_high_strong_not_breaking=True,
                  macd_bull_hist_expanding=True, ma5_gt_ma10_gt_ma20=True)
    if technical == "RUNAWAY_DOWN":
        kw.update(keeps_breaking_lows=True, macd_bear_hist_expanding=True, kd_low_weak=True)
    return engine.TechnicalSignals(**kw)


def new_predicates(technical: str):
    right = [PredicateTruth.FALSE, PredicateTruth.FALSE, PredicateTruth.FALSE]
    up_price = [PredicateTruth.FALSE]
    up_confirm = [PredicateTruth.FALSE, PredicateTruth.FALSE, PredicateTruth.FALSE]
    down_break = [PredicateTruth.FALSE]
    down_accel = [PredicateTruth.FALSE, PredicateTruth.FALSE]
    if technical in {"RIGHT_ADD", "RUNAWAY_UP_AND_RIGHT"}:
        right = [PredicateTruth.TRUE, PredicateTruth.TRUE, PredicateTruth.TRUE]
    if technical in {"RUNAWAY_UP", "RUNAWAY_UP_AND_RIGHT"}:
        up_price = [PredicateTruth.TRUE]
        up_confirm = [PredicateTruth.TRUE, PredicateTruth.TRUE, PredicateTruth.TRUE]
    if technical == "RUNAWAY_DOWN":
        down_break = [PredicateTruth.TRUE]
        down_accel = [PredicateTruth.TRUE, PredicateTruth.TRUE]
    return right, up_price, up_confirm, down_break, down_accel


def run_legacy_case(engine, case: dict[str, Any], common: dict[str, Any]) -> dict[str, Any]:
    unknown = case["safety"] == "REQUIRED_UNKNOWN"
    decision = engine.decide(
        hard_gate=engine.HardGateInput(budget_or_limit_unverified=unknown),
        technical=legacy_technical(engine, case["technical"]),
        price=engine.PriceLayerInput(left_price_condition=False, price_layer=case["legacy_price_layer"]),
        position=engine.PositionInput(
            target_amount=float(common["project_target_position_amount"]),
            current_amount=float(common["confirmed_position_amount"]),
            available_cash=float(common["equity_executable_budget"]),
        ),
        fundamentals_ok=True,
        credit_liquidity_safe=True,
        valuation_not_extreme=True,
        limit_price=float(common["normalized_order_price"]),
        meta=engine.SnapshotMeta(run_id=case["case_id"], analysis_timestamp="2026-09-26T08:12:00+08:00", market_data_as_of="2026-09-26"),
        asset_symbol=common["asset_id"],
        data_quality=(engine.DataQuality.INSUFFICIENT if unknown else engine.DataQuality.OK),
    )
    raw = primitive(decision)
    cls_name = decision.special_classification.name if decision.special_classification is not None else None
    current_label = {
        None: "無特殊分類",
        "LEFT_BUY": "左側買點",
        "RIGHT_ADD": "右側加碼",
        "RUNAWAY_UP": "Runaway Up",
        "RUNAWAY_DOWN": "Runaway Down",
        "TECHNICAL_REDUCTION": "技術減碼",
        "TRUE_RISK_REDUCTION": "真正降低風險",
    }[cls_name]
    normalized = {
        "account_binding": {"status": "UNSUPPORTED_LEGACY_CONTRACT"},
        "funding_source": {"available_cash": dstr(common["equity_executable_budget"]), "lineage": "UNSUPPORTED_LEGACY_CONTRACT"},
        "unknown_state": "LEGACY_HARD_GATE_CONFLATION" if unknown else "KNOWN_SAFE",
        "target_rate": dstr(decision.canonical_deployment_target_rate),
        "completion_rate": dstr(decision.target_completion_rate),
        "gap_rate": dstr(decision.deployment_gap_rate),
        "gap_amount": dstr(decision.deployment_gap_amount),
        "classification": current_label,
        "new_buy_allowed": decision.new_order_permission.value == "ALLOWED",
        "execution_amount": dstr(decision.recommended_new_amount),
        "execution_quantity": None if decision.approximate_shares is None else str(decision.approximate_shares),
        "diagnostic_category": (
            "DATA_INSUFFICIENCY_AS_HARD_GATE" if unknown else
            "RUNAWAY_DOWN" if decision.runaway_down else
            "ALLOW_BUY" if decision.new_order_permission.value == "ALLOWED" else
            "BLOCKED"
        ),
        "reason_codes": list(decision.reason_codes),
        "legacy_decision_field_count": len(dataclasses.fields(decision)),
        "legacy_has_formal_13": False,
        "legacy_has_order_lifecycle_state_machine": hasattr(engine, "OrderLifecycleState"),
    }
    return {"raw": raw, "normalized": normalized, "digest": stable_digest(raw)}


def build_new_analysis(case_id: str, common: dict[str, Any], classification: str, core, dep, gap, plan, unknown: bool):
    values = {name: "NOT_APPLICABLE" for name in CANONICAL_FIELD_NAMES}
    values.update({
        "latest_price": Decimal(common["canonical_valuation_price"]),
        "market_data_as_of": "2026-09-26T08:12:00+08:00",
        "asset_behavior_classification": "BROAD_ETF",
        "primary_framework": "V82",
        "secondary_framework": "NONE",
        "fundamental_state": core.fundamentals.context.value,
        "valuation_state": core.valuation.level.value,
        "left_buy_point_state": PredicateTruth.FALSE.value,
        "right_confirmation_state": core.technical.right_confirmation.value,
        "runaway_state": {"up": core.technical.runaway_up.value, "down": core.technical.runaway_down.value},
        "macro_state": "UNKNOWN" if unknown else "OK",
        "credit_liquidity_state": "UNKNOWN" if unknown else "OK",
        "material_news_policy_state": "OK",
        "position_cap": Decimal(common["project_target_position_amount"]),
        "project_target_position": gap.project_target_position_amount,
        "confirmed_position": gap.confirmed_amount,
        "actual_completion_rate": gap.actual_completion_rate,
        "normal_deployment_mode": dep.mode.value,
        "primary_special_classification": classification,
        "execution_action": plan.action,
        "canonical_deployment_target_rate": dep.target_rate,
        "execution_amount": plan.execution_amount,
        "execution_quantity": plan.execution_quantity,
        "execution_price": plan.execution_price,
        "projected_post_fill_completion_rate": plan.projected_post_fill_completion_rate,
        "order_submission_plan": plan.order_plan,
        "cancel_conditions": list(plan.reason_codes),
        "reevaluation_conditions": ["NEXT_CANONICAL_REFRESH"],
    })
    md = {}
    if unknown:
        md["macro_state"] = {"data_quality": DataQuality.UNKNOWN, "issue_codes": ["MISSING"]}
        md["credit_liquidity_state"] = {"data_quality": DataQuality.UNKNOWN, "issue_codes": ["MISSING"]}
    analysis = assemble_canonical_analysis(values=values, run_id=case_id, rule_version=RULE_VERSION, field_metadata=md)
    view = project_formal_execution_view(analysis)
    return analysis, view


def run_new_case(case: dict[str, Any], common: dict[str, Any]) -> dict[str, Any]:
    inp = runtime_input(case["case_id"], common)
    bound = validate_and_bind_funding(inp).bound_equity_budget
    unknown = case["safety"] == "REQUIRED_UNKNOWN"
    safety = [EvidenceFact(
        "macro_safety", "UNKNOWN" if unknown else "OK", RequirementLevel.SAFETY_REQUIRED,
        DataQuality.UNKNOWN if unknown else DataQuality.OK,
        Freshness.UNKNOWN if unknown else Freshness.FRESH,
        PitStatus.UNVERIFIABLE if unknown else PitStatus.VERIFIED,
        "E07-FROZEN-SAFETY",
    )]
    right, up_price, up_confirm, down_break, down_accel = new_predicates(case["technical"])
    core = evaluate_core_rule_state(
        valuation_metrics=[{"metric_name":"PE","data_quality":"OK","freshness":"FRESH","pit_status":"VERIFIED","current":20,"historical_median":20,"secondary_confirmation":"NORMAL","expensiveness_percentile":50}],
        valuation_waterfall=["PE"],
        fundamental_fields=[{"field_name":"earnings","requirement_level":"MODULE_REQUIRED","field_value_state":"KNOWN","data_quality":"OK","direction":"STABLE"}],
        safety_facts=safety,
        right_signals=right, up_price=up_price, up_confirm=up_confirm,
        down_break=down_break, down_accel=down_accel,
        hard_gate_predicates=[PredicateTruth.FALSE],
        theses=[{"state":"NORMAL","critical":False}],
        structural_confirmation=PredicateTruth.TRUE,
    )
    predicates = {
        "TRUE_RISK_REDUCTION": PredicateTruth.FALSE,
        "RUNAWAY_DOWN": core.technical.runaway_down,
        "TECHNICAL_REDUCTION": PredicateTruth.FALSE,
        "RUNAWAY_UP": core.technical.runaway_up,
        "RIGHT_ADD": core.technical.right_confirmation,
        "LEFT_BUY_POINT": PredicateTruth.FALSE,
    }
    classification = arbitrate_primary_special_classification(predicates)
    mode = select_deployment_mode(
        runaway_up=core.technical.runaway_up,
        right_add=core.technical.right_confirmation,
        left_buy_point=PredicateTruth.FALSE,
    )
    dep = resolve_deployment_stage(
        mode=mode,
        trend_stage=(case["new_stage"] if mode.value == "Trend Deployment" else None),
    )
    if dep.target_rate is None:
        raise AssertionError(f"E07_NEW_DEPLOYMENT_STAGE_UNKNOWN:{case['case_id']}")
    gap = calculate_position_gap(
        project_target_position_amount=Decimal(common["project_target_position_amount"]),
        target_rate=dep.target_rate,
        confirmed_position_qty=Decimal(common["confirmed_position_amount"]) / Decimal(common["canonical_valuation_price"]),
        canonical_valuation_price=Decimal(common["canonical_valuation_price"]),
        active_orders=(),
    )
    plan = build_buy_execution_plan(
        gap=gap, permission=core.permission, bound_equity_budget=bound,
        order_working_price=Decimal(common["normalized_order_price"]), minimum_lot=Decimal(common["minimum_lot"]),
        normalized_order_price=Decimal(common["normalized_order_price"]), execution_currency=common["currency"],
        order_intent_id=f"OID-{case['case_id']}",
    )
    analysis, view = build_new_analysis(case["case_id"], common, classification, core, dep, gap, plan, unknown)
    raw = {
        "bound_equity_budget": primitive(bound),
        "core": primitive(core),
        "classification": classification,
        "deployment": primitive(dep),
        "gap": primitive(gap),
        "plan": primitive(plan),
        "canonical_49": primitive(analysis.fields),
        "formal_13": primitive(view.fields),
    }
    normalized = {
        "account_binding": {"domain": bound.domain.value, "broker": bound.broker, "account": bound.account},
        "funding_source": {"amount": dstr(bound.amount), "currency": bound.currency, "cash_basis": bound.cash_basis.value, "source_contract": bound.source_contract, "source_reference_ids": list(bound.source_reference_ids)},
        "unknown_state": "UNKNOWN_FAIL_CLOSED" if unknown else "KNOWN_SAFE",
        "target_rate": dstr(dep.target_rate),
        "completion_rate": dstr(gap.actual_completion_rate),
        "gap_rate": dstr(dep.target_rate - (gap.actual_completion_rate or Decimal("0"))),
        "gap_amount": dstr(gap.final_deployment_gap_amount),
        "classification": classification,
        "new_buy_allowed": core.permission.new_buy_order_permission,
        "execution_amount": dstr(plan.execution_amount),
        "execution_quantity": dstr(plan.execution_quantity),
        "diagnostic_category": (
            "DATA_INSUFFICIENCY" if "DATA_INSUFFICIENCY" in core.permission.reason_codes else
            "RUNAWAY_DOWN" if "RUNAWAY_DOWN" in core.permission.reason_codes else
            "ALLOW_BUY" if core.permission.new_buy_order_permission else
            "BLOCKED"
        ),
        "permission_reason_codes": list(core.permission.reason_codes),
        "plan_reason_codes": list(plan.reason_codes),
        "canonical_49_count": len(analysis.fields),
        "formal_13_count": len(view.fields),
        "order_lifecycle_sample": {
            "NONE_TO_SUBMITTED": validate_order_transition(None, OrderLifecycleState.SUBMITTED),
            "SUBMITTED_TO_PARTIAL_FILL": validate_order_transition(OrderLifecycleState.SUBMITTED, OrderLifecycleState.PARTIAL_FILL),
            "PARTIAL_FILL_TO_FILLED": validate_order_transition(OrderLifecycleState.PARTIAL_FILL, OrderLifecycleState.FILLED),
        },
    }
    return {"raw": raw, "normalized": normalized, "digest": stable_digest(raw)}


def diff_record(invariant: str, case_id: str, legacy: Any, new: Any, *, category: str | None = None, resolved: bool = True, severity: str = "NONE", note: str = "", resolution_basis: str | None = None) -> dict[str, Any]:
    equal = primitive(legacy) == primitive(new)
    if equal:
        return {
            "invariant": invariant, "case_id": case_id, "comparison_status": "NO_DIFFERENCE",
            "legacy": primitive(legacy), "new": primitive(new), "classification": None,
            "severity": "NONE", "resolved": True, "resolution_basis": resolution_basis or SOURCE_REFS[invariant], "note": note,
        }
    if category not in ALLOWED_DIFF_CLASSIFICATIONS:
        raise AssertionError(f"DIFFERENCE_REQUIRES_W4_CLASSIFICATION:{invariant}:{case_id}")
    return {
        "invariant": invariant, "case_id": case_id, "comparison_status": "DIFFERENCE",
        "legacy": primitive(legacy), "new": primitive(new), "classification": category,
        "severity": severity, "resolved": bool(resolved), "resolution_basis": resolution_basis or SOURCE_REFS[invariant], "note": note,
    }


def main() -> int:
    QA.mkdir(exist_ok=True)
    evidence_contract = validate_e07_evidence_contract()
    baseline_sha = verify_authorized_baseline()
    engine, _legacy_models, _legacy_deployment = import_legacy()
    frozen = json.loads(FROZEN_INPUTS.read_text(encoding="utf-8"))
    common = frozen["common_facts"]
    legacy_outputs: dict[str, Any] = {}
    new_outputs: dict[str, Any] = {}
    comparisons: list[dict[str, Any]] = []

    for case in frozen["cases"]:
        cid = case["case_id"]
        l1 = run_legacy_case(engine, case, common)
        l2 = run_legacy_case(engine, case, common)
        n1 = run_new_case(case, common)
        n2 = run_new_case(case, common)
        if l1["digest"] != l2["digest"]:
            raise AssertionError(f"LEGACY_NONDETERMINISTIC:{cid}")
        if n1["digest"] != n2["digest"]:
            raise AssertionError(f"NEW_RUNTIME_NONDETERMINISTIC:{cid}")
        legacy_outputs[cid] = l1
        new_outputs[cid] = n1

        # Still-valid canonical meanings must match unless the current SOT explicitly changed them.
        comparisons.append(diff_record("classification/priority", cid, l1["normalized"]["classification"], n1["normalized"]["classification"]))
        for key in ("completion_rate",):
            comparisons.append(diff_record("Target/Gap/Completion", cid+":"+key, l1["normalized"][key], n1["normalized"][key]))
        for key in ("target_rate", "gap_rate", "gap_amount"):
            category = "EXPECTED_RULE_CHANGE" if cid == "E07-C06-RU-STAGE8-CURRENT-RULE" else None
            note = "Current W8 SOT requires an already-adjudicated trend stage; Legacy mechanically forces Runaway Up to 100%." if category else ""
            comparisons.append(diff_record("Target/Gap/Completion", cid+":"+key, l1["normalized"][key], n1["normalized"][key], category=category, severity="P1" if category else "NONE", resolved=True, note=note, resolution_basis=("v82_runtime_greenfield/src/livingwater_v82_runtime/deployment.py + v82_runtime_greenfield/tools/w8_deployment_execution_gate.py" if category else None)))
        comparisons.append(diff_record("diagnostics", cid+":buy_permission", l1["normalized"]["new_buy_allowed"], n1["normalized"]["new_buy_allowed"]))
        if cid == "E07-C04-SAFETY-UNKNOWN":
            comparisons.append(diff_record(
                "UNKNOWN", cid, l1["normalized"]["unknown_state"], n1["normalized"]["unknown_state"],
                category="LEGACY_DEFECT", severity="P1", resolved=True,
                note="Current W3 says required safety data insufficiency is fail-closed UNKNOWN and must not be fabricated as Hard Gate TRIGGERED.",
            ))
            comparisons.append(diff_record(
                "diagnostics", cid+":reason_semantics", l1["normalized"]["diagnostic_category"], n1["normalized"]["diagnostic_category"],
                category="LEGACY_DEFECT", severity="P1", resolved=True,
                note="Legacy conflates required-data insufficiency with a hard-gate flag; current diagnostics preserve DATA_INSUFFICIENCY.",
            ))
        else:
            comparisons.append(diff_record("UNKNOWN", cid, l1["normalized"]["unknown_state"], n1["normalized"]["unknown_state"]))
            comparisons.append(diff_record("diagnostics", cid+":reason_semantics", l1["normalized"]["diagnostic_category"], n1["normalized"]["diagnostic_category"]))
        comparisons.append(diff_record("determinism", cid, {"repeat_digest_equal": l1["digest"] == l2["digest"]}, {"repeat_digest_equal": n1["digest"] == n2["digest"]}))

    # Contract capabilities absent from Legacy are real execution differences, not invented Legacy values.
    sample_new = new_outputs["E07-C01-BASE-KNOWN"]["normalized"]
    comparisons.append(diff_record(
        "account_binding", "E07-CAPABILITY", {"status":"UNSUPPORTED_LEGACY_CONTRACT"}, sample_new["account_binding"],
        category="EXPECTED_RULE_CHANGE", severity="P1", resolved=True,
        note="C7 Funding/Account Isolation was added after the Legacy v1.10 runtime; current binding is same domain+broker+account only.",
    ))
    comparisons.append(diff_record(
        "funding_source", "E07-CAPABILITY", {"available_cash":"60","lineage":"UNSUPPORTED_LEGACY_CONTRACT"}, sample_new["funding_source"],
        category="EXPECTED_RULE_CHANGE", severity="P1", resolved=True,
        note="Legacy has an amount-only available_cash input; current runtime must preserve C7 owner/currency/AVAILABLE/source lineage.",
    ))
    comparisons.append(diff_record(
        "order_lifecycle", "E07-CAPABILITY", {"state_machine":"UNSUPPORTED_LEGACY_CONTRACT"}, sample_new["order_lifecycle_sample"],
        category="EXPECTED_RULE_CHANGE", severity="P1", resolved=True,
        note="Current W3 lifecycle separates Recommendation/Intent/Broker states/Confirmed Fill/Reconciliation.",
    ))
    comparisons.append(diff_record(
        "49_fields", "E07-CAPABILITY", {"legacy_decision_fields": legacy_outputs["E07-C01-BASE-KNOWN"]["normalized"]["legacy_decision_field_count"], "canonical_49": False},
        {"canonical_49": sample_new["canonical_49_count"]},
        category="EXPECTED_RULE_CHANGE", severity="P1", resolved=True,
        note="Legacy V82Decision predates the exact 49-field canonical analysis contract.",
    ))
    comparisons.append(diff_record(
        "13_fields", "E07-CAPABILITY", {"formal_13": False}, {"formal_13": sample_new["formal_13_count"]},
        category="EXPECTED_RULE_CHANGE", severity="P1", resolved=True,
        note="Legacy runtime predates the exact 49→13 unique formal execution projection.",
    ))

    required_invariants = ["account_binding","funding_source","UNKNOWN","Target/Gap/Completion","classification/priority","order_lifecycle","49_fields","13_fields","diagnostics","determinism"]
    covered = {i: sum(1 for r in comparisons if r["invariant"] == i) for i in required_invariants}
    unresolved_p0 = [r for r in comparisons if not r["resolved"] and r["severity"] == "P0"]
    unresolved_p1 = [r for r in comparisons if not r["resolved"] and r["severity"] == "P1"]
    new_defects = [r for r in comparisons if r.get("classification") == "NEW_RUNTIME_DEFECT"]
    unknown_review = [r for r in comparisons if r.get("classification") == "UNKNOWN_NEEDS_REVIEW"]
    data_contract_unresolved = [r for r in comparisons if r.get("classification") == "DATA/CONTRACT_MISMATCH" and not r["resolved"]]
    status = "PASS" if all(covered.values()) and not unresolved_p0 and not unresolved_p1 and not new_defects and not unknown_review and not data_contract_unresolved else "FAIL"

    out = {
        "gate": "W12 E07 Authorized Legacy Shadow/Dual-run",
        "status": status,
        "authorization": "ABC_V82_W12_E07_Legacy_Shadow_Authorization_2026-09-26_0812",
        "baseline_sha256": baseline_sha,
        "legacy_health_tests": "34/34 PASS",
        "frozen_semantic_inputs_sha256": sha256(FROZEN_INPUTS),
        "adapter_mapping_sha256": sha256(ADAPTER_MAP),
        "frozen_schema_version": evidence_contract["frozen_schema_version"],
        "rule_context": evidence_contract["rule_context"],
        "adapter_rows_verified": evidence_contract["adapter_rows"],
        "adapter_invariants_verified": evidence_contract["adapter_invariants"],
        "adapter_resolution_basis_verified": evidence_contract["adapter_resolution_basis_verified"],
        "adapter_business_rules_added": bool(evidence_contract["adapter_business_rule_rows"]),
        "same_frozen_semantic_input": True,
        "new_runtime_order_action_published": False,
        "required_invariants": required_invariants,
        "coverage": covered,
        "comparison_count": len(comparisons),
        "differences": [r for r in comparisons if r["comparison_status"] == "DIFFERENCE"],
        "unresolved_p0": unresolved_p0,
        "unresolved_p1": unresolved_p1,
        "new_runtime_defects": new_defects,
        "unknown_needs_review": unknown_review,
        "all_invariants_covered": all(covered.values()),
        "dual_run_readiness": status == "PASS",
        "comparisons": comparisons,
    }
    (QA / "A78_W12_E07_LEGACY_OUTPUTS.json").write_text(json.dumps(legacy_outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (QA / "A78_W12_E07_NEW_OUTPUTS.json").write_text(json.dumps(new_outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (QA / "A78_W12_E07_LEGACY_SHADOW_GATE.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (QA / "A78_W12_E07_DIFFERENCE_CLASSIFICATION.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["invariant","case_id","comparison_status","classification","severity","resolved","resolution_basis","note"])
        for r in comparisons:
            w.writerow([r["invariant"],r["case_id"],r["comparison_status"],r.get("classification") or "",r["severity"],str(r["resolved"]).upper(),r["resolution_basis"],r["note"]])
    (QA / "A78_W12_E07_LEGACY_SHADOW_GATE.txt").write_text(
        f"{status} E07 Legacy Shadow/Dual-run\n"
        f"LEGACY_HEALTH=34/34 PASS\n"
        f"CASES={len(frozen['cases'])}\nCOMPARISONS={len(comparisons)}\n"
        f"INVARIANTS_COVERED={sum(1 for v in covered.values() if v)}/{len(required_invariants)}\n"
        f"UNRESOLVED_P0={len(unresolved_p0)}\nUNRESOLVED_P1={len(unresolved_p1)}\n"
        f"ADAPTER_ROWS_VERIFIED={out['adapter_rows_verified']}\n"
        f"ADAPTER_BUSINESS_RULES_ADDED={str(out['adapter_business_rules_added']).upper()}\n"
        f"ADAPTER_RESOLUTION_BASIS_VERIFIED={str(out['adapter_resolution_basis_verified']).upper()}\n"
        f"FROZEN_RULE_CONTEXT={json.dumps(out['rule_context'], ensure_ascii=False, sort_keys=True)}\n"
        f"FROZEN_INPUT_SHA256={out['frozen_semantic_inputs_sha256']}\nADAPTER_SHA256={out['adapter_mapping_sha256']}\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "gate": out["gate"], "status": status, "cases": len(frozen["cases"]),
        "comparisons": len(comparisons), "invariants": f"{sum(1 for v in covered.values() if v)}/{len(required_invariants)}",
        "unresolved_p0": len(unresolved_p0), "unresolved_p1": len(unresolved_p1),
    }, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
