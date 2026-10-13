"""Synthetic offline digest test coverage; no independent live witness."""
import hashlib
from pf_evidence_digest_verify import check_artifact, MAX_BYTES

def test_matching_artifact_still_holds_gate_a(tmp_path):
    p=tmp_path/"proof.bin"
    p.write_bytes(b"approved test fixture")
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    out=check_artifact(p,digest)
    assert out["match"] is True
    assert out["gate_a"]=="HOLD"

def test_modified_artifact_rejected(tmp_path):
    p=tmp_path/"proof.bin"
    p.write_bytes(b"version1")
    original=hashlib.sha256(p.read_bytes()).hexdigest()
    p.write_bytes(b"version2")
    assert check_artifact(p,original)["reason"]=="digest_mismatch"

def test_wrong_digest_syntax_rejected(tmp_path):
    p=tmp_path/"proof.bin"
    p.write_bytes(b"test")
    for digest in (None, "", "a"*63, "A"*64, "z"*64):
        out=check_artifact(p,digest)
        assert out["match"] is False
        assert out["reason"]=="invalid_digest"

def test_missing_artifact_fail_closed(tmp_path):
    out=check_artifact(tmp_path/"missing", "a"*64)
    assert out["state"]=="HOLD"
    assert out["match"] is False

def test_symlink_rejected(tmp_path):
    target=tmp_path/"target"
    target.write_bytes(b"test")
    link=tmp_path/"link"
    link.symlink_to(target)
    assert check_artifact(link,hashlib.sha256(b"test").hexdigest())["reason"]=="not_regular_file"

def test_oversized_artifact_rejected(tmp_path):
    p=tmp_path/"large.bin"
    with p.open("wb") as f:
        f.truncate(MAX_BYTES + 1)
    assert check_artifact(p, "a"*64)["reason"]=="oversized_file"
