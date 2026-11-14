"""PM V82-CYCLE-PENDING-RELEASE: pending events cannot release daily room."""
from copy import deepcopy
from decimal import Decimal
import pytest
from test_v10_daily_slice import new_cycle,event,room,rates
from livingwater_v82_runtime.daily_slice import CycleLedgerStore


def opened(filled='0'):
    cycle=event(new_cycle('100'),eid='PLAN',remaining='25')
    cycle=event(cycle,eid='OPEN',state='OPEN',remaining='25')
    if filled!='0':
        cycle=event(cycle,eid='PARTIAL',state='PARTIAL_FILL',filled=filled,
            remaining=str(Decimal(25)-Decimal(filled)))
    return cycle


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
@pytest.mark.parametrize('filled',['0','10'])
@pytest.mark.parametrize('shrink',['ZERO','PARTIAL'])
def test_pending_full_or_partial_unconfirmed_shrink_is_rejected(pending,filled,shrink):
    cycle=opened(filled);before=deepcopy(cycle)
    remaining='0' if shrink=='ZERO' else str(Decimal(24)-Decimal(filled))
    with pytest.raises(ValueError,match='UNCONFIRMED_COMMITMENT_REDUCTION'):
        event(cycle,eid='MALFORMED_PENDING',state=pending,filled=filled,remaining=remaining)
    assert cycle==before and Decimal(room(cycle)['cycle_room'])==0


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
def test_release_flag_alone_cannot_make_a_pending_reduction_confirmed(pending):
    cycle=opened();receipt={**cycle['intents']['I1']['receipt'],'release_confirmed':True}
    with pytest.raises(ValueError,match='UNCONFIRMED_COMMITMENT_REDUCTION'):
        event(cycle,eid='FLAG_WITHOUT_CONFIRMED_STATE',state=pending,remaining='0',receipt=receipt)


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
def test_high_precision_unconfirmed_shrink_cannot_round_back_to_previous_total(pending):
    with pytest.raises(ValueError,match='UNCONFIRMED_COMMITMENT_REDUCTION'):
        event(opened(),eid='PRECISE_DROP',state=pending,
            remaining='24.99999999999999999999999999999999999999')


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
@pytest.mark.parametrize('terminal',['CANCELLED','EXPIRED','REJECTED'])
def test_verified_fill_transfers_commitment_to_spent_and_confirmed_release_is_idempotent(
        tmp_path,pending,terminal):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True)
    cycle=opened();store.save(cycle,expected_revision=None)
    old_revision=cycle['revision']
    cycle=event(cycle,eid='PENDING',state=pending,remaining='25')
    store.save(cycle,expected_revision=old_revision)
    old_revision=cycle['revision']
    cycle=event(cycle,eid='FILL_WHILE_PENDING',state=pending,filled='10',remaining='15')
    store.save(cycle,expected_revision=old_revision)
    worker=CycleLedgerStore(store.path);saved=worker.get(cycle['slice_cycle_id'])
    assert saved==cycle
    assert event(saved,eid='FILL_WHILE_PENDING',state=pending,filled='10',remaining='15')==saved
    assert (Decimal(room(saved)['cycle_spent']),Decimal(room(saved)['cycle_committed']),
        Decimal(room(saved)['cycle_room']))==(10,15,0)
    assert saved['G0']=='100' and Decimal(saved['B0'])==25
    released=event(saved,eid='CONFIRMED_RELEASE',state=terminal,filled='10',remaining='0')
    worker.save(released,expected_revision=saved['revision'])
    assert Decimal(room(released)['cycle_spent'])==10 and Decimal(room(released)['cycle_room'])==15
    assert event(released,eid='CONFIRMED_RELEASE',state=terminal,filled='10',remaining='0')==released
    reused=event(released,iid='I2',eid='REUSE_RELEASED_ONLY',remaining='15')
    worker.save(reused,expected_revision=released['revision'])
    worker.save(deepcopy(reused),expected_revision=reused['revision'])
    assert CycleLedgerStore(store.path).get(reused['slice_cycle_id'])==reused
    assert Decimal(room(reused)['cycle_room'])==0
    with pytest.raises(ValueError,match='EXCEEDS_ROOM'):
        event(reused,iid='I3',eid='CANNOT_REUSE_TWICE',remaining='1')


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
@pytest.mark.parametrize('filled',['0','10'])
@pytest.mark.parametrize('shrink',['ZERO','PARTIAL'])
def test_direct_sqlite_save_rejects_the_same_unconfirmed_reduction(tmp_path,pending,filled,shrink):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True)
    cycle=opened(filled);store.save(cycle,expected_revision=None)
    changed=deepcopy(cycle);changed['revision']+=1
    intent=changed['intents']['I1'];intent['state']=pending
    intent['remaining_amount']='0' if shrink=='ZERO' else str(Decimal(24)-Decimal(filled))
    intent['receipt']['release_confirmed']=False
    with pytest.raises(ValueError,match='UNCONFIRMED_COMMITMENT_REDUCTION'):
        store.save(changed,expected_revision=cycle['revision'])
    assert CycleLedgerStore(store.path).get(cycle['slice_cycle_id'])==cycle


@pytest.mark.parametrize('terminal',['CANCELLED','EXPIRED','REJECTED','LOCAL_RELEASED','FILLED'])
def test_direct_storage_cannot_bypass_release_confirmation(tmp_path,terminal):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True)
    cycle=opened();store.save(cycle,expected_revision=None)
    changed=deepcopy(cycle);changed['revision']+=1
    changed['intents']['I1'].update(state=terminal,remaining_amount='0')
    changed['intents']['I1']['receipt']['release_confirmed']=False
    with pytest.raises(ValueError,match='RELEASE_CONFIRMATION_REQUIRED'):
        store.save(changed,expected_revision=cycle['revision'])
    assert store.get(cycle['slice_cycle_id'])==cycle


@pytest.mark.parametrize('live',['OPEN','PARTIAL_FILL'])
def test_relabeling_a_pending_event_as_another_live_state_cannot_release_room(live):
    cycle=event(opened(),eid='PENDING',state='CANCEL_PENDING',remaining='25')
    with pytest.raises(ValueError,match='UNCONFIRMED_COMMITMENT_REDUCTION'):
        event(cycle,eid='RELABEL',state=live,remaining='0')


@pytest.mark.parametrize('pending',['CANCEL_PENDING','REPLACE_PENDING'])
def test_lower_current_speed_does_not_release_existing_pending_commitment(pending):
    cycle=event(opened(),eid='PENDING',state=pending,remaining='25')
    slower=rates(macro_pressure='TRUE')
    cycle=event(cycle,eid='FILL',state=pending,filled='10',remaining='15',speed_result=slower)
    assert Decimal(room(cycle,speed_result=slower)['cycle_committed'])==15
    assert Decimal(room(cycle,speed_result=slower)['cycle_room'])==0
    assert Decimal(cycle['B0'])==25 and cycle['G0']=='100'
