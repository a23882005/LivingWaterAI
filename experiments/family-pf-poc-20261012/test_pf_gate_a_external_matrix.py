"""External Gate A receipt matrix stays HOLD until independently adjudicated."""
import json
from pf_gate_a_external_matrix import evaluate, load, IDS

def valid():
    return [{"evidence_id": i, "artifact_reference": "proof/2026/oct/" + i,
             "sha256": "a"*64, "reviewer_reference": "reviewer/reference/001",
             "status": "INDEPENDENTLY_REVIEWED"} for i in IDS]

def test_absent_stays_blocked():
    r=evaluate(None)
    assert r["gate_a"]=="HOLD" and not r["work13_allowed"]
    assert len(r["controls"])==9 and not r["external_evidence_verified"]

def test_all_claims_still_require_external_human_verification():
    r=evaluate(valid())
    assert not r["validation_errors"]
    assert r["gate_a"]=="HOLD"
    assert all(e["state"]=="CLAIM_SUBMITTED_FOR_INDEPENDENT_VERIFICATION" for e in r["controls"])
    assert "manual_reviewer_action" in r

def test_missing_and_duplicate_controls_fail_closed():
    x=valid()[:]
    x[-1]=dict(x[0])
    r=evaluate(x)
    assert "invalid_or_duplicate_evidence_id" in r["validation_errors"]
    assert "missing_control" in r["validation_errors"]

def test_unexpected_field_rejected():
    x=valid();x[0]["oauth_token"]="DO_NOT_EXPOSE"
    assert "invalid_entry_schema" in evaluate(x)["validation_errors"]
    assert "DO_NOT_EXPOSE" not in json.dumps(evaluate(x))

def test_malformed_sha_rejected():
    x=valid();x[3]["sha256"]="not_a_real_digest"
    assert "invalid_sha256" in evaluate(x)["validation_errors"]

def test_missing_independent_review_rejected():
    x=valid();x[4]["status"]="PASS"
    assert "independent_review_not_confirmed" in evaluate(x)["validation_errors"]

def test_suspicious_reference_rejected():
    x=valid();x[0]["artifact_reference"]="Bearer abc123"
    assert "invalid_artifact_reference" in evaluate(x)["validation_errors"]

def test_manifest_duplicate_key_rejected(tmp_path):
    p=tmp_path/"evidence.json";p.write_text('[{"evidence_id":"EA-01","evidence_id":"EA-02"}]')
    import pytest
    with pytest.raises(ValueError,match="duplicate_manifest_key"):load(p)

def test_manifest_oversize_rejected(tmp_path):
    p=tmp_path/"evidence.json";p.write_bytes(b" "*65537)
    import pytest
    with pytest.raises(ValueError,match="oversized_evidence_manifest"):load(p)

def test_empty_record_and_wrong_type_rejected():
    assert evaluate({})["gate_a"]=="HOLD"
    assert "invalid_entry_schema" in evaluate([{} for _ in IDS])["validation_errors"]

def test_cli_writes_only_safe_blocked_status(tmp_path,monkeypatch):
    import sys
    from pf_gate_a_external_matrix import main
    out=tmp_path/"matrix.json"
    monkeypatch.setattr(sys,"argv",["script","--output",str(out)])
    assert main()==0
    r=json.loads(out.read_text())
    assert r["gate_a"]=="HOLD" and r["work13_allowed"] is False
