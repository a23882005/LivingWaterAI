#!/usr/bin/env python3
# 最後修改日期時間（台灣時間）：2026/10/19 08:03｜檔案名稱：macro_safety_monthly.py｜版本：真實月快照與月斜率乾跑
"""Build a research-only monthly Macro Safety slope/backtest CSV.

This tool consumes an already computed health score from a verified daily V70
archive. It never computes or changes the score, and never interpolates rows.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

DAILY_REQUIRED = {
    "observation_date", "run_timestamp_utc", "v70_version", "source_commit",
    "health_score", "score_status", "neutral_imputed_items",
}
PRICE_REQUIRED = {"date", "close"}
OUTPUT_FIELDS = [
    "snapshot_month", "snapshot_date", "source_daily_observation_date",
    "health_score", "previous_snapshot_date", "previous_health_score",
    "elapsed_months", "delta_points", "slope_points_per_month",
    "sp500_start_date", "sp500_start_close", "sp500_forward_end_date",
    "sp500_forward_end_close", "sp500_forward_3m_return_pct", "return_status",
    "score_status", "neutral_imputed_items", "run_timestamp_utc", "source_commit",
]


class DataError(ValueError):
    pass


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise DataError(f"{path}: CSV has no header")
        rows = list(reader)
        return rows, list(reader.fieldnames)


def read_daily(path: Path) -> list[dict[str, str]]:
    rows, fields = _read_rows(path)
    missing = DAILY_REQUIRED - set(fields)
    if missing:
        raise DataError(
            f"{path}: not a daily Macro Safety archive; missing required columns "
            f"{', '.join(sorted(missing))}. Quarterly research files cannot be used "
            "or expanded into monthly observations."
        )
    return read_daily_from_rows(rows)


def read_daily_from_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    parsed = []
    seen = set()
    for row in rows:
        try:
            obs = date.fromisoformat(row["observation_date"])
            timestamp = datetime.fromisoformat(row["run_timestamp_utc"].replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise DataError(f"Invalid daily observation date/timestamp: {row}") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
            raise DataError(f"Daily run_timestamp_utc must be timezone-aware UTC: {row}")
        key = (row["observation_date"], row["run_timestamp_utc"])
        if key in seen:
            raise DataError(f"Duplicate daily record key: {key}")
        seen.add(key)
        if not row.get("v70_version", "").strip() or not row.get("source_commit", "").strip():
            raise DataError(f"Missing V70 version or source commit at {obs}")
        if row.get("neutral_imputed_items") is None:
            raise DataError(f"Missing neutral_imputed_items at {obs}")
        if row["score_status"].strip().upper() not in {"VALID", "FORMAL_VALID"}:
            continue
        try:
            score = float(row["health_score"])
        except (ValueError, TypeError) as exc:
            raise DataError(f"Invalid health_score at {obs}: {row['health_score']!r}") from exc
        if not math.isfinite(score) or not 0 <= score <= 100:
            raise DataError(f"health_score outside 0..100 at {obs}: {score}")
        row["_date"] = obs.isoformat()
        row["_score"] = score
        parsed.append(row)
    parsed.sort(key=lambda r: (r["_date"], r["run_timestamp_utc"]))
    return parsed


def read_prices(path: Path) -> list[tuple[date, float]]:
    rows, fields = _read_rows(path)
    missing = PRICE_REQUIRED - set(fields)
    if missing:
        raise DataError(f"{path}: missing S&P 500 price columns: {', '.join(sorted(missing))}")
    values = []
    for row in rows:
        try:
            day, close = date.fromisoformat(row["date"]), float(row["close"])
        except (ValueError, TypeError) as exc:
            raise DataError(f"Invalid price row: {row}") from exc
        if not math.isfinite(close) or close <= 0:
            raise DataError(f"Invalid S&P 500 close: {row}")
        values.append((day, close))
    if not values:
        raise DataError(f"{path}: S&P 500 price file has no observations")
    if len({d for d, _ in values}) != len(values):
        raise DataError("S&P 500 price file has duplicate dates")
    return sorted(values)


def _cutoff(year: int, month: int, cutoff_day: int) -> date:
    # If a month is shorter than the configured day, use its final calendar day.
    nxt = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return min(date(year, month, 1) + timedelta(days=cutoff_day - 1), nxt - timedelta(days=1))


def _price_at_or_before(prices: list[tuple[date, float]], day: date):
    eligible = [(d, p) for d, p in prices if d <= day]
    return eligible[-1] if eligible else (None, None)


def _price_at_or_after(prices: list[tuple[date, float]], day: date):
    eligible = [(d, p) for d, p in prices if d >= day]
    return eligible[0] if eligible else (None, None)


def build_monthly(daily, prices, cutoff_day: int, as_of: date, run_timestamp_utc: str,
                  retry_month: str | None = None):
    if not 1 <= cutoff_day <= 31:
        raise DataError("cutoff_day must be 1..31")
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in daily:
        d = date.fromisoformat(row["_date"])
        month = d.strftime("%Y-%m")
        month_cutoff = _cutoff(d.year, d.month, cutoff_day)
        # A delayed retry may use the real successful daily observation after
        # the planned day, but only for the explicitly named month.
        if retry_month == month and as_of > month_cutoff:
            month_cutoff = as_of
        if d <= as_of and d <= month_cutoff:
            by_month.setdefault(d.strftime("%Y-%m"), []).append(row)

    chosen = []
    for month in sorted(by_month):
        # The latest verified daily observation on or before that month's cutoff.
        chosen.append(max(by_month[month], key=lambda r: (r["_date"], r["run_timestamp_utc"])))

    output = []
    prev = None
    for row in chosen:
        snap = date.fromisoformat(row["_date"])
        if prices:
            start_date, start_close = _price_at_or_before(prices, snap)
            target = _add_months(snap, 3)
            end_date, end_close = _price_at_or_after(prices, target)
            matured = target <= as_of and end_date is not None and end_date <= as_of
            ret = (end_close / start_close - 1) * 100 if matured and start_close else None
            return_status = "REALIZED" if matured and ret is not None else "PENDING"
        else:
            start_date = start_close = end_date = end_close = ret = None
            matured = False
            return_status = "SOURCE_PENDING"
        elapsed = delta = slope = None
        prev_date = prev_score = ""
        if prev:
            prev_date, prev_score = prev["_date"], prev["_score"]
            elapsed = _elapsed_calendar_months(date.fromisoformat(prev_date), snap)
            delta = row["_score"] - prev_score
            slope = delta / elapsed if elapsed > 0 else None
        output.append({
            "snapshot_month": snap.strftime("%Y-%m"),
            "snapshot_date": snap.isoformat(),
            "source_daily_observation_date": snap.isoformat(),
            "health_score": _fmt(row["_score"]),
            "previous_snapshot_date": prev_date,
            "previous_health_score": _fmt(prev_score) if prev_score != "" else "",
            "elapsed_months": _fmt(elapsed), "delta_points": _fmt(delta),
            "slope_points_per_month": _fmt(slope),
            "sp500_start_date": start_date.isoformat() if start_date else "",
            "sp500_start_close": _fmt(start_close),
            "sp500_forward_end_date": end_date.isoformat() if matured and end_date else "",
            "sp500_forward_end_close": _fmt(end_close) if matured else "",
            "sp500_forward_3m_return_pct": _fmt(ret),
            "return_status": return_status,
            "score_status": row["score_status"],
            "neutral_imputed_items": row["neutral_imputed_items"],
            "run_timestamp_utc": run_timestamp_utc,
            "source_commit": row["source_commit"],
        })
        prev = row
    return output


def _add_months(d: date, months: int) -> date:
    n = d.month - 1 + months
    year, month = d.year + n // 12, n % 12 + 1
    # Clamp to month end (e.g. Nov 30 + 3 months => Feb 28/29).
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return min(date(year, month, 1) + timedelta(days=d.day - 1), next_month - timedelta(days=1))


def _elapsed_calendar_months(start: date, end: date) -> float:
    """Calendar-month duration; same-day monthly snapshots count as exactly 1."""
    if end <= start:
        return 0.0
    whole = (end.year - start.year) * 12 + end.month - start.month
    while whole > 0 and _add_months(start, whole) > end:
        whole -= 1
    anchor = _add_months(start, whole)
    if anchor == end:
        return float(whole)
    next_anchor = _add_months(start, whole + 1)
    span_days = (next_anchor - anchor).days
    return whole + (end - anchor).days / span_days


def _fmt(value):
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def write_atomic(path: Path, rows: Iterable[dict[str, str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_existing_monthly(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows, fields = _read_rows(path)
    missing = set(OUTPUT_FIELDS) - set(fields)
    if missing:
        raise DataError(f"Existing monthly output has an invalid schema: {', '.join(sorted(missing))}")
    keys = [row["snapshot_month"] for row in rows]
    if len(keys) != len(set(keys)):
        raise DataError("Existing monthly output has duplicate snapshot_month keys")
    return [{field: row[field] for field in OUTPUT_FIELDS} for row in rows]


def merge_monthly(new_rows: list[dict[str, str]], existing_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Upsert by month, keep untouched months, and never downgrade realized returns."""
    merged = {row["snapshot_month"]: dict(row) for row in existing_rows}
    for fresh in new_rows:
        key = fresh["snapshot_month"]
        old = merged.get(key)
        candidate = dict(fresh)
        if old and old["snapshot_date"] == fresh["snapshot_date"] and old["health_score"] == fresh["health_score"]:
            if old["return_status"] == "REALIZED" and fresh["return_status"] == "PENDING":
                for field in ("sp500_start_date", "sp500_start_close", "sp500_forward_end_date",
                              "sp500_forward_end_close", "sp500_forward_3m_return_pct", "return_status"):
                    candidate[field] = old[field]
            if all(candidate[field] == old[field] for field in OUTPUT_FIELDS if field != "run_timestamp_utc"):
                candidate = old
        merged[key] = candidate
    return [merged[key] for key in sorted(merged)]


