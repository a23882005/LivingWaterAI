"""Synthetic broker confirmations: replacement is never implicit cash release."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import pytest
from test_family_c7_source_assembly import original_case,assemble,ROOT
from replacement_order_source import reconcile


def case(tmp_path,*,filled='0',remaining='6'):
    module,ci,request,context,tactical,identities,facts,desc=original_case(tmp_path)
    old=facts['orders'][0];old.update(state='REPLACED',remaining_quantity='0',filled_quantity=filled,
        broker_order_id='SYNTHETIC_OLD_ORDER',broker_revision_id='1',filled_quantity_basis='CHAIN_CUMULATIVE',currency=request['owner']['currency'],
        last_acknowledged_commitment=dict(order_quantity='10',commitment_price='1',source_reference='SYNTHETIC_LAST_ACK',as_of=request['evaluation_at']))
    new=deepcopy(old);new.update(event_id='SYNTHETIC_NEW',state='OPEN',broker_order_id='SYNTHETIC_NEW_ORDER',
        order_quantity=str(int(filled)+int(remaining)),remaining_quantity=remaining)
    new.pop('last_acknowledged_commitment');facts['orders'].append(new)
    if filled!='0':
        facts['fills']=[dict(fill_id='SYNTHETIC_FILL',order_event_id=old['event_id'],account=old['account'],
            asset_id=old['asset_id'],quantity=filled,applied_to_position_id='SYNTHETIC_POSITION',economic_effect_id='SYNTHETIC_POSITION_EFFECT')]
    def confirm(before=old,after=new,cid='SYNTHETIC_ACK'):
        data=dict(schema_version='Family.W8.OrderReplacementConfirmation.v1',confirmation_id=cid,
            **{k:request[k] for k in ('client_id','run_id','evaluation_at','owner')},
            source_db_sha256=request['client_snapshot']['payload']['source_sha256'],asset_id=old['asset_id'],intent_id=old['intent_id'],
            predecessor_event_id=before['event_id'],successor_event_id=after['event_id'],
            predecessor_order_key={k:before.get(k) for k in ('broker_order_id','broker_revision_id')},
            successor_order_key={k:after.get(k) for k in ('broker_order_id','broker_revision_id')},
            confirmed_at=request['evaluation_at'],available_at=request['evaluation_at'],source_reference='SYNTHETIC_SOURCE_OWNER_ACK',
            evidence_state='VERIFIED',unfilled_commitment_transferred=True,currency=request['owner']['currency'])
        path=tmp_path/(cid+'.json');path.write_text(json.dumps(data))
        return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),retrieved_at=request['evaluation_at'])
    facts['replacement_confirmations']=[confirm()]
    return module,ci,request,context,tactical,identities,facts,desc,confirm


def change(source,fn):
    path=Path(source['local_path']);data=json.loads(path.read_text());fn(data)
    path.write_text(json.dumps(data));source['sha256']=sha256(path.read_bytes()).hexdigest()


def terminal_ack(order,fixture):
    owner=fixture[6]['accounts'][0]['owner'];at=fixture[2]['evaluation_at']
    if not order.get('broker_order_id'):order['broker_order_id']='SYNTHETIC_TERMINAL_ORDER'
    order['terminal_acknowledgment']=dict(evidence_state='VERIFIED',source_reference='SYNTHETIC_BROKER_TERMINAL_ACK',
        broker_order_id=order['broker_order_id'],broker_revision_id=order.get('broker_revision_id'),final_state=order['state'],
        currency=owner['currency'],owner=deepcopy(owner),asset_id=order['asset_id'],confirmed_at=at,available_at=at,
        **{k:order[k] for k in ('order_quantity','filled_quantity','remaining_quantity')})


def build(tmp_path,fixture):
    m,ci,r,c,t,ids,f,desc,*_=fixture
    out=assemble(ROOT,r,c,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    scope=out['scope_candidate'];ci=deepcopy(ci);ci['identity']=deepcopy(scope['identity'])
    ci['source_references']+=out['source_references'];ci['allocations']['current_allocation']['snapshot']=out['current_allocation']
    ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='TWD',value_state='KNOWN')
    cap=m.capacity(scope,ci,r['evaluation_at']);m.validate_confirmed_book(scope,ci,r['evaluation_at'])
    return out,cap


def test_confirmed_replacement_counts_successor_once_without_releasing_cash(tmp_path):
    data=case(tmp_path);f=data[6];before=deepcopy(f);out,cap=build(tmp_path,data)
    assert cap['occupied']=='71' and cap['incremental_capacity']=='29'
    orders=[r for r in out['scope_candidate']['exposures'] if r['kind']=='ACTIVE_BUY_RESERVATION']
    assert [(r['event_id'],r['amount']) for r in orders]==[('SYNTHETIC_NEW','6')]
    cash=out['scope_candidate']['funding_buckets'][0]
    assert cash['cash_amount']=='40' and cash['reserved_amount']=='10' and cash['authorized_incremental_amount']=='50'
    replay=out['original_observations']['order_replacement_replay']
    assert not replay['confirmed_cash_release_created'] and not replay['ledger_written']
    assert replay['retired_predecessors'][0]['state']=='REPLACED' and f==before
    assert all(Path(s['local_path']).is_file() for s in out['raw_sources'])
    (tmp_path/'REPLACEMENT_BUSINESS_INVARIANT.json').write_text(json.dumps(dict(synthetic=True,
        request=data[2],context=data[3],tactical=data[4],identities=data[5],native_canonical_seed=data[1],
        portfolio_facts_source=data[7](),expected_scope=out['scope_candidate'],
        capacity=cap,cash=cash,replay=replay),indent=2))


def test_legacy_snapshot_without_replacements_is_exact_and_unmodified(tmp_path):
    *_,facts,desc=original_case(tmp_path);request=original_case(tmp_path)[2];before=deepcopy(facts)
    result,receipt=reconcile(facts,request)
    assert result==facts['orders'] and receipt is None and facts==before


@pytest.mark.parametrize('remaining',['1','6','10'])
def test_partial_fills_stay_in_position_and_unique_execution_is_counted_once(tmp_path,remaining):
    data=case(tmp_path,filled='4',remaining=remaining);data[6]['fills'].append(deepcopy(data[6]['fills'][0]))
    out,cap=build(tmp_path,data)
    assert cap['occupied']==str(65+int(remaining))
    assert out['original_observations']['order_replacement_replay']['chains'][0]['unique_fill_ids']==['SYNTHETIC_FILL']


def test_multistep_chain_retires_all_predecessors_but_only_latest_reserves(tmp_path):
    data=case(tmp_path);facts=data[6];middle=facts['orders'][1];last=deepcopy(middle)
    last.update(event_id='SYNTHETIC_LAST',broker_order_id='SYNTHETIC_LAST_ORDER',order_quantity='4',remaining_quantity='4')
    middle.update(state='REPLACED',remaining_quantity='0',last_acknowledged_commitment=dict(
        order_quantity='6',commitment_price='1',source_reference='SYNTHETIC_SECOND_ACK',as_of=data[2]['evaluation_at']))
    facts['orders'].append(last);facts['replacement_confirmations'].append(data[8](middle,last,'SYNTHETIC_SECOND_ACK'))
    out,cap=build(tmp_path,data);assert cap['occupied']=='69'
    assert out['original_observations']['order_replacement_replay']['chains'][0]['events']==['SYNTHETIC_BUY','SYNTHETIC_NEW','SYNTHETIC_LAST']


def test_same_broker_order_id_requires_distinct_explicit_revisions(tmp_path):
    data=case(tmp_path);old,new=data[6]['orders'];new.update(broker_order_id=old['broker_order_id'],broker_revision_id='2')
    data[6]['replacement_confirmations']=[data[8]()]
    _,cap=build(tmp_path,data);assert cap['occupied']=='71'


@pytest.mark.parametrize('state',['CANCELLED','REJECTED','EXPIRED'])
def test_terminal_successor_has_no_remaining_order_but_does_not_unlock_reserved_cash(tmp_path,state):
    data=case(tmp_path);data[6]['orders'][1].update(state=state,order_quantity='6',remaining_quantity='0')
    terminal_ack(data[6]['orders'][1],data)
    out,cap=build(tmp_path,data)
    assert cap['occupied']=='65' and out['scope_candidate']['funding_buckets'][0]['cash_amount']=='40'


def test_filled_successor_requires_complete_cumulative_fills_and_positions(tmp_path):
    data=case(tmp_path,filled='4',remaining='0');data[6]['orders'][1]['state']='FILLED'
    _,cap=build(tmp_path,data);assert cap['occupied']=='65'


@pytest.mark.parametrize('field',['client_id','run_id','evaluation_at','owner','asset_id','intent_id','source_db_sha256','schema_version'])
def test_foreign_account_run_database_asset_or_intent_proof_rejected(tmp_path,field):
    data=case(tmp_path);change(data[6]['replacement_confirmations'][0],lambda d:d.update({field:'OTHER'}))
    with pytest.raises((PermissionError,ValueError)):build(tmp_path,data)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(evidence_state='UNKNOWN'),lambda d:d.update(unfilled_commitment_transferred=False),
    lambda d:d.update(source_reference=''),lambda d:d.update(confirmed_at='2099-01-01T00:00:00Z'),
    lambda d:d.update(available_at='2099-01-01T00:00:00Z'),
    lambda d:d.update(predecessor_event_id='MISSING'),lambda d:d.update(successor_event_id='MISSING'),
    lambda d:d['successor_order_key'].update(broker_order_id='OTHER')])
def test_unverified_future_or_unbound_successor_never_retires_old_commitment(tmp_path,mutate):
    data=case(tmp_path);change(data[6]['replacement_confirmations'][0],mutate)
    with pytest.raises((PermissionError,ValueError)):build(tmp_path,data)


@pytest.mark.parametrize('mutate',[
    lambda f:f.update(replacement_confirmations=[]),lambda f:f['orders'].pop(),
    lambda f:f['orders'][0].pop('last_acknowledged_commitment'),
    lambda f:f['orders'][0]['last_acknowledged_commitment'].update(order_quantity='1'),
    lambda f:f['orders'][1].update(filled_quantity_basis='PER_ORDER'),
    lambda f:f['orders'][1].update(side='SELL'),lambda f:f['orders'][1].update(account='OTHER'),
    lambda f:f['orders'][1].update(intent_id='OTHER'),lambda f:f['coverage'].update(orders_complete=False),
    lambda f:f['coverage'].update(fills_reconciled=False)])
def test_missing_original_lifecycle_or_fill_scope_blocks_assembly(tmp_path,mutate):
    data=case(tmp_path);mutate(data[6])
    with pytest.raises((PermissionError,ValueError)):build(tmp_path,data)


def test_acknowledgment_bytes_are_rechecked_and_registered_in_native_sources(tmp_path):
    data=case(tmp_path);out,_=build(tmp_path,data);source=data[6]['replacement_confirmations'][0]
    assert any(r['sha256']==source['sha256'] for r in out['raw_sources'])
    Path(source['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):build(tmp_path,data)


def test_identical_confirmation_and_order_rows_do_not_double_count(tmp_path):
    data=case(tmp_path);facts=data[6];facts['replacement_confirmations'].append(deepcopy(facts['replacement_confirmations'][0]));facts['orders'].append(deepcopy(facts['orders'][1]))
    _,cap=build(tmp_path,data);assert cap['occupied']=='71'


def test_successor_larger_than_reserved_cash_is_rejected_by_original_cash_guard(tmp_path):
    data=case(tmp_path,remaining='20')
    with pytest.raises(ValueError,match='CASH_RESERVATION_RECONCILIATION_REQUIRED'):build(tmp_path,data)


def test_replacement_does_not_allow_second_release_against_retired_event(tmp_path):
    data=case(tmp_path);data[6]['confirmed_releases']=[{'releases_event_id':'SYNTHETIC_BUY'}]
    with pytest.raises(ValueError,match='CANNOT_BE_RELEASED_AGAIN'):build(tmp_path,data)


def test_missing_fill_execution_or_reset_cumulative_counter_is_rejected(tmp_path):
    data=case(tmp_path,filled='4');data[6]['fills']=[]
    with pytest.raises(ValueError,match='FILLS_NOT_RECONCILED'):build(tmp_path,data)
    data=case(tmp_path,filled='4');data[6]['orders'][1]['filled_quantity']='0'
    with pytest.raises(ValueError,match='FILL_REGRESSION'):build(tmp_path,data)


def test_native_consumer_rechecks_the_confirmation_after_source_assembly(tmp_path):
    from deployment_c7_sources import family_scope_source,FAMILY_PROFILE
    data=case(tmp_path);out,_=build(tmp_path,data)
    context={'family_c7_profile':FAMILY_PROFILE,'family_c7_scope_source':out['source_descriptor']}
    assert family_scope_source(data[2],context)['family_scope']==out['scope_candidate']
    Path(data[6]['replacement_confirmations'][0]['local_path']).write_text('TAMPERED')
    with pytest.raises(PermissionError,match='ORIGINAL_SOURCE_BYTES_CHANGED'):family_scope_source(data[2],context)


def test_conflicting_duplicate_confirmations_are_not_idempotent(tmp_path):
    data=case(tmp_path);source=data[6]['replacement_confirmations'][0]
    path=tmp_path/'CONFLICTING_ACK.json';path.write_text(Path(source['local_path']).read_text())
    second=dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),retrieved_at=source['retrieved_at'])
    change(second,lambda d:d.update(successor_event_id='OTHER'));data[6]['replacement_confirmations'].append(second)
    with pytest.raises(ValueError,match='CONFLICTING_CONFIRMATION'):build(tmp_path,data)


def test_forks_and_duplicate_broker_order_versions_cannot_claim_two_successors(tmp_path):
    data=case(tmp_path);f=data[6];extra=deepcopy(f['orders'][1]);extra['event_id']='SECOND_LABEL'
    f['orders'].append(extra)
    with pytest.raises(ValueError,match='BROKER_ORDER_VERSION_DUPLICATED'):build(tmp_path,data)
    extra['broker_order_id']='SYNTHETIC_OTHER_SUCCESSOR';f['replacement_confirmations'].append(data[8](f['orders'][0],extra,'FORK_ACK'))
    with pytest.raises(ValueError,match='FORK_OR_MERGE'):build(tmp_path,data)


def test_cyclic_replacement_book_is_rejected(tmp_path):
    data=case(tmp_path);f=data[6];old,new=f['orders'];new.update(state='REPLACED',remaining_quantity='0',
        last_acknowledged_commitment=dict(order_quantity='6',commitment_price='1',source_reference='SYNTHETIC_CYCLE_ACK',as_of=data[2]['evaluation_at']))
    f['replacement_confirmations'].append(data[8](new,old,'SYNTHETIC_CYCLE_ACK'))
    with pytest.raises(ValueError,match='CYCLIC_LINEAGE'):build(tmp_path,data)


def test_regressed_confirmation_time_in_serial_chain_is_rejected(tmp_path):
    data=case(tmp_path);f=data[6];middle=f['orders'][1];last=deepcopy(middle)
    last.update(event_id='LAST',broker_order_id='LAST',order_quantity='4',remaining_quantity='4')
    middle.update(state='REPLACED',remaining_quantity='0',last_acknowledged_commitment=dict(
        order_quantity='6',commitment_price='1',source_reference='EARLIER_ACK',as_of='2026-09-25T00:00:00Z'))
    f['orders'].append(last);proof=data[8](middle,last,'EARLIER_ACK')
    change(proof,lambda d:d.update(confirmed_at='2026-09-25T00:00:00Z'));f['replacement_confirmations'].append(proof)
    with pytest.raises(ValueError,match='ACKNOWLEDGMENT_ORDER_CONFLICT'):build(tmp_path,data)


@pytest.mark.parametrize('state',['CANCEL_PENDING','REPLACE_PENDING'])
def test_successor_pending_request_preserves_last_broker_ack_guard(tmp_path,state):
    data=case(tmp_path);data[6]['orders'][1]['state']=state
    with pytest.raises(ValueError,match='PENDING_COMMITMENT_REDUCTION_UNCONFIRMED'):build(tmp_path,data)


@pytest.mark.parametrize('field,value',[('remaining_quantity','99'),('filled_quantity',True),('filled_quantity','NaN')])
def test_impossible_predecessor_counters_cannot_be_discarded_as_retired(tmp_path,field,value):
    data=case(tmp_path);data[6]['orders'][0][field]=value
    with pytest.raises(ValueError):build(tmp_path,data)


@pytest.mark.parametrize('state',['CANCELLED','REJECTED','EXPIRED'])
def test_ordinary_terminal_orders_preserve_total_quantity_and_cash_reservation(tmp_path,state):
    fixture=original_case(tmp_path);fixture[6]['orders'][0].update(state=state,remaining_quantity='0')
    terminal_ack(fixture[6]['orders'][0],fixture)
    out,cap=build(tmp_path,fixture)
    assert cap['occupied']=='65' and out['scope_candidate']['funding_buckets'][0]['reserved_amount']=='10'


@pytest.mark.parametrize('state',['FILLED','CANCELLED','REJECTED','EXPIRED'])
def test_terminal_successor_with_remaining_shares_does_not_clear_order(tmp_path,state):
    data=case(tmp_path);data[6]['orders'][1]['state']=state
    with pytest.raises(ValueError,match='TERMINAL_ORDER_REMAINING_CONFLICT'):build(tmp_path,data)


@pytest.mark.parametrize('which',['predecessor','successor','proof'])
def test_replacement_commitment_currency_is_explicit_and_never_inferred_from_account(tmp_path,which):
    data=case(tmp_path)
    if which=='proof':change(data[6]['replacement_confirmations'][0],lambda d:d.update(currency='USD'))
    else:data[6]['orders'][0 if which=='predecessor' else 1]['currency']='USD'
    with pytest.raises(PermissionError,match='ACCOUNT_ASSET_OR_INTENT_CONFLICT'):build(tmp_path,data)


@pytest.mark.parametrize('field,value',[
    ('evidence_state','UNKNOWN'),('broker_order_id','OTHER'),('owner',{}),('currency','USD'),
    ('asset_id','OTHER'),('final_state','OPEN'),('confirmed_at','2099-01-01T00:00:00Z'),
    ('available_at','2099-01-01T00:00:00Z'),('filled_quantity','1')])
def test_zero_remaining_terminal_order_requires_exact_known_broker_confirmation(tmp_path,field,value):
    data=case(tmp_path);order=data[6]['orders'][1];order.update(state='CANCELLED',remaining_quantity='0');terminal_ack(order,data)
    order['terminal_acknowledgment'][field]=value
    with pytest.raises((PermissionError,ValueError)):build(tmp_path,data)


def test_unconfirmed_terminal_counter_does_not_unlock_exposure(tmp_path):
    data=case(tmp_path);data[6]['orders'][1].update(state='CANCELLED',remaining_quantity='0')
    with pytest.raises(PermissionError,match='ACKNOWLEDGMENT_REQUIRED'):build(tmp_path,data)


def test_partial_terminal_successor_keeps_predecessor_executions_in_current_position(tmp_path):
    data=case(tmp_path,filled='4',remaining='6');order=data[6]['orders'][1]
    order.update(state='CANCELLED',remaining_quantity='0');terminal_ack(order,data)
    _,cap=build(tmp_path,data);assert cap['occupied']=='65'


def test_ordinary_partial_terminal_requires_linked_execution_receipts(tmp_path):
    data=original_case(tmp_path);order=data[6]['orders'][0]
    order.update(state='CANCELLED',remaining_quantity='0',filled_quantity='4');terminal_ack(order,data)
    with pytest.raises(ValueError,match='EXECUTIONS_NOT_RECONCILED'):build(tmp_path,data)
    data[6]['fills']=[dict(fill_id='SYNTHETIC_TERMINAL_FILL',order_event_id=order['event_id'],account=order['account'],
        asset_id=order['asset_id'],quantity='4',applied_to_position_id='SYNTHETIC_POSITION',economic_effect_id='SYNTHETIC_POSITION_EFFECT')]
    _,cap=build(tmp_path,data);assert cap['occupied']=='65'
