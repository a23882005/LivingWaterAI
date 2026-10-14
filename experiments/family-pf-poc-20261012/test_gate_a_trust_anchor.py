"""Pinned reviewer trust tests; generated keys are not real reviewer credentials."""
import base64, hashlib, json
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pf_gate_a_trust_anchor import review_with_pinned_reviewer
from pf_gate_a_checklist import REQUIRED_EVIDENCE

NOW=datetime(2026,10,12,tzinfo=timezone.utc)

def evidence():
    private=Ed25519PrivateKey.generate()
    public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    encoded=base64.b64encode(public).decode()
    fingerprint=hashlib.sha256(public).hexdigest()
    payload={'checks':{k:True for k in REQUIRED_EVIDENCE},
             'evidence_urls':{k:'https://auditor.example.org/'+k for k in REQUIRED_EVIDENCE},
             'reviewer_role':'independent_gate_a_reviewer',
             'environment':'external_live_https_oauth','verified_at':NOW.isoformat()}
    signature=base64.b64encode(private.sign(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())).decode()
    return payload,signature,encoded,fingerprint

def test_correct_pinned_key_only_reaches_review():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,fp,NOW)['state']=='ATTESTED_FOR_REVIEW'

def test_missing_governance_fingerprint_holds():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,None,NOW)['state']=='HOLD'

def test_unapproved_self_signed_key_holds():
    p,s,key,fp=evidence()
    other=evidence()[3]
    assert review_with_pinned_reviewer(p,s,key,other,NOW)['state']=='HOLD'

def test_invalid_public_key_holds():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,'wrong',fp,NOW)['state']=='HOLD'

def test_wrong_length_fingerprint_holds():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,'123',NOW)['state']=='HOLD'

def test_signed_payload_tampering_holds():
    p,s,key,fp=evidence()
    p['environment']='not_live'
    assert review_with_pinned_reviewer(p,s,key,fp,NOW)['state']=='HOLD'

def test_nonhex_reviewer_fingerprint_holds():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,"z"*64,NOW)["state"]=="HOLD"


def test_tampered_signature_holds():
    p,s,key,fp=evidence()
    import base64
    raw=bytearray(base64.b64decode(s))
    raw[0]^=1
    changed=base64.b64encode(raw).decode()
    assert review_with_pinned_reviewer(p,changed,key,fp,NOW)["state"]=="HOLD"

def test_valid_pinned_key_never_reports_release_pass():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,fp,NOW)["state"]=="ATTESTED_FOR_REVIEW"


def test_wrong_fingerprint_rejected():
    p,s,key,fp=evidence()
    bad=('0' if fp[0]!='0' else '1')+fp[1:]
    assert review_with_pinned_reviewer(p,s,key,bad,NOW)['state']=='HOLD'

def test_uppercase_fingerprint_is_review_only():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,s,key,fp.upper(),NOW)['state']=='ATTESTED_FOR_REVIEW'


def test_unsigned_claims_with_valid_fingerprint_hold():
    p,s,key,fp=evidence()
    assert review_with_pinned_reviewer(p,'',key,fp,NOW)['state']=='HOLD'

def test_signed_claims_with_wrong_reviewer_role_hold():
    p,s,key,fp=evidence()
    p['reviewer_role']='developer'
    assert review_with_pinned_reviewer(p,s,key,fp,NOW)['state']=='HOLD'
