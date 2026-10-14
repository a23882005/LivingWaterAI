"""Synthetic provenance receipt tests; no external data or network access."""
import hashlib
import json
import pytest
from pf_ci_evidence_receipt import receipt_from_junit, emit, verify

HEAD = "a" * 40
def xml(tests="3", failures="0", errors="0", skipped="0"):
    cases = "".join('<testcase classname="synthetic" name="safe{}"/>'.format(i) for i in range(int(tests))) if tests.isdigit() else ""
    return '<testsuites><testsuite tests="{}" failures="{}" errors="{}" skipped="{}">{}</testsuite></testsuites>'.format(tests, failures, errors, skipped, cases)

def write_xml(tmp_path, data):
    p = tmp_path / "results.xml"
    p.write_text(data, encoding="utf-8")
    return p

def test_receipt_minimal_and_gate_hold(tmp_path):
    path = write_xml(tmp_path, xml())
    receipt = emit(path, HEAD, tmp_path / "receipt")
    assert receipt["counts"]["tests"] == 3
    assert receipt["evidence_class"] == "SYNTHETIC_CI_ONLY"
    assert receipt["external_gate_a"] == "HOLD"
    assert receipt["work13_allowed"] is False
    assert verify(tmp_path / "receipt") == receipt
    assert "\"classname\"" not in (tmp_path / "receipt" / "receipt.json").read_text()
    assert "\"name\": \"safe\"" not in (tmp_path / "receipt" / "receipt.json").read_text()

def test_errors_and_failures_fail_closed(tmp_path):
    for kwargs in ({"failures":"1"}, {"errors":"1"}, {"tests":"0"}, {"tests":"bad"}):
        with pytest.raises(ValueError):
            receipt_from_junit(write_xml(tmp_path, xml(**kwargs)), HEAD)

def test_invalid_commit_rejected(tmp_path):
    with pytest.raises(ValueError):
        receipt_from_junit(write_xml(tmp_path, xml()), "not-a-real-sha")

def test_tampered_receipt_detected(tmp_path):
    emit(write_xml(tmp_path, xml()), HEAD, tmp_path / "receipt")
    p = tmp_path / "receipt" / "receipt.json"
    p.write_text(p.read_text().replace("HOLD", "PASS"))
    with pytest.raises(ValueError, match="sha256_mismatch"):
        verify(tmp_path / "receipt")

def test_forged_release_claim_rejected_even_with_valid_sha(tmp_path):
    emit(write_xml(tmp_path, xml()), HEAD, tmp_path / "receipt")
    folder = tmp_path / "receipt"
    p = folder / "receipt.json"
    data = json.loads(p.read_text())
    data["work13_allowed"] = True
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    p.write_bytes(payload)
    (folder / "receipt.sha256").write_text(hashlib.sha256(payload).hexdigest() + "  receipt.json\n")
    with pytest.raises(ValueError, match="unsafe_release_claim"):
        verify(folder)

def test_non_junit_and_secret_like_raw_content_not_carried(tmp_path):
    with pytest.raises(ValueError):
        receipt_from_junit(write_xml(tmp_path, "<not-junit/>"), HEAD)
    path = write_xml(tmp_path, xml().replace("safe", "Bearer_sensitive_token"))
    emit(path, HEAD, tmp_path / "receipt")
    assert "Bearer_sensitive_token" not in (tmp_path / "receipt" / "receipt.json").read_text()

def test_invalid_checksum_file_rejected(tmp_path):
    emit(write_xml(tmp_path, xml()), HEAD, tmp_path / "receipt")
    (tmp_path / "receipt" / "receipt.sha256").write_text("invalid")
    with pytest.raises(ValueError, match="sha256_mismatch"):
        verify(tmp_path / "receipt")

def test_null_or_string_counts_rejected(tmp_path):
    emit(write_xml(tmp_path, xml()), HEAD, tmp_path / "receipt")
    folder = tmp_path / "receipt"
    p = folder / "receipt.json"
    value = json.loads(p.read_text())
    value["counts"]["tests"] = "3"
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    p.write_bytes(payload)
    (folder / "receipt.sha256").write_text(hashlib.sha256(payload).hexdigest() + "  receipt.json\n")
    with pytest.raises(ValueError, match="invalid_counts"):
        verify(folder)

def test_expected_commit_must_match_even_with_valid_receipt(tmp_path):
    emit(write_xml(tmp_path, xml()), HEAD, tmp_path / "receipt")
    with pytest.raises(ValueError, match="receipt_commit_mismatch"):
        verify(tmp_path / "receipt", "b" * 40)

def test_skipped_and_inconsistent_junit_rejected(tmp_path):
    bad = '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="only"/></testsuite></testsuites>'
    for raw in (xml(skipped="1"), bad):
        with pytest.raises(ValueError, match="synthetic_suite_not_passed"):
            receipt_from_junit(write_xml(tmp_path, raw), HEAD)
