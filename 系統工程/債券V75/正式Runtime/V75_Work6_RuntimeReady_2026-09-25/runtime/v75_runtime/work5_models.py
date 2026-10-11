from __future__ import annotations

from enum import StrEnum
from pydantic import Field, model_validator

from .enums import EvaluationState, GateState
from .models import Money, StrictModel, V75RunOutput


class Work5FinalClassification(StrEnum):
    ACTIONABLE = "ACTIONABLE"
    NO_NEW_MONEY_ACTION = "NO_NEW_MONEY_ACTION"
    EXISTING_POSITION_REVIEW = "EXISTING_POSITION_REVIEW"
    HARD_WAIT = "HARD_WAIT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class Work5FinalSnapshot(StrictModel):
    """Final Work5 snapshot envelope for LivingWaterAI integration.

    This is an integration/read model only. It must not recompute target, gap,
    predicates, deployment percentages, or funding semantics.
    """
    run_id: str = Field(min_length=1)
    broker_account_id: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    final_classification: Work5FinalClassification
    gate_state: GateState
    evaluation_state: EvaluationState
    bond_long_term_target: Money | None = None
    output: V75RunOutput
    source_lineage: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_identity(self) -> "Work5FinalSnapshot":
        if self.output.run_id != self.run_id:
            raise ValueError("Work5 snapshot run_id must match output")
        if self.output.broker_account_id != self.broker_account_id:
            raise ValueError("Work5 snapshot broker_account_id must match output")
        if self.output.currency != self.currency:
            raise ValueError("Work5 snapshot currency must match output")
        if self.output.evaluation_state != self.evaluation_state:
            raise ValueError("Work5 snapshot evaluation_state must match output")
        return self
