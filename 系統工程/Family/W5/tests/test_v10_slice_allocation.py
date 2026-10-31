from copy import deepcopy
from decimal import Decimal
import sys
import pytest
from test_native_adapters import ROOT
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.slice_allocation import allocate,funding_layers

OWNER={'client_id':'SYNTHETIC','broker':'SYNTHETIC','account':'A','currency':'USD','funding_domain':'US_DIRECT'}


def case():
    return dict(owner=OWNER,pool_id='SYNTHETIC_V70_ROOM',remaining_tactical_room='100',
        slices=[{'owner':OWNER,'asset_id':s,'bucket_id':'CASH','currency':'USD','slice':v,
            'fx_to_bucket':'1','fx_bucket_to_budget':'1'} for s,v in (('A','75'),('B','25'))],
        buckets=[{'owner':OWNER,'bucket_id':'CASH','currency':'USD','available_authorized_notional_cash':'80',
            'funding_source_ids':['ONE_ACCOUNT_AVAILABLE_CASH']}])


def test_shared_cash_and_v70_room_are_each_applied_once():
    args=case();before=deepcopy(args);out=allocate(**args)
    assert Decimal(out['allocations']['A'])==60 and Decimal(out['allocations']['B'])==20
    assert sum(map(Decimal,out['allocations'].values()))==80 and args==before
    args['remaining_tactical_room']='40';out=allocate(**args)
    assert sum(map(Decimal,out['allocations'].values()))==40
    assert Decimal(out['allocations']['A'])==30 and Decimal(out['allocations']['B'])==10


def test_unknown_competing_asset_is_not_zero_but_known_zero_pool_short_circuits():
    a=case();a['slices'][1]['slice']=None
    assert all(v is None for v in allocate(**a)['allocations'].values())
    a['remaining_tactical_room']='0';assert set(allocate(**a)['allocations'].values())=={'0'}
    a['remaining_tactical_room']='100';a['buckets'][0]['available_authorized_notional_cash']='0'
    assert set(allocate(**a)['allocations'].values())=={'0'}


def test_reporting_fx_and_source_identity_are_required_and_cash_cannot_be_copied_to_two_buckets():
    a=case();a['slices'][0]['currency']='TWD';a['slices'][0]['fx_to_bucket']='0.03125'
    assert allocate(**a)['allocations']['A'] is None
    a['slices'][0]['fx_source_reference']='SYNTHETIC_REPORTING_FX'
    assert allocate(**a)['allocations']['A'] is not None
    a['buckets'].append({**a['buckets'][0],'bucket_id':'DUPLICATED'})
    with pytest.raises(ValueError,match='FUNDING_SOURCE'):allocate(**a)
    a=case();a['slices'][0]['owner']={**OWNER,'account':'OTHER'}
    with pytest.raises(ValueError,match='OWNER_MISMATCH'):allocate(**a)


def test_authorized_sgov_planning_pool_does_not_become_settled_cash_or_defensive_ammo():
    source={'source_id':'SYNTHETIC_SGOV','physical_value':'120000','defensive_bond_role':'40000',
        'dry_powder_role':'80000','retained_dry_floor':'0','other_dry_commitments':'0',
        'sale_authorized':True,'role_source_reference':'SYNTHETIC_CURRENT_ROLE_SOURCE'}
    out=funding_layers(available_cash='20000',settled_cash='20000',sgov_sources=[source])
    assert out['planning_pool']=='100000' and out['settled_execution_cash']=='20000'
    assert out['authorized_mobilizable_sgov']=='80000'
    assert not out['sgov_included_in_settled_cash'] and not out['sgov_sale_performed']
    source['sale_authorized']=False
    assert funding_layers(available_cash='20000',settled_cash='20000',sgov_sources=[source])['planning_pool']=='20000'


def test_unknown_sgov_source_does_not_overwrite_known_cash_and_bad_roles_are_rejected():
    source={'source_id':'SYNTHETIC_SGOV','sale_authorized':None}
    result=funding_layers(available_cash='20000',settled_cash=None,sgov_sources=[source])
    assert result['available_cash']=='20000' and result['settled_execution_cash'] is None and result['planning_pool'] is None
    source.update(sale_authorized=True,physical_value='100',defensive_bond_role='40',dry_powder_role='80',
        retained_dry_floor='0',other_dry_commitments='0',role_source_reference='SYNTHETIC')
    with pytest.raises(ValueError,match='ROLES_EXCEED'):funding_layers(available_cash='0',settled_cash='0',sgov_sources=[source])
