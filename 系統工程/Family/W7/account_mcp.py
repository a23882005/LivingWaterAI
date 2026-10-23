"""B07 stateless JSON MCP transport for verified session inspection only.

Business tools belong to B08 onward. No caller identity, SQL, path, resource ID,
or password accepted. HTTP deployment must enforce TLS/Host and bounded bodies.
"""
import json
from account_oauth import OAuthError,SCOPE

class AccountMCP:
    def __init__(self,oauth):self.oauth=oauth

    def handle(self,method,headers,raw=b''):
        headers={k.lower():v for k,v in headers.items()}
        out={'Cache-Control':'no-store','Content-Type':'application/json'}
        if method!='POST':return 405,out,b''
        if headers.get('content-type','').split(';')[0].strip()!='application/json':return 415,out,b''
        if len(raw)>8192:return 413,out,b''
        # Same-origin browser calls only; server-to-server clients omit Origin.
        from urllib.parse import urlsplit
        p=urlsplit(self.oauth.resource);origin=p.scheme+'://'+p.netloc
        if headers.get('origin') not in (None,origin):return 403,out,b''
        challenge=f'Bearer resource_metadata="{self.oauth.resource}/.well-known/oauth-protected-resource", scope="{SCOPE}"'
        try:
            value=headers.get('authorization','')
            if not value.startswith('Bearer '):raise OAuthError('invalid_token')
            principal=self.oauth.authenticate(value[7:])
        except (OAuthError,PermissionError):
            out['WWW-Authenticate']=challenge
            return 401,out,json.dumps({'error':'AUTH_REQUIRED'}).encode()
        except Exception:
            return 503,out,json.dumps({'error':'SERVICE_RETRY'}).encode()
        rid=None
        try:
            def unique(pairs):
                d={}
                for k,v in pairs:
                    if k in d:raise ValueError()
                    d[k]=v
                return d
            msg=json.loads(raw,object_pairs_hook=unique)
            if not isinstance(msg,dict) or msg.get('jsonrpc')!='2.0' or not isinstance(msg.get('method'),str):raise ValueError()
            rid=msg.get('id')
            if rid is not None and type(rid) not in (str,int):raise ValueError()
            name=msg['method'];params=msg.get('params',{})
            if not isinstance(params,dict):raise ValueError()
            if name=='notifications/initialized' and 'id' not in msg:return 202,out,b''
            if 'id' not in msg:raise ValueError()
            if name=='initialize':
                version=params.get('protocolVersion')
                if version not in ('2024-11-05','2025-03-26','2025-06-18'):version='2025-06-18'
                result={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'Family-account','version':'0.1.0'}}
            elif name=='ping':result={}
            elif name=='tools/list':
                result={'tools':[{'name':'family_session','description':'查詢目前已登入的Family帳號與固定登入截止時間。',
                    'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
                    'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False},
                    'securitySchemes':[{'type':'oauth2','scopes':[SCOPE]}]}]}
            elif name=='tools/call':
                if set(params)-{'name','arguments','_meta'} or params.get('name')!='family_session' or params.get('arguments',{})!={}:
                    return 200,out,json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32602,'message':'Invalid tool arguments'}}).encode()
                data={'user_id':principal.subject[len('account:'):], 'access_expires_at':principal.expires_at}
                result={'content':[{'type':'text','text':json.dumps(data)}],'structuredContent':data,'isError':False}
            else:return 200,out,json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}).encode()
            return 200,out,json.dumps({'jsonrpc':'2.0','id':rid,'result':result},ensure_ascii=False).encode()
        except (ValueError,TypeError,KeyError,UnicodeError):
            return 400,out,json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32600,'message':'Invalid request'}}).encode()
