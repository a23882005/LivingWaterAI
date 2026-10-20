from copy import deepcopy
from decimal import Decimal
import pytest
from family_input import digest
from family_boundary import prepare_input
from family_runner import FamilyRunner
from stock_source_bridge import bind_stock_source,apply_stock_policy
from stock_engine import run_stock_engine
from test_family_runner import runner_case
from test_family_boundary import refresh_snapshot
from test_native_adapters import ROOT


def refresh(req,ctx):
    refresh_snapshot(req,ctx)
    if 'valuation_source' in ctx:req['valuation_digest']=digest(ctx['valuation_source'])
    ctx['native_binding']['request_digest']=digest(req)
    ctx['native_binding']['bundle_digest']=digest(req['native_bundle'])


@pytest.mark.parametrize('case,code',[
    ('mapping','STOCK_INSTRUMENT_MAPPING_REQUIRED'),('ticker','STOCK_INSTRUMENT_MISMATCH'),
    ('exchange','STOCK_INSTRUMENT_MISMATCH'),('quantity','STOCK_POSITION_QUANTITY_MISMATCH'),
    ('unknown','STOCK_QUANTITY_UNKNOWN'),('duplicate','SOURCE_ROW_MISSING_OR_AMBIGUOUS')])
def test_rehashed_source_mismatch_stops_before_native_engine(case,code,monkeypatch):
    req,ctx=runner_case();t=req['client_snapshot']['payload']['tables'];calls=[]
    if case=='mapping':ctx['native_binding'].pop('stock_instrument')
    elif case=='ticker':t['portfolio_instrument'][0]['ticker']='OTHER'
    elif case=='exchange':t['portfolio_instrument'][0]['exchange_code']='OTHER'
    elif case=='quantity':t['portfolio_position'][0]['quantity_decimal']='2.125'
    elif case=='unknown':t['portfolio_position'][0]['quantity_decimal']=None
    else:t['portfolio_position'].append(deepcopy(t['portfolio_position'][0]))
    refresh(req,ctx)
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']==code and calls==[]
    assert out['canonical_result'] is None


@pytest.mark.parametrize('policy,expected',[
    ('allow','450'),('exclusion','0'),('deny','0'),('unconfirmed','0'),('ambiguous','0')])
def test_w1_policy_controls_actual_v82_buy_cap_preserving_risk_inputs(policy,expected):
    req,ctx=runner_case();t=req['client_snapshot']['payload']['tables']
    if policy=='exclusion':t['universe_membership'][2]['membership_code']='IN'
    elif policy=='deny':t['permission_policy'][0]['decision_code']='DENY'
    elif policy=='unconfirmed':t['permission_confirmation']=[]
    elif policy=='ambiguous':t['permission_policy'].append(deepcopy(t['permission_policy'][0]))
    refresh(req,ctx);before=deepcopy((req,ctx))
    prepared=prepare_input(req,trusted_context=ctx)
    source=bind_stock_source(req,prepared,ctx['native_binding'])
    data=apply_stock_policy(req['native_bundle'],source)
    result=run_stock_engine(ROOT,data['stock_request'],data['stock_evidence'],data['producer_contract'])
    assert result['execution'].execution_amount==Decimal(expected)
    assert data['stock_evidence']['core']==req['native_bundle']['stock_evidence']['core']
    assert data['stock_request']['asset_context']['confirmed_position_snapshot']['quantity']==0
    assert source['policy']['retain_in_holdings_and_drift']
    assert (req,ctx)==before


def test_empty_complete_holdings_maps_to_zero_without_dropping_instrument():
    req,ctx=runner_case();req['client_snapshot']['payload']['tables']['portfolio_position']=[]
    refresh(req,ctx)
    source=bind_stock_source(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])
    assert source['confirmed_quantity']=='0' and source['source_position'] is None
    assert source['policy']['existing_holding'] is False
