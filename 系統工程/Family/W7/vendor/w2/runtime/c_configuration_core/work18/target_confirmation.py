"""W2-18 explicit Final Target confirmation and versioning in isolated staging."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Mapping


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


@dataclass(frozen=True)
class StagingDecision:
    status: str
    ledger: Mapping[str, Any]
    event: Mapping[str, Any]
    issue_codes: tuple[str, ...]
    no_commit: bool


def create_pending_version(*, ledger: Mapping[str, Any] | None, draft: Mapping[str, Any],
                           proposed_at: str, expires_at: str, policy_version: str,
                           data_version: str, source_reference_ids: list[str],
                           expected_latest_version: int | None = None) -> StagingDecision:
    """Create a versioned PENDING record in an in-memory TEST staging ledger."""
    target_hash = str(draft.get("draft_hash", ""))
    without_hash = {k: v for k, v in draft.items() if k != "draft_hash"}
    if (draft.get("status") != "DRAFT" or draft.get("confirmation_status") != "PENDING"
            or draft.get("is_trade_authorized") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", target_hash) or _hash(without_hash) != target_hash):
        return _blocked(ledger, "DRAFT_INVALID_OR_HASH_MISMATCH")
    client_id = str((draft.get("identity") or {}).get("client_id", ""))
    if not client_id or not policy_version or not data_version or not source_reference_ids:
        return _blocked(ledger, "VERSION_OR_SOURCE_EVIDENCE_MISSING")
    proposed, expires = _dt(proposed_at), _dt(expires_at)
    if proposed is None or expires is None or expires <= proposed:
        return _blocked(ledger, "PROPOSAL_TIME_OR_EXPIRY_INVALID")
    state = deepcopy(dict(ledger or {"client_id": client_id, "latest_version": 0, "versions": []}))
    if state.get("client_id") != client_id:
        return _blocked(ledger, "LEDGER_CLIENT_MISMATCH")
    latest = int(state.get("latest_version", 0))
    if expected_latest_version is not None and expected_latest_version != latest:
        return _blocked(ledger, "VERSION_CONFLICT")
    if any(v.get("target_hash") == target_hash for v in state.get("versions", [])):
        existing = next(v for v in state["versions"] if v.get("target_hash") == target_hash)
        return StagingDecision("IDEMPOTENT", state,
                               _event("PENDING_VERSION_ALREADY_EXISTS", client_id, existing["version"], target_hash), (), True)
    # A superseded pending version loses its signature path. Previously confirmed
    # versions remain effective until a newer exact hash is explicitly confirmed.
    for version in state.get("versions", []):
        if version.get("status") == "PENDING":
            version["status"] = "SUPERSEDED"
    next_version = latest + 1
    record = {"version": next_version, "target_id": f"FT-{client_id}-v{next_version}",
              "target_hash": target_hash, "status": "PENDING", "proposed_at": proposed_at,
              "expires_at": expires_at, "policy_version": policy_version, "data_version": data_version,
              "source_reference_ids": sorted(set(source_reference_ids)), "draft": deepcopy(dict(draft)),
              "confirmation_evidence": None}
    state.setdefault("versions", []).append(record)
    state["latest_version"] = next_version
    return StagingDecision("PENDING", state, _event("TARGET_VERSION_PENDING", client_id, next_version, target_hash), (), True)


def apply_confirmation(*, ledger: Mapping[str, Any], client_id: str, version: int,
                       target_hash: str, action: str, client_explicit_decision: str,
                       confirmed_at: str, confirmed_by: str, source_reference_ids: list[str],
                       now: str) -> StagingDecision:
    """Confirm/reject one exact target version in TEST staging; no external commit."""
    state = deepcopy(dict(ledger))
    if state.get("client_id") != client_id:
        return _blocked(ledger, "CROSS_CLIENT_CONFIRMATION")
    versions = state.get("versions", [])
    record = next((v for v in versions if v.get("version") == version), None)
    if record is None or version != state.get("latest_version"):
        return _blocked(ledger, "TARGET_VERSION_CONFLICT")
    if record.get("target_hash") != target_hash:
        return _blocked(ledger, "TARGET_HASH_MISMATCH")
    if action not in {"CONFIRM", "REJECT"}:
        return _blocked(ledger, "CONFIRMATION_ACTION_INVALID")
    evidence = {"action": action, "client_explicit_decision": client_explicit_decision,
                "confirmed_at": confirmed_at, "confirmed_by": confirmed_by,
                "source_reference_ids": sorted(set(source_reference_ids))}
    evidence_hash = _hash(evidence)
    if action == "CONFIRM" and record.get("status") == "CONFIRMED":
        if record.get("confirmation_evidence_hash") == evidence_hash:
            return StagingDecision("IDEMPOTENT", state,
                                   _event("TARGET_CONFIRMATION_REPLAY", client_id, version, target_hash), (), True)
        return _blocked(ledger, "DUPLICATE_CONFIRMATION_CONFLICT")
    if action == "REJECT" and record.get("status") == "REJECTED":
        if record.get("rejection_evidence_hash") == evidence_hash:
            return StagingDecision("IDEMPOTENT", state,
                                   _event("TARGET_REJECTION_REPLAY", client_id, version, target_hash), (), True)
        return _blocked(ledger, "DUPLICATE_REJECTION_CONFLICT")
    if client_explicit_decision != "TRUE" or confirmed_by != client_id:
        return _blocked(ledger, "EXPLICIT_CLIENT_CONFIRMATION_REQUIRED")
    if not source_reference_ids or not set(source_reference_ids).issubset(set(record.get("source_reference_ids", []))):
        return _blocked(ledger, "CONFIRMATION_SOURCE_MISMATCH")
    if action == "REJECT":
        if record.get("status") != "PENDING":
            return _blocked(ledger, "TARGET_NOT_PENDING")
        record["status"] = "REJECTED"
        record["confirmation_evidence"] = evidence
        record["rejection_evidence_hash"] = evidence_hash
        return StagingDecision("REJECTED", state, _event("TARGET_REJECTED_NO_COMMIT", client_id, version, target_hash), (), True)
    if record.get("status") != "PENDING":
        return _blocked(ledger, "TARGET_NOT_PENDING")
    proposed, expires, confirmed, current = (_dt(record.get("proposed_at")), _dt(record.get("expires_at")),
                                                _dt(confirmed_at), _dt(now))
    if proposed is None or expires is None or confirmed is None or current is None:
        return _blocked(ledger, "CONFIRMATION_TIME_INVALID")
    if confirmed < proposed:
        return _blocked(ledger, "CONFIRMATION_BEFORE_PROPOSAL")
    if confirmed > current:
        return _blocked(ledger, "CONFIRMATION_AFTER_NOW")
    if current > expires or confirmed > expires:
        return _blocked(ledger, "TARGET_EXPIRED")
    record["status"] = "CONFIRMED"
    record["confirmation_evidence"] = evidence
    record["confirmation_evidence_hash"] = evidence_hash
    for older in versions:
        if older["version"] != version and older.get("status") == "CONFIRMED":
            older["status"] = "SUPERSEDED"
    return StagingDecision("CONFIRMED", state,
                           _event("TARGET_CONFIRMED_IN_TEST_STAGING", client_id, version, target_hash), (), True)


def _event(kind: str, client_id: str, version: int, target_hash: str) -> dict[str, Any]:
    return {"event_type": kind, "client_id": client_id, "version": version,
            "target_hash": target_hash, "write_scope": "ISOLATED_TEST_STAGING"}


def _blocked(ledger: Mapping[str, Any] | None, code: str) -> StagingDecision:
    original = deepcopy(dict(ledger or {}))
    return StagingDecision("BLOCKED", original,
                           {"event_type": "NO_COMMIT", "issue_code": code,
                            "write_scope": "ISOLATED_TEST_STAGING"}, (code,), True)
