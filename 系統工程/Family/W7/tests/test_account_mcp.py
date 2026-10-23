import json
import pytest
from test_accounts import env
from test_account_oauth import setup,issue,exchange
from account_mcp import AccountMCP

@pytest.fixture
def app(setup):
    s,t,_=setup;pair=exchange(s,issue(s,t))
    return AccountMCP(s),{'Content-Type':'application/json','Authorization':'Bearer '+pair['access_token']}

def call(app,name,params=None,**kw):
    a,h=app;body={'jsonrpc':'2.0','id':1,'method':name,'params':params or {}}
    return a.handle('POST',dict(h,**kw),json.dumps(body).encode())

def test_initialize_list_call(app):
    assert json.loads(call(app,'initialize',{'protocolVersion':'2025-06-18'})[2])['result']['protocolVersion']=='2025-06-18'
    assert json.loads(call(app,'tools/list')[2])['result']['tools'][0]['name']=='family_session'
    r=json.loads(call(app,'tools/call',{'name':'family_session','arguments':{}})[2])
    assert r['result']['structuredContent']['user_id']=='mou'
    assert 'Bearer' not in str(r)

@pytest.mark.parametrize('args',[{'user_id':'Arthur'},{'sql':'select 1'},{'path':'/etc/passwd'},None])
def test_no_identity_override(app,args):
    r=json.loads(call(app,'tools/call',{'name':'family_session','arguments':args})[2])
    assert r['error']['code']==-32602

def test_unauthorized(app):
    a,h=app;s,headers,_=a.handle('POST',{'Content-Type':'application/json'},b'{}')
    assert s==401 and 'resource_metadata=' in headers['WWW-Authenticate']

def test_origin(app):assert call(app,'ping',Origin='https://evil.example')[0]==403

def test_duplicate_json(app):
    a,h=app;assert a.handle('POST',h,b'{"jsonrpc":"2.0","jsonrpc":"1.0"}')[0]==400

def test_bounds(app):
    a,h=app;assert a.handle('POST',h,b'x'*8193)[0]==413
    assert a.handle('GET',h)[0]==405

def test_notification(app):
    a,h=app;assert a.handle('POST',h,b'{"jsonrpc":"2.0","method":"notifications/initialized"}')[0]==202
