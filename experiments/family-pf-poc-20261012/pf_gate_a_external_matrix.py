"""Offline external Gate A acceptance matrix validator.

Only evidence *references* from independently approved external operations.
No tokens, no customer data, no URL fetches; fail closed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

IDS = tuple("EA-%02d" % i for i in range(1, 10))
DIGEST = re.compile(r"^[a-f0-9]{64}$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{5,255}$")
REQUIRED_KEYS = {"evidence_id", "artifact_reference", "sha256", "reviewer_reference", "status"}
PASS_STATUS = "INDEPENDENTLY_REVIEWED"
MAX_BYTES = 65536

def evaluate(entries):
    output = {"schema": "family-pf-gate-a-external-matrix-v1",
              "gate_a": "HOLD", "work13_allowed": False,
              "external_evidence_verified": False, "validation_errors": [],
              "controls": [{"id": i, "state": "NOT_VERIFIED"} for i in IDS]}
    if not isinstance(entries, list) or len(entries) != 9:
        output["validation_errors"].append("exactly_nine_entries_required")
        return output
    seen = set()
    for e in entries:
        if not isinstance(e, dict) or set(e) != REQUIRED_KEYS:
            output["validation_errors"].append("invalid_entry_schema")
            continue
        key = e["evidence_id"]
        if not isinstance(key, str) or key not in IDS or key in seen:
            output["validation_errors"].append("invalid_or_duplicate_evidence_id")
            continue
        seen.add(key)
        if e["status"] != PASS_STATUS:
            output["validation_errors"].append("independent_review_not_confirmed")
        for item in ("artifact_reference", "reviewer_reference"):
            v = e[item]
            if not isinstance(v, str) or not REF.fullmatch(v):
                output["validation_errors"].append("invalid_" + item)
        if not isinstance(e["sha256"], str) or not DIGEST.fullmatch(e["sha256"]):
            output["validation_errors"].append("invalid_sha256")
        # Self-claimed references can only ever qualify for human verification.
        if not output["validation_errors"]:
            output["controls"][IDS.index(key)]["state"] = "CLAIM_SUBMITTED_FOR_INDEPENDENT_VERIFICATION"
    if seen != set(IDS):
        output["validation_errors"].append("missing_control")
    if not output["validation_errors"]:
        output["external_evidence_verified"] = False
        output["manual_reviewer_action"] = "Verify audit-store originals, identity of reviewer, provenance, OAuth/TLS evidence, and governance sign-off"
    return output

def load(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized_evidence_manifest")
    def no_duplicates(pairs):
        item = {}
        for k, v in pairs:
            if k in item:
                raise ValueError("duplicate_manifest_key")
            item[k] = v
        return item
    return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = evaluate(load(args.manifest)) if args.manifest else evaluate(None)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        result = evaluate(None)
        result["validation_errors"] = ["unreadable_or_invalid_manifest"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
