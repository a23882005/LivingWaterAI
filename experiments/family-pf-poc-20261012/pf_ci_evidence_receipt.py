"""Create and verify minimal synthetic CI evidence; never represents external Gate A proof."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

SCHEMA = "family-pf-synthetic-ci-receipt-v1"
GATE = "HOLD"
CHECKSUM_FILE = "receipt.sha256"
RECEIPT_FILE = "receipt.json"

def receipt_from_junit(path, head_sha):
    if not isinstance(head_sha, str) or len(head_sha) != 40 or any(x not in "0123456789abcdef" for x in head_sha):
        raise ValueError("invalid_commit_sha")
    raw = Path(path).read_bytes()
    root = ElementTree.fromstring(raw)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if root.tag not in ("testsuites", "testsuite") or not suites:
        raise ValueError("no_junit_suites")
    total = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in total:
            value = suite.attrib.get(key, "")
            if not value.isdigit():
                raise ValueError("invalid_junit_count")
            total[key] += int(value)
    if total["tests"] <= 0 or total["failures"] or total["errors"] or total["skipped"]:
        raise ValueError("synthetic_suite_not_passed")
    if sum(len(suite.findall("testcase")) for suite in suites) != total["tests"]:
        raise ValueError("synthetic_suite_not_passed")
    return {
        "schema": SCHEMA, "evidence_class": "SYNTHETIC_CI_ONLY",
        "commit_sha": head_sha, "junit_sha256": hashlib.sha256(raw).hexdigest(),
        "counts": total, "external_gate_a": GATE, "work13_allowed": False,
        "external_oauth_verified": False, "independent_audit_reviewed": False,
    }

def emit(xml_path, head_sha, output_dir):
    receipt = receipt_from_junit(xml_path, head_sha)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (target / RECEIPT_FILE).write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (target / CHECKSUM_FILE).write_text(f"{digest}  {RECEIPT_FILE}\n", encoding="ascii")
    return receipt

def verify(directory, expected_commit=None):
    root = Path(directory)
    payload = (root / RECEIPT_FILE).read_bytes()
    line = (root / CHECKSUM_FILE).read_text(encoding="ascii")
    if line != hashlib.sha256(payload).hexdigest() + "  receipt.json\n":
        raise ValueError("receipt_sha256_mismatch")
    receipt = json.loads(payload)
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema", "evidence_class", "commit_sha", "junit_sha256", "counts",
        "external_gate_a", "work13_allowed", "external_oauth_verified",
        "independent_audit_reviewed",
    }:
        raise ValueError("invalid_receipt_schema")
    if receipt["schema"] != SCHEMA or receipt["evidence_class"] != "SYNTHETIC_CI_ONLY" or receipt["external_gate_a"] != GATE:
        raise ValueError("invalid_receipt_classification")
    if any(receipt[k] is not False for k in ("work13_allowed", "external_oauth_verified", "independent_audit_reviewed")):
        raise ValueError("unsafe_release_claim")
    counts = receipt["counts"]
    if not isinstance(counts, dict) or set(counts) != {"tests", "failures", "errors", "skipped"}:
        raise ValueError("invalid_counts")
    if any(type(counts[k]) is not int or counts[k] < 0 for k in counts):
        raise ValueError("invalid_counts")
    if counts["tests"] < 1 or counts["failures"] or counts["errors"] or counts["skipped"]:
        raise ValueError("synthetic_suite_not_passed")
    for k in ("commit_sha", "junit_sha256"):
        v = receipt[k]
        if not isinstance(v, str) or len(v) != (40 if k == "commit_sha" else 64) or any(c not in "0123456789abcdef" for c in v):
            raise ValueError("invalid_digest")
    if expected_commit is not None and receipt["commit_sha"] != expected_commit:
        raise ValueError("receipt_commit_mismatch")
    return receipt

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("emit", "verify"))
    parser.add_argument("--junit")
    parser.add_argument("--commit")
    parser.add_argument("--expected-commit")
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    if args.action == "emit":
        if not args.junit or not args.commit:
            parser.error("emit requires --junit and --commit")
        print(json.dumps(emit(args.junit, args.commit, args.directory), sort_keys=True))
    else:
        print(json.dumps(verify(args.directory, args.expected_commit), sort_keys=True))
