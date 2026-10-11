#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from livingwater_v82_runtime.validation import (
    C7_CONTRACT_NAME,
    C7_CONTRACT_VERSION,
    INPUT_CONTRACT_NAME,
    INPUT_CONTRACT_VERSION,
    validate_and_bind_funding,
)
from livingwater_v82_runtime.enums import (
    DataQuality,
    Freshness,
    HardGateState,
    OrderLifecycleState,
    PitStatus,
    PredicateTruth,
    RequirementLevel,
)
from livingwater_v82_runtime.core_rules import EvidenceFact, evaluate_core_rule_state
from livingwater_v82_runtime.deployment import (
    ActiveOrderExposure,
    build_buy_execution_plan,
    calculate_position_gap,
    resolve_deployment_stage,
    select_deployment_mode,
    validate_order_transition,
)
from livingwater_v82_runtime.canonical_output import (
    CANONICAL_FIELD_NAMES,
    FORMAL_OUTPUT_NAMES,
    assemble_canonical_analysis,
    build_runtime_output,
    project_formal_execution_view,
    validate_formal_view_against_analysis,
    validate_run_lineage,
)
from livingwater_v82_runtime.persistence import JsonlSnapshotRepository, content_digest

RULE_VERSION = "V82-v1.21.0"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.V82.RuntimeOutput"
OUTPUT_CONTRACT_VERSION = "V82-OUTPUT-v1.0.1-W2-RECHECK2"
STREAM = "US_BROKER|ib|C"
RECHECK_AS_OF = "2026/09/26 09:05（台灣時間）"

TESTS: list[tuple[str, bool, str]] = []
CUTOVER_EVIDENCE: dict[str, object] = {
    "activation_performed": False,
    "candidate_state": "PENDING_AUTHORIZED_E07_SHADOW_EXECUTION",
    "legacy_executable_authorized_evidence_present": True,
    "frozen_legacy_output_fixture_in_authorized_checkpoint": False,
    "shadow_method": "AUTHORIZED_LEGACY_EXECUTABLE_DUAL_RUN",
    "unresolved_p0": [],
    "unresolved_p1": [],
}


def check(test_id: str, fn) -> None:
    try:
        detail = fn()
        TESTS.append((test_id, True, "" if detail is None else str(detail)))
    except Exception as exc:  # noqa: BLE001 - QA harness captures every failure.
        TESTS.append((test_id, False, f"{type(exc).__name__}: {exc}"))


def eq(actual, expected, msg: str = "") -> None:
    assert actual == expected, msg or f"{actual!r} != {expected!r}"


def truth(value, msg: str = "") -> None:
    assert value, msg or f"expected truthy value, got {value!r}"


def raises(fn, contains: str | None = None):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if contains:
            assert contains in str(exc), str(exc)
        return exc
    raise AssertionError("expected exception")


def base_runtime_input(*, run_id: str = "W12-R1") -> dict:
    contexts = []
    identities = [
        ("TW_LOCAL_BROKER", "tw", "A"),
        ("TW_SUB_BROKERAGE", "sub", "B"),
        ("US_BROKER", "ib", "C"),
    ]
    for domain, broker, account in identities:
        contexts.append(
            {
                "domain": domain,
                "broker": broker,
                "account": account,
                "bucket_new_investment_amount": 100,
                "brokerage_cash_state": {"total": 150, "available": 100, "unsettled": 20, "reserved": 10},
                "executable_budget": {
                    "equity": {
                        "amount": 60,
                        "cash_basis": "AVAILABLE",
                        "source_domain": domain,
                        "source_broker": broker,
                        "source_account": account,
                    },
                    "bond": {
                        "amount": 40,
                        "cash_basis": "AVAILABLE",
                        "source_domain": domain,
                        "source_broker": broker,
                        "source_account": account,
                    },
                },
                "source_reference_ids": [f"{domain}-ref"],
            }
        )
    return {
        "contract_name": INPUT_CONTRACT_NAME,
        "contract_version": INPUT_CONTRACT_VERSION,
        "run_id": run_id,
        "client_project_version": "P1",
        "asset": {"asset_id": "QQQ", "asset_type": "BROAD_ETF", "asset_grade": "A", "portfolio_role": "CORE"},
        "execution_account": {"domain": "US_BROKER", "broker": "ib", "account": "C"},
        "client_target": {"project_target_position": 1000, "authorization_reference": "AUTH1"},
        "upstream_v70_snapshot": {
            "run_id": run_id,
            "upstream_v70_snapshot_id": f"V70-{run_id}",
            "v70_stock_tactical_budget_amount": 100,
            "v70_stock_tactical_budget_currency": "USD",
            "v70_stock_tactical_budget_status": "KNOWN",
            "v70_stock_tactical_budget_data_as_of": "2026-09-26",
            "v70_original_dry_powder_amount": 100,
            "v70_original_dry_powder_currency": "USD",
            "v70_budget_source_reference": "v70",
            "v70_budget_data_quality": "OK",
            "v70_budget_issue_codes": [],
        },
        "confirmed_position_snapshot": {},
        "source_lineage": [run_id, "QQQ", "C7"],
        "market_data_bundle": {},
        "event_context": {},
        "c7_funding_context": {
            "contract_name": C7_CONTRACT_NAME,
            "contract_version": C7_CONTRACT_VERSION,
            "run_id": run_id,
            "base_currency": "USD",
            "bank_cash_scope": "OUT_OF_SCOPE",
            "total_new_investment_amount": 300,
            "contexts": contexts,
            "source_reference_ids": ["c7"],
        },
    }


