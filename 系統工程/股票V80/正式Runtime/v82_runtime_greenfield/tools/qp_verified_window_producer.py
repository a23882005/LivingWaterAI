from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass, asdict
from decimal import Decimal, getcontext, ROUND_HALF_EVEN
from math import log, sqrt
from pathlib import Path
from typing import Any

getcontext().prec = 50
getcontext().rounding = ROUND_HALF_EVEN

OK = "OK"
UNKNOWN = "UNKNOWN"


def D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


@dataclass(frozen=True)
class Result:
    status: str
    value: Any = None
    reason: str = ""
    evidence: Any = None


@dataclass(frozen=True)
class Row:
    date: str
    cached_close: Decimal
    cached_dividend: Decimal
    split_ratio: Decimal
    raw_close: Decimal
    raw_dividend_old_share: Decimal


def midrank(x: float, refs: list[float]) -> Decimal:
    if not refs or len(set(refs)) <= 1:
        raise ValueError("INSUFFICIENT_OR_CONSTANT_REFERENCE")
    less = sum(v < x for v in refs)
    equal = sum(v == x for v in refs)
    return D("100") * (D(less) + D("0.5") * D(equal)) / D(len(refs))


def sample_stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        raise ValueError("INSUFFICIENT_SIGMA_WINDOW")
    mu = sum(xs) / len(xs)
    return sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv_bytes(path: Path) -> tuple[bytes, list[dict[str, str]]]:
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    return data, list(csv.DictReader(io.StringIO(text)))


