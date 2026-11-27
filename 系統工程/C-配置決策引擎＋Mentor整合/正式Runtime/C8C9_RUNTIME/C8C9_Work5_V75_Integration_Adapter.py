"""C8C9 Work5 - V75 Integration Adapter.

This adapter binds the exact owner account's C7/Work3 bond executable budget and
source-owned V75 context to the already-ready frozen V75 runtime contract. It
must not patch V75, perform FX, derive AVAILABLE cash, recompute target/gap/
deployment, create a second Funding Domain Engine, or invent SGOV routing.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
WORK3_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffResult"
WORK3_CONTRACT_VERSION = "C8C9-W3-CHO-v1.0.1-RECHECK2"
WORK2_CONTRACT_VERSION = "C8C9-W2-UIC-v1.0.1-RECHECK1"
C7_CONTRACT_NAME = "LivingWaterAI.C.Work7.FundingContext"
C7_CONTRACT_VERSION = "C-W7-FUND-v1.0.0"
V75_RULE_VERSION = "債券V75.md v2.7.0"
V75_PREDICATE_VERSION = "V75_PREDICATE_PARAMS_v1.0.3"
V75_WORK5_CONTRACT_ID = "V75_WORK5_LIVINGWATERAI_INTEGRATION_OUTPUT_v1.0.0"
V75_WORK6_CONTRACT_ID = "V75_WORK6_RUNTIME_READY_CONTRACT_v1.0.0"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work5.V75AdapterInput"
INPUT_CONTRACT_VERSION = "C8C9-W5-V75AI-v1.0.1-RECHECK1"
SOURCE_CONTEXT_NAME = "LivingWaterAI.C8C9.Work5.V75SourceContext"
SOURCE_CONTEXT_VERSION = "C8C9-W5-V75SC-v1.0.1-RECHECK1"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work5.V75IntegrationResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W5-V75AO-v1.0.1-RECHECK1"
INPUT_SCHEMA_FILENAME = "C8C9_Work5_V75_Adapter_Input.schema_RECHECK1_2026-09-27_0207.json"
OUTPUT_SCHEMA_FILENAME = "C8C9_Work5_V75_Integration_Output.schema_RECHECK1_2026-09-27_0207.json"
FROZEN_V75_INPUT_SCHEMA_FILENAME = "C8C9_Work5_Frozen_V75RunInput.schema_RECHECK1_2026-09-27_0207.json"
FROZEN_V75_W6_SCHEMA_FILENAME = "C8C9_Work5_Frozen_Work6RuntimeReadySnapshot.schema_RECHECK1_2026-09-27_0207.json"
FORMAL_DOMAINS = {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}
SETTLEMENT_STATES = {"SETTLED", "UNSETTLED", "PARTIAL", "UNKNOWN"}
_SCHEMA_CACHE: dict[str, Draft202012Validator] = {}


class V75IntegrationError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise V75IntegrationError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W5.SHAPE", f"{field} must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W5.REQUIRED_FIELD", f"{field} must be a non-empty string")
    return value


def _number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _fail("C8C9.W5.MONEY", f"{field} boolean is invalid")
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        _fail("C8C9.W5.MONEY", f"{field} must be a finite nonnegative decimal-compatible value")
    if not d.is_finite() or d < 0:
        _fail("C8C9.W5.MONEY", f"{field} must be finite nonnegative")
    return d


def _schema_validator(filename: str) -> Draft202012Validator:
    cached = _SCHEMA_CACHE.get(filename)
    if cached is not None:
        return cached
    p = Path(__file__).resolve().parent / filename
    if not p.exists():
        _fail("C8C9.W5.SCHEMA_MISSING", f"required packaged schema missing: {filename}")
    try:
        schema = json.loads(p.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except Exception as exc:
        _fail("C8C9.W5.SCHEMA_INVALID", f"cannot load packaged schema {filename}: {exc}")
    _SCHEMA_CACHE[filename] = validator
    return validator


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            _fail("C8C9.W5.NON_JSON", "non-finite Decimal cannot be serialized")
        # Frozen V75 schemas explicitly accept decimal strings. Preserve exact value.
        return format(value, "f")
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        _fail("C8C9.W5.NON_JSON", "non-finite float cannot be serialized")
    return value


def _absence_contract():
    import importlib.util
    path=Path(__file__).resolve().parents[4]/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/funding_absence.py'
    spec=importlib.util.spec_from_file_location('c7_confirmed_absence_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _validate_schema(instance: Any, filename: str, code: str) -> None:
    normalized = _jsonable(instance)
    validator=_schema_validator(filename);absence=_absence_contract()
    if absence.is_extended(normalized):validator=Draft202012Validator(absence.extend_schema(validator.schema))
    errs = sorted(validator.iter_errors(normalized), key=lambda e: list(e.absolute_path))
    if errs:
        e = errs[0]
        path = "/" + "/".join(str(x) for x in e.absolute_path)
        _fail(code, f"{path or '/'}: {e.message}")


def _canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except Exception as exc:
        _fail("C8C9.W5.NON_JSON", f"cannot provenance-hash context: {exc}")
    return sha256(raw).hexdigest()


def _contains_exact_json_fragment(container: Any, target: Any) -> bool:
    """Return True only when target is preserved exactly somewhere inside container.

    Work3 deliberately preserves source-owned nested/scalar context shapes.  Work5
    therefore must prove that the concrete V75 market slice came from that shared
    context without inventing a new Macro/Market schema.
    """
    c = _jsonable(container)
    t = _jsonable(target)
    if c == t:
        return True
    if isinstance(c, Mapping):
        return any(_contains_exact_json_fragment(v, t) for v in c.values())
    if isinstance(c, list):
        return any(_contains_exact_json_fragment(v, t) for v in c)
    return False


def _owner_tuple(owner: Mapping[str, Any]) -> tuple[str, str, str]:
    domain = _nonempty(owner.get("funding_domain"), "owner.funding_domain")
    broker = _nonempty(owner.get("broker"), "owner.broker")
    account = _nonempty(owner.get("account"), "owner.account")
    if domain not in FORMAL_DOMAINS:
        _fail("C8C9.W5.OWNER", "owner funding_domain invalid")
    return domain, broker, account


def _money_value_matches_work3(mv0: Any, work3_money: Any, field: str, currency: str) -> None:
    mv = _mapping(mv0, field)
    status = mv.get("status")
    value = mv.get("value")
    if work3_money is None:
        if status == "KNOWN" or value is not None:
            _fail("C8C9.W5.SGOV_ROLE_SOURCE_MISMATCH", f"{field} may not fabricate known amount when Work3 source is null")
        return
    wm = _mapping(work3_money, field + ".work3_source")
    if status != "KNOWN" or value is None:
        _fail("C8C9.W5.SGOV_ROLE_SOURCE_MISMATCH", f"{field} must be KNOWN because Work3 carries a source amount")
    vm = _mapping(value, field + ".value")
    if vm.get("currency") != currency or wm.get("currency") != currency:
        _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", f"{field} currency mismatch")
    if _number(vm.get("amount"), field + ".value.amount") != _number(wm.get("amount"), field + ".work3.amount"):
        _fail("C8C9.W5.SGOV_ROLE_SOURCE_MISMATCH", f"{field} differs from Work3 source role amount")


def _validate_work3(w3: Mapping[str, Any], run_id: str) -> tuple[tuple[str, str, str], Mapping[str, Any]]:
    if w3.get("contract_name") != WORK3_CONTRACT_NAME or w3.get("contract_version") != WORK3_CONTRACT_VERSION:
        _fail("C8C9.W5.WORK3_CONTRACT", "Work3 contract/version mismatch")
    if w3.get("baseline_id") != BASELINE_ID or w3.get("work2_contract_version") != WORK2_CONTRACT_VERSION:
        _fail("C8C9.W5.BASELINE_OR_WORK2_VERSION", "frozen baseline/Work2 contract mismatch")
    if w3.get("run_id") != run_id:
        _fail("C8C9.W5.RUN_ID_MISMATCH", "Work3 run_id differs from Work5 run_id")
    owner = _owner_tuple(_mapping(w3.get("owner"), "work3_handoff.owner"))
    currency = _nonempty(w3.get("currency"), "work3_handoff.currency")
    if len(currency) != 3 or currency.upper() != currency:
        _fail("C8C9.W5.CURRENCY", "Work3 currency must be uppercase 3-letter code")
    funding = _mapping(w3.get("funding_context"), "work3_handoff.funding_context")
    settlement = _mapping(funding.get("settlement"), "funding_context.settlement")
    if settlement.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W5.CASH_BASIS", "cash_basis must remain AVAILABLE")
    budgets = _mapping(funding.get("executable_budget"), "funding_context.executable_budget")
    bond = _mapping(budgets.get("bond"), "funding_context.executable_budget.bond")
    if bond.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W5.CASH_BASIS", "bond leg must remain AVAILABLE")
    if _owner_tuple(_mapping(bond.get("owner"), "bond.owner")) != owner:
        _fail("C8C9.W5.CROSS_OWNER_FUNDING", "Work3 bond owner differs from Work3 owner")
    if bond.get("currency") != currency:
        _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", "Work3 bond currency differs from Work3 owner currency")
    _number(bond.get("amount"), "Work3 bond amount")
    bind = _mapping(_mapping(w3.get("engine_bindings"), "engine_bindings").get("v75"), "engine_bindings.v75")
    expected = {
        "consumer": "V75",
        "run_id": run_id,
        "executable_budget_pointer": "/funding_context/executable_budget/bond",
        "remaining_target_gap_pointer": "/funding_context/remaining_target_gap/v75",
        "final_target_pointer": "/final_target",
        "sgov_context_access": "READ_ONLY_BOUNDARY_CONTEXT",
    }
    for key, value in expected.items():
        if bind.get(key) != value:
            _fail("C8C9.W5.WORK3_V75_BINDING", f"engine_bindings.v75.{key} drift")
    if _owner_tuple(_mapping(bind.get("owner"), "engine_bindings.v75.owner")) != owner:
        _fail("C8C9.W5.CROSS_OWNER_FUNDING", "V75 binding owner differs")
    shared = _mapping(w3.get("shared_decision_context"), "shared_decision_context")
    if shared.get("run_id") != run_id:
        _fail("C8C9.W5.RUN_ID_MISMATCH", "shared context run_id mismatch")
    shared_id = _nonempty(shared.get("context_id"), "shared_decision_context.context_id")
    if shared.get("as_of") != _mapping(w3.get("temporal"), "temporal").get("as_of"):
        _fail("C8C9.W5.AS_OF_MISMATCH", "shared as_of differs from Work3 temporal.as_of")
    digest = _canonical_digest(shared)
    if bind.get("shared_context_id") != shared_id or bind.get("shared_context_digest_sha256") != digest:
        _fail("C8C9.W5.SHARED_CONTEXT_MISMATCH", "Work3 V75 binding does not match exact shared context id/digest")
    v70 = _mapping(w3.get("v70_runtime_context"), "v70_runtime_context")
    if v70.get("run_id") != run_id:
        _fail("C8C9.W5.RUN_ID_MISMATCH", "V70 context run_id mismatch")
    v70_sid = _nonempty(v70.get("upstream_v70_snapshot_id"), "v70_runtime_context.upstream_v70_snapshot_id")
    if _mapping(w3.get("lineage"), "lineage").get("upstream_snapshot_ids", {}).get("v70") != v70_sid:
        _fail("C8C9.W5.V70_LINEAGE_MISMATCH", "V70 snapshot does not match Work3 lineage")
    versions = _mapping(w3.get("versions"), "versions")
    if _mapping(versions.get("rule"), "versions.rule").get("V75") != V75_RULE_VERSION:
        _fail("C8C9.W5.V75_RULE_VERSION", "Work3 V75 rule version differs from frozen V75 runtime")
    sgov = _mapping(funding.get("sgov_boundary"), "funding_context.sgov_boundary")
    if sgov.get("roles_kept_separate") is not True or sgov.get("final_aggregate_computed_in_work2") is not False:
        _fail("C8C9.W5.SGOV_ROLE_SEPARATION", "Work3 SGOV role separation/aggregate ownership drift")
    if sgov.get("physical_subledger_out_of_scope") is not True:
        _fail("C8C9.W5.SGOV_PHYSICAL_SUBLEDGER", "Family physical SGOV sub-ledger remains out of scope")
    return owner, bind


def _validate_c7_against_work3(c7: Mapping[str, Any], w3: Mapping[str, Any], owner: tuple[str, str, str], run_id: str) -> Mapping[str, Any]:
    if c7.get("contract_name") != C7_CONTRACT_NAME or c7.get("contract_version") not in (C7_CONTRACT_VERSION,_absence_contract().VERSION):
        _fail("C8C9.W5.C7_CONTRACT", "C7 FundingContext contract/version mismatch")
    if c7.get("run_id") != run_id:
        _fail("C8C9.W5.RUN_ID_MISMATCH", "C7 run_id mismatch")
    if c7.get("bank_cash_scope") != "OUT_OF_SCOPE":
        _fail("C8C9.W5.BANK_CASH_FORBIDDEN", "bank cash must remain OUT_OF_SCOPE")
    if c7.get("base_currency") != w3.get("currency"):
        _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", "C7 base_currency must directly equal Work3 currency")
    contexts = c7.get("contexts")
    if not isinstance(contexts, list) or len(contexts) != 3:
        _fail("C8C9.W5.C7_DOMAIN_SET", "C7 FundingContext must retain exactly three contexts")
    domains: list[str] = []
    selected: list[Mapping[str, Any]] = []
    bucket_sum = Decimal("0")
    seen_ba: set[tuple[Any, Any]] = set()
    for idx, ctx0 in enumerate(contexts):
        ctx = _mapping(ctx0, f"c7.contexts[{idx}]")
        ident = (ctx.get("domain"), ctx.get("broker"), ctx.get("account"))
        if ident[0] not in FORMAL_DOMAINS:
            _fail("C8C9.W5.C7_DOMAIN_SET", "invalid C7 domain")
        domains.append(ident[0])
        try:absent=_absence_contract().validate_absent(ctx,c7.get("contract_version"))
        except ValueError as error:_fail("C8C9.W5.ACCOUNT_ABSENCE",str(error))
        if absent:continue
        ba = (ident[1], ident[2])
        if ba in seen_ba:
            _fail("C8C9.W5.C7_DUPLICATE_ACCOUNT", "broker+account duplicated")
        seen_ba.add(ba)
        bucket_sum += _number(ctx.get("bucket_new_investment_amount"), f"c7.contexts[{idx}].bucket_new_investment_amount")
        cash = _mapping(ctx.get("brokerage_cash_state"), f"c7.contexts[{idx}].brokerage_cash_state")
        cash_d = {k: _number(cash.get(k), f"c7.contexts[{idx}].cash.{k}") for k in ("total", "available", "unsettled", "reserved")}
        if any(cash_d[k] > cash_d["total"] for k in ("available", "unsettled", "reserved")):
            _fail("C8C9.W5.C7_CASH_STATE", "cash substate exceeds total")
        budget = _mapping(ctx.get("executable_budget"), f"c7.contexts[{idx}].executable_budget")
        legs: dict[str, Decimal] = {}
        for leg_name in ("equity", "bond"):
            leg = _mapping(budget.get(leg_name), f"c7.contexts[{idx}].{leg_name}")
            if leg.get("cash_basis") != "AVAILABLE":
                _fail("C8C9.W5.CASH_BASIS", f"C7 {leg_name} cash_basis not AVAILABLE")
            leg_owner = (leg.get("source_domain"), leg.get("source_broker"), leg.get("source_account"))
            if leg_owner != ident:
                _fail("C8C9.W5.CROSS_OWNER_FUNDING", f"C7 {leg_name} owner mismatch")
            legs[leg_name] = _number(leg.get("amount"), f"c7.contexts[{idx}].{leg_name}.amount")
        if legs["equity"] + legs["bond"] > cash_d["available"]:
            _fail("C8C9.W5.C7_BUDGET_EXCEEDS_AVAILABLE", "C7 equity+bond exceeds available")
        if legs["equity"] + legs["bond"] > _number(ctx.get("bucket_new_investment_amount"), "bucket"):
            _fail("C8C9.W5.C7_BUDGET_EXCEEDS_BUCKET", "C7 equity+bond exceeds account bucket")
        if ident == owner:
            selected.append(ctx)
    if set(domains) != FORMAL_DOMAINS or len(set(domains)) != 3:
        _fail("C8C9.W5.C7_DOMAIN_SET", "each formal C7 domain must appear exactly once")
    if bucket_sum != _number(c7.get("total_new_investment_amount"), "c7.total_new_investment_amount"):
        _fail("C8C9.W5.C7_TOTAL_MISMATCH", "C7 bucket total mismatch")
    if len(selected) != 1:
        _fail("C8C9.W5.EXECUTION_ACCOUNT_MATCH", "owner must match exactly one C7 context")
    sel = selected[0]
    w3fund = _mapping(w3.get("funding_context"), "funding_context")
    if deepcopy(sel.get("brokerage_cash_state")) != deepcopy(_mapping(w3fund.get("settlement"), "settlement").get("cash_state")):
        _fail("C8C9.W5.C7_WORK3_TAMPER", "selected C7 cash state differs from frozen Work3 owner context")
    for leg_name in ("equity", "bond"):
        cleg = _mapping(_mapping(sel.get("executable_budget"), "selected budget").get(leg_name), f"selected.{leg_name}")
        wleg = _mapping(_mapping(w3fund.get("executable_budget"), "w3 budget").get(leg_name), f"w3.{leg_name}")
        if _number(cleg.get("amount"), "c7 leg") != _number(wleg.get("amount"), "w3 leg"):
            _fail("C8C9.W5.C7_WORK3_TAMPER", f"selected C7 {leg_name} amount differs from Work3")
        if wleg.get("currency") != c7.get("base_currency") or wleg.get("cash_basis") != cleg.get("cash_basis"):
            _fail("C8C9.W5.C7_WORK3_TAMPER", f"selected C7 {leg_name} basis/currency differs from Work3")
    return sel


def _money_value_known(amount: Any, currency: str) -> dict[str, Any]:
    return {"status": "KNOWN", "value": {"amount": deepcopy(amount), "currency": currency}}


def build_v75_runtime_input(request: Mapping[str, Any]) -> dict[str, Any]:
    req = _mapping(request, "request")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W5.CONTRACT", "Work5 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W5.BASELINE", "Frozen Baseline mismatch")
    # Self-schema fail-closed: caller validation is never trusted.
    _validate_schema(req, INPUT_SCHEMA_FILENAME, "C8C9.W5.INPUT_SCHEMA")
    run_id = _nonempty(req.get("run_id"), "run_id")
    w3 = _mapping(req.get("work3_handoff"), "work3_handoff")
    owner, bind = _validate_work3(w3, run_id)
    c7 = _mapping(req.get("c7_funding_context"), "c7_funding_context")
    selected = _validate_c7_against_work3(c7, w3, owner, run_id)
    src = _mapping(req.get("v75_source_context"), "v75_source_context")
    if src.get("contract_name") != SOURCE_CONTEXT_NAME or src.get("contract_version") != SOURCE_CONTEXT_VERSION:
        _fail("C8C9.W5.SOURCE_CONTEXT_CONTRACT", "V75 source context contract/version mismatch")
    if src.get("run_id") != run_id:
        _fail("C8C9.W5.RUN_ID_MISMATCH", "V75 source context run_id mismatch")
    source_refs = src.get("source_reference_ids")
    if not isinstance(source_refs, list) or not source_refs or any(not isinstance(x, str) or not x.strip() for x in source_refs):
        _fail("C8C9.W5.LINEAGE", "V75 source context requires non-empty source_reference_ids")
    currency = w3["currency"]
    settlement_status = src.get("funding_settlement_status")
    if settlement_status not in SETTLEMENT_STATES:
        _fail("C8C9.W5.SETTLEMENT_STATE", "V75 source settlement status invalid")
    work3_settlement = _mapping(w3["funding_context"].get("settlement"), "work3 settlement")
    if work3_settlement.get("source_status") != settlement_status:
        _fail("C8C9.W5.SETTLEMENT_STATE_MISMATCH", "V75 source settlement status must exactly match Work3 source_status")
    bond_budget_amount = _number(
        _mapping(w3["funding_context"]["executable_budget"].get("bond"), "bond").get("amount"),
        "bond amount",
    )
    if settlement_status != "SETTLED" and bond_budget_amount > 0:
        _fail(
            "C8C9.W5.SETTLEMENT_NOT_EXECUTABLE",
            f"{settlement_status} funding cannot feed a positive V75 bond executable budget before SETTLED",
        )
    sgov = _mapping(w3["funding_context"].get("sgov_boundary"), "sgov_boundary")
    _money_value_matches_work3(src.get("sgov_bond_bucket_amount"), sgov.get("sgov_bond_bucket_amount"), "sgov_bond_bucket_amount", currency)
    _money_value_matches_work3(src.get("sgov_dry_powder_bucket_amount"), sgov.get("sgov_dry_powder_bucket_amount"), "sgov_dry_powder_bucket_amount", currency)
    v70 = _mapping(w3.get("v70_runtime_context"), "v70_runtime_context")
    v70_snap = _mapping(src.get("v70_snapshot"), "v75_source_context.v70_snapshot")
    if v70_snap.get("data_timestamp") != v70.get("snapshot_as_of"):
        _fail("C8C9.W5.V70_SNAPSHOT_MISMATCH", "V75 v70_snapshot timestamp differs from Work3 V70 snapshot_as_of")
    if deepcopy(v70_snap.get("payload")) != deepcopy(v70.get("payload")):
        _fail("C8C9.W5.V70_SNAPSHOT_MISMATCH", "V75 v70_snapshot payload must preserve exact Work3 V70 payload")
    v70_refs = set(v70.get("source_reference_ids") or [])
    snap_refs = set(v70_snap.get("source_lineage") or [])
    if not v70_refs or not v70_refs.issubset(snap_refs):
        _fail("C8C9.W5.V70_LINEAGE_MISMATCH", "V75 v70_snapshot lineage must contain Work3 V70 source refs")
    shared = _mapping(w3.get("shared_decision_context"), "shared_decision_context")
    shared_id = _nonempty(shared.get("context_id"), "shared_decision_context.context_id")
    shared_digest = _canonical_digest(shared)
    if bind.get("shared_context_id") != shared_id or bind.get("shared_context_digest_sha256") != shared_digest:
        _fail("C8C9.W5.SHARED_CONTEXT_MISMATCH", "Work3 V75 binding/shared context mismatch")

    # The V75 market slice must be demonstrably sourced from the exact shared
    # Loop-2 decision context.  Work3 keeps source-owned shapes, so bind by
    # exact fragment + as-of + lineage join rather than inventing a new schema.
    market_snap = _mapping(src.get("market_snapshot"), "v75_source_context.market_snapshot")
    market_payload = market_snap.get("payload")
    market_timestamp = _nonempty(market_snap.get("data_timestamp"), "market_snapshot.data_timestamp")
    market_lineage = market_snap.get("source_lineage")
    if not isinstance(market_lineage, list) or not market_lineage or any(not isinstance(x, str) or not x.strip() for x in market_lineage):
        _fail("C8C9.W5.SHARED_MARKET_LINEAGE_MISMATCH", "V75 market_snapshot requires non-empty source_lineage")
    if not _contains_exact_json_fragment(shared.get("payload"), market_payload):
        _fail("C8C9.W5.SHARED_MARKET_PAYLOAD_MISMATCH", "V75 market_snapshot payload is not preserved in Work3 shared decision context")
    if not _contains_exact_json_fragment(shared.get("data_as_of"), market_timestamp):
        _fail("C8C9.W5.SHARED_MARKET_AS_OF_MISMATCH", "V75 market_snapshot timestamp is not preserved in Work3 shared decision context data_as_of")
    shared_refs = {x for x in (shared.get("source_reference_ids") or []) if isinstance(x, str) and x}
    if not shared_refs.intersection(set(market_lineage)):
        _fail("C8C9.W5.SHARED_MARKET_LINEAGE_MISMATCH", "V75 market_snapshot lineage has no exact join to Work3 shared-context source refs")

    # Required source snapshots must also be represented in the source-owned
    # data_as_of envelope; this prevents contradictory/stale transport metadata.
    source_data_as_of = src.get("data_as_of")
    if not _contains_exact_json_fragment(source_data_as_of, market_timestamp):
        _fail("C8C9.W5.SOURCE_DATA_AS_OF_MISMATCH", "V75 source data_as_of does not preserve market_snapshot timestamp")
    if not _contains_exact_json_fragment(source_data_as_of, v70_snap.get("data_timestamp")):
        _fail("C8C9.W5.SOURCE_DATA_AS_OF_MISMATCH", "V75 source data_as_of does not preserve v70_snapshot timestamp")

    source_digest = _canonical_digest(src)
    cash = _mapping(selected.get("brokerage_cash_state"), "selected brokerage_cash_state")
    bond_leg = _mapping(_mapping(selected.get("executable_budget"), "selected executable_budget").get("bond"), "selected bond")
    lineage: list[str] = []
    def add(value: Any) -> None:
        if isinstance(value, str) and value and value not in lineage:
            lineage.append(value)
    for x in _mapping(w3.get("lineage"), "lineage").get("source_reference_ids", []): add(x)
    for x in v70.get("source_reference_ids", []): add(x)
    for x in shared.get("source_reference_ids", []): add(x)
    for x in source_refs: add(x)
    for x in market_lineage: add(x)
    for x in v70_snap.get("source_lineage", []): add(x)
    add(f"C8C9.W3.CONTEXT_HANDOFF:{w3.get('context_handoff_id')}")
    add(f"C8C9.W3.SHARED_CONTEXT_ID:{shared_id}")
    add(f"C8C9.W3.SHARED_CONTEXT_SHA256:{shared_digest}")
    add(f"C8C9.W5.V75_SOURCE_CONTEXT_SHA256:{source_digest}")
    if not lineage:
        _fail("C8C9.W5.LINEAGE", "V75 source_lineage cannot be empty")
    v75_input = {
        "client_ref": deepcopy(src["client_ref"]),
        "run_id": run_id,
        "analysis_timestamp": deepcopy(_mapping(w3.get("temporal"), "temporal")["as_of"]),
        "expected_rule_version": V75_RULE_VERSION,
        "predicate_version": V75_PREDICATE_VERSION,
        "deployment_parameter_version": deepcopy(src["deployment_parameter_version"]),
        "broker_account_id": owner[2],
        "broker_domain_type": owner[0],
        "currency": currency,
        "bond_executable_budget": {"amount": deepcopy(bond_leg["amount"]), "currency": currency},
        "broker_cash_total": _money_value_known(cash["total"], currency),
        "broker_cash_available": _money_value_known(cash["available"], currency),
        "broker_cash_unsettled": _money_value_known(cash["unsettled"], currency),
        "broker_cash_reserved": _money_value_known(cash["reserved"], currency),
        "sgov_bond_bucket_amount": deepcopy(src["sgov_bond_bucket_amount"]),
        "sgov_dry_powder_bucket_amount": deepcopy(src["sgov_dry_powder_bucket_amount"]),
        "funding_settlement_status": settlement_status,
        "life_stage_code": deepcopy(src["life_stage_code"]),
        "strategic_bond_weight_b0": deepcopy(src["strategic_bond_weight_b0"]),
        "existing_bond_holdings": deepcopy(src["existing_bond_holdings"]),
        "target_bond_holdings": deepcopy(src["target_bond_holdings"]),
        "authorized_universe": deepcopy(src["authorized_universe"]),
        "market_snapshot": deepcopy(src["market_snapshot"]),
        "v70_snapshot": deepcopy(src["v70_snapshot"]),
        "source_lineage": lineage,
    }
    _validate_schema(v75_input, FROZEN_V75_INPUT_SCHEMA_FILENAME, "C8C9.W5.FROZEN_V75_INPUT_SCHEMA")
    # Explicit same-account/currency guards before the frozen runtime consumes the object.
    for col_name in ("existing_bond_holdings", "target_bond_holdings"):
        for item in v75_input[col_name]:
            if item.get("broker_account_id") not in (None, owner[2]):
                _fail("C8C9.W5.CROSS_ACCOUNT_CONTEXT", f"{col_name} contains cross-account item")
            m = item.get("amount") or item.get("target_amount")
            if isinstance(m, Mapping) and m.get("currency") != currency:
                _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", f"{col_name} contains cross-currency item")
    binding = {
        "run_id": run_id,
        "owner": {"funding_domain": owner[0], "broker": owner[1], "account": owner[2]},
        "currency": currency,
        "work3_context_handoff_id": w3.get("context_handoff_id"),
        "upstream_v70_snapshot_id": v70.get("upstream_v70_snapshot_id"),
        "shared_context_id": shared_id,
        "shared_context_digest_sha256": shared_digest,
        "v75_source_context_digest_sha256": source_digest,
        "bond_executable_budget": {
            "amount": deepcopy(bond_leg["amount"]),
            "currency": currency,
            "cash_basis": "AVAILABLE",
            "owner": {"funding_domain": owner[0], "broker": owner[1], "account": owner[2]},
            "source_pointer": "/funding_context/executable_budget/bond",
        },
        "remaining_target_gap_pointer": "/funding_context/remaining_target_gap/v75",
        "sgov_bond_bucket_amount": deepcopy(src["sgov_bond_bucket_amount"]),
        "sgov_dry_powder_bucket_amount": deepcopy(src["sgov_dry_powder_bucket_amount"]),
        "sgov_context_access": "READ_ONLY_BOUNDARY_CONTEXT",
    }
    return {"v75_runtime_input": _jsonable(v75_input), "integration_binding": _jsonable(binding)}


def _recursive_key_present(value: Any, forbidden_key: str) -> bool:
    if isinstance(value, Mapping):
        if forbidden_key in value:
            return True
        return any(_recursive_key_present(v, forbidden_key) for v in value.values())
    if isinstance(value, list):
        return any(_recursive_key_present(v, forbidden_key) for v in value)
    return False


def consume_v75_runtime_ready(runtime_ready_snapshot: Any, integration_binding: Mapping[str, Any]) -> dict[str, Any]:
    raw = runtime_ready_snapshot.model_dump(mode="json") if hasattr(runtime_ready_snapshot, "model_dump") else runtime_ready_snapshot
    snap = _jsonable(_mapping(raw, "runtime_ready_snapshot"))
    binding = _mapping(integration_binding, "integration_binding")
    _validate_schema(snap, FROZEN_V75_W6_SCHEMA_FILENAME, "C8C9.W5.FROZEN_V75_OUTPUT_SCHEMA")
    if snap.get("run_id") != binding.get("run_id"):
        _fail("C8C9.W5.RUN_ID_MISMATCH", "V75 Work6 snapshot run_id differs from binding")
    if snap.get("broker_account_id") != _mapping(binding.get("owner"), "binding.owner").get("account"):
        _fail("C8C9.W5.ACCOUNT_MISMATCH", "V75 Work6 snapshot account differs from owner binding")
    if snap.get("currency") != binding.get("currency"):
        _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", "V75 Work6 snapshot currency differs from binding")
    out = _mapping(snap.get("output"), "runtime_ready_snapshot.output")
    if out.get("run_id") != binding.get("run_id") or out.get("broker_account_id") != _mapping(binding.get("owner"), "binding.owner").get("account"):
        _fail("C8C9.W5.V75_OUTPUT_IDENTITY", "canonical V75 output run/account differs from binding")
    if out.get("broker_domain_type") != _mapping(binding.get("owner"), "binding.owner").get("funding_domain"):
        _fail("C8C9.W5.V75_OUTPUT_IDENTITY", "canonical V75 output domain differs from binding")
    if out.get("currency") != binding.get("currency"):
        _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", "canonical V75 output currency differs from binding")
    if out.get("rule_version") != V75_RULE_VERSION or out.get("predicate_version") != V75_PREDICATE_VERSION:
        _fail("C8C9.W5.V75_VERSION", "canonical V75 output rule/predicate version mismatch")

    required_lineage = {
        f"C8C9.W3.CONTEXT_HANDOFF:{binding.get('work3_context_handoff_id')}",
        f"C8C9.W3.SHARED_CONTEXT_ID:{binding.get('shared_context_id')}",
        f"C8C9.W3.SHARED_CONTEXT_SHA256:{binding.get('shared_context_digest_sha256')}",
        f"C8C9.W5.V75_SOURCE_CONTEXT_SHA256:{binding.get('v75_source_context_digest_sha256')}",
    }
    out_lineage = out.get("source_lineage")
    snap_lineage = snap.get("source_lineage")
    if not isinstance(out_lineage, list) or not required_lineage.issubset(set(out_lineage)):
        _fail("C8C9.W5.V75_OUTPUT_LINEAGE_MISMATCH", "canonical V75 output lost required Work3/Work5 provenance tokens")
    if not isinstance(snap_lineage, list) or not required_lineage.issubset(set(snap_lineage)):
        _fail("C8C9.W5.V75_OUTPUT_LINEAGE_MISMATCH", "V75 Work6 runtime-ready snapshot lost required Work3/Work5 provenance tokens")

    allocation = _mapping(out.get("bond_allocation_final"), "bond_allocation_final")
    if allocation.get("contract_id") != V75_WORK5_CONTRACT_ID:
        _fail("C8C9.W5.V75_OUTPUT_CONTRACT", "V75 Work5 allocation contract id mismatch")
    scope = _mapping(allocation.get("account_scope"), "bond_allocation_final.account_scope")
    owner = _mapping(binding.get("owner"), "binding.owner")
    if scope.get("broker_account_id") != owner.get("account") or scope.get("broker_domain_type") != owner.get("funding_domain") or scope.get("currency") != binding.get("currency"):
        _fail("C8C9.W5.ACCOUNT_MISMATCH", "serialized V75 account_scope differs from owner binding")
    if _recursive_key_present(allocation, "sgov_dry_powder_bucket_amount"):
        _fail("C8C9.W5.SGOV_DRY_POWDER_OUTPUT_FORBIDDEN", "V75 final allocation must not aggregate SGOV_DRY_POWDER_BUCKET")
    # Preserve SGOV_BOND role exactly.
    if _jsonable(out.get("sgov_bond_bucket_amount")) != _jsonable(binding.get("sgov_bond_bucket_amount")):
        _fail("C8C9.W5.SGOV_ROLE_SOURCE_MISMATCH", "V75 output SGOV_BOND_BUCKET differs from bound source role")
    budget = _number(_mapping(binding.get("bond_executable_budget"), "binding.bond_executable_budget").get("amount"), "bound bond budget")
    deployed = Decimal("0")
    decisions = out.get("per_asset_decisions") or []
    if not isinstance(decisions, list):
        _fail("C8C9.W5.V75_CANONICAL_OUTPUT", "per_asset_decisions must be an array")
    for idx, decision0 in enumerate(decisions):
        decision = _mapping(decision0, f"per_asset_decisions[{idx}]")
        money = decision.get("deploy_amount")
        if money is not None:
            m = _mapping(money, f"per_asset_decisions[{idx}].deploy_amount")
            if m.get("currency") != binding.get("currency"):
                _fail("C8C9.W5.NO_FX_CURRENCY_MISMATCH", "V75 deploy amount currency differs from owner currency")
            deployed += _number(m.get("amount"), f"per_asset_decisions[{idx}].deploy_amount.amount")
    if deployed > budget:
        _fail("C8C9.W5.V75_BUDGET_RECONCILIATION", "V75 deployed amount exceeds bound bond executable budget")
    undeployed = out.get("v75_undeployed_to_sgov")
    if undeployed is not None:
        u = _mapping(undeployed, "v75_undeployed_to_sgov")
        if owner.get("funding_domain") != "US_BROKER" or binding.get("currency") != "USD" or u.get("currency") != "USD":
            _fail("C8C9.W5.SGOV_ROUTE_GUARD", "V75_UNDEPLOYED_TO_SGOV requires same US_BROKER account and USD")
        if deployed + _number(u.get("amount"), "v75_undeployed_to_sgov.amount") != budget:
            _fail("C8C9.W5.V75_BUDGET_RECONCILIATION", "deployed + V75 undeployed-to-SGOV must reconcile exactly to bound bond budget")
        alloc_u = allocation.get("v75_undeployed_to_sgov")
        if _jsonable(alloc_u) != _jsonable(undeployed):
            _fail("C8C9.W5.SGOV_ROUTE_GUARD", "allocation V75_UNDEPLOYED_TO_SGOV differs from canonical output")
    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "run_id": binding["run_id"],
        "owner": deepcopy(owner),
        "currency": binding["currency"],
        "work3_context_handoff_id": binding["work3_context_handoff_id"],
        "upstream_v70_snapshot_id": binding["upstream_v70_snapshot_id"],
        "shared_context_id": binding["shared_context_id"],
        "shared_context_digest_sha256": binding["shared_context_digest_sha256"],
        "v75_source_context_digest_sha256": binding["v75_source_context_digest_sha256"],
        "consumed_bond_executable_budget": deepcopy(binding["bond_executable_budget"]),
        "sgov_semantics": {
            "sgov_bond_bucket_amount": deepcopy(binding["sgov_bond_bucket_amount"]),
            "sgov_dry_powder_bucket_amount": deepcopy(binding["sgov_dry_powder_bucket_amount"]),
            "v75_undeployed_to_sgov": deepcopy(undeployed),
            "roles_kept_separate": True,
            "dry_powder_input_read_only": True,
            "adapter_created_undeployed_route": False,
            "same_account_usd_route_guard_enforced": True,
        },
        "canonical_v75_runtime_ready_snapshot": deepcopy(snap),
        "canonical_v75_output": deepcopy(out),
        "source_semantics_policy": "PRESERVE_FROZEN_V75_NO_BUSINESS_RECOMPUTE",
        "integration_diagnostics": [],
    }
    _validate_schema(result, OUTPUT_SCHEMA_FILENAME, "C8C9.W5.OUTPUT_SCHEMA")
    # Alias is transport-only and must stay byte-semantically equal after normalization.
    if result["canonical_v75_output"] != result["canonical_v75_runtime_ready_snapshot"]["output"]:
        _fail("C8C9.W5.V75_CANONICAL_OUTPUT", "canonical V75 output alias drift")
    return result


__all__ = [
    "BASELINE_ID",
    "INPUT_CONTRACT_NAME",
    "INPUT_CONTRACT_VERSION",
    "SOURCE_CONTEXT_NAME",
    "SOURCE_CONTEXT_VERSION",
    "OUTPUT_CONTRACT_NAME",
    "OUTPUT_CONTRACT_VERSION",
    "V75IntegrationError",
    "build_v75_runtime_input",
    "consume_v75_runtime_ready",
]
