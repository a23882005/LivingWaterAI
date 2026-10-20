"""Reuse native C8C9 Work6 and add exact Family multi-claim conservation."""
from copy import deepcopy
from family_boundary import require
from family_input import digest
from funding_guard import check_aggregate,owner_key
from runtime_loader import load_c_module


def reconcile_funding(repo_path,*,family_owner,native_request,owner_binding,expected_binding_digest,claims):
    require(digest(owner_binding)==expected_binding_digest,'OWNER_BINDING_HASH_MISMATCH','owner_binding')
    require(owner_binding.get('family_owner')==family_owner,'OWNER_BINDING_MISMATCH','owner_binding.family_owner')
    require(bool(owner_binding.get('source_reference')) and bool(owner_binding.get('version')),'OWNER_BINDING_SOURCE_REQUIRED','owner_binding')
    owner_key(family_owner)
    w3=native_request['work3_handoff']
    require(w3.get('owner')==owner_binding.get('native_owner'),'NATIVE_OWNER_MISMATCH','work3_handoff.owner')
    require(w3.get('currency')==family_owner['currency']==owner_binding.get('currency'),'OWNER_CURRENCY_MISMATCH','owner_binding.currency')
    require(w3.get('client_state_context',{}).get('payload',{}).get('client_id')==family_owner['client_id'],'NATIVE_CLIENT_MISMATCH','work3_handoff.client_state_context')
    native=load_c_module(repo_path,6).validate_funding_account_isolation(deepcopy(native_request))
    cash=native['cash_eligibility']
    aggregate=check_aggregate(owner=family_owner,run_id=native['run_id'],available=cash['available'],
        equity_budget=cash['equity_executable_budget'],bond_budget=cash['bond_executable_budget'],claims=claims)
    return {'schema_version':'Family.W5.FundingReconciliation.v1','native_work6':native,'aggregate':aggregate,
        'owner_binding_digest':expected_binding_digest,'available_source':'C8C9.Work6.cash_eligibility.available',
        'input_digest':digest(native_request),'trade_action':'NO_TRADE'}
