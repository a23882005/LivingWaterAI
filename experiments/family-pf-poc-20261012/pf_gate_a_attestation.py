"""Additional signed-evidence gate for external Gate A review; no deployment or release action."""
import base64
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
import ipaddress
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from pf_gate_a_checklist import evaluate_gate_a, REQUIRED_EVIDENCE

def _url(url):
    try:
        p=urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
            return False
        if p.port not in (None,443) or p.hostname.lower() == "localhost":
            return False
        if p.hostname.lower().endswith((".test",".example",".invalid",".localhost")):
            return False
        try:
            return ipaddress.ip_address(p.hostname).is_global
        except ValueError:
            return True
    except (TypeError, ValueError):
        return False

def verify_attestation(payload, signature_b64, reviewer_pubkey_b64, now=None):
    """HOLD unless an independently signed, fresh, evidence-linked record verifies.

    Trust anchor MUST be configured out-of-band by a governance authority.
    Possession of a self-generated signing key does not demonstrate external review.
    """
    hold={"state":"HOLD"}
    if not (isinstance(payload,dict) and isinstance(signature_b64,str)
            and isinstance(reviewer_pubkey_b64,str)):
        return hold
    if evaluate_gate_a(payload.get("checks")).get("state")!="PASS":
        return hold
    if payload.get("reviewer_role")!="independent_gate_a_reviewer":
        return hold
    if payload.get("environment")!="external_live_https_oauth":
        return hold
    refs=payload.get("evidence_urls")
    if not isinstance(refs,dict) or any(not _url(refs.get(k)) for k in REQUIRED_EVIDENCE):
        return hold
    try:
        instant=datetime.fromisoformat(payload["verified_at"].replace("Z","+00:00"))
        moment=now or datetime.now(timezone.utc)
        if instant.tzinfo is None or moment.tzinfo is None or instant>moment or moment-instant>timedelta(days=7):
            return hold
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(reviewer_pubkey_b64,validate=True))
        signature=base64.b64decode(signature_b64,validate=True)
        message=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        key.verify(signature,message)
    except (ValueError,TypeError,KeyError,InvalidSignature,OverflowError,AttributeError):
        return hold
    return {"state":"ATTESTED_FOR_REVIEW"}
