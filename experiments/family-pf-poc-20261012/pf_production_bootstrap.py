"""Fail-closed application wiring for production MCP configuration.

This is a constructor, not a deployed service. OAuth verifier and authorization
scope must be supplied by the trusted server bootstrap, not request parameters.
"""
from pf_deployment_config import DeploymentConfig
from pf_mcp_protocol import attach_mcp

def attach_production_mcp(app, verifier, scope, environ=None):
    """Validate deployment environment before registering any MCP routes."""
    config = DeploymentConfig.from_environment(environ)
    return attach_mcp(app, verifier, scope, deployment_config=config)
