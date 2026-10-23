"""B07 same-origin browser account boundary; provider/MCP OAuth is separate.

No CORS, URL passwords, bearer values in response JSON, or request-body logging.
The trusted gateway provides actual method/path/Host/Origin/peer. Config supplies
one canonical HTTPS origin and logical connection scope, never caller claims.
"""
import hashlib
import hmac
import html
from http.cookies import SimpleCookie, CookieError
import json
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

SESSION = '__Host-family_session'
CSRF = '__Host-family_csrf'
LIMIT = 8192

class RequestError(Exception):
    def __init__(self, status, code): self.status, self.code = status, code

class RateLimiter:
    """Private single-host state, not account DB. Never store raw IP/password.

    All processes share this file. Fixed minute windows: 30/IP, 120/global.
    Authentication has the separate durable per-account throttle in B07 core.
    """
    def __init__(self, path, key, clock=time.time):
        self.path, self.key, self.clock = str(path), key, clock
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    def admit(self, peer):
        bucket = int(self.clock()) // 60
        ip = hmac.new(self.key, str(peer).encode(), hashlib.sha256).hexdigest()
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute('CREATE TABLE IF NOT EXISTS rate(bucket INTEGER,k TEXT,n INTEGER,PRIMARY KEY(bucket,k))')
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM rate WHERE bucket<?', (bucket-1,))
            allowed = True
            for key, maximum in [('global',120), (ip,30)]:
                db.execute('INSERT OR IGNORE INTO rate VALUES(?,?,0)',(bucket,key))
                db.execute('UPDATE rate SET n=n+1 WHERE bucket=? AND k=?',(bucket,key))
                count=db.execute('SELECT n FROM rate WHERE bucket=? AND k=?',(bucket,key)).fetchone()[0]
                allowed = allowed and count <= maximum
        return allowed

def _json_unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj: raise ValueError('DUPLICATE_FIELD')
        obj[key] = value
    return obj

def _cookies(value):
    if len(value) > 4096: raise RequestError(400,'INVALID_COOKIE')
    parsed = SimpleCookie()
    try: parsed.load(value)
    except CookieError: raise RequestError(400,'INVALID_COOKIE') from None
    return {key: item.value for key,item in parsed.items()}

def _cookie(name, value, lifetime):
    return ('Set-Cookie', f'{name}={value}; Path=/; Max-Age={max(0,int(lifetime))}; Secure; HttpOnly; SameSite=Strict')

