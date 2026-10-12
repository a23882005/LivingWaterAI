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
