"""Unsettled cash can reach zero-budget diagnostics, never positive buys."""
from copy import deepcopy
from decimal import Decimal
import pytest
from tactical_budget import tactical_cap,TacticalBudgetError


def handoff():
    return {'run_id':'SYNTHETIC','currency':'USD','v70_runtime_context':{
        'run_id':'SYNTHETIC','upstream_v70_snapshot_id':'SYNTHETIC_V70','source_reference_ids':['SYNTHETIC_SOURCE'],
        'payload':{'run_id':'SYNTHETIC','value_state':'KNOWN','data_quality':'OK','issue_codes':[],
            'stock_tactical_amount':'100','bond_tactical_amount':'50'}},
        'funding_context':{'settlement':{'source_status':'UNKNOWN','cash_basis':'AVAILABLE',
            'cash_state':{'total':'1000','available':'0','reserved':'0','unsettled':'0'}},
            'executable_budget':{'equity':{'amount':'0'},'bond':{'amount':'0'}}}}


@pytest.mark.parametrize('leg',['equity','bond'])
def test_zero_trial_does_not_assert_settlement_or_release_physical_assets(leg):
    source=handoff();before=deepcopy(source);cap=tactical_cap(source,leg)
    assert cap['amount']==0 and cap['source_amount']>0
    assert cap['reason_codes']==['ZERO_EXECUTABLE_BUDGET__SETTLEMENT_NOT_ASSERTED']
    assert source==before and source['funding_context']['settlement']['source_status']=='UNKNOWN'


@pytest.mark.parametrize('kind',['budget','available','missing','wrong_basis','unknown_budget'])
def test_no_positive_or_missing_money_is_admitted_by_the_zero_trial(kind):
    source=handoff();funding=source['funding_context']
    if kind=='budget':funding['executable_budget']['bond']['amount']='1'
    elif kind=='available':funding['settlement']['cash_state']['available']='1'
    elif kind=='missing':funding['settlement']['cash_state']['available']=None
    elif kind=='wrong_basis':funding['settlement']['cash_basis']='TOTAL'
    else:funding['executable_budget']['bond']['amount']=None
    with pytest.raises(TacticalBudgetError,match='SETTLED_AVAILABLE_REQUIRED'):tactical_cap(source,'bond')
