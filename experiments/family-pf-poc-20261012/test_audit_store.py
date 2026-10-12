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
