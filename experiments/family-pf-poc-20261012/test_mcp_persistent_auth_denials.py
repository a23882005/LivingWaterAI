"""Persistence tests for anonymous MCP authentication/origin rejection."""
import sqlite3
from pf_audit_store import AuditStore
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

KEY=b"synthetic-test-dedicated-key-32-bytes-value"

def test_authentication_and_origin_denials_persist(env,tmp_path):
    client,scope,sign,verifier,_=env
    path=tmp_path/"denials.sqlite"
    attach_mcp(client.app,verifier,scope,persistent_audit=AuditStore(path,KEY))
    body={"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
    wrong_origin=client.post("/mcp",json=body,headers={
        "Authorization":"Bearer "+sign("joseph"),"Origin":"https://untrusted.example.net"})
    missing=client.post("/mcp",json=body)
    bad=client.post("/mcp",json=body,headers={"Authorization":"Bearer invalid-token"})
    assert [wrong_origin.status_code,missing.status_code,bad.status_code]==[403,401,401]
    assert AuditStore(path,KEY).verify()==3
    with sqlite3.connect(path) as db:
        rows=db.execute("SELECT action,decision,reason,actor_ref FROM audit_events ORDER BY seq").fetchall()
    assert [r[2] for r in rows]==["untrusted_origin","missing_bearer","token_rejected"]
    assert all(r[1]=="DENY" and r[3]=="anonymous" for r in rows)


def test_denial_audit_survives_reopen(env,tmp_path):
    client,scope,sign,verifier,_=env
    path=tmp_path/"reopen.sqlite"
    attach_mcp(client.app,verifier,scope,persistent_audit=AuditStore(path,KEY))
    body={"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
    assert client.post("/mcp",json=body).status_code==401
    assert client.post("/mcp",json=body,headers={"Authorization":"Bearer invalid-token"}).status_code==401
    assert AuditStore(path,KEY).verify()==2
    with sqlite3.connect(path) as db:
        rows=db.execute("SELECT decision,reason FROM audit_events ORDER BY seq").fetchall()
    assert rows==[("DENY","missing_bearer"),("DENY","token_rejected")]
