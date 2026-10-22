"""WORK12-11 deterministic Risk calculations under W12.1-FREEZE-v1.2.0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite, sqrt
from statistics import mean, stdev
from typing import Iterable, Sequence


class ContractViolation(ValueError):
    """Input is outside the frozen contract or cannot be calculated safely."""


@dataclass(frozen=True)
class Result:
    status: str
    value: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RecoveryResult:
    status: str
    mdd: float | None = None
    peak_date: date | None = None
    peak_value: float | None = None
    trough_date: date | None = None
    trough_value: float | None = None
    recovery_date: date | None = None
    recovery_time_calendar_days: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RiskFreeObservation:
    observed_on: date
    annual_quoted_percent: float
    currency: str
    source: str


RF_SOURCES = {
    "USD": "Federal Reserve H.15 / FRED DGS3MO",
    "TWD": "Central Bank of the Republic of China (Taiwan) 91-day Central Bank Certificate issuance rate",
}


def _finite(values: Iterable[float], name: str) -> list[float]:
    out = [float(x) for x in values]
    if not out or not all(isfinite(x) for x in out):
        raise ContractViolation(f"{name} must contain finite observations")
    return out


def max_drawdown_daily_wealth(wealth: Sequence[float], *, blocking_gap: bool = False) -> Result:
    """Frozen MDD: min(wealth_t / running_peak_t - 1), as negative decimal."""
    if blocking_gap:
        return Result("UNKNOWN", reason="blocking daily wealth data gap")
    values = _finite(wealth, "daily wealth")
    if any(x <= 0 for x in values):
        raise ContractViolation("daily wealth observations must be positive")
    peak = values[0]
    mdd = 0.0
    for value in values:
        peak = max(peak, value)
        mdd = min(mdd, value / peak - 1.0)
    return Result("KNOWN", mdd)


def recovery_metrics(
    dates: Sequence[date], wealth: Sequence[float], *, blocking_gap: bool = False
) -> RecoveryResult:
    """Frozen drawdown/recovery events under W12.1-FREEZE-v1.2.0.

    - Same-window only; no look-before/look-ahead.
    - Equal peak tie: latest occurrence at/before selected trough.
    - Equal MDD trough tie: earliest occurrence.
    - Recovery: first observation strictly after trough with wealth >= peak value.
    - Recovery time: calendar days from trough to recovery.
    """
    if blocking_gap:
        return RecoveryResult("UNKNOWN", reason="blocking daily wealth data gap")
    if len(dates) != len(wealth) or not dates:
        raise ContractViolation("dates and daily wealth must be non-empty and aligned")
    if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
        raise ContractViolation("dates must be strictly increasing")
    values = _finite(wealth, "daily wealth")
    if any(x <= 0 for x in values):
        raise ContractViolation("daily wealth observations must be positive")

    peak_value = values[0]
    peak_idx = 0
    selected_peak_idx = 0
    trough_idx = 0
    min_dd = 0.0

    for i, value in enumerate(values):
        # Latest equal peak wins for subsequent drawdown anchoring.
        if value >= peak_value:
            peak_value = value
            peak_idx = i
        dd = value / peak_value - 1.0
        # Strict inequality preserves earliest trough on equal-MDD ties.
        if dd < min_dd:
            min_dd = dd
            trough_idx = i
            selected_peak_idx = peak_idx

    if min_dd == 0.0:
        return RecoveryResult(
            "NOT_APPLICABLE", mdd=0.0,
            reason="MDD=0; no drawdown episode exists for recovery semantics",
        )

    selected_peak_value = values[selected_peak_idx]
    recovery_idx: int | None = None
    for i in range(trough_idx + 1, len(values)):
        if values[i] >= selected_peak_value:
            recovery_idx = i
            break

    if recovery_idx is None:
        return RecoveryResult(
            "UNRECOVERED_AT_PERIOD_END",
            mdd=min_dd,
            peak_date=dates[selected_peak_idx],
            peak_value=selected_peak_value,
            trough_date=dates[trough_idx],
            trough_value=values[trough_idx],
            recovery_date=None,
            recovery_time_calendar_days=None,
            reason="selected peak was not recovered before the exact period end",
        )

    recovery_date = dates[recovery_idx]
    return RecoveryResult(
        "KNOWN",
        mdd=min_dd,
        peak_date=dates[selected_peak_idx],
        peak_value=selected_peak_value,
        trough_date=dates[trough_idx],
        trough_value=values[trough_idx],
        recovery_date=recovery_date,
        recovery_time_calendar_days=(recovery_date - dates[trough_idx]).days,
    )


def resolve_monthly_rf(
    year: int, month: int, currency: str, observations: Sequence[RiskFreeObservation]
) -> Result:
    """Select last official observation within that month; never cross-month fill."""
    if currency not in RF_SOURCES:
        return Result("UNKNOWN", reason=f"unsupported currency: {currency}")
    expected_source = RF_SOURCES[currency]
    same_month = [o for o in observations if o.observed_on.year == year and o.observed_on.month == month]
    if not same_month:
        return Result("UNKNOWN", reason="whole month has no official risk-free observation")
    if any(o.currency != currency or o.source != expected_source for o in same_month):
        return Result("BLOCKED", reason="risk-free source/currency does not match frozen source map")
    chosen = max(same_month, key=lambda o: o.observed_on)
    if not isfinite(chosen.annual_quoted_percent):
        return Result("BLOCKED", reason="risk-free observation is not finite")
    return Result("KNOWN", (chosen.annual_quoted_percent / 100.0) / 12.0)


def _excess_returns(returns: Sequence[float], monthly_rf: Sequence[float]) -> list[float] | Result:
    if len(returns) != len(monthly_rf):
        return Result("UNKNOWN", reason="monthly return and risk-free observations are not fully aligned")
    if not returns:
        return Result("NOT_APPLICABLE", reason="no complete monthly observations")
    r = _finite(returns, "monthly returns")
    rf = _finite(monthly_rf, "monthly risk-free rates")
    if any(x <= -1 for x in r) or any(x <= -1 for x in rf):
        raise ContractViolation("monthly return and risk-free rates must be greater than -100%")
    return [((1.0 + x) / (1.0 + y)) - 1.0 for x, y in zip(r, rf)]


def _history_gate(n: int, *, required_months: int | None, special_full_window: bool) -> Result | None:
    if special_full_window:
        if required_months not in (84, 120, 180):
            raise ContractViolation("7Y/10Y/15Y full-window requirement must be 84/120/180 months")
        if n < required_months:
            return Result("SHORT_HISTORY", reason=f"requires {required_months} complete monthly returns; found {n}")
    if n < 12:
        return Result("NOT_APPLICABLE", reason="fewer than 12 complete monthly returns")
    if 12 <= n <= 23:
        return Result("SHORT_HISTORY", reason="12-23 complete monthly returns")
    return None


def sharpe_monthly_rf(
    returns: Sequence[float], monthly_rf: Sequence[float], *, required_months: int | None = None,
    special_full_window: bool = False,
) -> Result:
    excess = _excess_returns(returns, monthly_rf)
    if isinstance(excess, Result):
        return excess
    gate = _history_gate(len(excess), required_months=required_months, special_full_window=special_full_window)
    if gate:
        return gate
    if len(excess) < 2 or stdev(excess) == 0:
        return Result("NOT_APPLICABLE", reason="sample standard deviation is zero or undefined")
    return Result("KNOWN", sqrt(12.0) * mean(excess) / stdev(excess))


def sortino_monthly_rf(
    returns: Sequence[float], monthly_rf: Sequence[float], *, required_months: int | None = None,
    special_full_window: bool = False,
) -> Result:
    excess = _excess_returns(returns, monthly_rf)
    if isinstance(excess, Result):
        return excess
    gate = _history_gate(len(excess), required_months=required_months, special_full_window=special_full_window)
    if gate:
        return gate
    downside = sqrt(mean(min(x, 0.0) ** 2 for x in excess))
    if downside == 0:
        return Result("NOT_APPLICABLE", reason="DownsideDeviation=0")
    return Result("KNOWN", sqrt(12.0) * mean(excess) / downside)


def calmar_matched_window(cagr: float, mdd: float, *, cagr_range: str, mdd_range: str,
                          cagr_basis: str, mdd_basis: str, years: float) -> Result:
    """Frozen Calmar: CAGR/MDD for exactly the same range and total-return basis."""
    if cagr_range != mdd_range or cagr_basis != mdd_basis:
        return Result("BLOCKED", reason="CAGR and MDD must have the exact same range and total-return basis")
    if cagr_basis != "PRE_TAX_TOTAL_RETURN":
        return Result("BLOCKED", reason="basis is not the frozen pre-tax total-return basis")
    if years < 1:
        return Result("NOT_APPLICABLE", reason="period shorter than one year")
    if years < 3:
        return Result("SHORT_HISTORY", reason="period is at least 1Y and shorter than 36 months")
    if mdd == 0:
        return Result("NOT_APPLICABLE", reason="MDD=0")
    if not all(isfinite(float(x)) for x in (cagr, mdd, years)) or mdd > 0:
        raise ContractViolation("CAGR/MDD/years must be finite and MDD must be non-positive")
    return Result("KNOWN", float(cagr) / abs(float(mdd)))
