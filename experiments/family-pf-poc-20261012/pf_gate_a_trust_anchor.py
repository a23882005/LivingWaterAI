"""Governance-pinned reviewer trust. Synthetic tests only; no Gate A release."""
import base64
import hashlib
import hmac
from pf_gate_a_attestation import verify_attestation

def review_with_pinned_reviewer(payload, signature_b64, reviewer_pubkey_b64, trusted_fingerprint, now=None):
    hold={"state":"HOLD"}
    if not isinstance(trusted_fingerprint,str) or len(trusted_fingerprint)!=64 or not all(c in "0123456789abcdefABCDEF" for c in trusted_fingerprint):
        return hold
    try:
        public_key=base64.b64decode(reviewer_pubkey_b64,validate=True)
        if len(public_key)!=32:
            return hold
        actual=hashlib.sha256(public_key).hexdigest()
    except (ValueError,TypeError):
        return hold
    if not hmac.compare_digest(actual,trusted_fingerprint.lower()):
        return hold
    return verify_attestation(payload,signature_b64,reviewer_pubkey_b64,now)
