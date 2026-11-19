"""MCP HTTP Origin / DNS-rebinding safety regression tests (synthetic only)."""
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

def invoke(env, origin_marker, path='/mcp'):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope)
    headers={'Authorization':'Bearer '+sign('joseph')}
    if origin_marker is not None:
        headers['Origin']=origin_marker
    r=client.post(path,headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
    return r,scope

def test_unknown_origin_denied(env):
    r,scope=invoke(env,'https://attacker.example')
    assert r.status_code==403 and scope.audit[-1]['decision']=='DENY'

def test_null_origin_denied(env):
    r,scope=invoke(env,'null')
    assert r.status_code==403 and scope.audit[-1]['reason']=='untrusted_origin'

def test_suffix_trick_origin_denied(env):
    r,scope=invoke(env,'https://trusted.example.test.evil.example')
    assert r.status_code==403

def test_exact_allowlisted_origin_accepted(env):
    r,scope=invoke(env,'https://trusted.example.test')
    assert r.status_code==200 and 'result' in r.json()

def test_no_browser_origin_still_requires_token(env):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope)
    r=client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
    assert r.status_code==401
