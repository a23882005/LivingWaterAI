"""C8C9 Work9 - Unified Deployment Output + Mentor Return Contract.

This integration layer consumes already-canonical Work4/5/6/7/8 results and
returns one canonical deployment envelope for Mentor explanation.

It performs *normalization only*.  It must not recompute V82/V75 investment
logic, Final Target, Drift, Funding, SGOV aggregation, FX, or client preference.
All source-owned decisions are retained explicitly so Mentor can explain them
without silently turning UNKNOWN into false/zero/neutral or a risk warning into
an allocation instruction.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping
from decimal import Decimal, InvalidOperation

from jsonschema import Draft202012Validator

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work9.UnifiedDeploymentInput"
INPUT_CONTRACT_VERSION = "C8C9-W9-UDI-v1.0.0"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work9.CanonicalDeploymentResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W9-CDR-v1.0.0"
MENTOR_RETURN_CONTRACT_NAME = "LivingWaterAI.C8C9.Work9.MentorReturn"
MENTOR_RETURN_CONTRACT_VERSION = "C8C9-W9-MR-v1.0.0"

WORK4_NAME = "LivingWaterAI.C8C9.Work4.V82IntegrationResult"
WORK4_VERSION = "C8C9-W4-V82AO-v1.0.0"
WORK5_NAME = "LivingWaterAI.C8C9.Work5.V75IntegrationResult"
WORK5_VERSION = "C8C9-W5-V75AO-v1.0.1-RECHECK1"
WORK6_NAME = "LivingWaterAI.C8C9.Work6.FundingAccountIsolationResult"
WORK6_VERSION = "C8C9-W6-FAIO-v1.0.0"
WORK7_NAME = "LivingWaterAI.C8C9.Work7.SGOVRuntimeRoleResult"
WORK7_VERSION = "C8C9-W7-SGOVO-v1.0.0"
WORK8_NAME = "LivingWaterAI.C8C9.Work8.ProtectedHoldingProtectionResult"
WORK8_VERSION = "C8C9-W8-PHPO-v1.0.1"

FORMAL_DOMAINS = {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}
CANONICAL_ACTIONS = {
    "BUY", "WAIT", "HOLD", "PAUSE", "NO_ACTION", "BLOCK", "UNKNOWN", "NEEDS_REVIEW"
}

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "WORK9_OUTPUT"
_INPUT_SCHEMA = _OUT / "C8C9_Work9_Unified_Deployment_Input.schema_2026-09-28_0342.json"
_OUTPUT_SCHEMA = _OUT / "C8C9_Work9_Canonical_Deployment_Result.schema_2026-09-28_0342.json"
_WORK4_SCHEMA = _OUT / "C8C9_Work9_Frozen_Work4_V82_Integration_Output.schema_2026-09-28_0342.json"
_WORK5_SCHEMA = _OUT / "C8C9_Work9_Frozen_Work5_V75_Integration_Output.schema_2026-09-28_0342.json"
_WORK6_SCHEMA = _OUT / "C8C9_Work9_Frozen_Work6_Funding_Account_Isolation_Output.schema_2026-09-28_0342.json"
_WORK7_SCHEMA = _OUT / "C8C9_Work9_Frozen_Work7_SGOV_Runtime_Role_Output.schema_2026-09-28_0342.json"
_WORK8_SCHEMA = _OUT / "C8C9_Work9_Frozen_Work8_Protected_Holding_Output.schema_2026-09-28_0342.json"


class UnifiedDeploymentError(ValueError):
    """Fail-closed Work9 integration error."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise UnifiedDeploymentError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("C8C9.W9.SHAPE", f"{field} must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("C8C9.W9.SHAPE", f"{field} must be a non-empty string")
    return value


