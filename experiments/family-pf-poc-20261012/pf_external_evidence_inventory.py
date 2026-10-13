"""Offline Gate A evidence inventory lint. No external calls or release authority.

A complete inventory is REVIEW_PACKAGE_READY, never Gate A PASS.
Evidence references and review decisions must be verified by a separate authority.
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
import ipaddress
from pf_gate_a_checklist import REQUIRED_EVIDENCE

def _safe_reference(ref):
    if not isinstance(ref, str):
        return False
    try:
        parts = urlsplit(ref)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return False
        if parts.query or parts.fragment or parts.port not in (None, 443):
            return False
        host = parts.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".test", ".invalid", ".example")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return bool(parts.path and parts.path != "/" and "\\" not in parts.path and not any(ord(ch) < 32 or ord(ch) == 127 for ch in ref))
    except (TypeError, ValueError):
        return False

def inspect_inventory(entries, now=None):
    """Check shape and reference hygiene; never validate contents or authenticate a reviewer."""
    result = {"state": "HOLD", "missing": [], "invalid": [],
              "verification": "NOT_INDEPENDENTLY_VERIFIED", "gate_a": "HOLD"}
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        result["invalid"].append("validation_clock")
        return result
    if not isinstance(entries, dict):
        result["missing"] = list(REQUIRED_EVIDENCE)
        return result
    for key in REQUIRED_EVIDENCE:
        record = entries.get(key)
        if record is None:
            result["missing"].append(key)
            continue
        if not isinstance(record, dict):
            result["invalid"].append(key)
            continue
        if record.get("result") != "OBSERVED":
            result["invalid"].append(key)
            continue
        if not _safe_reference(record.get("evidence_url")):
            result["invalid"].append(key)
            continue
        if not isinstance(record.get("witness_role"), str) or record["witness_role"] != "independent_security_reviewer":
            result["invalid"].append(key)
            continue
        stamp = record.get("observed_at")
        if not isinstance(stamp, str):
            result["invalid"].append(key)
            continue
        try:
            observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            result["invalid"].append(key)
            continue
        if observed.tzinfo is None or observed > moment or moment - observed > timedelta(days=7):
            result["invalid"].append(key)
    if not result["missing"] and not result["invalid"]:
        result["state"] = "REVIEW_PACKAGE_READY"
    return result
