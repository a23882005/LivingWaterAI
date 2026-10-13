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


def test_empty_file_hash_match_still_hold(tmp_path):
    p=tmp_path/"empty.bin"
    p.write_bytes(b"")
    out=check_artifact(p,hashlib.sha256(b"").hexdigest())
    assert out["match"] is True
    assert out["gate_a"]=="HOLD"

def test_directory_rejected(tmp_path):
    out=check_artifact(tmp_path,"a"*64)
    assert out["reason"]=="not_regular_file"
    assert out["match"] is False

def test_file_under_size_cap_matches(tmp_path):
    p=tmp_path/"small.bin"
    p.write_bytes(b"x"*1024)
    out=check_artifact(p,hashlib.sha256(p.read_bytes()).hexdigest())
    assert out["reason"]=="digest_match"
    assert out["gate_a"]=="HOLD"

def test_artifact_digest_result_never_authorizes_release(tmp_path):
    p=tmp_path/"evidence.bin"
    p.write_bytes(b"synthetic")
    out=check_artifact(p,hashlib.sha256(b"synthetic").hexdigest())
    assert out["match"] is True
    assert out["state"]=="HOLD"
    assert out["gate_a"]=="HOLD"

def test_mismatched_digest_stays_hold(tmp_path):
    p=tmp_path/"evidence.bin"
    p.write_bytes(b"new")
    out=check_artifact(p,hashlib.sha256(b"old").hexdigest())
    assert out["match"] is False
    assert out["gate_a"]=="HOLD"


def test_fifo_is_not_read_as_evidence(tmp_path):
    import os
    import pytest
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unsupported")
    p=tmp_path/"pipe"
    os.mkfifo(p)
    out=check_artifact(p,"a"*64)
    assert out["match"] is False
    assert out["gate_a"]=="HOLD"

def test_digest_bytes_type_is_rejected(tmp_path):
    p=tmp_path/"proof.bin"
    p.write_bytes(b"payload")
    assert check_artifact(p,b"a"*64)["reason"]=="invalid_digest"

def test_exact_maximum_size_is_permitted(tmp_path):
    p=tmp_path/"boundary.bin"
    with p.open("wb") as stream:
        stream.truncate(MAX_BYTES)
    digest=hashlib.sha256()
    with p.open("rb") as stream:
        while block:=stream.read(65536):
            digest.update(block)
    result=check_artifact(p,digest.hexdigest())
    assert result["match"] is True
    assert result["gate_a"]=="HOLD"
