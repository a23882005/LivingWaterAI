"""C8C9 Work4 - V82 Integration Adapter.

C8C9-owned adapter only. It binds a frozen Work3 handoff and the original full
C7 FundingContext to the already-ready V82 Runtime contract. It does not patch
V82, recompute targets/gaps/completion, perform FX, derive AVAILABLE cash, or
route unused equity funding to SGOV.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
WORK3_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffResult"
WORK3_CONTRACT_VERSION = "C8C9-W3-CHO-v1.0.1-RECHECK2"
WORK2_CONTRACT_VERSION = "C8C9-W2-UIC-v1.0.1-RECHECK1"
C7_CONTRACT_NAME = "LivingWaterAI.C.Work7.FundingContext"
C7_CONTRACT_VERSION = "C-W7-FUND-v1.0.0"
V82_INPUT_NAME = "LivingWaterAI.V82.RuntimeInput"
V82_INPUT_VERSION = "V82-INPUT-v1.0.1-W2-RECHECK2"
V82_OUTPUT_NAME = "LivingWaterAI.V82.RuntimeOutput"
V82_OUTPUT_VERSION = "V82-OUTPUT-v1.0.1-W2-RECHECK2"
V82_RULE_VERSION = "V82-v1.21.0"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work4.V82AdapterInput"
INPUT_CONTRACT_VERSION = "C8C9-W4-V82AI-v1.0.0"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work4.V82IntegrationResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W4-V82AO-v1.0.0"
INPUT_SCHEMA_FILENAME = "C8C9_Work4_V82_Adapter_Input.schema_2026-09-26_1429.json"
OUTPUT_SCHEMA_FILENAME = "C8C9_Work4_V82_Integration_Output.schema_2026-09-26_1429.json"
_SCHEMA_CACHE: dict[str, Draft202012Validator] = {}

FORMAL_DOMAINS = {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}
CANONICAL_FIELD_NAMES = (
    "latest_price","market_data_as_of","asset_behavior_classification","primary_framework","secondary_framework",
    "fundamental_state","valuation_state","td9_high_state","td9_low_state","kd_state","macd_state","ma_state","emv_state","rsi_state","volume_price_state",
    "daily_timeframe_state","weekly_timeframe_state","monthly_timeframe_state","atr_value","drawdown_from_reference_high","previous_swing_low_1","previous_swing_low_2","previous_swing_low_3",
    "price_map","first_buy_zone","second_price_zone","deep_extreme_discount_zone","left_buy_point_state","right_confirmation_state","runaway_state","macro_state","credit_liquidity_state",
    "material_news_policy_state","exposure_overlap","position_cap","project_target_position","confirmed_position","actual_completion_rate","normal_deployment_mode","primary_special_classification",
    "execution_action","canonical_deployment_target_rate","execution_amount","execution_quantity","execution_price","projected_post_fill_completion_rate","order_submission_plan","cancel_conditions","reevaluation_conditions"
)
FORMAL_OUTPUT_NAMES=("今日特殊分類","目前部署階段","目標與完成率","今日動作","執行比例","執行金額","執行股數","執行價格","成交後完成率","是否掛單","掛單方式","取消條件","下一次重新評估條件")

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

def _normalize_formal_13(value: Any) -> list[dict[str, Any]]:
    """Serialize the frozen V82 in-memory 13-field Mapping to its frozen JSON wire wrapper.

    This is transport-only: values are copied verbatim and no investment value is
    recomputed. Already-wire-shaped arrays are validated and copied unchanged.
    """
    if isinstance(value, Mapping):
        if tuple(value.keys()) != FORMAL_OUTPUT_NAMES:
            _fail("C8C9.W4.V82_CANONICAL_OUTPUT", "V82 in-memory 13-field view must preserve exact order/set")
        return [
            {"ordinal": ordinal, "display_label": label, "canonical_mapping": mapping, "value": deepcopy(value[label])}
            for ordinal, label, mapping in FORMAL_MAPPING_META
        ]
    if isinstance(value, list):
        if len(value) != 13:
            _fail("C8C9.W4.V82_CANONICAL_OUTPUT", "V82 wire fields_1_to_13 must contain exactly 13 entries")
        normalized=deepcopy(value)
        for item, (ordinal,label,mapping) in zip(normalized, FORMAL_MAPPING_META):
            row=_mapping(item,"v82_output.fields_1_to_13[]")
            if row.get("ordinal")!=ordinal or row.get("display_label")!=label or row.get("canonical_mapping")!=mapping or "value" not in row:
                _fail("C8C9.W4.V82_CANONICAL_OUTPUT", "V82 wire fields_1_to_13 mapping drift")
        return normalized
    _fail("C8C9.W4.V82_CANONICAL_OUTPUT", "V82 fields_1_to_13 must be in-memory Mapping or frozen wire array")


def _verify_formal_13_projection(canonical: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    def cv(name: str) -> Any:
        env=_mapping(canonical.get(name),f"canonical_analysis.{name}")
        if "value" not in env:
            _fail("C8C9.W4.V82_CANONICAL_OUTPUT", f"canonical field {name} missing value")
        return env["value"]
    order=cv("order_submission_plan")
    order_map=_mapping(order,"canonical_analysis.order_submission_plan.value") if order != "UNKNOWN" else None
    expected=(
        cv("primary_special_classification"),
        {"mode":cv("normal_deployment_mode"),"execution_context":cv("execution_action")},
        {"project_target_position":cv("project_target_position"),"confirmed_position":cv("confirmed_position"),"actual_completion_rate":cv("actual_completion_rate")},
        cv("execution_action"),cv("canonical_deployment_target_rate"),cv("execution_amount"),cv("execution_quantity"),cv("execution_price"),cv("projected_post_fill_completion_rate"),
        "UNKNOWN" if order_map is None else order_map.get("should_place_order"),
        "UNKNOWN" if order_map is None else {k:order_map.get(k) for k in ("order_type","time_in_force","scheduling_mode")},
        cv("cancel_conditions"),cv("reevaluation_conditions"),
    )
    for i,(row,exp) in enumerate(zip(rows,expected),1):
        if row.get("value") != exp:
            _fail("C8C9.W4.V82_13_VIEW_CONFLICT", f"fields_1_to_13 row {i} differs from canonical projection")


class V82IntegrationError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise V82IntegrationError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W4.SHAPE", f"{field} must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W4.REQUIRED_FIELD", f"{field} must be a non-empty string")
    return value


def _number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _fail("C8C9.W4.MONEY", f"{field} boolean is invalid")
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value < 0:
            _fail("C8C9.W4.MONEY", f"{field} must be finite nonnegative")
    elif not isinstance(value, str):
        _fail("C8C9.W4.MONEY", f"{field} must be JSON number or decimal string")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _fail("C8C9.W4.MONEY", f"{field} invalid decimal")
    if not d.is_finite() or d < 0:
        _fail("C8C9.W4.MONEY", f"{field} must be finite nonnegative")
    return d


def _schema_validator(filename: str) -> Draft202012Validator:
    cached = _SCHEMA_CACHE.get(filename)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().with_name(filename)
    if not path.is_file():
        _fail("C8C9.W4.SCHEMA_MISSING", f"required packaged schema missing: {filename}")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except Exception as exc:
        _fail("C8C9.W4.SCHEMA_INVALID", f"cannot load packaged schema {filename}: {exc}")
    _SCHEMA_CACHE[filename] = validator
    return validator


def _absence_contract():
    import importlib.util
    path=Path(__file__).resolve().parents[4]/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/funding_absence.py'
    spec=importlib.util.spec_from_file_location('c7_confirmed_absence_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _validate_schema(instance: Any, filename: str, code: str) -> None:
    validator=_schema_validator(filename);absence=_absence_contract()
    if absence.is_extended(instance):
        validator=Draft202012Validator(absence.extend_schema(validator.schema))
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        e = errors[0]
        path = "/" + "/".join(str(x) for x in e.absolute_path) if e.absolute_path else "/"
        _fail(code, f"schema rejection at {path}: {e.message}")


def _decimal_to_json_number(value: Decimal) -> int | float:
    if not value.is_finite():
        _fail("C8C9.W4.NON_JSON", "non-finite Decimal cannot be serialized")
    if value == value.to_integral_value():
        return int(value)
    candidate = float(value)
    if not math.isfinite(candidate) or Decimal(str(candidate)) != value:
        _fail("C8C9.W4.PRECISION_LOSS", f"Decimal {value} cannot be represented as a JSON number without value drift")
    return candidate


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Decimal):
        return _decimal_to_json_number(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and value.__class__.__module__ != "builtins":
        return _jsonable(value.value)
    return value


def _canonical_digest(value: Any) -> str:
    try:
        raw=json.dumps(_jsonable(value),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W4.NON_JSON", f"cannot provenance-hash context: {exc}")
    return sha256(raw).hexdigest()


def _owner_tuple(owner: Mapping[str, Any]) -> tuple[str,str,str]:
    domain=owner.get("funding_domain")
    if domain not in FORMAL_DOMAINS:
        _fail("C8C9.W4.OWNER", "owner funding_domain invalid")
    return (domain,_nonempty(owner.get("broker"),"owner.broker"),_nonempty(owner.get("account"),"owner.account"))


def _resolve_json_pointer(root: Any, pointer: str) -> Any:
    if pointer == "":
        return root
    if not isinstance(pointer,str) or not pointer.startswith("/"):
        _fail("C8C9.W4.TARGET_POINTER", "project_target_pointer must be an RFC6901-style absolute pointer")
    current=root
    for raw in pointer.split("/")[1:]:
        token=raw.replace("~1","/").replace("~0","~")
        if isinstance(current, Mapping):
            if token not in current:
                _fail("C8C9.W4.TARGET_POINTER", f"missing object token {token!r}")
            current=current[token]
        elif isinstance(current, list):
            try: idx=int(token)
            except ValueError: _fail("C8C9.W4.TARGET_POINTER", f"list token {token!r} is not an index")
            if idx < 0 or idx >= len(current):
                _fail("C8C9.W4.TARGET_POINTER", f"list index {idx} out of range")
            current=current[idx]
        else:
            _fail("C8C9.W4.TARGET_POINTER", f"cannot descend through scalar at {token!r}")
    return deepcopy(current)


def _validate_work3(w3: Mapping[str,Any], run_id: str) -> tuple[tuple[str,str,str], Mapping[str,Any]]:
    if w3.get("contract_name") != WORK3_CONTRACT_NAME or w3.get("contract_version") != WORK3_CONTRACT_VERSION:
        _fail("C8C9.W4.WORK3_CONTRACT", "Work3 contract/version mismatch")
    if w3.get("baseline_id") != BASELINE_ID or w3.get("work2_contract_version") != WORK2_CONTRACT_VERSION:
        _fail("C8C9.W4.BASELINE_OR_WORK2_VERSION", "frozen baseline/Work2 contract mismatch")
    if w3.get("run_id") != run_id:
        _fail("C8C9.W4.RUN_ID_MISMATCH", "Work3 run_id differs from Work4 run_id")
    owner=_owner_tuple(_mapping(w3.get("owner"),"work3_handoff.owner"))
    currency=_nonempty(w3.get("currency"),"work3_handoff.currency")
    if len(currency)!=3 or currency.upper()!=currency:
        _fail("C8C9.W4.CURRENCY", "Work3 currency must be uppercase 3-letter code")
    funding=_mapping(w3.get("funding_context"),"work3_handoff.funding_context")
    settlement=_mapping(funding.get("settlement"),"funding_context.settlement")
    if settlement.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W4.CASH_BASIS", "cash_basis must remain AVAILABLE")
    budgets=_mapping(funding.get("executable_budget"),"funding_context.executable_budget")
    equity=_mapping(budgets.get("equity"),"funding_context.executable_budget.equity")
    if equity.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W4.CASH_BASIS", "equity leg must remain AVAILABLE")
    if _owner_tuple(_mapping(equity.get("owner"),"equity.owner")) != owner:
        _fail("C8C9.W4.CROSS_OWNER_FUNDING", "Work3 equity owner differs from Work3 owner")
    if equity.get("currency") != currency:
        _fail("C8C9.W4.NO_FX_CURRENCY_MISMATCH", "Work3 equity currency differs from Work3 owner currency")
    _number(equity.get("amount"),"Work3 equity amount")
    bind=_mapping(_mapping(w3.get("engine_bindings"),"engine_bindings").get("v82"),"engine_bindings.v82")
    expected={
        "run_id":run_id,
        "executable_budget_pointer":"/funding_context/executable_budget/equity",
        "remaining_target_gap_pointer":"/funding_context/remaining_target_gap/v82",
        "final_target_pointer":"/final_target",
        "v70_original_dry_powder_executable":False,
        "sgov_bucket_access":"FORBIDDEN",
    }
    for k,v in expected.items():
        if bind.get(k) != v:
            _fail("C8C9.W4.WORK3_V82_BINDING", f"engine_bindings.v82.{k} drift")
    if _owner_tuple(_mapping(bind.get("owner"),"engine_bindings.v82.owner")) != owner:
        _fail("C8C9.W4.CROSS_OWNER_FUNDING", "V82 binding owner differs")
    final_target=_mapping(w3.get("final_target"),"final_target")
    allocation_id=_nonempty(final_target.get("allocation_id"),"final_target.allocation_id")
    if final_target.get("authorization_reference") != allocation_id or bind.get("authorization_reference") != allocation_id:
        _fail("C8C9.W4.AUTHORIZATION_REFERENCE", "authorization_reference must be exact confirmed C7 allocation_id")
    proof=_mapping(final_target.get("confirmation_proof"),"final_target.confirmation_proof")
    _nonempty(proof.get("confirmed_at"),"final_target.confirmation_proof.confirmed_at")
    _nonempty(proof.get("confirmed_by"),"final_target.confirmation_proof.confirmed_by")
    sgov=_mapping(funding.get("sgov_boundary"),"funding_context.sgov_boundary")
    if sgov.get("v82_undeployed_to_sgov") is not None or sgov.get("v82_raw_equity_budget_auto_route_forbidden") is not True or sgov.get("v82_access_forbidden") is not True:
        _fail("C8C9.W4.SGOV_BOUNDARY", "V82 SGOV fabrication/auto-route/access is forbidden")
    shared=_mapping(w3.get("shared_decision_context"),"shared_decision_context")
    if shared.get("run_id") != run_id:
        _fail("C8C9.W4.RUN_ID_MISMATCH", "shared context run_id mismatch")
    shared_id=_nonempty(shared.get("context_id"),"shared_decision_context.context_id")
    if shared.get("as_of") != _mapping(w3.get("temporal"),"temporal").get("as_of"):
        _fail("C8C9.W4.AS_OF_MISMATCH", "shared as_of differs from Work3 temporal.as_of")
    digest=_canonical_digest(shared)
    if bind.get("shared_context_id") != shared_id or bind.get("shared_context_digest_sha256") != digest:
        _fail("C8C9.W4.SHARED_CONTEXT_MISMATCH", "Work3 V82 binding does not match exact shared context id/digest")
    v70=_mapping(w3.get("v70_runtime_context"),"v70_runtime_context")
    if v70.get("run_id") != run_id:
        _fail("C8C9.W4.RUN_ID_MISMATCH", "V70 context run_id mismatch")
    v70_sid=_nonempty(v70.get("upstream_v70_snapshot_id"),"v70_runtime_context.upstream_v70_snapshot_id")
    if _mapping(w3.get("lineage"),"lineage").get("upstream_snapshot_ids",{}).get("v70") != v70_sid:
        _fail("C8C9.W4.V70_LINEAGE_MISMATCH", "V70 snapshot does not match Work3 lineage")
    return owner, bind


def _validate_c7_against_work3(c7: Mapping[str,Any], w3: Mapping[str,Any], owner: tuple[str,str,str], run_id:str) -> Mapping[str,Any]:
    if c7.get("contract_name") != C7_CONTRACT_NAME or c7.get("contract_version") not in (C7_CONTRACT_VERSION,_absence_contract().VERSION):
        _fail("C8C9.W4.C7_CONTRACT", "C7 FundingContext contract/version mismatch")
    if c7.get("run_id") != run_id:
        _fail("C8C9.W4.RUN_ID_MISMATCH", "C7 run_id mismatch")
    if c7.get("bank_cash_scope") != "OUT_OF_SCOPE":
        _fail("C8C9.W4.BANK_CASH_FORBIDDEN", "bank cash must remain OUT_OF_SCOPE")
    if c7.get("base_currency") != w3.get("currency"):
        _fail("C8C9.W4.NO_FX_CURRENCY_MISMATCH", "C7 base_currency must directly equal Work3 currency")
    contexts=c7.get("contexts")
    if not isinstance(contexts,list) or len(contexts)!=3:
        _fail("C8C9.W4.C7_DOMAIN_SET", "C7 FundingContext must retain exactly three contexts")
    domains=[]; selected=[]; bucket_sum=Decimal("0")
    seen_ba=set()
    for idx,ctx0 in enumerate(contexts):
        ctx=_mapping(ctx0,f"c7.contexts[{idx}]")
        ident=(ctx.get("domain"),ctx.get("broker"),ctx.get("account"))
        if ident[0] not in FORMAL_DOMAINS:
            _fail("C8C9.W4.C7_DOMAIN_SET", "invalid C7 domain")
        domains.append(ident[0])
        try:absent=_absence_contract().validate_absent(ctx,c7.get("contract_version"))
        except ValueError as error:_fail("C8C9.W4.ACCOUNT_ABSENCE",str(error))
        if absent:continue
        ba=(ident[1],ident[2])
        if ba in seen_ba: _fail("C8C9.W4.C7_DUPLICATE_ACCOUNT", "broker+account duplicated")
        seen_ba.add(ba)
        bucket_sum += _number(ctx.get("bucket_new_investment_amount"),f"c7.contexts[{idx}].bucket_new_investment_amount")
        cash=_mapping(ctx.get("brokerage_cash_state"),f"c7.contexts[{idx}].brokerage_cash_state")
        cash_d={k:_number(cash.get(k),f"c7.contexts[{idx}].cash.{k}") for k in ("total","available","unsettled","reserved")}
        if any(cash_d[k] > cash_d["total"] for k in ("available","unsettled","reserved")):
            _fail("C8C9.W4.C7_CASH_STATE", "cash substate exceeds total")
        budget=_mapping(ctx.get("executable_budget"),f"c7.contexts[{idx}].executable_budget")
        legs={}
        for leg_name in ("equity","bond"):
            leg=_mapping(budget.get(leg_name),f"c7.contexts[{idx}].{leg_name}")
            if leg.get("cash_basis") != "AVAILABLE": _fail("C8C9.W4.CASH_BASIS", f"C7 {leg_name} cash_basis not AVAILABLE")
            leg_owner=(leg.get("source_domain"),leg.get("source_broker"),leg.get("source_account"))
            if leg_owner != ident: _fail("C8C9.W4.CROSS_OWNER_FUNDING", f"C7 {leg_name} owner mismatch")
            legs[leg_name]=_number(leg.get("amount"),f"c7.contexts[{idx}].{leg_name}.amount")
        if legs["equity"]+legs["bond"] > cash_d["available"]:
            _fail("C8C9.W4.C7_BUDGET_EXCEEDS_AVAILABLE", "C7 equity+bond exceeds available")
        if legs["equity"]+legs["bond"] > _number(ctx.get("bucket_new_investment_amount"),"bucket"):
            _fail("C8C9.W4.C7_BUDGET_EXCEEDS_BUCKET", "C7 equity+bond exceeds account bucket")
        if ident == owner: selected.append(ctx)
    if set(domains)!=FORMAL_DOMAINS or len(set(domains))!=3:
        _fail("C8C9.W4.C7_DOMAIN_SET", "each formal C7 domain must appear exactly once")
    if bucket_sum != _number(c7.get("total_new_investment_amount"),"c7.total_new_investment_amount"):
        _fail("C8C9.W4.C7_TOTAL_MISMATCH", "C7 bucket total mismatch")
    if len(selected)!=1:
        _fail("C8C9.W4.EXECUTION_ACCOUNT_MATCH", "owner must match exactly one C7 context")
    sel=selected[0]
    w3fund=_mapping(w3.get("funding_context"),"funding_context")
    if deepcopy(sel.get("brokerage_cash_state")) != deepcopy(_mapping(w3fund.get("settlement"),"settlement").get("cash_state")):
        _fail("C8C9.W4.C7_WORK3_TAMPER", "selected C7 cash state differs from frozen Work3 owner context")
    for leg_name in ("equity","bond"):
        cleg=_mapping(_mapping(sel.get("executable_budget"),"selected budget").get(leg_name),f"selected.{leg_name}")
        wleg=_mapping(_mapping(w3fund.get("executable_budget"),"w3 budget").get(leg_name),f"w3.{leg_name}")
        if _number(cleg.get("amount"),"c7 leg") != _number(wleg.get("amount"),"w3 leg"):
            _fail("C8C9.W4.C7_WORK3_TAMPER", f"selected C7 {leg_name} amount differs from Work3")
        if wleg.get("currency") != c7.get("base_currency") or wleg.get("cash_basis") != cleg.get("cash_basis"):
            _fail("C8C9.W4.C7_WORK3_TAMPER", f"selected C7 {leg_name} basis/currency differs from Work3")
    return sel


def build_v82_runtime_input(request: Mapping[str,Any]) -> dict[str,Any]:
    req=_mapping(request,"request")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W4.CONTRACT", "Work4 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W4.BASELINE", "Frozen Baseline mismatch")
    run_id=_nonempty(req.get("run_id"),"run_id")
    w3=_mapping(req.get("work3_handoff"),"work3_handoff")
    owner,bind=_validate_work3(w3,run_id)
    c7=_mapping(req.get("c7_funding_context"),"c7_funding_context")
    selected=_validate_c7_against_work3(c7,w3,owner,run_id)
    asset_ctx=_mapping(req.get("asset_context"),"asset_context")
    asset=_mapping(asset_ctx.get("asset"),"asset_context.asset")
    asset_id=_nonempty(asset.get("asset_id"),"asset.asset_id")
    client_project_version=_nonempty(asset_ctx.get("client_project_version"),"asset_context.client_project_version")
    target_pointer=_nonempty(asset_ctx.get("project_target_pointer"),"asset_context.project_target_pointer")
    project_target=_resolve_json_pointer(_mapping(w3.get("final_target"),"final_target").get("payload"),target_pointer)
    confirmed=deepcopy(asset_ctx.get("confirmed_position_snapshot"))
    if confirmed is None:
        _fail("C8C9.W4.CONFIRMED_POSITION", "confirmed_position_snapshot may not be null")
    v70=_mapping(w3.get("v70_runtime_context"),"v70_runtime_context")
    vp=_mapping(v70.get("payload"),"v70_runtime_context.payload")
    for required in ("stock_tactical_amount","v70_original_dry_powder_amount","value_state","data_quality","issue_codes"):
        if required not in vp:
            _fail("C8C9.W4.V70_SOURCE_FIELD_MISSING", f"v70 payload missing {required}")
    issue_codes=vp.get("issue_codes")
    if not isinstance(issue_codes,list) or any(not isinstance(x,str) for x in issue_codes):
        _fail("C8C9.W4.V70_SOURCE_FIELD", "v70 issue_codes must be string array")
    shared=_mapping(w3.get("shared_decision_context"),"shared_decision_context")
    shared_digest=_canonical_digest(shared)
    shared_id=_nonempty(shared.get("context_id"),"shared_decision_context.context_id")
    if bind.get("shared_context_id")!=shared_id or bind.get("shared_context_digest_sha256")!=shared_digest:
        _fail("C8C9.W4.SHARED_CONTEXT_MISMATCH", "Work3 binding/shared context mismatch")
    # Runtime boundary is independently schema-validated inside the Adapter; callers
    # are not trusted to have run JSON Schema first. Semantic checks above remain
    # authoritative for precise cross-source diagnostics.
    _validate_schema(req, INPUT_SCHEMA_FILENAME, "C8C9.W4.INPUT_SCHEMA")
    shared_refs=shared.get("source_reference_ids")
    if not isinstance(shared_refs,list) or not shared_refs:
        _fail("C8C9.W4.SHARED_CONTEXT_LINEAGE", "shared source_reference_ids required")
    lineage=[]
    def add(x:str):
        if x and x not in lineage: lineage.append(x)
    for x in _mapping(w3.get("lineage"),"lineage").get("source_reference_ids",[]): add(x)
    for x in v70.get("source_reference_ids",[]): add(x)
    for x in shared_refs: add(x)
    add(f"C8C9.W3.CONTEXT_HANDOFF:{w3.get('context_handoff_id')}")
    add(f"C8C9.W3.SHARED_CONTEXT_ID:{shared_id}")
    add(f"C8C9.W3.SHARED_CONTEXT_SHA256:{shared_digest}")
    if not lineage: _fail("C8C9.W4.LINEAGE", "V82 source_lineage cannot be empty")
    market_bundle={
        "shared_context_id":shared_id,
        "shared_context_digest_sha256":shared_digest,
        "as_of":shared.get("as_of"),
        "payload":deepcopy(shared.get("payload")),
        "data_as_of":deepcopy(shared.get("data_as_of")),
        "source_reference_ids":deepcopy(shared_refs),
        "versions":deepcopy(shared.get("versions",{})),
    }
    final_target=_mapping(w3.get("final_target"),"final_target")
    v82_input={
        "contract_name":V82_INPUT_NAME,
        "contract_version":V82_INPUT_VERSION,
        "run_id":run_id,
        "client_project_version":client_project_version,
        "asset":deepcopy(asset),
        "execution_account":{"domain":owner[0],"broker":owner[1],"account":owner[2]},
        "client_target":{"project_target_position":project_target,"authorization_reference":final_target["allocation_id"]},
        "upstream_v70_snapshot":{
            "run_id":run_id,
            "upstream_v70_snapshot_id":v70["upstream_v70_snapshot_id"],
            "v70_stock_tactical_budget_amount":deepcopy(vp["stock_tactical_amount"]),
            "v70_stock_tactical_budget_currency":w3["currency"],
            "v70_stock_tactical_budget_status":deepcopy(vp["value_state"]),
            "v70_stock_tactical_budget_data_as_of":v70["snapshot_as_of"],
            "v70_original_dry_powder_amount":deepcopy(vp["v70_original_dry_powder_amount"]),
            "v70_original_dry_powder_currency":w3["currency"],
            "v70_budget_source_reference":deepcopy(v70.get("source_reference_ids")),
            "v70_budget_data_quality":deepcopy(vp["data_quality"]),
            "v70_budget_issue_codes":deepcopy(issue_codes),
        },
        "c7_funding_context":deepcopy(c7),
        "confirmed_position_snapshot":confirmed,
        "market_data_bundle":market_bundle,
        "event_context":deepcopy(asset_ctx.get("event_context")) if "event_context" in asset_ctx else None,
        "source_lineage":lineage,
    }
    eq=_mapping(_mapping(selected.get("executable_budget"),"selected.executable_budget").get("equity"),"selected.equity")
    binding={
        "run_id":run_id,
        "owner":{"funding_domain":owner[0],"broker":owner[1],"account":owner[2]},
        "currency":w3["currency"],
        "asset_id":asset_id,
        "work3_context_handoff_id":w3.get("context_handoff_id"),
        "upstream_v70_snapshot_id":v70["upstream_v70_snapshot_id"],
        "shared_context_id":shared_id,
        "shared_context_digest_sha256":shared_digest,
        "authorization_reference":final_target["allocation_id"],
        "equity_executable_budget":{"amount":deepcopy(eq["amount"]),"currency":w3["currency"],"cash_basis":"AVAILABLE","owner":{"funding_domain":owner[0],"broker":owner[1],"account":owner[2]},"source_pointer":"/funding_context/executable_budget/equity"},
        "v70_original_dry_powder_executable":False,
        "v82_undeployed_to_sgov_present":False,
    }
    return {"v82_runtime_input":v82_input,"integration_binding":binding}


def consume_v82_runtime_output(v82_output: Any, integration_binding: Mapping[str,Any]) -> dict[str,Any]:
    out=_mapping(_jsonable(v82_output),"v82_output")
    b=_mapping(integration_binding,"integration_binding")
    if out.get("contract_name") != V82_OUTPUT_NAME or out.get("contract_version") != V82_OUTPUT_VERSION:
        _fail("C8C9.W4.V82_OUTPUT_CONTRACT", "V82 output contract/version mismatch")
    if out.get("run_id") != b.get("run_id"):
        _fail("C8C9.W4.RUN_ID_MISMATCH", "V82 output run_id differs from binding")
    if out.get("asset_id") != b.get("asset_id"):
        _fail("C8C9.W4.ASSET_MISMATCH", "V82 output asset_id differs from binding")
    if out.get("upstream_v70_snapshot_id") != b.get("upstream_v70_snapshot_id"):
        _fail("C8C9.W4.V70_LINEAGE_MISMATCH", "V82 output V70 snapshot differs from binding")
    if out.get("rule_version") != V82_RULE_VERSION:
        _fail("C8C9.W4.V82_RULE_VERSION", "V82 output rule version drift")
    lineage=out.get("source_lineage")
    if not isinstance(lineage,list) or not lineage:
        _fail("C8C9.W4.V82_OUTPUT_LINEAGE", "V82 output source_lineage required")
    required_tokens={f"C8C9.W3.SHARED_CONTEXT_ID:{b.get('shared_context_id')}",f"C8C9.W3.SHARED_CONTEXT_SHA256:{b.get('shared_context_digest_sha256')}"}
    if not required_tokens.issubset(set(lineage)):
        _fail("C8C9.W4.SHARED_CONTEXT_MISMATCH", "V82 output lineage does not prove same Work3 shared context")
    ca=_mapping(out.get("canonical_analysis"),"v82_output.canonical_analysis")
    if tuple(ca.keys()) != CANONICAL_FIELD_NAMES:
        _fail("C8C9.W4.V82_CANONICAL_OUTPUT", "V82 canonical_analysis must preserve exact 49-field order/set")
    # Frozen V82 Python model stores the exact 13-field projection as an ordered
    # Mapping, while the frozen V82 JSON Output Schema uses a 13-entry wire array.
    # Work4 performs only this transport serialization; every value is preserved.
    out["fields_1_to_13"]=_normalize_formal_13(out.get("fields_1_to_13"))
    _verify_formal_13_projection(ca,out["fields_1_to_13"])
    # Explicit source-boundary guard: current Ready output has no such canonical field.
    def scan(value:Any):
        if isinstance(value,Mapping):
            for k,v in value.items():
                if str(k).upper()=="V82_UNDEPLOYED_TO_SGOV":
                    _fail("C8C9.W4.V82_SGOV_FABRICATION", "V82 output must not fabricate V82_UNDEPLOYED_TO_SGOV")
                scan(v)
        elif isinstance(value,list):
            for v in value: scan(v)
    scan(out)
    result={
        "contract_name":OUTPUT_CONTRACT_NAME,
        "contract_version":OUTPUT_CONTRACT_VERSION,
        "baseline_id":BASELINE_ID,
        "run_id":b["run_id"],
        "owner":deepcopy(b["owner"]),
        "currency":b["currency"],
        "asset_id":b["asset_id"],
        "work3_context_handoff_id":b["work3_context_handoff_id"],
        "upstream_v70_snapshot_id":b["upstream_v70_snapshot_id"],
        "shared_context_id":b["shared_context_id"],
        "shared_context_digest_sha256":b["shared_context_digest_sha256"],
        "authorization_reference":b["authorization_reference"],
        "consumed_equity_executable_budget":deepcopy(b["equity_executable_budget"]),
        "canonical_v82_output":deepcopy(out),
        "source_semantics_policy":"PRESERVE_V82_CANONICAL_OUTPUT_NO_LOSSY_TRANSLATION",
        "integration_diagnostics":[],
    }
    _validate_schema(result, OUTPUT_SCHEMA_FILENAME, "C8C9.W4.OUTPUT_SCHEMA")
    return result


__all__=[
    "BASELINE_ID","INPUT_CONTRACT_NAME","INPUT_CONTRACT_VERSION","OUTPUT_CONTRACT_NAME","OUTPUT_CONTRACT_VERSION",
    "V82IntegrationError","build_v82_runtime_input","consume_v82_runtime_output",
]
