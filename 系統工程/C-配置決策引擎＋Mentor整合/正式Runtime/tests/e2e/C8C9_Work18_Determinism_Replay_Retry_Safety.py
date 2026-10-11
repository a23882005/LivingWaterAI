"""C8C9 Work18 - Determinism + Replay + Retry Safety.

C-owned replay-safety semantics around the frozen Work9 canonical deployment
result. This module does NOT implement Family persistence, a funding ledger,
correction/supersede storage, DB migration, or any V82/V75/V70 business rule.

It provides deterministic, persistence-compatible identifiers and lineage that
a downstream persistence layer may consume later, while keeping the actual
persistence owner outside ABC Work18.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WORK9_PATH = ROOT / "WORK9_OUTPUT/C8C9_Work9_Unified_Deployment_Mentor_Return.py"
FIXTURE_PATH = ROOT / "WORK11_OUTPUT/FIXTURES/W15_W16_W18_WORK9_INPUT_HAPPY.json"
HARNESS_ID = "C8C9-W18-DETERMINISM-REPLAY-RETRY-v1.0.0"
IDEMPOTENCY_KEY_VERSION = "C8C9-W18-IDEMP-v1"
RUN_LINEAGE_VERSION = "C8C9-W18-RUN-LINEAGE-v1"

# Hash fields whose values are derived from serialized run-bound objects. They
# are evidence bindings, not economic inputs, and therefore are excluded from
# the semantic request projection used for replay-compatible identity.
_RUN_DERIVED_HASH_KEYS = {
    "work4_v82_integration_sha256",
    "work5_v75_integration_sha256",
    "work6_funding_isolation_sha256",
    "canonical_v82_output_sha256",
}


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


def base_request() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _semantic_copy(value: Any) -> Any:
    """Drop transport/run-only identity while preserving business semantics."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "run_id" or k in _RUN_DERIVED_HASH_KEYS:
                continue
            out[k] = _semantic_copy(v)
        return out
    if isinstance(value, list):
        return [_semantic_copy(x) for x in value]
    return deepcopy(value)


def semantic_request_projection(req: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical persistence-compatible request identity (no storage side effect)."""
    return _semantic_copy(req)


def economic_result_projection(work9_result: Mapping[str, Any]) -> dict[str, Any]:
    """Project only economic/status meaning, excluding run-bound trace hashes."""
    core = work9_result["canonical_deployment_result"]
    items = []
    for item in core["items"]:
        items.append({
            "item_id": item["item_id"],
            "source_engine": item["source_engine"],
            "asset_id": item["asset_id"],
            "canonical_action": deepcopy(item["canonical_action"]),
            "source_action": deepcopy(item["source_action"]),
            "client_preference_action": deepcopy(item["client_preference_action"]),
            "deployment_amount": deepcopy(item["deployment_amount"]),
            "deployment_ratio": deepcopy(item["deployment_ratio"]),
            "account_owner": deepcopy(item["account_owner"]),
            "funding_source": deepcopy(item["funding_source"]),
            "reason_codes": deepcopy(item["reason_codes"]),
        })
    return {
        "owner": deepcopy(work9_result["owner"]),
        "currency": work9_result["currency"],
        "items": items,
        "undeployed_disposition": deepcopy(core["undeployed_disposition"]),
        "funding_context": deepcopy(core["funding_context"]),
    }


def idempotency_compatible_key(req: Mapping[str, Any]) -> str:
    semantic_sha = digest(semantic_request_projection(req))
    return f"{IDEMPOTENCY_KEY_VERSION}:{semantic_sha}"


def build_run_lineage(req: Mapping[str, Any], work9_result: Mapping[str, Any]) -> dict[str, Any]:
    w4 = req["work4_v82_integration_result"]
    w5 = req["work5_v75_integration_result"]
    w6 = req["work6_funding_account_isolation_result"]
    return {
        "lineage_version": RUN_LINEAGE_VERSION,
        "run_id": req["run_id"],
        "idempotency_compatible_key": idempotency_compatible_key(req),
        "request_serialized_sha256": digest(req),
        "request_semantic_sha256": digest(semantic_request_projection(req)),
        "canonical_work9_result_sha256": digest(work9_result),
        "economic_result_sha256": digest(economic_result_projection(work9_result)),
        "baseline_id": req["baseline_id"],
        "contract_versions": {
            "work9_input": req["contract_version"],
            "work4": w4["contract_version"],
            "work5": w5["contract_version"],
            "work6": w6["contract_version"],
            "work7": req["work7_sgov_runtime_role_result"]["contract_version"],
            "work8": req["work8_protected_holding_result"]["contract_version"],
            "v82_rule": w4["canonical_v82_output"].get("rule_version"),
            "v75_rule": w5["canonical_v75_output"].get("rule_version"),
            "v75_predicate": w5["canonical_v75_output"].get("predicate_version"),
            "v75_deployment_parameter": w5["canonical_v75_output"].get("deployment_parameter_version"),
        },
        "snapshot_lineage": {
            "work3_context_handoff_id": w4["work3_context_handoff_id"],
            "upstream_v70_snapshot_id": w4["upstream_v70_snapshot_id"],
            "shared_context_id": w4["shared_context_id"],
            "shared_context_digest_sha256": w4["shared_context_digest_sha256"],
            "final_target_allocation_id": w4["authorization_reference"],
        },
        "owner": deepcopy(w6["owner"]),
        "currency": w6["currency"],
        "persistence_performed": False,
        "family_ledger_created": False,
    }


def execute(req: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = deepcopy(req if req is not None else base_request())
    before = deepcopy(request)
    w9 = _load("c8c9_w18_work9", WORK9_PATH)
    result = w9.build_unified_deployment(request)
    if request != before:
        raise AssertionError("Work9 mutated request")
    return {
        "harness_id": HARNESS_ID,
        "work9_result": result,
        "run_lineage": build_run_lineage(request, result),
        "economic_result": economic_result_projection(result),
    }


def rewrite_run_id(req: Mapping[str, Any], new_run_id: str) -> dict[str, Any]:
    """QA helper: same economic request under another transport run identity."""
    out = deepcopy(req)
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k in list(v):
                if k == "run_id":
                    v[k] = new_run_id
                else:
                    walk(v[k])
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(out)
    # Re-bind exact serialized objects whose hashes legitimately changed because
    # run_id is part of their formal serialized contracts.
    w4 = out["work4_v82_integration_result"]
    w5 = out["work5_v75_integration_result"]
    w6 = out["work6_funding_account_isolation_result"]
    w7 = out["work7_sgov_runtime_role_result"]
    w8 = out["work8_protected_holding_result"]
    w8["source_binding"]["work4_v82_integration_sha256"] = digest(w4)
    w8["source_binding"]["canonical_v82_output_sha256"] = digest(w4["canonical_v82_output"])
    w7["source_digests"]["work5_v75_integration_sha256"] = digest(w5)
    w7["source_digests"]["work6_funding_isolation_sha256"] = digest(w6)
    return out


__all__ = [
    "HARNESS_ID", "IDEMPOTENCY_KEY_VERSION", "RUN_LINEAGE_VERSION",
    "base_request", "canonical_json", "digest", "semantic_request_projection",
    "economic_result_projection", "idempotency_compatible_key",
    "build_run_lineage", "execute", "rewrite_run_id",
]
