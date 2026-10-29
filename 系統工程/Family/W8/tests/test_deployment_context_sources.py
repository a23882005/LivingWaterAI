"""Existing source contexts pass original bindings; absent sources stay absent."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from deployment_context_sources import extend
from deployment_component_sources import collect
from on_demand_analysis import assemble_native_input,NativeSourceAssemblyError
from runtime_loader import load_c_module
from test_deployment_component_sources import case


def inputs():
    request,report=case();request['expected_versions']['funding']='SYNTHETIC_FUNDING_VERSION'
    prepared=SimpleNamespace(payload={'positions':[{
        'instrument_key':'SYNTHETIC_QQQ','quantity':'5',
        'source_instrument':{'instrument_key':'SYNTHETIC_QQQ','ticker':'QQQ'}}]})
    return request,report,prepared,collect(ROOT,request,report,'QQQ')


def test_known_v70_cash_and_position_keys_are_reused_without_deployment_qualification():
    request,report,prepared,sources=inputs();before=deepcopy((request,report,prepared.payload,sources))
    result=extend(ROOT,request,report,prepared,sources)
    assert result['source_validation_issues']==[]
    assert result['context_call_trace']==[
        'W5.bind_v70_source:reused_verified_shared_context',
        'C8C9.Work6.validate_funding_account_isolation:context_replay',
        'W5.bind_funding_source:reused_verified_cash_trial','W8.map_prepared_stock_instrument']
    assert set(result['trusted_context'])=={'funding_source','v70_source'}
    bundle=sources['native_bundle'];stock=bundle['stock_request']
    assert result['native_bundle']==bundle
    v70=result['trusted_context']['v70_source']
    assert v70['context']==stock['work3_handoff']['v70_runtime_context']
    funding=result['trusted_context']['funding_source']
    assert funding['c7_funding_context']==stock['c7_funding_context']
    assert funding['owner_binding']['family_owner']==request['owner']
    assert funding['owner_binding']['version']=='SYNTHETIC_FUNDING_VERSION'
    assert result['context_bindings']['funding_source']['external_funding_event_attested'] is False
    assert result['context_bindings']['funding_source']['status']=='ORIGINAL_SOURCE_AND_WORK6_ISOLATION_PASSED'
    mapping=result['native_binding']['stock_instrument']
    assert mapping['instrument_key']=='SYNTHETIC_QQQ' and mapping['asset_id']=='QQQ'
    assert result['context_bindings']['stock_instrument']['exchange_or_canonical_price_qualification_asserted'] is False
    assert (request,report,prepared.payload,sources)==before
    with pytest.raises(NativeSourceAssemblyError) as caught:assemble_native_input(request,{},result)
    assert len(caught.value.missing)==9
    assert set(caught.value.missing)=={
        'native_bundle.stock_evidence','native_bundle.producer_contract','native_bundle.stock_source_fields',
        'native_bundle.bond_evidence','native_bundle.asset_framework','trusted_context.valuation_source',
        'trusted_context.c7_source','trusted_context.technical_source','native_binding.bond_instruments'}


def test_missing_funding_version_stays_missing_without_an_invented_source_version():
    request,report,prepared,sources=inputs();request['expected_versions'].pop('funding')
    result=extend(ROOT,request,report,prepared,sources)
    assert 'funding_source' not in result['trusted_context']
    assert result['source_validation_issues'][0]['code']=='FUNDING_EXPECTED_VERSION_REQUIRED'
    assert result['trusted_context']['v70_source']


def test_unknown_v70_amount_is_not_replaced_by_the_zero_cash_trial():
    request,report,prepared,sources=inputs()
    for key in ('stock_request','bond_request'):
        sources['native_bundle'][key]['work3_handoff']['v70_runtime_context']['payload']['value_state']='UNKNOWN'
    sources['native_bundle']['bond_request']['v75_source_context']['v70_snapshot']['payload']['value_state']='UNKNOWN'
    result=extend(ROOT,request,report,prepared,sources)
    assert 'v70_source' not in result['trusted_context']
    assert result['source_validation_issues'][0]['code']=='TACTICAL_VALUE_NOT_KNOWN'
    assert sources['native_bundle']['stock_request']['work3_handoff']['v70_runtime_context']['payload']['value_state']=='UNKNOWN'


def test_original_work6_rejection_keeps_funding_context_unbound(monkeypatch):
    import deployment_context_sources as M
    request,report,prepared,sources=inputs();w6=load_c_module(ROOT,6)
    def rejected(_):raise ValueError('SYNTHETIC_CASH_REJECTION')
    monkeypatch.setattr(w6,'validate_funding_account_isolation',rejected)
    monkeypatch.setattr(M,'load_c_module',lambda root,n:w6 if n==6 else load_c_module(root,n))
    result=extend(ROOT,request,report,prepared,sources)
    assert 'funding_source' not in result['trusted_context']
    assert result['source_validation_issues'][0]['source_section']=='trusted_context.funding_source'
    assert 'SYNTHETIC_CASH_REJECTION' in result['source_validation_issues'][0]['message']


@pytest.mark.parametrize('kind',['analysis_owner','native_owner'])
def test_foreign_analysis_or_native_account_cannot_supply_contexts(kind):
    request,report,prepared,sources=inputs()
    if kind=='analysis_owner':report['owner']['account']='OTHER'
    else:sources['native_bundle']['stock_request']['work3_handoff']['owner']['account']='OTHER'
    with pytest.raises(PermissionError,match='DEPLOYMENT_CONTEXT_'):
        extend(ROOT,request,report,prepared,sources)


@pytest.mark.parametrize('kind',['quantity','instrument_key'])
def test_position_binding_preserves_prepared_identity_and_exact_quantity(kind):
    request,report,prepared,sources=inputs();position=prepared.payload['positions'][0]
    position[kind]='999' if kind=='quantity' else 'OTHER'
    with pytest.raises(PermissionError,match='DEPLOYMENT_STOCK_POSITION_MAPPING_MISMATCH'):
        extend(ROOT,request,report,prepared,sources)
