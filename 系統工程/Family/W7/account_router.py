"""Exact HTTPS routes for account UI, OAuth discovery and stateless MCP."""
from urllib.parse import urlsplit
from oauth_http import OAuthHTTP
from account_mcp import AccountMCP


class AccountRouter:
    def __init__(self,oauth,account,base):
        self.oauth,self.account,self.base=oauth,account,base
        self.http=OAuthHTTP(oauth,account,base)
        self.mcp=AccountMCP(oauth)
        origin=account.origin
        if oauth.issuer!=origin+base+'/oauth' or oauth.resource!=origin+base+'/mcp':
            raise ValueError('ROUTE_CONFIGURATION_MISMATCH')

    def handle(self,method,path,headers,raw=b'',peer=''):
        h={k.lower():v for k,v in headers.items()}
        empty=[('Content-Type','application/json'),('Cache-Control','no-store')]
        if h.get('host')!=self.account.host or h.get('origin') not in (None,self.account.origin):return 403,empty,b'{}'
        if len(raw)>8192 or len(path)>10000:return 413,empty,b'{}'
        p=urlsplit(path)
        if p.scheme or p.netloc or p.fragment or '%' in p.path or '//' in p.path or '/.' in p.path.replace('/.well-known/','/well-known/'):
            return 400,empty,b'{}'
        metadata={self.base+'/oauth/.well-known/oauth-authorization-server':'/metadata',
            '/.well-known/oauth-authorization-server'+self.base+'/oauth':'/metadata',
            self.base+'/mcp/.well-known/oauth-protected-resource':'/resource-metadata',
            '/.well-known/oauth-protected-resource'+self.base+'/mcp':'/resource-metadata'}
        if p.path in metadata and not p.query:
            return self.http.handle(method,metadata[p.path],h,raw,peer)
        if p.path==self.base+'/mcp' and not p.query:
            status,hs,body=self.mcp.handle(method,h,raw)
            return status,list(hs.items()),body
        if p.path in (self.base+'/oauth/authorize',self.base+'/oauth/token'):
            return self.http.handle(method,path[len(self.base+'/oauth'):],h,raw,peer)
        account_paths=('/', '/login','/session','/change-password','/logout','/manage')
        suffix=p.path[len(self.base):] if p.path.startswith(self.base) else None
        if suffix in ('',)+account_paths and not p.query:
            return self.account.handle(method,suffix or '/',h,raw,peer)
        return 404,empty,b'{}'
