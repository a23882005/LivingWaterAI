"""Offline Gate A evidence workplan, derived from authorization manifest status.

No HTTP, no credentials, no approval authority. Avoid exposing manifest values.
"""
import argparse
import json
from pathlib import Path
from pf_external_start_guard import assess, load_manifest

REQUIRED_EVIDENCE = (
    ("EA-01", "Public HTTPS MCP endpoint: independent TLS and host verification"),
    ("EA-02", "Real IdP configuration: token issuer, audience, scope and JWKS"),
    ("EA-03", "Synthetic tenant A: authorized access using issued credential"),
    ("EA-04", "Synthetic tenant B: authorized access using separate credential"),
    ("EA-05", "A principal denied access to tenant B (both resource and active tenant)"),
    ("EA-06", "B principal denied access to tenant A (both resource and active tenant)"),
    ("EA-07", "Audit events retained in independent durable evidence store"),
    ("EA-08", "Independent custodian integrity verification and review"),
    ("EA-09", "Separate governance owner written Gate A release decision"),
)

def build_plan(manifest):
    decision = assess(manifest)
    return {
        "schema": "family-pf-gate-a-workplan-v1",
        "authorization_preflight": decision["external_test_start"],
        "gate_a": "HOLD",
        "work13_allowed": False,
        "remote_tests_executed": False,
        "authorization_issues": sorted(set(decision["errors"])),
        "missing_approval_fields": sorted(set(decision["missing_fields"])),
        "evidence_required": [
            {"id": evidence_id, "task": description, "state": "NOT_VERIFIED"}
            for evidence_id, description in REQUIRED_EVIDENCE
        ],
        "operator_step": (
            "Obtain authorized operator review; only then conduct separately approved external tests"
            if decision["external_test_start"] == "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
            else "Resolve missing approvals and invalid authorization manifest before external testing"
        ),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.manifest is None:
        plan = build_plan({})
    else:
        try:
            plan = build_plan(load_manifest(args.manifest))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            plan = build_plan({})
            plan["authorization_issues"] = ["invalid_manifest_file"]
    blob = json.dumps(plan, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(blob, encoding="utf-8")
    else:
        print(blob, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
