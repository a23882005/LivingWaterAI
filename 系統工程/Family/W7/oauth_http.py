"""OAuth HTTP boundary. Exact pre-registered public clients; no DCR/URL fetch.

GET authorize renders the existing account page plus explicit consent. The
existing same-origin CSRF and private cookies protect POST consent and login.
A deployment router maps browser account calls to the existing AccountHTTP.
"""
import html
import json
from urllib.parse import parse_qsl,urlsplit,urlencode
from account_http import _cookies,SESSION,CSRF,RequestError
from account_oauth import OAuthError

class OAuthHTTP:
    def __init__(self,oauth,account,account_base):
        self.oauth,self.account,self.base=oauth,account,account_base
        if not account_base.startswith('/') or any(x in account_base for x in ('?','#','"',"'",'\\','<','>')):
            raise ValueError('SAFE_ACCOUNT_BASE_REQUIRED')

    def _params(self,raw):
        if len(raw)>8192:raise OAuthError('invalid_request')
        pairs=parse_qsl(raw,keep_blank_values=True,max_num_fields=12,strict_parsing=True)
        d=dict(pairs)
        if len(d)!=len(pairs):raise OAuthError('invalid_request')
        return d

    def _authorize(self,p):
        if set(p)!={'response_type','client_id','redirect_uri','resource','scope','state','code_challenge','code_challenge_method'}:
            raise OAuthError('invalid_request')
        if p['response_type']!='code' or not 1<=len(p['state'])<=512:raise OAuthError('invalid_request')
        self.oauth.validate_request(p['client_id'],p['redirect_uri'],p['resource'],p['scope'],p['code_challenge_method'],p['code_challenge'])

    def handle(self,method,path,headers,raw=b'',peer=''):
        out=[('Content-Type','application/json'),('Cache-Control','no-store'),('Referrer-Policy','no-referrer')]
        headers={k.lower():v for k,v in headers.items()}
        try:
            if headers.get('host')!=self.account.host:raise OAuthError('invalid_request')
            if headers.get('origin') not in (None,self.account.origin):raise OAuthError('invalid_request')
            if len(raw)>8192: return 413,out,b'{}'
            if not self.account.limiter.admit(peer):return 429,out,b'{"error":"temporarily_unavailable"}'
            url=urlsplit(path)
            if method=='GET' and url.path=='/metadata' and not url.query:
                return 200,out,json.dumps(self.oauth.metadata()).encode()
            if method=='GET' and url.path=='/resource-metadata' and not url.query:
                return 200,out,json.dumps(self.oauth.resource_metadata()).encode()
            if url.path=='/authorize':
                p=self._params(url.query);self._authorize(p)
                if method=='GET':
                    status,hs,body=self.account.handle('GET','/',headers,peer=peer)
                    if status!=200:return status,hs,body
                    page=body.decode().replace("const base=location.pathname.replace(/\\/$/,'').replace(/\\/index\\.php$/,'');",'const base='+json.dumps(self.base)+';')
                    # No inline JS added: existing CSP nonce is reused by extending its script.
                    button='<section><h2>連接 ChatGPT</h2><p>允許此連接查詢您目前登入的 Family 帳號；登入期限保持原四小時。</p><button id="consent" type="button">同意連接</button></section>'
                    page=page.replace('<script nonce=',button+'<script nonce=',1)
                    js="""\ndocument.querySelector('#consent').onclick=async()=>{const b=document.querySelector('#consent');b.disabled=true;try{const r=await fetch(location.pathname+location.search,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Family-CSRF':csrf},body:JSON.stringify({consent:true})});const v=await r.json();if(r.ok){location.assign(v.redirect);}else{status.textContent=v.error==='access_denied'?'請先登入並完成初始密碼修改。':'授權未完成，請重新連接。';}}catch(e){status.textContent='連線中斷，請重新連接。';}finally{b.disabled=false;}};\n"""
                    return status,hs,page.replace('</script>',js+'</script>',1).encode()
                if method!='POST' or headers.get('origin')!=self.account.origin or headers.get('content-type','').split(';')[0]!='application/json':
                    raise OAuthError('invalid_request')
                cookies=_cookies(headers.get('cookie',''))
                self.account._check_csrf(headers.get('x-family-csrf',''),cookies.get(CSRF,''))
                if raw!=b'{"consent":true}':raise OAuthError('invalid_request')
                code=self.oauth.issue(cookies.get(SESSION,''),p['client_id'],p['redirect_uri'],p['resource'],p['scope'],p['code_challenge_method'],p['code_challenge'])
                separator='&' if urlsplit(p['redirect_uri']).query else '?'
                redirect=p['redirect_uri']+separator+urlencode({'code':code,'state':p['state'],'iss':self.oauth.issuer})
                return 200,out,json.dumps({'redirect':redirect}).encode()
            if url.path!='/token' or url.query or method!='POST':return 404,out,b'{}'
            if headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':raise OAuthError('invalid_request')
            p=self._params(raw.decode('utf-8'))
            if p.get('grant_type')=='authorization_code' and set(p)=={'grant_type','code','client_id','redirect_uri','resource','code_verifier'}:
                result=self.oauth.exchange(p['code'],p['client_id'],p['redirect_uri'],p['resource'],p['code_verifier'])
            elif p.get('grant_type')=='refresh_token' and set(p)=={'grant_type','refresh_token','client_id','resource'}:
                result=self.oauth.refresh(p['refresh_token'],p['client_id'],p['resource'])
            else:raise OAuthError('invalid_request')
            return 200,out,json.dumps(result).encode()
        except OAuthError as e:return 400,out,json.dumps({'error':str(e)}).encode()
        except (PermissionError,RequestError):return 403,out,b'{"error":"access_denied"}'
        except (ValueError,UnicodeError,TypeError):return 400,out,b'{"error":"invalid_request"}'
        except Exception:return 503,out,b'{"error":"temporarily_unavailable"}'
