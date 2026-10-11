from __future__ import annotations

from enum import StrEnum
from pydantic import Field, model_validator

from .enums import EvaluationState, GateState
from .models import StrictModel, V75RunOutput
from .work5_models import Work5FinalClassification, Work5FinalSnapshot


class Work6CutoverState(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class Work6RuntimeReadySnapshot(StrictModel):
    """Cutover/readiness envelope. It never recomputes Work1-Work5 investment logic."""
    run_id: str = Field(min_length=1)
    broker_account_id: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    cutover_state: Work6CutoverState
    runtime_ready: bool
    gate_state: GateState
    evaluation_state: EvaluationState
    final_classification: Work5FinalClassification
    output: V75RunOutput
    blocking_reason_codes: list[str]
    source_lineage: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_cutover_identity_and_state(self) -> "Work6RuntimeReadySnapshot":
        if self.output.run_id != self.run_id:
            raise ValueError("Work6 run_id must match Work5 output")
        if self.output.broker_account_id != self.broker_account_id:
            raise ValueError("Work6 broker_account_id must match Work5 output")
        if self.output.currency != self.currency:
            raise ValueError("Work6 currency must match Work5 output")
        if self.output.evaluation_state != self.evaluation_state:
            raise ValueError("Work6 evaluation_state must match Work5 output")
        if self.runtime_ready != (self.cutover_state == Work6CutoverState.READY):
            raise ValueError("Work6 runtime_ready must exactly match cutover_state")
        if self.runtime_ready and self.blocking_reason_codes:
            raise ValueError("Work6 READY cannot contain blocking reasons")
        if not self.runtime_ready and not self.blocking_reason_codes:
            raise ValueError("Work6 BLOCKED requires blocking reasons")
        return self