def reconstruct_raw_rows(csv_path: str | Path, spec: dict[str, Any]) -> Result:
    path = Path(csv_path)
    if not path.is_file():
        return Result(UNKNOWN, reason="SOURCE_CSV_NOT_FOUND")
    raw_bytes, records = _read_csv_bytes(path)
    actual_sha = git_blob_sha(raw_bytes)
    expected_sha = spec.get("source_blob_sha")
    if expected_sha and actual_sha != expected_sha:
        return Result(UNKNOWN, reason="SOURCE_BLOB_SHA_MISMATCH",
                      evidence={"expected": expected_sha, "actual": actual_sha})
    gate_reasons = {
        "bar_date_alignment_verified": "BAR_DATE_ALIGNMENT_NOT_VERIFIED",
        "event_coverage_verified": "EVENT_COVERAGE_NOT_VERIFIED",
        "calendar_verified": "CALENDAR_NOT_VERIFIED",
        "timestamp_evidence_verified": "TIMESTAMP_EVIDENCE_NOT_VERIFIED",
    }
    for gate, reason in gate_reasons.items():
        if spec.get(gate) is not True:
            return Result(UNKNOWN, reason=reason)

    start = spec["verified_window_start"]
    end = spec["verified_window_end"]
    filtered: list[dict[str, str]] = []
    for r in records:
        dt = r.get("Date", "")
        if start <= dt <= end:
            filtered.append(r)
    if not filtered:
        return Result(UNKNOWN, reason="NO_ROWS_IN_VERIFIED_WINDOW")
    expected_rows = spec.get("expected_row_count")
    if expected_rows is not None and len(filtered) != int(expected_rows):
        return Result(UNKNOWN, reason="ROW_COUNT_MISMATCH",
                      evidence={"expected": int(expected_rows), "actual": len(filtered)})
    dates = [r["Date"] for r in filtered]
    if dates != sorted(set(dates)):
        return Result(UNKNOWN, reason="DUPLICATE_OR_NONMONOTONIC_SESSIONS")
    if dates[0] != start or dates[-1] != end:
        return Result(UNKNOWN, reason="VERIFIED_WINDOW_BOUNDARY_MISMATCH",
                      evidence={"first": dates[0], "last": dates[-1], "expected_first": start, "expected_last": end})

    parsed: list[dict[str, Any]] = []
    for r in filtered:
        try:
            close = D(r["Close"])
            div = D(r.get("Dividends") or "0")
            split = D(r.get("Stock Splits") or "0")
        except Exception as exc:
            return Result(UNKNOWN, reason="CSV_NUMERIC_PARSE_ERROR", evidence={"date": r.get("Date"), "error": str(exc)})
        if close <= 0 or div < 0 or split < 0:
            return Result(UNKNOWN, reason="INVALID_PRICE_OR_ACTION_VALUE", evidence={"date": r["Date"]})
        parsed.append({"date": r["Date"], "close": close, "div": div, "split": split})

    # yfinance auto_adjust=False still back-adjusts historical Close and Dividends for
    # future splits. Rebuild old-share/raw price basis by multiplying each row by all
    # split ratios strictly after that row. The split date itself remains post-split.
    future_factor = D("1")
    rebuilt_rev: list[Row] = []
    for r in reversed(parsed):
        raw_close = r["close"] * future_factor
        raw_div = r["div"] * future_factor
        split_ratio = r["split"] if r["split"] not in (D("0"), D("1")) else D("1")
        if r["div"] != 0 and split_ratio != 1:
            return Result(UNKNOWN, reason="SAME_DAY_SPLIT_AND_CASH_RIGHTS_ORDER_UNKNOWN",
                          evidence={"date": r["date"]})
        rebuilt_rev.append(Row(r["date"], r["close"], r["div"], split_ratio, raw_close, raw_div))
        if split_ratio != 1:
            future_factor *= split_ratio
    rebuilt = list(reversed(rebuilt_rev))
    event_count = sum(1 for r in rebuilt if r.cached_dividend != 0 or r.split_ratio != 1)
    expected_event_count = spec.get("event_count_verified")
    if expected_event_count is not None and event_count != int(expected_event_count):
        return Result(UNKNOWN, reason="EVENT_COUNT_MISMATCH",
                      evidence={"expected": int(expected_event_count), "actual": event_count})
    max_err = D(spec.get("max_event_value_relative_error", 0))
    tolerance = D(spec.get("event_value_relative_error_tolerance", "0.005"))
    if max_err > tolerance:
        return Result(UNKNOWN, reason="EVENT_VALUE_VERIFICATION_TOLERANCE_EXCEEDED",
                      evidence={"max_relative_error": str(max_err), "tolerance": str(tolerance)})

    return Result(OK, rebuilt, evidence={
        "rows": len(rebuilt),
        "first_date": rebuilt[0].date,
        "last_date": rebuilt[-1].date,
        "source_blob_sha": actual_sha,
        "event_count_verified": spec.get("event_count_verified"),
        "max_event_value_relative_error": spec.get("max_event_value_relative_error"),
        "verification_source": spec.get("verification_source"),
    })


