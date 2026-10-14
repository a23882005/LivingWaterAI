from pf_external_start_guard import assess, REQUIRED

def good():
    x = {key: "approved-" + key for key in REQUIRED}
    x.update(environment_type="isolated_nonproduction",
             test_data_class="synthetic_only", approval_for_live_test=True,
             endpoint_origin="https://approved.external.org")
    return x

def test_missing_dependencies_blocked():
    r = assess({"approval_for_live_test": True})
    assert r["external_test_start"] == "BLOCKED"
    assert "approved_scope_id" in r["missing_fields"]
    assert r["gate_a"] == "HOLD"

def test_complete_manifest_only_enables_operator_review():
    r = assess(good())
    assert r["external_test_start"] == "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
    assert r["gate_a"] == "HOLD" and not r["work13_allowed"]

def test_same_tenant_rejected():
    x = good()
    x["synthetic_tenant_b_id"] = x["synthetic_tenant_a_id"]
    assert "test_tenants_must_differ" in assess(x)["errors"]

def test_self_review_rejected():
    x = good()
    x["independent_reviewer_id"] = x["test_executor_id"]
    assert "reviewer_must_be_independent" in assess(x)["errors"]

def test_live_test_explicit_approval_required():
    x = good()
    x["approval_for_live_test"] = False
    assert assess(x)["external_test_start"] == "BLOCKED"

def test_rejects_real_data_or_production():
    x = good()
    x["test_data_class"] = "real_client"
    assert assess(x)["external_test_start"] == "BLOCKED"
    x = good()
    x["environment_type"] = "production"
    assert assess(x)["external_test_start"] == "BLOCKED"

def test_secrets_rejected():
    x = good()
    x["access_token"] = "dummy"
    assert "secret_like_key_in_manifest" in assess(x)["errors"]

def test_url_must_not_contain_embedded_secret():
    x = good()
    x["endpoint_origin"] = "https://usr:pw@host.org"
    assert assess(x)["external_test_start"] == "BLOCKED"

def test_non_object_blocks():
    assert assess([])["external_test_start"] == "BLOCKED"
