"""OAuth protected-resource discovery tests: synthetic issuer, not a real identity provider."""
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

def test_metadata_endpoint_announces_resource_and_issuer(env):
    c,scope,sign,v,_=env
    attach_mcp(c.app,v,scope)
    r=c.get('/.well-known/oauth-protected-resource')
    assert r.status_code==200
    assert r.json()['resource']=='https://pf.example.test/mcp'
    assert r.json()['authorization_servers']==['https://auth.example.test']

def test_missing_token_returns_discovery_challenge(env):
    c,scope,sign,v,_=env
    attach_mcp(c.app,v,scope)
    r=c.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==401
    assert 'resource_metadata="https://pf.example.test/.well-known/oauth-protected-resource"' in r.headers['WWW-Authenticate']

def test_invalid_token_returns_discovery_challenge(env):
    c,scope,sign,v,_=env
    attach_mcp(c.app,v,scope)
    r=c.post('/mcp',headers={'Authorization':'Bearer invalid'},json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==401
    assert r.headers['WWW-Authenticate'].startswith('Bearer resource_metadata=')
    assert scope.audit[-1]['decision']=='DENY'

def test_resource_metadata_has_read_only_scope(env):
    c,scope,sign,v,_=env
    attach_mcp(c.app,v,scope)
    scopes=c.get('/.well-known/oauth-protected-resource').json()['scopes_supported']
    assert scopes==['pf:read']
