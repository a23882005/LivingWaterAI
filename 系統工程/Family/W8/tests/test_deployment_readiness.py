"""C7's actual invariant diagnoses a boundary; it never replaces approval."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from deployment_readiness import c7_bucket_preflight,completion_gaps


def inputs(stock='0.8',bond='0.2',dry='0'):
    targets=[{'instrument_id':symbol,'ticker':symbol,'asset_type':kind,
        'weight':{'value_state':'KNOWN','value':weight}} for symbol,kind,weight in
        [('STOCK','equity exposure',stock),('SGOV','bond ETF',bond),('DRY','cash',dry)]]
    req={'client_id':'SYNTHETIC','run_id':'SYNTHETIC_RUN',
        'confirmed_target':{'payload':{'draft':{'target_lines':targets}}}}
    report={'analysis_result':{'positions':[{'symbol':'STOCK','native_product_identity':{},
        'current_analysis':{'v70_tactical_budget':{'allocation':{'sTot':70,'bTot':17.5,'cTot':12.5}}}}]}}
    return req,report


def test_actual_c7_bucket_mismatch_preserves_approval_and_does_not_emit_formal_source():
    req,report=inputs();before=deepcopy((req,report))
    result=c7_bucket_preflight(ROOT,req,report,{})
    assert result['status']=='ORIGINAL_BUCKET_MISMATCH'
    assert result['native_integrated_framework_state']=='NONE'
    assert all(i['code']=='C_W7_V70_FINAL_TARGET_BUCKET_MISMATCH' for i in result['native_issues'])
    assert [(r['work6_final_target_bucket_weight'],r['target_weight']) for r in result['bucket_comparison']]==[(.8,.7),(.2,.175),(0,.125)]
    assert not result['full_c7_source_produced'] and result['approval_unchanged']
    assert (req,report)==before


def test_compatible_bucket_math_does_not_imply_confirmed_work6_or_c7_readiness():
    req,report=inputs('.7','.175','.125')
    result=c7_bucket_preflight(ROOT,req,report,{})
    assert result['status']=='BUCKET_INVARIANT_PASSED' and result['native_issues']==[]
    assert result['full_c7_source_produced'] is False
    assert 'asset_framework' not in result


def test_generic_etf_type_cannot_be_silently_classified_as_equity():
    req,report=inputs();req['confirmed_target']['payload']['draft']['target_lines'][0]['asset_type']='ETF'
    result=c7_bucket_preflight(ROOT,req,report,{})
    assert result['mapping'][0]['bucket']=='UNKNOWN'
    assert 'C_W7_ASSET_BUCKET_UNKNOWN' in [r['code'] for r in result['native_issues']]


def test_remaining_issues_separate_undefined_terms_unobtained_data_and_engineering():
    report={'native_bond_source':{'predicate_observations':{
        'SGOV':{'PRED-007':{'original_result':{'assessment_status':'INSUFFICIENT_DATA'},'metrics':{'srf_usage_usd':'0'}},
            'PRED-008':{'original_result':{'assessment_status':'VALID'}}},
        'SPSB':{'PRED-007':{'original_result':{'assessment_status':'INSUFFICIENT_DATA'},'metrics':{}},
            'PRED-008':{'original_result':{'assessment_status':'INSUFFICIENT_DATA'}}}}},
        'v75_macro_inputs':{'etf_quality_assessments':{'SPSB':{'unprovided_inputs':[
            'trailing_12m_roc_pct_with_complete_issuer_breakdown','median_20d_bid_ask_spread_pct']}}}}
    result=completion_gaps(report,['trusted_context.c7_source','native_bundle.asset_framework'])
    assert {r['field'] for r in result['specification_undefined']} >= {'SOFR_OIS.comparison_tenor','FRA_OIS.forward_start_period'}
    fields=[r['field'] for r in result['data_not_acquired']]
    assert 'SPSB.PRED-008.five_year_weekly_YTM_or_SEC_yield' in fields
    assert not any('SGOV.PRED-008' in field for field in fields)
    assert len(result['engineering_not_connected'])==2
    assert all(r['owner_input_required'] is False for r in result['engineering_not_connected'])
    assert result['quality_missing_values_not_normalized_to_zero']
