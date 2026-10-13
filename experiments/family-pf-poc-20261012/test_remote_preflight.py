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