def known_core_state(*, insufficient: bool = False):
    safety = [
        EvidenceFact(
            "macro_safety",
            "OK",
            RequirementLevel.SAFETY_REQUIRED,
            DataQuality.UNKNOWN if insufficient else DataQuality.OK,
            Freshness.UNKNOWN if insufficient else Freshness.FRESH,
            PitStatus.UNVERIFIABLE if insufficient else PitStatus.VERIFIED,
            "macro-source",
        )
    ]
    return evaluate_core_rule_state(
        valuation_metrics=[{
            "metric_name": "PE", "data_quality": "OK", "freshness": "FRESH", "pit_status": "VERIFIED",
            "current": 20, "historical_median": 20, "secondary_confirmation": "NORMAL", "expensiveness_percentile": 50,
        }],
        valuation_waterfall=["PE"],
        fundamental_fields=[{
            "field_name": "earnings", "requirement_level": "MODULE_REQUIRED", "field_value_state": "KNOWN",
            "data_quality": "OK", "direction": "STABLE",
        }],
        safety_facts=safety,
        right_signals=[PredicateTruth.FALSE, PredicateTruth.FALSE, PredicateTruth.FALSE],
        up_price=[PredicateTruth.FALSE],
        up_confirm=[PredicateTruth.FALSE, PredicateTruth.FALSE, PredicateTruth.FALSE],
        down_break=[PredicateTruth.FALSE],
        down_accel=[PredicateTruth.FALSE, PredicateTruth.FALSE],
        hard_gate_predicates=[PredicateTruth.FALSE],
        theses=[{"state": "NORMAL", "critical": False}],
        structural_confirmation=PredicateTruth.TRUE,
    )


def execute_case(*, run_id: str, confirmed_qty: Decimal = Decimal("0"), project_target: Decimal = Decimal("1000"),
                 insufficient: bool = False, active_orders=(), order_intent_id: str | None = None):
    inp = base_runtime_input(run_id=run_id)
    inp["client_target"]["project_target_position"] = float(project_target)
    bound = validate_and_bind_funding(inp)
    validate_run_lineage(run_id=run_id, upstream_v70_run_id=run_id, c7_funding_run_id=run_id)
    core = known_core_state(insufficient=insufficient)
    mode = select_deployment_mode(
        runaway_up=core.technical.runaway_up,
        right_add=core.technical.right_confirmation,
        left_buy_point=PredicateTruth.FALSE,
    )
    deployment = resolve_deployment_stage(mode=mode)
    truth(deployment.target_rate is not None, "base deployment stage must remain known")
    gap = calculate_position_gap(
        project_target_position_amount=project_target,
        target_rate=deployment.target_rate,
        confirmed_position_qty=confirmed_qty,
        canonical_valuation_price=Decimal("10"),
        active_orders=active_orders,
    )
    plan = build_buy_execution_plan(
        gap=gap,
        permission=core.permission,
        bound_equity_budget=bound.bound_equity_budget,
        order_working_price=Decimal("10"),
        minimum_lot=Decimal("1"),
        normalized_order_price=Decimal("10"),
        execution_currency="USD",
        order_intent_id=order_intent_id or f"OID-{run_id}",
    )
    return inp, bound, core, deployment, gap, plan