def _canon(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W9.NON_JSON", f"value is not canonical JSON serializable: {exc}")


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
        _fail("C8C9.W9.SCHEMA_LOAD", f"cannot load {path.name}: {exc}")


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
    owner = _mapping(value, field)
    domain = _nonempty(owner.get("funding_domain"), field + ".funding_domain")
    broker = _nonempty(owner.get("broker"), field + ".broker")
    account = _nonempty(owner.get("account"), field + ".account")
    if domain not in FORMAL_DOMAINS:
        _fail("C8C9.W9.OWNER", f"{field}.funding_domain invalid")
    return domain, broker, account


def _owner_obj(owner: tuple[str, str, str]) -> dict[str, str]:
    return {"funding_domain": owner[0], "broker": owner[1], "account": owner[2]}


def _number_text(value: Any, field: str) -> str:
    if isinstance(value, bool):
        _fail("C8C9.W9.NUMERIC", f"{field} cannot be boolean")
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        text = str(value).strip()
        if not text:
            _fail("C8C9.W9.NUMERIC", f"{field} must be nonnegative numeric")
        try:
            dec = Decimal(text)
        except (InvalidOperation, ValueError):
            _fail("C8C9.W9.NUMERIC", f"{field} must be nonnegative numeric")
        if not dec.is_finite() or dec < 0:
            _fail("C8C9.W9.NUMERIC", f"{field} must be finite and nonnegative")
        return text
    _fail("C8C9.W9.NUMERIC", f"{field} must be numeric")


def _canonical_v82_value(v82: Mapping[str, Any], name: str) -> Any:
    canonical = _mapping(v82.get("canonical_analysis"), "canonical_v82_output.canonical_analysis")
    env = _mapping(canonical.get(name), f"canonical_v82_output.canonical_analysis.{name}")
    if env.get("field_name") != name or "value" not in env:
        _fail("C8C9.W9.V82_FIELD", f"canonical V82 field envelope invalid: {name}")
    return deepcopy(env.get("value"))


def _v82_issue_codes(v82: Mapping[str, Any]) -> list[str]:
    canonical = _mapping(v82.get("canonical_analysis"), "canonical_v82_output.canonical_analysis")
    out: list[str] = []
    for name, env in canonical.items():
        obj = _mapping(env, f"canonical_v82_output.canonical_analysis.{name}")
        codes = obj.get("issue_codes")
        if not isinstance(codes, list) or any(not isinstance(x, str) for x in codes):
            _fail("C8C9.W9.V82_FIELD", f"invalid issue_codes in {name}")
        for code in codes:
            if code not in out:
                out.append(code)
    return out


def _money_slot_from_v82(value: Any) -> dict[str, Any]:
    if value == "UNKNOWN":
        return {"status": "UNKNOWN", "value": None}
    if value is None:
        return {"status": "NOT_APPLICABLE", "value": None}
    money = _mapping(value, "v82.execution_amount")
    amount = money.get("amount")
    currency = _nonempty(money.get("currency"), "v82.execution_amount.currency")
    _number_text(amount, "v82.execution_amount.amount")
    return {"status": "KNOWN", "value": {"amount": deepcopy(amount), "currency": currency}}


def _percent_slot_from_v82(value: Any) -> dict[str, Any]:
    if value == "UNKNOWN":
        return {"status": "UNKNOWN", "value": None}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("C8C9.W9.V82_FIELD", "canonical_deployment_target_rate must be numeric or UNKNOWN")
    if value < 0 or value > 100:
        _fail("C8C9.W9.V82_FIELD", "canonical_deployment_target_rate outside 0..100")
    return {"status": "KNOWN", "value": {"value": value, "unit": "PERCENT"}}


def _money_slot_from_v75(value: Any) -> dict[str, Any]:
    if value is None:
        return {"status": "NOT_APPLICABLE", "value": None}
    money = _mapping(value, "v75.deploy_amount")
    amount = money.get("amount")
    currency = _nonempty(money.get("currency"), "v75.deploy_amount.currency")
    _number_text(amount, "v75.deploy_amount.amount")
    return {"status": "KNOWN", "value": {"amount": deepcopy(amount), "currency": currency}}


def _percent_slot_from_v75(value: Any) -> dict[str, Any]:
    if value is None:
        return {"status": "NOT_APPLICABLE", "value": None}
    obj = _mapping(value, "v75.deployment_pct")
    val = obj.get("value")
    if isinstance(val, bool) or not isinstance(val, (int, float, str)):
        _fail("C8C9.W9.V75_FIELD", "deployment_pct.value invalid")
    try:
        fv = float(val)
    except Exception:
        _fail("C8C9.W9.V75_FIELD", "deployment_pct.value not numeric")
    if fv < 0 or fv > 100:
        _fail("C8C9.W9.V75_FIELD", "deployment_pct outside 0..100")
    return {"status": "KNOWN", "value": {"value": deepcopy(val), "unit": obj.get("unit", "PERCENT")}}


def _normalize_v82_action(raw_action: Any, protected: bool) -> tuple[str, list[str]]:
    # Protected client-facing action is source-owned by C Work6/7 and was validated
    # in Work8. The V82 raw risk action is retained separately, not overwritten.
    if protected:
        return "HOLD", ["C8C9_W9_PROTECTED_CLIENT_ACTION_FROM_C_WORK6_7"]
    if not isinstance(raw_action, str) or not raw_action:
        return "UNKNOWN", ["C8C9_W9_V82_ACTION_NOT_STRING"]
    mapping = {
        "BUY": "BUY",
        "NO_NEW_BUY": "NO_ACTION",
        "BLOCKED_UNKNOWN": "BLOCK",
        "WAIT": "WAIT",
        "HOLD": "HOLD",
        "PAUSE": "PAUSE",
        "NO_ACTION": "NO_ACTION",
        "BLOCK": "BLOCK",
        "UNKNOWN": "UNKNOWN",
        "NEEDS_REVIEW": "NEEDS_REVIEW",
    }
    if raw_action in mapping:
        return mapping[raw_action], []
    # Never invent a sell/reduce translation. Preserve the exact source action
    # and escalate the Mentor-facing normalized state to review.
    return "NEEDS_REVIEW", ["C8C9_W9_UNMAPPED_V82_SOURCE_ACTION_REVIEW"]


def _normalize_v75_action(decision: Mapping[str, Any]) -> tuple[str, list[str]]:
    eval_state = decision.get("evaluation_state")
    gate_state = decision.get("gate_state")
    new_action = decision.get("new_money_action")
    existing_action = decision.get("existing_position_action")
    deploy_state = decision.get("deployment_state")

    if eval_state == "INVALID_INPUT":
        return "BLOCK", ["C8C9_W9_V75_INVALID_INPUT"]
    if eval_state == "INSUFFICIENT_DATA":
        return "UNKNOWN", ["C8C9_W9_V75_INSUFFICIENT_DATA"]
    if eval_state == "REVIEW_REQUIRED":
        return "NEEDS_REVIEW", ["C8C9_W9_V75_REVIEW_REQUIRED"]
    if gate_state == "HARD_WAIT" or deploy_state == "HARD_WAIT" or new_action == "WAIT":
        return "WAIT", []
    if gate_state == "RESTRICT":
        return "NEEDS_REVIEW", ["C8C9_W9_V75_RESTRICT_REVIEW"]
    if new_action == "PAUSE" or deploy_state == "PAUSE":
        return "PAUSE", []
    if new_action in {"SMALL_BUY", "LEFT_BUY", "DEEP_LEFT_BUY", "RIGHT_COMPLETE"} or deploy_state in {"SMALL_BUY", "LEFT_BUY", "DEEP_LEFT_BUY", "RIGHT_COMPLETE"}:
        return "BUY", []
    if new_action in {None, "NOT_APPLICABLE"}:
        if existing_action == "HOLD":
            return "HOLD", []
        if existing_action in {"REBOUND_SMALL_SELL", "TECHNICAL_TRIM", "TRUE_RISK_REDUCTION"}:
            return "NEEDS_REVIEW", ["C8C9_W9_V75_EXISTING_POSITION_REDUCTION_REVIEW"]
        if existing_action in {None, "NOT_APPLICABLE"}:
            return "NO_ACTION", []
    # Exact raw fields stay in source_decision. Unknown combination is never guessed.
    return "NEEDS_REVIEW", ["C8C9_W9_UNMAPPED_V75_SOURCE_ACTION_REVIEW"]


def _normalize_v75_envelope_action(v75: Mapping[str, Any], ready: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    """Normalize only source-owned top-level readiness/completeness facts.

    None means the envelope is fully runtime-eligible and per-asset decisions are
    sufficient. Any returned action is an account-scope guard/status, not a new
    investment decision.
    """
    eval_state = v75.get("evaluation_state")
    ready_eval = ready.get("evaluation_state")
    classification = ready.get("final_classification")
    gate_state = ready.get("gate_state")
    runtime_ready = ready.get("runtime_ready")
    cutover_state = ready.get("cutover_state")
    formal_eligible = v75.get("formal_output_eligible")

    states = {eval_state, ready_eval}
    if "INVALID_INPUT" in states:
        return "BLOCK", ["C8C9_W9_V75_ENVELOPE_INVALID_INPUT"]
    if "INSUFFICIENT_DATA" in states or classification == "INSUFFICIENT_DATA":
        return "UNKNOWN", ["C8C9_W9_V75_ENVELOPE_INSUFFICIENT_DATA"]
    if "REVIEW_REQUIRED" in states or classification in {"REVIEW_REQUIRED", "EXISTING_POSITION_REVIEW"}:
        return "NEEDS_REVIEW", ["C8C9_W9_V75_ENVELOPE_REVIEW_REQUIRED"]
    if gate_state == "HARD_WAIT" or classification == "HARD_WAIT":
        return "WAIT", ["C8C9_W9_V75_ENVELOPE_HARD_WAIT"]
    if runtime_ready is not True or cutover_state != "READY" or formal_eligible is not True:
        return "BLOCK", ["C8C9_W9_V75_ENVELOPE_NOT_RUNTIME_ELIGIBLE"]
    return None, []


def _require_empty_diagnostics(obj: Mapping[str, Any], label: str) -> None:
    d = obj.get("integration_diagnostics")
    if d != []:
        _fail("C8C9.W9.UPSTREAM_DIAGNOSTICS", f"{label}.integration_diagnostics must be empty")


def build_unified_deployment(req: Mapping[str, Any]) -> dict[str, Any]:
    """Build the Work9 canonical deployment result without recomputing source logic."""
    _schema(req, _INPUT_SCHEMA, "C8C9.W9.INPUT_SCHEMA")
    if req.get("contract_name") != INPUT_CONTRACT_NAME or req.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W9.INPUT_CONTRACT", "Work9 input contract/version mismatch")
    if req.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W9.BASELINE", "baseline_id mismatch")
    run_id = _nonempty(req.get("run_id"), "run_id")

    w4 = _mapping(req.get("work4_v82_integration_result"), "work4_v82_integration_result")
    w5 = _mapping(req.get("work5_v75_integration_result"), "work5_v75_integration_result")
    w6 = _mapping(req.get("work6_funding_account_isolation_result"), "work6_funding_account_isolation_result")
    w7 = _mapping(req.get("work7_sgov_runtime_role_result"), "work7_sgov_runtime_role_result")
    w8 = _mapping(req.get("work8_protected_holding_result"), "work8_protected_holding_result")

    for obj, schema, label in [
        (w4, _WORK4_SCHEMA, "WORK4"), (w5, _WORK5_SCHEMA, "WORK5"),
        (w6, _WORK6_SCHEMA, "WORK6"), (w7, _WORK7_SCHEMA, "WORK7"),
        (w8, _WORK8_SCHEMA, "WORK8"),
    ]:
        _schema(obj, schema, f"C8C9.W9.{label}_SCHEMA")
        if obj.get("baseline_id") != BASELINE_ID or obj.get("run_id") != run_id:
            _fail("C8C9.W9.RUN_OR_BASELINE", f"{label} run/baseline mismatch")
        _require_empty_diagnostics(obj, label)

    contracts = [
        (w4, WORK4_NAME, WORK4_VERSION, "WORK4"),
        (w5, WORK5_NAME, WORK5_VERSION, "WORK5"),
        (w6, WORK6_NAME, WORK6_VERSION, "WORK6"),
        (w7, WORK7_NAME, WORK7_VERSION, "WORK7"),
        (w8, WORK8_NAME, WORK8_VERSION, "WORK8"),
    ]
    for obj, name, version, label in contracts:
        if obj.get("contract_name") != name or obj.get("contract_version") != version:
            _fail("C8C9.W9.UPSTREAM_CONTRACT", f"{label} contract/version mismatch")

    owner = _owner_tuple(w6.get("owner"), "work6.owner")
    currency = _nonempty(w6.get("currency"), "work6.currency")
    if len(currency) != 3 or currency.upper() != currency:
        _fail("C8C9.W9.CURRENCY", "currency must be uppercase ISO-like 3-letter code")
    for label, obj in [("WORK4", w4), ("WORK5", w5), ("WORK7", w7)]:
        if _owner_tuple(obj.get("owner"), f"{label}.owner") != owner or obj.get("currency") != currency:
            _fail("C8C9.W9.OWNER_MISMATCH", f"{label} owner/currency differs from Work6 canonical owner")

    handoff = _nonempty(w6.get("work3_context_handoff_id"), "work6.work3_context_handoff_id")
    for label, obj in [("WORK4", w4), ("WORK5", w5), ("WORK7", w7)]:
        if obj.get("work3_context_handoff_id") != handoff:
            _fail("C8C9.W9.WORK3_LINEAGE", f"{label} Work3 handoff mismatch")
    for field in ("upstream_v70_snapshot_id", "shared_context_id", "shared_context_digest_sha256"):
        if w4.get(field) != w5.get(field):
            _fail("C8C9.W9.SHARED_CONTEXT_LINEAGE", f"Work4/Work5 {field} mismatch")

    # Exact upstream serialized binding.
    if w8.get("asset_id") != w4.get("asset_id"):
        _fail("C8C9.W9.V82_ASSET_BINDING", "Work8 asset differs from Work4 asset")
    sb = _mapping(w8.get("source_binding"), "work8.source_binding")
    if sb.get("work4_context_handoff_id") != handoff:
        _fail("C8C9.W9.WORK3_LINEAGE", "Work8 Work4 context handoff differs")
    if sb.get("final_target_allocation_id") != w4.get("authorization_reference"):
        _fail("C8C9.W9.FINAL_TARGET_BINDING", "Work8 Final Target allocation differs from Work4 authorization reference")
    if sb.get("work4_v82_integration_sha256") != _digest(w4):
        _fail("C8C9.W9.WORK8_WORK4_BINDING", "Work8 does not bind exact Work4 result")
    if sb.get("canonical_v82_output_sha256") != _digest(w4.get("canonical_v82_output")):
        _fail("C8C9.W9.WORK8_V82_BINDING", "Work8 V82 digest differs from Work4 canonical V82")
    if _canon(w8.get("canonical_v82_output")) != _canon(w4.get("canonical_v82_output")):
        _fail("C8C9.W9.WORK8_V82_BINDING", "Work8 canonical V82 output differs from Work4 canonical V82")

    source_digests = _mapping(w7.get("source_digests"), "work7.source_digests")
    if source_digests.get("work5_v75_integration_sha256") != _digest(w5):
        _fail("C8C9.W9.WORK7_WORK5_BINDING", "Work7 does not bind exact Work5 result")
    if source_digests.get("work6_funding_isolation_sha256") != _digest(w6):
        _fail("C8C9.W9.WORK7_WORK6_BINDING", "Work7 does not bind exact Work6 result")

    # Funding amounts are compared only; they are not recomputed.
    cash = _mapping(w6.get("cash_eligibility"), "work6.cash_eligibility")
    if cash.get("cash_basis") != "AVAILABLE" or cash.get("unsettled_reserved_consumed") is not False or cash.get("available_formula_inferred") is not False:
        _fail("C8C9.W9.FUNDING_SAFETY", "Work6 cash eligibility boundary drift")
    w4_eq = _mapping(w4.get("consumed_equity_executable_budget"), "work4.consumed_equity_executable_budget")
    w5_bond = _mapping(w5.get("consumed_bond_executable_budget"), "work5.consumed_bond_executable_budget")
    w4_eq_num = Decimal(_number_text(w4_eq.get("amount"), "work4.equity.amount"))
    w6_eq_num = Decimal(_number_text(cash.get("equity_executable_budget"), "work6.equity_executable_budget"))
    if w4_eq_num != w6_eq_num:
        _fail("C8C9.W9.FUNDING_BINDING", "Work4 equity budget differs from Work6 isolated equity budget")
    w5_bond_num = Decimal(_number_text(w5_bond.get("amount"), "work5.bond.amount"))
    w6_bond_num = Decimal(_number_text(cash.get("bond_executable_budget"), "work6.bond_executable_budget"))
    if w5_bond_num != w6_bond_num:
        _fail("C8C9.W9.FUNDING_BINDING", "Work5 bond budget differs from Work6 isolated bond budget")
    if _owner_tuple(w4_eq.get("owner"), "work4.equity.owner") != owner or _owner_tuple(w5_bond.get("owner"), "work5.bond.owner") != owner:
        _fail("C8C9.W9.FUNDING_BINDING", "executable budget owner mismatch")
    if w4_eq.get("cash_basis") != "AVAILABLE" or w5_bond.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W9.FUNDING_BINDING", "only AVAILABLE executable budgets may be normalized")

    # V75 Ready snapshot must carry the exact canonical output.
    v75 = _mapping(w5.get("canonical_v75_output"), "work5.canonical_v75_output")
    ready = _mapping(w5.get("canonical_v75_runtime_ready_snapshot"), "work5.canonical_v75_runtime_ready_snapshot")
    if _canon(ready.get("output")) != _canon(v75):
        _fail("C8C9.W9.V75_READY_BINDING", "Work5 Ready snapshot.output differs from canonical_v75_output")
    if v75.get("run_id") != run_id or v75.get("broker_account_id") != owner[2] or v75.get("broker_domain_type") != owner[0] or v75.get("currency") != currency:
        _fail("C8C9.W9.V75_IDENTITY", "canonical V75 run/account/domain/currency mismatch")

    # Work7 undeployed disposition must be exact Frozen V75 contribution.
    sgov_roles = _mapping(w7.get("sgov_roles"), "work7.sgov_roles")
    contribution = _mapping(sgov_roles.get("v75_undeployed_to_sgov"), "work7.sgov_roles.v75_undeployed_to_sgov")
    if _canon(contribution.get("contribution")) != _canon(v75.get("v75_undeployed_to_sgov")):
        _fail("C8C9.W9.UNDEPLOYED_BINDING", "Work7 undeployed contribution differs from canonical V75 output")
    route_safety = _mapping(w7.get("route_safety"), "work7.route_safety")
    required_true = [
        "roles_kept_separate", "same_us_broker_account_guard_enforced",
        "v82_equity_budget_auto_route_forbidden", "idle_usd_auto_route_forbidden",
        "reserved_cash_auto_route_forbidden", "unsettled_cash_auto_route_forbidden",
        "same_run_double_count_forbidden",
    ]
    if any(route_safety.get(k) is not True for k in required_true) or route_safety.get("final_dry_powder_aggregate_computed") is not False or route_safety.get("family_physical_subledger_created") is not False:
        _fail("C8C9.W9.SGOV_SAFETY", "Work7 SGOV safety assertions drifted")

    # Re-bind serialized evidence that is presentation-facing in Work7/Work5.
    funding_evidence = _mapping(w7.get("funding_evidence"), "work7.funding_evidence")
    for key in ("equity_executable_budget", "bond_executable_budget", "unsettled", "reserved"):
        if Decimal(_number_text(funding_evidence.get(key), f"work7.funding_evidence.{key}")) != Decimal(_number_text(cash.get(key), f"work6.cash_eligibility.{key}")):
            _fail("C8C9.W9.WORK7_FUNDING_EVIDENCE", f"Work7 funding evidence {key} differs from Work6")
    if funding_evidence.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W9.WORK7_FUNDING_EVIDENCE", "Work7 funding evidence cash_basis drift")
    w5_sgov = _mapping(w5.get("sgov_semantics"), "work5.sgov_semantics")
    if _canon(w5_sgov.get("v75_undeployed_to_sgov")) != _canon(v75.get("v75_undeployed_to_sgov")):
        _fail("C8C9.W9.UNDEPLOYED_BINDING", "Work5 SGOV semantics differs from canonical V75 undeployed contribution")
    contribution_amt = contribution.get("contribution")
    expected_evidence = None if contribution_amt is None else _number_text(_mapping(contribution_amt, "work7.contribution").get("amount"), "work7.contribution.amount")
    observed_evidence = funding_evidence.get("v75_undeployed_contribution")
    if expected_evidence is None:
        if observed_evidence is not None:
            _fail("C8C9.W9.WORK7_FUNDING_EVIDENCE", "Work7 undeployed evidence should be null")
    else:
        if observed_evidence is None or Decimal(_number_text(observed_evidence, "work7.funding_evidence.v75_undeployed_contribution")) != Decimal(expected_evidence):
            _fail("C8C9.W9.WORK7_FUNDING_EVIDENCE", "Work7 undeployed evidence differs from Work7 contribution")

    # ---- Normalize V82 source facts ----
    v82 = _mapping(w4.get("canonical_v82_output"), "work4.canonical_v82_output")
    raw_v82_action = _canonical_v82_value(v82, "execution_action")
    protected_obj = _mapping(w8.get("protected_holding"), "work8.protected_holding")
    protection_applied = protected_obj.get("protection_applied") is True
    normalized_v82_action, v82_norm_reasons = _normalize_v82_action(raw_v82_action, protection_applied)
    if normalized_v82_action not in CANONICAL_ACTIONS:
        _fail("C8C9.W9.INTERNAL", "invalid normalized V82 action")
    v82_reasons = _v82_issue_codes(v82)
    for code in v82_norm_reasons:
        if code not in v82_reasons:
            v82_reasons.append(code)
    v82_amount = _money_slot_from_v82(_canonical_v82_value(v82, "execution_amount"))
    v82_ratio = _percent_slot_from_v82(_canonical_v82_value(v82, "canonical_deployment_target_rate"))
    v82_item_id = f"V82:{w4['asset_id']}"
    v82_item = {
        "item_id": v82_item_id,
        "source_engine": "V82",
        "asset_id": w4["asset_id"],
        "canonical_action": normalized_v82_action,
        "source_action": deepcopy(raw_v82_action),
        "client_preference_action": deepcopy(_mapping(w8.get("client_action_protection"), "work8.client_action_protection").get("client_facing_action")),
        "deployment_amount": v82_amount,
        "deployment_ratio": v82_ratio,
        "account_owner": _owner_obj(owner),
        "funding_source": {
            "budget_type": "EQUITY_EXECUTABLE_BUDGET",
            "cash_basis": "AVAILABLE",
            "amount": deepcopy(w4_eq.get("amount")),
            "currency": currency,
            "source_pointer": w4_eq.get("source_pointer"),
        },
        "reason_codes": v82_reasons,
        "data_lineage": deepcopy(v82.get("source_lineage", [])),
        "rule_lineage": [
            f"V82_RULE:{v82.get('rule_version')}",
            f"WORK4_CONTRACT:{w4.get('contract_version')}",
            f"WORK8_CONTRACT:{w8.get('contract_version')}",
        ],
        "source_snapshot_digest_sha256": _digest(v82),
        "source_decision": {
            "raw_execution_action": deepcopy(raw_v82_action),
            "order_submission_plan": _canonical_v82_value(v82, "order_submission_plan"),
            "cancel_conditions": _canonical_v82_value(v82, "cancel_conditions"),
            "reevaluation_conditions": _canonical_v82_value(v82, "reevaluation_conditions"),
            "protected_holding": deepcopy(protected_obj),
            "risk_signal_visibility": deepcopy(w8.get("v82_signal_visibility")),
        },
    }

    # ---- Normalize V75 source facts ----
    items = [v82_item]
    per_asset = v75.get("per_asset_decisions", [])
    if not isinstance(per_asset, list):
        _fail("C8C9.W9.V75_FIELD", "per_asset_decisions must be an array")
    envelope_action, envelope_reasons = _normalize_v75_envelope_action(v75, ready)
    if envelope_action is not None or not per_asset:
        if envelope_action is None:
            envelope_action, envelope_reasons = "NO_ACTION", ["C8C9_W9_V75_NO_PER_ASSET_DECISIONS"]
        top_reasons = v75.get("reason_codes", []) or []
        blocking = ready.get("blocking_reason_codes", []) or []
        if not isinstance(top_reasons, list) or any(not isinstance(x, str) for x in top_reasons):
            _fail("C8C9.W9.V75_FIELD", "V75 top-level reason_codes invalid")
        if not isinstance(blocking, list) or any(not isinstance(x, str) for x in blocking):
            _fail("C8C9.W9.V75_FIELD", "V75 blocking_reason_codes invalid")
        top_lineage = v75.get("source_lineage", []) or []
        ready_lineage = ready.get("source_lineage", []) or []
        if not isinstance(top_lineage, list) or not isinstance(ready_lineage, list) or any(not isinstance(x, str) for x in [*top_lineage, *ready_lineage]):
            _fail("C8C9.W9.V75_FIELD", "V75 envelope source_lineage invalid")
        items.append({
            "item_id": "V75:__ACCOUNT_SCOPE__",
            "source_engine": "V75",
            "asset_id": "__ACCOUNT_SCOPE__",
            "canonical_action": envelope_action,
            "source_action": {
                "runtime_ready": deepcopy(ready.get("runtime_ready")),
                "cutover_state": deepcopy(ready.get("cutover_state")),
                "gate_state": deepcopy(ready.get("gate_state")),
                "evaluation_state": deepcopy(ready.get("evaluation_state")),
                "final_classification": deepcopy(ready.get("final_classification")),
                "formal_output_eligible": deepcopy(v75.get("formal_output_eligible")),
            },
            "client_preference_action": None,
            "deployment_amount": {"status": "NOT_APPLICABLE", "value": None},
            "deployment_ratio": {"status": "NOT_APPLICABLE", "value": None},
            "account_owner": _owner_obj(owner),
            "funding_source": {
                "budget_type": "BOND_EXECUTABLE_BUDGET",
                "cash_basis": "AVAILABLE",
                "amount": deepcopy(w5_bond.get("amount")),
                "currency": currency,
                "source_pointer": w5_bond.get("source_pointer"),
            },
            "reason_codes": list(dict.fromkeys([*top_reasons, *blocking, *envelope_reasons])),
            "data_lineage": list(dict.fromkeys([*top_lineage, *ready_lineage])),
            "rule_lineage": [
                f"V75_RULE:{v75.get('rule_version')}",
                f"V75_PREDICATE:{v75.get('predicate_version')}",
                f"V75_DEPLOYMENT_PARAMETER:{v75.get('deployment_parameter_version')}",
                f"WORK5_CONTRACT:{w5.get('contract_version')}",
            ],
            "source_snapshot_digest_sha256": _digest({"canonical_v75_output": v75, "runtime_ready_snapshot": ready}),
            "source_decision": {"canonical_v75_output": deepcopy(v75), "runtime_ready_snapshot": deepcopy(ready)},
        })
    for decision_raw in per_asset:
        decision = _mapping(decision_raw, "v75.per_asset_decision")
        asset_id = _nonempty(decision.get("asset_id"), "v75.per_asset_decision.asset_id")
        # Same asset id across engines is allowed only as two distinct source-engine items,
        # but duplicate within V75 would be ambiguous and is rejected.
        if f"V75:{asset_id}" in {x["item_id"] for x in items}:
            _fail("C8C9.W9.DUPLICATE_ITEM", f"duplicate V75 asset {asset_id}")
        action, extra_reasons = _normalize_v75_action(decision)
        if action not in CANONICAL_ACTIONS:
            _fail("C8C9.W9.INTERNAL", "invalid normalized V75 action")
        reasons = decision.get("reason_codes", [])
        if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons):
            _fail("C8C9.W9.V75_FIELD", f"reason_codes invalid for {asset_id}")
        reasons = list(dict.fromkeys([*reasons, *extra_reasons]))
        src_lineage = decision.get("source_lineage", [])
        if not isinstance(src_lineage, list) or any(not isinstance(x, str) for x in src_lineage):
            _fail("C8C9.W9.V75_FIELD", f"source_lineage invalid for {asset_id}")
        combined_lineage = list(dict.fromkeys([*src_lineage, *(v75.get("source_lineage", []) or [])]))
        items.append({
            "item_id": f"V75:{asset_id}",
            "source_engine": "V75",
            "asset_id": asset_id,
            "canonical_action": action,
            "source_action": {
                "deployment_state": deepcopy(decision.get("deployment_state")),
                "new_money_action": deepcopy(decision.get("new_money_action")),
                "existing_position_action": deepcopy(decision.get("existing_position_action")),
                "gate_state": deepcopy(decision.get("gate_state")),
                "evaluation_state": deepcopy(decision.get("evaluation_state")),
            },
            "client_preference_action": None,
            "deployment_amount": _money_slot_from_v75(decision.get("deploy_amount")),
            "deployment_ratio": _percent_slot_from_v75(decision.get("deployment_pct")),
            "account_owner": _owner_obj(owner),
            "funding_source": {
                "budget_type": "BOND_EXECUTABLE_BUDGET",
                "cash_basis": "AVAILABLE",
                "amount": deepcopy(w5_bond.get("amount")),
                "currency": currency,
                "source_pointer": w5_bond.get("source_pointer"),
            },
            "reason_codes": reasons,
            "data_lineage": combined_lineage,
            "rule_lineage": [
                f"V75_RULE:{v75.get('rule_version')}",
                f"V75_PREDICATE:{v75.get('predicate_version')}",
                f"V75_DEPLOYMENT_PARAMETER:{v75.get('deployment_parameter_version')}",
                f"WORK5_CONTRACT:{w5.get('contract_version')}",
            ],
            "source_snapshot_digest_sha256": _digest(decision),
            "source_decision": deepcopy(decision),
        })

    contribution_money = contribution.get("contribution")
    disposition_status = "NONE" if contribution_money is None else "ROUTE_TO_SGOV_DRY_POWDER"
    undeployed = {
        "status": disposition_status,
        "source_role": "V75_UNDEPLOYED_TO_SGOV",
        "destination_role": "SGOV_DRY_POWDER_BUCKET",
        "contribution": deepcopy(contribution_money),
        "account_owner": _owner_obj(owner),
        "contribution_applied_to_aggregate": False,
        "final_dry_powder_aggregate_computed": False,
        "family_physical_subledger_created": False,
    }

    core = {
        "items": items,
        "undeployed_disposition": undeployed,
        "funding_context": {
            "cash_basis": "AVAILABLE",
            "equity_executable_budget": deepcopy(cash.get("equity_executable_budget")),
            "bond_executable_budget": deepcopy(cash.get("bond_executable_budget")),
            "unsettled": deepcopy(cash.get("unsettled")),
            "reserved": deepcopy(cash.get("reserved")),
            "funding_reallocation_performed": False,
            "available_formula_recomputed": False,
        },
    }
    core_digest = _digest(core)
    item_ids = [x["item_id"] for x in items]
    mentor_return = {
        "contract_name": MENTOR_RETURN_CONTRACT_NAME,
        "contract_version": MENTOR_RETURN_CONTRACT_VERSION,
        "run_id": run_id,
        "owner": _owner_obj(owner),
        "currency": currency,
        "canonical_deployment_result_sha256": core_digest,
        "item_ids": item_ids,
        "interpretation_policy": "EXPLAIN_CANONICAL_SOURCE_FACTS_ONLY_NO_RECOMPUTE",
        "unknown_false_zero_neutral_equivalence_forbidden": True,
        "risk_signal_and_client_preference_must_remain_separate": True,
        "cross_account_or_domain_reallocation_forbidden": True,
        "mentor_may_explain_but_not_mutate_actions": True,
    }

    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "run_id": run_id,
        "owner": _owner_obj(owner),
        "currency": currency,
        "source_bindings": {
            "work3_context_handoff_id": handoff,
            "work4_v82_integration_sha256": _digest(w4),
            "work5_v75_integration_sha256": _digest(w5),
            "work6_funding_isolation_sha256": _digest(w6),
            "work7_sgov_runtime_role_sha256": _digest(w7),
            "work8_protected_holding_sha256": _digest(w8),
            "final_target_allocation_id": sb.get("final_target_allocation_id"),
        },
        "canonical_deployment_result": core,
        "canonical_deployment_result_sha256": core_digest,
        "mentor_return": mentor_return,
        "source_semantics_policy": "NORMALIZE_ONLY_PRESERVE_V82_V75_C_PROTECTION_FUNDING_AND_SGOV_SOURCE_FACTS_NO_RECOMPUTE",
        "integration_diagnostics": [],
    }
    _schema(result, _OUTPUT_SCHEMA, "C8C9.W9.OUTPUT_SCHEMA")
    return result


