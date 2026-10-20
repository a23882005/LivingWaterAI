"""Execute frozen V82 core and deployment functions from explicit evidence.

This component stops at native calculation results. Canonical 49/13 projection
and the Family runner are separate integration boundaries.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys
import json
from family_input import digest
from runtime_loader import load_c_module
from tactical_budget import tactical_cap

V82_PATH=Path('系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src')


class StockEvidenceError(ValueError):
    pass


def _time(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise StockEvidenceError('TIMEZONE_REQUIRED')
    return d


def run_stock_engine(repo_path, adapter_request, evidence, producer_contract):
    """producer_contract is trusted dispatch configuration, never request input."""
    req,facts=deepcopy(adapter_request),deepcopy(evidence)
    source=Path(repo_path).resolve()/V82_PATH
    if str(source) not in sys.path: sys.path.insert(0,str(source))
    import livingwater_v82_runtime as native
    if Path(native.__file__).resolve().parent != source/'livingwater_v82_runtime':
        raise StockEvidenceError('RUNTIME_SOURCE_MISMATCH')
    from livingwater_v82_runtime.core_rules import EvidenceFact,evaluate_core_rule_state
    from livingwater_v82_runtime.enums import PredicateTruth,RequirementLevel,DataQuality,Freshness,PitStatus,OrderLifecycleState
    from livingwater_v82_runtime.deployment import (select_deployment_mode,resolve_deployment_stage,
        calculate_position_gap,build_buy_execution_plan,ActiveOrderExposure)
    adapter=load_c_module(repo_path,4)
    built=adapter.build_v82_runtime_input(req)
    wire=built['v82_runtime_input']; binding=built['integration_binding']
    funded=native.validate_and_bind_funding(wire)
    cap=tactical_cap(req['work3_handoff'],'equity')
    for key in ('producer','version','exchange','currency','timeframe','adjustment','parameters'):
        if key not in producer_contract or facts.get(key)!=producer_contract[key]:
            raise StockEvidenceError('PRODUCER_CONTRACT_MISMATCH:'+key)
    if not facts.get('source_reference') or facts.get('asset_id')!=binding['asset_id'] or facts.get('run_id')!=binding['run_id']:
        raise StockEvidenceError('EVIDENCE_IDENTITY')
    if facts['currency']!=binding['currency']: raise StockEvidenceError('CURRENCY_MISMATCH')
    now=_time(facts['evaluated_at']); observed=_time(facts['as_of']); available=_time(facts['available_at'])
    if observed>available or available>now: raise StockEvidenceError('FUTURE_EVIDENCE')
    if facts.get('price_field')!='Close': raise StockEvidenceError('CLOSE_REQUIRED')
    if facts.get('sample_state')!='COMPLETE': raise StockEvidenceError('SAMPLE_INCOMPLETE')
    for swing in facts['swings']:
        if swing['asset_id']!=binding['asset_id']: raise StockEvidenceError('SWING_ASSET_MISMATCH')
        if _time(swing['confirmed_at'])>now: raise StockEvidenceError('FUTURE_SWING')
    core=deepcopy(facts['core'])
    if not core['safety_facts'] or not core['hard_gate_predicates']:
        raise StockEvidenceError('SAFETY_EVIDENCE_REQUIRED')
    core['safety_facts']=[EvidenceFact(**{**f,'requirement':RequirementLevel(f['requirement']),
        'data_quality':DataQuality(f['data_quality']),'freshness':Freshness(f['freshness']),
        'pit_status':PitStatus(f['pit_status'])}) for f in core['safety_facts']]
    for key in ('right_signals','up_price','up_confirm','down_break','down_accel','hard_gate_predicates'):
        if not core[key]: raise StockEvidenceError('SIGNAL_EVIDENCE_REQUIRED:'+key)
        core[key]=[PredicateTruth(x) for x in core[key]]
    for key in ('structural_confirmation','ma20_ok'):core[key]=PredicateTruth(core[key])
    state=evaluate_core_rule_state(**core)
    mode=select_deployment_mode(runaway_up=state.technical.runaway_up,
        right_add=state.technical.right_confirmation,left_buy_point=PredicateTruth(facts['left_buy_point']))
    stage=resolve_deployment_stage(mode=mode,left_stage=facts.get('left_stage'),trend_stage=facts.get('trend_stage'))
    trace=['C8C9.Work4.build_v82_runtime_input','V82.validate_and_bind_funding','W5.tactical_cap',
           'V82.evaluate_core_rule_state','V82.select_deployment_mode','V82.resolve_deployment_stage']
    result={'input_digest':digest({'request':req,'evidence':facts,'producer_contract':producer_contract}),
        'built_input':built,'core_state':state,'deployment':stage,'tactical_cap':cap,'call_trace':trace,
        'evidence':facts,
        'production':'HOLD','trade_action':'NO_TRADE'}
    if stage.target_rate is None:
        return {**result,'status':'INSUFFICIENT_DATA','execution':None}
    orders=[ActiveOrderExposure(**{**o,'state':OrderLifecycleState(o['state']),
        'order_qty':Decimal(str(o['order_qty'])),'confirmed_filled_qty':Decimal(str(o['confirmed_filled_qty']))})
        for o in facts['active_orders']]
    gap=calculate_position_gap(project_target_position_amount=wire['client_target']['project_target_position'],
        target_rate=stage.target_rate,confirmed_position_qty=wire['confirmed_position_snapshot']['quantity'],
        canonical_valuation_price=facts['valuation_price'],active_orders=orders)
    plan=build_buy_execution_plan(gap=gap,permission=state.permission,
        bound_equity_budget=funded.bound_equity_budget,order_working_price=facts['order_working_price'],
        minimum_lot=facts['minimum_lot'],required_known_caps=[cap['amount'],*facts['required_known_caps']],
        normalized_order_price=facts['normalized_order_price'],execution_currency=binding['currency'],
        order_intent_id=facts['order_intent_id'])
    trace.extend(['V82.calculate_position_gap','V82.build_buy_execution_plan'])
    return {**result,'status':plan.action,'position_gap':gap,'execution':plan}


def assemble_stock_output(repo_path, calculation, source_fields, c7_computation=None):
    """Use the native 49/13 assembler; display fields remain producer-owned."""
    from livingwater_v82_runtime.canonical_output import (CANONICAL_FIELD_NAMES,
        assemble_canonical_analysis,build_runtime_output)
    from livingwater_v82_runtime.core_rules import arbitrate_primary_special_classification
    from livingwater_v82_runtime.enums import PredicateTruth
    if calculation.get('execution') is None:
        raise StockEvidenceError('NATIVE_EXECUTION_UNRESOLVED')
    adapter=load_c_module(repo_path,4)
    wire=calculation['built_input']['v82_runtime_input']; binding=calculation['built_input']['integration_binding']
    core,stage,gap,plan=(calculation[k] for k in ('core_state','deployment','position_gap','execution'))
    facts=calculation['evidence']
    def money(amount):
        return {'amount':amount,'currency':binding['currency'],'source_reference':facts['source_reference'],
                'as_of':facts['as_of'],'status':'KNOWN'}
    order=asdict(plan.order_plan)
    if order['should_place_order'] is not True and order['should_place_order'] is not False:
        raise StockEvidenceError('NATIVE_ORDER_PLAN_UNRESOLVED')
    order['limit_price']=money(plan.execution_price) if plan.execution_price is not None else None
    for key in ('order_type','time_in_force','scheduling_mode'):
        if order[key] is None:order[key]='NONE'
    # Percent conversion is an explicit wire-unit conversion (fraction to %).
    # All monetary/quantity decisions are copied directly from native outputs.
    special=arbitrate_primary_special_classification({
        'TRUE_RISK_REDUCTION':PredicateTruth(facts['risk_reduction_predicate']),
        'TECHNICAL_REDUCTION':PredicateTruth(facts['technical_reduction_predicate']),
        'RUNAWAY_DOWN':core.technical.runaway_down,'RUNAWAY_UP':core.technical.runaway_up,
        'RIGHT_ADD':core.technical.right_confirmation,'LEFT_BUY_POINT':PredicateTruth(facts['left_buy_point'])})
    computed={'latest_price':money(Decimal(str(facts['valuation_price']))),'market_data_as_of':facts['as_of'],
        'left_buy_point_state':facts['left_buy_point'],'primary_special_classification':special,
        'fundamental_state':core.fundamentals.context.value,'valuation_state':core.valuation.level.value,
        'right_confirmation_state':core.technical.right_confirmation.value,
        'runaway_state':{'up':core.technical.runaway_up.value,'down':core.technical.runaway_down.value},
        'project_target_position':gap.project_target_position_amount,'confirmed_position':gap.confirmed_amount,
        'actual_completion_rate':gap.actual_completion_rate if gap.actual_completion_rate is not None else 'UNKNOWN','normal_deployment_mode':stage.mode.value,
        'execution_action':plan.action,'canonical_deployment_target_rate':stage.target_rate*100,
        'execution_amount':('UNKNOWN' if plan.execution_amount is None else
            money(plan.execution_amount)),
        'execution_quantity':plan.execution_quantity,'execution_price':order['limit_price'],
        'projected_post_fill_completion_rate':plan.projected_post_fill_completion_rate if plan.projected_post_fill_completion_rate is not None else 'UNKNOWN',
        'order_submission_plan':order}
    if set(source_fields)!=set(CANONICAL_FIELD_NAMES)-set(computed):
        raise StockEvidenceError('CANONICAL_SOURCE_FIELDS_MISMATCH')
    target_projection=None
    if c7_computation is not None:
        from target_units import project_target_units
        target_projection=project_target_units(calculation,c7_computation)
        computed['project_target_position']=target_projection['canonical_target_weight']
    values={**deepcopy(source_fields),**computed}
    schema=json.loads((Path(repo_path)/V82_PATH/'livingwater_v82_runtime/schema/runtime_output.schema.json').read_text())
    metadata={name:{'data_type':schema['properties']['canonical_analysis']['properties'][name]['properties']['data_type']['const'],
        'data_as_of':facts['as_of'],'source_reference':facts['source_reference'],
        'data_quality':'UNKNOWN' if value=='UNKNOWN' else 'OK',
        'issue_codes':list(plan.reason_codes)} for name,value in values.items()}
    if target_projection is not None:
        metadata['project_target_position'].update(
            data_as_of=target_projection['source_target']['weight']['as_of'],
            source_reference=['C7:'+target_projection['c7_snapshot_id'],
                              'UNIT:portfolio_weight','SOURCE_SHA256:'+target_projection['source_digest']])
    analysis=assemble_canonical_analysis(values=values,run_id=wire['run_id'],
        rule_version=adapter.V82_RULE_VERSION,field_metadata=metadata)
    output=build_runtime_output(analysis=analysis,run_id=wire['run_id'],
        v82_snapshot_id='W5-V82-'+calculation['input_digest'],
        upstream_v70_snapshot_id=binding['upstream_v70_snapshot_id'],asset_id=binding['asset_id'],
        rule_version=adapter.V82_RULE_VERSION,contract_name=adapter.V82_OUTPUT_NAME,
        contract_version=adapter.V82_OUTPUT_VERSION,data_as_of={'technical':facts['as_of'],'shared':wire['market_data_bundle']['data_as_of']},evaluated_at=facts['evaluated_at'],
        source_lineage=tuple([*wire['source_lineage'],facts['source_reference']]),
        output_status='UNKNOWN' if plan.action=='BLOCKED_UNKNOWN' else 'OK')
    return adapter.consume_v82_runtime_output(output,binding)
