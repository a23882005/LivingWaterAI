"""C8C9 Work6 - Funding + Account Isolation Integration Guard.

C8C9-owned validation/integration seam only.  It proves that the already-owned
C7 Funding Context, Work3 handoff, Work4 V82 adapter serialization, and Work5
V75 adapter serialization remain bound to the same formal run and exact
funding owner.  It never optimizes funding, moves cash, performs FX, derives
available cash, or creates a second Funding Domain Engine.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work6.FundingAccountIsolationInput"
INPUT_CONTRACT_VERSION = "C8C9-W6-FAII-v1.0.0"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work6.FundingAccountIsolationResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W6-FAIO-v1.0.0"
WORK3_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffResult"
WORK3_CONTRACT_VERSION = "C8C9-W3-CHO-v1.0.1-RECHECK2"
WORK4_INPUT_RESULT_KEYS = {"v82_runtime_input", "integration_binding"}
WORK5_INPUT_RESULT_KEYS = {"v75_runtime_input", "integration_binding"}
C7_CONTRACT_NAME = "LivingWaterAI.C.Work7.FundingContext"
C7_CONTRACT_VERSION = "C-W7-FUND-v1.0.0"
FORMAL_DOMAINS = {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}

_ROOT = Path(__file__).resolve().parents[1]
_INPUT_SCHEMA = _ROOT / "WORK6_OUTPUT/C8C9_Work6_Funding_Account_Isolation_Input.schema_2026-09-27_0242.json"
_OUTPUT_SCHEMA = _ROOT / "WORK6_OUTPUT/C8C9_Work6_Funding_Account_Isolation_Output.schema_2026-09-27_0242.json"
_C7_SCHEMA = _ROOT / "WORK6_OUTPUT/C8C9_Work6_Frozen_C7_Funding_Context.schema_2026-09-27_0242.json"
_W3_SCHEMA = _ROOT / "WORK3_OUTPUT/C8C9_Work3_Context_Handoff_Output.schema_RECHECK2_2026-09-26_1357.json"


class FundingAccountIsolationError(ValueError):
    """Fail-closed Work6 integration error. Codes are diagnostics only."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise FundingAccountIsolationError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W6.SHAPE", f"{field} must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W6.SHAPE", f"{field} must be a non-empty string")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        _fail("C8C9.W6.SHAPE", f"{field} key mismatch; missing={sorted(missing)} extra={sorted(extra)}")


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _fail("C8C9.W6.MONEY", f"{field} boolean is not money")
    if isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            _fail("C8C9.W6.MONEY", f"{field} must be finite")
        out = Decimal(str(value))
    elif isinstance(value, str):
        try:
            out = Decimal(value)
        except InvalidOperation:
            _fail("C8C9.W6.MONEY", f"{field} is not a decimal")
    else:
        _fail("C8C9.W6.MONEY", f"{field} must be a JSON number or decimal string")
    if not out.is_finite() or out < 0:
        _fail("C8C9.W6.MONEY", f"{field} must be finite and nonnegative")
    return out


def _canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W6.NON_JSON_CONTEXT", f"not canonical JSON serializable: {exc}")
    return sha256(raw).hexdigest()


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return schema
    except Exception as exc:  # pragma: no cover - package corruption path
        _fail("C8C9.W6.SCHEMA_LOAD", f"cannot load schema {path.name}: {exc}")


