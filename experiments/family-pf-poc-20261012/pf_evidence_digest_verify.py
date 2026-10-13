"""Offline, bounded, explicit-path digest comparison. Never authorizes Gate A."""
import hashlib
import hmac
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024

def check_artifact(path, expected_digest):
    result = {"match": False, "state": "HOLD", "gate_a": "HOLD"}
    if not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
        result["reason"] = "invalid_digest"
        return result
    try:
        p = Path(path)
        if p.is_symlink() or not p.is_file():
            result["reason"] = "not_regular_file"
            return result
        if p.stat().st_size > MAX_BYTES:
            result["reason"] = "oversized_file"
            return result
        digest = hashlib.sha256()
        total = 0
        with p.open("rb") as stream:
            while block := stream.read(65536):
                total += len(block)
                if total > MAX_BYTES:
                    result["reason"] = "oversized_file"
                    return result
                digest.update(block)
        result["match"] = hmac.compare_digest(digest.hexdigest(), expected_digest)
        result["reason"] = "digest_match" if result["match"] else "digest_mismatch"
        return result
    except (OSError, ValueError, TypeError):
        result["reason"] = "unreadable_file"
        return result
