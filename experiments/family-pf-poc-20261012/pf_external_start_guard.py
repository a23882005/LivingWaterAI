"""Fail-closed Family PF authorization preflight, offline only.

This checker never performs HTTP requests and never grants Gate A release authority.
"""
import argparse
import json
from pathlib import Path

REQUIRED = (
    "approved_scope_id", "environment_id", "endpoint_origin", "test_window_utc",
    "budget_approval_id", "test_executor_id", "idp_approval_id",
    "synthetic_tenant_a_id", "synthetic_tenant_b_id",
    "audit_custodian_id", "audit_store_approval_id",
    "independent_reviewer_id", "gate_governance_owner_id",
)
SECRET_MARKERS = ("token", "password", "secret", "cookie", "private_key", "authorization_header")

def assess(manifest):
    result = {"external_test_start": "BLOCKED", "gate_a": "HOLD",
              "work13_allowed": False, "missing_fields": [], "errors": []}
    if not isinstance(manifest, dict):
        result["errors"].append("manifest_must_be_object")
        return result
    if any(s in str(key).lower() for key in manifest for s in SECRET_MARKERS):
        result["errors"].append("secret_like_key_in_manifest")
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
    if manifest.get("synthetic_tenant_a_id") == manifest.get("synthetic_tenant_b_id"):
        result["errors"].append("test_tenants_must_differ")
    if manifest.get("test_executor_id") == manifest.get("independent_reviewer_id"):
        result["errors"].append("reviewer_must_be_independent")
    origin = manifest.get("endpoint_origin")
    if not isinstance(origin, str) or not origin.startswith("https://") or any(c in origin for c in ("@", "?", "#")):
        result["errors"].append("endpoint_must_be_https_origin_without_credentials")
    if not result["errors"] and not result["missing_fields"]:
        result["external_test_start"] = "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        doc = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        doc = None
    outcome = assess(doc)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if outcome["external_test_start"].startswith("READY_") else 2

if __name__ == "__main__":
    raise SystemExit(main())
