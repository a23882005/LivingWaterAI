"""Synthetic stateless JSON-RPC MCP transport. No production deployment."""
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field
from pf_backend_auth import AuthorizationDenied
from pf_oauth_verifier import TokenRejected

class RpcBody(BaseModel):
    jsonrpc: str
    id: int | str | None = None
    method: str
    params: dict = Field(default_factory=dict)

TOOL = {'name':'pf_read_resource','description':'Read an authorized synthetic resource',
        'inputSchema': {'type':'object','properties':{'active_client_id':{'type':'string'},'resource_id':{'type':'string'}},
                        'required':['active_client_id','resource_id'],'additionalProperties':False}}

def attach_mcp(app, verifier, scope):
    # Synthetic metadata URL; replace with actual HTTPS origin and OAuth issuer before deployment.
    metadata_url = 'https://pf.example.test/.well-known/oauth-protected-resource'
    challenge = {'WWW-Authenticate': f'Bearer resource_metadata="{metadata_url}"'}

    @app.middleware('http')
    async def ensure_oauth_challenge(request, call_next):
        response = await call_next(request)
        if request.url.path == '/mcp' and response.status_code == 401:
            response.headers['WWW-Authenticate'] = challenge['WWW-Authenticate']
        return response

    @app.get('/.well-known/oauth-protected-resource')
    def protected_resource_metadata():
        return {'resource':'https://pf.example.test/mcp',
                'authorization_servers':['https://auth.example.test'],
                'scopes_supported':['pf:read']}

    @app.post('/mcp')
    def mcp_rpc(body: RpcBody, authorization: str | None = Header(default=None), origin: str | None = Header(default=None)):
        # Synthetic allowlist. Real deployment must load exact allowed origins from trusted configuration.
        if origin is not None and origin not in {'https://trusted.example.test'}:
            scope.audit.append({'action':'mcp_origin','decision':'DENY','reason':'untrusted_origin'})
            raise HTTPException(403,'forbidden_origin')
        if not authorization or not authorization.startswith('Bearer '):
            scope.audit.append({'action':'mcp_authentication','decision':'DENY','reason':'missing_bearer'})
            raise HTTPException(401,'unauthorized',headers=challenge)
        try:
            principal=verifier.verify(authorization[7:])
        except TokenRejected as ex:
            scope.audit.append({'action':'mcp_authentication','decision':'DENY','reason':str(ex)})
            raise HTTPException(401,'unauthorized') from ex
        if body.jsonrpc != '2.0' or body.id is None:
            return {'jsonrpc':'2.0','id':body.id,'error':{'code':-32600,'message':'Invalid Request'}}
        if body.method == 'initialize':
            result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'family-pf-synthetic-poc','version':'0.1'}}
        elif body.method == 'tools/list':
            result={'tools':[TOOL]}
        elif body.method == 'tools/call':
            if body.params.get('name') != TOOL['name']:
                return {'jsonrpc':'2.0','id':body.id,'error':{'code':-32602,'message':'Unknown tool'}}
            args=body.params.get('arguments',{})
            if not isinstance(args,dict) or set(args) != {'active_client_id','resource_id'} or any(not isinstance(v,str) or not v for v in args.values()):
                return {'jsonrpc':'2.0','id':body.id,'error':{'code':-32602,'message':'Invalid arguments'}}
            try:
                value=scope.read(verified_user_id=principal,active_client_id=args['active_client_id'],resource_id=args['resource_id'])
            except AuthorizationDenied:
                return {'jsonrpc':'2.0','id':body.id,'result':{'content':[{'type':'text','text':'access_denied'}],'isError':True}}
            result={'content':[{'type':'text','text':value}]}
        else:
            return {'jsonrpc':'2.0','id':body.id,'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':body.id,'result':result}
    return app
