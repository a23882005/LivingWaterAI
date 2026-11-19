"""Synthetic package verification does not constitute Gate A approval."""
import hashlib
from datetime import datetime, timezone
from pf_evidence_package_verify import verify_package
from pf_gate_a_checklist import REQUIRED_EVIDENCE

NOW=datetime(2026,10,14,tzinfo=timezone.utc)

def make_package(tmp_path):
    records={}
    paths={}
    for key in REQUIRED_EVIDENCE:
        path=tmp_path/(key+".bin")
        data=("synthetic:"+key).encode()
        path.write_bytes(data)
        paths[key]=path
        records[key]={"result":"OBSERVED","evidence_url":"https://auditor.example.org/review/"+key,
                     "witness_role":"independent_security_reviewer",
                     "observed_at":NOW.isoformat(),"sha256":hashlib.sha256(data).hexdigest()}
    return records,paths

def test_matching_synthetic_package_never_releases(tmp_path):
    entries,paths=make_package(tmp_path)
    result=verify_package(entries,paths,NOW)
    assert result["state"]=="FILES_MATCH_INVENTORY"
    assert result["gate_a"]=="HOLD"
    assert result["verification"]=="NOT_INDEPENDENTLY_VERIFIED"
    assert len(result["artifacts"])==len(REQUIRED_EVIDENCE)

def test_tampered_artifact_holds(tmp_path):
    entries,paths=make_package(tmp_path)
    paths["audit_denials_verified"].write_bytes(b"tampered")
    result=verify_package(entries,paths,NOW)
    assert result["state"]=="HOLD"
    assert result["artifacts"]["audit_denials_verified"]=="digest_mismatch"

def test_missing_artifact_holds(tmp_path):
    entries,paths=make_package(tmp_path)
    paths["remote_https_reachable"].unlink()
    assert verify_package(entries,paths,NOW)["state"]=="HOLD"

def test_missing_path_mapping_holds(tmp_path):
    entries,paths=make_package(tmp_path)
    del paths["external_oauth_login_verified"]
    assert verify_package(entries,paths,NOW)["state"]=="HOLD"

def test_invalid_inventory_holds_without_trusting_files(tmp_path):
    entries,paths=make_package(tmp_path)
    entries["cross_client_negative_verified"]["result"]="PLANNED"
    assert verify_package(entries,paths,NOW)["state"]=="HOLD"


def test_duplicate_artifact_mapping_is_rejected(tmp_path):
    entries,paths=make_package(tmp_path)
    first=REQUIRED_EVIDENCE[0]
    second=REQUIRED_EVIDENCE[1]
    paths[second]=paths[first]
    entries[second]["sha256"]=entries[first]["sha256"]
    result=verify_package(entries,paths,NOW)
    assert result["state"]=="HOLD"
    assert result["artifacts"][second]=="duplicate_artifact_path"
    assert result["gate_a"]=="HOLD"

def test_extra_path_mapping_is_rejected(tmp_path):
    entries,paths=make_package(tmp_path)
    paths["unexpected"]=tmp_path/"extra"
    assert verify_package(entries,paths,NOW)["state"]=="HOLD"

def test_non_path_mapping_value_rejected(tmp_path):
    entries,paths=make_package(tmp_path)
    paths[REQUIRED_EVIDENCE[0]]=123
    assert verify_package(entries,paths,NOW)["state"]=="HOLD"


def test_identical_digest_across_different_files_rejected(tmp_path):
    entries,paths=make_package(tmp_path)
    first,second=REQUIRED_EVIDENCE[:2]
    paths[second].write_bytes(paths[first].read_bytes())
    entries[second]["sha256"]=entries[first]["sha256"]
    result=verify_package(entries,paths,NOW)
    assert result["state"]=="HOLD"
    assert result["artifacts"][second]=="duplicate_artifact_digest"

def test_invalid_path_with_null_byte_rejected(tmp_path):
    entries,paths=make_package(tmp_path)
    paths[REQUIRED_EVIDENCE[0]]="invalid"+chr(0)+"path"
    result=verify_package(entries,paths,NOW)
    assert result["state"]=="HOLD"
    assert result["artifacts"][REQUIRED_EVIDENCE[0]]=="invalid_artifact_path"

def test_empty_path_map_is_hold(tmp_path):
    entries,_=make_package(tmp_path)
    assert verify_package(entries,{},NOW)["gate_a"]=="HOLD"


def test_package_with_trusted_root_matches(tmp_path):
    entries,paths=make_package(tmp_path)
    result=verify_package(entries,paths,NOW,trusted_root=tmp_path)
    assert result["state"]=="FILES_MATCH_INVENTORY"
    assert result["gate_a"]=="HOLD"

def test_artifact_outside_trusted_root_fails_closed(tmp_path):
    vault=tmp_path/"vault"
    vault.mkdir()
    entries,paths=make_package(tmp_path)
    result=verify_package(entries,paths,NOW,trusted_root=vault)
    assert result["state"]=="HOLD"
    assert result["artifacts"][REQUIRED_EVIDENCE[0]]=="outside_trusted_root"

def test_missing_trusted_root_fails_closed(tmp_path):
    entries,paths=make_package(tmp_path)
    result=verify_package(entries,paths,NOW,trusted_root=tmp_path/"missing")
    assert result["state"]=="HOLD"
    assert result["path_policy"]=="invalid_trusted_root"

def test_trusted_root_symlink_escape_rejected(tmp_path):
    vault=tmp_path/"vault"
    vault.mkdir()
    outside=tmp_path/"outside"
    outside.mkdir()
    entries,paths=make_package(tmp_path)
    first=REQUIRED_EVIDENCE[0]
    destination=outside/"proof.bin"
    destination.write_bytes(paths[first].read_bytes())
    alias=vault/"proof-link"
    alias.symlink_to(destination)
    paths[first]=alias
    result=verify_package(entries,paths,NOW,trusted_root=vault)
    assert result["state"]=="HOLD"
    assert result["artifacts"][first]=="outside_trusted_root"
