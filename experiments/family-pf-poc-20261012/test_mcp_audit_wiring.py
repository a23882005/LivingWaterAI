"""MCP request-path audit wiring tests; synthetic subjects and resources only."""
import sqlite3
import pytest
from pf_audit_store import AuditStore
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

KEY=b"synthetic-test-dedicated-key-32-bytes-value"

def test_mcp_both_cross_client_denials_persist(env,tmp_path):
    client,scope,sign,verifier,_=env
    db=tmp_path/"mcp_audit.sqlite"
    store=AuditStore(db,KEY)
    attach_mcp(client.app,verifier,scope,persistent_audit=store)
    cases=[
        ("joseph","mou","r-m",True),
        ("mou","joseph","r-j",True),
        ("joseph","joseph","r-j",False),
        ("mou","mou","r-m",False)
    ]
    for sub,client_id,res,denied in cases:
        r=client.post("/mcp",headers={"Authorization":"Bearer "+sign(sub)},
            json={"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"pf_read_resource","arguments":{
                "active_client_id":client_id,"resource_id":res}}})
        assert r.status_code==200
        assert bool(r.json()["result"].get("isError")) is denied
        if denied:
            assert "synthetic-j" not in r.text and "synthetic-m" not in r.text
    assert AuditStore(db,KEY).verify()==4
    with sqlite3.connect(db) as con:
        rows=con.execute("SELECT decision,reason,actor_ref FROM audit_events ORDER BY seq").fetchall()
    assert [row[0] for row in rows]==["DENY","DENY","ALLOW","ALLOW"]
    assert all(row[2]=="synthetic_subject" for row in rows)

class BrokenAudit:
    def append(self,event):
        raise OSError("storage unavailable")

def test_mcp_audit_write_failure_blocks_protected_output(env):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope,persistent_audit=BrokenAudit())
    with pytest.raises(OSError):
        client.post("/mcp",headers={"Authorization":"Bearer "+sign("joseph")},
            json={"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"pf_read_resource","arguments":{
                "active_client_id":"joseph","resource_id":"r-j"}}})
