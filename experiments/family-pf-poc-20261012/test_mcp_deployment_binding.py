"""Check production-config binding on the isolated MCP app; no public deployment."""
from pf_deployment_config import DeploymentConfig, DeploymentConfigError
from pf_mcp_protocol import attach_mcp
from test_oauth_integration import env

CONFIG={
    'PF_ENVIRONMENT':'production',
    'PF_RESOURCE_ORIGIN':'https://pf.example.com',
    'PF_AUTHORIZATION_ORIGIN':'https://login.example.com',
    'PF_ALLOWED_BROWSER_ORIGIN':'https://app.example.com'
}

def build(env):
    c,scope,sign,v,_=env
    config=DeploymentConfig.from_environment(CONFIG)
    attach_mcp(c.app,v,scope,deployment_config=config)
    return c,scope,sign

def test_configured_metadata_resource(env):
    c,scope,sign=build(env)
    assert c.get('/.well-known/oauth-protected-resource').json()['resource']=='https://pf.example.com/mcp'

def test_configured_metadata_issuer(env):
    c,scope,sign=build(env)
    assert c.get('/.well-known/oauth-protected-resource').json()['authorization_servers']==['https://login.example.com']

def test_configured_challenge(env):
    c,scope,sign=build(env)
    r=c.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==401 and 'https://pf.example.com/.well-known/oauth-protected-resource' in r.headers['WWW-Authenticate']

def test_configured_trusted_origin(env):
    c,scope,sign=build(env)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+sign('joseph'),'Origin':'https://app.example.com'},json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==200

def test_former_synthetic_origin_now_rejected(env):
    c,scope,sign=build(env)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+sign('joseph'),'Origin':'https://trusted.example.test'},json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==403 and scope.audit[-1]['decision']=='DENY'

def test_other_browser_origin_rejected(env):
    c,scope,sign=build(env)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+sign('joseph'),'Origin':'https://evil.example.com'},json={'jsonrpc':'2.0','id':1,'method':'initialize'})
    assert r.status_code==403

def test_invalid_config_rejected_before_server_wiring():
    from fastapi import FastAPI
    try:
        invalid=DeploymentConfig.from_environment({**CONFIG,'PF_RESOURCE_ORIGIN':'http://bad.example.com'})
    except DeploymentConfigError:
        return
    assert False, 'invalid deployment configuration unexpectedly accepted'
