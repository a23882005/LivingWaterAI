"""C8C9 Work14 - Multi-account + Funding E2E Matrix executor.

Work14-owned orchestration only.  It consumes the Gate-E-qualified vNext Funding
Contract sidecar and the requalified Work1-10 integration bridge.  It does not
change V70/V82/V75 business logic and never treats reporting currency as
executable currency.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
OV = ROOT / "CONTRACT_EXTENSION_VNEXT"
EXECUTOR_ID = "C8C9-W14-MULTIACCOUNT-FUNDING-E2E-v1.0.0"
OUTPUT_CONTRACT = "LivingWaterAI.C8C9.Work14.MultiAccountFundingE2EResult"
OUTPUT_VERSION = "C8C9-W14-FUND-E2E-v1.0.0"

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

C7 = _load("w14_c7_vnext", OV / "GATE_A_C_WORK7/c_work7_funding_context_vnext.py")
RQ = _load("w14_requal_vnext", OV / "GATE_B_WORK1_10/c8c9_vnext_requalification.py")

class Work14Error(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

def _fail(code: str, detail: str):
    raise Work14Error(code, detail)

def _canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def digest(v: Any) -> str:
    return sha256(_canon(v)).hexdigest()

def _d(v: Any) -> Decimal:
    return Decimal(str(v))

def _owner_tuple(c: Mapping[str, Any]) -> tuple[str, str, str]:
    return c["funding_domain"], c["broker"], c["account"]

def execute(parent: Mapping[str, Any]) -> dict[str, Any]:
    """Execute Work14 funding/account E2E using only qualified predecessor contracts."""
    parent = deepcopy(dict(parent))
    c7 = C7.validate_funding_context(parent)
    gate = RQ.formal_gate(parent)

    contexts = parent["contexts"]
    by_key = {c["owner_key"]: c for c in contexts}
    if len(by_key) != len(contexts):
        _fail("C8C9.W14.DUP_OWNER", "canonical owner coverage is not one-to-one")

    envs = gate["owner_envelopes"]
    w4 = gate["work4_v82_guards"]
    w5 = gate["work5_v75_guards"]
    down = gate["work7_9_bindings"]
    for label, rows in (("owner_envelopes", envs), ("work4", w4), ("work5", w5), ("work7_9", down)):
        if len(rows) != len(contexts):
            _fail("C8C9.W14.OWNER_COVERAGE", f"{label} {len(rows)} != {len(contexts)}")
        if {r["owner_key"] for r in rows} != set(by_key):
            _fail("C8C9.W14.OWNER_COVERAGE", f"{label} owner set mismatch")

    observed_by_currency: dict[str, Decimal] = {}
    executable_by_currency: dict[str, dict[str, Decimal]] = {}
    owner_results = []
    w4_by = {r["owner_key"]: r for r in w4}
    w5_by = {r["owner_key"]: r for r in w5}
    down_by = {r["owner_key"]: r for r in down}
    env_by = {r["owner_key"]: r for r in envs}
    for c in contexts:
        key = c["owner_key"]
        cur = c["currency"]
        observed_by_currency[cur] = observed_by_currency.get(cur, Decimal("0")) + _d(c["bucket_new_investment_amount"])
        executable_by_currency.setdefault(cur, {"equity": Decimal("0"), "bond": Decimal("0")})
        eq = _d(c["executable_budget"]["equity"]["amount"])
        bd = _d(c["executable_budget"]["bond"]["amount"])
        executable_by_currency[cur]["equity"] += eq
        executable_by_currency[cur]["bond"] += bd
        a, b, d = w4_by[key], w5_by[key], down_by[key]
        if _d(a["amount"]) != eq or _d(b["amount"]) != bd:
            _fail("C8C9.W14.BUDGET_BINDING", key)
        if a["currency"] != cur or b["currency"] != cur or d["currency"] != cur:
            _fail("C8C9.W14.CURRENCY_BINDING", key)
        if a["owner_run_id"] != c["owner_run_id"] or b["owner_run_id"] != c["owner_run_id"] or d["owner_run_id"] != c["owner_run_id"]:
            _fail("C8C9.W14.OWNER_RUN_BINDING", key)
        if d["run_id"] != parent["run_id"] or d["lineage_status"] != "SAME_PARENT_RUN_OWNER_LOCAL":
            _fail("C8C9.W14.RUN_LINEAGE", key)
        if eq > 0 or bd > 0:
            if c["settlement"]["status"] != "SETTLED":
                _fail("C8C9.W14.SETTLEMENT", key)
        owner_results.append({
            "owner_key": key,
            "owner_run_id": c["owner_run_id"],
            "owner": {"funding_domain": c["funding_domain"], "broker": c["broker"], "account": c["account"]},
            "currency": cur,
            "settlement_status": c["settlement"]["status"],
            "bucket_new_investment_amount": c["bucket_new_investment_amount"],
            "available": c["brokerage_cash_state"]["available"],
            "unsettled": c["brokerage_cash_state"]["unsettled"],
            "reserved": c["brokerage_cash_state"]["reserved"],
            "equity_executable": c["executable_budget"]["equity"]["amount"],
            "bond_executable": c["executable_budget"]["bond"]["amount"],
            "work3_handoff_sha256": digest(env_by[key]["work3_handoff"]),
            "downstream_lineage_status": d["lineage_status"],
        })

    declared = {k: _d(v) for k, v in parent["funding_totals_by_currency"].items()}
    if declared != observed_by_currency:
        _fail("C8C9.W14.FUNDING_RECONCILIATION", f"declared={declared} observed={observed_by_currency}")

    result = {
        "contract_name": OUTPUT_CONTRACT,
        "contract_version": OUTPUT_VERSION,
        "executor_id": EXECUTOR_ID,
        "vnext_contract": C7.CONTRACT_VERSION,
        "run_id": parent["run_id"],
        "funding_event_id": parent["funding_event_id"],
        "base_currency_reporting_only": parent["base_currency"],
        "owner_count": len(contexts),
        "funding_domains_present": sorted({c["funding_domain"] for c in contexts}),
        "account_native_currencies_present": sorted({c["currency"] for c in contexts}),
        "repeated_funding_domains": sorted({d for d in {c["funding_domain"] for c in contexts} if sum(c["funding_domain"] == d for c in contexts) > 1}),
        "funding_event_reconciliation": {
            "declared_totals_by_currency": {k: float(v) for k, v in sorted(declared.items())},
            "observed_totals_by_currency": {k: float(v) for k, v in sorted(observed_by_currency.items())},
            "exact": True,
            "cross_currency_scalar_total_computed": False,
        },
        "executable_totals_by_currency": {
            cur: {leg: float(val) for leg, val in legs.items()} for cur, legs in sorted(executable_by_currency.items())
        },
        "owner_results": owner_results,
        "work6_v82_isolation": deepcopy(gate["work6_v82_isolation"]),
        "work6_v75_isolation": deepcopy(gate["work6_v75_isolation"]),
        "safety": {
            "no_implicit_fx": gate["no_implicit_fx"] is True,
            "cross_account_funding_forbidden": True,
            "cross_broker_funding_forbidden": True,
            "cross_domain_funding_forbidden": True,
            "settled_only_positive_executable": True,
            "available_formula_inferred": c7["available_formula_inferred"],
            "reserved_unsettled_consumed_as_executable": False,
            "normalized_reporting_evidence_used_for_execution": False,
            "unknown_preserved_not_coerced": True,
        },
        "runtime_identity": {
            "idempotency_key_fields": deepcopy(c7["runtime_idempotency_key_fields"]),
            "canonical_owner_results": len(owner_results),
            "funding_event_count_in_this_request": c7["funding_event_count_in_this_request"],
        },
        "predecessor_requalification_evidence": {
            "deterministic_sha256": gate["deterministic_sha256"],
            "historical_work14_release_flag": gate["work14_release"],
            "family_f2_release": gate["family_f2_release"],
            "production_cutover": gate["production_cutover"],
        },
    }
    result["canonical_result_sha256"] = digest(result)
    return result

__all__ = ["EXECUTOR_ID", "OUTPUT_CONTRACT", "OUTPUT_VERSION", "Work14Error", "execute", "digest", "C7", "RQ"]
