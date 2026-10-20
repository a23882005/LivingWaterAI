from copy import deepcopy
from decimal import Decimal
import pytest
from test_native_adapters import ROOT,request
from stock_engine import run_stock_engine,StockEvidenceError
from tactical_budget import TacticalBudgetError
import json
from test_native_adapters import FIXTURES
from stock_engine import assemble_stock_output
from output_bridge import normalize_stock


def source_fields():
    original=json.loads((FIXTURES/'work4_adapter_output.json').read_text())
    calculated={'latest_price','market_data_as_of','left_buy_point_state','primary_special_classification',
        'fundamental_state','valuation_state','right_confirmation_state','runaway_state',
        'project_target_position','confirmed_position','actual_completion_rate','normal_deployment_mode',
        'execution_action','canonical_deployment_target_rate','execution_amount','execution_quantity',
        'execution_price','projected_post_fill_completion_rate','order_submission_plan'}
    return {k:v['value'] for k,v in original['canonical_analysis'].items() if k not in calculated}


def stock_case():
    req=request(4)
    req['asset_context']['confirmed_position_snapshot']['quantity']=0
    contract={'producer':'W5_SYNTHETIC_TEST','version':'1','exchange':'NASDAQ','currency':'USD',
        'timeframe':'DAILY','adjustment':'SPLIT_ADJUSTED','parameters':{'source':'frozen-native-signals'}}
    facts={**contract,'asset_id':'QQQ','run_id':req['run_id'],'source_reference':'SYNTHETIC:QQQ',
        'evaluated_at':'2026-09-26T14:06:00+08:00','as_of':'2026-09-26T14:01:00+08:00',
        'available_at':'2026-09-26T14:02:00+08:00','price_field':'Close','sample_state':'COMPLETE',
        'swings':[],'left_buy_point':'FALSE','risk_reduction_predicate':'FALSE',
        'technical_reduction_predicate':'FALSE','active_orders':[],'valuation_price':'10',
        'order_working_price':'10','normalized_order_price':'10','minimum_lot':'1',
        'required_known_caps':['1000'],'order_intent_id':'SYNTHETIC-INTENT-001',
        'core':{'valuation_metrics':[{'metric_name':'PE','current':'20','historical_median':'20',
            'data_quality':'OK','freshness':'FRESH','pit_status':'VERIFIED'}],
            'valuation_waterfall':['PE'],'fundamental_fields':[{'field_name':'growth',
                'requirement_level':'MODULE_REQUIRED','field_value_state':'KNOWN','data_quality':'OK','direction':'IMPROVING'}],
            'safety_facts':[{'name':'macro','value':'OK','requirement':'SAFETY_REQUIRED','data_quality':'OK',
                'freshness':'FRESH','pit_status':'VERIFIED','source_reference':'SYNTHETIC:macro'}],
            'right_signals':['TRUE','TRUE','TRUE'],'up_price':['FALSE'],'up_confirm':['FALSE','FALSE','FALSE'],
            'down_break':['FALSE'],'down_accel':['FALSE','FALSE'],'hard_gate_predicates':['FALSE'],
            'theses':[{'state':'VALID','critical':False}],'structural_confirmation':'FALSE','ma20_ok':'TRUE'}}
    return req,facts,contract


def test_actual_stock_buy_is_limited_by_tactical_and_c7():
    req,facts,contract=stock_case();before=deepcopy((req,facts,contract))
    result=run_stock_engine(ROOT,req,facts,contract)
    assert result['status']=='BUY'
    assert result['execution'].execution_amount==Decimal('450')
    assert result['execution'].execution_quantity==Decimal('45')
    assert result['core_state'].valuation.level.value=='NORMAL'
    assert (req,facts,contract)==before
    req['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']='125'
    result=run_stock_engine(ROOT,req,facts,contract)
    assert result['execution'].execution_amount==Decimal('120')


