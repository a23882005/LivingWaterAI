from __future__ import annotations

import argparse
import hashlib
import json
from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ENGINE_CONTRACT = "W12-7-PRETAX-PERFORMANCE-v1.0.0"
FROZEN_METHOD_CONTRACT = "W12.1-FREEZE-v1.1.0"
TOTAL_RETURN_METHOD_ID = "TR_WEALTH_PRETAX_V1"
TOTAL_RETURN_METHOD_VERSION = "1.0.0"
CAGR_METHOD_ID = "CAGR_ACT3652425_V1"
CAGR_METHOD_VERSION = "1.0.0"
CALCULATION_VERSION = "W12-7-CALC-v1.0.0"
METHODOLOGY_VERSION = FROZEN_METHOD_CONTRACT
WEALTH_BASE = Decimal("100")
BNDW = "BNDW"
REINVESTMENT_PRICE_RULE = "FIRST_FROZEN_OBSERVATION_ON_OR_AFTER_EVENT_DATE"
WINDOW_BOUNDARY_RULE = "USE_WORK12_4_CLOSED_BOUNDARY_ARTIFACT_EXACTLY"
CORPORATE_ACTION_RULE = "USE_WORK12_6_CLOSED_GUARDS; FROZEN_SPLIT_ADJUSTED_SERIES_MUST_NOT_BE_MULTIPLIED_AGAIN"


class PerformanceEngineError(ValueError):
    pass


class InstrumentExcludedError(PerformanceEngineError):
    pass


@dataclass(frozen=True)
class PricePoint:
    instrument: str
    instrument_id: str
    observation_date: date
    value: Decimal
    observation_type: str
    currency: str
    price_basis: str
    dataset_id: str
    row_sha256: str


@dataclass(frozen=True)
class DistributionEvent:
    instrument: str
    event_date: date
    event_date_basis: str
    pay_date_fallback_used: bool
    currency: str
    gross_amount_per_unit: Decimal
    component_count: int
    component_distribution_ids: str
    component_distribution_types: str


@dataclass(frozen=True)
class WealthPoint:
    instrument: str
    observation_date: str
    price_decimal: str
    units_decimal: str
    wealth_index_decimal: str
    reinvestment_event_count: int
    reinvestment_gross_per_unit_decimal: str


