import json
from http.cookies import SimpleCookie
import sqlite3
import uuid
import pytest
from test_accounts import env, activate
from account_http import AccountHTTP, RateLimiter, SESSION, CSRF

ORIGIN='https://family.example'

class Client:
    def __init__(self, app): self.app,self.cookies,self.csrf=app,{},''
    def call(self,path='/',body=None,headers=None,method=None,raw=None,peer='test-ip'):
        h={'Host':'family.example','Cookie':'; '.join(k+'='+v for k,v in self.cookies.items())}
        if body is not None:
            h.update({'Origin':ORIGIN,'Content-Type':'application/json','X-Family-CSRF':self.csrf})
            raw=json.dumps(dict(body,request_id=body.get('request_id',uuid.uuid4().hex))).encode()
        h.update(headers or {})
        status,out,data=self.app.handle(method or ('POST' if body is not None else 'GET'),path,h,raw or b'',peer)
        for key,value in out:
            if key=='Set-Cookie':
                p=SimpleCookie();p.load(value)
                for k,v in p.items():self.cookies[k]=v.value
        if CSRF in self.cookies:self.csrf=self.cookies[CSRF]
        return status,out,data

@pytest.fixture
def browser(env):
    manager,_,now,_,root=env
    clock=lambda:now[0]
    app=AccountHTTP(manager,ORIGIN,'family-connection',RateLimiter(root/'rate.db',manager.key,clock),clock)
    client=Client(app);client.call()
    return client,env

def test_login_cookie_and_no_token_in_json(browser):
    c,(m,_,_,_,_)=browser;activate(m)
    status,headers,raw=c.call('/login',{'user_id':'mou','password':'secret-mou'})
    assert status==200
    assert c.cookies[SESSION].encode() not in raw
    cookie=next(v for k,v in headers if k=='Set-Cookie')
    assert all(x in cookie for x in ['Secure','HttpOnly','SameSite=Strict','Path=/','Max-Age=14400'])
    assert json.loads(c.call('/session')[2])['result']['user_id']=='mou'
    assert c.call('/logout',{})[0]==200
    assert c.call('/session')[0]==401

def test_activation_change_and_cookie_clear(browser):
    c,_=browser
    assert c.call('/login',{'user_id':'mou','password':'initial-mou'})[0]==200
    assert c.call('/session')[0]==401
    assert c.call('/change-password',{'current_password':'initial-mou','new_password':'replacement'})[0]==200
    assert c.cookies[SESSION]==''
    assert c.call('/login',{'user_id':'mou','password':'replacement'})[0]==200

def test_switch_revokes_old_cookie_but_expired_cookie_allows_login(browser):
    c,(m,_,now,_,_)=browser;activate(m);activate(m,'Arthur')
    c.call('/login',{'user_id':'mou','password':'secret-mou'});old=c.cookies[SESSION]
    assert c.call('/login',{'user_id':'Arthur','password':'secret-Arthur'})[0]==200
    with pytest.raises(PermissionError):m.authenticate(old,'family-connection')
    now[0]+=14400;c.call()
    assert c.call('/login',{'user_id':'mou','password':'secret-mou'})[0]==200

def test_login_retry_after_cookie_was_already_received(browser):
    c,(m,_,_,_,_)=browser;activate(m)
    body={'user_id':'mou','password':'secret-mou','request_id':'same-request-0001'}
    assert c.call('/login',body)[0]==200
    original=c.cookies[SESSION]
    assert c.call('/login',body)[0]==200
    assert c.cookies[SESSION]==original

@pytest.mark.parametrize('headers,status',[
    ({'Origin':'https://evil.example'},403),({'Origin':''},403),
    ({'Host':'evil.example'},400),({'Content-Type':'text/plain'},415),
    ({'X-Family-CSRF':'forged'},403)])
def test_pre_auth_boundaries(browser,headers,status):
    c,_=browser
    assert c.call('/login',{'user_id':'mou','password':'initial-mou'},headers=headers)[0]==status

def test_expired_csrf_and_forged_matching_cookie(browser):
    c,(_,_,now,_,_)=browser;now[0]+=900
    assert c.call('/login',{'user_id':'mou','password':'initial-mou'})[0]==403
    c.cookies[CSRF]=c.csrf='forged'
    assert c.call('/logout',{})[0]==403

def test_invalid_fields_json_query_and_size(browser):
    c,_=browser
    assert c.call('/login',{'user_id':'mou','password':'initial-mou','role':'manager'})[0]==400
    assert c.call('/?password=x')[0]==400
    assert c.call('/',method='PUT')[0]==405
    assert c.call('/login',method='POST',raw=b'x'*8193)[0]==413
    h={'Origin':ORIGIN,'Content-Type':'application/json','X-Family-CSRF':c.csrf}
    assert c.call('/logout',headers=h,method='POST',raw=b'{"request_id":"a","request_id":"b"}')[0]==400

def test_http_management_checks_real_role(browser):
    c,(m,_,_,_,_)=browser;activate(m)
    c.call('/login',{'user_id':'mou','password':'secret-mou'})
    body=dict(operation='disable',user_id='Arthur',password=None,role='member',until=1500)
    assert c.call('/manage',body)[0]==401
    activate(m,'coach');c.call('/login',{'user_id':'coach','password':'secret-coach'})
    assert c.call('/manage',body)[0]==200

def test_limiter_shared_across_instances_and_no_raw_ip(env):
    m,_,now,_,root=env
    for i in range(30): assert RateLimiter(root/'rate.db',m.key,lambda:now[0]).admit('private-ip')
    assert not RateLimiter(root/'rate.db',m.key,lambda:now[0]).admit('private-ip')
    assert b'private-ip' not in (root/'rate.db').read_bytes()
    now[0]+=60
    assert RateLimiter(root/'rate.db',m.key,lambda:now[0]).admit('private-ip')

def test_page_csp_and_error_redaction(browser):
    c,(m,_,_,_,_)=browser
    status,headers,body=c.call()
    assert status==200 and b'__CSRF__' not in body and b'__NONCE__' not in body
    assert 'frame-ancestors' in dict(headers)['Content-Security-Policy']
    def broken(*args,**kwargs):raise OSError('a-secret-provider-response')
    m.login=broken
    status,_,body=c.call('/login',{'user_id':'mou','password':'initial-mou'})
    assert status==503 and b'a-secret' not in body
