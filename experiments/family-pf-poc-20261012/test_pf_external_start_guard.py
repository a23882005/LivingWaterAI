from datetime import datetime, timezone, timedelta
from pf_external_start_guard import assess, REQUIRED

def good():
    x = {key: "approved-" + key for key in REQUIRED}
    now = datetime.now(timezone.utc)
    start = (now + timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=2)).isoformat()
    x["test_window_utc"] = start + "/" + end
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

def test_origin_rejects_nonpublic_and_malformed_urls():
    for invalid in (
        "https://localhost", "https://127.0.0.1", "https://192.168.1.2",
        "https://[::1]", "https://example.test",
        "https://site.org/private/path", "https://site.org:8443",
        "https://site.org?auth=1", "https://site.org#fragment",
        "https://site.org\\\\attack", "https://site.org bad", "https://",
        "http://site.org", "https://site.org@evil.org",
    ):
        x = good()
        x["endpoint_origin"] = invalid
        r = assess(x)
        assert r["external_test_start"] == "BLOCKED", invalid
        assert "endpoint_must_be_public_https_origin" in r["errors"], invalid

def test_public_https_origin_still_requires_human_review():
    x = good()
    x["endpoint_origin"] = "https://auth.example.org:443"
    r = assess(x)
    assert r["external_test_start"] == "READY_FOR_AUTHORIZED_OPERATOR_REVIEW"
    assert r["gate_a"] == "HOLD"

def test_window_must_be_future_bounded_utc():
    for value in ("pending", "2026-01-01T00:00:00Z/2026-01-02T00:00:00Z",
                  "2029-01-01T00:00:00/2029-01-01T01:00:00",
                  "2099-01-01T00:00:00Z/2099-01-04T00:00:00Z",
                  "2099-01-01T02:00:00Z/2099-01-01T01:00:00Z"):
        x = good()
        x["test_window_utc"] = value
        assert "test_window_must_be_future_utc_under_24h" in assess(x)["errors"]
        assert assess(x)["external_test_start"] == "BLOCKED"
