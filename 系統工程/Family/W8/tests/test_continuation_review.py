from copy import deepcopy
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from family_input import digest
from runtime_loader import load_c_module
from mentor_bridge import explain_holdings_recommendations
from continuation_mentor import build as mentor
from deployment_blockers import build as blockers
from deployment_progress_review import build as progress
from family_runner import FamilyRunner


def case():
    owner={'client_id':'SYNTHETIC','funding_domain':'US_DIRECT','broker':'SYNTHETIC','account':'SYNTHETIC','currency':'USD'}
    request={'client_id':'SYNTHETIC','run_id':'SYNTHETIC-RUN','owner':owner,
        'evaluation_at':'2026-10-29T22:00:00Z','client_snapshot':{'payload':{'source_sha256':'0'*64}},
        'confirmed_target':{'synthetic':True}}
    identity={k:deepcopy(request[k]) for k in ('client_id','run_id','owner')};identity['source_db_sha256']='0'*64
    facts={'owner':owner,'symbol':'SYNTHETIC','holding':{'quantity':'1'},
        'current_judgment':{'mode':'UNKNOWN','stage_reference':'UNKNOWN'},
        'recommendation':{'buy_gap_amount':None,'target_rate':None,'cumulative_target_amount':None,
            'currency':'USD','missing_fields':['native_mode_and_stage_target_rate']}}
    facts['delivery_digest']=digest(facts)
    work9_request={'contract_name':'LivingWaterAI.C8C9.Work9.HoldingsRecommendationInput',
        'contract_version':'1.0',**identity,'positions':[{'instrument_id':'SYNTHETIC','native_component_delivery':facts}]}
    work9=load_c_module(ROOT,9).build_holdings_recommendation_return(work9_request)
    explained=explain_holdings_recommendations(ROOT,work9_request,work9,trusted_context={**identity,
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','expected_result_digest':digest(work9)})
    analysis={**identity,'work9_result':work9,'mentor':explained,
        'analysis_result':{'positions':[{'instrument_id':'SYNTHETIC','symbol':'SYNTHETIC','current_analysis':{},
            'formal_conclusion':{'selected_mode':'UNKNOWN','formal_stage':'UNKNOWN',
                'stage_required_unknown_fields':['fundamentals_long_term_viable'],
                'call_trace':['V82.select_deployment_mode']}}]},
        'native_funding_advice':{'items':{'SYNTHETIC':{'status':'FUNDING_BOUND','symbol':'SYNTHETIC',
            'issues':[{'code':'REQUIRED_SOURCE_UNAVAILABLE','field_path':'native_mode_and_stage_target_rate'}]}}}}
    analysis['report_digest']=digest(analysis)
    work6={'loop_status':'FINAL_TARGET_CONFIRMED','final_target_engine_result':{'issues':[
        {'code':'C_DATA_INSUFFICIENT','blocking':True,'field_path':'allocation.positions[0].ticker','message':'Missing benchmark asset'}]}}
    c7={'status':'RETURN_TO_V70','residual_allocation':{'buckets':[{'bucket':'STOCK',
        'target_weight':.525,'work6_final_target_bucket_weight':.62}]},'issues':[
        {'code':'C_W7_V70_FINAL_TARGET_BUCKET_MISMATCH','field_path':'asset_framework.STOCK','message':'Original mismatch'}]}
    return request,analysis,work6,c7


def test_original_work9_items_and_c7_cause_are_available_through_the_blocked_entry():
    req,a,w6,c7=case();before=deepcopy(a);out=progress(ROOT,req,a,w6,c7,[])
    view=out['mentor_review'];assert a==before
    assert view['items'][0]['recommendation']['recommended_buy_amount']['amount'] is None
    assert view['items'][0]['recommendation']['recommended_sell_amount']['amount'] is None
    assert view['blockers']['contract_reconfirmation'][0]['same_run_v70_weight']==.525
    assert not view['blockers']['contract_reconfirmation'][0]['external_NBBO_yield_ROC_dependency']
    result=FamilyRunner._error(req,'DATA_UNAVAILABLE',{'code':'C7_FRAMEWORK_NOT_READY',
        'configuration_review':{'mentor_review':view}})
    assert result['mentor'] is None and result['canonical_result'] is None
    assert result['mentor_review']==view and not result['formal_deployment_ready']
    assert not view['full_native_pipeline_complete'] and not view['broker_execution_allowed']


def test_native_selector_unknown_facts_are_not_mislabeled_as_a_missing_producer():
    req,a,w6,c7=case();out=blockers(a,w6,c7)
    row=out['native_decision_inputs'][0]
    assert row['native_selector_connected'] and row['category']=='ORIGINAL_NATIVE_INPUT_UNRESOLVED'
    assert row['required_unknown_fields']==['fundamentals_long_term_viable']
    assert out['configuration_engine_inputs'][0]['category']=='BENCHMARK_UNIVERSE_COVERAGE'
    assert out['contract_reconfirmation'][0]['v70_source_field'].endswith('stock_tactical_weight.value')


def test_market_data_shortages_only_mark_their_actual_consumers():
    req,a,w6,c7=case();out=blockers(a,w6,c7)
    gaps={r['id']:r for r in out['separate_market_data_gaps']}
    assert gaps['SPSB_FIVE_YEAR_WEEKLY_YIELDS']['affected_fields']==['SPSB.PRED-008']
    assert 'C7 bucket comparison' in gaps['SIP_NBBO_20_COMPLETE_SESSIONS']['unaffected']
    assert out['available_analysis_not_globally_blocked_by_data_gaps']


def test_changed_owner_or_advisory_amount_cannot_be_resigned_into_the_review():
    req,a,w6,c7=case();a['mentor']['owner']={**a['mentor']['owner'],'account':'OTHER'}
    with pytest.raises(PermissionError,match='SOURCE_IDENTITY'):mentor(req,a,w6,c7,blockers(a,w6,c7))
    req,a,w6,c7=case();a['mentor']['items'][0]['recommendation']['recommended_buy_amount']['amount']='100'
    with pytest.raises(PermissionError,match='FINANCIAL_MUTATION'):mentor(req,a,w6,c7,blockers(a,w6,c7))


def test_no_scoped_work9_source_does_not_create_a_mentor():
    req,a,w6,c7=case();a.pop('work9_result')
    assert mentor(req,a,w6,c7,blockers(a,w6,c7)) is None


def test_actual_v75_rule_wait_and_target_contracts_are_identified_without_overriding_them():
    req,a,w6,c7=case()
    a['native_bond_source']={'structural_state':{'evaluation_state':'INVALID_INPUT',
        'issues':[{'code':'US_GENERIC_CORE_TARGET_RATIO_MISMATCH','field':'target_bond_holdings'}]},
        'native_runtime_attempt':{'status':'INVALID_INPUT'},
        'predicate_observations':{'SPSB':{'PRED-008':{'input_freshness_verified':False,
            'metrics':{},'original_result':{'assessment_status':'INSUFFICIENT_DATA','aggregate_state':None}}}}}
    out=blockers(a,w6,c7,ROOT)['v75_original_contract']
    assert out['runtime_rule_version']=='債券V75.md v2.7.0'
    assert out['native_us_long_term_weights_percent']=={'SGOV':'70','SPSB':'30'}
    assert out['structural_issues'][0]['field']=='target_bond_holdings'
    assert all(r['line'] for r in out['original_contract_locations'])
    assert out['predicate_input_limitations'][0]['missing_or_unqualified_input_is_wait'] is False
    assert not out['undeployed_contribution_is_sgov_buy_authorization']
    assert not out['approved_target_overwritten']