def build_analysis(*, run_id: str, core, deployment, gap, plan, unknown_credit: bool = False):
    values = {name: "KNOWN" for name in CANONICAL_FIELD_NAMES}
    values.update({
        "latest_price": Decimal("10"),
        "market_data_as_of": "2026-09-26T06:43:00+08:00",
        "asset_behavior_classification": "BROAD_ETF",
        "primary_framework": "V82",
        "secondary_framework": "NONE",
        "fundamental_state": core.fundamentals.context.value,
        "valuation_state": core.valuation.level.value,
        "left_buy_point_state": PredicateTruth.FALSE.value,
        "right_confirmation_state": core.technical.right_confirmation.value,
        "runaway_state": {"up": core.technical.runaway_up.value, "down": core.technical.runaway_down.value},
        "macro_state": "OK",
        "credit_liquidity_state": "UNKNOWN" if unknown_credit else "OK",
        "material_news_policy_state": "OK",
        "position_cap": Decimal("1000"),
        "project_target_position": gap.project_target_position_amount,
        "confirmed_position": gap.confirmed_amount,
        "actual_completion_rate": gap.actual_completion_rate,
        "normal_deployment_mode": deployment.mode.value,
        "primary_special_classification": "UNKNOWN" if unknown_credit else "無特殊分類",
        "execution_action": plan.action,
        "canonical_deployment_target_rate": deployment.target_rate,
        "execution_amount": plan.execution_amount,
        "execution_quantity": plan.execution_quantity,
        "execution_price": plan.execution_price,
        "projected_post_fill_completion_rate": plan.projected_post_fill_completion_rate,
        "order_submission_plan": plan.order_plan,
        "cancel_conditions": list(plan.reason_codes),
        "reevaluation_conditions": ["NEXT_CANONICAL_REFRESH"],
    })
    md = {}
    if unknown_credit:
        md["credit_liquidity_state"] = {"data_quality": DataQuality.UNKNOWN, "issue_codes": ["MISSING"]}
        md["primary_special_classification"] = {"data_quality": DataQuality.UNKNOWN, "issue_codes": ["MISSING"]}
    analysis = assemble_canonical_analysis(values=values, run_id=run_id, rule_version=RULE_VERSION, field_metadata=md)
    view = project_formal_execution_view(analysis)
    validate_formal_view_against_analysis(analysis, view.fields)
    return analysis, view


def output_for(*, run_id: str, analysis, snapshot_id: str):
    return build_runtime_output(
        analysis=analysis,
        run_id=run_id,
        v82_snapshot_id=snapshot_id,
        upstream_v70_snapshot_id=f"V70-{run_id}",
        asset_id="QQQ",
        rule_version=RULE_VERSION,
        contract_name=OUTPUT_CONTRACT_NAME,
        contract_version=OUTPUT_CONTRACT_VERSION,
        data_as_of={"market": "2026-09-26"},
        evaluated_at="2026-09-26T06:43:00+08:00",
        source_lineage=(run_id, "QQQ", "C7"),
        output_status="OK",
    )


def e01_happy_path():
    run_id = "W12-E01"
    _, bound, core, dep, gap, plan = execute_case(run_id=run_id)
    eq((bound.bound_equity_budget.domain.value, bound.bound_equity_budget.broker, bound.bound_equity_budget.account), ("US_BROKER", "ib", "C"))
    eq(plan.action, "BUY")
    analysis, view = build_analysis(run_id=run_id, core=core, deployment=dep, gap=gap, plan=plan)
    eq(len(analysis.fields), 49)
    eq(tuple(view.fields.keys()), FORMAL_OUTPUT_NAMES)
    out = output_for(run_id=run_id, analysis=analysis, snapshot_id="W12-E01-S1")
    eq(out.run_id, run_id)
    eq(out.source_lineage, (run_id, "QQQ", "C7"))
    digest1 = content_digest(out)
    digest2 = content_digest(output_for(run_id=run_id, analysis=analysis, snapshot_id="W12-E01-S1"))
    eq(digest1, digest2)
    return f"49+13 deterministic digest={digest1[:16]}"


