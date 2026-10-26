import json
import pytest
from test_accounts import env
from test_account_oauth import setup
from account_http import AccountHTTP,RateLimiter
from account_router import AccountRouter

@pytest.fixture
def router(setup,tmp_path):
    oauth,session,(manager,*_)=setup
    oauth.issuer='https://family.example/entry/oauth';oauth.resource='https://family.example/entry/mcp'
    account=AccountHTTP(manager,'https://family.example','family-connection',RateLimiter(tmp_path/'rate.db',manager.key,clock=manager.clock),clock=manager.clock)
    return AccountRouter(oauth,account,'/entry')

@pytest.mark.parametrize('path',['/entry/oauth/.well-known/oauth-authorization-server','/.well-known/oauth-authorization-server/entry/oauth'])
def test_issuer_discovery(router,path):
    s,_,b=router.handle('GET',path,{'Host':'family.example'})
    assert s==200 and json.loads(b)['token_endpoint']=='https://family.example/entry/oauth/token'


def test_mcp_challenge_points_to_working_metadata(router):
    s,hs,_=router.handle('POST','/entry/mcp',{'Host':'family.example','Content-Type':'application/json'},b'{}')
    assert s==401
    assert 'https://family.example/entry/mcp/.well-known/oauth-protected-resource' in dict(hs)['WWW-Authenticate']
    assert router.handle('POST','/entry/mcp',{'Host':'family.example','Content-Type':'application/json'},b'x'*50000)[0] == 401
    s,_,b=router.handle('GET','/entry/mcp/.well-known/oauth-protected-resource',{'Host':'family.example'})
    assert s==200 and json.loads(b)['resource']=='https://family.example/entry/mcp'

@pytest.mark.parametrize('path',['/entry-other/login','/entry/../login','/entry/%2e%2e/login','/entry/mcp?user=other','https://evil.example/entry/login'])
def test_no_route_alias(router,path):
    assert router.handle('GET',path,{'Host':'family.example'})[0] in (400,404)


def test_host_and_origin(router):
    assert router.handle('GET','/entry',{'Host':'evil.example'})[0]==403
    assert router.handle('GET','/entry',{'Host':'family.example','Origin':'https://evil.example'})[0]==403


def test_token_is_direct_oauth_reply(router):
    status,_,body=router.handle('POST','/entry/oauth/token',{'Host':'family.example','Content-Type':'application/x-www-form-urlencoded'},b'grant_type=unknown')
    assert status==400 and json.loads(body)=={'error':'invalid_request'}
