"""Minimal privacy-preserving reviewer handoff; no external release authority."""
from pf_gate_a_checklist import REQUIRED_EVIDENCE
from pf_independent_review_preflight import review_preflight

def build_handoff(entries, local_paths, trusted_root, now=None):
    checked=review_preflight(entries,local_paths,trusted_root,now)
    ready=checked["state"]=="READY_FOR_INDEPENDENT_REVIEW"
    return {
        "schema_version":1,
        "review_status":"AWAITING_INDEPENDENT_WITNESS" if ready else "INCOMPLETE",
        "gate_a":"HOLD",
        "verification":"NOT_INDEPENDENTLY_VERIFIED",
        "required_evidence_categories":list(REQUIRED_EVIDENCE),
        "validated_local_files":len(REQUIRED_EVIDENCE) if ready else 0,
        "outstanding_external_checks":[
            "authorized_public_https_mcp",
            "real_oauth_and_resource_binding",
            "bilateral_live_tenant_denials",
            "persisted_independently_verified_audit",
            "independent_reviewer_governance_signoff",
        ],
        "safe_to_release":False,
    }
