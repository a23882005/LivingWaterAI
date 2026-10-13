"""Gate A is HOLD without independent remote evidence."""
from pf_gate_a_checklist import evaluate_gate_a, REQUIRED_EVIDENCE

def test_no_evidence_holds():
    assert evaluate_gate_a(None)["state"] == "HOLD"

def test_local_ci_success_alone_holds():
    assert evaluate_gate_a({"local_ci_passed":True})["state"] == "HOLD"

def test_remote_endpoint_alone_holds():
    assert evaluate_gate_a({"remote_https_reachable":True})["state"] == "HOLD"

def test_missing_audit_proof_holds():
    evidence={key:True for key in REQUIRED_EVIDENCE}
    evidence["audit_denials_verified"]=False
    assert evaluate_gate_a(evidence)["state"] == "HOLD"

def test_non_boolean_claim_cannot_count_as_proof():
    evidence={key:True for key in REQUIRED_EVIDENCE}
    evidence["external_oauth_login_verified"]="yes"
    assert evaluate_gate_a(evidence)["state"] == "HOLD"

def test_complete_evidence_checklist_is_eligible_for_review():
    evidence={key:True for key in REQUIRED_EVIDENCE}
    assert evaluate_gate_a(evidence)=={"state":"READY_FOR_REVIEW","missing":[]}


def test_all_evidence_false_remains_hold():
    evidence = {key: False for key in REQUIRED_EVIDENCE}
    outcome = evaluate_gate_a(evidence)
    assert outcome["state"] == "HOLD"
    assert set(outcome["missing"]) == set(REQUIRED_EVIDENCE)

def test_missing_one_required_evidence_is_hold():
    for missing_key in REQUIRED_EVIDENCE:
        evidence = {key: True for key in REQUIRED_EVIDENCE}
        del evidence[missing_key]
        outcome = evaluate_gate_a(evidence)
        assert outcome == {"state": "HOLD", "missing": [missing_key]}

def test_all_truthy_strings_never_substitute_for_boolean_true():
    evidence = {key: "true" for key in REQUIRED_EVIDENCE}
    assert evaluate_gate_a(evidence)["state"] == "HOLD"

def test_extra_unrelated_claim_does_not_authorize_release():
    evidence = {key: True for key in REQUIRED_EVIDENCE}
    evidence["local_ci_passed"] = True
    evidence["release_approved"] = True
    assert evaluate_gate_a(evidence)["state"] == "READY_FOR_REVIEW"


def test_evidence_null_or_zero_not_accepted():
    for invalid in (None, 0, [], {}):
        evidence={key:True for key in REQUIRED_EVIDENCE}
        evidence["audit_denials_verified"]=invalid
        assert evaluate_gate_a(evidence)["state"]=="HOLD"

def test_no_evidence_and_empty_dict_same_required_missing():
    assert evaluate_gate_a({})=={"state":"HOLD","missing":list(REQUIRED_EVIDENCE)}