def e02_known_no_action():
    run_id = "W12-E02"
    _, _, core, dep, gap, plan = execute_case(run_id=run_id, confirmed_qty=Decimal("10"))
    eq(gap.final_deployment_gap_amount, Decimal("0"))
    eq(plan.action, "NO_NEW_BUY")
    eq(plan.order_plan.should_place_order, False)
    truth("UNKNOWN" not in plan.reason_codes)
    _, view = build_analysis(run_id=run_id, core=core, deployment=dep, gap=gap, plan=plan)
    eq(view.fields["今日動作"], "NO_NEW_BUY")
    return "explicit known no-action"


def e03_unknown_fail_closed():
    run_id = "W12-E03"
    _, _, core, dep, gap, plan = execute_case(run_id=run_id, insufficient=True)
    eq(core.permission.hard_gate, HardGateState.UNKNOWN)
    eq(core.permission.new_buy_order_permission, False)
    truth("DATA_INSUFFICIENCY" in core.permission.reason_codes)
    eq(plan.action, "NO_NEW_BUY")
    analysis, view = build_analysis(run_id=run_id, core=core, deployment=dep, gap=gap, plan=plan, unknown_credit=True)
    eq(analysis.fields["credit_liquidity_state"].value, "UNKNOWN")
    eq(analysis.fields["credit_liquidity_state"].data_quality, DataQuality.UNKNOWN)
    eq(view.fields["今日特殊分類"], "UNKNOWN")
    return "UNKNOWN preserved; new buy fail-closed"


def e04_order_lifecycle_reconciliation():
    truth(validate_order_transition(None, OrderLifecycleState.SUBMITTED))
    truth(validate_order_transition(OrderLifecycleState.SUBMITTED, OrderLifecycleState.PARTIAL_FILL))
    truth(validate_order_transition(OrderLifecycleState.PARTIAL_FILL, OrderLifecycleState.FILLED))
    partial = calculate_position_gap(
        project_target_position_amount=Decimal("500"), target_rate=Decimal("0.1"), confirmed_position_qty=Decimal("1"),
        canonical_valuation_price=Decimal("10"),
        active_orders=[ActiveOrderExposure("E04", "BUY", OrderLifecycleState.PARTIAL_FILL, Decimal("3"), Decimal("1"))],
    )
    filled = calculate_position_gap(
        project_target_position_amount=Decimal("500"), target_rate=Decimal("0.1"), confirmed_position_qty=Decimal("3"),
        canonical_valuation_price=Decimal("10"),
        active_orders=[ActiveOrderExposure("E04", "BUY", OrderLifecycleState.FILLED, Decimal("3"), Decimal("3"))],
    )
    eq(partial.projected_position_amount, Decimal("30"))
    eq(filled.projected_position_amount, Decimal("30"))
    eq(partial.final_deployment_gap_amount, filled.final_deployment_gap_amount)
    return "partial/fill broker facts reconcile without double count"


def e05_restart_recovery():
    with tempfile.TemporaryDirectory() as td:
        repo = JsonlSnapshotRepository(td)
        payload = {"confirmed_position": "20", "run_id": "W12-E05"}
        repo.append(snapshot_id="E05-S1", kind="V82_RUNTIME_OUTPUT", run_id="W12-E05", payload=payload,
                    rule_version=RULE_VERSION, contract_version=OUTPUT_CONTRACT_VERSION,
                    source_lineage=("W12-E05", "QQQ"), created_at="2026-09-26T06:43:00+08:00",
                    idempotency_key="E05-IDEM", domain="US_BROKER", broker="ib", account="C")
        repo.publish("E05-S1")
        repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E05-S1", expected_snapshot_id=None)
        restarted = JsonlSnapshotRepository(td)
        latest = restarted.latest(STREAM)
        truth(latest is not None)
        eq(latest.snapshot_id, "E05-S1")
        eq(latest.payload, payload)
        eq(latest.digest, content_digest(payload))
    return "restart recovered published pointer/history"


