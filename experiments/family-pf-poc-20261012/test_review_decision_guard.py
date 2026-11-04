from pf_review_decision_guard import REVIEW_CHECKS, inspect_claimed_review

def locked(result):
    assert result["gate_a"] == "HOLD"
    assert result["safe_to_release"] is False
    assert result["work13_allowed"] is False

def test_missing_input():
    locked(inspect_claimed_review(None))
    locked(inspect_claimed_review({}))

def test_complete_claim_still_requires_governance():
    checks = {key: True for key in REVIEW_CHECKS}
    result = inspect_claimed_review({"checks": checks})
    locked(result)
    assert result["reason"] == "self_report_cannot_authorize_release"

def test_missing_check():
    checks = {key: True for key in REVIEW_CHECKS}
    checks.pop("bilateral_live_tenant_denials")
    result = inspect_claimed_review({"checks": checks})
    locked(result)
    assert result["reason"] == "incomplete_review_claim"

def test_non_boolean_check():
    for value in ("true", 1, False, None):
        checks = {key: True for key in REVIEW_CHECKS}
        checks["real_oauth_and_resource_binding"] = value
        result = inspect_claimed_review({"checks": checks})
        locked(result)

def test_extra_check():
    checks = {key: True for key in REVIEW_CHECKS}
    checks["unexpected"] = True
    result = inspect_claimed_review({"checks": checks})
    locked(result)
