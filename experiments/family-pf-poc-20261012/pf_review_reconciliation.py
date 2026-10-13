"""Reconcile isolated evidence review claims without granting release.

Inputs are untrusted declarations, never independently authenticated records.
No file contents, credentials, or customer identifiers are emitted.
"""
from pf_review_decision_guard import REVIEW_CHECKS, inspect_claimed_review

def reconcile_review_claims(claims):
    result = {
        "gate_a": "HOLD",
        "work13_allowed": False,
        "safe_to_release": False,
        "state": "REQUIRES_INDEPENDENT_VERIFICATION",
        "claim_count": 0,
        "conflicted_checks": [],
        "unresolved_checks": list(REVIEW_CHECKS),
    }
    if not isinstance(claims, list) or not claims or len(claims) > 20:
        result["reason"] = "invalid_claim_batch"
        return result
    result["claim_count"] = len(claims)
    for claim in claims:
        if not isinstance(claim, dict):
            result["reason"] = "invalid_claim"
            return result
        verdict = inspect_claimed_review(claim)
        if verdict["reason"] == "invalid_review_input":
            result["reason"] = "invalid_claim"
            return result
    for key in REVIEW_CHECKS:
        values = [claim.get("checks", {}).get(key) for claim in claims]
        if any(v is not True for v in values):
            result["conflicted_checks"].append(key)
    result["reason"] = "claims_do_not_substitute_for_independent_evidence"
    return result
