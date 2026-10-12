"""Read-only public HTTPS MCP preflight. Does NOT certify OAuth or Gate A.

Usage (only against an explicitly approved test endpoint):
  python pf_remote_preflight.py https://mcp.your-approved-domain.example/mcp

No credentials, user records, or OAuth tokens are sent. Redirects are disabled.
"""
import json
import sys
from urllib.parse import urlsplit
import httpx

def validated_url(url):
    if not isinstance(url, str):
        raise ValueError("An explicit HTTPS endpoint is required")
    p=urlsplit(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("HTTPS origin without embedded credentials or query required")
    if p.hostname in ("localhost","127.0.0.1") or p.hostname.endswith((".test",".invalid",".example",".localhost")):
        raise ValueError("Placeholder or loopback URL cannot be used as remote evidence")
    if p.path != "/mcp":
        raise ValueError("Endpoint must end in /mcp")
    return url

def verify_remote_metadata(url, transport=None):
    """Unauthenticated read-only probe. Output contains no request secrets."""
    url=validated_url(url)
    p=urlsplit(url)
    origin=f"{p.scheme}://{p.netloc}"
    expected=origin+"/.well-known/oauth-protected-resource"
    result={"remote_transport":"NOT_VERIFIED","metadata":"NOT_VERIFIED",
            "external_oauth_login":"NOT_TESTED","cross_client_isolation":"NOT_TESTED",
            "audit_logs":"NOT_TESTED","gate_a":"HOLD"}
    client=transport or httpx.Client(timeout=8,follow_redirects=False,trust_env=False)
    try:
        response=client.get(expected,headers={"Accept":"application/json"})
        if response.status_code!=200:
            result["reason"]="metadata_http_status_"+str(response.status_code)
            return result
        result["remote_transport"]="HTTPS_RESPONSE"
        obj=response.json()
        if not isinstance(obj,dict) or obj.get("resource")!=url:
            result["reason"]="resource_identifier_mismatch"
            return result
        issuers=obj.get("authorization_servers")
        if not isinstance(issuers,list) or len(issuers)!=1 or not isinstance(issuers[0],str) or not issuers[0].startswith("https://"):
            result["reason"]="invalid_authorization_server"
            return result
        result["metadata"]="DISCOVERABLE"
        # No credential or login attempts. A metadata response is NOT OAuth verification.
        return result
    except (httpx.HTTPError,ValueError,KeyError,json.JSONDecodeError):
        result["reason"]="request_or_metadata_error"
        return result
    finally:
        if transport is None:
            client.close()

if __name__=="__main__":
    if len(sys.argv)!=2:
        print("Usage: python pf_remote_preflight.py https://approved-test-host/mcp",file=sys.stderr)
        sys.exit(2)
    try:
        result=verify_remote_metadata(sys.argv[1])
    except ValueError as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(2)
    print(json.dumps(result,indent=2,sort_keys=True))
    sys.exit(0 if result["metadata"]=="DISCOVERABLE" else 1)
