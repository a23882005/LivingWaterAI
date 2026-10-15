#!/usr/bin/env python3
# 最後修改日期時間（台灣）：2026/10/16 02:30｜版本：D009-v2｜檔案：macro18_alert.py
"""Persist per-indicator failure counts and signal actionable notifications.

Exit 2 when alert-worthy, exit 0 otherwise. State is written to automation-state
worktree. No email address or secret is stored here.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from macro18_state import read_valid, atomic_write

CORE = {"m02", "m07", "m01", "m08", "m05", "m19"}
BAD = {"STALE", "MISSING"}


def evaluate(report, previous, today):
    old = previous.get("indicators", {})
    updated = {}
    alerts = []
    for key, item in report["items"].items():
        if key == "s03":
            continue
        status = item["status"]
        before = old.get(key, {})
        count = int(before.get("consecutive_failures", 0)) + 1 if status in BAD else 0
        last_alert = before.get("last_alert_date")
        should_alert = (count in (1, 3) or (count > 3 and last_alert != today)) if count else False
        if key in CORE and status in BAD and last_alert != today:
            should_alert = True
        if should_alert:
            alerts.append({"indicator": key, "status": status, "count": count,
                           "observation_date": item.get("observation_date")})
        updated[key] = {
            "consecutive_failures": count,
            "last_alert_date": today if should_alert else (last_alert if count else None),
            "status": status,
        }
    return {"schema": "D009-alert-state-v1", "updated_at": today, "indicators": updated}, alerts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--alert-file", required=True)
    args = p.parse_args()
    report = read_valid(args.report)
    state_path = Path(args.state)
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            if previous.get("schema") != "D009-alert-state-v1":
                raise ValueError("invalid alert state schema")
        except (ValueError, OSError, TypeError) as exc:
            raise RuntimeError("Alert state invalid; refuse to silently reset counts") from exc
    else:
        previous = {}
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    state, alerts = evaluate(report, previous, today)
    atomic_write(state_path, (json.dumps(state, ensure_ascii=False, indent=2)+"\n").encode())
    atomic_write(args.alert_file, (json.dumps({"alerts": alerts}, ensure_ascii=False, indent=2)+"\n").encode())
    print("D009 alerts:", json.dumps(alerts, ensure_ascii=False))
    if alerts:
        print("::warning::D009 macro indicators require attention; inspect alert artifact")


if __name__ == "__main__":
    main()