def reconstruct_ib_snapshot(snapshot_path: str | Path, spec: dict[str, Any]) -> Result:
    path = Path(snapshot_path)
    if not path.is_file():
        return Result(UNKNOWN, reason="SOURCE_SNAPSHOT_NOT_FOUND")
    raw_bytes = path.read_bytes()
    actual_sha = git_blob_sha(raw_bytes)
    expected_sha = spec.get("source_blob_sha")
    if expected_sha and actual_sha != expected_sha:
        return Result(UNKNOWN, reason="SOURCE_BLOB_SHA_MISMATCH",
                      evidence={"expected": expected_sha, "actual": actual_sha})
    gate_reasons = {
        "bar_date_alignment_verified": "BAR_DATE_ALIGNMENT_NOT_VERIFIED",
        "event_coverage_verified": "EVENT_COVERAGE_NOT_VERIFIED",
        "calendar_verified": "CALENDAR_NOT_VERIFIED",
        "timestamp_evidence_verified": "TIMESTAMP_EVIDENCE_NOT_VERIFIED",
    }
    for gate, reason in gate_reasons.items():
        if spec.get(gate) is not True:
            return Result(UNKNOWN, reason=reason)
    try:
        obj = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        return Result(UNKNOWN, reason="SNAPSHOT_JSON_PARSE_ERROR", evidence={"error": str(exc)})
    if obj.get("contract") != "V82_QP_IB_SNAPSHOT_v1":
        return Result(UNKNOWN, reason="IB_SNAPSHOT_CONTRACT_MISMATCH")
    if obj.get("price_basis") != "SPLIT_BACK_ADJUSTED_CLOSE":
        return Result(UNKNOWN, reason="IB_PRICE_BASIS_UNVERIFIED")
    if obj.get("cash_dividend_basis") != "OLD_SHARE_GROSS":
        return Result(UNKNOWN, reason="IB_CASH_BASIS_UNVERIFIED")
    times = obj.get("time") or []
    closes = obj.get("close") or []
    if len(times) != len(closes) or not times:
        return Result(UNKNOWN, reason="IB_BAR_ARRAY_LENGTH_MISMATCH")
    events_by_date: dict[str, dict[str, Decimal]] = {}
    for e in obj.get("corp_actions") or []:
        dt = str(e.get("date") or "")
        if len(dt) == 8 and dt.isdigit():
            dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        slot = events_by_date.setdefault(dt, {"div": D("0"), "split": D("1")})
        typ = e.get("type")
        try:
            val = D(e.get("value"))
        except Exception as exc:
            return Result(UNKNOWN, reason="IB_EVENT_NUMERIC_PARSE_ERROR", evidence={"date": dt, "error": str(exc)})
        if typ == "CashDividends":
            if val < 0:
                return Result(UNKNOWN, reason="INVALID_CASH_DIVIDEND", evidence={"date": dt})
            slot["div"] += val
        elif typ == "Splits":
            if val <= 0:
                return Result(UNKNOWN, reason="INVALID_SPLIT_RATIO", evidence={"date": dt})
            slot["split"] *= val
        else:
            return Result(UNKNOWN, reason="UNSUPPORTED_CORPORATE_ACTION", evidence={"date": dt, "type": typ})

    start = spec["verified_window_start"]
    end = spec["verified_window_end"]
    parsed: list[dict[str, Any]] = []
    for t, c in zip(times, closes):
        dt = str(t)[:10]
        if not (start <= dt <= end):
            continue
        try:
            close = D(c)
        except Exception as exc:
            return Result(UNKNOWN, reason="IB_CLOSE_NUMERIC_PARSE_ERROR", evidence={"date": dt, "error": str(exc)})
        if close <= 0:
            return Result(UNKNOWN, reason="INVALID_PRICE_VALUE", evidence={"date": dt})
        event = events_by_date.get(dt, {"div": D("0"), "split": D("1")})
        if event["div"] != 0 and event["split"] != 1:
            return Result(UNKNOWN, reason="SAME_DAY_SPLIT_AND_CASH_RIGHTS_ORDER_UNKNOWN", evidence={"date": dt})
        parsed.append({"date": dt, "close": close, "div": event["div"], "split": event["split"]})
    if not parsed:
        return Result(UNKNOWN, reason="NO_ROWS_IN_VERIFIED_WINDOW")
    expected_rows = spec.get("expected_row_count")
    if expected_rows is not None and len(parsed) != int(expected_rows):
        return Result(UNKNOWN, reason="ROW_COUNT_MISMATCH",
                      evidence={"expected": int(expected_rows), "actual": len(parsed)})
    dates = [r["date"] for r in parsed]
    if dates != sorted(set(dates)):
        return Result(UNKNOWN, reason="DUPLICATE_OR_NONMONOTONIC_SESSIONS")
    if dates[0] != start or dates[-1] != end:
        return Result(UNKNOWN, reason="VERIFIED_WINDOW_BOUNDARY_MISMATCH",
                      evidence={"first": dates[0], "last": dates[-1], "expected_first": start, "expected_last": end})
    bar_dates = set(dates)
    orphan_events = sorted(d for d in events_by_date if start <= d <= end and d not in bar_dates)
    if orphan_events:
        return Result(UNKNOWN, reason="CORPORATE_ACTION_WITHOUT_BAR", evidence={"dates": orphan_events})

    # IB chart Close is split-back-adjusted, while the corporate-action cash values
    # observed in this contract are old-share gross cash. Rebuild only the price basis;
    # do not multiply the cash dividend by future splits a second time.
    future_factor = D("1")
    rebuilt_rev: list[Row] = []
    for r in reversed(parsed):
        raw_close = r["close"] * future_factor
        raw_div = r["div"]
        rebuilt_rev.append(Row(r["date"], r["close"], r["div"], r["split"], raw_close, raw_div))
        if r["split"] != 1:
            future_factor *= r["split"]
    rebuilt = list(reversed(rebuilt_rev))
    event_count = sum(1 for r in rebuilt if r.cached_dividend != 0 or r.split_ratio != 1)
    expected_event_count = spec.get("event_count_verified")
    if expected_event_count is not None and event_count != int(expected_event_count):
        return Result(UNKNOWN, reason="EVENT_COUNT_MISMATCH",
                      evidence={"expected": int(expected_event_count), "actual": event_count})
    max_err = D(spec.get("max_event_value_relative_error", 0))
    tolerance = D(spec.get("event_value_relative_error_tolerance", "0.005"))
    if max_err > tolerance:
        return Result(UNKNOWN, reason="EVENT_VALUE_VERIFICATION_TOLERANCE_EXCEEDED",
                      evidence={"max_relative_error": str(max_err), "tolerance": str(tolerance)})
    return Result(OK, rebuilt, evidence={
        "rows": len(rebuilt),
        "first_date": rebuilt[0].date,
        "last_date": rebuilt[-1].date,
        "source_blob_sha": actual_sha,
        "event_count_verified": spec.get("event_count_verified"),
        "max_event_value_relative_error": spec.get("max_event_value_relative_error"),
        "verification_source": spec.get("verification_source"),
        "source_type": "IB_SNAPSHOT_JSON",
    })


