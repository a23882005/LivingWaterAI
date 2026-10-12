from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

def rpc(e,sub,method,params=None,token=True):
    c,scope,sign,verifier,_=e
    attach_mcp(c.app,verifier,scope)
    h={'Authorization':'Bearer '+sign(sub)} if token else {}
    return c.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})

def test_mcp_requires_oauth(env):
    assert rpc(env,'joseph','initialize',token=False).status_code==401

def test_mcp_initialize(env):
    assert rpc(env,'joseph','initialize').json()['result']['serverInfo']['name']=='family-pf-synthetic-poc'

def test_mcp_tools_list(env):
    assert rpc(env,'mou','tools/list').json()['result']['tools'][0]['name']=='pf_read_resource'

def test_mcp_joseph_allowed(env):
    assert rpc(env,'joseph','tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'joseph','resource_id':'r-j'}}).json()['result']['content'][0]['text']=='synthetic-j'

def test_mcp_mou_allowed(env):
    assert rpc(env,'mou','tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'mou','resource_id':'r-m'}}).json()['result']['content'][0]['text']=='synthetic-m'

def test_mcp_cross_client_deny(env):
    out=rpc(env,'joseph','tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'mou','resource_id':'r-m'}}).json()
    assert out['result']['isError'] and 'synthetic-m' not in str(out)
    assert env[1].audit[-1]['decision']=='DENY'

def test_mcp_resource_tamper_denied(env):
    out=rpc(env,'joseph','tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'joseph','resource_id':'r-m'}}).json()
    assert out['result']['isError']

def test_mcp_unknown_method_fails(env):
    assert rpc(env,'joseph','secret/admin').json()['error']['code']==-32601

def test_mcp_extra_args_rejected(env):
    out=rpc(env,'joseph','tools/call',{'name':'pf_read_resource','arguments':{'active_client_id':'joseph','resource_id':'r-j','project_hint':'mou'}}).json()
    assert out['error']['code']==-32602
