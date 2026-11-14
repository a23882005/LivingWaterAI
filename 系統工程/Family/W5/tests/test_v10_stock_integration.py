from copy import deepcopy
from decimal import Decimal
import sys
from family_input import digest
from test_native_adapters import ROOT
from test_stock_engine import stock_case,source_fields
from stock_engine import run_stock_engine,assemble_stock_output
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.approved_profiles import SPEC_SHA256
from livingwater_v82_runtime.daily_slice import open_cycle,speed,maturity


def adopted_case():
    req,facts,contract=stock_case();native_owner=req['work3_handoff']['owner']
    owner={**native_owner,'client_id':req['work3_handoff']['client_state_context']['payload']['client_id'],
        'currency':'USD','funding_domain':'US_DIRECT'}
    facts['core']['valuation_metrics'][0].update(metric_name='FORWARD_PE',current='10',historical_median='10')
    facts['core']['valuation_waterfall']=['FORWARD_PE']
    context={'schema_version':'V82.ApprovedDecisionContext.v1','spec_sha256':SPEC_SHA256,
        'native_owner':deepcopy(native_owner),
        'identity':{'client_id':owner['client_id'],'asset_id':'QQQ','run_id':facts['run_id'],
            'owner':owner,'snapshot_id':'SYNTHETIC_DB','evaluation_at':facts['evaluated_at']},
        'profile_id':'TECH_AI_HIGH_GROWTH_ETF','market_identity':{'listing':'SYNTHETIC_X','share_class':'SYNTHETIC'},
        'current_metric_value':'10','fundamentals_viable':'TRUE','left_price_conditions':{'reasonable_value':'TRUE'},
        'left_safety':'TRUE','off_low':'TRUE','credit_level':0,'credit_allows_right':'TRUE','core_etf':'TRUE','high_beta':'FALSE',
        'macro_pressure':'FALSE','right_valuation_condition':'TRUE','right_event_dependencies':[],
        'right_event_dependency_scope_verified':True,'stage_required_facts':{'asset_identity':'TRUE','primary_framework':'TRUE'},
        'stage_restrictions':[],'absolute_range_proof':None,'valuation_history':None,'price_history':None,
        'maturity_signals':[],'session':{'session_id':'2026-09-26','exchange':'NASDAQ','open_for_planning':True},
        'execution_costs':{'fee_reserve':'0','source_reference':'SYNTHETIC_EXPLICIT_ZERO_FEES'}}
    velocity=speed(mode='Right Confirmation',maturity_result=maturity([]),credit_level=0,
        core_etf='TRUE',high_beta='FALSE',macro_pressure='FALSE',extreme_valuation='OFF')
    cycle=open_cycle(owner=owner,session_id='2026-09-26',exchange='NASDAQ',asset_id='QQQ',
        opened_at=facts['evaluated_at'],gap='950',speed_result=velocity,permission=True,
        exposure_reconciled=True,session_open=True)
    context['cycle_snapshot']={'status':'VERIFIED','cycle':cycle}
    context['shared_allocation_request']={'owner':owner,'pool_id':'SYNTHETIC_POOL','remaining_tactical_room':'450',
        'slices':[{'owner':owner,'asset_id':'QQQ','bucket_id':'CASH','currency':'USD','slice':'237.5',
            'fx_to_bucket':'1','fx_bucket_to_budget':'1'}],
        'buckets':[{'owner':owner,'bucket_id':'CASH','currency':'USD','available_authorized_notional_cash':'1000',
            'funding_source_ids':['SYNTHETIC_ONE_CASH']} ]}
    facts['approved_v10_context']=context
    bind_context(facts,contract)
    return req,facts,contract


def bind_context(facts,contract):
    contract['parameters']['approved_v10_context_digest']=digest(facts['approved_v10_context'])
    facts['parameters']=deepcopy(contract['parameters'])


def test_same_native_core_full_right_stage_slice_funding_min_and_49_13_output():
    req,facts,contract=adopted_case();before=deepcopy((req,facts,contract))
    out=run_stock_engine(ROOT,req,facts,contract)
    assert out['deployment'].mode.value=='Right Confirmation' and out['deployment'].stage=='STAGE_8'
    assert out['position_gap'].target_amount==950 and out['position_gap'].final_deployment_gap_amount==950
    assert Decimal(out['daily_slice']['cap'])==Decimal('237.5')
    assert out['execution'].maximum_allowed_buy_amount==Decimal('237.5')
    assert out['execution'].execution_amount==230 and out['execution'].execution_quantity==23
    wire=assemble_stock_output(ROOT,out,source_fields())['canonical_v82_output']
    assert len(wire['canonical_analysis'])==49 and len(wire['fields_1_to_13'])==13
    assert (req,facts,contract)==before


def test_gate_preserves_full_right_stage_target_gap_but_new_buy_zero_and_left_false():
    req,facts,contract=adopted_case();facts['core']['hard_gate_predicates']=['TRUE']
    # Shared allocation is generated afresh from this known-zero native slice.
    facts['approved_v10_context']['shared_allocation_request']['slices'][0]['slice']='0';bind_context(facts,contract)
    out=run_stock_engine(ROOT,req,facts,contract)
    assert out['deployment'].stage=='STAGE_8' and out['position_gap'].final_deployment_gap_amount==950
    assert out['approved_v10_analysis']['right_entry']['truth']=='TRUE'
    assert out['approved_v10_analysis']['market_predicates']['left']=='FALSE'
    assert out['execution'].execution_amount==0 and out['daily_slice']['cap']=='0'


def test_missing_cycle_is_not_an_empty_ledger_or_a_full_maximum_slice():
    req,facts,contract=adopted_case();c=facts['approved_v10_context'];c['cycle_snapshot']=None;c['shared_allocation_request']=None
    bind_context(facts,contract);out=run_stock_engine(ROOT,req,facts,contract)
    assert out['deployment'].stage=='STAGE_8'
    assert out['execution'].execution_amount is None and out['daily_slice']['cap'] is None
    assert out['daily_slice']['status']=='CYCLE_LEDGER_SOURCE_UNAVAILABLE'