def build_wealth(rows: list[Row]) -> Result:
    if len(rows) < 2:
        return Result(UNKNOWN, reason="INSUFFICIENT_DAILY_CLOSES")
    wealth = [D("100")]
    log_returns: list[float | None] = [None]
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        cur = rows[i]
        if prev.raw_close <= 0 or cur.raw_close <= 0:
            return Result(UNKNOWN, reason="NONPOSITIVE_RAW_CLOSE", evidence={"date": cur.date})
        gross = (cur.split_ratio * cur.raw_close + cur.raw_dividend_old_share) / prev.raw_close
        if gross <= 0:
            return Result(UNKNOWN, reason="NONPOSITIVE_GROSS_RETURN", evidence={"date": cur.date})
        wealth.append(wealth[-1] * gross)
        log_returns.append(log(float(gross)))
    return Result(OK, {"wealth": wealth, "log_returns": log_returns})


def _z_at(index: int, rows: list[Row], wealth: list[Decimal], log_returns: list[float | None]) -> dict[str, Any] | None:
    if index < 314:
        return None
    high_idx = index - 251
    for j in range(index - 250, index + 1):
        if wealth[j] >= wealth[high_idx]:
            high_idx = j
    if high_idx < 63:
        return None
    lr = log_returns[high_idx - 62: high_idx + 1]
    if len(lr) != 63 or any(x is None for x in lr):
        return None
    sigma = sample_stdev([float(x) for x in lr])
    if sigma <= 0:
        return None
    high = float(wealth[high_idx])
    current = float(wealth[index])
    drawdown_log = max(0.0, log(high / current))
    z = drawdown_log / (sigma * sqrt(252))
    return {
        "Z": z,
        "D_log": drawdown_log,
        "peak_index": high_idx,
        "peak_date": rows[high_idx].date,
        "peak_wealth": str(wealth[high_idx]),
        "sigma_h": sigma,
    }


