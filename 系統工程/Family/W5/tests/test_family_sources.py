from copy import deepcopy
from decimal import Decimal
from datetime import datetime,timedelta
import sys
import pytest
from family_boundary import prepare_input,BoundaryError
from family_runner import FamilyRunner
from family_input import digest
from market_bridge import read_macro_snapshot
from macro_source_bridge import project_macro,validate_macro_consumers
from bond_source_bridge import bind_bond_sources
from bond_engine import run_bond_engine,V75_PATH
from test_family_runner import runner_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


@pytest.mark.parametrize('case,code',[
 ('funding_missing','FUNDING_SOURCE_REQUIRED'),('funding_cash','FUNDING_SOURCE_PAYLOAD_MISMATCH'),
 ('funding_version','FUNDING_SOURCE_VERSION_MISMATCH'),('funding_owner','FUNDING_SOURCE_OWNER_MISMATCH'),
 ('macro_not_ready','MACRO_NOT_READY'),('move_value','MOVE_NATIVE_VALUE_MISMATCH'),
 ('move_future','MOVE_AVAILABLE_AFTER_EVIDENCE'),('bond_mapping','BOND_INSTRUMENT_MAPPING_REQUIRED'),
 ('bond_quantity','BOND_POSITION_QUANTITY_MISMATCH'),('bond_unknown','BOND_QUANTITY_UNKNOWN'),
 ('bond_currency','BOND_INSTRUMENT_MISMATCH'),('bond_account','BOND_EVIDENCE_OWNER_MISMATCH'),
 ('holding_account','BOND_HOLDING_OWNER_MISMATCH')])
def test_source_semantics_rejected_before_engine_even_after_rehash(case,code,monkeypatch):
    req,ctx=runner_case();calls=[]
    if case=='funding_missing':ctx.pop('funding_source')
    elif case=='funding_cash':req['native_bundle']['stock_request']['c7_funding_context']['contexts'][2]['brokerage_cash_state']['available']=999
    elif case=='funding_version':ctx['funding_source']['owner_binding']['version']='OTHER'
    elif case=='funding_owner':ctx['funding_source']['owner_binding']['family_owner']['account']='OTHER'
    elif case=='macro_not_ready':req['macro_snapshot']['payload']['verification']['ready']=False
    elif case=='move_value':req['native_bundle']['bond_evidence']['SGOV']['metrics']['PRED-005']['move']='999'
    elif case=='move_future':req['macro_snapshot']['payload']['asOf']=req['macro_snapshot']['asOf']='2026-10-01T00:00:00Z'
    elif case=='bond_mapping':ctx['native_binding']['bond_instruments'].pop('SGOV')
    elif case=='bond_quantity':req['client_snapshot']['payload']['tables']['portfolio_position'][1]['quantity_decimal']='2'
    elif case=='bond_unknown':req['client_snapshot']['payload']['tables']['portfolio_position'][1]['quantity_decimal']=None
    elif case=='bond_currency':req['client_snapshot']['payload']['tables']['portfolio_instrument'][1]['quote_currency']='TWD'
    elif case=='bond_account':req['native_bundle']['bond_evidence']['SGOV']['broker_account_id']='OTHER'
    elif case=='holding_account':req['native_bundle']['bond_request']['v75_source_context']['existing_bond_holdings'][0]['broker_account_id']='OTHER'
    req['macro_snapshot']['digest']=digest(req['macro_snapshot']['payload'])
    req['expected_versions']['market']=ctx['expected_versions']['market']=req['macro_snapshot']['digest']
    refresh(req,ctx)
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']==code and calls==[]


