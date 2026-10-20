from copy import deepcopy
from decimal import Decimal
import pytest
from family_boundary import prepare_input
from family_input import digest
from family_runner import FamilyRunner
from bond_engine import run_bond_engine, money_wire
from bond_source_bridge import bind_bond_sources
from bond_target_bridge import bind_bond_targets
from mentor_bridge import explain_native, MentorError
from test_family_runner import runner_case
from test_mentor_bridge import mentor_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def bound_case():
    req,ctx=runner_case();prepared=prepare_input(req,trusted_context=ctx)
    prepared.payload['family_sources']={'bond':bind_bond_sources(req,prepared,ctx['native_binding'])}
    return req,ctx,prepared,bind_bond_targets(req,prepared,ctx['native_binding'])


def test_long_term_targets_and_today_budget_are_distinct_native_values():
    req,ctx,prepared,bound=bound_case();b=req['native_bundle'];before=deepcopy((req,bound))
    out=run_bond_engine(ROOT,b['bond_request'],b['bond_evidence'],prepared.payload['family_sources']['bond'])
    assert [Decimal(bound['items'][a]['native_target']['target_amount']['amount']) for a in ('SGOV','SPSB')]==[5600,2400]
    assert sum(Decimal(x['deploy_amount']['amount']) for x in out['runtime_ready']['output']['per_asset_decisions'])==350
    assert (req,bound)==before


@pytest.mark.parametrize('kind,code',[
    ('alias','BOND_TARGET_ID_MAPPING_REQUIRED'),('duplicate_alias','BOND_TARGET_ID_MAPPING_REQUIRED'),
    ('coverage','BOND_TARGET_COVERAGE_MISMATCH'),('money','BOND_TARGET_AMOUNT_MISMATCH'),
    ('ticker','BOND_TARGET_TICKER_MISMATCH'),('unknown','BOND_TARGET_AMOUNT_UNAVAILABLE'),
    ('fx','BOND_TARGET_FX_SOURCE_REQUIRED'),('policy','BOND_HOLDING_POLICY_UNAVAILABLE'),
    ('protected','BOND_PROTECTED_FLAG_MISMATCH'),('action','BOND_C7_CLIENT_ACTION_REQUIRED')])
def test_bond_target_errors_stop_family_dispatch(kind,code,monkeypatch):
    req,ctx=runner_case();b=req['native_bundle'];lines=req['confirmed_target']['payload']['draft']['target_lines']
    line=next(x for x in lines if x['instrument_id']=='SGOV.US')
    if kind=='alias':ctx['native_binding']['bond_instruments']['SGOV'].pop('target_instrument_id')
    elif kind=='duplicate_alias':ctx['native_binding']['bond_instruments']['SPSB']['target_instrument_id']='SGOV.US'
    elif kind=='coverage':b['bond_request']['v75_source_context']['target_bond_holdings'].pop()
    elif kind=='money':b['bond_request']['v75_source_context']['target_bond_holdings'][0]['target_amount']['amount']='350'
    elif kind=='ticker':line['ticker']='OTHER'
    elif kind=='unknown':line['target_amount']['value_state']='UNKNOWN'
    elif kind=='fx':line['target_amount']['currency']='TWD'
    elif kind=='policy':req['client_snapshot']['payload']['tables']['holding_policy_confirmation'].pop(1)
    elif kind=='protected':next(x for x in b['asset_framework']['drift_snapshot']['items'] if x['instrument_id']=='SGOV.US')['protected']=True
    else:next(x for x in b['asset_framework']['drift_snapshot']['items'] if x['instrument_id']=='SGOV.US')['client_facing_action']=''
    draft=req['confirmed_target']['payload']['draft'];draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    req['confirmed_target']['target_hash']=req['confirmed_target']['payload']['target_hash']=ctx['target_hash']=draft['draft_hash']
    refresh(req,ctx)
    ctx['native_binding']['target_binding_digest']=prepare_input(req,trusted_context=ctx).payload['target_binding']['binding_digest']
    refresh(req,ctx);calls=[]
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['issue_codes'][0]['code']==code and calls==[]


def policy_mentor_case():
    _,_,_,facts=bound_case();req,u,ctx=mentor_case()
    # Independent synthetic presentation context for Work21's BNDW/SGOV golden.
    bndw=deepcopy(facts['items']['SGOV']);bndw.update(asset_id='BNDW',target_instrument_id='BNDW.US')
    bndw['target_line'].update(instrument_id='BNDW.US',ticker='BNDW')
    bndw['native_target']['asset_id']='BNDW'
    bndw['c7_drift'].update(instrument_id='BNDW.US',ticker='BNDW')
    bndw['policy']['instrument_key']='BNDW_KEY'
    facts['items']={'BNDW':bndw,'SGOV':facts['items']['SGOV']}
    ctx['client_id']=facts['client_id'];facts['run_id']=ctx['run_id']
    facts['owner']=deepcopy(ctx['owner']);facts['currency']=ctx['currency']
    ctx['expected_bond_context_digest']=digest(facts)
    return req,u,ctx,facts


def test_mentor_retains_native_actions_and_exact_c7_policy_evidence():
    req,u,ctx,facts=policy_mentor_case();before=deepcopy((req,u,ctx,facts))
    out=explain_native(ROOT,req,u,trusted_context=ctx,bond_context=facts)
    rows=[x for x in out['items'] if x['source_facts']['source_engine']=='V75']
    assert len(rows)==2 and all(x['client_action'] is None for x in rows)
    assert all(x['c7_client_action']=='HOLD' for x in rows)
    assert rows[0]['family_policy_context']['target_line']['target_amount']['amount']=='5600.00'
    assert out['canonical_deployment_result']==u['canonical_deployment_result']
    assert (req,u,ctx,facts)==before


@pytest.mark.parametrize('kind,code',[('hash','BOND_CONTEXT_DIGEST_MISMATCH'),
    ('scope','BOND_CONTEXT_SCOPE_MISMATCH:client_id'),('coverage','BOND_CONTEXT_COVERAGE_MISMATCH'),
    ('missing','BOND_CONTEXT_REQUIRED'),('permission','BOND_PERMISSION_DEPLOYMENT_MISMATCH')])
def test_mentor_rejects_changed_or_conflicting_bond_context(kind,code):
    req,u,ctx,facts=policy_mentor_case()
    if kind=='hash':facts['items']['SGOV']['c7_drift']['client_facing_action']='CHANGED'
    elif kind=='scope':facts['client_id']='OTHER'
    elif kind=='coverage':facts['items'].pop('BNDW')
    elif kind=='missing':facts=None
    else:facts['items']['BNDW']['new_buy_candidate']=False
    if kind not in ('hash','missing'):ctx['expected_bond_context_digest']=digest(facts)
    with pytest.raises(MentorError,match=code):explain_native(ROOT,req,u,trusted_context=ctx,bond_context=facts)


def test_frozen_money_serialization_preserves_native_decimal_value_and_source():
    raw={'x':[{'amount':'0E-28','currency':'USD'},{'amount':'1E+3','currency':'USD'}],
         'reason_code':'1E+3'};before=deepcopy(raw)
    wire=money_wire(raw)
    assert wire['x']==[{'amount':'0','currency':'USD'},
                       {'amount':'1000','currency':'USD'}]
    assert [Decimal(x['amount']) for x in wire['x']]==[Decimal(x['amount']) for x in raw['x']]
    assert raw==before and wire['reason_code']=='1E+3'
