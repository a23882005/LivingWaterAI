"""Live TCP loopback transport smoke tests. Synthetic keys, no public deployment."""
import socket
import threading
import time
from contextlib import contextmanager

import httpx
import uvicorn
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env


@contextmanager
def live_server(env):
    client, scope, sign, verifier, _ = env
    attach_mcp(client.app, verifier, scope)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    config = uvicorn.Config(client.app, log_level="error", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        until = time.monotonic() + 5
        while not server.started and time.monotonic() < until:
            time.sleep(.01)
        assert server.started, "Loopback server failed to start"
        yield f"http://127.0.0.1:{port}", sign, scope
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive(), "Loopback server failed to terminate"


def invoke(base, token=None, active="joseph", resource="r-j"):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return httpx.post(base + "/mcp", headers=headers,
        json={"jsonrpc":"2.0","id":1,"method":"tools/call",
              "params":{"name":"pf_read_resource",
                        "arguments":{"active_client_id":active,"resource_id":resource}}},
        timeout=5)


def test_real_tcp_loopback_oauth_challenge(env):
    with live_server(env) as (base, sign, scope):
        result = invoke(base)
        assert result.status_code == 401
        assert "resource_metadata=" in result.headers["WWW-Authenticate"]
        assert scope.audit[-1]["decision"] == "DENY"


def test_real_tcp_loopback_authorized_resource(env):
    with live_server(env) as (base, sign, scope):
        result = invoke(base, sign("joseph"))
        assert result.status_code == 200
        assert result.json()["result"]["content"][0]["text"] == "synthetic-j"


def test_real_tcp_loopback_cross_client_denial(env):
    with live_server(env) as (base, sign, scope):
        result = invoke(base, sign("joseph"), active="mou", resource="r-m")
        assert result.status_code == 200
        assert result.json()["result"]["isError"] is True
        assert "synthetic-m" not in result.text
        assert scope.audit[-1]["decision"] == "DENY"


def test_real_tcp_loopback_second_identity_authorized(env):
    """Second synthetic test tenant must independently access its own fixture."""
    with live_server(env) as (base, sign, scope):
        response = invoke(base, sign("mou"), active="mou", resource="r-m")
        assert response.status_code == 200
        assert response.json()["result"]["content"][0]["text"] == "synthetic-m"
        assert scope.audit[-1]["decision"] == "ALLOW"


def test_real_tcp_loopback_reverse_cross_client_denial(env):
    """Reject cross-tenant access in the B-to-A direction, not only A-to-B."""
    with live_server(env) as (base, sign, scope):
        response = invoke(base, sign("mou"), active="joseph", resource="r-j")
        assert response.status_code == 200
        assert response.json()["result"]["isError"] is True
        assert "synthetic-j" not in response.text
        assert scope.audit[-1]["decision"] == "DENY"


def test_real_tcp_loopback_switching_active_tenant_cannot_escalate(env):
    """Requests by the same principal must re-authorize every tenant switch."""
    with live_server(env) as (base, sign, scope):
        token = sign("joseph")
        allowed = invoke(base, token, active="joseph", resource="r-j")
        denied = invoke(base, token, active="mou", resource="r-m")
        allowed_again = invoke(base, token, active="joseph", resource="r-j")
        assert allowed.status_code == denied.status_code == allowed_again.status_code == 200
        assert allowed.json()["result"]["content"][0]["text"] == "synthetic-j"
        assert denied.json()["result"]["isError"] is True
        assert "synthetic-m" not in denied.text
        assert allowed_again.json()["result"]["content"][0]["text"] == "synthetic-j"
        assert [event["decision"] for event in scope.audit[-3:]] == ["ALLOW", "DENY", "ALLOW"]

def test_loopback_missing_token_does_not_expose_any_tenant_resource(env):
    with live_server(env) as (base, sign, scope):
        for active, resource in (("joseph", "r-j"), ("mou", "r-m")):
            response = invoke(base, active=active, resource=resource)
            assert response.status_code == 401
            assert "synthetic-j" not in response.text
            assert "synthetic-m" not in response.text
        assert [entry["decision"] for entry in scope.audit[-2:]] == ["DENY", "DENY"]

def test_loopback_wrong_tenant_resource_even_if_active_tenant_matches(env):
    with live_server(env) as (base, sign, scope):
        cases = [
            (sign("joseph"), "joseph", "r-m", "synthetic-m"),
            (sign("mou"), "mou", "r-j", "synthetic-j"),
        ]
        for token, active, resource, secret in cases:
            response = invoke(base, token, active=active, resource=resource)
            assert response.status_code == 200
            assert response.json()["result"]["isError"] is True
            assert secret not in response.text
        assert [event["decision"] for event in scope.audit[-2:]] == ["DENY", "DENY"]

def test_loopback_alternating_principals_stays_isolated(env):
    with live_server(env) as (base, sign, scope):
        first = invoke(base, sign("joseph"), active="joseph", resource="r-j")
        second = invoke(base, sign("mou"), active="mou", resource="r-m")
        third = invoke(base, sign("joseph"), active="mou", resource="r-m")
        fourth = invoke(base, sign("mou"), active="joseph", resource="r-j")
        assert [first.status_code, second.status_code, third.status_code, fourth.status_code] == [200]*4
        assert first.json()["result"]["content"][0]["text"] == "synthetic-j"
        assert second.json()["result"]["content"][0]["text"] == "synthetic-m"
        assert third.json()["result"]["isError"] is True
        assert fourth.json()["result"]["isError"] is True
        assert [event["decision"] for event in scope.audit[-4:]] == ["ALLOW", "ALLOW", "DENY", "DENY"]


def test_loopback_browser_origin_is_rejected(env):
    with live_server(env) as (base, sign, scope):
        response = httpx.post(base + "/mcp",
            headers={"Authorization": "Bearer " + sign("joseph"),
                     "Origin": "https://untrusted.example.test"},
            json={"jsonrpc": "2.0", "id": 201, "method": "tools/call",
                  "params": {"name": "pf_read_resource",
                             "arguments": {"active_client_id": "joseph", "resource_id": "r-j"}}},
            timeout=5)
        assert response.status_code == 403
        assert "synthetic-j" not in response.text
        assert scope.audit[-1]["decision"] == "DENY"


def test_loopback_non_bearer_auth_is_rejected(env):
    with live_server(env) as (base, sign, scope):
        response = httpx.post(base + "/mcp",
            headers={"Authorization": "Basic dummy"},
            json={"jsonrpc": "2.0", "id": 202, "method": "tools/list"},
            timeout=5)
        assert response.status_code == 401
        assert "resource_metadata=" in response.headers["WWW-Authenticate"]
        assert scope.audit[-1]["decision"] == "DENY"


def test_loopback_tool_arguments_reject_unexpected_key(env):
    with live_server(env) as (base, sign, scope):
        response = httpx.post(base + "/mcp",
            headers={"Authorization": "Bearer " + sign("joseph")},
            json={"jsonrpc": "2.0", "id": 203, "method": "tools/call",
                  "params": {"name": "pf_read_resource",
                             "arguments": {"active_client_id": "joseph",
                                           "resource_id": "r-j",
                                           "unexpected": "mou"}}},
            timeout=5)
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32602
        assert "synthetic-j" not in response.text


def test_loopback_unknown_tool_never_reads_resource(env):
    with live_server(env) as (base, sign, scope):
        before = len(scope.audit)
        response = httpx.post(base + "/mcp",
            headers={"Authorization": "Bearer " + sign("joseph")},
            json={"jsonrpc": "2.0", "id": 301, "method": "tools/call",
                  "params": {"name": "pf_admin_read_all",
                             "arguments": {"active_client_id": "joseph", "resource_id": "r-j"}}},
            timeout=5)
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32602
        assert "synthetic-j" not in response.text
        assert len(scope.audit) == before


def test_loopback_invalid_rpc_envelope_fails_without_data(env):
    with live_server(env) as (base, sign, scope):
        before = len(scope.audit)
        response = httpx.post(base + "/mcp",
            headers={"Authorization": "Bearer " + sign("joseph")},
            json={"jsonrpc": "1.0", "id": 302, "method": "tools/call",
                  "params": {"name": "pf_read_resource",
                             "arguments": {"active_client_id": "joseph", "resource_id": "r-j"}}},
            timeout=5)
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32600
        assert "synthetic-j" not in response.text
        assert len(scope.audit) == before
