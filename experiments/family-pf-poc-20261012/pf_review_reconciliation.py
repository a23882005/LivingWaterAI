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
        "disputed_checks": [],
        "unresolved_checks": list(REVIEW_CHECKS),
        "all_claims_positive": False,
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
        if verdict["reason"] in ("invalid_review_input", "incomplete_review_claim"):
            result["reason"] = "invalid_claim"
            return result
    for key in REVIEW_CHECKS:
        values = [claim["checks"].get(key) if isinstance(claim.get("checks"), dict) else None for claim in claims]
        if any(v is not True for v in values):
            result["conflicted_checks"].append(key)
        if any(v is True for v in values) and any(v is not True for v in values):
            result["disputed_checks"].append(key)
    result["all_claims_positive"] = not result["conflicted_checks"]
    result["reason"] = "claims_do_not_substitute_for_independent_evidence"
    return result
