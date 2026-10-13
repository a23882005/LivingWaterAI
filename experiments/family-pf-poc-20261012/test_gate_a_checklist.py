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
