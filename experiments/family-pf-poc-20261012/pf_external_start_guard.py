"""Fail-closed Family PF authorization preflight, offline only.

This checker never performs HTTP requests and never grants Gate A release authority.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import re
from datetime import datetime, timezone

REQUIRED = (
    "approved_scope_id", "environment_id", "endpoint_origin", "test_window_utc",
    "budget_approval_id", "test_executor_id", "idp_approval_id",
    "synthetic_tenant_a_id", "synthetic_tenant_b_id",
    "audit_custodian_id", "audit_store_approval_id",
    "independent_reviewer_id", "gate_governance_owner_id",
)
MAX_MANIFEST_BYTES = 65536
MAX_FIELD_LENGTH = 512
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SECRET_MARKERS = ("token", "password", "secret", "cookie", "private_key", "authorization_header")

def assess(manifest):
    result = {"external_test_start": "BLOCKED", "gate_a": "HOLD",
              "work13_allowed": False, "missing_fields": [], "errors": []}
    if not isinstance(manifest, dict):
        result["errors"].append("manifest_must_be_object")
        return result
    if any(s in str(key).lower() for key in manifest for s in SECRET_MARKERS):
        result["errors"].append("secret_like_key_in_manifest")
    # Fail closed on unrecognized manifest fields: prevent unreviewed controls or
    # accidental credentials from being silently ignored by an operator.
    permitted = set(REQUIRED) | {"environment_type", "test_data_class", "approval_for_live_test"}
    if set(manifest) - permitted:
        result["errors"].append("unknown_manifest_fields")
    for key, value in manifest.items():
        if not isinstance(key, str) or not isinstance(value, (str, bool)):
            result["errors"].append("invalid_manifest_field_type")
            break
        if isinstance(value, str) and (
            len(value) > MAX_FIELD_LENGTH or
            any(ord(ch) < 32 or ord(ch) == 127 for ch in value) or
            value != value.strip()
        ):
            result["errors"].append("unsafe_manifest_field_value")
            break
    for field in REQUIRED:
        val = manifest.get(field)
        if not isinstance(val, str) or not val.strip() or val.strip().lower() in {"pending", "tbd", "none", "blocked", "todo", "unknown"}:
            result["missing_fields"].append(field)
    if manifest.get("environment_type") != "isolated_nonproduction":
        result["errors"].append("must_be_isolated_nonproduction")
    if manifest.get("test_data_class") != "synthetic_only":
        result["errors"].append("must_use_synthetic_only")
    if manifest.get("approval_for_live_test") is not True:
        result["errors"].append("live_test_not_explicitly_approved")
    # Require a real, unambiguous future test window, rather than a prose label.
    window = manifest.get("test_window_utc")
    if isinstance(window, str) and "/" in window:
        try:
            start_s, end_s = window.split("/")
            def utc_time(value):
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
                    raise ValueError("non_utc_timestamp")
                return dt.astimezone(timezone.utc)
            start, end = utc_time(start_s), utc_time(end_s)
            if not (start < end and start > datetime.now(timezone.utc) and (end - start).total_seconds() <= 86400):
                raise ValueError("invalid_window_bounds")
        except (ValueError, TypeError, AttributeError):
            result["errors"].append("test_window_must_be_future_utc_under_24h")
    else:
        result["errors"].append("test_window_must_be_future_utc_under_24h")
    if str(manifest.get("synthetic_tenant_a_id", "")).strip().casefold() == str(manifest.get("synthetic_tenant_b_id", "")).strip().casefold():
        result["errors"].append("test_tenants_must_differ")
    # Separation of duties must cover all three operating roles, not just two.
    roles = [manifest.get(k) for k in ("test_executor_id", "audit_custodian_id",
                                      "independent_reviewer_id", "gate_governance_owner_id")]
    if all(isinstance(v, str) and v.strip() for v in roles) and len({v.strip().casefold() for v in roles}) != len(roles):
        result["errors"].append("role_separation_violation")
    if manifest.get("test_executor_id") == manifest.get("independent_reviewer_id"):
        result["errors"].append("reviewer_must_be_independent")
    origin = manifest.get("endpoint_origin")
    try:
        parsed = urlsplit(origin) if isinstance(origin, str) else None
        valid_origin = (
            parsed is not None and parsed.scheme == "https" and
            bool(parsed.hostname) and not parsed.username and not parsed.password and
            parsed.port in (None, 443) and parsed.path in ("", "/") and
            not parsed.query and not parsed.fragment and "\\" not in origin and
            not any(ch.isspace() for ch in origin) and
            parsed.hostname.lower() not in {"localhost"} and
            not parsed.hostname.endswith(".") and
            all(DNS_LABEL.fullmatch(label) for label in parsed.hostname.lower().split(".")) and
            not parsed.hostname.lower().endswith((".localhost", ".test", ".invalid", ".example"))
        )
        if valid_origin:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                ip = None
            if ip is not None and not ip.is_global:
                valid_origin = False
    except (ValueError, TypeError):
        valid_origin = False
    if not valid_origin:
        result["errors"].append("endpoint_must_be_public_https_origin")
    if not result["errors"] and not result["missing_fields"]:
        result["external_test_start"] = "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
    return result

def load_manifest(path):
    """Bound input and reject ambiguous duplicate JSON object keys before approval."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest_too_large")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_manifest_key")
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        doc = load_manifest(args.manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        doc = None
    outcome = assess(doc)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if outcome["external_test_start"].startswith("READY_") else 2

if __name__ == "__main__":
    raise SystemExit(main())
