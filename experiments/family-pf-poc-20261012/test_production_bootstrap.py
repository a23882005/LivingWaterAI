"""The official production bootstrap fails closed before MCP route registration."""
import pytest
from pf_production_bootstrap import attach_production_mcp
from pf_deployment_config import DeploymentConfigError
from test_oauth_integration import env

GOOD = {
    'PF_ENVIRONMENT':'production',
    'PF_RESOURCE_ORIGIN':'https://pf.example.com',
    'PF_AUTHORIZATION_ORIGIN':'https://login.example.com',
    'PF_ALLOWED_BROWSER_ORIGIN':'https://app.example.com',
}

def test_missing_environment_fails_before_routes_registered(env):
    c, scope, sign, verifier, _=env
    with pytest.raises(DeploymentConfigError):
        attach_production_mcp(c.app, verifier, scope, {})
    assert all(getattr(route,'path',None)!='/mcp' for route in c.app.routes)

def test_test_domain_fails_before_routes_registered(env):
    c, scope, sign, verifier, _=env
    with pytest.raises(DeploymentConfigError):
        attach_production_mcp(c.app, verifier, scope, {**GOOD,'PF_RESOURCE_ORIGIN':'https://pf.example.test'})
    assert all(getattr(route,'path',None)!='/mcp' for route in c.app.routes)

def test_valid_production_environment_wires_metadata(env):
    c, scope, sign, verifier, _=env
    attach_production_mcp(c.app, verifier, scope, GOOD)
    response=c.get('/.well-known/oauth-protected-resource')
    assert response.status_code==200
    assert response.json()['resource']=='https://pf.example.com/mcp'

def test_valid_bootstrap_denies_cross_client(env):
    c, scope, sign, verifier, _=env
    attach_production_mcp(c.app, verifier, scope, GOOD)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+sign('joseph')},
      json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
      'name':'pf_read_resource','arguments':{'active_client_id':'mou','resource_id':'r-m'}}})
    assert r.json()['result']['isError'] is True
    assert scope.audit[-1]['decision']=='DENY'
