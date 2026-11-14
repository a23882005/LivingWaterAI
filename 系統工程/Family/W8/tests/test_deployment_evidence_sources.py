"""Same-run evidence producers execute original components and retain gaps."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from family_input import digest
from deployment_evidence_sources import stock_sources
from deployment_context_sources import extend
from family_technical_bridge import bind_technical_source,apply_technical_source
from stock_engine import run_stock_engine
from native_funding_advice import plain
from test_deployment_context_sources import technical_case
from test_stock_engine import stock_case
from v75_native_attempt import normalized_evidence


def inputs(folder):
    request,report,prepared,sources=technical_case(folder)
    sources=extend(ROOT,request,report,prepared,sources)
    row=report['analysis_result']['positions'][0];_,facts,_=stock_case()
    row['scenario_class']={'formal_v82_class':'SYNTHETIC_CLASS'}
    row['core_observation']['actual_inputs']=deepcopy(facts['core'])
    row['current_analysis']['recommendation']['order_source']={'status':'VERIFIED','active_orders':[]}
    symbol=row['symbol'];equity=report['qualified_equity_inputs']['items'][symbol]
    technical=sources['trusted_context']['technical_source'];meta=technical['metadata']
    facts.update(asset_id=symbol,run_id=request['run_id'],evaluated_at=request['evaluation_at'],
        available_at=request['evaluation_at'],as_of=equity['session_close_at'],valuation_price=equity['rows'][-1]['Close'],
        exchange=meta['exchange'],currency=meta['currency'],timeframe=meta['timeframe'],adjustment=meta['provider_price_basis'])
    contract={k:facts[k] for k in ('producer','version','exchange','currency','timeframe','adjustment','parameters')}
    from livingwater_v82_runtime.canonical_output import CANONICAL_FIELD_NAMES
    from deployment_evidence_sources import CALCULATED
    bundle={**sources['native_bundle'],'stock_evidence':facts,'producer_contract':contract,
        'stock_source_fields':{k:'UNKNOWN' for k in CANONICAL_FIELD_NAMES if k not in CALCULATED}}
    probe=deepcopy(request);probe['native_bundle']=bundle;probe['technical_source_digest']=digest(technical)
    bound=bind_technical_source(ROOT,probe,{**sources['trusted_context'],'native_binding':sources['native_binding']})
    effective=apply_technical_source(bundle,bound)
    result=run_stock_engine(ROOT,effective['stock_request'],effective['stock_evidence'],effective['producer_contract'])
    row['core_observation']['actual_inputs']=deepcopy(effective['stock_evidence']['core'])
    row['core_observation']['result']=plain(result['core_state'])
    sources['component_results']={}
    return request,report,sources


def test_stock_sources_preserve_unknown_financials_and_do_not_claim_full_canonical(tmp_path):
    request,report,sources=inputs(tmp_path);before=deepcopy((request,report))
    stock_sources(ROOT,request,report,sources)
    bundle=sources['native_bundle'];result=sources['component_results']['stock']
    assert {'stock_evidence','producer_contract','stock_source_fields'}<=bundle.keys()
    assert bundle['stock_evidence']['core']==report['analysis_result']['positions'][0]['core_observation']['actual_inputs']
    assert bundle['stock_evidence']['risk_reduction_predicate']=='UNKNOWN'
    assert bundle['stock_evidence']['order_working_price'] is None
    assert bundle['stock_evidence']['required_known_caps']==[]  # No-new-money fixture has a verified zero cap.
    assert bundle['stock_source_fields']['primary_framework']=='UNKNOWN'
    assert sources['context_bindings']['stock_evidence']['full_native_canonical_complete'] is False
    assert result['trade_action']=='NO_TRADE' and (request,report)==before


def test_unverified_orders_cannot_be_silently_replaced_with_empty_exposure(tmp_path):
    request,report,sources=inputs(tmp_path)
    report['analysis_result']['positions'][0]['current_analysis']['recommendation']['order_source']={'status':'UNKNOWN'}
    stock_sources(ROOT,request,report,sources)
    assert 'stock_evidence' not in sources['native_bundle'] and sources['component_results']=={}


def test_changed_core_result_is_rejected_despite_same_source_label(tmp_path):
    request,report,sources=inputs(tmp_path)
    report['analysis_result']['positions'][0]['core_observation']['result']['permission']['new_buy_order_permission']='ALTERED'
    with pytest.raises(PermissionError,match='DEPLOYMENT_CORE_SOURCE_REPLAY_MISMATCH'):
        stock_sources(ROOT,request,report,sources)


def test_normalized_bond_evidence_is_produced_even_when_template_is_incompatible():
    source={'adapter_request':{'v75_source_context':{'market_snapshot':{'data_timestamp':'2026-10-27T22:00:00Z'},
        'target_bond_holdings':[{'asset_id':'SGOV'}],'existing_bond_holdings':[{'asset_id':'SGOV'}]}},
        'native_validation':{'accepted':True},'structural_state':{'work3_complete':False},
        'shared_inputs':{'work3_input':{'shared_decision_context':{'payload':{}}}},
        'predicate_observations':{'SGOV':{'PRED-007':{'input_freshness_verified':False,'metrics':{'sofr_ois_bps':'1'}}}},
        'physical_holdings':{'SGOV':{'quantity':'14','valuation':{'amount':'1400','currency':'USD'}}},
        'sgov_role_source':{'status':'SOURCE_DERIVED_ACCOUNTING','digest':'SYNTHETIC_ROLES','roles':{
            'sgov_bond_bucket_amount':{'amount':'0','currency':'USD'},
            'sgov_dry_powder_bucket_amount':{'amount':'1400','currency':'USD'}}}}
    request={'run_id':'SYNTHETIC','owner':{'account':'SYNTHETIC_ACCOUNT','currency':'USD'},
        'evaluation_at':'2026-10-29T04:00:00Z'}
    before=deepcopy(source);evidence,excluded=normalized_evidence(request,source)
    assert set(evidence['SGOV']['metrics'])=={'PRED-%03d'%n for n in range(1,11)}
    assert evidence['SGOV']['metrics']['PRED-007']=={} and 'PRED-007' in excluded['SGOV']
    policy=evidence['SGOV']['existing_policy']
    assert policy['current_position_quantity']=='0' and policy['investment_logic_invalidated'] is None
    assert 'effective_duration_years' not in evidence['SGOV'] and 'asset_credit_class' not in evidence['SGOV']
    assert source==before