@pytest.mark.parametrize('deny',['SGOV','SPSB'])
def test_bond_native_zero_cap_preserves_other_asset_and_actual_budget(deny):
    req,ctx=runner_case();t=req['client_snapshot']['payload']['tables']
    next(r for r in t['permission_policy'] if r['instrument_key']==deny+'_KEY')['decision_code']='DENY'
    refresh(req,ctx);before=deepcopy((req,ctx))
    bound=bind_bond_sources(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])
    b=req['native_bundle']
    result=run_bond_engine(ROOT,b['bond_request'],b['bond_evidence'],bound)
    out=result['runtime_ready']['output'];decisions={r['asset_id']:r for r in out['per_asset_decisions']}
    assert Decimal(decisions[deny]['deploy_amount']['amount'])==0
    other='SGOV' if deny=='SPSB' else 'SPSB'
    assert Decimal(decisions[other]['deploy_amount']['amount'])>0
    assert sum(Decimal(r['deploy_amount']['amount']) for r in decisions.values())+Decimal(out['v75_undeployed_to_sgov']['amount'])==350
    assert (req,ctx)==before


def test_bond_policy_preserves_native_existing_risk_reduction():
    req,ctx=runner_case();t=req['client_snapshot']['payload']['tables']
    next(r for r in t['permission_policy'] if r['instrument_key']=='SGOV_KEY')['decision_code']='DENY'
    refresh(req,ctx)
    bound=bind_bond_sources(req,prepare_input(req,trusted_context=ctx),ctx['native_binding'])
    b=req['native_bundle'];b['bond_evidence']['SGOV']['existing_policy']['investment_logic_invalidated']=True
    result=run_bond_engine(ROOT,b['bond_request'],b['bond_evidence'],bound)
    d=next(r for r in result['runtime_ready']['output']['per_asset_decisions'] if r['asset_id']=='SGOV')
    assert d['existing_position_action']=='TRUE_RISK_REDUCTION'
    assert Decimal(d['deploy_amount']['amount'])==0


def test_actual_w3_reader_move_reaches_original_v75_predicate_without_rewriting_feed():
    snapshot=read_macro_snapshot(ROOT,source_commit='32c9322c8bb3150480f6c86becf28e04592f5e8e')
    before=deepcopy(snapshot)
    observed=datetime.fromisoformat(snapshot['asOf'].replace('Z','+00:00'))
    with pytest.raises(BoundaryError,match='FUTURE_MACRO'):
        project_macro(snapshot,(observed-timedelta(seconds=1)).isoformat())
    projected=project_macro(snapshot,observed.isoformat())
    sys.path.insert(0,str(ROOT/V75_PATH))
    from v75_runtime.predicates import EVALUATORS
    value=projected['fields']['PRED-005.move']['value']
    # The feed supplies MOVE only; the 5-day change remains separately sourced.
    observed=datetime.fromisoformat(snapshot['asOf'].replace('Z','+00:00'))
    incomplete=EVALUATORS['PRED-005']({'move':value},observed,['W3:/indicators/m12'])
    complete=EVALUATORS['PRED-005']({'move':value,'move_pct_change_5bd':'0'},observed,
                                 ['W3:/indicators/m12','SYNTHETIC:5BD_CHANGE'])
    assert incomplete.assessment_status.value!='VALID'
    assert complete.assessment_status.value=='VALID'
    assert Decimal(value)==Decimal(str(snapshot['payload']['indicators']['m12']['value']))
    assert projected['fields']['PRED-005.move']['source_row']==snapshot['payload']['indicators']['m12']
    assert snapshot==before


def test_family_dispatch_uses_shared_funding_bridge_with_real_engine_claims(monkeypatch):
    import native_pipeline
    req,ctx=runner_case();captured=[];original=native_pipeline.reconcile_funding
    def spy(*args,**kw):
        result=original(*args,**kw);captured.append((deepcopy(kw),result));return result
    monkeypatch.setattr(native_pipeline,'reconcile_funding',spy)
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']=='C8C9.W8.FINAL_TARGET_BINDING'
    assert len(captured)==1
    kw,result=captured[0]
    assert all(c['owner']==req['owner'] for c in kw['claims'])
    assert result['aggregate']['owner']==req['owner']
    assert Decimal(result['aggregate']['equity_used'])==450
    assert Decimal(result['aggregate']['bond_used'])>0
    assert Decimal(result['aggregate']['available_remaining'])>=0
