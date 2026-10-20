from copy import deepcopy
import json
import pytest
from test_native_adapters import ROOT,FIXTURES,request
from test_stock_engine import stock_case,source_fields
from test_bond_engine import evidence
from test_sgov_bridge import case
from native_pipeline import run_native_pipeline,PipelineError


def pipeline_case():
    stock,facts,contract=stock_case();bond=request(5)
    stock.update(run_id=bond['run_id'],work3_handoff=deepcopy(bond['work3_handoff']),
                 c7_funding_context=deepcopy(bond['c7_funding_context']))
    facts['run_id']=bond['run_id']
    template=json.loads((FIXTURES/'work8_protected_request.json').read_text())['c_work7_asset_framework_result']
    # Explicit synthetic fixture adaptation; never used to manufacture client targets.
    template=json.loads(json.dumps(template).replace('TSM.US','QQQ'))
    w3=bond['work3_handoff']
    template['identity']['run_id']=bond['run_id']
    template['identity']['client_id']=w3['client_state_context']['payload']['client_id']
    template['snapshot_lineage']['run_id']=bond['run_id']
    template['work6_final_target_reference'].update(allocation_id=w3['final_target']['allocation_id'],
        confirmed_at=w3['final_target']['confirmation_proof']['confirmed_at'],
        confirmed_by=w3['final_target']['confirmation_proof']['confirmed_by'])
    for key in ('base_currency','total_new_investment_amount','contexts','bank_cash_scope'):
        template['funding_context_snapshot'][key]=deepcopy(bond['c7_funding_context'][key])
    _,physical=case()
    return {'stock_request':stock,'bond_request':bond,'stock_evidence':facts,
        'producer_contract':contract,'stock_source_fields':source_fields(),'bond_evidence':evidence(),
        'asset_framework':template,'physical_sgov':physical}


@pytest.mark.xfail(strict=True, raises=ValueError, reason='OPEN W5-C8C9-TARGET-UNIT: native Work8 compares money to weight')
def test_actual_engines_to_full_work9_and_mentor():
    data=pipeline_case();before=deepcopy(data)
    try:
        result=run_native_pipeline(ROOT,data)
    except ValueError as error:
        assert getattr(error,'code',None)=='C8C9.W8.FINAL_TARGET_BINDING'
        assert 'differs from C7 integrated target' in str(error)
        assert data==before
        raise
    assert result['status']=='NATIVE_PIPELINE_COMPLETE'
    assert result['mentor_return']==result['unified_result']['mentor_return']
    assert result['mentor_return']['canonical_deployment_result_sha256']==result['unified_result']['canonical_deployment_result_sha256']
    assert result['funding_aggregate']['equity_used']=='450'
    assert result['trade_action']=='NO_TRADE'
    assert data==before


@pytest.mark.parametrize('mutation',['client','shared','funding'])
def test_cross_source_mismatch_prevents_engine_dispatch(mutation):
    data=pipeline_case()
    if mutation=='client':data['asset_framework']['identity']['client_id']='OTHER'
    if mutation=='shared':data['bond_request']['work3_handoff']['currency']='TWD'
    if mutation=='funding':data['asset_framework']['funding_context_snapshot']['base_currency']='TWD'
    with pytest.raises(PipelineError,match='MISMATCH'):run_native_pipeline(ROOT,data)
