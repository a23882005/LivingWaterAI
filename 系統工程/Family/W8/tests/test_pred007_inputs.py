"""New USD source slots preserve partial coverage and leave TWD unchanged."""
from pathlib import Path
from copy import deepcopy
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from test_pred007_amendment import fixture,AT
from v75_pred007_inputs import extend
from v75_macro_inputs import slot
from v75_pred007_policy import BASE_VERSION,AMENDMENT_ID,RULESET_SHA256
from deployment_readiness import completion_gaps


def source_pool():
    return {'formal_parameters':{'parameter_version':BASE_VERSION},'available_at':'2026-10-29T09:07:00Z',
        'source_proofs':{'NYFED_REPO':{'source_reference':'SYNTHETIC_SRF_SOURCE','available_at':'2026-10-29T09:07:00Z'}},
        'calculations':{'PRED-007':{'observed_date':'2026-10-28'}},
        'shared_metrics':{'PRED-007':{'srf_usage_usd':'6000000'}},'asset_metrics':{},
        'unprovided_inputs':{'PRED-007':['sofr_ois_bps','fra_ois_bps','treasury_market_depth_percentile_3y']},
        'qualified_bond_markets':{
            'SGOV':{'currency':'USD','eligible':True,'observed_date':'2026-10-28'},
            'TW_BOND':{'currency':'TWD','eligible':True,'observed_date':'2026-10-28'}}}


def test_three_of_four_is_eligible_despite_missing_depth_and_old_snapshot_is_retained(tmp_path):
    source,_=fixture(tmp_path);pool=extend(source_pool(),source,AT);previous={'metrics':{'sofr_ois_bps':'20'}}
    row=slot(pool,'PRED-007','SGOV',previous,AT)
    assert row['deployment_input_eligible'] and row['original_result']['aggregate_state']=='NORMAL'
    assert row['amendment_assessment']['coverage_count']=='3/4' and row['unprovided_inputs']
    assert row['rule_identity']['amendment_id']==AMENDMENT_ID and row['rule_identity']['ruleset_sha256']==RULESET_SHA256
    assert row['previous_observation']==previous and 'sofr_ois_bps' not in row['metrics']
    assert row['original_result']['required_input_missing']==[]
    assert row['amendment_assessment']['missing_candidates'][0]['candidate']=='D'


def test_non_usd_retains_original_evaluator_and_does_not_consume_new_fields(tmp_path):
    source,_=fixture(tmp_path);pool=extend(source_pool(),source,AT)
    row=slot(pool,'PRED-007','TW_BOND',None,AT)
    assert row['metrics']=={'srf_usage_usd':'6000000'}
    assert 'amendment_assessment' not in row and row['original_result']['assessment_status']=='INSUFFICIENT_DATA'


def test_retired_spread_terms_never_reappear_as_waiting_for_owner_decision(tmp_path):
    source,_=fixture(tmp_path);pool=extend(source_pool(),source,AT)
    row=slot(pool,'PRED-007','SGOV',None,AT)
    report={'native_bond_source':{'predicate_observations':{'SGOV':{'PRED-007':row}}}}
    gaps=completion_gaps(report,['trusted_context.c7_source'])
    assert gaps['specification_undefined']==[]
    assert any('3/4' in r['reason'] and 'not a standalone blocker' in r['reason'] for r in gaps['data_not_acquired'])


def test_new_source_is_opt_in_for_historical_replays():
    pool=source_pool();before=deepcopy(pool)
    assert extend(pool,None,AT)==before
