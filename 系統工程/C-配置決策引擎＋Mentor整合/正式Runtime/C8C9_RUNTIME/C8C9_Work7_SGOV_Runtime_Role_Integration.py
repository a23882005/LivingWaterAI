"""C8C9 Work7 - SGOV Runtime Role Integration.

C8C9-owned semantic validation seam only. It preserves the already-owned SGOV
roles and verifies that a Frozen V75 undeployed contribution is legally routed
for the same US_BROKER/account/USD run. It does NOT aggregate a final dry-powder
bucket, build the Family physical SGOV sub-ledger, move cash, perform FX, patch
V75/V82, or create a second Funding Engine.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work7.SGOVRuntimeRoleInput"
INPUT_CONTRACT_VERSION = "C8C9-W7-SGOVI-v1.0.0"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work7.SGOVRuntimeRoleResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W7-SGOVO-v1.0.0"
WORK3_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffResult"
WORK3_CONTRACT_VERSION = "C8C9-W3-CHO-v1.0.1-RECHECK2"
WORK5_CONTRACT_NAME = "LivingWaterAI.C8C9.Work5.V75IntegrationResult"
WORK5_CONTRACT_VERSION = "C8C9-W5-V75AO-v1.0.1-RECHECK1"
WORK6_CONTRACT_NAME = "LivingWaterAI.C8C9.Work6.FundingAccountIsolationResult"
WORK6_CONTRACT_VERSION = "C8C9-W6-FAIO-v1.0.0"

_ROOT = Path(__file__).resolve().parents[1]
_INPUT_SCHEMA = _ROOT / "WORK7_OUTPUT/C8C9_Work7_SGOV_Runtime_Role_Input.schema_2026-09-28_0017.json"
_OUTPUT_SCHEMA = _ROOT / "WORK7_OUTPUT/C8C9_Work7_SGOV_Runtime_Role_Output.schema_2026-09-28_0017.json"
_W3_SCHEMA = _ROOT / "WORK3_OUTPUT/C8C9_Work3_Context_Handoff_Output.schema_RECHECK2_2026-09-26_1357.json"
_W5_SCHEMA = _ROOT / "WORK5_OUTPUT/C8C9_Work5_V75_Integration_Output.schema_RECHECK1_2026-09-27_0207.json"
_W6_SCHEMA = _ROOT / "WORK6_OUTPUT/C8C9_Work6_Funding_Account_Isolation_Output.schema_2026-09-27_0242.json"


class SGOVRuntimeRoleError(ValueError):
    """Fail-closed Work7 integration error."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise SGOVRuntimeRoleError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W7.SHAPE", f"{field} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        _fail("C8C9.W7.SHAPE", f"{field} key mismatch; missing={sorted(missing)} extra={sorted(extra)}")


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W7.SHAPE", f"{field} must be a non-empty string")
    return value


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _fail("C8C9.W7.MONEY", f"{field} boolean is not money")
    if isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            _fail("C8C9.W7.MONEY", f"{field} must be finite")
        out = Decimal(str(value))
    elif isinstance(value, str):
        try:
            out = Decimal(value)
        except InvalidOperation:
            _fail("C8C9.W7.MONEY", f"{field} is not decimal money")
    else:
        _fail("C8C9.W7.MONEY", f"{field} must be a JSON number or decimal string")
    if not out.is_finite() or out < 0:
        _fail("C8C9.W7.MONEY", f"{field} must be finite and nonnegative")
    return out


