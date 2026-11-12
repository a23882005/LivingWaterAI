"""Fail-closed independent review decision guard, not a release mechanism.

A field supplied in an input object is not an authenticated reviewer decision.
No offline payload may unlock Gate A, change WORK13, or authorize deployment.
"""
REVIEW_CHECKS=(
    "authorized_public_https_mcp",
    "real_oauth_and_resource_binding",
    "bilateral_live_tenant_denials",
    "persisted_independently_verified_audit",
    "independent_reviewer_governance_signoff",
)

def inspect_claimed_review(payload):
    outcome={"gate_a":"HOLD","work13_allowed":False,"safe_to_release":False,
             "state":"REQUIRES_OUT_OF_BAND_GOVERNANCE","unverified_checks":list(REVIEW_CHECKS)}
    if not isinstance(payload,dict):
        outcome["reason"]="invalid_review_input"
        return outcome
    checks=payload.get("checks")
    if not isinstance(checks,dict) or set(checks)!=set(REVIEW_CHECKS):
        outcome["reason"]="incomplete_review_claim"
        return outcome
    if any(checks.get(key) is not True for key in REVIEW_CHECKS):
        outcome["reason"]="unverified_review_claim"
        return outcome
    outcome["reason"]="self_report_cannot_authorize_release"
    return outcome
