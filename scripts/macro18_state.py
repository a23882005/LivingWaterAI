#!/usr/bin/env python3
# 最後修改：2026/10/16（台灣時間；精確時間未核實）｜版本：D009-v1｜檔案：macro18_state.py
"""Validate and rotate the last three distinct verified 18-macro JSON snapshots.

Usage:
  python scripts/macro18_state.py snapshot --input build/macro18/18_macro_verification.json --state-dir /tmp/macro-state
  python scripts/macro18_state.py recover --output data/18_macro_verification.json --state-dir /tmp/macro-state
Snapshots are validated observations, not a claim of fresh source retrieval.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

EXCLUDED = {"m06", "m03_qqq", "m03_spy", "m03_vt", "s05"}
VALID_STATUSES = {"OK", "USABLE", "STALE", "MISSING"}


def validate(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), dict):
        raise ValueError("invalid macro report schema")
    items = raw["items"]
    expected = {"m07","m01","m08","m02","m04","m05","m09","m10","m12",
                "m13","m14","m15","m16","m17","m18","m19","m20","s04","s03"}
    if set(items) != expected or any(k in items for k in EXCLUDED):
        raise ValueError("expected 18 independent indicators plus s03")
    if raw.get("independent_indicators", {}).get("total") != 18:
        raise ValueError("independent count mismatch")
    for key, item in items.items():
        if not isinstance(item, dict) or item.get("id") != key:
            raise ValueError("invalid item: " + key)
        if item.get("status") not in VALID_STATUSES:
            raise ValueError("invalid status: " + key)
        if item.get("value") is not None:
            import math
            if not math.isfinite(float(item["value"])):
                raise ValueError("nonfinite value: " + key)
            day = dt.date.fromisoformat(item["observation_date"])
            if day > dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date():
                raise ValueError("future observation: " + key)
            if not str(item.get("source_url", "")).startswith("https://"):
                raise ValueError("missing verified source: " + key)
    if any(k not in items for k in ("m07","m16")):
        raise ValueError("required indicators missing")
    if items["s03"]["value"] != items["m07"]["value"]:
        raise ValueError("VIX duplicate mismatch")
    history = raw.get("lei_history")
    if not isinstance(history, list) or len(history) != 3:
        raise ValueError("LEI three-month history absent")
    dates = [dt.date.fromisoformat(h["observation_date"]) for h in history]
    if dates != sorted(dates) or len(set(dates)) != 3:
        raise ValueError("LEI history dates must be unique and ascending")
    if any(not isinstance(h.get("value"), (int, float)) for h in history):
        raise ValueError("LEI history contains nonnumeric value")
    if history[-1].get("observation_date") != items["m16"].get("observation_date"):
        raise ValueError("LEI history date mismatch")
    if history[-1].get("value") != items["m16"].get("value"):
        raise ValueError("LEI history value mismatch")
    return raw


def read_valid(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="."+path.name+".", delete=False) as f:
            temp = Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def snapshots(state_dir):
    return sorted((Path(state_dir) / "backups").glob("macro18_*.json"), reverse=True)


def _is_valid_backup(path):
    try:
        read_valid(path)
        return True
    except (ValueError, OSError, TypeError, KeyError):
        return False


def snapshot(source, state_dir):
    raw = read_valid(source)
    payload = (json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    existing = snapshots(state_dir)
    # Don't rotate identical content. A stale report is not a new market observation.
    if existing:
        try:
            newest_valid = next((p for p in existing if _is_valid_backup(p)), None)
            old = read_valid(newest_valid) if newest_valid else None
            if old is not None and all(old["items"][k]["value"] == raw["items"][k]["value"] and old["items"][k]["observation_date"] == raw["items"][k]["observation_date"] for k in raw["items"]) and old.get("lei_history") == raw.get("lei_history"):
                print("D009 snapshot unchanged; existing backups retained")
                return False
        except (ValueError, OSError, TypeError, KeyError):
            pass
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = Path(state_dir) / "backups" / f"macro18_{stamp}_{digest}.json"
    atomic_write(target, payload)
    # Preserve the three newest VALID backups; corrupt files must not displace them.
    valid = []
    for old in snapshots(state_dir):
        try:
            read_valid(old)
            valid.append(old)
        except (ValueError, OSError, TypeError, KeyError):
            print("D009 invalid backup retained for investigation:", old.name)
    for old in valid[3:]:
        old.unlink()
    print("D009 validated snapshot saved:", target.name)
    return True


def recover(output, state_dir):
    for candidate in snapshots(state_dir):
        try:
            raw = read_valid(candidate)
            # A restored snapshot is historical, even if it was OK when first collected.
            for item in raw["items"].values():
                if item.get("value") is not None:
                    item["status"] = "STALE"
                    item["detail"] = (item.get("detail") or "") + "; D009 historical backup recovery"
            raw["recovery"] = {"mode": "HISTORICAL_BACKUP", "snapshot": candidate.name}
            atomic_write(output, (json.dumps(raw, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))
            print("D009 recovered HISTORICAL backup:", candidate.name)
            return candidate.name
        except (ValueError, OSError, TypeError, KeyError) as exc:
            print("D009 backup rejected:", candidate.name, type(exc).__name__)
    raise RuntimeError("No validated backup available; fail closed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("snapshot", "recover", "verify"))
    p.add_argument("--state-dir", required=True)
    p.add_argument("--input")
    p.add_argument("--output")
    a = p.parse_args()
    if a.command == "snapshot":
        if not a.input: p.error("--input required")
        snapshot(a.input, a.state_dir)
    elif a.command == "verify":
        if not a.input: p.error("--input required")
        read_valid(a.input)
        print("D009 report validation PASS")
    else:
        if not a.output: p.error("--output required")
        recover(a.output, a.state_dir)


if __name__ == "__main__":
    main()
