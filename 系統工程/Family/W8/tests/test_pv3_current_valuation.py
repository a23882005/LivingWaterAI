"""Synthetic PV3 current-Primary qualification, independent of comparison history."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests'),str(HERE/'tests')]
from formal_mode_analysis import native
native(ROOT)
from livingwater_v82_runtime.core_rules import resolve_valuation
from livingwater_v82_runtime.approved_decision import evaluate
from livingwater_v82_runtime.approved_profiles import left_profile,resolve_approved_stage,absolute_range
from test_v10_stock_integration import adopted_case
from stock_engine import run_stock_engine,_plain
import test_v82_core_source as core_fixture


def pb(**changes):
    return {'metric_name':'PB','current':'3.4','historical_median':None,
        'unit':'multiple','source_reference':'SYNTHETIC_PB_CURRENT_SOURCE',
        'data_quality':'OK','freshness':'FRESH','pit_status':'VERIFIED',**changes}


def context_and_core(metric):
    request,facts,contract=adopted_case()
    core=_plain(run_stock_engine(ROOT,request,facts,contract)['core_state'])
    core['valuation']=_plain(resolve_valuation([metric],['PB']))
    core['technical'].update(runaway_up='FALSE',right_confirmation='FALSE',runaway_down='FALSE')
    context=deepcopy(facts['approved_v10_context'])
    context.update(current_metric_value=metric.get('current'),left_price_conditions={'SYNTHETIC_PRICE_LEAF':'TRUE'},
        valuation_history=None,price_history=None)
    return context,core


def test_current_pb_without_history_makes_B2_true_without_completing_report_or_higher_stages():
    metric=pb();before=deepcopy(metric);context,core=context_and_core(metric)
    result=evaluate(context,core)
    assert metric==before
    assert core['valuation']['current_primary_eligible'] is True
    assert core['valuation']['level']=='UNKNOWN' and core['valuation']['formal_output_eligible'] is False
    assert result['current_primary_qualification']['truth']=='TRUE'
    assert result['left_stage_profile']['eligible']['2']=='TRUE'
    assert result['left_stage_profile']['eligible']['3']=='UNKNOWN'
    assert result['left_stage_profile']['known_lower_bound']==2
    assert result['left_stage_profile']['possible_upper_bound']==7
    assert result['formal_stage']=='UNKNOWN' and result['canonical_target_rate'] is None
    assert result['qV']['status']!='COMPLETE' and result['qP']['status']!='COMPLETE'
    assert 'valuation_legal' not in result['stage_audit']['required_unknown_fields']


def test_proven_false_higher_price_depth_leaves_stage2_without_inventing_qP_qV():
    context,core=context_and_core(pb());result=evaluate(context,core)
    profile=left_profile(price_entry='TRUE',valuation_legal=result['current_primary_qualification']['truth'],
        depth='0',q_price=None,q_value=None,metric='PB',current='3.4',range_result=result['range_result'])
    decision,_=resolve_approved_stage(mode=result['selected_mode'],left_result=profile,q_value=None,
        range_result=result['range_result'],required_facts={'asset_identity':'TRUE','primary_framework':'TRUE',
            'fundamentals_viable':'TRUE','valuation_legal':'TRUE'},restrictions=[],snapshot_id='SYNTHETIC_DB')
    assert decision.stage=='STAGE_2' and decision.target_rate==Decimal('.20')
    assert all(profile['eligible'][str(i)]=='FALSE' for i in range(3,8))


@pytest.mark.parametrize('change',[
    {'freshness':'STALE'},{'freshness':'UNKNOWN'},{'pit_status':'UNVERIFIABLE'},
    {'data_quality':'UNKNOWN'},{'metric_name':'TRAILING_PE'},
    {'current':None},{'current':'NaN'},{'current':'Infinity'},{'current':True},
    {'current':'-3.4'},{'current':'0'}])
def test_stale_wrong_method_missing_or_invalid_current_input_does_not_qualify_B2(change):
    context,core=context_and_core(pb(**change));result=evaluate(context,core)
    assert core['valuation']['current_primary_eligible'] is False
    assert result['current_primary_qualification']['truth']=='UNKNOWN'
    assert result['left_stage_profile']['eligible']['2']=='UNKNOWN'
    assert result['formal_stage']=='UNKNOWN'


def test_context_cannot_promote_or_change_actual_current_primary():
    context,core=context_and_core(pb());context['current_metric_value']='34'
    context['current_primary_eligible']=True
    assert evaluate(context,core)['left_stage_profile']['eligible']['2']=='UNKNOWN'
    del core['valuation']['current_primary_eligible']
    context['current_metric_value']='3.4'
    assert evaluate(context,core)['left_stage_profile']['eligible']['2']=='UNKNOWN'


def test_current_qualification_does_not_clear_fundamental_safety_or_false_price():
    context,core=context_and_core(pb());context['fundamentals_viable']='UNKNOWN'
    result=evaluate(context,core)
    assert result['left_stage_profile']['eligible']['2']=='TRUE'
    assert result['left_inputs']['fundamentals_long_term_viable']=='UNKNOWN'
    assert result['formal_stage']=='UNKNOWN'
    context['left_safety']='FALSE'
    assert evaluate(context,core)['market_predicates']['left']=='FALSE'
    context['left_price_conditions']={'SYNTHETIC_FALSE_PRICE':'FALSE'}
    assert evaluate(context,core)['left_stage_profile']['eligible']['2']=='FALSE'


def test_original_report_result_and_fallback_order_are_preserved():
    result=resolve_valuation([pb(historical_median='4')],['PB'])
    assert result.level.value=='NORMAL' and result.formal_output_eligible is True
    result=resolve_valuation([pb(),pb(metric_name='FORWARD_PE',freshness='STALE')],['FORWARD_PE','PB'])
    assert result.primary_metric=='PB' and result.fallback_used and result.current_primary_eligible
    assert not result.formal_output_eligible
    # A chosen current Primary is retained even when a later candidate has a
    # historical comparison. Missing history is not a waterfall fallback.
    result=resolve_valuation([pb(),pb(metric_name='FCF_YIELD',historical_median='4')],['PB','FCF_YIELD'])
    assert result.primary_metric=='PB' and not result.fallback_used


def test_qualified_yield_keeps_its_original_sign_and_comparison_remains_unknown():
    metric=pb(metric_name='FCF_YIELD',current='-1.2',unit='%')
    result=resolve_valuation([metric],['FCF_YIELD'])
    assert result.current_primary_eligible and result.current_primary_value==Decimal('-1.2')
    assert result.level.value=='UNKNOWN' and not result.formal_output_eligible
    assert metric['current']=='-1.2'


@pytest.mark.parametrize('bad',['wrong_asset','expired','missing_proof','missing_methodology','missing_unit','changed_value_proof'])
def test_original_source_reader_rejects_bad_current_source_before_PV3(bad):
    f=core_fixture.CoreSourceTests();f.setUp()
    try:
        metric=pb(source_reference=f.proof['source_reference'],source_sha256=f.proof['sha256'],as_of=f.proof['as_of'])
        f.leaf('valuation_metrics',[metric])
        if bad=='wrong_asset':f.data['asset_id']='OTHER'
        elif bad=='expired':f.data['leaves']['valuation_metrics']['proof']['valid_until']='2026-10-30T00:02:00Z'
        elif bad=='missing_proof':f.data['leaves']['valuation_metrics']['proof']={}
        elif bad=='missing_methodology':f.data['leaves']['valuation_metrics']['proof']['methodology_reference']=None
        elif bad=='missing_unit':metric['unit']=None
        else:metric['source_sha256']='b'*64
        with pytest.raises((ValueError,PermissionError,KeyError)):f.source()
    finally:f.doCleanups()


def test_original_qualified_reader_to_native_Core_retains_current_pb_without_history():
    f=core_fixture.CoreSourceTests();f.setUp()
    try:
        f.leaf('valuation_metrics',[pb(source_reference=f.proof['source_reference'],
            source_sha256=f.proof['sha256'],as_of=f.proof['as_of'])])
        out=f.evaluate(f.source());valuation=out['result']['valuation']
        assert valuation['current_primary_eligible'] is True and valuation['current_primary_value']=='3.4'
        assert valuation['level']=='UNKNOWN' and valuation['formal_output_eligible'] is False
        assert out['result']['permission']['new_buy_order_permission'] is False
    finally:f.doCleanups()
