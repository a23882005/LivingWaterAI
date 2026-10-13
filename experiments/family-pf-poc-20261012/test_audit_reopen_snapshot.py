from pf_audit_store import AuditStore

def test_empty_audit_reopen(tmp_path):
    path = tmp_path / 'audit.sqlite'
    store = AuditStore(path, b'test-key-32-bytes-and-longer-123456789')
    assert store.verify() == 0
    assert AuditStore(path, b'test-key-32-bytes-and-longer-123456789').verify() == 0
