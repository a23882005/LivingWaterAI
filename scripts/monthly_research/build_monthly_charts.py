#!/usr/bin/env python3
"""Render exactly seven monthly V70 research charts when licensed data is mature."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path

INSTITUTIONS = {
    "高盛": ("goldman.png", "#c0392b", "Goldman Sachs"),
    "摩根大通": ("jpm.png", "#2874a6", "JPMorgan"),
    "摩根士丹利": ("morgan_stanley.png", "#7d3c98", "Morgan Stanley"),
    "美國銀行": ("bofa.png", "#d68910", "Bank of America"),
    "瑞銀": ("ubs.png", "#148f77", "UBS"),
}
LICENSE_SCHEMA = "V70.3/SP500-public-display-license-v1"
CHARTS = tuple(item[0] for item in INSTITUTIONS.values()) + (
    "macro_slope_candidate.png", "overview_7lines.png"
)
PNG = b"\x89PNG\r\n\x1a\n"


def _number(value):
    if value is None or str(value).strip().upper() in {"", "NA", "N/A", "NONE"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        return list(reader)


def _licensed(manifest_path, today):
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except OSError:
        return False, "display-license manifest missing", None
    if manifest.get("schema") != LICENSE_SCHEMA or manifest.get("status") != "AUTHORIZED":
        return False, "no verified public-display authorization", None
    if manifest.get("benchmark") != "S&P 500":
        return False, "license is not for the S&P 500 index", None
    for key in ("source_url", "license_evidence_url", "license_id"):
        if not str(manifest.get(key, "")).startswith("https://") and key != "license_id":
            return False, f"missing {key}", None
        if key == "license_id" and not str(manifest.get(key, "")).strip():
            return False, f"missing {key}", None
    allowed = manifest.get("allowed_uses", [])
    required = {"historical_index_values", "derived_forward_3m_returns", "public_static_charts"}
    if not isinstance(allowed, list) or not required.issubset(set(allowed)):
        return False, "license does not authorize all chart uses", None
    expires = manifest.get("valid_through")
    if expires:
        try:
            if date.fromisoformat(expires) < today:
                return False, "display license expired", None
        except ValueError:
            return False, "invalid license expiry date", None
    return True, "", manifest


def _clear(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in CHARTS:
        (output_dir / name).unlink(missing_ok=True)


def _status(output_dir, status, reason="", **details):
    payload = {
        "schema": "V70.3/monthly-research-chart-status-v1",
        "status": status,
        "reason": reason,
        "charts": list(CHARTS) if status == "READY" else [],
        **details,
    }
    (output_dir / "monthly_chart_status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def build(monthly_csv, output_dir, license_manifest, today=None):
    output_dir = Path(output_dir)
    _clear(output_dir)
    today = today or date.today()
    ok, reason, license_info = _licensed(license_manifest, today)
    if not ok:
        return _status(output_dir, "BLOCKED", reason)

    rows = _read_csv(monthly_csv)
    by_month = {}
    for row in rows:
        institution = row.get("institution", "").strip()
        month = row.get("snapshot_month", "").strip()
        if institution not in INSTITUTIONS:
            raise ValueError(f"Unexpected institution in monthly research CSV: {institution!r}")
        if not month or month in by_month.setdefault(institution, {}):
            raise ValueError(f"Missing or duplicate month for {institution}: {month}")
        date.fromisoformat(row["snapshot_date"])
        by_month[institution][month] = row

    if set(by_month) != set(INSTITUTIONS) or any(not by_month[k] for k in INSTITUTIONS):
        return _status(output_dir, "BLOCKED", "CSV must contain the five institutions only")

    months = sorted(set.intersection(*(set(by_month[k]) for k in INSTITUTIONS)))
    common = []
    for month in months:
        firm_rows = {name: by_month[name][month] for name in INSTITUTIONS}
        base = next(iter(firm_rows.values()))
        if any(row["snapshot_date"] != base["snapshot_date"] for row in firm_rows.values()):
            continue
        if any(row.get("macro_score_status") not in {"VALID", "FORMAL_VALID"} for row in firm_rows.values()):
            continue
        slope = _number(base.get("macro_slope_points_per_month"))
        realized = _number(base.get("macro_sp500_forward_3m_return_pct"))
        if (slope is None or realized is None or base.get("macro_return_status") != "REALIZED"
                or any(row.get("macro_return_status") != "REALIZED"
                       or _number(row.get("macro_sp500_forward_3m_return_pct")) != realized
                       for row in firm_rows.values())):
            continue
        if any(_number(firm_rows[name].get("forecast_implied_return_pct")) is None
               for name in INSTITUTIONS):
            continue
        common.append((month, base, firm_rows, slope, realized))

    if len(common) < 3:
        return _status(output_dir, "BLOCKED",
                       "need at least three common monthly observations with real slopes, five bank forecasts, and realized licensed returns",
                       eligible_months=len(common))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to render the seven monthly PNGs") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    dates = [date.fromisoformat(item[1]["snapshot_date"]) for item in common]
    realized = [item[4] for item in common]
    for institution, (filename, color, english_name) in INSTITUTIONS.items():
        forecast = [_number(item[2][institution]["forecast_implied_return_pct"]) for item in common]
        fig, ax = plt.subplots(figsize=(11, 6))
        ax.plot(dates, forecast, marker="o", color=color, linewidth=2.4, label="Institution forecast implied return")
        ax.plot(dates, realized, marker="s", color="#202020", linewidth=2.2, label="S&P 500 realized forward 3M return")
        ax.axhline(0, color="#777777", linewidth=.8)
        ax.set_title(f"{english_name} | monthly snapshot comparison (n={len(common)})")
        ax.set_ylabel("Return (%)")
        ax.grid(True, alpha=.25)
        ax.legend(loc="best")
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(output_dir / filename, dpi=160)
        plt.close(fig)

    fig, left = plt.subplots(figsize=(11, 6))
    right = left.twinx()
    left.plot(dates, [item[4] for item in common], marker="s", color="#202020",
              linewidth=2.5, label="S&P 500 realized forward 3M return (%)")
    right.plot(dates, [item[3] for item in common], marker="o", color="#00a6a6",
               linewidth=2.5, label="Macro Safety slope (score points/month)")
    left.set_title(f"Macro Safety monthly slope vs S&P 500 realized forward 3M return (n={len(common)})")
    left.set_ylabel("S&P 500 return (%)")
    right.set_ylabel("Macro score points per calendar month")
    left.grid(True, alpha=.25)
    handles1, labels1 = left.get_legend_handles_labels()
    handles2, labels2 = right.get_legend_handles_labels()
    left.legend(handles1 + handles2, labels1 + labels2, loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_dir / "macro_slope_candidate.png", dpi=160)
    plt.close(fig)

    fig, left = plt.subplots(figsize=(13, 7))
    right = left.twinx()
    for institution, (filename, color) in INSTITUTIONS.items():
        values = [_number(item[2][institution]["forecast_implied_return_pct"]) for item in common]
        left.plot(dates, values, marker="o", linewidth=1.8, color=color, label=f"{english_name} forecast")
    left.plot(dates, realized, marker="s", linewidth=2.7, color="#202020",
              label="S&P 500 realized forward 3M return")
    right.plot(dates, [item[3] for item in common], marker="D", linewidth=2,
               color="#00a6a6", label="Macro slope (score points/month)")
    left.axhline(0, color="#777777", linewidth=.8)
    left.set_title(f"Five institutions + Macro Safety + S&P 500 | monthly overview (n={len(common)})")
    left.set_ylabel("Return (%)")
    right.set_ylabel("Macro score points per calendar month")
    left.grid(True, alpha=.25)
    h1, l1 = left.get_legend_handles_labels()
    h2, l2 = right.get_legend_handles_labels()
    left.legend(h1 + h2, l1 + l2, loc="best", ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_dir / "overview_7lines.png", dpi=160)
    plt.close(fig)

    invalid = [name for name in CHARTS
               if not (output_dir / name).is_file()
               or (output_dir / name).read_bytes()[:8] != PNG]
    if invalid:
        _clear(output_dir)
        return _status(output_dir, "BLOCKED", "PNG verification failed: " + ", ".join(invalid))
    return _status(
        output_dir, "READY", "",
        eligible_months=len(common),
        first_month=common[0][0],
        last_month=common[-1][0],
        benchmark_source_url=license_info["source_url"],
        license_id=license_info["license_id"],
        license_evidence_url=license_info["license_evidence_url"],
        license_valid_through=license_info.get("valid_through"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-monthly", required=True, type=Path)
    parser.add_argument("--license-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    status = build(args.bank_monthly, args.output_dir, args.license_manifest)
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
