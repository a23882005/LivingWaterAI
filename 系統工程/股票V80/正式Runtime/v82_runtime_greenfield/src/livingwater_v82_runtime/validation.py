"""W6 input validation and C7 funding/account isolation consumer guard.

This module validates/selects/binds only. It never allocates, sweeps, nets,
transfers, converts, optimizes, or routes funding and therefore does not create
a second Funding Domain Engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .enums import CashBasis, FundingDomain
from .models import BoundEquityBudgetView
from .schema_runtime import compile_schema
from . import funding_absence
from jsonschema import Draft202012Validator

INPUT_CONTRACT_NAME = "LivingWaterAI.V82.RuntimeInput"
INPUT_CONTRACT_VERSION = "V82-INPUT-v1.0.1-W2-RECHECK2"
C7_CONTRACT_NAME = "LivingWaterAI.C.Work7.FundingContext"
C7_CONTRACT_VERSION = "C-W7-FUND-v1.0.0"
FORMAL_DOMAINS = frozenset(d.value for d in FundingDomain)

@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    meaning: str

class V82InputValidationError(ValueError):
    """Fail-closed W6 contract error carrying canonical diagnostic issues."""
    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{x.code}@{x.path}: {x.meaning}" for x in self.issues))

@dataclass(frozen=True, slots=True)
class ValidatedFundingBinding:
    bound_equity_budget: BoundEquityBudgetView
    c7_contract_name: str
    c7_contract_version: str
    run_id: str


def _issue(code: str, path: str, meaning: str) -> V82InputValidationError:
    return V82InputValidationError([ValidationIssue(code, path, meaning)])


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _issue("V82E_REQUIRED_FIELD_MISSING", path, "required object is absent or malformed")
    return value


def _required(obj: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in obj or obj[key] is None:
        raise _issue("V82E_REQUIRED_FIELD_MISSING", f"{path}.{key}", "required field is missing")
    return obj[key]


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _issue("V82E_REQUIRED_FIELD_MISSING", path, "required non-empty string is missing")
    return value


def _money(value: Any, path: str, code: str) -> Decimal:
    # bool is an int subclass but is never a money amount.
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _issue(code, path, "amount must be a finite nonnegative numeric value")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _issue(code, path, "amount must be a finite nonnegative numeric value")
    if not d.is_finite() or d < 0:
        raise _issue(code, path, "amount must be finite and nonnegative")
    return d


def _identity(ctx: Mapping[str, Any], path: str) -> tuple[str, str, str]:
    domain = _nonempty_string(_required(ctx, "domain", path), f"{path}.domain")
    if domain not in FORMAL_DOMAINS:
        raise _issue("V82E_ILLEGAL_FUNDING_DOMAIN", f"{path}.domain", "domain is outside the exact three-domain contract")
    broker = _nonempty_string(_required(ctx, "broker", path), f"{path}.broker")
    account = _nonempty_string(_required(ctx, "account", path), f"{path}.account")
    return domain, broker, account


def _validate_leg(leg: Mapping[str, Any], ctx_id: tuple[str, str, str], path: str) -> Decimal:
    amount = _money(_required(leg, "amount", path), f"{path}.amount", "V82E_EXECUTABLE_BUDGET_AMOUNT_INVALID")
    cash_basis = _required(leg, "cash_basis", path)
    if cash_basis != CashBasis.AVAILABLE.value:
        raise _issue("V82E_CASH_BASIS_NOT_AVAILABLE", f"{path}.cash_basis", "executable leg cash_basis must be AVAILABLE")
    owner = (
        _nonempty_string(_required(leg, "source_domain", path), f"{path}.source_domain"),
        _nonempty_string(_required(leg, "source_broker", path), f"{path}.source_broker"),
        _nonempty_string(_required(leg, "source_account", path), f"{path}.source_account"),
    )
    if owner[0] not in FORMAL_DOMAINS:
        raise _issue("V82E_ILLEGAL_FUNDING_DOMAIN", f"{path}.source_domain", "owner domain is outside the exact three-domain contract")
    if owner != ctx_id:
        # Preserve the most specific cross-* diagnostic when possible.
        if owner[0] != ctx_id[0]:
            code = "V82E_CROSS_DOMAIN_FUNDING"
        elif owner[1] != ctx_id[1]:
            code = "V82E_CROSS_BROKER_FUNDING"
        elif owner[2] != ctx_id[2]:
            code = "V82E_CROSS_ACCOUNT_FUNDING"
        else:
            code = "V82E_EQUITY_BUDGET_OWNER_MISMATCH"
        raise _issue(code, path, "executable leg owner does not equal its account context")
    return amount


def validate_and_bind_funding(runtime_input: Mapping[str, Any]) -> ValidatedFundingBinding:
    """Validate W6 funding/account isolation and return the immutable equity view.

    Exact Decimal arithmetic is used for reconciliation. W6 intentionally does
    not invent an upstream tolerance that is absent from C-W7-FUND-v1.0.0.
    """
    root = _mapping(runtime_input, "$")
    if _required(root, "contract_name", "$") != INPUT_CONTRACT_NAME or _required(root, "contract_version", "$") != INPUT_CONTRACT_VERSION:
        raise _issue("V82E_CONTRACT_CONFLICT", "$", "V82 runtime input contract identity mismatch")
    run_id = _nonempty_string(_required(root, "run_id", "$"), "$.run_id")
    execution = _mapping(_required(root, "execution_account", "$"), "$.execution_account")
    requested = _identity(execution, "$.execution_account")
    v70 = _mapping(_required(root, "upstream_v70_snapshot", "$"), "$.upstream_v70_snapshot")
    v70_run = _nonempty_string(_required(v70, "run_id", "$.upstream_v70_snapshot"), "$.upstream_v70_snapshot.run_id")
    c7 = _mapping(_required(root, "c7_funding_context", "$"), "$.c7_funding_context")
    if _required(c7, "contract_name", "$.c7_funding_context") != C7_CONTRACT_NAME or _required(c7, "contract_version", "$.c7_funding_context") not in (C7_CONTRACT_VERSION,funding_absence.VERSION):
        raise _issue("V82E_FUNDING_CONTEXT_CONTRACT_MISMATCH", "$.c7_funding_context", "C7 funding contract identity mismatch")
    c7_run = _nonempty_string(_required(c7, "run_id", "$.c7_funding_context"), "$.c7_funding_context.run_id")
    if len({run_id, v70_run, c7_run}) != 1:
        raise _issue("V82E_RUN_ID_MISMATCH", "$.run_id", "V82, V70 and C7 run_id must be identical")
    currency = _nonempty_string(_required(c7, "base_currency", "$.c7_funding_context"), "$.c7_funding_context.base_currency")
    if len(currency) != 3 or currency.upper() != currency or not currency.isalpha():
        raise _issue("V82E_EXECUTABLE_CURRENCY_MISSING", "$.c7_funding_context.base_currency", "base currency must be explicit uppercase 3-letter code")
    if _required(c7, "bank_cash_scope", "$.c7_funding_context") != "OUT_OF_SCOPE":
        raise _issue("V82E_BANK_CASH_FORBIDDEN", "$.c7_funding_context.bank_cash_scope", "bank cash must remain OUT_OF_SCOPE")
    total_new = _money(_required(c7, "total_new_investment_amount", "$.c7_funding_context"), "$.c7_funding_context.total_new_investment_amount", "V82E_FUNDING_TOTAL_INVALID")
    contexts = _required(c7, "contexts", "$.c7_funding_context")
    if not isinstance(contexts, (list, tuple)):
        raise _issue("V82E_REQUIRED_FIELD_MISSING", "$.c7_funding_context.contexts", "contexts must be an array")
    if len(contexts) != 3:
        raise _issue("V82E_FUNDING_DOMAIN_SET_INVALID", "$.c7_funding_context.contexts", "exactly three funding contexts are required")

    seen_ids: set[tuple[str, str, str]] = set()
    seen_broker_accounts: set[tuple[str, str]] = set()
    domains: list[str] = []
    bucket_sum = Decimal("0")
    normalized: list[tuple[tuple[str, str, str], Mapping[str, Any], Decimal]] = []

    for i, raw_ctx in enumerate(contexts):
        path = f"$.c7_funding_context.contexts[{i}]"
        ctx = _mapping(raw_ctx, path)
        try:absent=funding_absence.validate_absent(ctx,c7['contract_version'])
        except ValueError as exc:raise _issue('V82E_ABSENT_CONTEXT_INVALID',path,str(exc))
        if absent:
            domains.append(ctx['domain'])
            continue
        ctx_id = _identity(ctx, path)
        domains.append(ctx_id[0])
        if ctx_id in seen_ids:
            raise _issue("V82E_DUPLICATE_ACCOUNT_CONTEXT", path, "duplicate domain+broker+account context")
        seen_ids.add(ctx_id)
        ba = (ctx_id[1], ctx_id[2])
        if ba in seen_broker_accounts:
            raise _issue("V82E_DUPLICATE_BROKER_ACCOUNT_CONTEXT", path, "broker+account pair duplicated across funding domains")
        seen_broker_accounts.add(ba)
        bucket = _money(_required(ctx, "bucket_new_investment_amount", path), f"{path}.bucket_new_investment_amount", "V82E_FUNDING_BUCKET_AMOUNT_INVALID")
        bucket_sum += bucket
        cash = _mapping(_required(ctx, "brokerage_cash_state", path), f"{path}.brokerage_cash_state")
        cash_values = {k: _money(_required(cash, k, f"{path}.brokerage_cash_state"), f"{path}.brokerage_cash_state.{k}", "V82E_BROKERAGE_CASH_STATE_INVALID") for k in ("total", "available", "unsettled", "reserved")}
        if any(cash_values[k] > cash_values["total"] for k in ("available", "unsettled", "reserved")):
            raise _issue("V82E_BROKERAGE_CASH_STATE_INCONSISTENT", f"{path}.brokerage_cash_state", "cash substate individually exceeds total")
        budget = _mapping(_required(ctx, "executable_budget", path), f"{path}.executable_budget")
        equity = _mapping(_required(budget, "equity", f"{path}.executable_budget"), f"{path}.executable_budget.equity")
        bond = _mapping(_required(budget, "bond", f"{path}.executable_budget"), f"{path}.executable_budget.bond")
        equity_amount = _validate_leg(equity, ctx_id, f"{path}.executable_budget.equity")
        bond_amount = _validate_leg(bond, ctx_id, f"{path}.executable_budget.bond")
        combined = equity_amount + bond_amount
        if combined > cash_values["available"]:
            raise _issue("V82E_EXECUTABLE_BUDGET_EXCEEDS_AVAILABLE", f"{path}.executable_budget", "equity+bond exceeds same-account available cash")
        if combined > bucket:
            raise _issue("V82E_EXECUTABLE_BUDGET_EXCEEDS_ACCOUNT_BUCKET", f"{path}.executable_budget", "equity+bond exceeds same-account new-investment bucket")
        normalized.append((ctx_id, ctx, equity_amount))

    if set(domains) != FORMAL_DOMAINS or len(domains) != len(set(domains)):
        raise _issue("V82E_FUNDING_DOMAIN_SET_INVALID", "$.c7_funding_context.contexts", "each formal funding domain must appear exactly once")
    if bucket_sum != total_new:
        raise _issue("V82E_FUNDING_BUCKET_TOTAL_MISMATCH", "$.c7_funding_context.total_new_investment_amount", "account buckets do not exactly reconcile to total")
    matches = [(ctx, amount) for ident, ctx, amount in normalized if ident == requested]
    if not matches:
        raise _issue("V82E_EXECUTION_ACCOUNT_NOT_FOUND", "$.execution_account", "requested account has no exact C7 context")
    if len(matches) != 1:
        raise _issue("V82E_DUPLICATE_ACCOUNT_CONTEXT", "$.execution_account", "requested account selection is ambiguous")
    selected, amount = matches[0]
    refs = selected.get("source_reference_ids")
    if not isinstance(refs, (list, tuple)) or not refs or any(not isinstance(x, str) or not x for x in refs) or len(refs) != len(set(refs)):
        raise _issue("V82E_REQUIRED_FIELD_MISSING", "$.c7_funding_context.contexts[].source_reference_ids", "source_reference_ids must be non-empty unique strings")
    # Full W2 JSON-Schema shape validation is performed after funding-specific
    # diagnostics so B02 can preserve its more specific canonical error codes.
    validator=compile_schema("runtime_input")
    if c7['contract_version']==funding_absence.VERSION:
        validator=Draft202012Validator(funding_absence.extend_schema(validator.schema))
    schema_errors = sorted(validator.iter_errors(root), key=lambda e: list(e.absolute_path))
    if schema_errors:
        err = schema_errors[0]
        path = "$" + "".join(f"[{x}]" if isinstance(x, int) else f".{x}" for x in err.absolute_path)
        code = "V82E_REQUIRED_FIELD_MISSING" if err.validator == "required" else ("V82E_INVALID_ENUM" if err.validator in {"enum", "const"} else "V82E_CONTRACT_CONFLICT")
        raise _issue(code, path, f"runtime input schema violation: {err.message}")

    bound = BoundEquityBudgetView(
        domain=FundingDomain(requested[0]), broker=requested[1], account=requested[2], amount=amount,
        currency=currency, cash_basis=CashBasis.AVAILABLE, source_contract=f"{C7_CONTRACT_NAME}/{c7['contract_version']}",
        source_reference_ids=tuple(refs),
    )
    return ValidatedFundingBinding(bound, C7_CONTRACT_NAME, c7["contract_version"], run_id)
