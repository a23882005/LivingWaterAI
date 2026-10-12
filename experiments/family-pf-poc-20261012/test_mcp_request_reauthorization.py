"""Regression: authorization is re-evaluated on every synthetic MCP request."""
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

def send(client, token, active_client, resource):
    return client.post('/mcp',headers={'Authorization':'Bearer '+token},
      json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
      'name':'pf_read_resource','arguments':{'active_client_id':active_client,'resource_id':resource}}})

def test_switching_principal_requires_fresh_scope_check(env):
    client, scope, sign, verifier, _ = env
    attach_mcp(client.app,verifier,scope)
    assert send(client,sign('joseph'),'joseph','r-j').json()['result']['content'][0]['text']=='synthetic-j'
    denied=send(client,sign('mou'),'joseph','r-j').json()
    assert denied['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'

def test_authentication_not_cached_after_valid_request(env):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope)
    accepted=send(client,sign('joseph'),'joseph','r-j')
    assert accepted.status_code==200 and accepted.json()['result']['content'][0]['text']=='synthetic-j'
    denied=send(client,'bad.jwt.token','joseph','r-j')
    assert denied.status_code==401
    assert scope.audit[-1]['decision']=='DENY'

def test_resource_scope_checked_after_previous_success(env):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope)
    token=sign('joseph')
    assert send(client,token,'joseph','r-j').json()['result']['content'][0]['text']=='synthetic-j'
    denied=send(client,token,'joseph','r-m').json()
    assert denied['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'

def test_other_client_success_never_grants_backdoor(env):
    client,scope,sign,verifier,_=env
    attach_mcp(client.app,verifier,scope)
    assert send(client,sign('mou'),'mou','r-m').json()['result']['content'][0]['text']=='synthetic-m'
    denied=send(client,sign('joseph'),'mou','r-m').json()
    assert denied['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'
