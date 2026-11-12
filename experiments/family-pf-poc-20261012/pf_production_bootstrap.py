"""Fail-closed experimental production bootstrap; does not deploy a service."""
import os
import base64
from pathlib import Path
from pf_deployment_config import DeploymentConfig
from pf_mcp_protocol import attach_mcp
from pf_audit_store import AuditStore

def attach_production_mcp(app, verifier, scope, environ=None):
    env = os.environ if environ is None else environ
    config = DeploymentConfig.from_environment(env)
    names = ("PF_AUDIT_DB_PATH", "PF_AUDIT_INTEGRITY_KEY_B64", "PF_AUDIT_PSEUDONYM_KEY_B64")
    if any(not env.get(name) for name in names):
        raise ValueError("Persistent audit configuration is required")
    path = Path(env["PF_AUDIT_DB_PATH"])
    if not path.is_absolute() or path.suffix != ".sqlite":
        raise ValueError("Absolute SQLite path required")
    try:
        integrity = base64.b64decode(env["PF_AUDIT_INTEGRITY_KEY_B64"], validate=True)
        pseudonym = base64.b64decode(env["PF_AUDIT_PSEUDONYM_KEY_B64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid audit key encoding") from exc
    audit = AuditStore(path, integrity, pseudonym_key=pseudonym)
    return attach_mcp(app, verifier, scope, deployment_config=config, persistent_audit=audit)
