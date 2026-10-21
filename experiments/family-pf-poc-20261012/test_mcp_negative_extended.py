"""Extra negative tests for the synthetic MCP transport, not live OAuth."""
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

def request(env, method, params=None, *, bearer=True, jwt=None, rpc_version='2.0', msg_id=1):
    c, scope, sign, verifier, _ = env
    attach_mcp(c.app, verifier, scope)
    headers = {'Authorization': 'Bearer ' + (jwt if jwt is not None else sign('joseph'))} if bearer else {}
    response = c.post('/mcp', headers=headers, json={
        'jsonrpc': rpc_version, 'id': msg_id, 'method': method, 'params': params or {}})
    return response, scope

def test_read_requires_bearer_even_if_resource_is_correct(env):
    r, scope = request(env,'tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'joseph','resource_id':'r-j'}},bearer=False)
    assert r.status_code == 401
    assert scope.audit[-1]['decision'] == 'DENY'

def test_invalid_jwt_rejected_and_audited(env):
    r, scope = request(env,'initialize',jwt='malformed.jwt.payload')
    assert r.status_code == 401
    assert scope.audit[-1]['decision'] == 'DENY'

def test_reverse_client_access_blocked(env):
    c, scope, sign, verifier, _ = env
    attach_mcp(c.app,verifier,scope)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+sign('mou')},json={
        'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':'pf_read_resource','arguments':{'active_client_id':'joseph','resource_id':'r-j'}}})
    assert r.json()['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'

def test_client_scope_and_resource_owner_both_must_match(env):
    r, scope = request(env,'tools/call',{'name':'pf_read_resource',
        'arguments':{'active_client_id':'joseph','resource_id':'r-m'}})
    assert r.json()['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'

def test_bad_rpc_version_rejected(env):
    r,_=request(env,'initialize',rpc_version='1.0')
    assert r.json()['error']['code'] == -32600

def test_missing_rpc_id_rejected(env):
    r,_=request(env,'initialize',msg_id=None)
    assert r.json()['error']['code'] == -32600

def test_no_unlisted_mcp_tool_execution(env):
    r,_=request(env,'tools/call',{'name':'read_all_clients','arguments':{}})
    assert r.json()['error']['code'] == -32602
