"""W9 canonical 49-field analysis and unique 13-field execution projection.

This module is an assembler/projection boundary only. It does not recompute
W6 funding, W7 core rules, or W8 deployment/order math.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping
from .enums import DataQuality
from .models import CanonicalAnalysis49, CanonicalFieldEnvelope, FormalExecutionView13, V82RuntimeOutput

CANONICAL_FIELD_NAMES = (
"latest_price","market_data_as_of","asset_behavior_classification","primary_framework","secondary_framework",
"fundamental_state","valuation_state","td9_high_state","td9_low_state","kd_state","macd_state","ma_state","emv_state","rsi_state","volume_price_state",
"daily_timeframe_state","weekly_timeframe_state","monthly_timeframe_state","atr_value","drawdown_from_reference_high","previous_swing_low_1","previous_swing_low_2","previous_swing_low_3",
"price_map","first_buy_zone","second_price_zone","deep_extreme_discount_zone","left_buy_point_state","right_confirmation_state","runaway_state","macro_state","credit_liquidity_state",
"material_news_policy_state","exposure_overlap","position_cap","project_target_position","confirmed_position","actual_completion_rate","normal_deployment_mode","primary_special_classification",
"execution_action","canonical_deployment_target_rate","execution_amount","execution_quantity","execution_price","projected_post_fill_completion_rate","order_submission_plan","cancel_conditions","reevaluation_conditions")

FORMAL_OUTPUT_NAMES=("今日特殊分類","目前部署階段","目標與完成率","今日動作","執行比例","執行金額","執行股數","執行價格","成交後完成率","是否掛單","掛單方式","取消條件","下一次重新評估條件")

class CanonicalAssemblyError(ValueError): pass

def _is_unknown_value(value: Any) -> bool:
    """True only for explicit UNKNOWN sentinels; never treats 0/False/empty as UNKNOWN."""
    raw = getattr(value, "value", value)
    return raw == "UNKNOWN"

def _value(x: Any) -> Any:
    return x.value if isinstance(x, CanonicalFieldEnvelope) else x

def assemble_canonical_analysis(*, values:Mapping[str,Any], run_id:str, rule_version:str,
    field_metadata:Mapping[str,Mapping[str,Any]]|None=None) -> CanonicalAnalysis49:
    if not run_id or not rule_version: raise CanonicalAssemblyError("RUN_ID_AND_RULE_VERSION_REQUIRED")
    expected=set(CANONICAL_FIELD_NAMES); got=set(values)
    if got != expected:
        missing=sorted(expected-got); extra=sorted(got-expected)
        raise CanonicalAssemblyError(f"V82E_49_FIELD_COUNT_MISMATCH missing={missing} extra={extra}")
    md=field_metadata or {}; out={}
    for name in CANONICAL_FIELD_NAMES:
        m=md.get(name,{})
        dq=m.get("data_quality",DataQuality.OK)
        if isinstance(dq,str):
            try: dq=DataQuality(dq)
            except ValueError: dq=DataQuality.UNKNOWN
        if dq is DataQuality.UNKNOWN and not _is_unknown_value(values[name]):
            raise CanonicalAssemblyError(f"V82E_UNKNOWN_COERCION field={name}")
        out[name]=CanonicalFieldEnvelope(name,values[name],str(m.get("data_type","CANONICAL")),m.get("data_as_of"),m.get("source_reference"),dq,tuple(m.get("issue_codes",())),rule_version,run_id)
    return CanonicalAnalysis49(out)

def project_formal_execution_view(analysis:CanonicalAnalysis49) -> FormalExecutionView13:
    f=analysis.fields
    if tuple(f.keys()) != CANONICAL_FIELD_NAMES: raise CanonicalAssemblyError("CANONICAL_49_ORDER_OR_SET_INVALID")
    order=_value(f["order_submission_plan"])
    order_keys=("should_place_order","order_type","limit_price","quantity","time_in_force","scheduling_mode","broker_or_adapter_constraints","order_intent_id")
    if isinstance(order,Mapping):
        if set(order) != set(order_keys):
            raise CanonicalAssemblyError("V82E_ORDER_PLAN_SHAPE_INVALID")
        should=order["should_place_order"]
        method={k:order.get(k) for k in ("order_type","time_in_force","scheduling_mode")}
        if should is True and (order.get("quantity") != _value(f["execution_quantity"]) or order.get("limit_price") != _value(f["execution_price"])):
            raise CanonicalAssemblyError("V82E_ORDER_PLAN_DUPLICATE_VALUE_CONFLICT")
    else:
        try:
            vals={k:getattr(order,k) for k in order_keys}
        except AttributeError as e:
            raise CanonicalAssemblyError("V82E_ORDER_PLAN_SHAPE_INVALID") from e
        should=vals["should_place_order"]
        method={k:vals[k] for k in ("order_type","time_in_force","scheduling_mode")}
        if should is True and (vals["quantity"] != _value(f["execution_quantity"]) or vals["limit_price"] != _value(f["execution_price"])):
            raise CanonicalAssemblyError("V82E_ORDER_PLAN_DUPLICATE_VALUE_CONFLICT")
    view={
      "今日特殊分類":_value(f["primary_special_classification"]),
      "目前部署階段":{"mode":_value(f["normal_deployment_mode"]),"execution_context":_value(f["execution_action"])},
      "目標與完成率":{"project_target_position":_value(f["project_target_position"]),"confirmed_position":_value(f["confirmed_position"]),"actual_completion_rate":_value(f["actual_completion_rate"])},
      "今日動作":_value(f["execution_action"]),"執行比例":_value(f["canonical_deployment_target_rate"]),"執行金額":_value(f["execution_amount"]),
      "執行股數":_value(f["execution_quantity"]),"執行價格":_value(f["execution_price"]),"成交後完成率":_value(f["projected_post_fill_completion_rate"]),
      "是否掛單":should,"掛單方式":method,"取消條件":_value(f["cancel_conditions"]),"下一次重新評估條件":_value(f["reevaluation_conditions"])}
    if tuple(view.keys()) != FORMAL_OUTPUT_NAMES: raise AssertionError("FORMAL_13_MAPPING_DRIFT")
    return FormalExecutionView13(view)

def validate_formal_view_against_analysis(analysis:CanonicalAnalysis49, view:Mapping[str,Any]) -> None:
    """Fail closed if a transported 13-field view drifts from the canonical projection."""
    expected=project_formal_execution_view(analysis).fields
    if dict(view) != dict(expected):
        raise CanonicalAssemblyError("V82E_13_VIEW_MAPPING_CONFLICT")

def validate_run_lineage(*, run_id:str, upstream_v70_run_id:str, c7_funding_run_id:str) -> None:
    if not run_id or upstream_v70_run_id != run_id or c7_funding_run_id != run_id:
        raise CanonicalAssemblyError("V82E_RUN_ID_MISMATCH")

def build_runtime_output(*, analysis:CanonicalAnalysis49, run_id:str, v82_snapshot_id:str, upstream_v70_snapshot_id:str,
    asset_id:str, rule_version:str, contract_name:str, contract_version:str, data_as_of:Any, evaluated_at:Any,
    source_lineage:tuple[str,...], output_status:Any) -> V82RuntimeOutput:
    if not all((run_id,v82_snapshot_id,upstream_v70_snapshot_id,asset_id,rule_version,contract_name,contract_version)):
        raise CanonicalAssemblyError("OUTPUT_IDENTITY_OR_LINEAGE_REQUIRED")
    for env in analysis.fields.values():
        if env.run_id != run_id or env.rule_version != rule_version: raise CanonicalAssemblyError("CANONICAL_LINEAGE_MISMATCH")
    view=project_formal_execution_view(analysis)
    return V82RuntimeOutput(contract_name,contract_version,run_id,v82_snapshot_id,upstream_v70_snapshot_id,asset_id,rule_version,data_as_of,evaluated_at,tuple(source_lineage),output_status,analysis.fields,view.fields)
