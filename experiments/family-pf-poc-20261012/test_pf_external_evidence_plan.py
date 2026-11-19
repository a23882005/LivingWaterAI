"""Gate A evidence plan contract: offline, sanitized, never a release decision."""
import json
import pytest
from pf_external_evidence_plan import REQUIRED_EVIDENCE, build_plan, main
from test_pf_external_start_guard import good

def test_all_nine_unique_evidence_controls_are_required():
    ids = [row[0] for row in REQUIRED_EVIDENCE]
    assert ids == ["EA-%02d" % i for i in range(1, 10)]

def test_missing_manifest_does_not_release():
    plan = build_plan({})
    assert plan["gate_a"] == "HOLD"
    assert plan["work13_allowed"] is False
    assert plan["remote_tests_executed"] is False
    assert plan["authorization_preflight"] == "BLOCKED"
    assert len(plan["evidence_required"]) == 9
    assert all(row["state"] == "NOT_VERIFIED" for row in plan["evidence_required"])

def test_complete_synthetic_manifest_only_enables_operator_review():
    plan = build_plan(good())
    assert plan["authorization_preflight"] == "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
    assert plan["gate_a"] == "HOLD"
    assert plan["work13_allowed"] is False
    assert all(row["state"] == "NOT_VERIFIED" for row in plan["evidence_required"])

@pytest.mark.parametrize("mutate", [
    lambda m: m.update(approval_for_live_test=False),
    lambda m: m.update(environment_type="production"),
    lambda m: m.update(test_data_class="client_records"),
    lambda m: m.update(synthetic_tenant_b_id=m["synthetic_tenant_a_id"]),
    lambda m: m.update(independent_reviewer_id=m["test_executor_id"]),
    lambda m: m.update(endpoint_origin="http://unsafe.example.org"),
])
def test_no_unauthorized_status_leak_or_gate_release(mutate):
    manifest = good()
    mutate(manifest)
    plan = build_plan(manifest)
    assert plan["authorization_preflight"] == "BLOCKED"
    assert plan["gate_a"] == "HOLD"
    assert plan["work13_allowed"] is False

def test_report_never_includes_manifest_values():
    manifest = good()
    manifest["approved_scope_id"] = "PRIVATE_APPROVAL_REFERENCE"
    manifest["audit_store_approval_id"] = "PRIVATE_AUDIT_REFERENCE"
    plan = build_plan(manifest)
    serialized = json.dumps(plan)
    assert "PRIVATE_APPROVAL_REFERENCE" not in serialized
    assert "PRIVATE_AUDIT_REFERENCE" not in serialized
    assert "approved.external.org" not in serialized

def test_unrecognized_secret_field_cannot_enter_plan():
    manifest = good()
    manifest["access_token"] = "SUPER_SECRET_DO_NOT_EXPORT"
    plan = build_plan(manifest)
    assert plan["authorization_preflight"] == "BLOCKED"
    assert "SUPER_SECRET_DO_NOT_EXPORT" not in json.dumps(plan)

def test_cli_without_manifest_emits_blocked_evidence(tmp_path, monkeypatch):
    import sys
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(sys, "argv", ["tool", "--output", str(output)])
    assert main() == 0
    plan = json.loads(output.read_text())
    assert plan["gate_a"] == "HOLD"
    assert plan["authorization_preflight"] == "BLOCKED"

def test_cli_corrupted_file_remains_blocked(tmp_path, monkeypatch):
    import sys
    manifest = tmp_path / "bad.json"
    manifest.write_text('{"unsafe":')
    output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["tool", "--manifest", str(manifest), "--output", str(output)])
    assert main() == 0
    plan = json.loads(output.read_text())
    assert "invalid_manifest_file" in plan["authorization_issues"]
    assert plan["gate_a"] == "HOLD"