def refresh_existing_returns(existing_rows: list[dict[str, str]], prices,
                             as_of: date) -> list[dict[str, str]]:
    """Recheck matured S&P 500 outcomes without changing archived score snapshots."""
    refreshed = []
    for old in existing_rows:
        row = dict(old)
        if prices and row.get("return_status") != "REALIZED":
            snap = date.fromisoformat(row["snapshot_date"])
            start_date, start_close = _price_at_or_before(prices, snap)
            target = _add_months(snap, 3)
            end_date, end_close = _price_at_or_after(prices, target)
            matured = target <= as_of and end_date is not None and end_date <= as_of
            if matured and start_close:
                row.update({
                    "sp500_start_date": start_date.isoformat(),
                    "sp500_start_close": _fmt(start_close),
                    "sp500_forward_end_date": end_date.isoformat(),
                    "sp500_forward_end_close": _fmt(end_close),
                    "sp500_forward_3m_return_pct": _fmt((end_close / start_close - 1) * 100),
                    "return_status": "REALIZED",
                })
        refreshed.append(row)
    return refreshed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", required=True, type=Path, help="verified daily archive CSV")
    p.add_argument("--sp500", type=Path, help="licensed S&P 500 daily close CSV; omit until a publishable source is configured")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cutoff-day", required=True, type=int,
                   help="explicit monthly observation cutoff (no default; schedule is unconfirmed)")
    p.add_argument("--retry-month", help="YYYY-MM; on a delayed retry, allow the actual successful daily row through --as-of for this month")
    p.add_argument("--as-of", required=True, type=date.fromisoformat,
                   help="data availability date used to mark forward returns matured")
    p.add_argument("--run-timestamp-utc", required=True,
                   help="actual execution timestamp in ISO-8601 UTC")
    args = p.parse_args(argv)
    try:
        # Validate timestamp, including timezone marker.
        ts = datetime.fromisoformat(args.run_timestamp_utc.replace("Z", "+00:00"))
        if ts.tzinfo is None or ts.utcoffset().total_seconds() != 0:
            raise DataError("run timestamp must be timezone-aware UTC (Z or +00:00)")
        daily = read_daily(args.daily)
        prices = read_prices(args.sp500) if args.sp500 else []
        if args.retry_month and (len(args.retry_month) != 7 or args.retry_month[4] != "-" or
                                 not args.retry_month[:4].isdigit() or not args.retry_month[5:].isdigit() or
                                 not 1 <= int(args.retry_month[5:]) <= 12):
            raise DataError("retry_month must have YYYY-MM format")
        existing_rows = read_existing_monthly(args.output)
        rows = build_monthly(daily, prices, args.cutoff_day, args.as_of,
                             args.run_timestamp_utc, args.retry_month)
        rows.extend(refresh_existing_returns(existing_rows, prices, args.as_of))
        if not rows:
            raise DataError("No eligible daily Macro Safety observations for the selected cutoff")
        rows = merge_monthly(rows, existing_rows)
        write_atomic(args.output, rows)
    except (DataError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps({"output": str(args.output), "monthly_rows": len(rows),
                      "realized_returns": sum(r["return_status"] == "REALIZED" for r in rows),
                      "pending_returns": sum(r["return_status"] == "PENDING" for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
