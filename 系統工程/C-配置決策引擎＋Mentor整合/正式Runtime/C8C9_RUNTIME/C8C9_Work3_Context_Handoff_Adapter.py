"""C8C9 Work3 - V70 Runtime Context Handoff Adapter (RECHECK2).

C8C9-owned integration adapter only. It validates and binds already-owned source
contexts for a single formal Loop-2 run. It MUST NOT recompute investment logic,
perform FX, alter budgets, flatten source data_as_of payloads, or create a second
Funding Domain Engine.

RECHECK2 hardening: Work3 now independently fail-closes malformed Work2 envelope
shape/monetary/version/lineage/status payloads instead of relying on callers to
have run the Work2 JSON Schema first.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping

BASELINE_ID = "C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e"
WORK2_ENVELOPE_NAME = "LivingWaterAI.C8C9.Work2.UnifiedIntegrationEnvelope"
WORK2_ENVELOPE_VERSION = "C8C9-W2-UIC-v1.0.1-RECHECK1"
INPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffInput"
INPUT_CONTRACT_VERSION = "C8C9-W3-CHI-v1.0.1-RECHECK2"
OUTPUT_CONTRACT_NAME = "LivingWaterAI.C8C9.Work3.ContextHandoffResult"
OUTPUT_CONTRACT_VERSION = "C8C9-W3-CHO-v1.0.1-RECHECK2"

_OWNER_DOMAINS = {"TW_LOCAL_BROKER", "TW_SUB_BROKERAGE", "US_BROKER"}
_DECIMAL_RE = re.compile(r"^\+?\d+(?:\.\d+)?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class HandoffValidationError(ValueError):
    """Fail-closed Work3 integration error. Codes are diagnostics, not business rules."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> None:
    raise HandoffValidationError(code, detail)


