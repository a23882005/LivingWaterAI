"""Persistent audit component tests (synthetic events; no customer records)."""
import sqlite3
import pytest
from pf_audit_store import AuditStore, AuditIntegrityError

KEY=b"test-only-integrity-key-32-bytes-xxxxxxxxx"

def event(decision="DENY",actor="synthetic-a",request="request-001"):
    return {"action":"resource_read","decision":decision,"reason":"foreign_client",
            "actor_ref":actor,"request_id":request}

def test_reopen_retains_both_denials(tmp_path):
    path=tmp_path/"audit.sqlite"
    AuditStore(path,KEY).append(event(actor="synthetic-a"))
    AuditStore(path,KEY).append(event(actor="synthetic-b",request="request-002"))
    assert AuditStore(path,KEY).verify()==2

def test_detect_mutated_record(tmp_path):
    path=tmp_path/"audit.sqlite"
    store=AuditStore(path,KEY)
    store.append(event())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE audit_events SET reason='tampered' WHERE seq=1")
    with pytest.raises(AuditIntegrityError):
        store.verify()

def test_detect_deleted_middle_record(tmp_path):
    path=tmp_path/"audit.sqlite"
    store=AuditStore(path,KEY)
    for i in range(3):
        store.append(event(request=f"req-{i}"))
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM audit_events WHERE seq=2")
    with pytest.raises(AuditIntegrityError):
        store.verify()

def test_reject_asset_or_token_payload(tmp_path):
    store=AuditStore(tmp_path/"audit.sqlite",KEY)
    with pytest.raises(ValueError):
        store.append({**event(),"holdings":"confidential"})
    with pytest.raises(ValueError):
        store.append({**event(),"token":"secret"})

def test_wrong_key_detected(tmp_path):
    path=tmp_path/"audit.sqlite"
    AuditStore(path,KEY).append(event())
    with pytest.raises(AuditIntegrityError):
        AuditStore(path,b"another-test-key-of-at-least-32-bytes").verify()

def test_empty_log(tmp_path):
    assert AuditStore(tmp_path/"audit.sqlite",KEY).verify()==0

def test_subject_pseudonyms_are_stable_distinct_and_secret_free(tmp_path):
    store=AuditStore(tmp_path/"pseudonyms.sqlite",KEY)
    first=store.pseudonymize("synthetic-first")
    again=store.pseudonymize("synthetic-first")
    second=store.pseudonymize("synthetic-second")
    assert first==again and first!=second
    assert "synthetic" not in first and len(first)==36
    different=AuditStore(tmp_path/"other.sqlite",b"a-separate-valid-key-with-more-than-32-bytes")
    assert different.pseudonymize("synthetic-first")!=first

def test_subject_pseudonym_rejects_missing_identity(tmp_path):
    store=AuditStore(tmp_path/"pseudonyms.sqlite",KEY)
    for invalid in ("",None,7):
        with pytest.raises(ValueError):
            store.pseudonymize(invalid)

def test_independent_pseudonym_key_does_not_change_audit_integrity(tmp_path):
    path=tmp_path/"separated.sqlite"
    pseudo_a=b"pseudonym-key-A-at-least-32-bytes-secret"
    pseudo_b=b"pseudonym-key-B-at-least-32-bytes-secret"
    first=AuditStore(path,KEY,pseudonym_key=pseudo_a)
    actor=first.pseudonymize("verified-subject")
    first.append(event(actor=actor))
    rotated=AuditStore(path,KEY,pseudonym_key=pseudo_b)
    assert rotated.verify()==1
    assert rotated.pseudonymize("verified-subject")!=actor

def test_separate_keys_reject_equal_or_invalid_keys(tmp_path):
    with pytest.raises(ValueError):
        AuditStore(tmp_path/"bad.sqlite",KEY,pseudonym_key=KEY)
    with pytest.raises(ValueError):
        AuditStore(tmp_path/"bad2.sqlite",KEY,pseudonym_key=b"short")