__all__ = [
    "BASELINE_ID", "INPUT_CONTRACT_NAME", "INPUT_CONTRACT_VERSION",
    "OUTPUT_CONTRACT_NAME", "OUTPUT_CONTRACT_VERSION",
    "MENTOR_RETURN_CONTRACT_NAME", "MENTOR_RETURN_CONTRACT_VERSION",
    "UnifiedDeploymentError", "build_unified_deployment",
]


def build_holdings_recommendation_return(request: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize menu-04 component results without requiring full deployment B.

    No investment calculation or strategy is implemented here. Actual native
    component facts and already-calculated amounts are copied verbatim. This
    return has its own scope and never masquerades as the full canonical result.
    """
    req=_mapping(request,'holdings_recommendation_request')
    if req.get('contract_name')!='LivingWaterAI.C8C9.Work9.HoldingsRecommendationInput' or req.get('contract_version')!='1.0':
        _fail('C8C9.W9.HOLDINGS_CONTRACT','invalid scoped recommendation input')
    client=_nonempty(req.get('client_id'),'client_id');run=_nonempty(req.get('run_id'),'run_id')
    owner=_mapping(req.get('owner'),'owner')
    if owner.get('client_id')!=client:_fail('C8C9.W9.HOLDINGS_OWNER','client/owner mismatch')
    source_sha=_nonempty(req.get('source_db_sha256'),'source_db_sha256')
    source_rows=req.get('positions')
    if not isinstance(source_rows,list):_fail('C8C9.W9.HOLDINGS_SHAPE','positions must be an array')
    items=[];seen=set()
    for index,source in enumerate(source_rows):
        row=_mapping(source,f'positions[{index}]');key=_nonempty(row.get('instrument_id'),'instrument_id')
        facts=_mapping(row.get('native_component_delivery'),'native_component_delivery')
        if key in seen or facts.get('owner')!=owner:_fail('C8C9.W9.HOLDINGS_BINDING','duplicate instrument or cross-owner facts')
        seen.add(key)
        if facts.get('delivery_digest')!=_digest({k:v for k,v in facts.items() if k!='delivery_digest'}):
            _fail('C8C9.W9.HOLDINGS_DIGEST','component delivery changed')
        judgment=_mapping(facts.get('current_judgment'),'current_judgment')
        amounts=_mapping(facts.get('recommendation'),'recommendation')
        amount=amounts.get('buy_gap_amount');rate=amounts.get('target_rate')
        if amount is not None:_number_text(amount,'recommended_buy_amount')
        item={'item_id':key,'asset_id':facts.get('symbol'),'mode':deepcopy(judgment.get('mode')),
            'stage':deepcopy(judgment.get('stage_reference')),
            'target_ratio':{'status':'KNOWN' if rate is not None else 'UNKNOWN','value':rate,'unit':'FRACTION'},
            'cumulative_target_amount':{'amount':deepcopy(amounts.get('cumulative_target_amount')),'currency':amounts.get('currency')},
            'recommended_buy_amount':{'status':'KNOWN' if amount is not None else 'UNKNOWN','amount':amount,'currency':amounts.get('currency')},
            'recommended_sell_amount':{'status':'UNKNOWN','amount':None,'reason':'NO_NATIVE_SELL_AMOUNT_PRODUCED'},
            'new_external_funding_buy_amount':deepcopy(amounts.get('new_external_funding_buy_amount')),
            'new_external_funding_scope':amounts.get('new_external_funding_scope'),
            'remaining_amount_dependencies':deepcopy(amounts.get('missing_fields',[])),
            'native_component_delivery':deepcopy(facts),'broker_submission_allowed':False}
        items.append(item)
    result={'contract_name':'LivingWaterAI.C8C9.Work9.HoldingsRecommendationReturn','contract_version':'1.0',
        'scope':'CURRENT_HOLDINGS_RECOMMENDATIONS__NOT_FULL_CAPITAL_DEPLOYMENT',
        'status':'NORMALIZED_WITH_LIMITATIONS' if any(i['remaining_amount_dependencies'] for i in items) else 'NORMALIZED',
        'client_id':client,'run_id':run,'owner':deepcopy(owner),'source_db_sha256':source_sha,
        'request_digest':req.get('request_digest'),'source_request_digest':_digest(req),'items':items,
        'mentor_return':{'scope':'EXPLAIN_NATIVE_COMPONENT_FACTS_AND_AMOUNT_LIMITATIONS',
            'item_ids':[i['item_id'] for i in items],'financial_mutation_allowed':False},
        'full_canonical_deployment_complete':False,'trade_action':'NO_TRADE'}
    result['result_digest']=_digest(result)
    return result


__all__.append('build_holdings_recommendation_return')