class AccountHTTP:
    def __init__(self, manager, origin, scope, limiter, clock=time.time):
        parsed = urlsplit(origin)
        if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('CANONICAL_HTTPS_ORIGIN_REQUIRED')
        self.manager,self.origin,self.host,self.scope,self.limiter,self.clock = manager,origin,parsed.netloc,scope,limiter,clock

    def _csrf(self):
        value=f'{int(self.clock())}.{secrets.token_hex(24)}'
        return value+'.'+self.manager._mac('browser-csrf',value)

    def _check_csrf(self, token, cookie):
        if not isinstance(token,str) or len(token)>256 or not hmac.compare_digest(token,cookie):
            raise RequestError(403,'CSRF_REQUIRED')
        try:
            stamp, nonce, signature=token.split('.')
            if len(nonce)!=48 or not 0 <= self.clock()-int(stamp) < 900:
                raise ValueError()
            if not hmac.compare_digest(signature,self.manager._mac('browser-csrf',stamp+'.'+nonce)):
                raise ValueError()
        except (ValueError, TypeError): raise RequestError(403,'CSRF_REQUIRED') from None

    def handle(self, method, path, headers, raw=b'', peer=''):
        response_headers=[('Cache-Control','no-store'),('Pragma','no-cache'),
            ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
            ('X-Frame-Options','DENY'),('Content-Type','application/json; charset=utf-8')]
        try:
            headers={key.lower():value for key,value in headers.items()}
            if headers.get('host') != self.host: raise RequestError(400,'INVALID_HOST')
            if '?' in path or '#' in path: raise RequestError(400,'QUERY_NOT_ALLOWED')
            if len(raw)>LIMIT: raise RequestError(413,'BODY_TOO_LARGE')
            if method not in ('GET','POST'): raise RequestError(405,'METHOD_NOT_ALLOWED')
            if headers.get('origin') not in (None,self.origin): raise RequestError(403,'ORIGIN_REJECTED')
            if not self.limiter.admit(peer): raise RequestError(429,'TRY_LATER')
            cookies=_cookies(headers.get('cookie',''))
            if method=='GET' and path=='/':
                csrf=self._csrf();nonce=secrets.token_hex(20)
                page=Path(__file__).with_name('account_login.html').read_text()
                page=page.replace('__CSRF__',html.escape(csrf,quote=True)).replace('__NONCE__',nonce)
                response_headers=[x for x in response_headers if x[0]!='Content-Type']
                response_headers.extend([('Content-Type','text/html; charset=utf-8'),_cookie(CSRF,csrf,900),
                    ('Content-Security-Policy',f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")])
                return 200,response_headers,page.encode()
            if method=='GET' and path=='/session':
                principal=self.manager.authenticate(cookies.get(SESSION,''),self.scope)
                result={'user_id':principal.subject.removeprefix('account:'),'expires_at':principal.expires_at}
            else:
                if method!='POST': raise RequestError(404,'NOT_FOUND')
                if headers.get('origin')!=self.origin: raise RequestError(403,'ORIGIN_REQUIRED')
                if headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
                    raise RequestError(415,'JSON_REQUIRED')
                self._check_csrf(headers.get('x-family-csrf',''),cookies.get(CSRF,''))
                try: body=json.loads(raw,object_pairs_hook=_json_unique)
                except (ValueError,UnicodeError): raise RequestError(400,'INVALID_JSON') from None
                schemas={'/login':{'user_id','password','request_id'},
                         '/change-password':{'current_password','new_password','request_id'},
                         '/logout':{'request_id'},
                         '/manage':{'operation','user_id','password','role','until','request_id'}}
                if path not in schemas: raise RequestError(404,'NOT_FOUND')
                if not isinstance(body,dict) or set(body)!=schemas[path]: raise RequestError(400,'INVALID_FIELDS')
                rid=body['request_id']
                if not isinstance(rid,str) or not 16<=len(rid)<=128: raise RequestError(400,'INVALID_REQUEST_ID')
                token=cookies.get(SESSION,'')
                if path=='/login':
                    replace=None
                    if token:
                        try:
                            self.manager.store.read(lambda db:self.manager._session(db,token,self.scope,allow_change=True))
                            replace=token
                        except PermissionError:
                            pass  # Expired cookie must not prevent a fresh login.
                    result=self.manager.login(body['user_id'],body['password'],self.scope,rid)
                    if replace and not hmac.compare_digest(replace,result['token']):
                        # Cookie state can differ on retry after a lost response.
                        # Keep login receipt stable; end previous browser session
                        # before returning the new cookie. Both writes are durable.
                        try:
                            self.manager.logout(replace,self.scope,'http-switch-'+self.manager._mac('switch',rid))
                        except PermissionError:
                            pass  # Concurrent logout/change already invalidated it.
                    response_headers.append(_cookie(SESSION,result.pop('token'),result['expires_at']-self.clock()))
                elif path=='/change-password':
                    result=self.manager.change_password(token,self.scope,body['current_password'],body['new_password'],rid)
                    response_headers.append(_cookie(SESSION,'',0))
                elif path=='/logout':
                    result=self.manager.logout(token,self.scope,rid)
                    response_headers.append(_cookie(SESSION,'',0))
                else:
                    result=self.manager.manage(token,self.scope,rid,body['operation'],body['user_id'],
                        password=body['password'],role=body['role'],until=body['until'])
            return 200,response_headers,json.dumps({'result':result},ensure_ascii=False).encode()
        except RequestError as error:
            status,code=error.status,error.code
        except PermissionError as error:
            code='PASSWORD_CHANGE_REQUIRED' if str(error)=='PASSWORD_CHANGE_REQUIRED' else 'AUTH_REQUIRED'
            status=401
        except (ValueError,TypeError,KeyError,sqlite3.IntegrityError):
            status,code=400,'INVALID_REQUEST'
        except Exception:
            status,code=503,'SERVICE_RETRY'
        return status,response_headers,json.dumps({'error':code}).encode()
