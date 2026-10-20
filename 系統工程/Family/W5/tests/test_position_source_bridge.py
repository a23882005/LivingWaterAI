from copy import deepcopy
from decimal import Decimal
import pytest
from family_runner import FamilyRunner
from family_boundary import prepare_input
from position_source_bridge import bind_stock_protection
from test_family_runner import runner_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def test_changed_quote_provenance_invalidates_old_request_before_dispatch(monkeypatch):
    req,ctx=runner_case();calls=[]
    ctx['valuation_source']['prices']['SGOV']['source_reference']='REVISED_QUOTE_SOURCE'
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']=='VALUATION_VERSION_CONFLICT' and calls==[]


@pytest.mark.parametrize('case,code',[
 ('missing','VALUATION_INPUT_REQUIRED'),('unknown','POSITION_VALUATION_UNAVAILABLE'),
 ('price','STOCK_VALUATION_SOURCE_MISMATCH'),('future','VALUATION_TIME_MISMATCH'),
 ('sgov','SGOV_PHYSICAL_VALUATION_MISMATCH'),('sgov_owner','SGOV_PHYSICAL_OWNER_MISMATCH'),
 ('bond_value','BOND_VALUATION_MISMATCH'),('policy','HOLDING_POLICY_UNAVAILABLE'),
 ('protected','HOLDING_POLICY_FRAMEWORK_MISMATCH'),('nav','DRIFT_NAV_SOURCE_MISMATCH'),
 ('weight','CURRENT_WEIGHT_VALUATION_MISMATCH'),('unit','VALUATION_PRICE_UNIT_REQUIRED')])
def test_mismatched_values_or_protection_rejected_before_engine(case,code,monkeypatch):
    req,ctx=runner_case();b=req['native_bundle'];calls=[]
    if case=='missing':ctx.pop('valuation_source')
    elif case=='unknown':ctx['valuation_source']['prices']['SGOV']['state']='UNKNOWN'
    elif case=='price':ctx['valuation_source']['prices']['QQQ']['value']='11'
    elif case=='future':ctx['valuation_source']['prices']['QQQ']['as_of']='2026-10-21T12:00:00Z'
    elif case=='sgov':b['physical_sgov']['physical_market_value']='999'
    elif case=='sgov_owner':b['physical_sgov']['owner']['account']='OTHER'
    elif case=='bond_value':b['bond_request']['v75_source_context']['existing_bond_holdings'][1]['amount']['amount']='10'
    elif case=='policy':req['client_snapshot']['payload']['tables']['holding_policy_confirmation']=[]
    elif case=='protected':next(r for r in b['asset_framework']['drift_snapshot']['items'] if r['instrument_id']=='QQQ')['protected']=True
    elif case=='nav':ctx['valuation_source']['portfolio_nav']['currency']='TWD'
    elif case=='weight':next(r for r in b['asset_framework']['drift_snapshot']['items'] if r['instrument_id']=='QQQ')['current_weight']['value']=.05
    elif case=='unit':ctx['valuation_source']['prices']['SGOV']['unit']='TOTAL_MARKET_VALUE'
    refresh(req,ctx)
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']==code and calls==[]


def test_real_work7_uses_w1_quantity_valuation_and_preserves_unfilled_contribution(monkeypatch):
    import native_pipeline
    req,ctx=runner_case();before=deepcopy((req,ctx));captures=[];original=native_pipeline.reconcile_sgov
    def spy(*args):
        result=original(*args);captures.append(result);return result
    monkeypatch.setattr(native_pipeline,'reconcile_sgov',spy)
    runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    prepared,_=runner._validate(req)
    v=prepared.payload['family_sources']['valuation']['positions']['SGOV']
    assert Decimal(v['value'])==120 and v['sources']['quantity']['value']=='1'
    assert v['sources']['price']['value']=='120'
    result=runner.analyze(req)
    assert result['issue_codes'][0]['code']=='C8C9.W8.FINAL_TARGET_BINDING'
    assert len(captures)==1
    assert Decimal(captures[0]['existing_assigned_amount'])==100
    assert Decimal(captures[0]['existing_unallocated_amount'])==20
    assert captures[0]['contribution_applied_to_holdings'] is False
    assert (req,ctx)==before


def test_confirmed_hold_as_is_binds_to_matching_framework_and_value():
    req,ctx=runner_case();tables=req['client_snapshot']['payload']['tables']
    tables['holding_policy_proposal'][0]['policy_code']='HOLD_AS_IS'
    tables['portfolio_position'][0]['quantity_decimal']='10'
    req['native_bundle']['stock_request']['asset_context']['confirmed_position_snapshot']['quantity']=10
    ctx['valuation_source']['portfolio_nav']['value']='2000'
    f=req['native_bundle']['asset_framework'];f['drift_snapshot']['denominator']['amount']=2000
    target=next(r for r in f['integrated_asset_framework']['instrument_targets'] if r['instrument_id']=='QQQ')
    target.update(protected=True,allocation_rule='LOCKED_CURRENT_WEIGHT')
    drift=next(r for r in f['drift_snapshot']['items'] if r['instrument_id']=='QQQ')
    drift.update(protected=True,client_facing_action='HOLD_PROTECTED')
    drift['current_weight']['value']=.05;drift['drift']['value']=0
    f['protected_locked_weights']=[{'instrument_id':'QQQ','ticker':'QQQ','bucket':'STOCK',
        'current_weight':.05,'final_target_weight':.05,'drift':0,'protected':True,
        'source_reference_ids':['SYNTHETIC_W1_POLICY']}]
    refresh(req,ctx)
    prepared,_=FamilyRunner(ROOT,context_provider=lambda:ctx)._validate(req)
    out=prepared.payload['family_sources']['protection']
    assert out['projection']['holding_policy']=='HOLD_AS_IS'
    assert Decimal(out['current_weight'])==Decimal('.05')
    assert prepared.payload['family_sources']['valuation']['positions']['QQQ']['value']=='100'
