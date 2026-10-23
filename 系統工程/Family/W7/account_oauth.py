"""B07 OAuth code/PKCE state through the B06 account store.

No provider credentials or raw bearer/code/refresh values in database receipts.
Exact clients/redirects come from verified private deployment configuration.
The HTTP layer must authenticate browser + CSRF + explicit consent before issue.
"""
import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit
from resource_headers import VerifiedPrincipal

SCOPE = 'family:session'
SCHEMA = (
 'CREATE TABLE IF NOT EXISTS oauth_code (code_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL, client TEXT NOT NULL, redirect TEXT NOT NULL, resource TEXT NOT NULL, scope TEXT NOT NULL, challenge TEXT NOT NULL, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0)',
 'CREATE TABLE IF NOT EXISTS oauth_grant (grant_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, client TEXT NOT NULL, resource TEXT NOT NULL, scope TEXT NOT NULL, issuer TEXT NOT NULL, expires INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)',
 'CREATE TABLE IF NOT EXISTS oauth_token (token_hash TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES oauth_grant(grant_id), kind TEXT NOT NULL, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0)',
)

class OAuthError(Exception):
    pass

@dataclass(frozen=True)
class OAuthPrincipal(VerifiedPrincipal):
    session_id: str
    proof: str = field(repr=False, compare=False)


def challenge(verifier):
    if not isinstance(verifier,str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier):
        raise OAuthError('invalid_grant')
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()

