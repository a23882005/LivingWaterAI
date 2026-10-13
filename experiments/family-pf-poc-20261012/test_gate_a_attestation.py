"""Signed Gate A attestation tests are synthetic; do not grant release."""
import base64
import json
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pf_gate_a_attestation import verify_attestation
from pf_gate_a_checklist import REQUIRED_EVIDENCE

NOW=datetime(2026,10,12,tzinfo=timezone.utc)

def fixture():
    private=Ed25519PrivateKey.generate()
    pub=base64.b64encode(private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    payload={"checks":{k:True for k in REQUIRED_EVIDENCE},
        "evidence_urls":{k:"https://auditor.example.org/evidence/"+k for k in REQUIRED_EVIDENCE},
        "reviewer_role":"independent_gate_a_reviewer",
        "environment":"external_live_https_oauth",
        "verified_at":NOW.isoformat()}
    return private,pub,payload

def sign(priv,p):
    msg=json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return base64.b64encode(priv.sign(msg)).decode()

def test_boolean_flags_alone_cannot_pass():
    assert verify_attestation({"checks":{k:True for k in REQUIRED_EVIDENCE}}, "", "",NOW)["state"]=="HOLD"

def test_valid_synthetic_signature_is_review_only():
    priv,pub,p=fixture()
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="ATTESTED_FOR_REVIEW"

def test_tampered_evidence_rejected():
    priv,pub,p=fixture()
    sig=sign(priv,p)
    p["evidence_urls"]["audit_denials_verified"]="https://attacker.example.org/fake"
    assert verify_attestation(p,sig,pub,NOW)["state"]=="HOLD"

def test_wrong_reviewer_key_rejected():
    priv,pub,p=fixture()
    another=Ed25519PrivateKey.generate()
    bad=base64.b64encode(another.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    assert verify_attestation(p,sign(priv,p),bad,NOW)["state"]=="HOLD"

def test_expired_record_rejected():
    priv,pub,p=fixture()
    p["verified_at"]=(NOW-timedelta(days=8)).isoformat()
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_future_record_rejected():
    priv,pub,p=fixture()
    p["verified_at"]=(NOW+timedelta(days=1)).isoformat()
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_test_domain_evidence_rejected():
    priv,pub,p=fixture()
    p["evidence_urls"]["remote_https_reachable"]="https://fake.example.test/proof"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_missing_negative_test_proof_rejected():
    priv,pub,p=fixture()
    p["checks"]["cross_client_negative_verified"]=False
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_unknown_reviewer_role_rejected():
    priv,pub,p=fixture()
    p["reviewer_role"]="self_signed_by_developer"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_nonsensical_signature_rejected():
    priv,pub,p=fixture()
    assert verify_attestation(p,"not base64!",pub,NOW)["state"]=="HOLD"

def test_signed_private_evidence_url_is_not_sufficient():
    priv,pub,p=fixture()
    p["evidence_urls"]["remote_https_reachable"]="https://127.0.0.1/proof"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_signed_localhost_url_is_not_sufficient():
    priv,pub,p=fixture()
    p["evidence_urls"]["external_oauth_login_verified"]="https://localhost/proof"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_signed_evidence_with_nonstandard_port_is_rejected():
    priv,pub,p=fixture()
    p["evidence_urls"]["audit_denials_verified"]="https://auditor.example.org:8443/proof"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_naive_validation_clock_holds():
    priv,pub,p=fixture()
    naive=datetime(2026,10,12)
    assert verify_attestation(p,sign(priv,p),pub,naive)["state"]=="HOLD"

def test_non_string_timestamp_holds():
    priv,pub,p=fixture()
    p["verified_at"]=123
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"


def test_valid_signature_with_wrong_environment_holds():
    priv,pub,p=fixture()
    p["environment"]="synthetic_ci"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_signature_with_missing_evidence_url_holds():
    priv,pub,p=fixture()
    del p["evidence_urls"]["audit_denials_verified"]
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_signature_with_untrusted_plain_http_url_holds():
    priv,pub,p=fixture()
    p["evidence_urls"]["remote_https_reachable"]="http://auditor.example.org/proof"
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="HOLD"

def test_complete_signed_record_never_becomes_gate_pass():
    priv,pub,p=fixture()
    assert verify_attestation(p,sign(priv,p),pub,NOW)["state"]=="ATTESTED_FOR_REVIEW"
