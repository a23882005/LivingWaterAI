#!/usr/bin/env python3
# 最後修改日期時間（台灣時間）：2026/10/19 08:03｜檔案名稱：capture_v703_daily_snapshot.py｜版本：正式 V70 分數每日稽核存檔
"""Capture the verified V70 browser Macro Safety score into an append-only CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = [
    "daily_record_id", "observation_date", "run_timestamp_utc", "feed_asof_utc",
    "v70_version", "source_commit", "feed_sha256", "health_score", "score_status",
    "neutral_imputed_items", "raw_indicator_values_json", "indicator_provenance_json",
    "source_snapshot_json",
]
EXPECTED_FEED_SCHEMA = "V70.3/family-macro-feed-v3"


class CaptureError(ValueError):
    pass


def validate_feed(feed: dict) -> dict:
    verification = feed.get("verification", {})
    if feed.get("schema") != EXPECTED_FEED_SCHEMA or feed.get("asOf") is None:
        raise CaptureError("Feed schema or asOf is not the current V70-3-27 format")
    if (verification.get("ready") is not True or verification.get("independentIndicators") != 25
            or verification.get("transportIndicators") != 28 or verification.get("valid") != 26
            or verification.get("totalRequired") != 26
            or verification.get("requiredScoringIndicators") != 22
            or verification.get("requiredScoringIndicatorsValidated") != 22):
        raise CaptureError("Feed has not passed the complete 25/28/26/22 V70 quality gate")
    indicators = feed.get("indicators")
    if not isinstance(indicators, dict) or len(indicators) != 28:
        raise CaptureError("Feed must contain exactly 28 transport indicators")
    if not all(feed.get("sourceSnapshot", {}).get(k) for k in ("macro18", "macro8", "wallstreet5")):
        raise CaptureError("Feed source snapshot is incomplete")
    timestamp = datetime.fromisoformat(str(feed["asOf"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise CaptureError("Feed asOf must be UTC")
    return indicators


def build_record(feed: dict, browser_snapshot: dict, run_timestamp_utc: str,
                 source_commit: str, feed_sha256: str) -> dict[str, str]:
    indicators = validate_feed(feed)
    if browser_snapshot.get("verified") is not True or browser_snapshot.get("canPublish") is not True:
        raise CaptureError("Live V70 page did not verify the feed and formal calculation")
    latest = browser_snapshot.get("latest")
    source_batch = browser_snapshot.get("sourceBatch")
    if not isinstance(latest, dict) or not isinstance(source_batch, dict):
        raise CaptureError("Live V70 page did not expose the verified calculation snapshot")
    if source_batch.get("asOf") != feed["asOf"]:
        raise CaptureError("Live browser feed timestamp differs from the validated build feed")
    if source_batch.get("sourceSnapshot") != feed.get("sourceSnapshot"):
        raise CaptureError("Live browser source lineage differs from the validated build feed")
    validation = latest.get("dataValidation", {})
    if validation.get("allMacroValuesPresent") is not True or validation.get("allDatesAndSourcesValid") is not True:
        raise CaptureError("Live Macro Safety inputs or source dates are incomplete")
    if latest.get("syntheticInputs") is True or str(latest.get("status", "")).startswith("DEMO_"):
        raise CaptureError("Synthetic/demo calculation cannot be archived as V70 daily data")
    try:
        score = float(latest["macroSafety"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CaptureError("Live page did not return mSafe_final") from exc
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise CaptureError(f"mSafe_final outside 0..100: {score}")
    if not latest.get("ruleVersion") or not source_commit or not feed_sha256:
        raise CaptureError("Missing V70 version, source commit, or feed digest")

    local_date = datetime.fromisoformat(feed["asOf"].replace("Z", "+00:00")).astimezone(
        ZoneInfo("Asia/Taipei")).date().isoformat()
    observation_date = feed.get("batchDateTaipei") or local_date
    raw_values = {key: ("NA" if row.get("value") is None or str(row.get("value")).strip() == ""
                        else row.get("value")) for key, row in indicators.items()}
    provenance = {key: row for key, row in indicators.items()}
    source_snapshot = {
        "asOf": feed["asOf"], "batchDateTaipei": feed.get("batchDateTaipei"),
        "sourceSnapshot": feed["sourceSnapshot"],
        "monthlyReleaseCalendar": feed.get("monthlyReleaseCalendar"),
        "browserRuleVersion": latest["ruleVersion"],
        "browserCalculatedAt": latest.get("calculatedAt"),
        "browserStatus": latest.get("status"),
    }
    record_key = "|".join((observation_date, feed["asOf"], source_commit))
    record_id = hashlib.sha256(record_key.encode("utf-8")).hexdigest()
    return {
        "daily_record_id": record_id, "observation_date": observation_date,
        "run_timestamp_utc": run_timestamp_utc, "feed_asof_utc": feed["asOf"],
        "v70_version": latest["ruleVersion"], "source_commit": source_commit,
        "feed_sha256": feed_sha256, "health_score": f"{score:.8f}".rstrip("0").rstrip("."),
        "score_status": "FORMAL_VALID", "neutral_imputed_items": "",
        "raw_indicator_values_json": json.dumps(raw_values, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "indicator_provenance_json": json.dumps(provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "source_snapshot_json": json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }


def read_archive(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or reader.fieldnames != FIELDS:
            raise CaptureError("Existing daily archive has an unexpected schema")
        rows = list(reader)
    ids = [r["daily_record_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise CaptureError("Existing daily archive contains duplicate record IDs")
    return rows


def append_idempotent(path: Path, record: dict[str, str]) -> bool:
    rows = read_archive(path)
    old = next((r for r in rows if r["daily_record_id"] == record["daily_record_id"]), None)
    if old:
        if any(old[f] != record[f] for f in FIELDS if f != "run_timestamp_utc"):
            raise CaptureError("An existing daily record ID has conflicting source or score data")
        return False
    rows.append(record)
    rows.sort(key=lambda r: (r["observation_date"], r["feed_asof_utc"], r["source_commit"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True


def read_live_snapshot(site_url: str, expected_asof: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise CaptureError("Playwright is required; install it with python -m pip install playwright") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
            page.route("**/cdn.tailwindcss.com/**", lambda route: route.abort())
            page.route("**/fonts.googleapis.com/**", lambda route: route.abort())
            url = site_url.rstrip("/") + "/?macro-safety-capture=" + expected_asof.replace(":", "")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_function(
                "window.v703FeedVerified===true && window.v703Latest && "
                "Number.isFinite(window.v703Latest.macroSafety) && window.v703SourceBatch",
                timeout=45000,
            )
            snapshot = page.evaluate("""() => ({
                verified: window.v703FeedVerified,
                canPublish: window.v703CanPublishFormalAllocation?.() === true,
                latest: window.v703Latest,
                sourceBatch: window.v703SourceBatch
            })""")
            return snapshot
        finally:
            browser.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True, type=Path)
    parser.add_argument("--site-url", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    try:
        feed_bytes = args.feed.read_bytes()
        feed = json.loads(feed_bytes.decode("utf-8"))
        validate_feed(feed)
        snapshot = read_live_snapshot(args.site_url, feed["asOf"])
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        record = build_record(feed, snapshot, now, args.source_commit, hashlib.sha256(feed_bytes).hexdigest())
        appended = append_idempotent(args.archive, record)
    except (CaptureError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"appended": appended, "observation_date": record["observation_date"],
                      "health_score": record["health_score"], "score_status": record["score_status"],
                      "archive": str(args.archive)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
