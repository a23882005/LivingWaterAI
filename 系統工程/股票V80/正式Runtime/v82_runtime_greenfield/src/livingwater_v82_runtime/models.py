"""Canonical transport models for W5.

These dataclasses represent contract shapes only. They deliberately do not
perform W6 funding/account validation, W7 rule calculations, W8 order logic,
or W9 persistence.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Sequence
from .enums import AssetGrade, AssetType, CashBasis, DataQuality, FundingDomain, PortfolioRole

@dataclass(frozen=True, slots=True)
class ExecutionAccountRef:
    domain: FundingDomain
    broker: str
    account: str

@dataclass(frozen=True, slots=True)
class AssetIdentity:
    asset_id: str
    asset_type: AssetType
    asset_grade: AssetGrade
    portfolio_role: PortfolioRole

@dataclass(frozen=True, slots=True)
class ClientTarget:
    project_target_position: Any
    authorization_reference: str
    position_cap: Any = None

@dataclass(frozen=True, slots=True)
class V70TacticalBudgetEnvelope:
    run_id: str
    upstream_v70_snapshot_id: str
    v70_stock_tactical_budget_amount: Any
    v70_stock_tactical_budget_currency: str
    v70_stock_tactical_budget_status: Any
    v70_stock_tactical_budget_data_as_of: str
    v70_original_dry_powder_amount: Any
    v70_original_dry_powder_currency: str
    v70_budget_source_reference: Any
    v70_budget_data_quality: DataQuality
    v70_budget_issue_codes: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class C7FundingContextConsumer:
    contract_name: str
    contract_version: str
    run_id: str
    base_currency: str
    payload: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class BoundEquityBudgetView:
    domain: FundingDomain
    broker: str
    account: str
    amount: Decimal
    currency: str
    cash_basis: CashBasis
    source_contract: str
    source_reference_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class CanonicalMoneyObject:
    amount: Any
    currency: str
    source_reference: Any
    as_of: Any
    status: Any

@dataclass(frozen=True, slots=True)
class StructuredOrderPlan:
    should_place_order: Any
    order_type: Any
    limit_price: Any
    quantity: Any
    time_in_force: Any
    scheduling_mode: Any
    broker_or_adapter_constraints: Any
    order_intent_id: Any

@dataclass(frozen=True, slots=True)
class CanonicalFieldEnvelope:
    field_name: str
    value: Any
    data_type: str
    data_as_of: Any
    source_reference: Any
    data_quality: DataQuality
    issue_codes: tuple[str, ...]
    rule_version: str
    run_id: str

@dataclass(frozen=True, slots=True)
class ContractDiagnostic:
    code: str
    severity_or_category: str
    meaning: str
    source_lineage: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class V82RuntimeInput:
    contract_name: str
    contract_version: str
    run_id: str
    client_project_version: str
    asset: Mapping[str, Any]
    execution_account: Mapping[str, Any]
    client_target: Mapping[str, Any]
    upstream_v70_snapshot: Mapping[str, Any]
    c7_funding_context: Mapping[str, Any]
    confirmed_position_snapshot: Any
    source_lineage: tuple[str, ...]
    market_data_bundle: Mapping[str, Any] | None = None
    event_context: Mapping[str, Any] | None = None

@dataclass(frozen=True, slots=True)
class CanonicalAnalysis49:
    fields: Mapping[str, CanonicalFieldEnvelope]

@dataclass(frozen=True, slots=True)
class FormalExecutionView13:
    fields: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class V82RuntimeOutput:
    contract_name: str
    contract_version: str
    run_id: str
    v82_snapshot_id: str
    upstream_v70_snapshot_id: str
    asset_id: str
    rule_version: str
    data_as_of: Any
    evaluated_at: Any
    source_lineage: tuple[str, ...]
    output_status: Any
    canonical_analysis: Mapping[str, Any]
    fields_1_to_13: Mapping[str, Any]
