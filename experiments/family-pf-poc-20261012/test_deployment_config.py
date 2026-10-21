"""Deployment config safety tests; no external traffic or OAuth secrets."""
import pytest
from pf_deployment_config import DeploymentConfig, DeploymentConfigError

GOOD = {
    'PF_ENVIRONMENT':'production',
    'PF_RESOURCE_ORIGIN':'https://pf.example.com',
    'PF_AUTHORIZATION_ORIGIN':'https://login.example.com',
    'PF_ALLOWED_BROWSER_ORIGIN':'https://app.example.com'
}

def test_valid_https_origins():
    cfg = DeploymentConfig.from_environment(GOOD)
    assert cfg.resource_origin == 'https://pf.example.com'

def test_environment_must_be_production():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_ENVIRONMENT':'testing'})

def test_missing_resource_origin_rejected():
    d=GOOD.copy(); d.pop('PF_RESOURCE_ORIGIN')
    with pytest.raises(DeploymentConfigError): DeploymentConfig.from_environment(d)

def test_plain_http_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_RESOURCE_ORIGIN':'http://pf.example.com'})

def test_test_domain_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_AUTHORIZATION_ORIGIN':'https://auth.example.test'})

def test_localhost_origin_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_ALLOWED_BROWSER_ORIGIN':'https://localhost'})

def test_issuer_same_as_resource_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_AUTHORIZATION_ORIGIN':'https://pf.example.com'})

def test_url_with_embedded_credentials_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_RESOURCE_ORIGIN':'https://user:secret@pf.example.com'})

def test_url_with_query_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_RESOURCE_ORIGIN':'https://pf.example.com/?token=oops'})

def test_wrong_origin_path_rejected():
    with pytest.raises(DeploymentConfigError):
        DeploymentConfig.from_environment({**GOOD,'PF_RESOURCE_ORIGIN':'https://pf.example.com/internal'})