def _canon(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W7.NON_JSON", f"value is not canonical JSON serializable: {exc}")


def _digest(value: Any) -> str:
    raw = json.dumps(_canon(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


@lru_cache(maxsize=None)
def _load_schema(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(obj)
        return obj
    except Exception as exc:  # pragma: no cover - package corruption
        _fail("C8C9.W7.SCHEMA_LOAD", f"cannot load {path.name}: {exc}")


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


def _owner_tuple(value: Any, field: str) -> tuple[str, str, str]:
    obj = _mapping(value, field)
    _exact_keys(obj, {"funding_domain", "broker", "account"}, field)
    domain = obj.get("funding_domain")
    if domain not in {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}:
        _fail("C8C9.W7.OWNER", f"{field}.funding_domain invalid")
    return (domain, _nonempty(obj.get("broker"), f"{field}.broker"), _nonempty(obj.get("account"), f"{field}.account"))


def _owner_obj(owner: tuple[str, str, str]) -> dict[str, str]:
    return {"funding_domain": owner[0], "broker": owner[1], "account": owner[2]}


def _money(value: Any, field: str) -> tuple[Decimal, str]:
    obj = _mapping(value, field)
    _exact_keys(obj, {"amount", "currency"}, field)
    cur = _nonempty(obj.get("currency"), f"{field}.currency")
    if len(cur) != 3 or cur.upper() != cur:
        _fail("C8C9.W7.CURRENCY", f"{field}.currency invalid")
    return _decimal(obj.get("amount"), f"{field}.amount"), cur


def _money_value(value: Any, field: str) -> tuple[Decimal, str]:
    obj = _mapping(value, field)
    _exact_keys(obj, {"status", "value"}, field)
    if obj.get("status") != "KNOWN":
        _fail("C8C9.W7.SGOV_ROLE_SOURCE", f"{field}.status must be KNOWN for runtime role integration")
    return _money(obj.get("value"), f"{field}.value")


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        if key in value:
            return True
        return any(_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_contains_key(v, key) for v in value)
    return False


def validate_sgov_runtime_roles(request: Mapping[str, Any]) -> dict[str, Any]:
    req = _canon(_mapping(request, "request"))
    _schema(req, _INPUT_SCHEMA, "C8C9.W7.INPUT_SCHEMA")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W7.CONTRACT", "Work7 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W7.BASELINE", "Frozen Baseline mismatch")
    run_id = _nonempty(req.get("run_id"), "run_id")

    w3 = _mapping(req.get("work3_handoff"), "work3_handoff")
    _schema(w3, _W3_SCHEMA, "C8C9.W7.WORK3_SCHEMA")
    if w3.get("contract_name") != WORK3_CONTRACT_NAME or w3.get("contract_version") != WORK3_CONTRACT_VERSION:
        _fail("C8C9.W7.WORK3_CONTRACT", "Work3 contract/version mismatch")
    if w3.get("baseline_id") != BASELINE_ID or w3.get("run_id") != run_id:
        _fail("C8C9.W7.RUN_OR_BASELINE", "Work3 run/baseline mismatch")
    owner = _owner_tuple(w3.get("owner"), "work3_handoff.owner")
    currency = _nonempty(w3.get("currency"), "work3_handoff.currency")

    funding = _mapping(w3.get("funding_context"), "work3_handoff.funding_context")
    sgov = _mapping(funding.get("sgov_boundary"), "work3_handoff.funding_context.sgov_boundary")
    expected_sgov_keys = {
        "v70_original_dry_powder", "sgov_bond_bucket_amount", "sgov_dry_powder_bucket_amount",
        "v75_undeployed_to_sgov", "v82_undeployed_to_sgov", "roles_kept_separate",
        "v82_access_forbidden", "v82_raw_equity_budget_auto_route_forbidden",
        "final_aggregate_computed_in_work2", "physical_subledger_out_of_scope"
    }
    _exact_keys(sgov, expected_sgov_keys, "work3_handoff.funding_context.sgov_boundary")
    if sgov.get("roles_kept_separate") is not True:
        _fail("C8C9.W7.SGOV_ROLE_SEPARATION", "SGOV roles must remain distinct")
    if sgov.get("v82_access_forbidden") is not True or sgov.get("v82_raw_equity_budget_auto_route_forbidden") is not True:
        _fail("C8C9.W7.V82_SGOV_FORBIDDEN", "V82 SGOV access/raw-equity auto-route must remain forbidden")
    if sgov.get("v82_undeployed_to_sgov") is not None:
        _fail("C8C9.W7.V82_SGOV_FABRICATION", "V82_UNDEPLOYED_TO_SGOV is absent in current Ready contract")
    if sgov.get("final_aggregate_computed_in_work2") is not False:
        _fail("C8C9.W7.AGGREGATE_OWNER", "Work2/Work7 must not compute final SGOV dry-powder aggregate")
    if sgov.get("physical_subledger_out_of_scope") is not True:
        _fail("C8C9.W7.FAMILY_SUBLEDGER_SCOPE", "Family physical SGOV sub-ledger must remain out of scope")
    w3_bond_amt, w3_bond_cur = _money(sgov.get("sgov_bond_bucket_amount"), "work3.sgov_bond_bucket_amount")
    w3_dry_amt, w3_dry_cur = _money(sgov.get("sgov_dry_powder_bucket_amount"), "work3.sgov_dry_powder_bucket_amount")
    if w3_bond_cur != currency or w3_dry_cur != currency:
        _fail("C8C9.W7.CURRENCY", "Work3 SGOV role currencies must equal owner currency")

    w4 = _mapping(req.get("work4_v82_adapter_result"), "work4_v82_adapter_result")
    _exact_keys(w4, {"v82_runtime_input", "integration_binding"}, "work4_v82_adapter_result")
    w4rt = _mapping(w4.get("v82_runtime_input"), "work4_v82_adapter_result.v82_runtime_input")
    w4b = _mapping(w4.get("integration_binding"), "work4_v82_adapter_result.integration_binding")
    if w4b.get("run_id") != run_id or w4rt.get("run_id") != run_id:
        _fail("C8C9.W7.RUN_ID_MISMATCH", "Work4 binding/runtime run_id differs")
    if _owner_tuple(w4b.get("owner"), "work4.binding.owner") != owner:
        _fail("C8C9.W7.OWNER_MISMATCH", "Work4 V82 binding owner differs from canonical owner")
    w4_execution = _mapping(w4rt.get("execution_account"), "work4.v82_runtime_input.execution_account")
    w4_serialized_owner = (w4_execution.get("domain"), w4_execution.get("broker"), w4_execution.get("account"))
    if w4_serialized_owner != owner:
        _fail("C8C9.W7.OWNER_MISMATCH", "Work4 serialized V82 execution owner differs from canonical owner")
    if w4b.get("currency") != currency:
        _fail("C8C9.W7.CURRENCY", "Work4 V82 currency differs")
    if w4b.get("work3_context_handoff_id") != w3.get("context_handoff_id"):
        _fail("C8C9.W7.WORK3_LINEAGE_MISMATCH", "Work4 does not bind exact Work3 handoff")
    w4eq_leg = _mapping(w4b.get("equity_executable_budget"), "work4.binding.equity_executable_budget")
    if w4eq_leg.get("currency") != currency or w4eq_leg.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W7.V82_BUDGET_MISMATCH", "Work4 V82 equity leg currency/cash basis drift")
    if _owner_tuple(w4eq_leg.get("owner"), "work4.binding.equity_executable_budget.owner") != owner:
        _fail("C8C9.W7.OWNER_MISMATCH", "Work4 V82 equity leg owner differs from canonical owner")
    if w4eq_leg.get("source_pointer") != "/funding_context/executable_budget/equity":
        _fail("C8C9.W7.V82_BUDGET_MISMATCH", "Work4 V82 equity leg source pointer drift")
    if w4b.get("v70_original_dry_powder_executable") is not False or w4b.get("v82_undeployed_to_sgov_present") is not False:
        _fail("C8C9.W7.V82_SGOV_FORBIDDEN", "Work4 binding indicates illegal V82 SGOV access/route")
    if _contains_key(w4rt, "v75_undeployed_to_sgov") or _contains_key(w4rt, "v82_undeployed_to_sgov"):
        _fail("C8C9.W7.V82_SGOV_FABRICATION", "V82 runtime input contains SGOV undeployed route field")

    w5 = _mapping(req.get("work5_v75_integration_result"), "work5_v75_integration_result")
    _schema(w5, _W5_SCHEMA, "C8C9.W7.WORK5_SCHEMA")
    if w5.get("contract_name") != WORK5_CONTRACT_NAME or w5.get("contract_version") != WORK5_CONTRACT_VERSION:
        _fail("C8C9.W7.WORK5_CONTRACT", "Work5 V75 integration contract/version mismatch")
    if w5.get("baseline_id") != BASELINE_ID or w5.get("run_id") != run_id:
        _fail("C8C9.W7.RUN_OR_BASELINE", "Work5 run/baseline mismatch")
    if _owner_tuple(w5.get("owner"), "work5.owner") != owner:
        _fail("C8C9.W7.OWNER_MISMATCH", "Work5 V75 owner differs from canonical owner")
    if w5.get("currency") != currency:
        _fail("C8C9.W7.CURRENCY", "Work5 V75 currency differs")
    if w5.get("work3_context_handoff_id") != w3.get("context_handoff_id"):
        _fail("C8C9.W7.WORK3_LINEAGE_MISMATCH", "Work5 does not bind exact Work3 handoff")

    sem = _mapping(w5.get("sgov_semantics"), "work5.sgov_semantics")
    for key in ("roles_kept_separate", "dry_powder_input_read_only", "same_account_usd_route_guard_enforced"):
        if sem.get(key) is not True:
            _fail("C8C9.W7.SGOV_ROLE_SEPARATION", f"Work5 {key} must remain true")
    if sem.get("adapter_created_undeployed_route") is not False:
        _fail("C8C9.W7.SGOV_ROUTE_SOURCE", "Work5 adapter may not create undeployed SGOV route")
    w5_bond_amt, w5_bond_cur = _money_value(sem.get("sgov_bond_bucket_amount"), "work5.sgov_bond_bucket_amount")
    w5_dry_amt, w5_dry_cur = _money_value(sem.get("sgov_dry_powder_bucket_amount"), "work5.sgov_dry_powder_bucket_amount")
    if (w5_bond_amt, w5_bond_cur) != (w3_bond_amt, w3_bond_cur):
        _fail("C8C9.W7.SGOV_ROLE_SOURCE", "SGOV_BOND_BUCKET drift between Work3 and Work5")
    if (w5_dry_amt, w5_dry_cur) != (w3_dry_amt, w3_dry_cur):
        _fail("C8C9.W7.SGOV_ROLE_SOURCE", "SGOV_DRY_POWDER_BUCKET drift between Work3 and Work5")

    canonical_v75 = _mapping(w5.get("canonical_v75_output"), "work5.canonical_v75_output")
    snap = _mapping(w5.get("canonical_v75_runtime_ready_snapshot"), "work5.canonical_v75_runtime_ready_snapshot")
    snap_out = _mapping(snap.get("output"), "work5.canonical_v75_runtime_ready_snapshot.output")
    undeployed = sem.get("v75_undeployed_to_sgov")
    if _canon(undeployed) != _canon(canonical_v75.get("v75_undeployed_to_sgov")) or _canon(undeployed) != _canon(snap_out.get("v75_undeployed_to_sgov")):
        _fail("C8C9.W7.SGOV_ROUTE_SOURCE", "V75_UNDEPLOYED_TO_SGOV must be exact Frozen V75 output contribution")
    contribution_amount: Decimal | None = None
    contribution_currency: str | None = None
    if undeployed is not None:
        contribution_amount, contribution_currency = _money(undeployed, "work5.v75_undeployed_to_sgov")
        if owner[0] != "US_BROKER" or currency != "USD" or contribution_currency != "USD":
            _fail("C8C9.W7.SGOV_ROUTE_GUARD", "V75_UNDEPLOYED_TO_SGOV requires same US_BROKER owner and USD")
        if canonical_v75.get("broker_account_id") != owner[2] or snap.get("broker_account_id") != owner[2]:
            _fail("C8C9.W7.SGOV_ROUTE_GUARD", "V75_UNDEPLOYED_TO_SGOV must remain same account")
        if canonical_v75.get("broker_domain_type") != "US_BROKER":
            _fail("C8C9.W7.SGOV_ROUTE_GUARD", "V75 canonical output domain must be US_BROKER for SGOV route")

    w6 = _mapping(req.get("work6_funding_isolation_result"), "work6_funding_isolation_result")
    _schema(w6, _W6_SCHEMA, "C8C9.W7.WORK6_SCHEMA")
    if w6.get("contract_name") != WORK6_CONTRACT_NAME or w6.get("contract_version") != WORK6_CONTRACT_VERSION:
        _fail("C8C9.W7.WORK6_CONTRACT", "Work6 contract/version mismatch")
    if w6.get("baseline_id") != BASELINE_ID or w6.get("run_id") != run_id:
        _fail("C8C9.W7.RUN_OR_BASELINE", "Work6 run/baseline mismatch")
    if _owner_tuple(w6.get("owner"), "work6.owner") != owner or w6.get("currency") != currency:
        _fail("C8C9.W7.OWNER_MISMATCH", "Work6 owner/currency differs from canonical owner")
    if w6.get("work3_context_handoff_id") != w3.get("context_handoff_id"):
        _fail("C8C9.W7.WORK3_LINEAGE_MISMATCH", "Work6 does not bind exact Work3 handoff")
    w4_c7 = _mapping(w4rt.get("c7_funding_context"), "work4.v82_runtime_input.c7_funding_context")
    if _digest(w4_c7) != w6.get("c7_funding_context_digest_sha256"):
        _fail("C8C9.W7.C7_LINEAGE_MISMATCH", "Work4 serialized C7 Funding Context differs from Work6 authoritative C7 digest")

    cash = _mapping(w6.get("cash_eligibility"), "work6.cash_eligibility")
    if cash.get("cash_basis") != "AVAILABLE" or cash.get("unsettled_reserved_consumed") is not False or cash.get("available_formula_inferred") is not False:
        _fail("C8C9.W7.CASH_ROUTE_GUARD", "Work6 cash eligibility boundary drift")
    eq_budget = _decimal(cash.get("equity_executable_budget"), "work6.equity_executable_budget")
    bond_budget = _decimal(cash.get("bond_executable_budget"), "work6.bond_executable_budget")
    w4eq = _mapping(w4b.get("equity_executable_budget"), "work4.binding.equity_executable_budget")
    w5bond = _mapping(w5.get("consumed_bond_executable_budget"), "work5.consumed_bond_executable_budget")
    if _decimal(w4eq.get("amount"), "work4.equity_executable_budget.amount") != eq_budget:
        _fail("C8C9.W7.V82_BUDGET_MISMATCH", "Work4 V82 equity budget differs from Work6 isolated equity budget")
    if _decimal(w5bond.get("amount"), "work5.bond_executable_budget.amount") != bond_budget:
        _fail("C8C9.W7.V75_BUDGET_MISMATCH", "Work5 V75 bond budget differs from Work6 isolated bond budget")
    if contribution_amount is not None and contribution_amount > bond_budget:
        _fail("C8C9.W7.SGOV_ROUTE_GUARD", "V75 undeployed contribution exceeds isolated bond executable budget")

    # Crucial scope: Work7 intentionally does NOT add current dry powder + contribution.
    # This avoids double counting and preserves final aggregation/physical reconciliation for Family F2.
    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "run_id": run_id,
        "owner": _owner_obj(owner),
        "currency": currency,
        "work3_context_handoff_id": w3.get("context_handoff_id"),
        "source_digests": {
            "work4_v82_adapter_binding_sha256": _digest(w4b),
            "work5_v75_integration_sha256": _digest(w5),
            "work6_funding_isolation_sha256": _digest(w6),
        },
        "sgov_roles": {
            "sgov_bond_bucket": {
                "role": "SGOV_BOND_BUCKET",
                "source": "V75_BOND_ROLE_CONTEXT",
                "amount": str(w3_bond_amt),
                "currency": w3_bond_cur,
                "aggregation_performed": False,
            },
            "sgov_dry_powder_bucket": {
                "role": "SGOV_DRY_POWDER_BUCKET",
                "source": "READ_ONLY_UPSTREAM_CONTEXT",
                "amount": str(w3_dry_amt),
                "currency": w3_dry_cur,
                "aggregation_performed": False,
            },
            "v75_undeployed_to_sgov": {
                "role": "V75_UNDEPLOYED_TO_SGOV",
                "source": "FROZEN_V75_OUTPUT",
                "contribution": deepcopy(undeployed),
                "destination_role": "SGOV_DRY_POWDER_BUCKET",
                "contribution_applied_to_aggregate": False,
            },
        },
        "route_safety": {
            "roles_kept_separate": True,
            "same_us_broker_account_guard_enforced": True,
            "v82_equity_budget_auto_route_forbidden": True,
            "idle_usd_auto_route_forbidden": True,
            "reserved_cash_auto_route_forbidden": True,
            "unsettled_cash_auto_route_forbidden": True,
            "same_run_double_count_forbidden": True,
            "final_dry_powder_aggregate_computed": False,
            "family_physical_subledger_created": False,
        },
        "funding_evidence": {
            "cash_basis": "AVAILABLE",
            "equity_executable_budget": str(eq_budget),
            "bond_executable_budget": str(bond_budget),
            "unsettled": str(_decimal(cash.get("unsettled"), "work6.unsettled")),
            "reserved": str(_decimal(cash.get("reserved"), "work6.reserved")),
            "v75_undeployed_contribution": None if contribution_amount is None else str(contribution_amount),
        },
        "source_semantics_policy": "PRESERVE_ROLES_VALIDATE_ROUTE_NO_AGGREGATE_NO_SECOND_FUNDING_ENGINE_NO_FX",
        "integration_diagnostics": [],
    }
    _schema(result, _OUTPUT_SCHEMA, "C8C9.W7.OUTPUT_SCHEMA")
    return result


__all__ = [
    "BASELINE_ID", "INPUT_CONTRACT_NAME", "INPUT_CONTRACT_VERSION",
    "OUTPUT_CONTRACT_NAME", "OUTPUT_CONTRACT_VERSION", "SGOVRuntimeRoleError",
    "validate_sgov_runtime_roles",
]
