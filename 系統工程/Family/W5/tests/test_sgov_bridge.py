from copy import deepcopy
import pytest
from test_native_adapters import ROOT,request
from test_bond_engine import evidence
from bond_engine import run_bond_engine
from runtime_loader import load_c_module
from sgov_bridge import reconcile_sgov


def case():
    bond_request=request(5)
    bond=run_bond_engine(ROOT,bond_request,evidence())
    stock_request=request(4)
    stock_request.update(run_id=bond_request['run_id'],work3_handoff=deepcopy(bond_request['work3_handoff']),
                         c7_funding_context=deepcopy(bond_request['c7_funding_context']))
    stock=load_c_module(ROOT,4).build_v82_runtime_input(stock_request)
    guard=load_c_module(ROOT,6)
    funding=guard.validate_funding_account_isolation({'contract_name':guard.INPUT_CONTRACT_NAME,
        'contract_version':guard.INPUT_CONTRACT_VERSION,'baseline_id':guard.BASELINE_ID,
        'run_id':bond_request['run_id'],'work3_handoff':bond_request['work3_handoff'],
        'c7_funding_context':bond_request['c7_funding_context'],'work4_adapter_result':stock,
        'work5_adapter_result':bond['built_input']})
    native=load_c_module(ROOT,7)
    req={'contract_name':native.INPUT_CONTRACT_NAME,'contract_version':native.INPUT_CONTRACT_VERSION,
        'baseline_id':native.BASELINE_ID,'run_id':bond_request['run_id'],
        'work3_handoff':bond_request['work3_handoff'],'work4_v82_adapter_result':stock,
        'work5_v75_integration_result':bond['canonical'],'work6_funding_isolation_result':funding}
    w3=bond_request['work3_handoff']
    physical={'client_id':w3['client_state_context']['payload']['client_id'],'owner':w3['owner'],
        'currency':w3['currency'],'run_id':w3['run_id'],'source_reference':'SYNTHETIC:PHYSICAL-SGOV',
        'physical_market_value':'120','as_of':'2026-09-26T14:00:00+08:00',
        'role_valuation_as_of':'2026-09-26T14:00:00+08:00'}
    return req,physical


def test_physical_roles_and_unfilled_contribution_are_separate():
    req,physical=case();result=reconcile_sgov(ROOT,req,physical)
    assert result['existing_assigned_amount']=='100.00'
    assert result['existing_unallocated_amount']=='20.00'
    assert result['contribution_applied_to_holdings'] is False
    assert result['physical_snapshot']==physical


@pytest.mark.parametrize('kind',['overallocated','wrong_owner','unknown'])
def test_physical_boundaries(kind):
    req,physical=case()
    if kind=='unknown':
        physical['physical_market_value']=None
        result=reconcile_sgov(ROOT,req,physical)
        assert result['status']=='UNKNOWN' and result['existing_unallocated_amount'] is None
    else:
        if kind=='overallocated':physical['physical_market_value']='90'
        else:physical['owner']={**physical['owner'],'account':'OTHER'}
        with pytest.raises(ValueError,match='SGOV_'):reconcile_sgov(ROOT,req,physical)
