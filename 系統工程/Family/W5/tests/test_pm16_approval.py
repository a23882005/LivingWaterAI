"""PM-approved source-separated None semantics; real existing runtime only."""
import json
from copy import deepcopy
from family_input import digest
from family_runner import FamilyRunner
from mentor_bridge import explain_native
from test_bond_target_mentor import policy_mentor_case
from test_family_end_to_end import full_family_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def test_approved_null_keeps_native_money_policy_and_c7_separate():
    req,u,ctx,facts=policy_mentor_case();before=deepcopy((req,u,facts))
    out=explain_native(ROOT,req,u,trusted_context=ctx,bond_context=facts)
    native={r['item_id']:r for r in u['canonical_deployment_result']['items']}
    for row in out['items']:
        if row['source_facts']['source_engine']!='V75':continue
        src=native[row['item_id']];fact=facts['items'][src['asset_id']]
        assert row['client_action'] is None and src['client_preference_action'] is None
        assert row['source_facts']==src
        assert row['risk_signal']==src['source_action']
        assert row['family_policy_context']['policy']==fact['policy']
        assert row['c7_client_action']==fact['c7_drift']['client_facing_action']
        assert json.loads(json.dumps(row))['client_action'] is None
    assert out['trade_action']=='NO_TRADE' and out['execution_advice_allowed'] is False
    assert (req,u,facts)==before


def test_unsupported_bond_hold_policy_stops_family_before_publication():
    req,ctx=full_family_case()
    tables=req['client_snapshot']['payload']['tables']
    rows=tables['holding_policy_proposal']
    bond=next(x for x in rows if x['instrument_key']=='SGOV_KEY')
    bond['policy_code']='HOLD_AS_IS'
    refresh(req,ctx)
    runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    result=runner.analyze(req)
    assert result['status'] in ('BLOCKED','DATA_UNAVAILABLE'),result
    assert result['mentor'] is None
    assert any(x['code']=='BOND_PROTECTED_FLAG_MISMATCH' for x in result['issue_codes']),result
    assert all(x['publication_count']==0 for x in runner.store._entries.values())


def test_original_c7_explicitly_rejects_bond_protection_contract():
    from c7_engine import run_c7_engine
    from test_c7_engine import original_case
    import importlib
    source,_=original_case()
    run_c7_engine(ROOT,source)  # Load verified original module and its dependencies.
    work6=deepcopy(source['work6_result'])
    work6['preference_locks']=[{'instrument_id':'SGOV',
        'protected_existing_holding':True,'client_preference_locked':True,
        'final_target_locked_to_current':True}]
    errors=importlib.import_module('work7.asset_framework').validate_protected_holding_contract(work6)
    assert 'protected SGOV is not an existing individual company stock' in errors
