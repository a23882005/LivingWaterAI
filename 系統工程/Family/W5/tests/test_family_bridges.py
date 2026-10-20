from copy import deepcopy
from pathlib import Path
import json,os
import pytest
from family_input import digest
from family_boundary import BoundaryError
from funding_guard import FundingError
from funding_bridge import reconcile_funding
from permission_bridge import project_permissions,protect_existing
from test_family_boundary import fixture
ROOT=Path(os.environ.get('W5_SOURCE_ROOT',Path(__file__).resolve().parents[4])).resolve()
F=Path(__file__).parent/'fixtures'


def funding_fixture():
    native=json.loads((F/'work6_funding_request.json').read_text())
    client=native['work3_handoff']['client_state_context']['payload']['client_id']
    family={'client_id':client,'funding_domain':'INVESTMENT_1','broker':'BROKER_KEY','account':'ACCOUNT_KEY','currency':'USD'}
    binding={'family_owner':family,'native_owner':native['work3_handoff']['owner'],'currency':'USD','source_reference':'SYNTHETIC_MAPPING','version':'1'}
    claims=[{'claim_id':str(i),'owner':deepcopy(family),'run_id':native['run_id'],'asset_class':kind,'amount':value}
        for i,(kind,value) in enumerate([('EQUITY','200'),('EQUITY','150'),('BOND','100')])]
    return dict(repo_path=ROOT,family_owner=family,native_request=native,owner_binding=binding,expected_binding_digest=digest(binding),claims=claims)


def test_native_funding_and_multi_asset_conservation():
    args=funding_fixture();before=deepcopy(args['native_request']);r=reconcile_funding(**args)
    assert r['aggregate']['equity_used']=='350' and r['aggregate']['bond_used']=='100'
    assert r['aggregate']['available_remaining']=='350.0'
    assert r['native_work6']['cash_eligibility']['available_formula_inferred'] is False
    assert args['native_request']==before


@pytest.mark.parametrize('case',['cross_account','cross_currency','overspend','duplicate','reserved','unsettled','binding'])
def test_funding_rejections(case):
    a=funding_fixture()
    if case=='cross_account':a['claims'][0]['owner']['account']='OTHER'
    elif case=='cross_currency':a['claims'][0]['owner']['currency']='TWD'
    elif case=='overspend':a['claims'][0]['amount']='600'
    elif case=='duplicate':a['claims'].append(deepcopy(a['claims'][0]))
    elif case in ('reserved','unsettled'):a['native_request']['work3_handoff']['funding_context']['executable_budget']['equity']['cash_basis']=case.upper()
    else:a['owner_binding']['version']='2'
    with pytest.raises((BoundaryError,FundingError,ValueError)):reconcile_funding(**a)


def test_zero_claims_preserve_full_explicit_available():
    a=funding_fixture();a['claims']=[]
    r=reconcile_funding(**a)
    assert r['aggregate']['available_remaining']=='800.0'


def policy_fixture(personal='IN',research='OUT',exclusion='OUT',decision='ALLOW'):
    req,ctx=fixture();snap=req['client_snapshot']['payload'];t=snap['tables'];client=req['client_id'];at='2026-10-01T00:00:00Z'
    for name,state in [('PERSONAL',personal),('RESEARCH',research),('EXCLUSION',exclusion)]:
        r={'client_id':client,'universe_code':name,'instrument_key':'VT_KEY','version_no':1,'membership_code':state,'effective_at_utc':at,'evidence_state':'VERIFIED'}
        t['universe_membership'].append(r);t['universe_confirmation'].append({**r,'confirmed_at_utc':at})
    t['permission_policy']=[{'client_id':client,'policy_key':'P1','version_no':1,'account_key':'ACCOUNT_1','instrument_key':'VT_KEY','action_code':'NEW_BUY','decision_code':decision,'effective_at_utc':at,'evidence_state':'VERIFIED'}]
    t['permission_confirmation']=[{'client_id':client,'policy_key':'P1','version_no':1,'confirmed_at_utc':at}]
    return snap


@pytest.mark.parametrize('personal,research,exclusion,decision,expected',[
 ('IN','OUT','OUT','ALLOW',True),('OUT','IN','OUT','ALLOW',False),('IN','OUT','IN','ALLOW',False),('IN','OUT','OUT','DENY',False)])
def test_universe_permission_and_existing_holding(personal,research,exclusion,decision,expected):
    snap=policy_fixture(personal,research,exclusion,decision)
    r=project_permissions(snap,account='ACCOUNT_1',evaluation_at='2026-10-20T12:00:00Z')[0]
    assert r['new_buy_candidate'] is expected
    assert r['existing_holding'] and r['retain_in_holdings_and_drift']


def test_protected_native_risk_visibility():
    req=json.loads((F/'work8_protected_request.json').read_text())
    client=req['c_work7_asset_framework_result']['identity']['client_id']
    projection={'client_id':client,'account_key':'ACCOUNT_KEY','instrument_key':'TSM_KEY','holding_policy':'HOLD_AS_IS','new_buy_candidate':False}
    binding={'instrument_key':'TSM_KEY','asset_id':req['work4_v82_integration_result']['asset_id'],'account_key':'ACCOUNT_KEY','native_owner':req['work4_v82_integration_result']['owner'],'source_reference':'SYNTHETIC_BINDING'}
    result=protect_existing(ROOT,native_request=req,projection=projection,instrument_binding=binding)
    assert result['client_action']=='HOLD_PROTECTED'
    assert result['risk_action']=='REDUCE_RISK'
    assert result['native_work8']['canonical_v82_output']==req['work4_v82_integration_result']['canonical_v82_output']


@pytest.mark.parametrize('case,expected',[('exact','KNOWN'),('unknown_fx','UNKNOWN'),('estimated','ESTIMATED'),('unknown_quantity','UNKNOWN'),('unknown_price','UNKNOWN')])
def test_valuation_quality_and_exact_units(case,expected):
    from valuation import value_position
    q={'state':'KNOWN','value':'2.125','instrument_key':'VT_KEY','source_reference':'SYNTHETIC','as_of':'2026-10-01T00:00:00Z'}
    p={**q,'value':'100.01','currency':'USD'}
    fx={'state':'KNOWN','value':'31.25','from_currency':'USD','to_currency':'TWD','source_reference':'SYNTHETIC','as_of':q['as_of']}
    if case=='unknown_fx':fx=None
    elif case=='estimated':q['state']='ESTIMATED'
    elif case=='unknown_quantity':q['state']='UNKNOWN'
    elif case=='unknown_price':p['state']='UNKNOWN'
    r=value_position(quantity=q,price=p,fx=fx,target_currency='TWD',evaluation_at='2026-10-20T12:00:00Z')
    assert r['state']==expected
    if expected!='UNKNOWN':assert r['value']=='6641.2890625'
    else:assert r['value'] is None
