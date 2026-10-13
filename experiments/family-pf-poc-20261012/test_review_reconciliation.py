from pf_review_reconciliation import reconcile_review_claims
from pf_review_decision_guard import REVIEW_CHECKS

def claim(value=True):
    return {"checks": {key:value for key in REVIEW_CHECKS}}

def locked(output):
    assert output["gate_a"] == "HOLD"
    assert output["work13_allowed"] is False
    assert output["safe_to_release"] is False

def test_all_positive_claims_not_authority():
    out=reconcile_review_claims([claim(),claim()])
    locked(out)
    assert out["conflicted_checks"]==[]
    assert out["reason"]=="claims_do_not_substitute_for_independent_evidence"

def test_conflicting_claims_visible():
    first=claim()
    second=claim()
    second["checks"]["bilateral_live_tenant_denials"]=False
    out=reconcile_review_claims([first,second])
    locked(out)
    assert out["conflicted_checks"]==["bilateral_live_tenant_denials"]

def test_incomplete_claim_fail_closed():
    out=reconcile_review_claims([{"checks": {}}])
    locked(out)
    assert out["reason"]=="invalid_claim"

def test_malformed_checks_fail_closed():
    for entry in ({"checks": []}, {"checks": None}, {"checks": "yes"}):
        out=reconcile_review_claims([entry])
        locked(out)
        assert out["reason"]=="invalid_claim"

def test_invalid_batches_fail_closed():
    for entries in (None, [], {}, [None], [claim()]*21):
        out=reconcile_review_claims(entries)
        locked(out)
        assert out["reason"] in ("invalid_claim_batch","invalid_claim")

def test_no_personal_payload_reflection():
    data=claim()
    data["notes"]="private-untrusted-test-marker"
    out=reconcile_review_claims([data])
    locked(out)
    assert "private-untrusted-test-marker" not in str(out)


def test_extra_claim_category_rejected():
    entry=claim()
    entry["checks"]["unrecognized"]="yes"
    out=reconcile_review_claims([entry])
    locked(out)
    assert out["reason"]=="invalid_claim"

def test_mixed_valid_and_incomplete_batch_rejected():
    out=reconcile_review_claims([claim(), {"checks":{"real_oauth_and_resource_binding":True}}])
    locked(out)
    assert out["reason"]=="invalid_claim"
