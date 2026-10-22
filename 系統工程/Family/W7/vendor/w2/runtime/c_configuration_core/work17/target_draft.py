"""W2-17 deterministic Final Target draft projection over frozen C Work6 output.

No allocation policy or trade quantity is calculated here. This module checks
the C proposal, enforces funding-bucket limits, and emits a traceable DRAFT.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


class TargetDraftError(ValueError):
    pass


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _d(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = Decimal(str(value))
        return x if x.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _known_metric(value: Any, *, amount_key: str = "value") -> Decimal | None:
    if not isinstance(value, Mapping) or value.get("value_state") != "KNOWN":
        return None
    return _d(value.get(amount_key))


@dataclass(frozen=True)
class DraftResult:
    status: str
    draft: Mapping[str, Any] | None
    issue_codes: tuple[str, ...]


def build_final_target_draft(*, c_work6_response: Mapping[str, Any],
                             funding_budgets: Sequence[Mapping[str, Any]],
                             planned_investments: Sequence[Mapping[str, Any]],
                             risk_by_instrument: Mapping[str, Mapping[str, Any]],
                             expected_client_id: str, expected_run_id: str) -> DraftResult:
    """Project one frozen C Work6 proposal into a bounded target-draft DTO.

    `planned_investments` are explicit W1/C-sourced proposed money amounts by
    funding bucket; estimated share quantities are never accepted. All amount
    comparisons stay within the same account bucket and currency.
    """
    issues: list[str] = []
    response = dict(c_work6_response)
    if response.get("status") != "OK" or response.get("engine_version") != "C-W6-v1.0.0":
        return DraftResult("BLOCKED", None, ("C_WORK6_NOT_OK_OR_VERSION_MISMATCH",))
    result = response.get("result")
    if not isinstance(result, Mapping):
        return DraftResult("BLOCKED", None, ("C_WORK6_RESULT_MISSING",))
    identity = result.get("identity") or {}
    if identity.get("client_id") != expected_client_id or identity.get("run_id") != expected_run_id:
        return DraftResult("BLOCKED", None, ("C_CLIENT_OR_RUN_MISMATCH",))
    if result.get("confirmation_status") != "PENDING" or result.get("loop_status") != "PROPOSAL_READY":
        return DraftResult("BLOCKED", None, ("TARGET_DRAFT_MUST_REMAIN_UNCONFIRMED",))
    slot = result.get("draft_allocation")
    if not isinstance(slot, Mapping) or slot.get("value_state") != "KNOWN":
        return DraftResult("BLOCKED", None, ("C_DRAFT_ALLOCATION_UNKNOWN",))
    snapshot = slot.get("snapshot")
    if not isinstance(snapshot, Mapping) or snapshot.get("stage") != "PROPOSED":
        return DraftResult("BLOCKED", None, ("C_DRAFT_STAGE_INVALID",))
    positions = snapshot.get("positions")
    if not isinstance(positions, list):
        return DraftResult("BLOCKED", None, ("C_DRAFT_POSITIONS_MISSING",))

    # Collapse byte-equivalent duplicate instrument positions once, with a visible
    # warning; conflicting duplicates are ambiguous and stop the draft.
    normalized_positions: list[Mapping[str, Any]] = []
    by_instrument: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for p in positions:
        if not isinstance(p, Mapping) or not p.get("instrument_id"):
            return DraftResult("BLOCKED", None, ("C_POSITION_ID_MISSING",))
        iid = str(p["instrument_id"])
        signature = _hash({"weight": p.get("weight"), "portfolio_amount": p.get("portfolio_amount"),
                           "asset_type": p.get("asset_type"), "base_currency": p.get("base_currency")})
        if iid in by_instrument:
            if by_instrument[iid][0] != signature:
                return DraftResult("BLOCKED", None, ("DUPLICATE_TARGET_INSTRUMENT_CONFLICT",))
            issues.append("DUPLICATE_TARGET_INSTRUMENT_COLLAPSED")
            continue
        by_instrument[iid] = (signature, p)
        normalized_positions.append(p)
    positions = sorted(normalized_positions, key=lambda p: str(p.get("instrument_id", "")))

    # C owns target weights and total target amounts. Verify weight conservation
    # using only known values; unknown values stay unknown and make the draft partial.
    weight_values: list[Decimal] = []
    lines: list[dict[str, Any]] = []
    for p in positions:
        if not isinstance(p, Mapping) or not p.get("instrument_id"):
            return DraftResult("BLOCKED", None, ("C_POSITION_ID_MISSING",))
        weight = _known_metric(p.get("weight"))
        amount = _known_metric(p.get("portfolio_amount"), amount_key="amount")
        if weight is None:
            issues.append("TARGET_WEIGHT_UNKNOWN")
        else:
            if weight < 0 or weight > 1:
                return DraftResult("BLOCKED", None, ("TARGET_WEIGHT_OUT_OF_RANGE",))
            weight_values.append(weight)
        amount_obj = p.get("portfolio_amount") or {}
        if amount is None:
            issues.append("TARGET_AMOUNT_UNKNOWN")
        risk = risk_by_instrument.get(str(p["instrument_id"]), {})
        mdd = risk.get("max_drawdown") if isinstance(risk, Mapping) else None
        recovery = risk.get("recovery_period") if isinstance(risk, Mapping) else None
        drawdown_money = risk.get("monetary_drawdown") if isinstance(risk, Mapping) else None
        # If a source says UNKNOWN but contains a numeric placeholder (including 0),
        # emit null so it cannot be mistaken for a measured zero.
        lines.append({
            "instrument_id": str(p["instrument_id"]), "ticker": p.get("ticker"),
            "display_name": p.get("display_name"), "asset_type": p.get("asset_type"),
            "weight": {"value": float(weight) if weight is not None else None,
                       "value_state": "KNOWN" if weight is not None else "UNKNOWN",
                       "source_reference_ids": sorted(set((p.get("weight") or {}).get("source_reference_ids", [])))},
            "target_amount": {"amount": float(amount) if amount is not None else None,
                              "currency": amount_obj.get("currency"),
                              "value_state": "KNOWN" if amount is not None else "UNKNOWN",
                              "source_reference_ids": sorted(set(amount_obj.get("source_reference_ids", [])))},
            "funding_bucket_id": p.get("funding_bucket_id"),
            "market": p.get("market"), "base_currency": p.get("base_currency"),
            "risk": {
                "max_drawdown": _metric_passthrough(mdd),
                "drawdown_amount": _metric_passthrough(drawdown_money, amount_key="amount"),
                "recovery_period": _metric_passthrough(recovery),
            },
            "source_reference_ids": sorted(set(p.get("source_reference_ids", []))),
        })
    if weight_values and abs(sum(weight_values, Decimal("0")) - Decimal("1")) > Decimal("0.0000005"):
        return DraftResult("BLOCKED", None, ("TARGET_WEIGHT_NOT_CONSERVED",))
    if len(weight_values) != len(positions):
        issues.append("TARGET_PERCENTAGES_PARTIAL")

    budgets: dict[str, Mapping[str, Any]] = {}
    for b in funding_budgets:
        bucket = str(b.get("funding_bucket_id", ""))
        if not bucket or bucket in budgets:
            return DraftResult("BLOCKED", None, ("FUNDING_BUCKET_MISSING_OR_DUPLICATE",))
        budgets[bucket] = b
    allocations: dict[tuple[str, str], Decimal] = {}
    seen: dict[tuple[str, str, str], tuple[Decimal, str]] = {}
    deduped: list[dict[str, Any]] = []
    for item in planned_investments:
        if any(k in item for k in ("estimated_shares", "target_shares", "estimated_quantity")):
            return DraftResult("BLOCKED", None, ("ESTIMATED_SHARE_COUNT_NOT_ACCEPTED",))
        iid, bucket, currency = (str(item.get(k, "")) for k in ("instrument_id", "funding_bucket_id", "currency"))
        amount = _d(item.get("amount"))
        if not iid or not bucket or not currency or amount is None or amount < 0:
            return DraftResult("BLOCKED", None, ("PLANNED_INVESTMENT_INVALID",))
        key = (bucket, currency, iid)
        prior = seen.get(key)
        if prior is not None:
            if prior != (amount, currency):
                return DraftResult("BLOCKED", None, ("DUPLICATE_INSTRUMENT_CONFLICT",))
            issues.append("DUPLICATE_IDENTICAL_COLLAPSED")
            continue
        seen[key] = (amount, currency)
        deduped.append(dict(item))
        allocations[(bucket, currency)] = allocations.get((bucket, currency), Decimal("0")) + amount

    deduped.sort(key=lambda x: (str(x.get("instrument_id")), str(x.get("funding_bucket_id")), str(x.get("currency"))))
    cash_residual: list[dict[str, Any]] = []
    for bucket, budget in sorted(budgets.items()):
        if budget.get("value_state") != "KNOWN":
            issues.append("AVAILABLE_BUDGET_UNKNOWN")
            cash_residual.append({"funding_bucket_id": bucket, "currency": budget.get("currency"),
                                  "available_amount": None, "allocated_amount": None,
                                  "cash_residual": None, "value_state": "UNKNOWN",
                                  "source_reference_ids": sorted(set(budget.get("source_reference_ids", [])))})
            continue
        currency = str(budget.get("currency", ""))
        available = _d(budget.get("available_amount"))
        total = _d(budget.get("total_amount"))
        protected = _d(budget.get("protected_amount"))
        if not currency or available is None or available < 0:
            return DraftResult("BLOCKED", None, ("AVAILABLE_BUDGET_INVALID",))
        if total is not None and protected is not None and available > max(Decimal("0"), total - protected) + Decimal("0.01"):
            return DraftResult("BLOCKED", None, ("PROTECTED_LIVING_EXPENSES_USED",))
        other_currencies = [c for (b, c) in allocations if b == bucket and c != currency]
        if other_currencies:
            return DraftResult("BLOCKED", None, ("FUNDING_CURRENCY_MISMATCH",))
        used = allocations.get((bucket, currency), Decimal("0"))
        if used > available + Decimal("0.01"):
            return DraftResult("BLOCKED", None, ("PLANNED_AMOUNT_EXCEEDS_AVAILABLE",))
        cash_residual.append({"funding_bucket_id": bucket, "currency": currency,
                              "available_amount": float(available), "allocated_amount": float(used),
                              "cash_residual": float(max(Decimal("0"), available-used)),
                              "value_state": "KNOWN",
                              "source_reference_ids": sorted(set(budget.get("source_reference_ids", [])))})
    for (bucket, _currency) in allocations:
        if bucket not in budgets:
            return DraftResult("BLOCKED", None, ("FUNDING_BUCKET_NOT_FOUND",))

    for line in lines:
        line["instrument_id"] = str(line["instrument_id"])
        planned_for_line = [{
            "amount": float(_d(x["amount"])), "currency": x["currency"], "value_state": "KNOWN",
            "funding_bucket_id": x["funding_bucket_id"], "source_reference_ids": sorted(set(x.get("source_reference_ids", [])))
        } for x in deduped if x["instrument_id"] == line["instrument_id"]]
        line["planned_investments"] = planned_for_line or [{
            "amount": None, "currency": None, "value_state": "UNKNOWN",
            "funding_bucket_id": line.get("funding_bucket_id"), "source_reference_ids": []}]
        line["funding_bucket_ids"] = sorted({x["funding_bucket_id"] for x in planned_for_line})

    if len(lines) > 10:
        issues.append("TARGET_HOLDINGS_OVER_10_REVIEW")
    if len({b.get("currency") for b in budgets.values() if b.get("currency")}) > 1:
        issues.append("MULTI_CURRENCY_SEPARATE_BUCKETS_NO_FX")
    issues = list(dict.fromkeys(issues))
    partial_codes = {"TARGET_WEIGHT_UNKNOWN", "TARGET_AMOUNT_UNKNOWN", "TARGET_PERCENTAGES_PARTIAL", "AVAILABLE_BUDGET_UNKNOWN"}
    status = "PARTIAL" if partial_codes.intersection(issues) else "DRAFT"
    categories: dict[str, dict[str, Any]] = {}
    for line in lines:
        category = str(line.get("asset_type") or "UNKNOWN")
        item = categories.setdefault(category, {"asset_type": category, "known_weight_total": Decimal("0"),
                                                "all_weights_known": True, "target_amount_by_currency": {},
                                                "source_reference_ids": set()})
        if line["weight"]["value_state"] == "KNOWN":
            item["known_weight_total"] += Decimal(str(line["weight"]["value"]))
        else:
            item["all_weights_known"] = False
        amount_obj = line["target_amount"]
        if amount_obj["value_state"] == "KNOWN" and amount_obj.get("currency"):
            c = amount_obj["currency"]
            item["target_amount_by_currency"][c] = item["target_amount_by_currency"].get(c, Decimal("0")) + Decimal(str(amount_obj["amount"]))
        item["source_reference_ids"].update(line["source_reference_ids"])
    category_summary = [{"asset_type": x["asset_type"],
                         "weight": {"value": float(x["known_weight_total"]) if x["all_weights_known"] else None,
                                    "value_state": "KNOWN" if x["all_weights_known"] else "UNKNOWN"},
                         "target_amount_by_currency": {c: float(a) for c, a in sorted(x["target_amount_by_currency"].items())},
                         "source_reference_ids": sorted(x["source_reference_ids"])}
                        for _, x in sorted(categories.items())]
    denominator = dict(snapshot.get("denominator") or {})
    if isinstance(denominator.get("source_reference_ids"), list):
        denominator["source_reference_ids"] = sorted(set(denominator["source_reference_ids"]))
    draft = {
        "contract_name": "LivingWaterAI.W2.FinalTargetDraft",
        "contract_version": "W2-17-v1.0.0", "status": status,
        "confirmation_status": "PENDING", "is_trade_authorized": False,
        "identity": {"client_id": expected_client_id, "run_id": expected_run_id,
                      "work6_snapshot_id": result.get("work6_snapshot_id")},
        "allocation_id": snapshot.get("allocation_id"), "as_of": snapshot.get("as_of"),
        "denominator": denominator,
        "allocation_by_asset_type": category_summary,
        "target_lines": lines, "cash_residual_by_funding_bucket": cash_residual,
        "c_work6_snapshot_id": result.get("work6_snapshot_id"),
        "source_reference_ids": sorted(set(
            [x for p in positions for x in p.get("source_reference_ids", [])] +
            [x for b in funding_budgets for x in b.get("source_reference_ids", [])])),
        "risk_trace": {line["instrument_id"]: dict(line["risk"]) for line in lines},
        "issue_codes": issues,
    }
    draft["draft_hash"] = _hash(draft)
    return DraftResult(status, draft, tuple(issues))


def _metric_passthrough(metric: Any, *, amount_key: str = "value") -> dict[str, Any]:
    if not isinstance(metric, Mapping) or metric.get("value_state") != "KNOWN":
        issues = list(metric.get("issue_codes", [])) if isinstance(metric, Mapping) else []
        return {"value": None, "value_state": "UNKNOWN", "unit": metric.get("unit") if isinstance(metric, Mapping) else None,
                "as_of": metric.get("as_of") if isinstance(metric, Mapping) else None,
                "source_reference_ids": sorted(set(metric.get("source_reference_ids", []))) if isinstance(metric, Mapping) else [],
                "issue_codes": issues or ["RISK_METRIC_UNKNOWN"]}
    value = _d(metric.get(amount_key))
    refs = sorted(set(metric.get("source_reference_ids", [])))
    if value is None or not refs:
        return {"value": None, "value_state": "UNKNOWN", "unit": metric.get("unit"),
                "as_of": metric.get("as_of"), "source_reference_ids": refs,
                "issue_codes": ["RISK_METRIC_INVALID" if value is None else "RISK_PROVENANCE_MISSING"]}
    return {"value": float(value), "value_state": "KNOWN", "unit": metric.get("unit"),
            "as_of": metric.get("as_of"), "source_reference_ids": refs,
            "issue_codes": list(metric.get("issue_codes", []))}
