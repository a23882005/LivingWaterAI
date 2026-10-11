"""C8C9 Work15 - SGOV Semantic E2E verification harness.

QA-only harness. It composes the already CLOSED Work3/4/5/6/7 seams plus the
Frozen V75 Runtime Ready package to prove SGOV role/source/owner/amount/routing
semantics end-to-end. It does not create a new Funding Engine, compute a final
SGOV dry-powder aggregate, or create a Family physical SGOV sub-ledger.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import zipfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def _load(name: str, rel: str):
    p = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {rel}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


W3 = _load("w3_w15", "WORK3_OUTPUT/C8C9_Work3_Context_Handoff_Adapter.py")
W4 = _load("w4_w15", "WORK4_OUTPUT/C8C9_Work4_V82_Integration_Adapter.py")
W5 = _load("w5_w15", "WORK5_OUTPUT/C8C9_Work5_V75_Integration_Adapter.py")
W6 = _load("w6_w15", "WORK6_OUTPUT/C8C9_Work6_Funding_Account_Isolation_Guard.py")
W7 = _load("w7_w15", "WORK7_OUTPUT/C8C9_Work7_SGOV_Runtime_Role_Integration.py")

HARNESS_ID = "C8C9-W15-SGOV-E2E-v1.0.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _ctx(domain: str, broker: str, account: str, bucket: float, cash: dict[str, float], equity: float, bond: float, ref: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "broker": broker,
        "account": account,
        "bucket_new_investment_amount": bucket,
        "brokerage_cash_state": cash,
        "executable_budget": {
            "equity": {"amount": equity, "cash_basis": "AVAILABLE", "source_domain": domain, "source_broker": broker, "source_account": account},
            "bond": {"amount": bond, "cash_basis": "AVAILABLE", "source_domain": domain, "source_broker": broker, "source_account": account},
        },
        "source_reference_ids": [ref],
    }


def build_upstream_fixture(run_id: str = "w15-run-001") -> dict[str, Any]:
    owner = {"funding_domain": "US_BROKER", "broker": "QA_BROKER", "account": "QA_ACCOUNT"}
    w2 = {
        "contract_name": "LivingWaterAI.C8C9.Work2.UnifiedIntegrationEnvelope",
        "contract_version": "C8C9-W2-UIC-v1.0.1-RECHECK1",
        "baseline_id": W7.BASELINE_ID,
        "run_id": run_id,
        "owner": deepcopy(owner),
        "currency": "USD",
        "settlement": {"cash_basis": "AVAILABLE", "cash_state": {"total": 1000.0, "available": 900.0, "unsettled": 100.0, "reserved": 100.0}, "source_status": "SETTLED"},
        "final_target": {
            "allocation_id": "C-W6-FINAL-W15-001",
            "authorization_reference": "C-W6-FINAL-W15-001",
            "confirmation_proof": {"confirmed_at": "2026-09-29T02:43:00+08:00", "confirmed_by": "qa-client"},
            "payload": {"instrument_targets": {"QQQ": {"project_target_position": 1000.0}, "BOND": {"project_target_position": 500.0}}},
        },
        "remaining_target_gap": {
            "v82": {"mode": "V82_EXISTING_RUNTIME_DERIVED", "payload": {"source_owned": True, "asset": "QQQ"}},
            "v75": {"mode": "V75_EXISTING_EXPLICIT_GAP", "payload": {"remaining_target_gap_amount": {"amount": "310.00", "currency": "USD"}}},
        },
        "executable_budget": {
            "equity": {"amount": 450.0, "currency": "USD", "cash_basis": "AVAILABLE", "owner": deepcopy(owner)},
            "bond": {"amount": 350.0, "currency": "USD", "cash_basis": "AVAILABLE", "owner": deepcopy(owner)},
        },
        "temporal": {
            "as_of": "2026-09-29T02:43:00+08:00",
            "data_as_of": {
                "C7": {"funding": "2026-09-29T02:42:00+08:00"},
                "V70": {"macro": {"timestamp": "2026-09-29T02:40:00+08:00"}},
                "V82": "2026-09-29T02:41:00+08:00",
                "V75": "2026-09-29T02:41:30+08:00",
            },
        },
        "versions": {
            "rule": {"V82": "V82-v1.21.0", "V75": W5.V75_RULE_VERSION},
            "data": {"shared_market": "snapshot-W15"},
            "schema": {"C7": "C-W7-FUND-v1.0.0", "W2": "C8C9-W2-UIC-v1.0.1-RECHECK1"},
        },
        "lineage": {"source_reference_ids": ["C7-ref", "V70-ref", "market-ref"], "upstream_snapshot_ids": {"v70": "v70-snap-W15", "c7": "c7-snap-W15"}},
        "reason_status": {"source_reason_codes": {"C7": [], "V82": [], "V75": []}, "source_status_codes": {"C7": "READY", "V82": "READY", "V75": "READY"}, "integration_diagnostics": []},
        "sgov_boundary": {
            "v70_original_dry_powder": {"amount": {"amount": "200.00", "currency": "USD"}, "weight": 0.2, "source_status": "KNOWN"},
            "sgov_bond_bucket_amount": {"amount": "40.00", "currency": "USD"},
            "sgov_dry_powder_bucket_amount": {"amount": "60.00", "currency": "USD"},
            "v75_undeployed_to_sgov": None,
            "v82_undeployed_to_sgov": None,
            "roles_kept_separate": True,
            "v82_access_forbidden": True,
            "v82_raw_equity_budget_auto_route_forbidden": True,
            "final_aggregate_computed_in_work2": False,
            "physical_subledger_out_of_scope": True,
        },
    }
    client = {"run_id": run_id, "source_namespace": "C.CLIENT_STATE", "payload": {"client_id": "client-w15", "portfolio_id": "portfolio-w15"}, "data_as_of": "2026-09-29T02:42:00+08:00", "source_reference_ids": ["client-ref"]}
    v70 = {
        "run_id": run_id,
        "source_namespace": "V70.RUNTIME_CONTEXT",
        "upstream_v70_snapshot_id": "v70-snap-W15",
        "snapshot_as_of": "2026-09-29T02:40:00+08:00",
        "payload": {"run_id": run_id, "stock_tactical_amount": "450.00", "bond_tactical_amount": "350.00", "v70_original_dry_powder_amount": "200.00", "value_state": "KNOWN", "data_quality": "OK", "issue_codes": []},
        "data_as_of": {"macro": "2026-09-29T02:40:00+08:00", "rates": {"curve": "2026-09-29T02:39:00+08:00"}},
        "source_reference_ids": ["V70-ref"],
    }
    shared = {
        "run_id": run_id,
        "source_namespace": "LOOP2.SHARED_DECISION_CONTEXT",
        "context_id": "loop2-context-W15",
        "context_version": "source-context-v15",
        "as_of": "2026-09-29T02:43:00+08:00",
        "payload": {"macro": {"rates": "source-owned"}, "market": {"snapshot_id": "market-W15"}, "news": {"snapshot_id": "news-W15"}},
        "data_as_of": {"macro": {"timestamp": "2026-09-29T02:40:00+08:00"}, "market": "2026-09-29T02:41:00+08:00", "news": {"timestamp": "2026-09-29T02:41:30+08:00"}},
        "source_reference_ids": ["market-ref", "macro-ref", "news-ref"],
        "versions": {"macro": "m15", "market": "mk15", "news": "n15"},
    }
    w3req = {"contract_name": W3.INPUT_CONTRACT_NAME, "contract_version": W3.INPUT_CONTRACT_VERSION, "baseline_id": W3.BASELINE_ID, "run_id": run_id, "work2_envelope": w2, "client_state_context": client, "v70_runtime_context": v70, "shared_decision_context": shared}
    w3out = W3.build_context_handoff(w3req)

    c7 = {
        "contract_name": W5.C7_CONTRACT_NAME,
        "contract_version": W5.C7_CONTRACT_VERSION,
        "run_id": run_id,
        "base_currency": "USD",
        "bank_cash_scope": "OUT_OF_SCOPE",
        "total_new_investment_amount": 1200.0,
        "contexts": [
            _ctx("TW_LOCAL_BROKER", "TW_LOCAL", "L1", 100.0, {"total": 100.0, "available": 100.0, "unsettled": 0.0, "reserved": 0.0}, 0.0, 0.0, "c7-local"),
            _ctx("TW_SUB_BROKERAGE", "TW_SUB", "S1", 100.0, {"total": 100.0, "available": 100.0, "unsettled": 0.0, "reserved": 0.0}, 0.0, 0.0, "c7-sub"),
            _ctx("US_BROKER", "QA_BROKER", "QA_ACCOUNT", 1000.0, {"total": 1000.0, "available": 900.0, "unsettled": 100.0, "reserved": 100.0}, 450.0, 350.0, "c7-us"),
        ],
        "source_reference_ids": ["c7-snapshot-W15"],
    }
    w4req = {
        "contract_name": W4.INPUT_CONTRACT_NAME,
        "contract_version": W4.INPUT_CONTRACT_VERSION,
        "baseline_id": W4.BASELINE_ID,
        "run_id": run_id,
        "work3_handoff": w3out,
        "c7_funding_context": c7,
        "asset_context": {"asset": {"asset_id": "QQQ", "asset_type": "BROAD_ETF", "asset_grade": "A", "portfolio_role": "CORE"}, "client_project_version": "CLIENT-PROJECT-v1", "project_target_pointer": "/instrument_targets/QQQ/project_target_position", "confirmed_position_snapshot": {"quantity": 10, "source": "BROKER"}},
    }
    w4built = W4.build_v82_runtime_input(w4req)

    source = {
        "contract_name": W5.SOURCE_CONTEXT_NAME,
        "contract_version": W5.SOURCE_CONTEXT_VERSION,
        "run_id": run_id,
        "client_ref": "CLIENT-W15-QA",
        "deployment_parameter_version": "P0-02-FROZEN",
        "funding_settlement_status": "SETTLED",
        "life_stage_code": "ACCUMULATION",
        "strategic_bond_weight_b0": {"value": "30", "unit": "PERCENT"},
        "existing_bond_holdings": [
            {"asset_id": "SGOV", "amount": {"amount": "40.00", "currency": "USD"}, "broker_account_id": "QA_ACCOUNT"},
            {"asset_id": "SPSB", "amount": {"amount": "0", "currency": "USD"}, "broker_account_id": "QA_ACCOUNT"},
        ],
        "target_bond_holdings": [
            {"asset_id": "SGOV", "target_amount": {"amount": "245.00", "currency": "USD"}, "broker_account_id": "QA_ACCOUNT"},
            {"asset_id": "SPSB", "target_amount": {"amount": "105.00", "currency": "USD"}, "broker_account_id": "QA_ACCOUNT"},
        ],
        "authorized_universe": ["SGOV", "SPSB"],
        "market_snapshot": {"data_timestamp": "2026-09-29T02:41:00+08:00", "data_source": "C8C9_WORK3_SHARED_MARKET", "freshness_state": "FRESH", "payload": {"snapshot_id": "market-W15"}, "source_lineage": ["market-ref"]},
        "v70_snapshot": {"data_timestamp": "2026-09-29T02:40:00+08:00", "data_source": "V70.RUNTIME_CONTEXT", "freshness_state": "FRESH", "payload": deepcopy(v70["payload"]), "source_lineage": ["V70-ref"]},
        "sgov_bond_bucket_amount": {"status": "KNOWN", "value": {"amount": "40.00", "currency": "USD"}},
        "sgov_dry_powder_bucket_amount": {"status": "KNOWN", "value": {"amount": "60.00", "currency": "USD"}},
        "source_reference_ids": ["V75-source-W15", "client-ref"],
        "data_as_of": {"client": "2026-09-29T02:42:00+08:00", "market": "2026-09-29T02:41:00+08:00", "v70": "2026-09-29T02:40:00+08:00"},
    }
    w5req = {"contract_name": W5.INPUT_CONTRACT_NAME, "contract_version": W5.INPUT_CONTRACT_VERSION, "baseline_id": W5.BASELINE_ID, "run_id": run_id, "work3_handoff": w3out, "c7_funding_context": c7, "v75_source_context": source}
    w5built = W5.build_v75_runtime_input(w5req)
    w6req = {"contract_name": W6.INPUT_CONTRACT_NAME, "contract_version": W6.INPUT_CONTRACT_VERSION, "baseline_id": W6.BASELINE_ID, "run_id": run_id, "work3_handoff": w3out, "c7_funding_context": c7, "work4_adapter_result": w4built, "work5_adapter_result": w5built}
    w6out = W6.validate_funding_account_isolation(w6req)

    return {"owner": owner, "run_id": run_id, "w2": w2, "w3": w3out, "c7": c7, "w4": w4built, "w5_built": w5built, "w6": w6out}


def run_frozen_v75_and_consume(fixture: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    v75_zip = ROOT / "SOURCE_PACKAGE/UPSTREAM_V75/V75_Work6_Checkpoint_RECHECK_PASS_2026-09-25.zip"
    with tempfile.TemporaryDirectory(prefix="w15_v75_") as td_s:
        td = Path(td_s)
        with zipfile.ZipFile(v75_zip) as z:
            z.extractall(td)
        vr = td / "V75_Work6_RuntimeReady_2026-09-25"
        sys.path.insert(0, str(vr / "runtime"))
        try:
            from v75_runtime import V75RunInput
            from v75_runtime.enums import DeploymentState, EvaluationState, ExistingPositionAction, GateState, NewMoneyAction
            from v75_runtime.models import Money, PerAssetDecision, PercentValue
            from v75_runtime.work3 import build_work3_state
            from v75_runtime.work5 import assemble_final_snapshot
            from v75_runtime.work6 import evaluate_runtime_ready

            run = V75RunInput.model_validate(fixture["w5_built"]["v75_runtime_input"])
            st = build_work3_state(run)
            decisions = []
            for pai in st.per_asset_inputs:
                decisions.append(
                    PerAssetDecision(
                        asset_id=pai.asset_id,
                        deployment_state=DeploymentState.PAUSE,
                        deployment_pct=PercentValue(value=Decimal("0")),
                        deploy_amount=Money(amount=Decimal("0"), currency=run.currency),
                        new_money_action=NewMoneyAction.PAUSE,
                        existing_position_action=ExistingPositionAction.HOLD,
                        existing_reduction_pct=None,
                        classification=[],
                        gate_state=GateState.PASS,
                        evaluation_state=EvaluationState.COMPLETE,
                        reason_codes=["C8C9_WORK15_QA_NO_ACTION"],
                        source_lineage=["C8C9_WORK15_QA"],
                    )
                )
            w5snap = assemble_final_snapshot(
                run=run,
                work3_state=st,
                decisions=decisions,
                v75_undeployed_to_sgov=Money(amount=run.bond_executable_budget.amount, currency=run.currency),
            )
            frozen_w6 = evaluate_runtime_ready(w5snap).model_dump(mode="json")
        finally:
            try:
                sys.path.remove(str(vr / "runtime"))
            except ValueError:
                pass
            # avoid cross-run module leakage from the extracted runtime package
            for key in [k for k in list(sys.modules) if k == "v75_runtime" or k.startswith("v75_runtime.")]:
                sys.modules.pop(key, None)
    integrated = W5.consume_v75_runtime_ready(frozen_w6, fixture["w5_built"]["integration_binding"])
    return frozen_w6, integrated


def build_work7_request(run_id: str = "w15-run-001") -> dict[str, Any]:
    fixture = build_upstream_fixture(run_id)
    frozen_w6, w5_integrated = run_frozen_v75_and_consume(fixture)
    req = {
        "contract_name": W7.INPUT_CONTRACT_NAME,
        "contract_version": W7.INPUT_CONTRACT_VERSION,
        "baseline_id": W7.BASELINE_ID,
        "run_id": run_id,
        "work3_handoff": fixture["w3"],
        "work4_v82_adapter_result": fixture["w4"],
        "work5_v75_integration_result": w5_integrated,
        "work6_funding_isolation_result": fixture["w6"],
    }
    return {"fixture": fixture, "frozen_v75_ready": frozen_w6, "work5_integrated": w5_integrated, "request": req}


def execute(run_id: str = "w15-run-001") -> dict[str, Any]:
    built = build_work7_request(run_id)
    request_before = deepcopy(built["request"])
    result = W7.validate_sgov_runtime_roles(built["request"])
    if built["request"] != request_before:
        raise AssertionError("Work7 mutated input")
    return {
        "harness_id": HARNESS_ID,
        "run_id": run_id,
        "owner": deepcopy(built["fixture"]["owner"]),
        "request": built["request"],
        "frozen_v75_ready": built["frozen_v75_ready"],
        "work5_integrated": built["work5_integrated"],
        "work7_result": result,
        "canonical_result_sha256": digest(result),
        "same_run_uniqueness_key": "|".join([
            result["run_id"],
            result["owner"]["funding_domain"],
            result["owner"]["broker"],
            result["owner"]["account"],
            result["source_digests"]["work5_v75_integration_sha256"],
            result["sgov_roles"]["v75_undeployed_to_sgov"]["destination_role"],
        ]),
    }


__all__ = ["HARNESS_ID", "ROOT", "W7", "build_upstream_fixture", "build_work7_request", "execute", "digest", "canonical_json"]
