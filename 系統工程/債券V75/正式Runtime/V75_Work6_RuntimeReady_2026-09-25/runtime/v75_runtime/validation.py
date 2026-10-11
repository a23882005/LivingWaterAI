from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .constants import BANK_FUNDING_FIELD_MARKERS, PREDICATE_VERSION, RULE_SOT_VERSION
from .enums import FreshnessState, SettlementState, ValidationDisposition, ValueStatus
from .models import PredicateResult, V75RunInput


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class ValidationResult:
    disposition: ValidationDisposition
    model: V75RunInput | PredicateResult | None
    issues: tuple[ValidationIssue, ...]

    @property
    def accepted(self) -> bool:
        return self.disposition == ValidationDisposition.ACCEPT


def _contains_bank_funding_field(value: Any, path: str = "") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            current_path = f"{path}.{key}" if path else str(key)
            if any(marker in key_lower for marker in BANK_FUNDING_FIELD_MARKERS):
                issues.append(ValidationIssue("BANK_FUNDING_OUT_OF_SCOPE", "bank funding fields are not valid V75 executable input", current_path))
            issues.extend(_contains_bank_funding_field(nested, current_path))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            issues.extend(_contains_bank_funding_field(nested, f"{path}[{idx}]"))
    return issues


def _schema_issues(exc: ValidationError) -> tuple[ValidationIssue, ...]:
    return tuple(
        ValidationIssue(
            "SCHEMA_VALIDATION_ERROR",
            error["msg"],
            ".".join(str(part) for part in error["loc"]),
        )
        for error in exc.errors()
    )


