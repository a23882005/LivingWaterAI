#!/usr/bin/env python3
# 最後修改日期時間（台灣）：2026/10/16 02:30｜版本：D009-v2｜檔案：macro18_alert.py
"""Persist per-indicator failure counts and signal actionable notifications.

Alerts are written as JSON for the workflow notification job. State is written
to the automation-state worktree. No email address or secret is stored here.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import requests
from v703_cpi_availability import (
    FRED_CPI, add_archived_notice_provenance, load_archived_official_release,
    valid_official_gap, verify_official_gap,
)
from macro18_state import read_valid, read_diagnostics, atomic_write

CORE = {"m02", "m07", "m01", "m08", "m05", "m19"}
BAD = {"STALE", "MISSING"}
CPI_GAP_ERROR = "Insufficient CPILFESL history; missing 2025-10"
CPI_GAP_START = dt.datetime(2026, 11, 10, 13, 30, tzinfo=dt.timezone.utc)
CPI_GAP_END = dt.datetime(2026, 12, 10, 13, 30, tzinfo=dt.timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def cpi_gap_candidate(item):
    if item.get("status") not in BAD or item.get("attempt_result") != "FAILED":
        return False
    attempts = item.get("source_attempts", {}).get("CPILFESL", [])
    # An actual provider error (timeout, 429, parse failure, etc.) keeps its alert.
    return bool(attempts) and all(
        a.get("result") == "FAILED" and a.get("http_status") == 200
        and a.get("error", "").endswith(": ValueError: " + CPI_GAP_ERROR)
        for a in attempts
    )


def fresh_cpi_gap_evidence(report, now):
    if not CPI_GAP_START <= now < CPI_GAP_END:
        return None
    if not cpi_gap_candidate(report["items"].get("m05", {})):
        return None
    try:
        manifest = json.loads((ROOT / "data/cpi_official_release_20261110.json").read_text(encoding="utf-8"))
        release = load_archived_official_release(
            (ROOT / "data/audit/cpi_official_release_20261110.html.gz").read_bytes(), manifest, now)
        response = requests.get(FRED_CPI, timeout=(5, 15))
        response.raise_for_status()
        return add_archived_notice_provenance(verify_official_gap(response.content, release, now), manifest)
    except (requests.RequestException, ValueError, OSError, KeyError, TypeError) as exc:
        print("D009 official CPI gap not reverified; normal alert policy retained:", type(exc).__name__)
        return None


def evaluate(report, previous, today, *, cpi_evidence=None, now=None):
    old = previous.get("indicators", {})
    updated = {}
    alerts = []
    for key, item in report["items"].items():
        if key == "s03":
            continue
        status = item["status"]
        before = old.get(key, {})
        retrieval_failed=item.get("attempt_result")=="FAILED"
        failed=status in BAD or retrieval_failed
        count = int(before.get("consecutive_failures", 0)) + 1 if failed else 0
        last_alert = before.get("last_alert_date")
        should_alert = bool(count and last_alert != today and (count == 1 or count == 3 or (count > 3 and count % 3 == 0)))
        if key in CORE and failed and last_alert != today:
            should_alert = True
        expected_gap = (key == "m05" and now is not None
                        and cpi_gap_candidate(item) and valid_official_gap(cpi_evidence, now))
        if expected_gap:
            # Preserve STALE/MISSING in the report and state. This is not a new observation.
            should_alert = False
            count = 0
        if should_alert:
            alerts.append({"indicator": key, "status": status, "count": count,
                           "observation_date": item.get("observation_date"),
                           "retrieval_failed":retrieval_failed, "error":item.get("retrieval_error") or item.get("error",""),
                           "attempted_at":item.get("attempted_at"),"cache_used":item.get("cache_used",False),
                           "last_verified_at":item.get("last_verified_at"),"source_attempts":item.get("source_attempts",{})})
        updated[key] = {
            "consecutive_failures": count,
            "last_alert_date": today if should_alert else (last_alert if count else None),
            "status": status,
        }
        if expected_gap:
            updated[key]["alert_disposition"] = "OFFICIAL_CPI_BASE_PERIOD_UNAVAILABLE"
    return {"schema": "D009-alert-state-v1", "updated_at": today, "indicators": updated}, alerts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--diagnostics",help="latest diagnostics bound to this exact report")
    p.add_argument("--state", required=True)
    p.add_argument("--alert-file", required=True)
    args = p.parse_args()
    report = read_valid(args.report)
    if args.diagnostics:
        report=read_diagnostics(args.diagnostics,report)
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
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    evidence = fresh_cpi_gap_evidence(report, now)
    state, alerts = evaluate(report, previous, today, cpi_evidence=evidence, now=now)
    payload = {"alerts": alerts}
    if state["indicators"].get("m05", {}).get("alert_disposition"):
        payload["official_cpi_gap"] = evidence
        print("D009 m05: official 2025-10 CPI base absent; no failure notification; report unchanged")
    atomic_write(state_path, (json.dumps(state, ensure_ascii=False, indent=2)+"\n").encode())
    atomic_write(args.alert_file, (json.dumps(payload, ensure_ascii=False, indent=2)+"\n").encode())
    print("D009 alerts:", json.dumps(alerts, ensure_ascii=False))
    if alerts:
        print("::warning::D009 macro indicators require attention; inspect alert artifact")


if __name__ == "__main__":
    main()
