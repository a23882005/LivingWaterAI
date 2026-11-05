"""Embed audited daily scores for the V70 rolling calendar-day chart.

Only the latest FORMAL_VALID snapshot per Taipei date is used. The immutable
archive remains unchanged; missing dates are left to the client as explicit gaps.
"""
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/macro_safety_daily.csv"
SCHEMA = "V70.3/daily-observation-v1"


def history_payload(path=ARCHIVE, today=None):
    today = today or dt.datetime.now(ZoneInfo("Asia/Taipei")).date()
    days = {}
    if Path(path).exists():
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"observation_date", "health_score", "score_status", "feed_asof_utc",
                        "run_timestamp_utc", "daily_record_id", "source_commit", "v70_version"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("Rolling history archive schema is incomplete")
            for row in reader:
                if row["score_status"] != "FORMAL_VALID" or row.get("neutral_imputed_items"):
                    continue
                try:
                    day = dt.date.fromisoformat(row["observation_date"])
                    score = float(row["health_score"])
                    feed = dt.datetime.fromisoformat(row["feed_asof_utc"].replace("Z", "+00:00"))
                    run = dt.datetime.fromisoformat(row["run_timestamp_utc"].replace("Z", "+00:00"))
                    if feed.tzinfo is None or run.tzinfo is None:
                        continue
                    if feed.astimezone(ZoneInfo("Asia/Taipei")).date() != day:
                        continue
                    if not math.isfinite(score) or not 0 <= score <= 100:
                        continue
                    if not (today - dt.timedelta(days=59) <= day <= today):
                        continue
                    if not all(row[key] for key in ("daily_record_id", "source_commit", "v70_version")):
                        continue
                except (ValueError, TypeError):
                    continue
                order = (feed, run, row["daily_record_id"])
                if day not in days or order > days[day][0]:
                    days[day] = (order, {
                        "date": day.isoformat(), "score": score, "version": row["v70_version"],
                        "feedAsOf": row["feed_asof_utc"], "recordId": row["daily_record_id"],
                        "sourceCommit": row["source_commit"], "kind": "archive",
                    })
    return {"schema": SCHEMA, "archiveThrough": max(days).isoformat() if days else None,
            "rows": [days[day][1] for day in sorted(days)]}


def embed_history(markup, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    result, count = re.subn(
        r'(<script id="v703-daily-history" type="application/json">).*?(</script>)',
        lambda match: match[1] + encoded + match[2], markup, count=1, flags=re.S)
    if count != 1:
        raise ValueError("Missing V70 daily history embedding point")
    return result
