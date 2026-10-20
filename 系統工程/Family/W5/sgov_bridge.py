"""Read-only Family physical/role reconciliation around original C8C9 Work7."""
from copy import deepcopy
from decimal import Decimal
from runtime_loader import load_c_module
from datetime import datetime


def reconcile_sgov(repo_path, native_request, physical_snapshot):
    req,physical=deepcopy(native_request),deepcopy(physical_snapshot)
    w3=req['work3_handoff']
    expected={'client_id':w3['client_state_context']['payload']['client_id'],
        'owner':w3['owner'],'currency':w3['currency'],'run_id':w3['run_id']}
    for key,value in expected.items():
        if physical.get(key)!=value:raise ValueError('SGOV_IDENTITY_MISMATCH:'+key)
    if not physical.get('source_reference'):raise ValueError('SGOV_SOURCE_REQUIRED')
    def time(value):
        t=datetime.fromisoformat(value.replace('Z','+00:00'))
        if t.tzinfo is None:raise ValueError('SGOV_TIMEZONE_REQUIRED')
        return t
    if time(physical['as_of'])>time(w3['temporal']['as_of']):raise ValueError('SGOV_FUTURE_SNAPSHOT')
    if physical['role_valuation_as_of']!=physical['as_of']:raise ValueError('SGOV_VALUATION_TIME_MISMATCH')
    native=load_c_module(repo_path,7).validate_sgov_runtime_roles(req)
    roles=native['sgov_roles']
    assigned=sum(Decimal(roles[k]['amount']) for k in ('sgov_bond_bucket','sgov_dry_powder_bucket'))
    amount=physical.get('physical_market_value')
    if amount is None:
        status,unallocated='UNKNOWN',None
    else:
        if isinstance(amount,(bool,float)):raise ValueError('SGOV_EXACT_AMOUNT_REQUIRED')
        amount=Decimal(amount)
        if not amount.is_finite() or amount<0:raise ValueError('SGOV_INVALID_AMOUNT')
        if assigned>amount:raise ValueError('SGOV_ROLE_OVERALLOCATION')
        status,unallocated='KNOWN',str(amount-assigned)
    return {'status':status,'physical_snapshot':physical,'native_work7':native,
        'existing_assigned_amount':str(assigned),'existing_unallocated_amount':unallocated,
        'recommended_unfilled_contribution':deepcopy(roles['v75_undeployed_to_sgov']['contribution']),
        'contribution_applied_to_holdings':False,'trade_action':'NO_TRADE'}
