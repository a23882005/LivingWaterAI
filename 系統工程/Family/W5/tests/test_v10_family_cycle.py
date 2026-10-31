"""Actual FamilyRunner, original Work9/Mentor, persistent synthetic ledger."""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from family_runner import FamilyRunner
from test_family_end_to_end import full_family_case
from c7_engine import run_c7_engine
from test_family_boundary import refresh_snapshot
from test_v10_stock_integration import adopted_case,bind_context
from test_native_adapters import ROOT
from livingwater_v82_runtime.daily_slice import CycleLedgerStore,open_cycle


def family_case(tmp_path):
    request,context=full_family_case();_,template,_=adopted_case()
    request['client_snapshot']['payload']['source_sha256']='a'*64
    refresh_snapshot(request,context)
    bundle=request['native_bundle'];facts=bundle['stock_evidence'];contract=bundle['producer_contract']
    bundle['stock_request']['asset_context']['confirmed_position_snapshot']['quantity']=0
    request['client_snapshot']['payload']['tables']['portfolio_position'][0]['quantity_decimal']='0'
    c7=context['c7_source'];work6=c7['work6_result']
    current=work6['final_target_engine_result']['allocations']['current_allocation']['snapshot']
    for row in current['positions']:
        if row['instrument_id']=='QQQ':row['weight']['value']=0;row['portfolio_amount']['amount']=0
        elif row['instrument_id']=='CORE.US':row['weight']['value']=.96;row['portfolio_amount']['amount']=960
    for row in work6['drift_snapshot']['items']:
        if row['instrument_id']=='QQQ':
            row['current_weight']['value']=0;row['drift']['value']=.1;row['client_facing_action']='INCREASE_TARGET_WEIGHT'
        elif row['instrument_id']=='CORE.US':row['current_weight']['value']=.96;row['drift']['value']=-.26
    bundle['asset_framework']=run_c7_engine(ROOT,c7)['result'];request['c7_source_digest']=digest(c7)
    facts['core']['valuation_metrics'][0].update(metric_name='FORWARD_PE',current='10',historical_median='10')
    facts['core']['valuation_waterfall']=['FORWARD_PE']
    adopted=deepcopy(template['approved_v10_context']);adopted['identity'].update(
        client_id=request['client_id'],run_id=request['run_id'],owner=deepcopy(request['owner']),
        evaluation_at=request['evaluation_at'],snapshot_id=request['client_snapshot']['payload']['source_sha256'])
    adopted['native_owner']=deepcopy(context['native_binding']['native_owner'])
    adopted['session']['session_id']=request['evaluation_at'][:10]
    adopted['planning_ledger_source']={'owner':deepcopy(request['owner']),'planning_write_authorized':True,
        'local_path':str(tmp_path/'planning.sqlite'),'source_reference':'SYNTHETIC_APPROVED_PLANNING_LEDGER'}
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True)
    initial=template['approved_v10_context']['cycle_snapshot']['cycle']
    cycle=open_cycle(owner=request['owner'],session_id=adopted['session']['session_id'],exchange='NASDAQ',asset_id='QQQ',
        opened_at=request['evaluation_at'],gap='95',speed_result=initial['initial_speed'],
        permission=True,exposure_reconciled=True,session_open=True)
    store.save(cycle,expected_revision=None)
    adopted['cycle_snapshot']={'status':'VERIFIED','cycle':cycle,'ledger_path':str(store.path)}
    group=adopted['shared_allocation_request'];group['owner']=deepcopy(request['owner'])
    for row in group['slices']+group['buckets']:row['owner']=deepcopy(request['owner'])
    group['slices'][0]['slice']='23.75'
    facts['approved_v10_context']=adopted;bind_context(facts,contract)
    refresh_snapshot(request,context)
    context['native_binding'].update(bundle_digest=digest(bundle),request_digest=digest(request))
    return request,context,store,cycle


def test_original_family_work9_mentor_positive_path_commits_local_plan_only_once(tmp_path):
    req,ctx,store,cycle=family_case(tmp_path);runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    first=runner.analyze(req)
    assert first['status']=='OK',first
    assert first['mentor'] and first['native_result']['unified_result']
    receipt=first['daily_slice_ledger_receipt']
    assert Decimal(receipt['planning_commitment'])>0 and not receipt['broker_cash_reserved']
    assert receipt['already_committed'] is False
    saved=store.get(cycle['slice_cycle_id']);assert len(saved['intents'])==1
    second=runner.analyze(req)
    assert second['status']=='OK',second
    assert second['daily_slice_ledger_receipt']['already_committed'] is True
    assert second['daily_slice_ledger_receipt']['new_commitment']=='0'
    # A fresh worker/process-equivalent object does not receive a new budget.
    third=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert third['status']=='OK',third
    assert third['daily_slice_ledger_receipt']['already_committed'] is True
    assert store.get(cycle['slice_cycle_id'])==saved
    assert first['trade_action']=='NO_TRADE' and first['production']=='HOLD'


