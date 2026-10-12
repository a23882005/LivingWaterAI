"""Gate A evidence checklist. Successful unit tests do not authorize release."""
REQUIRED_EVIDENCE = (
    "remote_https_reachable",
    "external_oauth_login_verified",
    "server_client_binding_verified",
    "cross_client_negative_verified",
    "audit_denials_verified",
)

def evaluate_gate_a(evidence):
    """Return HOLD unless all externally verified evidence is present."""
    if not isinstance(evidence, dict):
        return {"state": "HOLD", "missing": list(REQUIRED_EVIDENCE)}
    missing = [item for item in REQUIRED_EVIDENCE if evidence.get(item) is not True]
    return {"state": "PASS" if not missing else "HOLD", "missing": missing}
