"""No offline result authorizes live Gate A."""
from test_evidence_package_verify import NOW, make_package
from pf_independent_review_preflight import review_preflight

def test_good_package_needs_independent_review(tmp_path):
    entries,paths=make_package(tmp_path)
    result=review_preflight(entries,paths,tmp_path,NOW)
    assert result["state"]=="READY_FOR_INDEPENDENT_REVIEW"
    assert result["gate_a"]=="HOLD"
    assert result["verification"]=="NOT_INDEPENDENTLY_VERIFIED"

def test_root_is_mandatory(tmp_path):
    entries,paths=make_package(tmp_path)
    result=review_preflight(entries,paths,None,NOW)
    assert result["state"]=="HOLD"
    assert result["reason"]=="trusted_root_required"

def test_tampered_package_stays_hold(tmp_path):
    entries,paths=make_package(tmp_path)
    paths["audit_denials_verified"].write_bytes(b"altered")
    result=review_preflight(entries,paths,tmp_path,NOW)
    assert result["state"]=="HOLD"
    assert result["reason"]=="package_not_verified"

def test_wrong_vault_stays_hold(tmp_path):
    entries,paths=make_package(tmp_path)
    vault=tmp_path/"vault"
    vault.mkdir()
    result=review_preflight(entries,paths,vault,NOW)
    assert result["state"]=="HOLD"

def test_missing_vault_stays_hold(tmp_path):
    entries,paths=make_package(tmp_path)
    result=review_preflight(entries,paths,tmp_path/"not_present",NOW)
    assert result["state"]=="HOLD"