def _absence_contract():
    import importlib.util
    path=Path(__file__).resolve().parents[4]/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/funding_absence.py'
    spec=importlib.util.spec_from_file_location('c7_confirmed_absence_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _validate_schema(value: Any, path: Path, code: str) -> None:
    schema=_load_schema(path);absence=_absence_contract()
    if absence.is_extended(value):schema=absence.extend_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        e = errors[0]
        loc = "/".join(str(x) for x in e.absolute_path) or "$"
        _fail(code, f"{loc}: {e.message}")


def _owner_tuple(owner: Any, field: str) -> tuple[str, str, str]:
    obj = _mapping(owner, field)
    _exact_keys(obj, {"funding_domain", "broker", "account"}, field)
    domain = obj.get("funding_domain")
    if domain not in FORMAL_DOMAINS:
        _fail("C8C9.W6.OWNER", f"{field}.funding_domain invalid")
    return (domain, _nonempty(obj.get("broker"), f"{field}.broker"), _nonempty(obj.get("account"), f"{field}.account"))


def _owner_obj(owner: tuple[str, str, str]) -> dict[str, str]:
    return {"funding_domain": owner[0], "broker": owner[1], "account": owner[2]}


def _work3_validate(w3: Mapping[str, Any], run_id: str) -> tuple[tuple[str, str, str], str, Mapping[str, Any]]:
    _validate_schema(w3, _W3_SCHEMA, "C8C9.W6.WORK3_SCHEMA")
    if w3.get("contract_name") != WORK3_CONTRACT_NAME or w3.get("contract_version") != WORK3_CONTRACT_VERSION:
        _fail("C8C9.W6.WORK3_CONTRACT", "Work3 contract/version mismatch")
    if w3.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W6.BASELINE", "Work3 Frozen Baseline mismatch")
    if w3.get("run_id") != run_id:
        _fail("C8C9.W6.RUN_ID_MISMATCH", "Work3 run_id differs")
    owner = _owner_tuple(w3.get("owner"), "work3_handoff.owner")
    currency = _nonempty(w3.get("currency"), "work3_handoff.currency")
    funding = _mapping(w3.get("funding_context"), "work3_handoff.funding_context")
    settlement = _mapping(funding.get("settlement"), "work3_handoff.funding_context.settlement")
    if settlement.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W6.CASH_BASIS", "Work3 settlement cash_basis must remain AVAILABLE")
    budgets = _mapping(funding.get("executable_budget"), "work3_handoff.funding_context.executable_budget")
    for leg_name in ("equity", "bond"):
        leg = _mapping(budgets.get(leg_name), f"work3_handoff.executable_budget.{leg_name}")
        if leg.get("cash_basis") != "AVAILABLE":
            _fail("C8C9.W6.CASH_BASIS", f"Work3 {leg_name} executable budget must be AVAILABLE-basis")
        if _owner_tuple(leg.get("owner"), f"work3_handoff.{leg_name}.owner") != owner:
            _fail("C8C9.W6.WRONG_OWNER", f"Work3 {leg_name} owner differs from canonical owner")
        if leg.get("currency") != currency:
            _fail("C8C9.W6.NO_FX", f"Work3 {leg_name} currency differs from owner currency")
        _decimal(leg.get("amount"), f"work3_handoff.{leg_name}.amount")
    return owner, currency, funding


def _c7_validate(c7: Mapping[str, Any], run_id: str, owner: tuple[str, str, str], currency: str) -> tuple[Mapping[str, Any], Decimal, Decimal]:
    _validate_schema(c7, _C7_SCHEMA, "C8C9.W6.C7_SCHEMA")
    if c7.get("contract_name") != C7_CONTRACT_NAME or c7.get("contract_version") not in (C7_CONTRACT_VERSION,_absence_contract().VERSION):
        _fail("C8C9.W6.C7_CONTRACT", "C7 Funding Context contract/version mismatch")
    if c7.get("run_id") != run_id:
        _fail("C8C9.W6.RUN_ID_MISMATCH", "C7 Funding Context run_id differs")
    if c7.get("bank_cash_scope") != "OUT_OF_SCOPE":
        _fail("C8C9.W6.BANK_CASH_FORBIDDEN", "bank cash must remain OUT_OF_SCOPE")
    if c7.get("base_currency") != currency:
        _fail("C8C9.W6.NO_FX", "C7 base_currency differs; Work6 performs no FX")

    contexts = c7.get("contexts")
    if not isinstance(contexts, list) or len(contexts) != 3:
        _fail("C8C9.W6.DOMAIN_SET", "C7 must contain exactly three Funding Domain contexts")
    domains: list[str] = []
    seen_broker_accounts: set[tuple[str, str]] = set()
    selected: list[Mapping[str, Any]] = []
    bucket_sum = Decimal("0")
    for idx, ctx0 in enumerate(contexts):
        ctx = _mapping(ctx0, f"c7.contexts[{idx}]")
        ident = (ctx.get("domain"), ctx.get("broker"), ctx.get("account"))
        if ident[0] not in FORMAL_DOMAINS:
            _fail("C8C9.W6.DOMAIN_SET", f"context[{idx}] domain invalid")
        try:absent=_absence_contract().validate_absent(ctx,c7.get("contract_version"))
        except ValueError as error:_fail("C8C9.W6.ACCOUNT_ABSENCE",str(error))
        if absent:
            domains.append(ident[0])
            continue
        broker = _nonempty(ident[1], f"c7.contexts[{idx}].broker")
        account = _nonempty(ident[2], f"c7.contexts[{idx}].account")
        ident = (ident[0], broker, account)
        domains.append(ident[0])
        ba = (broker, account)
        if ba in seen_broker_accounts:
            _fail("C8C9.W6.DUPLICATE_ACCOUNT_CONTEXT", f"duplicated broker/account {broker}/{account}")
        seen_broker_accounts.add(ba)
        bucket = _decimal(ctx.get("bucket_new_investment_amount"), f"c7.contexts[{idx}].bucket_new_investment_amount")
        bucket_sum += bucket
        cash = _mapping(ctx.get("brokerage_cash_state"), f"c7.contexts[{idx}].brokerage_cash_state")
        cash_d = {k: _decimal(cash.get(k), f"c7.contexts[{idx}].cash.{k}") for k in ("total", "available", "unsettled", "reserved")}
        if any(cash_d[k] > cash_d["total"] for k in ("available", "unsettled", "reserved")):
            _fail("C8C9.W6.CASH_STATE", f"context[{idx}] cash substate exceeds total")
        ex = _mapping(ctx.get("executable_budget"), f"c7.contexts[{idx}].executable_budget")
        leg_amounts: dict[str, Decimal] = {}
        for leg_name in ("equity", "bond"):
            leg = _mapping(ex.get(leg_name), f"c7.contexts[{idx}].executable_budget.{leg_name}")
            if leg.get("cash_basis") != "AVAILABLE":
                _fail("C8C9.W6.CASH_BASIS", f"C7 {leg_name} budget does not use AVAILABLE cash")
            leg_owner = (leg.get("source_domain"), leg.get("source_broker"), leg.get("source_account"))
            if leg_owner != ident:
                if leg_owner[0] != ident[0]:
                    _fail("C8C9.W6.CROSS_DOMAIN_FUNDING", f"C7 {leg_name} budget source_domain crosses context")
                if leg_owner[1] != ident[1]:
                    _fail("C8C9.W6.CROSS_BROKER_FUNDING", f"C7 {leg_name} budget source_broker crosses context")
                _fail("C8C9.W6.CROSS_ACCOUNT_FUNDING", f"C7 {leg_name} budget source_account crosses context")
            leg_amounts[leg_name] = _decimal(leg.get("amount"), f"c7.contexts[{idx}].{leg_name}.amount")
        combined = leg_amounts["equity"] + leg_amounts["bond"]
        if combined > cash_d["available"]:
            _fail("C8C9.W6.UNAVAILABLE_CASH_MISUSE", f"context[{idx}] executable budgets exceed explicit available cash")
        if combined > bucket:
            _fail("C8C9.W6.ACCOUNT_BUCKET_OVERSPEND", f"context[{idx}] executable budgets exceed own account funding bucket")
        if ident == owner:
            selected.append(ctx)
    if len(set(domains)) != 3 or set(domains) != FORMAL_DOMAINS:
        _fail("C8C9.W6.DOMAIN_SET", "each formal Funding Domain must appear exactly once")
    total = _decimal(c7.get("total_new_investment_amount"), "c7.total_new_investment_amount")
    if bucket_sum != total:
        _fail("C8C9.W6.FUNDING_EVENT_TOTAL_MISMATCH", f"bucket sum {bucket_sum} != total {total}")
    if len(selected) != 1:
        _fail("C8C9.W6.WRONG_OWNER", "canonical Work3 owner must match exactly one C7 account context")
    return selected[0], bucket_sum, total


def _exact_money_leg(leg: Mapping[str, Any], expected_amount: Decimal, owner: tuple[str, str, str], currency: str, pointer: str, field: str) -> None:
    if _owner_tuple(leg.get("owner"), f"{field}.owner") != owner:
        _fail("C8C9.W6.WRONG_OWNER", f"{field}.owner differs from canonical owner")
    if leg.get("currency") != currency:
        _fail("C8C9.W6.NO_FX", f"{field}.currency differs from canonical currency")
    if leg.get("cash_basis") != "AVAILABLE":
        basis = str(leg.get("cash_basis"))
        if basis == "UNSETTLED":
            _fail("C8C9.W6.UNSETTLED_CASH_MISUSE", f"{field} attempts to consume unsettled cash")
        if basis == "RESERVED":
            _fail("C8C9.W6.RESERVED_CASH_MISUSE", f"{field} attempts to consume reserved cash")
        _fail("C8C9.W6.CASH_BASIS", f"{field} must remain AVAILABLE-basis")
    if _decimal(leg.get("amount"), f"{field}.amount") != expected_amount:
        _fail("C8C9.W6.BUDGET_BINDING_MISMATCH", f"{field}.amount differs from C7/Work3 executable budget")
    if leg.get("source_pointer") != pointer:
        _fail("C8C9.W6.BUDGET_POINTER_MISMATCH", f"{field}.source_pointer drift")


def _work4_validate(result: Mapping[str, Any], run_id: str, owner: tuple[str, str, str], currency: str, expected_equity: Decimal, c7: Mapping[str, Any], w3: Mapping[str, Any]) -> None:
    _exact_keys(result, WORK4_INPUT_RESULT_KEYS, "work4_adapter_result")
    runtime = _mapping(result.get("v82_runtime_input"), "work4_adapter_result.v82_runtime_input")
    binding = _mapping(result.get("integration_binding"), "work4_adapter_result.integration_binding")
    if runtime.get("run_id") != run_id or binding.get("run_id") != run_id:
        _fail("C8C9.W6.RUN_ID_MISMATCH", "Work4 adapter serialized run_id mismatch")
    execution = _mapping(runtime.get("execution_account"), "work4.v82_runtime_input.execution_account")
    serialized_owner = (execution.get("domain"), execution.get("broker"), execution.get("account"))
    if serialized_owner != owner:
        if serialized_owner[0] != owner[0]:
            _fail("C8C9.W6.SERIALIZED_ACCOUNT_SCOPE_TAMPER", "V82 serialized execution domain differs from canonical owner")
        if serialized_owner[1] != owner[1]:
            _fail("C8C9.W6.SERIALIZED_ACCOUNT_SCOPE_TAMPER", "V82 serialized execution broker differs from canonical owner")
        _fail("C8C9.W6.SERIALIZED_ACCOUNT_SCOPE_TAMPER", "V82 serialized execution account differs from canonical owner")
    if runtime.get("c7_funding_context") != c7:
        _fail("C8C9.W6.C7_SERIALIZATION_TAMPER", "Work4 serialized C7 Funding Context differs from authoritative input")
    if _owner_tuple(binding.get("owner"), "work4.integration_binding.owner") != owner:
        _fail("C8C9.W6.WRONG_OWNER", "Work4 integration binding owner differs")
    if binding.get("currency") != currency:
        _fail("C8C9.W6.NO_FX", "Work4 integration binding currency differs")
    eq = _mapping(binding.get("equity_executable_budget"), "work4.integration_binding.equity_executable_budget")
    _exact_money_leg(eq, expected_equity, owner, currency, "/funding_context/executable_budget/equity", "work4.equity_executable_budget")
    if binding.get("work3_context_handoff_id") != w3.get("context_handoff_id"):
        _fail("C8C9.W6.WORK3_LINEAGE_MISMATCH", "Work4 binding lost Work3 context_handoff_id")


def _work5_validate(result: Mapping[str, Any], run_id: str, owner: tuple[str, str, str], currency: str, expected_bond: Decimal, w3: Mapping[str, Any]) -> None:
    _exact_keys(result, WORK5_INPUT_RESULT_KEYS, "work5_adapter_result")
    runtime = _mapping(result.get("v75_runtime_input"), "work5_adapter_result.v75_runtime_input")
    binding = _mapping(result.get("integration_binding"), "work5_adapter_result.integration_binding")
    if runtime.get("run_id") != run_id or binding.get("run_id") != run_id:
        _fail("C8C9.W6.RUN_ID_MISMATCH", "Work5 adapter serialized run_id mismatch")
    serialized_owner = (runtime.get("broker_domain_type"), binding.get("owner", {}).get("broker"), runtime.get("broker_account_id"))
    # V75 frozen input does not serialize broker name; binding preserves that C7 field.
    if serialized_owner[0] != owner[0] or serialized_owner[2] != owner[2]:
        _fail("C8C9.W6.SERIALIZED_ACCOUNT_SCOPE_TAMPER", "V75 serialized domain/account differs from canonical owner")
    if _owner_tuple(binding.get("owner"), "work5.integration_binding.owner") != owner:
        _fail("C8C9.W6.WRONG_OWNER", "Work5 integration binding owner differs")
    if binding.get("currency") != currency or runtime.get("currency") != currency:
        _fail("C8C9.W6.NO_FX", "Work5 serialized currency differs")
    bond = _mapping(binding.get("bond_executable_budget"), "work5.integration_binding.bond_executable_budget")
    _exact_money_leg(bond, expected_bond, owner, currency, "/funding_context/executable_budget/bond", "work5.bond_executable_budget")
    runtime_bond = _mapping(runtime.get("bond_executable_budget"), "work5.v75_runtime_input.bond_executable_budget")
    if runtime_bond.get("currency") != currency or _decimal(runtime_bond.get("amount"), "work5.v75_runtime_input.bond_executable_budget.amount") != expected_bond:
        _fail("C8C9.W6.BUDGET_BINDING_MISMATCH", "V75 serialized bond executable budget differs from C7/Work3")
    if binding.get("work3_context_handoff_id") != w3.get("context_handoff_id"):
        _fail("C8C9.W6.WORK3_LINEAGE_MISMATCH", "Work5 binding lost Work3 context_handoff_id")


def validate_funding_account_isolation(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Work6 cross-line Funding/Account Isolation and return evidence snapshot."""
    req = _mapping(request, "request")
    _validate_schema(req, _INPUT_SCHEMA, "C8C9.W6.INPUT_SCHEMA")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W6.CONTRACT", "Work6 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W6.BASELINE", "Frozen Baseline mismatch")
    run_id = _nonempty(req.get("run_id"), "run_id")
    w3 = _mapping(req.get("work3_handoff"), "work3_handoff")
    owner, currency, funding = _work3_validate(w3, run_id)
    c7 = _mapping(req.get("c7_funding_context"), "c7_funding_context")
    selected, bucket_sum, total = _c7_validate(c7, run_id, owner, currency)

    selected_cash = _mapping(selected.get("brokerage_cash_state"), "selected.brokerage_cash_state")
    work3_settlement = _mapping(funding.get("settlement"), "work3.funding_context.settlement")
    if deepcopy(work3_settlement.get("cash_state")) != deepcopy(selected_cash):
        _fail("C8C9.W6.C7_WORK3_CASH_TAMPER", "Work3 owner cash state differs from selected C7 account")
    selected_budget = _mapping(selected.get("executable_budget"), "selected.executable_budget")
    work3_budget = _mapping(funding.get("executable_budget"), "work3.funding_context.executable_budget")
    expected: dict[str, Decimal] = {}
    for leg_name in ("equity", "bond"):
        c7_leg = _mapping(selected_budget.get(leg_name), f"selected.{leg_name}")
        w3_leg = _mapping(work3_budget.get(leg_name), f"work3.{leg_name}")
        if _decimal(c7_leg.get("amount"), f"selected.{leg_name}.amount") != _decimal(w3_leg.get("amount"), f"work3.{leg_name}.amount"):
            _fail("C8C9.W6.C7_WORK3_BUDGET_TAMPER", f"{leg_name} amount differs between C7 and Work3")
        if w3_leg.get("cash_basis") != "AVAILABLE":
            basis = str(w3_leg.get("cash_basis"))
            if basis == "UNSETTLED":
                _fail("C8C9.W6.UNSETTLED_CASH_MISUSE", "Work3 executable budget attempts unsettled cash")
            if basis == "RESERVED":
                _fail("C8C9.W6.RESERVED_CASH_MISUSE", "Work3 executable budget attempts reserved cash")
            _fail("C8C9.W6.CASH_BASIS", "Work3 executable budget must be AVAILABLE-basis")
        expected[leg_name] = _decimal(w3_leg.get("amount"), f"work3.{leg_name}.amount")

    available = _decimal(selected_cash.get("available"), "selected.cash.available")
    own_bucket = _decimal(selected.get("bucket_new_investment_amount"), "selected.bucket_new_investment_amount")
    combined = expected["equity"] + expected["bond"]
    if combined > available:
        _fail("C8C9.W6.UNAVAILABLE_CASH_MISUSE", "owner executable budgets exceed explicit available cash")
    if combined > own_bucket:
        _fail("C8C9.W6.ACCOUNT_BUCKET_OVERSPEND", "owner executable budgets exceed own funding bucket")

    w4 = _mapping(req.get("work4_adapter_result"), "work4_adapter_result")
    _work4_validate(w4, run_id, owner, currency, expected["equity"], c7, w3)
    w5 = _mapping(req.get("work5_adapter_result"), "work5_adapter_result")
    _work5_validate(w5, run_id, owner, currency, expected["bond"], w3)

    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "run_id": run_id,
        "owner": _owner_obj(owner),
        "currency": currency,
        "work3_context_handoff_id": w3.get("context_handoff_id"),
        "c7_funding_context_digest_sha256": _canonical_digest(c7),
        "funding_event_reconciliation": {
            "total_new_investment_amount": str(total),
            "three_domain_bucket_sum": str(bucket_sum),
            "exact_three_domains": True,
            "duplicate_broker_account_context": False,
        },
        "cash_eligibility": {
            "cash_basis": "AVAILABLE",
            "total": str(_decimal(selected_cash.get("total"), "cash.total")),
            "available": str(available),
            "unsettled": str(_decimal(selected_cash.get("unsettled"), "cash.unsettled")),
            "reserved": str(_decimal(selected_cash.get("reserved"), "cash.reserved")),
            "equity_executable_budget": str(expected["equity"]),
            "bond_executable_budget": str(expected["bond"]),
            "combined_executable_budget": str(combined),
            "within_available": True,
            "within_owner_bucket": True,
            "unsettled_reserved_consumed": False,
            "available_formula_inferred": False,
        },
        "adapter_binding_evidence": {
            "work4_v82_serialized_owner_matches": True,
            "work5_v75_serialized_owner_matches": True,
            "work4_equity_budget_exact": True,
            "work5_bond_budget_exact": True,
            "cross_account_funding_forbidden": True,
            "cross_broker_funding_forbidden": True,
            "cross_domain_funding_forbidden": True,
            "wrong_owner_forbidden": True,
        },
        "source_semantics_policy": "VALIDATE_ROUTE_ONLY_NO_SECOND_FUNDING_DOMAIN_ENGINE_NO_FX",
        "integration_diagnostics": [],
    }
    _validate_schema(result, _OUTPUT_SCHEMA, "C8C9.W6.OUTPUT_SCHEMA")
    return result


__all__ = [
    "BASELINE_ID",
    "INPUT_CONTRACT_NAME",
    "INPUT_CONTRACT_VERSION",
    "OUTPUT_CONTRACT_NAME",
    "OUTPUT_CONTRACT_VERSION",
    "FundingAccountIsolationError",
    "validate_funding_account_isolation",
]
