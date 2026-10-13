from pf_audit_store import AuditStore

def test_empty_audit_reopen(tmp_path):
    path = tmp_path / 'audit.sqlite'
    store = AuditStore(path, b'test-key-32-bytes-and-longer-123456789')
    assert store.verify() == 0
    assert AuditStore(path, b'test-key-32-bytes-and-longer-123456789').verify() == 0

def test_populated_audit_after_reopen(tmp_path):
    path = tmp_path / 'full.sqlite'
    key = b'test-key-32-bytes-and-longer-123456789'
    first = AuditStore(path, key)
    first.append({'action': 'read', 'decision': 'DENY', 'reason': 'test', 'actor_ref': 'sample', 'request_id': 'r1'})
    assert AuditStore(path, key).verify() == 1