def test_new_run_id_does_not_own_old_snapshot_replay_or_reset_cycle(tmp_path):
    req,ctx,store,cycle=family_case(tmp_path)
    assert FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)['status']=='OK'
    req=deepcopy(req);ctx=deepcopy(ctx);req['request_id']+='-CHANGED'
    ctx['native_binding']['request_digest']=digest(req)
    before=store.get(cycle['slice_cycle_id'])
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['status']=='DATA_UNAVAILABLE'
    assert result['issue_codes'][0]['code']=='V82_CYCLE_LEDGER_CHANGED_REBUILD_REQUIRED'
    assert store.get(cycle['slice_cycle_id'])==before


def test_foreign_owner_or_removed_durable_ledger_cannot_be_resigned_into_family(tmp_path):
    req,ctx,store,cycle=family_case(tmp_path)
    approved=req['native_bundle']['stock_evidence']['approved_v10_context']
    approved['identity']['owner']={**req['owner'],'account':'OTHER'}
    bind_context(req['native_bundle']['stock_evidence'],req['native_bundle']['producer_contract'])
    ctx['native_binding'].update(bundle_digest=digest(req['native_bundle']),request_digest=digest(req))
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['status']!='OK' and result['issue_codes'][0]['code']=='V82_APPROVED_CONTEXT_IDENTITY_MISMATCH'


def test_first_cycle_and_plan_are_committed_atomically_after_full_family_guards(tmp_path):
    req,ctx,_,cycle=family_case(tmp_path)
    empty=CycleLedgerStore(tmp_path/'first-cycle.sqlite',create=True)
    source=req['native_bundle']['stock_evidence']['approved_v10_context']
    source['planning_ledger_source']['local_path']=str(empty.path)
    source['cycle_snapshot'].update(status='PROPOSED',ledger_path=str(empty.path))
    bind_context(req['native_bundle']['stock_evidence'],req['native_bundle']['producer_contract'])
    ctx['native_binding'].update(bundle_digest=digest(req['native_bundle']),request_digest=digest(req))
    assert empty.get(cycle['slice_cycle_id']) is None
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['status']=='OK',result
    stored=empty.get(cycle['slice_cycle_id']);assert stored['revision']==1 and len(stored['intents'])==1
    assert not result['daily_slice_ledger_receipt']['already_committed']
    replay=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert replay['status']=='OK' and replay['daily_slice_ledger_receipt']['already_committed']
    assert empty.get(cycle['slice_cycle_id'])==stored


def test_existing_local_plan_in_same_cash_bucket_is_checked_before_publication(tmp_path):
    from livingwater_v82_runtime.daily_slice import update_intent
    req,ctx,store,cycle=family_case(tmp_path)
    source=req['native_bundle']['stock_evidence']['approved_v10_context'];group=source['shared_allocation_request']
    group['buckets'][0]['available_authorized_notional_cash']='20'
    group['slices'].append({**group['slices'][0],'asset_id':'OTHER','slice':'0'})
    other=open_cycle(owner=req['owner'],session_id=cycle['session_id'],exchange='NASDAQ',asset_id='OTHER',
        opened_at=req['evaluation_at'],gap='100',speed_result=cycle['initial_speed'],permission=True,
        exposure_reconciled=True,session_open=True)
    receipt={'owner':req['owner'],'asset_id':'OTHER','source_reference':'SYNTHETIC_PREEXISTING_LOCAL_PLAN',
        'source_hash':'SYNTHETIC_HASH','as_of':req['evaluation_at'],'available_at':req['evaluation_at'],
        'planning_pool_id':group['pool_id'],'funding_bucket_id':'CASH'}
    other=update_intent(other,event_id='OTHER_PLAN',intent_id='OTHER_PLAN',state='PLANNED',filled_amount='0',remaining_amount='10',
        receipt=receipt,evaluation_at=req['evaluation_at'],speed_result=cycle['initial_speed'],permission=True,
        session_id=cycle['session_id'],session_open=True)
    store.save(other,expected_revision=None)
    bind_context(req['native_bundle']['stock_evidence'],req['native_bundle']['producer_contract'])
    ctx['native_binding'].update(bundle_digest=digest(req['native_bundle']),request_digest=digest(req))
    runner=FamilyRunner(ROOT,context_provider=lambda:ctx);result=runner.analyze(req)
    assert result['status']=='DATA_UNAVAILABLE',result
    assert result['mentor'] is None and result['canonical_result'] is None
    assert store.get(cycle['slice_cycle_id'])['intents']=={}
    assert store.get(other['slice_cycle_id'])==other
    assert sum(x['publication_count'] for x in runner.store._entries.values())==0


def test_current_source_backed_request_cannot_omit_the_adopted_slice_contract(tmp_path):
    from v82_slice_bridge import bind
    from family_boundary import BoundaryError
    import pytest
    req,ctx,_,_=family_case(tmp_path);ctx['native_binding']['data_provenance']='SOURCE_BACKED'
    req['evaluation_at']='2026-10-30T00:00:00Z'
    del req['native_bundle']['stock_evidence']['approved_v10_context']
    with pytest.raises(BoundaryError,match='V82_APPROVED_CONTEXT_REQUIRED'):bind(ROOT,req,ctx)
