#!/usr/bin/env python3
# 最後修改日期時間（台灣時間）：2026/10/19 10:03｜檔案名稱：build_bank_macro_monthly.py｜版本：五機構與Macro月度合併
"""Join monthly Macro Safety snapshots to each institution's latest known S&P 500 target.

The output is a research series. Bank source records retain their verification
status; missing values are written as the literal NA. No forecasts are
interpolated and no Macro Safety score is calculated here.
"""
from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import date
from pathlib import Path

INSTITUTIONS = ("高盛", "摩根大通", "摩根士丹利", "美國銀行", "瑞銀")
BANK_REQUIRED = {
    "forecast_id", "institution", "forecast_target_index", "forecast_value",
    "forecast_target_date", "evidence_date", "publication_date",
    "forecast_horizon_days", "source_url", "verification_status",
}
MONTHLY_REQUIRED = {
    "snapshot_month", "snapshot_date", "health_score", "score_status",
    "previous_snapshot_date", "previous_health_score", "slope_points_per_month",
    "sp500_forward_3m_return_pct", "return_status",
}
FIELDS = [
    "snapshot_month", "snapshot_date", "institution", "forecast_id",
    "forecast_target_index", "forecast_target_date", "forecast_value",
    "forecast_evidence_date", "forecast_publication_date",
    "forecast_horizon_days", "forecast_status", "source_url",
    "macro_health_score", "macro_score_status", "previous_macro_snapshot_date",
    "previous_macro_health_score", "macro_slope_points_per_month",
    "macro_sp500_forward_3m_return_pct", "macro_return_status",
]


class DataError(ValueError):
    pass


def read_csv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise DataError(f"{path}: missing CSV header")
        return list(reader), set(reader.fieldnames)


def _need(fields: set[str], required: set[str], path: Path):
    missing = required - fields
    if missing:
        raise DataError(f"{path}: missing columns: {', '.join(sorted(missing))}")


def _na(value):
    if value is None or str(value).strip() == "":
        return "NA"
    return str(value).strip()


def build_rows(bank_rows: list[dict[str, str]], monthly_rows: list[dict[str, str]]):
    banks: dict[str, list[dict[str, str]]] = {name: [] for name in INSTITUTIONS}
    for row in bank_rows:
        institution = row.get("institution", "").strip()
        if institution not in banks:
            raise DataError(f"Unknown institution in bank register: {institution!r}")
        try:
            date.fromisoformat(row["evidence_date"])
            date.fromisoformat(row["forecast_target_date"])
            target = float(row["forecast_value"])
        except (ValueError, TypeError) as exc:
            raise DataError(f"Invalid forecast record: {row}") from exc
        if target <= 0:
            raise DataError(f"Forecast target must be positive: {row}")
        banks[institution].append(row)

    output = []
    seen_months = set()
    for month in sorted(monthly_rows, key=lambda r: r["snapshot_month"]):
        snapshot_month = month["snapshot_month"].strip()
        snapshot_date = date.fromisoformat(month["snapshot_date"])
        if snapshot_date.strftime("%Y-%m") != snapshot_month:
            raise DataError(f"snapshot_month/date mismatch: {snapshot_month}, {snapshot_date}")
        if snapshot_month in seen_months:
            raise DataError(f"Duplicate Macro Safety monthly snapshot: {snapshot_month}")
        seen_months.add(snapshot_month)
        if month.get("score_status", "").upper() not in {"VALID", "FORMAL_VALID"}:
            continue

        for institution in INSTITUTIONS:
            available = [r for r in banks[institution]
                         if date.fromisoformat(r["evidence_date"]) <= snapshot_date
                         and date.fromisoformat(r["forecast_target_date"]) > snapshot_date]
            forecast = max(available,
                           key=lambda r: (r["evidence_date"], r["forecast_target_date"], r["forecast_id"])) \
                if available else {}
            output.append({
                "snapshot_month": snapshot_month,
                "snapshot_date": snapshot_date.isoformat(),
                "institution": institution,
                "forecast_id": _na(forecast.get("forecast_id")),
                "forecast_target_index": _na(forecast.get("forecast_target_index")),
                "forecast_target_date": _na(forecast.get("forecast_target_date")),
                "forecast_value": _na(forecast.get("forecast_value")),
                "forecast_evidence_date": _na(forecast.get("evidence_date")),
                "forecast_publication_date": _na(forecast.get("publication_date")),
                "forecast_horizon_days": _na(forecast.get("forecast_horizon_days")),
                "forecast_status": _na(forecast.get("verification_status")),
                "source_url": _na(forecast.get("source_url")),
                "macro_health_score": _na(month.get("health_score")),
                "macro_score_status": _na(month.get("score_status")),
                "previous_macro_snapshot_date": _na(month.get("previous_snapshot_date")),
                "previous_macro_health_score": _na(month.get("previous_health_score")),
                "macro_slope_points_per_month": _na(month.get("slope_points_per_month")),
                "macro_sp500_forward_3m_return_pct": _na(month.get("sp500_forward_3m_return_pct")),
                "macro_return_status": _na(month.get("return_status")),
            })
    return output


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-register", required=True, type=Path)
    parser.add_argument("--macro-monthly", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        bank_rows, bank_fields = read_csv(args.bank_register)
        monthly_rows, monthly_fields = read_csv(args.macro_monthly)
        _need(bank_fields, BANK_REQUIRED, args.bank_register)
        _need(monthly_fields, MONTHLY_REQUIRED, args.macro_monthly)
        rows = build_rows(bank_rows, monthly_rows)
        if not rows:
            raise DataError("No valid monthly Macro Safety snapshots to join")
        write_csv(args.output, rows)
    except (DataError, OSError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(rows)} institution-month rows to {args.output}")


if __name__ == "__main__":
    main()
