"""Offline, bounded, explicit-path digest comparison. Never authorizes Gate A."""
import hashlib
import hmac
import os
import stat
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
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(p, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                result["reason"] = "not_regular_file"
                return result
            if opened.st_size > MAX_BYTES:
                result["reason"] = "oversized_file"
                return result
            before = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            while block := stream.read(65536):
                total += len(block)
                if total > MAX_BYTES:
                    result["reason"] = "oversized_file"
                    return result
                digest.update(block)
            finished = os.fstat(stream.fileno())
            after = (finished.st_dev, finished.st_ino, finished.st_size, finished.st_mtime_ns, finished.st_ctime_ns)
            if after != before:
                result["reason"] = "file_changed_during_read"
                return result
        result["match"] = hmac.compare_digest(digest.hexdigest(), expected_digest)
        result["reason"] = "digest_match" if result["match"] else "digest_mismatch"
        return result
    except (OSError, ValueError, TypeError):
        result["reason"] = "unreadable_file"
        return result