@dataclass(frozen=True)
class PerformanceResult:
    instrument: str
    instrument_id: str
    period_label: str
    period_type: str
    requested_as_of_date: str
    effective_observation_start: str | None
    effective_observation_end: str | None
    calendar_days: int | None
    cumulative_total_return_decimal: str | None
    cagr_decimal: str | None
    data_status: str
    reason: str
    return_basis: str
    price_basis: str | None
    distribution_reinvestment: str
    corporate_action_adjustment: str
    currency: str | None
    total_return_method_id: str
    total_return_method_version: str
    cagr_method_id: str
    cagr_method_version: str
    calculation_version: str
    methodology_version: str
    reinvestment_price_rule: str
    boundary_rule: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_date(value: object, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise PerformanceEngineError(f"invalid ISO date for {label}: {value!r}") from exc


def _positive_decimal(value: object, label: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PerformanceEngineError(f"invalid decimal for {label}: {value!r}") from exc
    if not out.is_finite() or out <= 0:
        raise PerformanceEngineError(f"{label} must be finite and > 0")
    return out


def _decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _one_year_anniversary(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def calculate_cagr(beginning_wealth: Decimal, ending_wealth: Decimal, start: date, end: date) -> Decimal:
    if beginning_wealth <= 0 or ending_wealth <= 0:
        raise PerformanceEngineError("wealth values must be > 0")
    if end < _one_year_anniversary(start):
        raise PerformanceEngineError("CAGR requires period >= 1 year")
    days = (end - start).days
    if days <= 0:
        raise PerformanceEngineError("CAGR requires positive calendar-day span")
    with localcontext() as ctx:
        ctx.prec = 50
        ratio = ending_wealth / beginning_wealth
        exponent = Decimal("365.2425") / Decimal(days)
        return +(ctx.power(ratio, exponent) - Decimal("1"))


def load_price_series(path: Path, active_universe: Iterable[str]) -> dict[str, list[PricePoint]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise PerformanceEngineError("price artifact must be a JSON list")
    active = tuple(active_universe)
    if BNDW in active:
        raise PerformanceEngineError("BNDW must not appear in active universe")
    grouped: dict[str, list[PricePoint]] = {i: [] for i in active}
    for n, row in enumerate(raw):
        try:
            instrument_id = str(row["instrument_id"])
            instrument = instrument_id.split(":", 1)[1] if instrument_id.startswith("inst:") else instrument_id
            if instrument == BNDW:
                raise InstrumentExcludedError("BNDW is permanently excluded")
            if instrument not in grouped:
                raise PerformanceEngineError(f"price row outside active universe: {instrument}")
            if str(row.get("data_status")).upper() != "KNOWN":
                raise PerformanceEngineError(f"non-KNOWN price row #{n}")
            grouped[instrument].append(
                PricePoint(
                    instrument=instrument,
                    instrument_id=instrument_id,
                    observation_date=_parse_date(row["observation_date"], "observation_date"),
                    value=_positive_decimal(row["value_decimal"], "price"),
                    observation_type=str(row["observation_type"]).upper(),
                    currency=str(row["currency"]).upper(),
                    price_basis=str(row["price_basis"]),
                    dataset_id=str(row["dataset_id"]),
                    row_sha256=str(row["row_sha256"]),
                )
            )
        except KeyError as exc:
            raise PerformanceEngineError(f"invalid price row #{n}: missing {exc}") from exc
    for instrument, series in grouped.items():
        if not series:
            raise PerformanceEngineError(f"missing price series: {instrument}")
        series.sort(key=lambda x: x.observation_date)
        dates = [p.observation_date for p in series]
        if len(dates) != len(set(dates)):
            raise PerformanceEngineError(f"duplicate price dates: {instrument}")
        if any(a >= b for a, b in zip(dates, dates[1:])):
            raise PerformanceEngineError(f"non-increasing price dates: {instrument}")
        for field, vals in {
            "instrument_id": {x.instrument_id for x in series},
            "observation_type": {x.observation_type for x in series},
            "currency": {x.currency for x in series},
            "price_basis": {x.price_basis for x in series},
            "dataset_id": {x.dataset_id for x in series},
        }.items():
            if len(vals) != 1:
                raise PerformanceEngineError(f"non-constant {field} for {instrument}: {sorted(vals)}")
        if series[0].observation_type not in {"PRICE", "NAV"}:
            raise PerformanceEngineError(f"unsupported observation_type for {instrument}")
    return grouped


def load_reinvestment_schedule(path: Path, active_universe: Iterable[str]) -> dict[str, list[DistributionEvent]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise PerformanceEngineError("reinvestment schedule must be a JSON list")
    active = tuple(active_universe)
    grouped: dict[str, list[DistributionEvent]] = {i: [] for i in active}
    for n, row in enumerate(raw):
        instrument = str(row.get("instrument"))
        if instrument == BNDW:
            raise InstrumentExcludedError("BNDW is permanently excluded")
        if instrument not in grouped:
            raise PerformanceEngineError(f"distribution row outside active universe: {instrument}")
        grouped[instrument].append(
            DistributionEvent(
                instrument=instrument,
                event_date=_parse_date(row["event_date"], "event_date"),
                event_date_basis=str(row["event_date_basis"]),
                pay_date_fallback_used=bool(row["pay_date_fallback_used"]),
                currency=str(row["currency"]).upper(),
                gross_amount_per_unit=_positive_decimal(row["gross_amount_per_unit_decimal"], "gross distribution"),
                component_count=int(row["component_count"]),
                component_distribution_ids=str(row["component_distribution_ids"]),
                component_distribution_types=str(row["component_distribution_types"]),
            )
        )
    for events in grouped.values():
        events.sort(key=lambda x: (x.event_date, x.component_distribution_ids))
    return grouped


def load_json_list(path: Path, label: str) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        raise PerformanceEngineError(f"{label} must be a JSON list")
    return obj


class PreTaxPerformanceEngine:
    def __init__(
        self,
        index_rows: Sequence[Mapping[str, object]],
        price_series: Mapping[str, Sequence[PricePoint]],
        distributions: Mapping[str, Sequence[DistributionEvent]],
        distribution_status_rows: Sequence[Mapping[str, object]],
        boundary_rows: Sequence[Mapping[str, object]],
        corporate_action_status_rows: Sequence[Mapping[str, object]],
        corporate_action_plan_rows: Sequence[Mapping[str, object]],
    ) -> None:
        self.index_rows = [dict(x) for x in index_rows]
        self.active = tuple(str(x["instrument"]) for x in self.index_rows)
        if BNDW in self.active:
            raise PerformanceEngineError("BNDW must not appear in active universe")
        if len(self.active) != len(set(self.active)):
            raise PerformanceEngineError("duplicate instrument in active universe")
        self.index_by_instrument = {str(x["instrument"]): dict(x) for x in self.index_rows}
        self.prices = {k: list(v) for k, v in price_series.items()}
        self.distributions = {k: list(v) for k, v in distributions.items()}
        if set(self.prices) != set(self.active) or set(self.distributions) != set(self.active):
            raise PerformanceEngineError("price/distribution universe mismatch")
        self.distribution_status = {str(x["instrument"]): dict(x) for x in distribution_status_rows}
        self.boundaries = {(str(x["instrument"]), str(x["period_label"])): dict(x) for x in boundary_rows}
        self.ca_status = {str(x["instrument"]): dict(x) for x in corporate_action_status_rows}
        self.ca_plan = [dict(x) for x in corporate_action_plan_rows]
        self._validate_upstream_contracts()
        self._wealth_cache: dict[str, tuple[WealthPoint, ...]] = {}

    def _validate_upstream_contracts(self) -> None:
        if set(self.distribution_status) != set(self.active):
            raise PerformanceEngineError("distribution status universe mismatch")
        if set(self.ca_status) != set(self.active):
            raise PerformanceEngineError("corporate-action status universe mismatch")
        expected_boundary_keys = {(i, p) for i in self.active for p in ("1Y", "3Y", "5Y", "10Y", "15Y")}
        if set(self.boundaries) != expected_boundary_keys:
            missing = sorted(expected_boundary_keys - set(self.boundaries))
            extra = sorted(set(self.boundaries) - expected_boundary_keys)
            raise PerformanceEngineError(f"WORK12-4 boundary matrix mismatch missing={missing} extra={extra}")
        for instrument in self.active:
            idx = self.index_by_instrument[instrument]
            series = self.prices[instrument]
            if len(series) != int(idx["price_rows"]):
                raise PerformanceEngineError(f"price row count mismatch: {instrument}")
            if series[0].dataset_id != str(idx["price_dataset_id"]):
                raise PerformanceEngineError(f"price dataset mismatch: {instrument}")
            price_currency = series[0].currency
            events = self.distributions[instrument]
            if any(e.currency != price_currency for e in events):
                raise PerformanceEngineError(f"distribution currency mismatch: {instrument}")
            status = self.distribution_status[instrument]
            if int(status["event_count"]) != int(idx.get("distribution_rows") or 0):
                raise PerformanceEngineError(f"distribution event count mismatch: {instrument}")
            if not events and str(status["cash_distribution_status"]) != "VERIFIED_NO_CASH_DISTRIBUTION":
                raise PerformanceEngineError(f"empty distribution series is not verified no-cash: {instrument}")
            ca = self.ca_status[instrument]
            if str(ca["frozen_series_adjustment_state"]) != "SPLIT_ADJUSTED":
                raise PerformanceEngineError(f"frozen series not split-adjusted: {instrument}")
            for row in (x for x in self.ca_plan if str(x["instrument"]) == instrument):
                if bool(row["apply_multiplicative_price_adjustment"]):
                    raise PerformanceEngineError(f"double-adjustment guard failed: {instrument}")
                if str(row["price_multiplier_decimal"]) != "1":
                    raise PerformanceEngineError(f"unexpected frozen price multiplier: {instrument}")
        if any(str(x.get("instrument")) == BNDW for x in self.ca_plan):
            raise PerformanceEngineError("BNDW present in corporate-action plan")

    def _instrument_guard(self, instrument: str) -> None:
        if instrument == BNDW:
            raise InstrumentExcludedError("BNDW is permanently excluded")
        if instrument not in self.index_by_instrument:
            raise PerformanceEngineError(f"instrument outside frozen active universe: {instrument}")

    def _distribution_buckets(self, instrument: str) -> dict[int, list[DistributionEvent]]:
        series = self.prices[instrument]
        dates = [p.observation_date for p in series]
        buckets: dict[int, list[DistributionEvent]] = {}
        for event in self.distributions[instrument]:
            idx = bisect_left(dates, event.event_date)
            # A distribution on/before the baseline observation is economically prior to the
            # canonical wealth baseline and must not be injected into starting wealth.
            if idx <= 0:
                continue
            if idx >= len(series):
                # Event is beyond the last frozen valuation; it is outside current wealth coverage.
                continue
            buckets.setdefault(idx, []).append(event)
        return buckets

    def build_wealth_series(self, instrument: str) -> tuple[WealthPoint, ...]:
        self._instrument_guard(instrument)
        if instrument in self._wealth_cache:
            return self._wealth_cache[instrument]
        series = self.prices[instrument]
        buckets = self._distribution_buckets(instrument)
        with localcontext() as ctx:
            ctx.prec = 50
            units = WEALTH_BASE / series[0].value
            out = [
                WealthPoint(
                    instrument=instrument,
                    observation_date=series[0].observation_date.isoformat(),
                    price_decimal=_decimal_string(series[0].value),
                    units_decimal=_decimal_string(units),
                    wealth_index_decimal=_decimal_string(WEALTH_BASE),
                    reinvestment_event_count=0,
                    reinvestment_gross_per_unit_decimal="0",
                )
            ]
            for idx in range(1, len(series)):
                price = series[idx].value
                events = buckets.get(idx, [])
                gross_sum = Decimal("0")
                for event in events:
                    gross_sum += event.gross_amount_per_unit
                    gross_cash = units * event.gross_amount_per_unit
                    units += gross_cash / price
                wealth = units * price
                if not wealth.is_finite() or wealth <= 0:
                    raise PerformanceEngineError(f"invalid wealth generated: {instrument} {series[idx].observation_date}")
                out.append(
                    WealthPoint(
                        instrument=instrument,
                        observation_date=series[idx].observation_date.isoformat(),
                        price_decimal=_decimal_string(price),
                        units_decimal=_decimal_string(units),
                        wealth_index_decimal=_decimal_string(wealth),
                        reinvestment_event_count=len(events),
                        reinvestment_gross_per_unit_decimal=_decimal_string(gross_sum),
                    )
                )
        result = tuple(out)
        self._wealth_cache[instrument] = result
        return result

    def calculate_period(self, instrument: str, period_label: str) -> PerformanceResult:
        self._instrument_guard(instrument)
        if period_label not in {"1Y", "3Y", "5Y", "10Y", "15Y"}:
            raise PerformanceEngineError(f"unsupported period_label: {period_label}")
        boundary = self.boundaries[(instrument, period_label)]
        idx = self.index_by_instrument[instrument]
        base_kwargs = dict(
            instrument=instrument,
            instrument_id=str(idx["instrument_id"]),
            period_label=period_label,
            period_type="TRAILING_NY",
            requested_as_of_date=str(boundary["requested_as_of_date"]),
            return_basis="PRE_TAX_TOTAL_RETURN",
            price_basis=str(idx["price_basis_values"]),
            distribution_reinvestment=f"GROSS_REINVEST@{REINVESTMENT_PRICE_RULE}",
            corporate_action_adjustment=CORPORATE_ACTION_RULE,
            currency=str(idx["price_currency_values"]),
            total_return_method_id=TOTAL_RETURN_METHOD_ID,
            total_return_method_version=TOTAL_RETURN_METHOD_VERSION,
            cagr_method_id=CAGR_METHOD_ID,
            cagr_method_version=CAGR_METHOD_VERSION,
            calculation_version=CALCULATION_VERSION,
            methodology_version=METHODOLOGY_VERSION,
            reinvestment_price_rule=REINVESTMENT_PRICE_RULE,
            boundary_rule=WINDOW_BOUNDARY_RULE,
        )
        if str(boundary["boundary_status"]) != "RESOLVED_OBSERVED_BOUNDARIES":
            return PerformanceResult(
                effective_observation_start=boundary.get("effective_observation_start"),
                effective_observation_end=boundary.get("effective_observation_end"),
                calendar_days=None,
                cumulative_total_return_decimal=None,
                cagr_decimal=None,
                data_status="NOT_APPLICABLE" if str(boundary["boundary_status"]).startswith("NOT_APPLICABLE") else "DATA_UNAVAILABLE",
                reason=f"WORK12-4 boundary status: {boundary['boundary_status']} | {boundary['reason']}",
                **base_kwargs,
            )
        start = _parse_date(boundary["effective_observation_start"], "effective_observation_start")
        end = _parse_date(boundary["effective_observation_end"], "effective_observation_end")
        if end <= start:
            raise PerformanceEngineError("resolved boundary end must be after start")
        wealth = {w.observation_date: Decimal(w.wealth_index_decimal) for w in self.build_wealth_series(instrument)}
        try:
            beginning = wealth[start.isoformat()]
            ending = wealth[end.isoformat()]
        except KeyError as exc:
            raise PerformanceEngineError(f"WORK12-4 boundary is not present in wealth observations: {exc}") from exc
        with localcontext() as ctx:
            ctx.prec = 50
            cumulative = ending / beginning - Decimal("1")
        try:
            cagr = calculate_cagr(beginning, ending, start, end)
        except PerformanceEngineError as exc:
            return PerformanceResult(
                effective_observation_start=start.isoformat(),
                effective_observation_end=end.isoformat(),
                calendar_days=(end - start).days,
                cumulative_total_return_decimal=_decimal_string(cumulative),
                cagr_decimal=None,
                data_status="NOT_APPLICABLE",
                reason=str(exc),
                **base_kwargs,
            )
        return PerformanceResult(
            effective_observation_start=start.isoformat(),
            effective_observation_end=end.isoformat(),
            calendar_days=(end - start).days,
            cumulative_total_return_decimal=_decimal_string(cumulative),
            cagr_decimal=_decimal_string(cagr),
            data_status="KNOWN",
            reason="Calculated deterministically from WORK12-4 closed boundaries + WORK12-5 gross reinvestment schedule + WORK12-6 no-double-adjustment guards.",
            **base_kwargs,
        )

    def validation_summary(self) -> dict:
        return {
            "engine_contract": ENGINE_CONTRACT,
            "frozen_method_contract": FROZEN_METHOD_CONTRACT,
            "calculation_version": CALCULATION_VERSION,
            "methodology_version": METHODOLOGY_VERSION,
            "total_return_method": {"method_id": TOTAL_RETURN_METHOD_ID, "method_version": TOTAL_RETURN_METHOD_VERSION},
            "cagr_method": {"method_id": CAGR_METHOD_ID, "method_version": CAGR_METHOD_VERSION},
            "reinvestment_price_rule": REINVESTMENT_PRICE_RULE,
            "boundary_rule": WINDOW_BOUNDARY_RULE,
            "corporate_action_rule": CORPORATE_ACTION_RULE,
            "active_universe_count": len(self.active),
            "active_universe": list(self.active),
            "bndw": "PERMANENTLY_EXCLUDED",
            "price_rows": sum(len(v) for v in self.prices.values()),
            "reinvestment_rows": sum(len(v) for v in self.distributions.values()),
            "boundary_rows": len(self.boundaries),
            "corporate_action_plan_rows": len(self.ca_plan),
            "full_batch_metrics_materialized": False,
            "work12_8_started": False,
            "risk_stage_started": False,
            "tax_after_tax_started": False,
        }


def _verify_manifest(root: Path, relpath: str) -> None:
    manifest_path = root / relpath
    obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in obj.get("files", []):
        p = root / item["path"]
        if not p.exists() or p.stat().st_size != int(item.get("size", item.get("size_bytes"))) or sha256_file(p) != str(item["sha256"]):
            raise PerformanceEngineError(f"upstream manifest integrity failure: {item['path']}")


def build_engine_from_root(root: Path) -> PreTaxPerformanceEngine:
    root = root.resolve()
    _verify_manifest(root, "05_WORK12-4_ENGINE/WORK12-4_ENGINE_MANIFEST.json")
    _verify_manifest(root, "10_WORK12-5_ENGINE/WORK12-5_ENGINE_MANIFEST.json")
    _verify_manifest(root, "15_WORK12-6_ENGINE/WORK12-6_ENGINE_MANIFEST.json")
    index_rows = load_json_list(root / "01_ENGINE_INPUT_FREEZE/ENGINE_INPUT_INDEX_11.json", "engine input index")
    active = [str(x["instrument"]) for x in index_rows]
    if len(active) != 11 or BNDW in active:
        raise PerformanceEngineError(f"frozen engine input universe must be 11 active instruments with BNDW excluded: {active}")
    prices = load_price_series(
        root / "90_FROZEN_INPUTS/canonical/performance_price_nav_observations.work12-2-12.reconciled.json", active
    )
    distributions = load_reinvestment_schedule(root / "10_WORK12-5_ENGINE/output/REINVESTMENT_SCHEDULE.json", active)
    return PreTaxPerformanceEngine(
        index_rows=index_rows,
        price_series=prices,
        distributions=distributions,
        distribution_status_rows=load_json_list(root / "10_WORK12-5_ENGINE/output/DISTRIBUTION_STATUS_11.json", "distribution statuses"),
        boundary_rows=load_json_list(root / "05_WORK12-4_ENGINE/EXACT_PERIOD_BOUNDARY_MATRIX_11x5_2026-10-02.json", "boundary matrix"),
        corporate_action_status_rows=load_json_list(root / "15_WORK12-6_ENGINE/output/CORPORATE_ACTION_STATUS_11.json", "corporate action statuses"),
        corporate_action_plan_rows=load_json_list(root / "15_WORK12-6_ENGINE/output/CORPORATE_ACTION_ADJUSTMENT_PLAN.json", "corporate action plan"),
    )


def version_lock() -> dict:
    return {
        "engine_contract": ENGINE_CONTRACT,
        "frozen_method_contract": FROZEN_METHOD_CONTRACT,
        "calculation_version": CALCULATION_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "performance_methods": [
            {"method_id": TOTAL_RETURN_METHOD_ID, "method_version": TOTAL_RETURN_METHOD_VERSION},
            {"method_id": CAGR_METHOD_ID, "method_version": CAGR_METHOD_VERSION},
        ],
        "integration_conventions": {
            "reinvestment_price_rule": REINVESTMENT_PRICE_RULE,
            "boundary_rule": WINDOW_BOUNDARY_RULE,
            "corporate_action_rule": CORPORATE_ACTION_RULE,
            "wealth_index_base": "100",
        },
        "ownership_guards": {
            "work12_7": ["TOTAL_RETURN_WEALTH_INDEX", "CUMULATIVE_TOTAL_RETURN", "CAGR"],
            "work12_8_full_batch": "NOT_STARTED",
            "work12_11_risk": "NOT_STARTED",
            "tax_after_tax": "NOT_STARTED",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WORK12-7 Pre-tax Total Return / CAGR engine integration")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--instrument")
    ap.add_argument("--period", choices=["1Y", "3Y", "5Y", "10Y", "15Y"])
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()
    if bool(args.instrument) != bool(args.period):
        raise SystemExit("--instrument and --period must be supplied together")
    eng = build_engine_from_root(args.root)
    obj = eng.validation_summary() if args.validate_only or not args.instrument else asdict(eng.calculate_period(args.instrument, args.period))
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
