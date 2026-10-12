"""Fail-closed deployment configuration validation (not a deployed service)."""
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

class DeploymentConfigError(ValueError):
    pass

def _https_origin(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeploymentConfigError(name + ': missing')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise DeploymentConfigError(name + ': HTTPS required')
    if p.path not in ('', '/') or p.hostname.endswith('.test') or p.hostname in ('localhost', '127.0.0.1'):
        raise DeploymentConfigError(name + ': public origin required')
    return value.rstrip('/')

@dataclass(frozen=True)
class DeploymentConfig:
    resource_origin: str
    authorization_origin: str
    allowed_browser_origin: str

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        if env.get('PF_ENVIRONMENT') != 'production':
            raise DeploymentConfigError('PF_ENVIRONMENT must equal production')
        values = {
            'resource_origin': _https_origin(env.get('PF_RESOURCE_ORIGIN'), 'PF_RESOURCE_ORIGIN'),
            'authorization_origin': _https_origin(env.get('PF_AUTHORIZATION_ORIGIN'), 'PF_AUTHORIZATION_ORIGIN'),
            'allowed_browser_origin': _https_origin(env.get('PF_ALLOWED_BROWSER_ORIGIN'), 'PF_ALLOWED_BROWSER_ORIGIN')
        }
        if values['resource_origin'] == values['authorization_origin']:
            raise DeploymentConfigError('OAuth issuer must be explicitly separated')
        return cls(**values)