def e06_cas_race_retry():
    with tempfile.TemporaryDirectory() as td:
        repo = JsonlSnapshotRepository(td)
        for sid, value in (("E06-A", 1), ("E06-B", 2)):
            repo.append(snapshot_id=sid, kind="V82_RUNTIME_OUTPUT", run_id="W12-E06", payload={"v": value},
                        rule_version=RULE_VERSION, contract_version=OUTPUT_CONTRACT_VERSION,
                        source_lineage=("W12-E06", sid), created_at="2026-09-26T06:43:00+08:00",
                        idempotency_key=f"IDEM-{sid}", domain="US_BROKER", broker="ib", account="C")
            repo.publish(sid)
        repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E06-A", expected_snapshot_id=None)
        raises(lambda: repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E06-B", expected_snapshot_id=None), "CAS_CONFLICT")
        eq(repo.latest(STREAM).snapshot_id, "E06-A")
        repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E06-B", expected_snapshot_id="E06-A")
        eq(repo.latest(STREAM).snapshot_id, "E06-B")
    return "stale CAS rejected; safe retry preserved update"


def _classify_shadow(*, case_id: str, legacy_semantic, new_semantic, frozen_contract: dict) -> dict:
    if frozen_contract.get("data_or_contract_mismatch"):
        category = "DATA/CONTRACT_MISMATCH"
        severity = frozen_contract.get("severity", "P1")
        resolved = bool(frozen_contract.get("resolved", False))
    elif legacy_semantic == new_semantic:
        category = "NO_DIFFERENCE"
        severity = "NONE"
        resolved = True
    elif frozen_contract.get("legacy_violates_current_contract") and frozen_contract.get("new_matches_current_contract"):
        category = "LEGACY_DEFECT"
        severity = frozen_contract.get("severity", "P1")
        resolved = True
    elif frozen_contract.get("expected_rule_change") and frozen_contract.get("new_matches_current_contract"):
        category = "EXPECTED_RULE_CHANGE"
        severity = frozen_contract.get("severity", "P1")
        resolved = True
    elif frozen_contract.get("new_matches_current_contract") is False:
        category = "NEW_RUNTIME_DEFECT"
        severity = frozen_contract.get("severity", "P1")
        resolved = False
    else:
        category = "UNKNOWN_NEEDS_REVIEW"
        severity = frozen_contract.get("severity", "P1")
        resolved = False
    return {
        "case_id": case_id,
        "legacy_semantic": legacy_semantic,
        "new_semantic": new_semantic,
        "classification": category,
        "severity": severity,
        "resolved": resolved,
    }


def e07_shadow_difference_classification():
    """Execute the ABC-authorized Legacy baseline and current Runtime on the same frozen semantic facts."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    helper = ROOT / "tools" / "w12_e07_legacy_shadow_gate.py"
    run = subprocess.run([sys.executable, str(helper)], cwd=str(ROOT), env=env, capture_output=True, text=True)
    if run.returncode != 0:
        raise AssertionError("AUTHORIZED_LEGACY_SHADOW_GATE_FAIL:" + ((run.stdout or "") + (run.stderr or ""))[-1200:])
    artifact = ROOT.parent / "QA_Results" / "A78_W12_E07_LEGACY_SHADOW_GATE.json"
    truth(artifact.is_file(), "E07 authorized shadow artifact missing")
    obj = json.loads(artifact.read_text(encoding="utf-8"))
    eq(obj.get("status"), "PASS")
    truth(obj.get("same_frozen_semantic_input") is True)
    truth(obj.get("adapter_business_rules_added") is False)
    truth(obj.get("all_invariants_covered") is True)
    truth(obj.get("dual_run_readiness") is True)
    eq(obj.get("unresolved_p0"), [])
    eq(obj.get("unresolved_p1"), [])
    required = [
        "account_binding", "funding_source", "UNKNOWN", "Target/Gap/Completion",
        "classification/priority", "order_lifecycle", "49_fields", "13_fields", "diagnostics", "determinism",
    ]
    eq(obj.get("required_invariants"), required)
    coverage = obj.get("coverage", {})
    truth(all(int(coverage.get(k, 0)) > 0 for k in required), f"invariant coverage incomplete: {coverage}")
    CUTOVER_EVIDENCE.update({
        "authorization": obj.get("authorization"),
        "legacy_baseline_sha256": obj.get("baseline_sha256"),
        "legacy_health_tests": obj.get("legacy_health_tests"),
        "frozen_semantic_inputs_sha256": obj.get("frozen_semantic_inputs_sha256"),
        "adapter_mapping_sha256": obj.get("adapter_mapping_sha256"),
        "adapter_business_rules_added": obj.get("adapter_business_rules_added"),
        "same_frozen_semantic_input": obj.get("same_frozen_semantic_input"),
        "shadow_cases": obj.get("differences", []),
        "shadow_comparison_count": obj.get("comparison_count"),
        "shadow_required_invariants": required,
        "shadow_coverage": f"{sum(1 for k in required if int(coverage.get(k, 0)) > 0)}/{len(required)}",
        "unresolved_p0": [],
        "unresolved_p1": [],
    })
    return f"authorized legacy/new dual-run PASS; comparisons={obj.get('comparison_count')}; invariants=10/10"


def _frozen_w9_compat_read(directory: str, stream_key: str) -> dict:
    """Independent compatibility reader for the frozen W9 JSONL persistence contract.

    This deliberately does not instantiate JsonlSnapshotRepository, so E08 is not
    the current implementation reading its own files. It validates the stable W9
    persisted shape/events/pointer semantics needed for release rollback/read-only
    recovery compatibility.
    """
    root = Path(directory)
    history = root / "snapshots.jsonl"
    events = root / "publication_events.jsonl"
    pointers = root / "latest_pointers.json"
    truth(history.is_file() and events.is_file() and pointers.is_file(), "W9 persistence files missing")
    required = {
        "snapshot_id", "kind", "run_id", "payload", "digest", "rule_version", "contract_version",
        "source_lineage", "created_at", "status", "supersedes_id", "domain", "broker", "account",
    }
    records: dict[str, dict] = {}
    for line in history.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        truth(required <= set(row), f"W9 persisted snapshot shape missing={sorted(required-set(row))}")
        eq(content_digest(row["payload"]), row["digest"], "W9 persisted digest mismatch")
        eq(row["contract_version"], OUTPUT_CONTRACT_VERSION, "W9-compatible output contract drift")
        eq(row["rule_version"], RULE_VERSION, "W9-compatible rule version drift")
        records[row["snapshot_id"]] = dict(row)
    published = set()
    for line in events.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        eq(ev.get("event"), "PUBLISH")
        truth(ev.get("snapshot_id") in records, "publish references missing snapshot")
        published.add(ev["snapshot_id"])
    ptrs = json.loads(pointers.read_text(encoding="utf-8"))
    truth(stream_key in ptrs, "W9 latest pointer missing")
    ptr = ptrs[stream_key]
    sid = ptr["snapshot_id"]
    truth(sid in records and sid in published, "W9 pointer must reference published snapshot")
    rec = records[sid]
    eq(f"{rec['domain']}|{rec['broker']}|{rec['account']}", stream_key, "W9 pointer account mismatch")
    return {"latest": rec, "records": records, "revision": int(ptr["revision"])}


def e08_rollback_rehearsal():
    with tempfile.TemporaryDirectory() as td:
        repo = JsonlSnapshotRepository(td)
        repo.append(snapshot_id="E08-PRE", kind="V82_RUNTIME_OUTPUT", run_id="W12-E08-PRE",
                    payload={"runtime_release": "PRE_CUTOVER", "broker_confirmed_position": "2"},
                    rule_version=RULE_VERSION, contract_version=OUTPUT_CONTRACT_VERSION,
                    source_lineage=("BROKER", "PRE"), created_at="2026-09-26T06:43:00+08:00",
                    idempotency_key="E08-PRE", domain="US_BROKER", broker="ib", account="C")
        repo.publish("E08-PRE")
        repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E08-PRE", expected_snapshot_id=None)
        repo.append(snapshot_id="E08-POST", kind="V82_RUNTIME_OUTPUT", run_id="W12-E08-POST",
                    payload={"runtime_release": "CUTOVER_CANDIDATE", "broker_confirmed_position": "3"},
                    rule_version=RULE_VERSION, contract_version=OUTPUT_CONTRACT_VERSION,
                    source_lineage=("BROKER", "POST_FILL"), created_at="2026-09-26T06:44:00+08:00",
                    idempotency_key="E08-POST", domain="US_BROKER", broker="ib", account="C",
                    supersedes_id="E08-PRE")
        repo.publish("E08-POST")
        repo.compare_and_swap_latest(stream_key=STREAM, new_snapshot_id="E08-POST", expected_snapshot_id="E08-PRE")

        frozen = _frozen_w9_compat_read(td, STREAM)
        eq(frozen["latest"]["snapshot_id"], "E08-POST")
        eq(frozen["latest"]["payload"]["broker_confirmed_position"], "3")
        eq(frozen["records"]["E08-PRE"]["payload"]["broker_confirmed_position"], "2")
        CUTOVER_EVIDENCE["rollback"] = {
            "runtime_release_rollback_rehearsed": True,
            "compatibility_reader": "FROZEN_W9_JSONL_CONTRACT_READER",
            "frozen_w9_reader_passed": True,
            "durable_latest_preserved": "E08-POST",
            "broker_confirmed_position_preserved": "3",
            "history_pre_snapshot_preserved": True,
        }
    return "frozen W9 compatibility reader consumed post-cutover canonical persistence; broker facts/history preserved"


check("E01", e01_happy_path)
check("E02", e02_known_no_action)
check("E03", e03_unknown_fail_closed)
check("E04", e04_order_lifecycle_reconciliation)
check("E05", e05_restart_recovery)
check("E06", e06_cas_race_retry)
check("E07", e07_shadow_difference_classification)
check("E08", e08_rollback_rehearsal)

passed = sum(ok for _, ok, _ in TESTS)
failed_ids = [i for i, ok, _ in TESTS if not ok]
if passed == len(TESTS):
    status = "PASS"
else:
    status = "FAIL"

if status != "PASS":
    for test_id, ok, detail in TESTS:
        if not ok:
            sev = "P0" if test_id in {"E04", "E08"} else "P1"
            CUTOVER_EVIDENCE[f"unresolved_{sev.lower()}"] = list(CUTOVER_EVIDENCE[f"unresolved_{sev.lower()}"]) + [
                {"test_id": test_id, "detail": detail}
            ]
else:
    CUTOVER_EVIDENCE["candidate_state"] = "READY_FOR_ABC_V82_RUNTIME_READY_GATE"

result = {
    "gate": "W12 Full E2E + Cutover + Runtime Readiness",
    "status": status,
    "passed": passed,
    "total": len(TESTS),
    "tests": [{"id": i, "pass": ok, "detail": detail} for i, ok, detail in TESTS],
    "cutover_evidence": CUTOVER_EVIDENCE,
    "formal_e2e_matrix_ids": [f"E0{i}" for i in range(1, 9)],
}
qa = ROOT.parent / "QA_Results"
qa.mkdir(exist_ok=True)
(qa / "A78_W12_FULL_E2E_CUTOVER_RUNTIME_READINESS_GATE.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
)
(qa / "A78_W12_FULL_E2E_CUTOVER_RUNTIME_READINESS_GATE.txt").write_text(
    f"{status} {passed}/{len(TESTS)}\n"
    + "\n".join(f"{i}: {'PASS' if ok else 'FAIL'} {detail}" for i, ok, detail in TESTS)
    + f"\nUNRESOLVED_P0={len(CUTOVER_EVIDENCE['unresolved_p0'])}"
    + f"\nUNRESOLVED_P1={len(CUTOVER_EVIDENCE['unresolved_p1'])}\n",
    encoding="utf-8",
)
issue_ledger = {
    "as_of": RECHECK_AS_OF,
    "state": CUTOVER_EVIDENCE["candidate_state"],
    "activation_performed": False,
    "unresolved_p0": CUTOVER_EVIDENCE["unresolved_p0"],
    "unresolved_p1": CUTOVER_EVIDENCE["unresolved_p1"],
    "c_work8_released": False,
}
(qa / "A78_W12_CUTOVER_ISSUE_LEDGER.json").write_text(json.dumps(issue_ledger, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "passed": passed, "total": len(TESTS), "status": status,
    "unresolved_p0": len(CUTOVER_EVIDENCE["unresolved_p0"]),
    "unresolved_p1": len(CUTOVER_EVIDENCE["unresolved_p1"]),
}, ensure_ascii=False))
if status == "FAIL":
    raise SystemExit(1)
