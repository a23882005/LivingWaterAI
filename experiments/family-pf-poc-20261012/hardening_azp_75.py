"""PF OAuth authorized-party hardening overlay for the archived 72-test suite.
Applies only in disposable GitHub CI working tree, never to production runtime.
"""
from pathlib import Path
p=Path("pf_oauth_verifier.py")
s=p.read_text(encoding="utf-8")
old="    leeway_seconds: int = 0"
assert s.count(old)==1
s=s.replace(old,old+"\n    authorized_party: str | None = None")
old="        if len(auds)>1 and payload.get('azp') is None:\n            raise TokenRejected('azp_required')"
new="""        azp = payload.get('azp')
        if len(auds) > 1 and (not isinstance(azp, str) or not azp):
            raise TokenRejected('azp_required')
        if self.authorized_party is not None and azp != self.authorized_party:
            raise TokenRejected('bad_authorized_party')"""
assert s.count(old)==1
p.write_text(s.replace(old,new),encoding="utf-8")
t=Path("tests/test_oauth_integration.py")
s=t.read_text(encoding="utf-8")
s+="""

def test_multiple_audiences_missing_azp_rejected(env):
    c,s,sign,*_=env
    assert call(c,sign(aud=['pf-test','other']),'joseph','r-j').status_code == 401

def test_mismatched_authorized_party_rejected(env):
    c,s,sign,v,*_=env
    v.authorized_party = 'approved-client'
    assert call(c,sign(aud=['pf-test','other'],azp='unapproved-client'),'joseph','r-j').status_code == 401

def test_matching_authorized_party_accepted(env):
    c,s,sign,v,*_=env
    v.authorized_party = 'approved-client'
    assert call(c,sign(aud=['pf-test','other'],azp='approved-client'),'joseph','r-j').status_code == 200
"""
t.write_text(s,encoding="utf-8")