@pytest.mark.parametrize('cause',['hard_gate','exceeds_cap','zero_budget','unknown_safety'])
def test_buy_restrictions_change_actual_native_result(cause):
    req,facts,contract=stock_case()
    if cause=='hard_gate': facts['core']['hard_gate_predicates']=['TRUE']
    if cause=='unknown_safety':facts['core']['safety_facts'][0]['data_quality']='UNKNOWN'
    if cause=='exceeds_cap':req['work3_handoff']['v70_runtime_context']['payload']['issue_codes']=['EXCEEDS_CAP']
    if cause=='zero_budget':req['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']='0'
    result=run_stock_engine(ROOT,req,facts,contract)
    assert result['status']=='NO_NEW_BUY'
    assert result['execution'].execution_amount==0


@pytest.mark.parametrize('field,value,reason',[
    ('price_field','Adj Close','CLOSE_REQUIRED'),('sample_state','MISSING','SAMPLE_INCOMPLETE'),
    ('asset_id','VT','EVIDENCE_IDENTITY'),('available_at','2026-09-27T00:00:00Z','FUTURE_EVIDENCE'),
    ('timeframe','WEEKLY','PRODUCER_CONTRACT_MISMATCH')])
def test_technical_evidence_boundaries(field,value,reason):
    req,facts,contract=stock_case();facts[field]=value
    with pytest.raises(StockEvidenceError,match=reason):run_stock_engine(ROOT,req,facts,contract)


def test_future_confirmed_swing_rejected():
    req,facts,contract=stock_case()
    facts['swings']=[{'asset_id':'QQQ','confirmed_at':'2026-09-27T00:00:00Z'}]
    with pytest.raises(StockEvidenceError,match='FUTURE_SWING'):run_stock_engine(ROOT,req,facts,contract)


def test_unknown_tactical_not_guessed_from_macro():
    req,facts,contract=stock_case()
    req['work3_handoff']['v70_runtime_context']['payload']['value_state']='UNKNOWN'
    with pytest.raises(TacticalBudgetError,match='TACTICAL_VALUE_NOT_KNOWN'):run_stock_engine(ROOT,req,facts,contract)


def test_real_stock_49_13_assembly_and_original_work9_mapping():
    req,facts,contract=stock_case()
    result=run_stock_engine(ROOT,req,facts,contract)
    integrated=assemble_stock_output(ROOT,result,source_fields())
    raw=integrated['canonical_v82_output']
    assert len(raw['canonical_analysis'])==49
    assert len(raw['fields_1_to_13'])==13
    view=normalize_stock(ROOT,integrated)
    assert view['canonical_action']=='BUY'
    assert view['execution_amount']['amount']==450
    assert view['execution_quantity']==45
    assert view['raw_output']==raw
    assert view['trade_action']=='NO_TRADE'


def test_unmapped_reduction_preserves_raw_risk_for_review():
    req,facts,contract=stock_case()
    integrated=assemble_stock_output(ROOT,run_stock_engine(ROOT,req,facts,contract),source_fields())
    integrated['canonical_v82_output']['canonical_analysis']['execution_action']['value']='REDUCE_RISK'
    view=normalize_stock(ROOT,integrated)
    assert view['canonical_action']=='NEEDS_REVIEW'
    assert view['source_action']=='REDUCE_RISK'


@pytest.mark.parametrize('case',['zero_budget','target_complete','hard_gate'])
def test_no_buy_canonical_preserves_zero_and_projection(case):
    req,facts,contract=stock_case()
    if case=='zero_budget':req['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']='0'
    if case=='target_complete':req['asset_context']['confirmed_position_snapshot']['quantity']=100
    if case=='hard_gate':facts['core']['hard_gate_predicates']=['TRUE']
    integrated=assemble_stock_output(ROOT,run_stock_engine(ROOT,req,facts,contract),source_fields())
    view=normalize_stock(ROOT,integrated)
    assert view['canonical_action']=='NO_ACTION'
    assert view['execution_amount']['amount']==0
    assert view['execution_quantity']==0
