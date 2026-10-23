import json
from urllib.parse import urlencode,urlsplit,parse_qs
import pytest
from test_accounts import env
from test_account_oauth import setup,CLIENT,REDIRECT,RESOURCE,SCOPE,V,challenge
from account_http import AccountHTTP,RateLimiter,SESSION,CSRF
from oauth_http import OAuthHTTP

@pytest.fixture
def web(setup,tmp_path):
    s,t,(m,_,now,_,_)=setup
    account=AccountHTTP(m,'https://family.example','family-connection',RateLimiter(tmp_path/'rate.db',m.key,clock=m.clock),clock=m.clock)
    app=OAuthHTTP(s,account,'/family')
    params=dict(response_type='code',client_id=CLIENT,redirect_uri=REDIRECT,resource=RESOURCE,scope=SCOPE,state='test-state',code_challenge=challenge(V),code_challenge_method='S256')
    path='/authorize?'+urlencode(params)
    headers={'Host':'family.example'}
    status,hs,body=app.handle('GET',path,headers)
    assert status==200
    csrf=next(v.split(';')[0].split('=',1)[1] for k,v in hs if k=='Set-Cookie' and v.startswith(CSRF+'='))
    headers.update({'Origin':'https://family.example','Cookie':f'{CSRF}={csrf}; {SESSION}={t["token"]}',
                    'X-Family-CSRF':csrf,'Content-Type':'application/json'})
    return app,path,headers,body

def test_login_page_and_consent_roundtrip(web):
    app,path,h,body=web
    assert b'const base="/family";' in body and b'id="consent"' in body
    status,_,body=app.handle('POST',path,h,b'{"consent":true}')
    assert status==200
    u=urlsplit(json.loads(body)['redirect']);q=parse_qs(u.query)
    assert u.netloc=='client.example' and q['state']==['test-state'] and q['iss']==[app.oauth.issuer]
    p=dict(grant_type='authorization_code',code=q['code'][0],client_id=CLIENT,redirect_uri=REDIRECT,resource=RESOURCE,code_verifier=V)
    status,_,body=app.handle('POST','/token',{'Host':'family.example','Content-Type':'application/x-www-form-urlencoded'},urlencode(p).encode())
    assert status==200
    token=json.loads(body)['access_token'];assert app.oauth.authenticate(token).subject=='account:mou'

@pytest.mark.parametrize('change',[{'Origin':'https://evil.example'},{'X-Family-CSRF':'bad'},{'Cookie':''}])
def test_consent_boundary(web,change):
    app,path,h,_=web;h.update(change)
    assert app.handle('POST',path,h,b'{"consent":true}')[0] in (400,403)

def test_no_open_redirect(web):
    app,path,h,_=web
    assert app.handle('GET',path.replace('client.example','evil.example'),h)[0]==400

def test_duplicate_params(web):
    app,path,h,_=web;assert app.handle('GET',path+'&client_id=wrong',h)[0]==400

def test_no_implicit_consent(web):
    app,path,h,_=web;assert app.handle('POST',path,h,b'{"consent":false}')[0]==400
