"""Offline inventory tests are synthetic and are not live Gate A evidence."""
from datetime import datetime, timezone, timedelta
from pf_external_evidence_inventory import inspect_inventory
from pf_gate_a_checklist import REQUIRED_EVIDENCE

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)

def records():
    return {key: {"result": "OBSERVED",
                  "evidence_url": "https://auditor.example.org/review/" + key,
                  "witness_role": "independent_security_reviewer",
                  "observed_at": NOW.isoformat()} for key in REQUIRED_EVIDENCE}

def test_empty_inventory_holds():
    result = inspect_inventory({}, NOW)
    assert result["state"] == "HOLD"
    assert result["missing"] == list(REQUIRED_EVIDENCE)

def test_full_synthetic_inventory_is_review_only():
    result = inspect_inventory(records(), NOW)
    assert result["state"] == "REVIEW_PACKAGE_READY"
    assert result["gate_a"] == "HOLD"
    assert result["verification"] == "NOT_INDEPENDENTLY_VERIFIED"

def test_every_missing_requirement_holds():
    for key in REQUIRED_EVIDENCE:
        items = records()
        del items[key]
        assert inspect_inventory(items, NOW)["missing"] == [key]

def test_self_review_cannot_be_review_ready():
    items = records()
    items["audit_denials_verified"]["witness_role"] = "developer"
    assert inspect_inventory(items, NOW)["state"] == "HOLD"

def test_observation_in_future_is_invalid():
    items = records()
    items["remote_https_reachable"]["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    assert inspect_inventory(items, NOW)["invalid"] == ["remote_https_reachable"]

def test_private_evidence_reference_is_invalid():
    items = records()
    items["external_oauth_login_verified"]["evidence_url"] = "https://127.0.0.1/proof"
    assert inspect_inventory(items, NOW)["state"] == "HOLD"

def test_query_string_with_token_is_invalid():
    items = records()
    items["server_client_binding_verified"]["evidence_url"] = "https://auditor.example.org/proof?token=secret"
    assert inspect_inventory(items, NOW)["state"] == "HOLD"

def test_no_unobserved_evidence_claims_allowed():
    items = records()
    items["cross_client_negative_verified"]["result"] = "PLANNED"
    assert inspect_inventory(items, NOW)["invalid"] == ["cross_client_negative_verified"]

def test_naive_validation_clock_holds():
    assert inspect_inventory(records(), datetime(2026,10,14))["state"] == "HOLD"


def test_stale_evidence_rejected():
    items=records()
    items['audit_denials_verified']['observed_at']=(NOW-timedelta(days=8)).isoformat()
    result=inspect_inventory(items,NOW)
    assert result['state']=='HOLD'
    assert result['invalid']==['audit_denials_verified']

def test_fresh_evidence_within_window_review_only():
    items=records()
    items['audit_denials_verified']['observed_at']=(NOW-timedelta(days=6)).isoformat()
    result=inspect_inventory(items,NOW)
    assert result['state']=='REVIEW_PACKAGE_READY'
    assert result['gate_a']=='HOLD'


def test_odd_url_separator_stays_hold():
    items=records()
    items['remote_https_reachable']['evidence_url']='https://auditor.example.org/a' + chr(92) + 'b'
    assert inspect_inventory(items,NOW)['state']=='HOLD'


def test_control_character_in_evidence_reference_rejected():
    for ch in (chr(10), chr(13), chr(9), chr(127)):
        items=records()
        items['remote_https_reachable']['evidence_url']='https://auditor.example.org/review/a'+ch+'b'
        result=inspect_inventory(items,NOW)
        assert result['state']=='HOLD'
        assert result['gate_a']=='HOLD'


def test_unicode_whitespace_evidence_url_rejected():
    for ch in (chr(32), chr(160), chr(8195)):
        items=records()
        items['remote_https_reachable']['evidence_url']='https://auditor.example.org/review/a'+ch+'b'
        result=inspect_inventory(items,NOW)
        assert result['state']=='HOLD'
        assert result['gate_a']=='HOLD'
