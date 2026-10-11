from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from .constants import (
    FORBIDDEN_GENERIC_SUB_STATES,
    PREDICATE_STATE_PRECEDENCE,
    PREDICATE_VERSION,
    PRED_010_INTERNAL_COMPONENT_STATES,
    RULE_SOT_VERSION,
)
from .enums import (
    BrokerDomainType,
    CanonicalUnit,
    DeploymentState,
    EvaluationState,
    ExistingPositionAction,
    FreshnessState,
    GateState,
    NewMoneyAction,
    PredicateAssessmentStatus,
    SettlementState,
    ValueStatus,
)

ISO_4217_LIKE = re.compile(r"^[A-Z]{3}$")


def _reject_nonfinite_json_numbers(value: JsonValue, path: str = "payload") -> None:
    """Keep generic canonical payloads JSON-round-trippable without NaN/Infinity loss."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains non-finite JSON number")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _reject_nonfinite_json_numbers(item, f"{path}[{idx}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_nonfinite_json_numbers(item, f"{path}.{key}")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class Money(StrictModel):
    amount: Decimal = Field(ge=0)
    currency: str

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not ISO_4217_LIKE.fullmatch(value):
            raise ValueError("currency must be a 3-letter uppercase ISO-4217 style code")
        return value


class MoneyValue(StrictModel):
    status: ValueStatus
    value: Money | None = None

    @model_validator(mode="after")
    def enforce_status_value(self) -> "MoneyValue":
        if self.status == ValueStatus.KNOWN and self.value is None:
            raise ValueError("KNOWN MoneyValue requires value")
        if self.status != ValueStatus.KNOWN and self.value is not None:
            raise ValueError("UNKNOWN/NOT_APPLICABLE MoneyValue must not carry a numeric value")
        return self


class PercentValue(StrictModel):
    value: Decimal = Field(ge=0, le=100)
    unit: CanonicalUnit = CanonicalUnit.PERCENT

    @model_validator(mode="after")
    def unit_must_match(self) -> "PercentValue":
        if self.unit != CanonicalUnit.PERCENT:
            raise ValueError("PercentValue unit must be PERCENT")
        return self


class PercentagePointValue(StrictModel):
    value: Decimal
    unit: CanonicalUnit = CanonicalUnit.PERCENTAGE_POINT

    @model_validator(mode="after")
    def unit_must_match(self) -> "PercentagePointValue":
        if self.unit != CanonicalUnit.PERCENTAGE_POINT:
            raise ValueError("PercentagePointValue unit must be PERCENTAGE_POINT")
        return self


class BasisPointValue(StrictModel):
    value: Decimal
    unit: CanonicalUnit = CanonicalUnit.BASIS_POINT

    @model_validator(mode="after")
    def unit_must_match(self) -> "BasisPointValue":
        if self.unit != CanonicalUnit.BASIS_POINT:
            raise ValueError("BasisPointValue unit must be BASIS_POINT")
        return self


class BrokerAccountContext(StrictModel):
    broker_account_id: str = Field(min_length=1)
    broker_domain_type: BrokerDomainType
    currency: str

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not ISO_4217_LIKE.fullmatch(value):
            raise ValueError("currency must be a 3-letter uppercase ISO-4217 style code")
        return value


class UpstreamFundingContext(StrictModel):
    """Upstream-only representation. V75 does not move funds between these buckets."""
    new_investment_cash_total: Money
    tw_local_broker_new_investment_amount: Money
    tw_sub_brokerage_new_investment_amount: Money
    us_broker_new_investment_amount: Money

    @model_validator(mode="after")
    def validate_three_bucket_sum(self) -> "UpstreamFundingContext":
        currencies = {
            self.new_investment_cash_total.currency,
            self.tw_local_broker_new_investment_amount.currency,
            self.tw_sub_brokerage_new_investment_amount.currency,
            self.us_broker_new_investment_amount.currency,
        }
        if len(currencies) != 1:
            raise ValueError("upstream funding split must use one declared funding currency before broker settlement")
        bucket_sum = (
            self.tw_local_broker_new_investment_amount.amount
            + self.tw_sub_brokerage_new_investment_amount.amount
            + self.us_broker_new_investment_amount.amount
        )
        if bucket_sum != self.new_investment_cash_total.amount:
            raise ValueError("three upstream broker funding buckets must sum exactly to new_investment_cash_total")
        return self


class SettlementStateModel(StrictModel):
    state: SettlementState
    as_of: datetime | date
    source_lineage: list[str]

    @field_validator("source_lineage")
    @classmethod
    def require_lineage(cls, values: list[str]) -> list[str]:
        if not values or any(not v.strip() for v in values):
            raise ValueError("SettlementStateModel requires non-empty source_lineage")
        return values


class RuntimeStateModel(StrictModel):
    freshness_state: FreshnessState
    evaluation_state: EvaluationState
    gate_state: GateState


class SnapshotModel(StrictModel):
    data_timestamp: datetime
    data_source: str = Field(min_length=1)
    freshness_state: FreshnessState
    source_lineage: list[str] = Field(default_factory=list)
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def payload_must_be_canonical_json(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _reject_nonfinite_json_numbers(value, "payload")
        return value

    @field_validator("source_lineage")
    @classmethod
    def no_blank_lineage(cls, values: list[str]) -> list[str]:
        if not values or any(not v.strip() for v in values):
            raise ValueError("SnapshotModel requires non-empty source_lineage")
        return values


class HoldingSnapshot(StrictModel):
    asset_id: str = Field(min_length=1)
    amount: Money
    broker_account_id: str | None = None


class TargetHoldingSnapshot(StrictModel):
    asset_id: str = Field(min_length=1)
    target_amount: Money
    broker_account_id: str | None = None


class PerAssetDeploymentInput(StrictModel):
    asset_id: str = Field(min_length=1)
    remaining_target_gap_amount: Money
    eligibility_state: str | None = None
    existing_position_amount: Money
    currency: str
    broker_account_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_gap_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        legacy_present = "remaining_target_gap" in data
        canonical_present = "remaining_target_gap_amount" in data
        if legacy_present and canonical_present:
            try:
                legacy_value = Money.model_validate(data["remaining_target_gap"])
                canonical_value = Money.model_validate(data["remaining_target_gap_amount"])
            except Exception as exc:
                raise ValueError("legacy/canonical remaining target gap values must both be valid Money") from exc
            if legacy_value != canonical_value:
                raise ValueError(
                    "legacy remaining_target_gap conflicts with canonical remaining_target_gap_amount"
                )
            data.pop("remaining_target_gap")
        elif legacy_present:
            data["remaining_target_gap_amount"] = data.pop("remaining_target_gap")
        return data

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not ISO_4217_LIKE.fullmatch(value):
            raise ValueError("currency must be a 3-letter uppercase ISO-4217 style code")
        return value

    @model_validator(mode="after")
    def currencies_must_agree(self) -> "PerAssetDeploymentInput":
        if self.remaining_target_gap_amount.currency != self.currency:
            raise ValueError("remaining_target_gap_amount currency must match per-asset currency")
        if self.existing_position_amount.currency != self.currency:
            raise ValueError("existing_position_amount currency must match per-asset currency")
        return self


class PredicateResult(StrictModel):
    predicate_id: str
    predicate_version: str
    aggregate_state: str | None = None
    sub_states: list[str] = Field(default_factory=list)
    assessment_status: PredicateAssessmentStatus
    as_of: datetime | date
    source_lineage: list[str]
    input_freshness_state: FreshnessState
    reason_codes: list[str] = Field(default_factory=list)
    required_input_missing: list[str] = Field(default_factory=list)

    @field_validator("predicate_id")
    @classmethod
    def predicate_id_is_known(cls, value: str) -> str:
        if value not in PREDICATE_STATE_PRECEDENCE:
            raise ValueError(f"unsupported predicate_id: {value}")
        return value

    @field_validator("predicate_version")
    @classmethod
    def predicate_version_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("predicate_version cannot be blank")
        if value != PREDICATE_VERSION:
            raise ValueError(f"predicate_version must be {PREDICATE_VERSION}")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_display_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if data.get("predicate_id") == "PRED-003":
            if data.get("aggregate_state") == "MIXED/STABLE":
                data["aggregate_state"] = "MIXED_STABLE"
            if isinstance(data.get("sub_states"), list):
                data["sub_states"] = ["MIXED_STABLE" if x == "MIXED/STABLE" else x for x in data["sub_states"]]
        return data

    @field_validator("source_lineage")
    @classmethod
    def formal_predicate_requires_lineage(cls, values: list[str]) -> list[str]:
        if not values or any(not v.strip() for v in values):
            raise ValueError("formal PredicateResult requires non-empty source_lineage")
        return values

    @model_validator(mode="after")
    def enforce_output_state_contract(self) -> "PredicateResult":
        if self.assessment_status == PredicateAssessmentStatus.VALID:
            if self.aggregate_state is None:
                raise ValueError("VALID requires aggregate_state")
            if not self.sub_states:
                raise ValueError("VALID requires non-empty sub_states")
            if self.aggregate_state not in self.sub_states:
                raise ValueError("VALID requires aggregate_state in sub_states")
            if self.input_freshness_state != FreshnessState.FRESH:
                raise ValueError("VALID formal PredicateResult requires FRESH input_freshness_state")
            if self.required_input_missing:
                raise ValueError("VALID formal PredicateResult cannot list required_input_missing")
            allowed = set(PREDICATE_STATE_PRECEDENCE[self.predicate_id])
            illegal = set(self.sub_states) - allowed
            if illegal:
                raise ValueError(f"sub_states contains non-canonical states: {sorted(illegal)}")
            if len(self.sub_states) != len(set(self.sub_states)):
                raise ValueError("sub_states cannot contain duplicates")
            precedence = PREDICATE_STATE_PRECEDENCE[self.predicate_id]
            expected_order = sorted(self.sub_states, key=precedence.index)
            if self.sub_states != expected_order:
                raise ValueError("sub_states must be ordered by canonical predicate precedence")
            if self.aggregate_state != self.sub_states[0]:
                raise ValueError("aggregate_state must equal the highest-precedence state in sub_states")
            if FORBIDDEN_GENERIC_SUB_STATES.intersection(self.sub_states):
                raise ValueError("generic assessment tokens cannot appear in sub_states")
            if self.predicate_id == "PRED-010" and PRED_010_INTERNAL_COMPONENT_STATES.intersection(self.sub_states):
                raise ValueError("PRED-010 component states must not appear in top-level sub_states")
        else:
            if self.aggregate_state is not None or self.sub_states:
                raise ValueError("non-VALID requires aggregate_state=null and sub_states=[]")
        return self


class PerAssetPredicateEvidence(StrictModel):
    """Asset-scoping envelope only; it does not calculate or aggregate predicates."""
    asset_id: str = Field(min_length=1)
    predicate_results: list[PredicateResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_predicate_ids(self) -> "PerAssetPredicateEvidence":
        ids = [result.predicate_id for result in self.predicate_results]
        if len(ids) != len(set(ids)):
            raise ValueError("per-asset predicate evidence cannot contain duplicate predicate_id values")
        return self


class V75RunInput(StrictModel):
    client_ref: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    analysis_timestamp: datetime
    expected_rule_version: str = Field(min_length=1)
    predicate_version: str
    deployment_parameter_version: str = Field(min_length=1)
    broker_account_id: str = Field(min_length=1)
    broker_domain_type: BrokerDomainType
    currency: str
    bond_executable_budget: Money
    broker_cash_total: MoneyValue
    broker_cash_available: MoneyValue
    broker_cash_unsettled: MoneyValue
    broker_cash_reserved: MoneyValue
    sgov_bond_bucket_amount: MoneyValue
    sgov_dry_powder_bucket_amount: MoneyValue
    funding_settlement_status: SettlementState
    life_stage_code: str = Field(min_length=1)
    strategic_bond_weight_b0: PercentValue | None
    existing_bond_holdings: list[HoldingSnapshot]
    target_bond_holdings: list[TargetHoldingSnapshot]
    authorized_universe: list[str]
    market_snapshot: SnapshotModel
    v70_snapshot: SnapshotModel
    source_lineage: list[str]
    per_asset_inputs: list[PerAssetDeploymentInput] = Field(default_factory=list)
    predicate_results: list[PredicateResult] = Field(default_factory=list)
    per_asset_predicate_evidence: list[PerAssetPredicateEvidence] = Field(default_factory=list)

    @field_validator("predicate_version")
    @classmethod
    def predicate_version_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("predicate_version cannot be blank")
        if value != PREDICATE_VERSION:
            raise ValueError(f"predicate_version must be {PREDICATE_VERSION}")
        return value

    @field_validator("expected_rule_version")
    @classmethod
    def rule_version_must_match_frozen_sot(cls, value: str) -> str:
        if value != RULE_SOT_VERSION:
            raise ValueError(f"expected_rule_version must be {RULE_SOT_VERSION}")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not ISO_4217_LIKE.fullmatch(value):
            raise ValueError("currency must be a 3-letter uppercase ISO-4217 style code")
        return value

    @field_validator("source_lineage")
    @classmethod
    def require_source_lineage(cls, values: list[str]) -> list[str]:
        if not values or any(not v.strip() for v in values):
            raise ValueError("V75RunInput requires non-empty source_lineage")
        return values

    @model_validator(mode="after")
    def validate_account_currency_and_settlement(self) -> "V75RunInput":
        currency = self.currency
        money_fields = {
            "bond_executable_budget": self.bond_executable_budget,
        }
        for name, money in money_fields.items():
            if money.currency != currency:
                raise ValueError(f"{name} currency must match run currency")

        money_value_fields = {
            "broker_cash_total": self.broker_cash_total,
            "broker_cash_available": self.broker_cash_available,
            "broker_cash_unsettled": self.broker_cash_unsettled,
            "broker_cash_reserved": self.broker_cash_reserved,
            "sgov_bond_bucket_amount": self.sgov_bond_bucket_amount,
            "sgov_dry_powder_bucket_amount": self.sgov_dry_powder_bucket_amount,
        }
        for name, mv in money_value_fields.items():
            if mv.status == ValueStatus.KNOWN and mv.value and mv.value.currency != currency:
                raise ValueError(f"{name} currency must match run currency")

        if self.funding_settlement_status == SettlementState.UNSETTLED and self.bond_executable_budget.amount > 0:
            raise ValueError("UNSETTLED funding cannot create positive bond_executable_budget")

        if self.broker_cash_available.status == ValueStatus.KNOWN:
            available_cash = self.broker_cash_available.value
            if available_cash is None:
                raise ValueError("KNOWN broker_cash_available requires a value")
            if self.bond_executable_budget.amount > available_cash.amount:
                raise ValueError("bond_executable_budget cannot exceed same-account broker_cash_available")

        for collection_name, collection in (
            ("existing_bond_holdings", self.existing_bond_holdings),
            ("target_bond_holdings", self.target_bond_holdings),
            ("per_asset_inputs", self.per_asset_inputs),
        ):
            for item in collection:
                item_account = getattr(item, "broker_account_id", None)
                if item_account is not None and item_account != self.broker_account_id:
                    raise ValueError(f"{collection_name} contains cross-account item")
                item_currency = getattr(item, "currency", None)
                if item_currency is not None and item_currency != currency:
                    raise ValueError(f"{collection_name} contains cross-currency item")
                amount_obj = getattr(item, "amount", None) or getattr(item, "target_amount", None)
                if isinstance(amount_obj, Money) and amount_obj.currency != currency:
                    raise ValueError(f"{collection_name} contains cross-currency money")

        def compare_timestamp_to_analysis(value: datetime | date, field_name: str) -> None:
            if isinstance(value, datetime):
                analysis_aware = self.analysis_timestamp.tzinfo is not None and self.analysis_timestamp.utcoffset() is not None
                value_aware = value.tzinfo is not None and value.utcoffset() is not None
                if analysis_aware != value_aware:
                    raise ValueError(f"{field_name} timezone-awareness must match analysis_timestamp")
                if value > self.analysis_timestamp:
                    raise ValueError(f"{field_name} cannot be later than analysis_timestamp")
            elif value > self.analysis_timestamp.date():
                raise ValueError(f"{field_name} cannot be later than analysis_timestamp date")

        for snapshot_name, snapshot in (("market_snapshot", self.market_snapshot), ("v70_snapshot", self.v70_snapshot)):
            compare_timestamp_to_analysis(snapshot.data_timestamp, f"{snapshot_name}.data_timestamp")

        global_predicate_ids = [result.predicate_id for result in self.predicate_results]
        if len(global_predicate_ids) != len(set(global_predicate_ids)):
            raise ValueError("run-level predicate_results cannot contain duplicate predicate_id values")
        for result in self.predicate_results:
            compare_timestamp_to_analysis(result.as_of, f"predicate_results[{result.predicate_id}].as_of")

        deployment_asset_id_list = [item.asset_id for item in self.per_asset_inputs]
        if len(deployment_asset_id_list) != len(set(deployment_asset_id_list)):
            raise ValueError("per_asset_inputs cannot contain duplicate asset_id values")

        evidence_asset_ids = [item.asset_id for item in self.per_asset_predicate_evidence]
        if len(evidence_asset_ids) != len(set(evidence_asset_ids)):
            raise ValueError("per_asset_predicate_evidence cannot contain duplicate asset_id envelopes")
        deployment_asset_ids = set(deployment_asset_id_list)
        for evidence in self.per_asset_predicate_evidence:
            if evidence.asset_id not in deployment_asset_ids:
                raise ValueError("per-asset predicate evidence must reference an asset present in per_asset_inputs")
            for result in evidence.predicate_results:
                compare_timestamp_to_analysis(
                    result.as_of,
                    f"per_asset_predicate_evidence[{evidence.asset_id}][{result.predicate_id}].as_of",
                )
        return self


class PerAssetDecision(StrictModel):
    """Schema only. Work2 never creates a decision or calculates amounts."""
    asset_id: str = Field(min_length=1)
    deployment_state: DeploymentState | None = None
    deployment_pct: PercentValue | None = None
    deploy_amount: Money | None = None
    new_money_action: NewMoneyAction | None = None
    existing_position_action: ExistingPositionAction | None = None
    existing_reduction_pct: PercentValue | None = None
    classification: list[str] = Field(default_factory=list)
    gate_state: GateState
    evaluation_state: EvaluationState
    reason_codes: list[str] = Field(default_factory=list)
    source_lineage: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_frozen_mapping_shape(self) -> "PerAssetDecision":
        from .constants import DEPLOYMENT_PCT_CONTRACT
        if self.deployment_state is not None and self.deployment_pct is not None:
            expected = DEPLOYMENT_PCT_CONTRACT[self.deployment_state]
            if self.deployment_pct.value != expected:
                raise ValueError("deployment_pct conflicts with frozen P0-02 deployment mapping")
        if self.existing_reduction_pct is not None:
            raise ValueError("numeric existing-position reduction is not authorized by current frozen SOT")
        return self


class V75RunOutput(StrictModel):
    """Output schema skeleton only. No Work2 engine populates investment decisions."""
    run_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    predicate_version: str
    deployment_parameter_version: str = Field(min_length=1)
    broker_account_id: str = Field(min_length=1)
    broker_domain_type: BrokerDomainType
    currency: str
    bond_long_term_target: Money | None = None
    bond_allocation_final: dict[str, JsonValue] = Field(default_factory=dict)
    per_asset_decisions: list[PerAssetDecision] = Field(default_factory=list)
    sgov_bond_bucket_amount: MoneyValue
    v75_undeployed_to_sgov: Money | None = None
    formal_output_eligible: bool
    evaluation_state: EvaluationState
    missing_required_fields: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    source_lineage: list[str] = Field(default_factory=list)

    @field_validator("bond_allocation_final")
    @classmethod
    def allocation_payload_must_be_canonical_json(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _reject_nonfinite_json_numbers(value, "bond_allocation_final")
        return value

    @field_validator("predicate_version")
    @classmethod
    def predicate_version_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("predicate_version cannot be blank")
        if value != PREDICATE_VERSION:
            raise ValueError(f"predicate_version must be {PREDICATE_VERSION}")
        return value

    @field_validator("rule_version")
    @classmethod
    def output_rule_version_must_match_frozen_sot(cls, value: str) -> str:
        if value != RULE_SOT_VERSION:
            raise ValueError(f"rule_version must be {RULE_SOT_VERSION}")
        return value

    @field_validator("currency")
    @classmethod
    def validate_output_currency(cls, value: str) -> str:
        value = value.upper()
        if not ISO_4217_LIKE.fullmatch(value):
            raise ValueError("currency must be a 3-letter uppercase ISO-4217 style code")
        return value

    @model_validator(mode="after")
    def validate_output_ownership_boundaries(self) -> "V75RunOutput":
        decision_asset_ids = [decision.asset_id for decision in self.per_asset_decisions]
        if len(decision_asset_ids) != len(set(decision_asset_ids)):
            raise ValueError("per_asset_decisions cannot contain duplicate asset_id values")
        if self.formal_output_eligible:
            if self.evaluation_state != EvaluationState.COMPLETE:
                raise ValueError("formal_output_eligible=true requires evaluation_state=COMPLETE")
            if self.missing_required_fields:
                raise ValueError("formal_output_eligible=true requires missing_required_fields=[]")
        if self.evaluation_state == EvaluationState.COMPLETE and self.missing_required_fields:
            raise ValueError("evaluation_state=COMPLETE cannot carry missing_required_fields")

        def contains_forbidden_dry_powder_key(value: Any) -> bool:
            if isinstance(value, dict):
                for key, nested in value.items():
                    key_norm = str(key).strip().lower()
                    if key_norm in {"sgov_dry_powder_bucket", "sgov_dry_powder_bucket_amount"}:
                        return True
                    if contains_forbidden_dry_powder_key(nested):
                        return True
            elif isinstance(value, list):
                return any(contains_forbidden_dry_powder_key(item) for item in value)
            return False

        if contains_forbidden_dry_powder_key(self.bond_allocation_final):
            raise ValueError("V75 output must not contain final SGOV_DRY_POWDER_BUCKET aggregate fields")
        if self.bond_long_term_target is not None and self.bond_long_term_target.currency != self.currency:
            raise ValueError("bond_long_term_target currency must match output currency")
        if (
            self.sgov_bond_bucket_amount.status == ValueStatus.KNOWN
            and self.sgov_bond_bucket_amount.value is not None
            and self.sgov_bond_bucket_amount.value.currency != self.currency
        ):
            raise ValueError("sgov_bond_bucket_amount currency must match output currency")
        for decision in self.per_asset_decisions:
            if decision.deploy_amount is not None and decision.deploy_amount.currency != self.currency:
                raise ValueError("per_asset_decisions deploy_amount currency must match output currency")
        if self.v75_undeployed_to_sgov is not None:
            if self.broker_domain_type != BrokerDomainType.US_BROKER:
                raise ValueError("v75_undeployed_to_sgov is only legal for US_BROKER")
            if self.currency != "USD" or self.v75_undeployed_to_sgov.currency != "USD":
                raise ValueError("v75_undeployed_to_sgov must remain same-account USD context")
        return self
