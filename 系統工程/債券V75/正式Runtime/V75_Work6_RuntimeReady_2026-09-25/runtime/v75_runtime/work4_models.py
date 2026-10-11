from decimal import Decimal
from enum import StrEnum
from pydantic import Field
from .models import StrictModel

class AssetCreditClassModel(StrEnum):
    TREASURY='TREASURY'; CORPORATE='CORPORATE'; MIXED='MIXED'
class Work4StaticRiskProfile(StrictModel):
    asset_id: str = Field(min_length=1)
    asset_credit_class: AssetCreditClassModel
    effective_duration_years: Decimal = Field(ge=0)
    source_lineage: list[str] = Field(min_length=1)
class ExistingPositionPolicyInput(StrictModel):
    current_position_quantity: Decimal = Field(ge=0)
    capital_gain_harvest_eligible: bool | None = None
    rebound_reduction_eligible: bool | None = None
    investment_logic_invalidated: bool | None = None
class Work4Step10Audit(StrictModel):
    asset_id: str = Field(min_length=1)
    contract_id: str
    step10_rule_ids: list[str]
    step10_direct_veto_rule_ids: list[str]
    step10_cap_rule_ids: list[str]
    step10_base_rule: str
