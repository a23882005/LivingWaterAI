from __future__ import annotations

from enum import StrEnum
from pydantic import Field, model_validator

from .enums import BrokerDomainType, EvaluationState, ValueStatus
from .models import Money, MoneyValue, PerAssetDeploymentInput, PercentValue, StrictModel


class Work3EligibilityState(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE_NEW_ALLOCATION = "INELIGIBLE_NEW_ALLOCATION"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class Work3BucketClass(StrEnum):
    US_GENERIC_CORE = "US_GENERIC_CORE"
    TW_GENERIC_CORE = "TW_GENERIC_CORE"
    AUTHORIZED_NON_CORE = "AUTHORIZED_NON_CORE"
    EXISTING_ONLY = "EXISTING_ONLY"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


class Work3IssueClass(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INFO = "INFO"


class Work3Issue(StrictModel):
    issue_class: Work3IssueClass
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    asset_id: str | None = None
    field: str | None = None


class AssetEligibilityAssessment(StrictModel):
    asset_id: str = Field(min_length=1)
    eligibility_state: Work3EligibilityState
    bucket_class: Work3BucketClass
    new_long_term_target_allowed: bool | None
    existing_position_management_allowed: bool
    authorized: bool
    reason_codes: list[str] = Field(default_factory=list)


class LongTermBucketLine(StrictModel):
    asset_id: str = Field(min_length=1)
    bucket_class: Work3BucketClass
    target_amount: Money
    template_weight_pct: PercentValue | None = None


class GapCalculation(StrictModel):
    asset_id: str = Field(min_length=1)
    target_amount: Money
    eligible_existing_amount: MoneyValue
    remaining_target_gap_amount: MoneyValue
    eligibility_state: Work3EligibilityState
    reason_codes: list[str] = Field(default_factory=list)


class BucketReconciliation(StrictModel):
    bond_long_term_target: Money
    us_generic_long_term_target: Money
    tw_generic_long_term_target: Money
    non_core_long_term_target: Money
    us_core_ratio_valid: bool | None
    tw_core_ratio_valid: bool | None
    target_sum_reconciled: bool
    reason_codes: list[str] = Field(default_factory=list)


class SgovRoleReconciliation(StrictModel):
    sgov_bond_bucket_amount: MoneyValue
    sgov_dry_powder_bucket_amount: MoneyValue
    observed_role_total_amount: MoneyValue
    roles_kept_separate: bool = True
    dry_powder_is_read_only_context: bool = True
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_role_separation(self) -> "SgovRoleReconciliation":
        if not self.roles_kept_separate:
            raise ValueError("SGOV bond and dry-powder roles must remain separate")
        if not self.dry_powder_is_read_only_context:
            raise ValueError("SGOV dry-powder input is read-only Integration context in Work3")
        return self


class Work3State(StrictModel):
    run_id: str = Field(min_length=1)
    broker_account_id: str = Field(min_length=1)
    broker_domain_type: BrokerDomainType
    currency: str
    rule_version: str = Field(min_length=1)
    predicate_version: str = Field(min_length=1)
    life_stage_code_passthrough: str = Field(min_length=1)
    evaluation_state: EvaluationState
    work3_complete: bool
    bond_long_term_target: Money | None = None
    eligibility_assessments: list[AssetEligibilityAssessment] = Field(default_factory=list)
    long_term_bucket_lines: list[LongTermBucketLine] = Field(default_factory=list)
    gap_calculations: list[GapCalculation] = Field(default_factory=list)
    per_asset_inputs: list[PerAssetDeploymentInput] = Field(default_factory=list)
    bucket_reconciliation: BucketReconciliation | None = None
    sgov_reconciliation: SgovRoleReconciliation | None = None
    missing_required_fields: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    issues: list[Work3Issue] = Field(default_factory=list)
    source_lineage: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_work3_state(self) -> "Work3State":
        if self.work3_complete and self.evaluation_state != EvaluationState.COMPLETE:
            raise ValueError("work3_complete=true requires evaluation_state=COMPLETE")
        if self.work3_complete and self.missing_required_fields:
            raise ValueError("work3_complete=true requires missing_required_fields=[]")
        if self.evaluation_state == EvaluationState.COMPLETE and self.issues:
            blocking = [i for i in self.issues if i.issue_class != Work3IssueClass.INFO]
            if blocking:
                raise ValueError("COMPLETE Work3 state cannot contain blocking issues")
        return self
