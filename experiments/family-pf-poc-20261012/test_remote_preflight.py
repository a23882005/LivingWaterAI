import httpx
import pytest
from pf_remote_preflight import validated_url,verify_remote_metadata

URL="https://pf.example.com/mcp"
META="https://pf.example.com/.well-known/oauth-protected-resource"

def test_reject_non_https():
    with pytest.raises(ValueError):validated_url("http://pf.example.com/mcp")

def test_reject_placeholder():
    with pytest.raises(ValueError):validated_url("https://localhost/mcp")

def test_reject_password():
    with pytest.raises(ValueError):validated_url("https://user:pass@pf.example.com/mcp")

def test_reject_ipv6_loopback():
    with pytest.raises(ValueError):
        validated_url("https://[::1]/mcp")

def test_reject_nonstandard_port():
    with pytest.raises(ValueError):
        validated_url("https://pf.example.com:8443/mcp")

def test_reject_wrong_route():
    with pytest.raises(ValueError):validated_url("https://pf.example.com/admin")

def test_readonly_metadata_never_approves_gate():
    def handle(request):
        assert request.method=="GET" and str(request.url)==META
        assert "authorization" not in request.headers
        return httpx.Response(200,json={"resource":URL,"authorization_servers":["https://auth.example.com"]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        state=verify_remote_metadata(URL,c)
    assert state["metadata"]=="DISCOVERABLE"
    assert state["external_oauth_login"]=="NOT_TESTED"
    assert state["gate_a"]=="HOLD"

def test_mismatched_resource_rejected():
    with httpx.Client(transport=httpx.MockTransport(
        lambda req:httpx.Response(200,json={"resource":"https://other.example.com/mcp","authorization_servers":["https://auth.example.com"]}))) as c:
        assert verify_remote_metadata(URL,c)["metadata"]=="NOT_VERIFIED"

def test_redirect_not_accepted():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={"Location":"https://redirect.example.com"})),follow_redirects=False) as c:
        assert verify_remote_metadata(URL,c)["metadata"]=="NOT_VERIFIED"

def test_no_provider_is_not_oauth_success():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={"resource":URL,"authorization_servers":[]}))) as c:
        assert verify_remote_metadata(URL,c)["metadata"]=="NOT_VERIFIED"

def test_private_ipv4_rejected():
    with pytest.raises(ValueError):
        validated_url("https://192.168.1.10/mcp")

def test_link_local_ipv4_rejected():
    with pytest.raises(ValueError):
        validated_url("https://169.254.169.254/mcp")

def test_private_ipv6_rejected():
    with pytest.raises(ValueError):
        validated_url("https://[fd00::1]/mcp")

@pytest.mark.parametrize("issuer", [
    "https://user:secret@auth.example.com",
    "https://auth.example.com?token=secret",
    "https://auth.example.com#fragment",
    "https://",
])
def test_bad_oauth_issuer_never_discovers(issuer):
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200,json={
            "resource":URL,"authorization_servers":[issuer]}))) as c:
        result=verify_remote_metadata(URL,c)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"

@pytest.mark.parametrize("issuer", [
    "https://auth.example.com:8443",
    "https://auth.example.com:99999",
])
def test_invalid_issuer_ports_keep_gate_on_hold(issuer):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200,json={
            "resource":URL,"authorization_servers":[issuer]}))) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"

@pytest.mark.parametrize("issuer", [
    "https://localhost",
    "https://127.0.0.1",
    "https://169.254.169.254",
    "https://[fd00::1]",
    "https://idp.example.test",
])
def test_private_issuer_addresses_fail_closed(issuer):
    with httpx.Client(transport=httpx.MockTransport(
        lambda req:httpx.Response(200,json={"resource":URL,
            "authorization_servers":[issuer]}))) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"


def test_server_error_keeps_gate_on_hold():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        result = verify_remote_metadata(URL, client)
    assert result['metadata'] == 'NOT_VERIFIED'
    assert result['gate_a'] == 'HOLD'

def test_malformed_metadata_keeps_gate_on_hold():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='invalid json'))) as client:
        result = verify_remote_metadata(URL, client)
    assert result['metadata'] == 'NOT_VERIFIED'
    assert result['gate_a'] == 'HOLD'

def test_empty_metadata_keeps_gate_on_hold():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))) as client:
        result = verify_remote_metadata(URL, client)
    assert result['metadata'] == 'NOT_VERIFIED'
    assert result['gate_a'] == 'HOLD'

def test_network_timeout_keeps_gate_on_hold():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic timeout")
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        result = verify_remote_metadata(URL, client)
    assert result["metadata"] == "NOT_VERIFIED"
    assert result["gate_a"] == "HOLD"

def test_metadata_probe_sends_no_authorization():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"resource":URL, "authorization_servers":["https://auth.example.com"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = verify_remote_metadata(URL, client)
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == META
    assert "authorization" not in seen[0].headers
    assert result["gate_a"] == "HOLD"

def test_multiple_authorization_servers_fail_closed():
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"resource":URL, "authorization_servers":["https://one.example.com", "https://two.example.com"]})
    )) as client:
        result = verify_remote_metadata(URL, client)
    assert result["metadata"] == "NOT_VERIFIED"
    assert result["gate_a"] == "HOLD"


@pytest.mark.parametrize("url", [
    "https://pf.example.com/mcp?access_token=secret",
    "https://pf.example.com/mcp#fragment",
    "https://user@pf.example.com/mcp",
    "https://pf.example.com:8443/mcp",
    "https://10.0.0.1/mcp",
])
def test_untrusted_metadata_target_rejected_before_network(url):
    with pytest.raises(ValueError):
        validated_url(url)

def test_metadata_array_is_rejected():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=[]))) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"

def test_metadata_issuer_non_string_is_rejected():
    with httpx.Client(transport=httpx.MockTransport(
        lambda req:httpx.Response(200,json={"resource":URL,"authorization_servers":[123]}))) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"


@pytest.mark.parametrize("issuer", [
    "http://auth.example.com",
    "https://auth.example.com?api_key=secret",
    "https://user:password@auth.example.com",
    "https://auth.example.com:444",
])
def test_issuer_auth_metadata_unsafe_origins_hold(issuer):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "resource": URL, "authorization_servers": [issuer]
        }))) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"

def test_successful_metadata_discovery_not_live_oauth_verification():
    def handler(request):
        return httpx.Response(200,json={
            "resource":URL,"authorization_servers":["https://auth.example.com"]
        })
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="DISCOVERABLE"
    assert result["external_oauth_login"]=="NOT_TESTED"
    assert result["cross_client_isolation"]=="NOT_TESTED"
    assert result["audit_logs"]=="NOT_TESTED"
    assert result["gate_a"]=="HOLD"


def test_discovery_does_not_follow_redirect_to_other_host():
    seen=[]
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302,headers={"Location":"https://unapproved.example.net/.well-known/oauth-protected-resource"})
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        result=verify_remote_metadata(URL,client)
    assert len(seen)==1
    assert seen==[META]
    assert result["metadata"]=="NOT_VERIFIED"
    assert result["gate_a"]=="HOLD"

def test_remote_preflight_does_not_send_customer_data():
    def handler(request):
        assert request.method=="GET"
        assert request.content==b""
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(200,json={"resource":URL,"authorization_servers":["https://auth.example.com"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=verify_remote_metadata(URL,client)
    assert result["metadata"]=="DISCOVERABLE"
    assert result["gate_a"]=="HOLD"