def _nested_predicate_version_issues(payload: dict[str, Any]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    for idx, result in enumerate(payload.get("predicate_results", []) or []):
        if isinstance(result, dict):
            version = result.get("predicate_version")
            if version is not None and str(version).strip() and version != PREDICATE_VERSION:
                issues.append(
                    ValidationIssue(
                        "VERSION_MISMATCH",
                        "nested predicate version mismatch",
                        f"predicate_results[{idx}].predicate_version",
                    )
                )
    for envelope_idx, envelope in enumerate(payload.get("per_asset_predicate_evidence", []) or []):
        if not isinstance(envelope, dict):
            continue
        for result_idx, result in enumerate(envelope.get("predicate_results", []) or []):
            if isinstance(result, dict):
                version = result.get("predicate_version")
                if version is not None and str(version).strip() and version != PREDICATE_VERSION:
                    issues.append(
                        ValidationIssue(
                            "VERSION_MISMATCH",
                            "nested per-asset predicate version mismatch",
                            f"per_asset_predicate_evidence[{envelope_idx}].predicate_results[{result_idx}].predicate_version",
                        )
                    )
    return tuple(issues)


def _nested_predicate_missing_version_issues(payload: dict[str, Any]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    for idx, result in enumerate(payload.get("predicate_results", []) or []):
        if isinstance(result, dict) and not str(result.get("predicate_version", "")).strip():
            issues.append(
                ValidationIssue(
                    "MISSING_REQUIRED_INPUT",
                    "nested predicate_version is required for formal PredicateResult",
                    f"predicate_results[{idx}].predicate_version",
                )
            )
    for envelope_idx, envelope in enumerate(payload.get("per_asset_predicate_evidence", []) or []):
        if not isinstance(envelope, dict):
            continue
        for result_idx, result in enumerate(envelope.get("predicate_results", []) or []):
            if isinstance(result, dict) and not str(result.get("predicate_version", "")).strip():
                issues.append(
                    ValidationIssue(
                        "MISSING_REQUIRED_INPUT",
                        "nested per-asset predicate_version is required for formal PredicateResult",
                        f"per_asset_predicate_evidence[{envelope_idx}].predicate_results[{result_idx}].predicate_version",
                    )
                )
    return tuple(issues)


def validate_predicate_result(payload: dict[str, Any]) -> ValidationResult:
    """Validate output-state shape without calculating any predicate condition."""
    supplied_version = payload.get("predicate_version")
    if not str(supplied_version or "").strip():
        return ValidationResult(
            ValidationDisposition.INSUFFICIENT_DATA,
            None,
            (ValidationIssue("MISSING_REQUIRED_INPUT", "predicate_version is required for formal PredicateResult", "predicate_version"),),
        )
    if supplied_version is not None and str(supplied_version).strip() and supplied_version != PREDICATE_VERSION:
        return ValidationResult(
            ValidationDisposition.REVIEW_REQUIRED,
            None,
            (ValidationIssue("VERSION_MISMATCH", "predicate version mismatch", "predicate_version"),),
        )
    try:
        model = PredicateResult.model_validate(payload)
    except ValidationError as exc:
        return ValidationResult(ValidationDisposition.INVALID_INPUT, None, _schema_issues(exc))

    if model.predicate_version != PREDICATE_VERSION:
        return ValidationResult(
            ValidationDisposition.REVIEW_REQUIRED,
            model,
            (ValidationIssue("VERSION_MISMATCH", "predicate version mismatch", "predicate_version"),),
        )
    return ValidationResult(ValidationDisposition.ACCEPT, model, ())


def validate_v75_run_input(
    payload: dict[str, Any],
    *,
    expected_rule_version: str | None = RULE_SOT_VERSION,
    expected_deployment_parameter_version: str | None = None,
) -> ValidationResult:
    """Work2 data-layer validation only. It never evaluates eligibility/predicates/deployment."""
    if not str(payload.get("predicate_version", "")).strip():
        return ValidationResult(
            ValidationDisposition.INSUFFICIENT_DATA,
            None,
            (ValidationIssue("MISSING_REQUIRED_INPUT", "predicate_version is required for formal branch-driving predicates", "predicate_version"),),
        )

    preflight_review_issues: list[ValidationIssue] = []
    if payload.get("predicate_version") != PREDICATE_VERSION:
        preflight_review_issues.append(ValidationIssue("VERSION_MISMATCH", "predicate version mismatch", "predicate_version"))
    supplied_rule_version = payload.get("expected_rule_version")
    if expected_rule_version is not None and supplied_rule_version is not None and supplied_rule_version != expected_rule_version:
        preflight_review_issues.append(ValidationIssue("VERSION_MISMATCH", "rule version mismatch", "expected_rule_version"))
    supplied_deployment_version = payload.get("deployment_parameter_version")
    if (
        expected_deployment_parameter_version is not None
        and supplied_deployment_version is not None
        and supplied_deployment_version != expected_deployment_parameter_version
    ):
        preflight_review_issues.append(ValidationIssue("VERSION_MISMATCH", "deployment parameter version mismatch", "deployment_parameter_version"))
    preflight_review_issues.extend(_nested_predicate_version_issues(payload))
    if preflight_review_issues:
        return ValidationResult(ValidationDisposition.REVIEW_REQUIRED, None, tuple(preflight_review_issues))

    nested_missing_version_issues = _nested_predicate_missing_version_issues(payload)
    if nested_missing_version_issues:
        return ValidationResult(ValidationDisposition.INSUFFICIENT_DATA, None, nested_missing_version_issues)

    bank_issues = _contains_bank_funding_field(payload)
    if bank_issues:
        return ValidationResult(ValidationDisposition.INVALID_INPUT, None, tuple(bank_issues))

    try:
        model = V75RunInput.model_validate(payload)
    except ValidationError as exc:
        return ValidationResult(ValidationDisposition.INVALID_INPUT, None, _schema_issues(exc))

    insuff_issues: list[ValidationIssue] = []
    if model.broker_cash_available.status != ValueStatus.KNOWN and model.bond_executable_budget.amount > 0:
        insuff_issues.append(ValidationIssue("MISSING_REQUIRED_INPUT", "broker_cash_available must be known for a positive executable budget", "broker_cash_available"))
    if model.funding_settlement_status == SettlementState.UNKNOWN and model.bond_executable_budget.amount > 0:
        insuff_issues.append(ValidationIssue("MISSING_REQUIRED_INPUT", "settlement state must be known for a positive executable budget", "funding_settlement_status"))
    for snapshot_name, snapshot in (("market_snapshot", model.market_snapshot), ("v70_snapshot", model.v70_snapshot)):
        if snapshot.freshness_state in {FreshnessState.STALE, FreshnessState.SUPERSEDED}:
            insuff_issues.append(ValidationIssue("STALE_REQUIRED_INPUT", f"{snapshot_name} is stale/superseded for formal downstream consumption", f"{snapshot_name}.freshness_state"))
        elif snapshot.freshness_state in {FreshnessState.UNKNOWN, FreshnessState.NOT_APPLICABLE}:
            insuff_issues.append(ValidationIssue("MISSING_REQUIRED_INPUT", f"{snapshot_name} has no usable fresh state for formal downstream consumption", f"{snapshot_name}.freshness_state"))
    if insuff_issues:
        return ValidationResult(ValidationDisposition.INSUFFICIENT_DATA, model, tuple(insuff_issues))

    return ValidationResult(ValidationDisposition.ACCEPT, model, ())