class OAuthService:
    def __init__(self, manager, issuer, resource, clients, browser_scope):
        for url in (issuer,resource):
            p=urlsplit(url)
            if p.scheme!='https' or not p.netloc or p.username or p.password or p.query or p.fragment:
                raise ValueError('CANONICAL_HTTPS_REQUIRED')
        if not clients: raise ValueError('VERIFIED_CLIENTS_REQUIRED')
        for client, redirects in clients.items():
            if not isinstance(client,str) or not client or not isinstance(redirects,list) or not redirects:
                raise ValueError('INVALID_CLIENT_CONFIG')
            for uri in redirects:
                p=urlsplit(uri)
                if p.scheme!='https' or not p.netloc or p.username or p.password or p.fragment:
                    raise ValueError('EXACT_HTTPS_REDIRECT_REQUIRED')
        self.manager,self.store,self.clock=manager,manager.store,manager.clock
        self.issuer,self.resource,self.clients,self.browser_scope=issuer,resource,clients,browser_scope

    def migrate(self):
        def run(db):
            for sql in SCHEMA: db.execute(sql)
            return {'oauth_schema':1}
        return self.manager._write('b07-oauth-schema-v1',['oauth-schema',1],run)

    def metadata(self):
        return {'issuer':self.issuer,'authorization_endpoint':self.issuer+'/authorize',
                'token_endpoint':self.issuer+'/token','response_types_supported':['code'],
                'grant_types_supported':['authorization_code','refresh_token'],
                'token_endpoint_auth_methods_supported':['none'],
                'code_challenge_methods_supported':['S256'], 'scopes_supported':[SCOPE],
                'authorization_response_iss_parameter_supported':True}

    def resource_metadata(self):
        return {'resource':self.resource,'authorization_servers':[self.issuer],
                'scopes_supported':[SCOPE],'bearer_methods_supported':['header']}

    def validate_request(self, client, redirect, resource, scope, method, code_challenge):
        if client not in self.clients or redirect not in self.clients[client]: raise OAuthError('invalid_client')
        if resource!=self.resource: raise OAuthError('invalid_target')
        if scope!=SCOPE: raise OAuthError('invalid_scope')
        if method!='S256' or not isinstance(code_challenge,str) or not re.fullmatch('[A-Za-z0-9_-]{43}',code_challenge):
            raise OAuthError('invalid_request')

    def _session(self,db,session_id):
        row=db.execute('SELECT s.*,a.enabled,a.must_change,a.generation AS current_generation,a.credential_until '
                       'FROM login_session s JOIN account a USING(user_id) WHERE token_hash=?',(session_id,)).fetchone()
        now=int(self.clock())
        if (not row or row['scope']!=self.browser_scope or row['revoked'] or not row['enabled'] or row['must_change']
            or row['generation']!=row['current_generation'] or not row['issued_at']<=now<row['expires_at']
            or (row['credential_until'] is not None and now>=row['credential_until'])):
            raise OAuthError('invalid_grant')
        return row

    def _hash(self,kind,value):
        if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{43}',value): raise OAuthError('invalid_grant')
        return self.manager._mac('oauth-'+kind,value)

    def issue(self,browser_token,client,redirect,resource,scope,method,code_challenge):
        self.validate_request(client,redirect,resource,scope,method,code_challenge)
        code=secrets.token_urlsafe(32); hashed=self._hash('code',code)
        def run(db):
            row=self.manager._session(db,browser_token,self.browser_scope)
            db.execute('INSERT INTO oauth_code VALUES(?,?,?,?,?,?,?,?,0)',
                (hashed,row['token_hash'],client,redirect,resource,scope,code_challenge,min(int(self.clock())+120,row['expires_at'])))
            return {'issued':True}
        self.manager._write('oauth-issue-'+secrets.token_hex(16),['issue',hashed],run)
        return code

    def _pair(self,db,grant_id,expires,access,refresh):
        now=int(self.clock()); access_exp=min(now+900,expires)
        for kind,value,end in [('access',access,access_exp),('refresh',refresh,expires)]:
            db.execute('INSERT INTO oauth_token VALUES(?,?,?,?,0)',(self._hash(kind,value),grant_id,kind,end))
        return {'token_type':'Bearer','expires_in':access_exp-now,'scope':SCOPE}

    def exchange(self,code,client,redirect,resource,verifier):
        hashed=self._hash('code',code); proof=challenge(verifier)
        access,refresh=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        def run(db):
            row=db.execute('SELECT * FROM oauth_code WHERE code_hash=?',(hashed,)).fetchone()
            if (not row or row['used'] or int(self.clock())>=row['expires'] or row['client']!=client
                or client not in self.clients or redirect not in self.clients[client] or row['redirect']!=redirect
                or resource!=self.resource or row['resource']!=resource or not hmac.compare_digest(row['challenge'],proof)):
                raise OAuthError('invalid_grant')
            session=self._session(db,row['session_id'])
            db.execute('UPDATE oauth_code SET used=1 WHERE code_hash=?',(hashed,))
            grant=secrets.token_hex(24)
            db.execute('INSERT INTO oauth_grant VALUES(?,?,?,?,?,?,?,0)',
                (grant,row['session_id'],client,resource,row['scope'],self.issuer,session['expires_at']))
            return self._pair(db,grant,session['expires_at'],access,refresh)
        result=self.manager._write('oauth-exchange-'+secrets.token_hex(16),['exchange',hashed],run)
        return dict(result,access_token=access,refresh_token=refresh)

    def refresh(self,token,client,resource):
        hashed=self._hash('refresh',token)
        access,refresh=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        def run(db):
            row=db.execute('SELECT t.*,g.session_id,g.client,g.resource,g.issuer,g.revoked,g.expires AS grant_expires '
                           'FROM oauth_token t JOIN oauth_grant g USING(grant_id) WHERE token_hash=? AND kind=?',
                           (hashed,'refresh')).fetchone()
            if (not row or row['issuer']!=self.issuer or row['revoked'] or client not in self.clients or row['client']!=client
                or resource!=self.resource or row['resource']!=resource or int(self.clock())>=row['expires']):
                raise OAuthError('invalid_grant')
            if row['used']:
                db.execute('UPDATE oauth_grant SET revoked=1 WHERE grant_id=?',(row['grant_id'],))
                return {'error':'invalid_grant'}  # commit family revocation before error
            self._session(db,row['session_id'])
            db.execute('UPDATE oauth_token SET used=1 WHERE token_hash=?',(hashed,))
            return self._pair(db,row['grant_id'],row['grant_expires'],access,refresh)
        result=self.manager._write('oauth-refresh-'+secrets.token_hex(16),['refresh',hashed],run)
        return dict(result,access_token=access,refresh_token=refresh)

    def authenticate(self,token,resource=None,scope=SCOPE):
        hashed=self._hash('access',token)
        if resource not in (None,self.resource) or scope!=SCOPE: raise OAuthError('invalid_token')
        def read(db):
            row=db.execute('SELECT t.*,g.session_id,g.client,g.resource,g.scope,g.issuer,g.revoked,g.expires AS grant_expires '
                           'FROM oauth_token t JOIN oauth_grant g USING(grant_id) WHERE token_hash=? AND kind=?',
                           (hashed,'access')).fetchone()
            if (not row or row['issuer']!=self.issuer or row['revoked'] or row['client'] not in self.clients or row['resource']!=self.resource
                or row['scope']!=scope or int(self.clock())>=min(row['expires'],row['grant_expires'])):
                raise OAuthError('invalid_token')
            s=self._session(db,row['session_id'])
            return OAuthPrincipal('account:'+s['user_id'],min(s['expires_at'],row['expires']),row['session_id'],token)
        return self.store.read(read)

    def session_guard(self,principal):
        if not isinstance(principal,OAuthPrincipal): return False
        try: return self.authenticate(principal.proof)==principal
        except (OAuthError,PermissionError): return False
