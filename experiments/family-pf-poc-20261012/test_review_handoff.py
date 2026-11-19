"""Only synthetic metadata; never include client information in handoff."""
from pf_review_handoff import build_handoff
from test_evidence_package_verify import make_package, NOW

def test_ready_handoff_is_not_release(tmp_path):
    entries,paths=make_package(tmp_path)
    out=build_handoff(entries,paths,tmp_path,NOW)
    assert out["review_status"]=="AWAITING_INDEPENDENT_WITNESS"
    assert out["safe_to_release"] is False
    assert out["gate_a"]=="HOLD"
    assert out["validated_local_files"]==5

def test_missing_root_incomplete(tmp_path):
    entries,paths=make_package(tmp_path)
    out=build_handoff(entries,paths,None,NOW)
    assert out["review_status"]=="INCOMPLETE"
    assert out["validated_local_files"]==0

def test_tampered_evidence_incomplete(tmp_path):
    entries,paths=make_package(tmp_path)
    paths["audit_denials_verified"].write_bytes(b"different")
    out=build_handoff(entries,paths,tmp_path,NOW)
    assert out["review_status"]=="INCOMPLETE"

def test_handoff_does_not_echo_evidence_urls_or_paths(tmp_path):
    entries,paths=make_package(tmp_path)
    entries["remote_https_reachable"]["evidence_url"]="https://auditor.example.org/review/sensitive-reference"
    out=build_handoff(entries,paths,tmp_path,NOW)
    rendered=str(out)
    assert "sensitive-reference" not in rendered
    assert str(tmp_path) not in rendered
    assert "sha256" not in rendered