def _canonical_bytes(value: Any) -> bytes:
    """Stable provenance serialization only; never used to change business values."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("C8C9.W3.NON_JSON_CONTEXT", f"context is not canonical JSON serializable: {exc}")


def _digest(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _require_nonempty_string(value: Any, code: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code, f"{field} must be a non-empty string")
    return value


def _require_mapping(value: Any, code: str, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code, f"{field} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], required: set[str], allowed: set[str], code: str, field: str) -> None:
    missing = required - set(value.keys())
    extra = set(value.keys()) - allowed
    if missing or extra:
        _fail(code, f"{field} key mismatch; missing={sorted(missing)} extra={sorted(extra)}")


def _validate_currency(value: Any, code: str, field: str) -> str:
    if not isinstance(value, str) or not _CURRENCY_RE.fullmatch(value):
        _fail(code, f"{field} must be a 3-letter uppercase currency code")
    return value


def _validate_nonnegative_amount(value: Any, code: str, field: str) -> None:
    if isinstance(value, bool):
        _fail(code, f"{field} boolean is not a monetary amount")
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value < 0:
            _fail(code, f"{field} must be a finite nonnegative JSON number")
        return
    if isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        return
    _fail(code, f"{field} must be a nonnegative JSON number or Decimal string")


def _validate_money(value: Any, code: str, field: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    obj = _require_mapping(value, code, field)
    _require_exact_keys(obj, {"amount", "currency"}, {"amount", "currency"}, code, field)
    _validate_nonnegative_amount(obj.get("amount"), code, f"{field}.amount")
    _validate_currency(obj.get("currency"), code, f"{field}.currency")


def _validate_owner(owner: Any, code: str = "C8C9.W3.OWNER_SHAPE", field: str = "owner") -> tuple[str, str, str]:
    obj = _require_mapping(owner, code, field)
    _require_exact_keys(obj, {"funding_domain", "broker", "account"}, {"funding_domain", "broker", "account"}, code, field)
    domain = obj.get("funding_domain")
    if domain not in _OWNER_DOMAINS:
        _fail(code, f"{field}.funding_domain is not canonical")
    broker = _require_nonempty_string(obj.get("broker"), code, f"{field}.broker")
    account = _require_nonempty_string(obj.get("account"), code, f"{field}.account")
    return (domain, broker, account)


def _validate_string_list(value: Any, code: str, field: str, *, nonempty: bool = False, unique: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(x, str) or not x for x in value):
        _fail(code, f"{field} must be {'a non-empty ' if nonempty else 'a '}list of non-empty strings")
    if unique and len(value) != len(set(value)):
        _fail(code, f"{field} must contain unique values")
    return value


def _validate_same_run(expected: str, label: str, actual: Any) -> None:
    if actual != expected:
        _fail("C8C9.W3.RUN_ID_MISMATCH", f"{label}.run_id={actual!r} expected {expected!r}")


def _validate_context_wrapper(wrapper: Any, expected_run: str, label: str) -> None:
    obj = _require_mapping(wrapper, "C8C9.W3.CONTEXT_SHAPE", label)
    _validate_same_run(expected_run, label, obj.get("run_id"))
    _require_nonempty_string(obj.get("source_namespace"), "C8C9.W3.CONTEXT_NAMESPACE", f"{label}.source_namespace")
    if "payload" not in obj:
        _fail("C8C9.W3.CONTEXT_PAYLOAD", f"{label}.payload is required")
    if "data_as_of" not in obj:
        _fail("C8C9.W3.CONTEXT_DATA_AS_OF", f"{label}.data_as_of is required")
    _validate_string_list(obj.get("source_reference_ids"), "C8C9.W3.CONTEXT_LINEAGE", f"{label}.source_reference_ids", nonempty=True, unique=True)
    payload = obj.get("payload")
    if isinstance(payload, Mapping) and payload.get("run_id") not in (None, expected_run):
        _fail("C8C9.W3.RUN_ID_MISMATCH", f"{label}.payload.run_id conflicts with handoff run")


def _validate_work2_envelope(w2: Any, expected_run: str) -> None:
    obj = _require_mapping(w2, "C8C9.W3.WORK2_SHAPE", "work2_envelope")
    required = {
        "contract_name", "contract_version", "baseline_id", "run_id", "owner", "currency", "settlement",
        "final_target", "remaining_target_gap", "executable_budget", "temporal", "versions", "lineage",
        "reason_status", "sgov_boundary",
    }
    _require_exact_keys(obj, required, required, "C8C9.W3.WORK2_SCHEMA_BOUNDARY", "work2_envelope")
    if obj.get("contract_name") != WORK2_ENVELOPE_NAME or obj.get("contract_version") != WORK2_ENVELOPE_VERSION:
        _fail("C8C9.W3.WORK2_CONTRACT", "Work2 envelope contract identity/version mismatch")
    if obj.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W3.BASELINE_MISMATCH", "Work2 envelope baseline differs from Frozen Baseline")
    _validate_same_run(expected_run, "work2_envelope", obj.get("run_id"))

    owner_key = _validate_owner(obj.get("owner"), field="work2_envelope.owner")
    currency = _validate_currency(obj.get("currency"), "C8C9.W3.CURRENCY", "work2_envelope.currency")

    settlement = _require_mapping(obj.get("settlement"), "C8C9.W3.SETTLEMENT_SHAPE", "work2_envelope.settlement")
    _require_exact_keys(settlement, {"cash_basis", "cash_state", "source_status"}, {"cash_basis", "cash_state", "source_status"}, "C8C9.W3.SETTLEMENT_SHAPE", "work2_envelope.settlement")
    if settlement.get("cash_basis") != "AVAILABLE":
        _fail("C8C9.W3.SETTLEMENT_BASIS", "cash_basis must remain AVAILABLE")
    if settlement.get("source_status") is not None and not isinstance(settlement.get("source_status"), str):
        _fail("C8C9.W3.SETTLEMENT_SHAPE", "settlement.source_status must be string or null")
    cash_state = _require_mapping(settlement.get("cash_state"), "C8C9.W3.CASH_STATE", "work2_envelope.settlement.cash_state")
    cash_keys = {"total", "available", "unsettled", "reserved"}
    _require_exact_keys(cash_state, cash_keys, cash_keys, "C8C9.W3.CASH_STATE", "work2_envelope.settlement.cash_state")
    for key in sorted(cash_keys):
        val = cash_state.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
            _fail("C8C9.W3.CASH_STATE", f"cash_state.{key} must be a finite nonnegative JSON number")

    budgets = _require_mapping(obj.get("executable_budget"), "C8C9.W3.BUDGET_SHAPE", "work2_envelope.executable_budget")
    _require_exact_keys(budgets, {"equity", "bond"}, {"equity", "bond"}, "C8C9.W3.BUDGET_SHAPE", "work2_envelope.executable_budget")
    for leg_name in ("equity", "bond"):
        leg = _require_mapping(budgets.get(leg_name), "C8C9.W3.BUDGET_SHAPE", f"work2_envelope.executable_budget.{leg_name}")
        leg_keys = {"amount", "currency", "cash_basis", "owner"}
        _require_exact_keys(leg, leg_keys, leg_keys, "C8C9.W3.BUDGET_SHAPE", f"work2_envelope.executable_budget.{leg_name}")
        _validate_nonnegative_amount(leg.get("amount"), "C8C9.W3.BUDGET_AMOUNT", f"{leg_name}.amount")
        if leg.get("cash_basis") != "AVAILABLE":
            _fail("C8C9.W3.BUDGET_BASIS", f"{leg_name} cash_basis must remain AVAILABLE")
        if _validate_owner(leg.get("owner"), field=f"{leg_name}.owner") != owner_key:
            _fail("C8C9.W3.CROSS_OWNER_FUNDING", f"{leg_name} owner differs from envelope owner")
        leg_currency = _validate_currency(leg.get("currency"), "C8C9.W3.CURRENCY", f"{leg_name}.currency")
        if leg_currency != currency:
            _fail("C8C9.W3.NO_FX_CURRENCY_MISMATCH", f"{leg_name} currency differs from envelope currency; Work3 cannot FX-convert")

    ft = _require_mapping(obj.get("final_target"), "C8C9.W3.FINAL_TARGET", "work2_envelope.final_target")
    ft_keys = {"allocation_id", "authorization_reference", "confirmation_proof", "payload"}
    _require_exact_keys(ft, ft_keys, ft_keys, "C8C9.W3.FINAL_TARGET", "work2_envelope.final_target")
    allocation_id = _require_nonempty_string(ft.get("allocation_id"), "C8C9.W3.FINAL_TARGET_CONFIRMATION", "final_target.allocation_id")
    _require_nonempty_string(ft.get("authorization_reference"), "C8C9.W3.FINAL_TARGET_CONFIRMATION", "final_target.authorization_reference")
    if ft.get("authorization_reference") != allocation_id:
        _fail("C8C9.W3.AUTHORIZATION_REFERENCE", "authorization_reference must equal confirmed C7 allocation_id")
    proof = _require_mapping(ft.get("confirmation_proof"), "C8C9.W3.FINAL_TARGET_CONFIRMATION", "final_target.confirmation_proof")
    _require_exact_keys(proof, {"confirmed_at", "confirmed_by"}, {"confirmed_at", "confirmed_by"}, "C8C9.W3.FINAL_TARGET_CONFIRMATION", "final_target.confirmation_proof")
    _require_nonempty_string(proof.get("confirmed_at"), "C8C9.W3.FINAL_TARGET_CONFIRMATION", "confirmed_at")
    _require_nonempty_string(proof.get("confirmed_by"), "C8C9.W3.FINAL_TARGET_CONFIRMATION", "confirmed_by")

    gaps = _require_mapping(obj.get("remaining_target_gap"), "C8C9.W3.GAP_NAMESPACE", "work2_envelope.remaining_target_gap")
    _require_exact_keys(gaps, {"v82", "v75"}, {"v82", "v75"}, "C8C9.W3.GAP_NAMESPACE", "work2_envelope.remaining_target_gap")
    allowed_modes = {"v82": {"V82_EXISTING_RUNTIME_DERIVED", "NOT_APPLICABLE"}, "v75": {"V75_EXISTING_EXPLICIT_GAP", "NOT_APPLICABLE"}}
    for engine in ("v82", "v75"):
        gap = _require_mapping(gaps.get(engine), "C8C9.W3.GAP_NAMESPACE", f"remaining_target_gap.{engine}")
        _require_exact_keys(gap, {"mode", "payload"}, {"mode", "payload"}, "C8C9.W3.GAP_NAMESPACE", f"remaining_target_gap.{engine}")
        if gap.get("mode") not in allowed_modes[engine]:
            _fail("C8C9.W3.GAP_NAMESPACE", f"remaining_target_gap.{engine}.mode is not canonical")

    temporal = _require_mapping(obj.get("temporal"), "C8C9.W3.TEMPORAL", "work2_envelope.temporal")
    _require_exact_keys(temporal, {"as_of", "data_as_of"}, {"as_of", "data_as_of"}, "C8C9.W3.TEMPORAL", "work2_envelope.temporal")
    _require_nonempty_string(temporal.get("as_of"), "C8C9.W3.TEMPORAL", "temporal.as_of")
    if not isinstance(temporal.get("data_as_of"), Mapping):
        _fail("C8C9.W3.TEMPORAL", "temporal.data_as_of must remain a source-namespaced object")

    versions = _require_mapping(obj.get("versions"), "C8C9.W3.VERSION_LINEAGE", "work2_envelope.versions")
    _require_exact_keys(versions, {"rule", "data", "schema"}, {"rule", "data", "schema"}, "C8C9.W3.VERSION_LINEAGE", "work2_envelope.versions")
    for key in ("rule", "data", "schema"):
        if not isinstance(versions.get(key), Mapping):
            _fail("C8C9.W3.VERSION_LINEAGE", f"versions.{key} must be an object")

    lineage = _require_mapping(obj.get("lineage"), "C8C9.W3.VERSION_LINEAGE", "work2_envelope.lineage")
    _require_exact_keys(lineage, {"source_reference_ids", "upstream_snapshot_ids"}, {"source_reference_ids", "upstream_snapshot_ids"}, "C8C9.W3.VERSION_LINEAGE", "work2_envelope.lineage")
    _validate_string_list(lineage.get("source_reference_ids"), "C8C9.W3.VERSION_LINEAGE", "lineage.source_reference_ids", unique=True)
    snapshots = _require_mapping(lineage.get("upstream_snapshot_ids"), "C8C9.W3.VERSION_LINEAGE", "lineage.upstream_snapshot_ids")
    if any(v is not None and (not isinstance(v, str) or not v) for v in snapshots.values()):
        _fail("C8C9.W3.VERSION_LINEAGE", "lineage.upstream_snapshot_ids values must be non-empty string or null")

    reason_status = _require_mapping(obj.get("reason_status"), "C8C9.W3.REASON_STATUS", "work2_envelope.reason_status")
    rs_keys = {"source_reason_codes", "source_status_codes", "integration_diagnostics"}
    _require_exact_keys(reason_status, rs_keys, rs_keys, "C8C9.W3.REASON_STATUS", "work2_envelope.reason_status")
    reason_codes = _require_mapping(reason_status.get("source_reason_codes"), "C8C9.W3.REASON_STATUS", "source_reason_codes")
    if any(not isinstance(v, list) or any(not isinstance(x, str) for x in v) for v in reason_codes.values()):
        _fail("C8C9.W3.REASON_STATUS", "source_reason_codes values must be string arrays")
    status_codes = _require_mapping(reason_status.get("source_status_codes"), "C8C9.W3.REASON_STATUS", "source_status_codes")
    if any(v is not None and not isinstance(v, str) for v in status_codes.values()):
        _fail("C8C9.W3.REASON_STATUS", "source_status_codes values must be string or null")
    _validate_string_list(reason_status.get("integration_diagnostics"), "C8C9.W3.REASON_STATUS", "integration_diagnostics")

    sgov = _require_mapping(obj.get("sgov_boundary"), "C8C9.W3.SGOV_BOUNDARY", "work2_envelope.sgov_boundary")
    sgov_keys = {
        "v70_original_dry_powder", "sgov_bond_bucket_amount", "sgov_dry_powder_bucket_amount", "v75_undeployed_to_sgov",
        "v82_undeployed_to_sgov", "roles_kept_separate", "v82_access_forbidden", "v82_raw_equity_budget_auto_route_forbidden",
        "final_aggregate_computed_in_work2", "physical_subledger_out_of_scope",
    }
    _require_exact_keys(sgov, sgov_keys, sgov_keys, "C8C9.W3.SGOV_BOUNDARY", "work2_envelope.sgov_boundary")
    dry = _require_mapping(sgov.get("v70_original_dry_powder"), "C8C9.W3.SGOV_BOUNDARY", "sgov_boundary.v70_original_dry_powder")
    _require_exact_keys(dry, {"amount", "weight", "source_status"}, {"amount", "weight", "source_status"}, "C8C9.W3.SGOV_BOUNDARY", "sgov_boundary.v70_original_dry_powder")
    _validate_money(dry.get("amount"), "C8C9.W3.SGOV_BOUNDARY", "v70_original_dry_powder.amount", nullable=True)
    weight = dry.get("weight")
    if weight is not None and (isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0 or weight > 1):
        _fail("C8C9.W3.SGOV_BOUNDARY", "v70_original_dry_powder.weight must be null or a finite number in [0,1]")
    if dry.get("source_status") is not None and not isinstance(dry.get("source_status"), str):
        _fail("C8C9.W3.SGOV_BOUNDARY", "v70_original_dry_powder.source_status must be string or null")
    for name in ("sgov_bond_bucket_amount", "sgov_dry_powder_bucket_amount", "v75_undeployed_to_sgov"):
        _validate_money(sgov.get(name), "C8C9.W3.SGOV_BOUNDARY", f"sgov_boundary.{name}", nullable=True)
    if sgov.get("v82_undeployed_to_sgov") is not None:
        _fail("C8C9.W3.V82_SGOV_FABRICATION", "current V82 Ready Output has no canonical V82_UNDEPLOYED_TO_SGOV")
    if sgov.get("v82_raw_equity_budget_auto_route_forbidden") is not True:
        _fail("C8C9.W3.RAW_EQUITY_TO_SGOV", "raw V82 equity budget auto-route prohibition must remain true")
    if sgov.get("roles_kept_separate") is not True or sgov.get("v82_access_forbidden") is not True:
        _fail("C8C9.W3.SGOV_ROLE_SEPARATION", "SGOV roles/access boundary must remain unchanged")
    if sgov.get("final_aggregate_computed_in_work2") is not False:
        _fail("C8C9.W3.SGOV_AGGREGATE_OWNER", "Work2/Work3 must not claim final SGOV aggregate was computed")
    if sgov.get("physical_subledger_out_of_scope") is not True:
        _fail("C8C9.W3.SGOV_BOUNDARY", "Family physical SGOV subledger remains out of scope")


def build_context_handoff(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a single formal-run context bundle and return a lossless handoff result."""
    if not isinstance(request, Mapping):
        _fail("C8C9.W3.INPUT_SHAPE", "request must be an object")
    if request.get("contract_name") != INPUT_CONTRACT_NAME or request.get("contract_version") != INPUT_CONTRACT_VERSION:
        _fail("C8C9.W3.INPUT_CONTRACT", "Work3 input contract identity/version mismatch")
    if request.get("baseline_id") != BASELINE_ID:
        _fail("C8C9.W3.BASELINE_MISMATCH", "input baseline differs from Frozen Baseline")
    run_id = _require_nonempty_string(request.get("run_id"), "C8C9.W3.RUN_ID", "run_id")

    w2 = request.get("work2_envelope")
    _validate_work2_envelope(w2, run_id)

    client_state = request.get("client_state_context")
    v70_context = request.get("v70_runtime_context")
    shared_context = request.get("shared_decision_context")
    for label, wrapper in (
        ("client_state_context", client_state),
        ("v70_runtime_context", v70_context),
        ("shared_decision_context", shared_context),
    ):
        _validate_context_wrapper(wrapper, run_id, label)

    v70_snapshot_id = _require_nonempty_string(v70_context.get("upstream_v70_snapshot_id"), "C8C9.W3.V70_SNAPSHOT", "v70_runtime_context.upstream_v70_snapshot_id")
    _require_nonempty_string(v70_context.get("snapshot_as_of"), "C8C9.W3.V70_SNAPSHOT", "v70_runtime_context.snapshot_as_of")
    w2_snapshots = w2["lineage"]["upstream_snapshot_ids"]
    if w2_snapshots.get("v70") != v70_snapshot_id:
        _fail("C8C9.W3.V70_LINEAGE_MISMATCH", "Work2 lineage v70 snapshot must exactly match Work3 V70 context")

    shared_id = _require_nonempty_string(shared_context.get("context_id"), "C8C9.W3.SHARED_CONTEXT_ID", "shared_decision_context.context_id")
    shared_as_of = _require_nonempty_string(shared_context.get("as_of"), "C8C9.W3.SHARED_CONTEXT_AS_OF", "shared_decision_context.as_of")
    decision_as_of = w2["temporal"]["as_of"]
    if shared_as_of != decision_as_of:
        _fail("C8C9.W3.AS_OF_MISMATCH", f"shared decision context as_of {shared_as_of!r} != Work2 as_of {decision_as_of!r}")

    # Shared decision context must be traceable into the Work2 lineage, without Work3
    # inventing or rewriting source ids. At least one exact source reference must join.
    w2_refs = set(w2["lineage"]["source_reference_ids"])
    shared_refs = set(shared_context["source_reference_ids"])
    if not (w2_refs & shared_refs):
        _fail("C8C9.W3.SHARED_CONTEXT_LINEAGE_MISMATCH", "shared decision context has no source-reference join to Work2 lineage")

    # Work3 may not reinterpret context versions. It fingerprints the exact shared object.
    shared_digest = _digest(shared_context)
    owner = deepcopy(w2["owner"])
    owner_digest = _digest(owner)
    handoff_id = "C8C9-W3-" + sha256(f"{run_id}|{owner_digest}|{shared_digest}".encode("utf-8")).hexdigest()[:32]

    # Deep copies preserve nested/object/scalar data_as_of and source payload shapes.
    result = {
        "contract_name": OUTPUT_CONTRACT_NAME,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "baseline_id": BASELINE_ID,
        "work2_contract_version": WORK2_ENVELOPE_VERSION,
        "context_handoff_id": handoff_id,
        "run_id": run_id,
        "owner": owner,
        "currency": w2["currency"],
        "final_target": deepcopy(w2["final_target"]),
        "client_state_context": deepcopy(client_state),
        "funding_context": {
            "settlement": deepcopy(w2["settlement"]),
            "executable_budget": deepcopy(w2["executable_budget"]),
            "remaining_target_gap": deepcopy(w2["remaining_target_gap"]),
            "sgov_boundary": deepcopy(w2["sgov_boundary"]),
        },
        "v70_runtime_context": deepcopy(v70_context),
        "shared_decision_context": deepcopy(shared_context),
        "temporal": deepcopy(w2["temporal"]),
        "versions": deepcopy(w2["versions"]),
        "lineage": deepcopy(w2["lineage"]),
        "reason_status": deepcopy(w2["reason_status"]),
        "engine_bindings": {
            "v82": {
                "consumer": "V82",
                "run_id": run_id,
                "owner": deepcopy(owner),
                "shared_context_id": shared_id,
                "shared_context_digest_sha256": shared_digest,
                "executable_budget_pointer": "/funding_context/executable_budget/equity",
                "remaining_target_gap_pointer": "/funding_context/remaining_target_gap/v82",
                "final_target_pointer": "/final_target",
                "authorization_reference": w2["final_target"]["allocation_id"],
                "v70_original_dry_powder_executable": False,
                "sgov_bucket_access": "FORBIDDEN",
            },
            "v75": {
                "consumer": "V75",
                "run_id": run_id,
                "owner": deepcopy(owner),
                "shared_context_id": shared_id,
                "shared_context_digest_sha256": shared_digest,
                "executable_budget_pointer": "/funding_context/executable_budget/bond",
                "remaining_target_gap_pointer": "/funding_context/remaining_target_gap/v75",
                "final_target_pointer": "/final_target",
                "sgov_context_access": "READ_ONLY_BOUNDARY_CONTEXT",
            },
        },
        "integration_diagnostics": [],
    }

    if result["engine_bindings"]["v82"]["shared_context_digest_sha256"] != result["engine_bindings"]["v75"]["shared_context_digest_sha256"]:
        _fail("C8C9.W3.CONTEXT_VERSION_CONFLICT", "V82/V75 shared context digest mismatch")
    if result["engine_bindings"]["v82"]["run_id"] != result["engine_bindings"]["v75"]["run_id"]:
        _fail("C8C9.W3.RUN_ID_MISMATCH", "V82/V75 binding run mismatch")

    return result


__all__ = [
    "BASELINE_ID",
    "INPUT_CONTRACT_NAME",
    "INPUT_CONTRACT_VERSION",
    "OUTPUT_CONTRACT_NAME",
    "OUTPUT_CONTRACT_VERSION",
    "HandoffValidationError",
    "build_context_handoff",
]
