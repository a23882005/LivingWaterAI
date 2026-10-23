import concurrent.futures
import importlib
import sqlite3
import uuid
import pytest
from test_accounts import env,activate,login
from account_oauth import OAuthService,OAuthError,challenge,SCOPE

CLIENT='verified-client'; REDIRECT='https://client.example/callback'; RESOURCE='https://family.example/mcp'
V='x'*43

def service(m):
    return OAuthService(m,'https://family.example/oauth',RESOURCE,{CLIENT:[REDIRECT]},'family-connection')

@pytest.fixture
def setup(env):
    m,make,now,d,root=env
    s=service(m);s.migrate();session=activate(m)
    return s,session,env

def issue(s,session,**kw):
    p=dict(client=CLIENT,redirect=REDIRECT,resource=RESOURCE,scope=SCOPE,method='S256',code_challenge=challenge(V));p.update(kw)
    return s.issue(session['token'],**p)

def exchange(s,code,**kw):
    p=dict(client=CLIENT,redirect=REDIRECT,resource=RESOURCE,verifier=V);p.update(kw)
    return s.exchange(code,**p)

def test_restart_and_private_state(setup):
    s,t,(m,make,now,d,root)=setup
    c=issue(s,t);p=exchange(service(make()),c)
    assert service(make()).authenticate(p['access_token']).subject=='account:mou'
    for secret in (c,p['access_token'],p['refresh_token'],t['token']):
        assert secret.encode() not in d.read('synthetic_accounts')
    with sqlite3.connect(root/'synthetic_accounts') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
    assert s.metadata()['code_challenge_methods_supported']==['S256']
    assert s.resource_metadata()['resource']==RESOURCE

@pytest.mark.parametrize('change',[{'client':'wrong'},{'redirect':REDIRECT+'/extra'},{'resource':RESOURCE+'/bad'},
 {'scope':'family:admin'},{'method':'plain'},{'code_challenge':'a'}, {'redirect':'https://evil.example'}])
def test_bad_authorization(setup,change):
    s,t,_=setup
    with pytest.raises(OAuthError):issue(s,t,**change)

@pytest.mark.parametrize('change',[{'client':'wrong'},{'redirect':REDIRECT+'/extra'},
 {'resource':RESOURCE+'/bad'},{'verifier':'z'*43},{'verifier':'short'}])
def test_bad_exchange_does_not_consume(setup,change):
    s,t,_=setup;c=issue(s,t)
    with pytest.raises(OAuthError):exchange(s,c,**change)
    assert exchange(s,c)['access_token']

def test_atomic_single_code_exchange(setup):
    s,t,_=setup;c=issue(s,t)
    def attempt(_):
        try:return bool(exchange(s,c))
        except OAuthError:return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2)))==[False,True]

def test_code_expiry(setup):
    s,t,(_,_,now,_,_)=setup;c=issue(s,t);now[0]+=120
    with pytest.raises(OAuthError):exchange(s,c)

def test_refresh_fixed_four_hours(setup):
    s,t,(_,_,now,_,_)=setup;p=exchange(s,issue(s,t));now[0]=t['expires_at']-10
    p=s.refresh(p['refresh_token'],CLIENT,RESOURCE);assert p['expires_in']==10
    assert s.authenticate(p['access_token']).expires_at==t['expires_at']
    now[0]+=10
    with pytest.raises(OAuthError):s.refresh(p['refresh_token'],CLIENT,RESOURCE)
    with pytest.raises(OAuthError):s.authenticate(p['access_token'])

def test_refresh_replay_revokes_grant(setup):
    s,t,_=setup;p=exchange(s,issue(s,t));q=s.refresh(p['refresh_token'],CLIENT,RESOURCE)
    with pytest.raises(PermissionError):s.refresh(p['refresh_token'],CLIENT,RESOURCE)
    with pytest.raises(OAuthError):s.authenticate(q['access_token'])

def test_logout_revokes_oauth(setup):
    s,t,(m,_,_,_,_)=setup;p=exchange(s,issue(s,t));principal=s.authenticate(p['access_token'])
    m.logout(t['token'],'family-connection',uuid.uuid4().hex)
    assert not s.session_guard(principal)
    with pytest.raises(OAuthError):s.refresh(p['refresh_token'],CLIENT,RESOURCE)

def test_password_change_revokes(setup):
    s,t,(m,_,_,_,_)=setup;p=exchange(s,issue(s,t))
    m.change_password(t['token'],'family-connection','secret-mou','changed',uuid.uuid4().hex)
    with pytest.raises(OAuthError):s.authenticate(p['access_token'])

def test_disable_revokes(setup):
    s,t,(m,_,_,_,_)=setup;p=exchange(s,issue(s,t));admin=activate(m,'coach')
    m.manage(admin['token'],'family-connection',uuid.uuid4().hex,'disable','mou')
    with pytest.raises(OAuthError):s.authenticate(p['access_token'])

def test_initial_password_cannot_authorize(env):
    m,*_=env;s=service(m);s.migrate();t=login(m,password='initial-mou')
    with pytest.raises(PermissionError):issue(s,t)

def test_other_login_survives_logout(setup):
    s,t,(m,_,_,_,_)=setup;other=login(m);p=exchange(s,issue(s,other))
    m.logout(t['token'],'family-connection',uuid.uuid4().hex)
    assert s.authenticate(p['access_token']).subject=='account:mou'

def test_access_scope_resource_and_rotation(setup):
    s,t,(m,make,_,_,_)=setup;p=exchange(s,issue(s,t))
    with pytest.raises(OAuthError):s.authenticate(p['access_token'],resource='https://wrong.example')
    with pytest.raises(OAuthError):s.authenticate(p['access_token'],scope='admin')
    with pytest.raises(OAuthError):service(make(b'z'*32)).authenticate(p['access_token'])
    with pytest.raises(OAuthError):s.authenticate(p['refresh_token'])