def calculate_qp(rows: list[Row], wealth_result: Result) -> Result:
    if wealth_result.status != OK:
        return wealth_result
    if len(rows) < 315:
        return Result(UNKNOWN, reason="INSUFFICIENT_DAILY_HISTORY_FOR_QP", evidence={"rows": len(rows)})
    wealth = wealth_result.value["wealth"]
    log_returns = wealth_result.value["log_returns"]
    month_last: dict[str, int] = {}
    for i, r in enumerate(rows):
        month_last[r.date[:7]] = i
    current_month = rows[-1].date[:7]
    refs: list[dict[str, Any]] = []
    for month, idx in sorted(month_last.items()):
        if month >= current_month:
            continue
        z = _z_at(idx, rows, wealth, log_returns)
        if z is not None:
            refs.append({"period": month, **z})
    if not refs:
        return Result(UNKNOWN, reason="NO_QP_MONTHLY_REFERENCE")
    serials = [int(r["period"][:4]) * 12 + int(r["period"][5:7]) - 1 for r in refs]
    expected = serials[-1] - serials[0] + 1
    coverage = D(len(refs)) / D(expected)
    max_gap = max((b - a - 1 for a, b in zip(serials, serials[1:])), default=0)
    span_years = D(serials[-1] - serials[0]) / D("12")
    if span_years < D("2"):
        return Result(UNKNOWN, reason="HISTORY_SPAN_UNDER_TWO_YEARS")
    if coverage < D("0.9"):
        return Result(UNKNOWN, reason="HISTORY_COVERAGE_BELOW_90_PERCENT")
    if max_gap > 2:
        return Result(UNKNOWN, reason="CONSECUTIVE_MISSING_PERIODS_OVER_TWO")
    current = _z_at(len(rows) - 1, rows, wealth, log_returns)
    if current is None:
        return Result(UNKNOWN, reason="CURRENT_Z_UNCALCULABLE")
    q_p = midrank(current["Z"], [r["Z"] for r in refs])
    return Result(OK, {
        "qP": str(q_p),
        "current_Z": current["Z"],
        "current_D_log": current["D_log"],
        "H_252": current["peak_wealth"],
        "peak_date": current["peak_date"],
        "sigma_h": current["sigma_h"],
        "reference_points": len(refs),
        "reference_first_period": refs[0]["period"],
        "reference_last_period": refs[-1]["period"],
        "reference_span_years": str(span_years),
        "reference_coverage": str(coverage),
        "max_consecutive_missing_periods": max_gap,
    })


def produce_one(repo_root: str | Path, spec: dict[str, Any]) -> Result:
    source = Path(repo_root) / spec["source_path"]
    source_type = spec.get("source_type", "YFINANCE_CSV")
    if source_type == "YFINANCE_CSV":
        raw = reconstruct_raw_rows(source, spec)
    elif source_type == "IB_SNAPSHOT_JSON":
        raw = reconstruct_ib_snapshot(source, spec)
    else:
        return Result(UNKNOWN, reason="UNSUPPORTED_SOURCE_TYPE", evidence={"source_type": source_type})
    if raw.status != OK:
        return raw
    wealth = build_wealth(raw.value)
    qp = calculate_qp(raw.value, wealth)
    if qp.status != OK:
        return qp
    expected = spec.get("expected_qp")
    if expected is not None:
        if abs(D(qp.value["qP"]) - D(expected)) > D(spec.get("expected_qp_tolerance", "0.000001")):
            return Result(UNKNOWN, reason="EXPECTED_QP_REGRESSION_MISMATCH",
                          evidence={"expected": expected, "actual": qp.value["qP"]})
    return Result(OK, qp.value, evidence=raw.evidence)


def produce_manifest(repo_root: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    out = {
        "contract": "V82_QP_VERIFIED_WINDOW_PRODUCER_v1",
        "rule_version": manifest["rule_version"],
        "source_main_commit": manifest["source_main_commit"],
        "generated_from_manifest": str(manifest_path),
        "items": {},
    }
    for symbol, spec in manifest["items"].items():
        r = produce_one(repo_root, spec)
        out["items"][symbol] = asdict(r)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--output")
    args = p.parse_args()
    out = produce_manifest(args.repo_root, args.manifest)
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if all(x["status"] == OK for x in out["items"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
