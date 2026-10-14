"""Contract tests for isolated synthetic workflow execution, no network and no YAML dependencies."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/family-pf-ci.yml"

def test_workflow_locks_manual_execution_to_isolated_branch():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert text.count("github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/family-pf-ci-20261012'") == 2

def test_workflow_never_persists_checkout_credentials():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("uses: actions/checkout@v4") == 2
    assert text.count("persist-credentials: false") == 2

def test_workflow_has_least_privilege_and_retention():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in text
    assert "retention-days: 7" in text
    assert "cancel-in-progress: false" in text
    assert "family-pf-synthetic-" in text

def test_workflow_requires_second_job_receipt_verification():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "verify-evidence-receipt:" in text
    assert "needs: verify-pf-full-suite" in text
    assert '--expected-commit "$PF_EXPECTED_SHA"' in text
    assert "family-pf-synthetic-receipt" in text

def test_workflow_never_runs_unapproved_public_endpoint_probe():
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "pf_remote_preflight.py https://" not in content
    assert "curl https://" not in content
    assert "secrets." not in content

def test_receipt_cannot_authorize_gate_or_production():
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "verify-evidence-receipt:" in content
    assert "upload-artifact@v4" in content
    assert "deploy-pages" not in content
    assert "environment: production" not in content


def test_workflow_does_not_grant_write_or_id_token_permissions():
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "contents: read" in content
    assert "contents: write" not in content
    assert "id-token: write" not in content
    assert "pull-requests: write" not in content


def test_workflow_does_not_execute_deployment_actions():
    content = WORKFLOW.read_text(encoding="utf-8")
    forbidden = ("azure/webapps-deploy", "aws-actions/configure-aws-credentials",
                 "cloudflare/pages-action", "actions/deploy-pages",
                 "google-github-actions/deploy-cloudrun")
    for action in forbidden:
        assert action not in content
    assert "environment: production" not in content
