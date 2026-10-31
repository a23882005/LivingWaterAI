from copy import deepcopy
from decimal import Decimal
import sys
import pytest
from test_native_adapters import ROOT
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.daily_slice import (maturity,speed,trend_timing,cycle_id,open_cycle,
    cycle_room,update_intent,CycleLedgerStore)

OWNER={'client_id':'SYNTHETIC','broker':'SYNTHETIC','account':'A','currency':'USD','funding_domain':'US_DIRECT'}
AT='2026-10-30T20:00:00Z';SESSION='2026-10-30'


def slots(true=3,unknown=0):
    return [{'id':'M'+str(i+1),'truth':'TRUE' if i<true else 'UNKNOWN' if i<true+unknown else 'FALSE'} for i in range(8)]


def rates(mode='Left Overweight',signals=None,**kw):
    args=dict(mode=mode,maturity_result=maturity(signals if signals is not None else slots()),
        credit_level=0,core_etf='TRUE',high_beta='FALSE',macro_pressure='FALSE',extreme_valuation='OFF')
    args.update(kw);return speed(**args)


def new_cycle(gap='150000',speed_result=None,session=SESSION,**kw):
    args=dict(owner=OWNER,session_id=session,exchange='SYNTHETIC_X',asset_id='SYNTHETIC',opened_at=AT,
        gap=gap,speed_result=speed_result or rates(),permission=True,exposure_reconciled=True,session_open=True)
    args.update(kw);return open_cycle(**args)


def room(cycle,**kw):
    args=dict(speed_result=rates(),permission=True,trend_allowed=True,session_id=SESSION,session_open=True)
    args.update(kw);return cycle_room(cycle,**args)


def event(cycle,iid='I1',eid='E1',state='PLANNED',filled='0',remaining='37500',**kw):
    receipt={'owner':OWNER,'asset_id':'SYNTHETIC','source_reference':'SYNTHETIC_RECONCILIATION',
        'source_hash':'SYNTHETIC_HASH','as_of':AT,'available_at':AT,'release_confirmed':state in ('CANCELLED','EXPIRED','REJECTED','LOCAL_RELEASED','FILLED')}
    args=dict(event_id=eid,intent_id=iid,state=state,filled_amount=filled,remaining_amount=remaining,
        receipt=receipt,evaluation_at=AT,speed_result=rates(),permission=True,session_id=SESSION,session_open=True)
    args.update(kw);return update_intent(cycle,**args)


def test_eight_canonical_slots_deduplicate_and_count_unknown_only_when_relevant():
    s=slots(2,1);assert maturity(s)['state']=='UNKNOWN'
    assert maturity(slots(3,5))['state']=='MATURE'
    assert maturity(slots(1,1))['state']=='IMMATURE'
    s.append(deepcopy(s[0]));assert maturity(s)['true_count']==2
    s.append({'id':'M1','truth':'FALSE'});assert 'M1' in maturity(s)['duplicate_conflicts']
    with pytest.raises(ValueError,match='UNREGISTERED'):maturity([{'id':'M9','truth':'TRUE'}])


@pytest.mark.parametrize('mode,immature,mature',[
    ('Base Deployment','0.1','0.2'),('Left Overweight','0.15','0.25'),
    ('Right Confirmation','0.25','0.25'),('Trend Deployment','0.2','0.2')])
def test_approved_mode_rates_and_unknown_maturity_dependence(mode,immature,mature):
    assert rates(mode,slots(0))['mode_rate']==immature
    assert rates(mode,slots(3))['mode_rate']==mature
    result=rates(mode,slots(2,1))
    assert result['mode_rate']==(None if mode in ('Base Deployment','Left Overweight') else mature)


def test_left_mature_and_immature_positive_37500_and_22500_cycles():
    assert new_cycle()['B0']=='37500.00'
    assert Decimal(new_cycle(speed_result=rates(signals=slots(0)))['B0'])==22500
    assert new_cycle(speed_result=rates(signals=slots(2,1))) is None


def test_approved_credit_macro_and_valuation_multipliers_do_not_change_target():
    assert rates(credit_level=1)['credit_multiplier']=='0.75'
    assert rates(credit_level=2)['credit_multiplier']=='0.5'
    assert rates(credit_level=2,high_beta='TRUE')['credit_multiplier']=='0'
    assert rates(credit_level=2,core_etf='UNKNOWN')['credit_multiplier'] is None
    assert rates('Right Confirmation',credit_level=2)['credit_multiplier']=='0'
    assert rates(credit_level=3)['credit_multiplier']=='0'
    assert rates(macro_pressure='TRUE')['macro_multiplier']=='0.75'
    assert rates(macro_pressure='UNKNOWN')['macro_multiplier'] is None
    assert rates('Base Deployment',extreme_valuation='ON')['valuation_multiplier']=='0.5'
    assert rates('Trend Deployment',extreme_valuation='UNKNOWN')['valuation_multiplier'] is None
    assert rates('Left Overweight',extreme_valuation='UNKNOWN')['valuation_multiplier']=='1'


def timing(**kw):
    args=dict(bars=[{'Open':'100','High':'101','Low':'99','Close':'100'}]*5,
        ma5='100',ma10='100',ma20='100',previous_atr14='2',previous_close='100',
        breakout_retest_success='FALSE',current_up='TRUE',previous_up='TRUE')
    args.update(kw);return trend_timing(**args)


def test_trend_extreme_exact_boundary_and_unknown_entry_are_local_to_new_slice():
    assert timing()['truth']=='TRUE'
    bars=[{'Open':'100','High':'105','Low':'100','Close':'104'}]*5
    out=timing(bars=bars,previous_atr14='2.5',previous_close='100')
    assert out['extreme_bull_bar']=='TRUE' and out['truth']=='FALSE'
    assert out['mode_stage_target_gap_changed'] is False
    out=timing(ma5=None,ma10=None,ma20=None,previous_up='UNKNOWN',breakout_retest_success='UNKNOWN')
    assert out['truth']=='UNKNOWN'
    bars=[{'Open':'100','High':'100','Low':'100','Close':'100'}]*5
    assert timing(bars=bars)['extreme_bull_bar']=='FALSE'


def test_fixed_G0_fill10_leaves15_not_12_5():
    c=new_cycle('100');c=event(c,remaining='25')
    c=event(c,eid='FILL',state='PARTIAL_FILL',filled='10',remaining='15')
    assert Decimal(room(c)['cycle_spent'])==10 and Decimal(room(c)['cycle_committed'])==15
    c=event(c,eid='CANCEL',state='CANCELLED',filled='10',remaining='0')
    assert Decimal(room(c)['cycle_room'])==15
    assert c['G0']=='100' and Decimal(c['B0'])==25


def test_cancel_request_keeps_commitment_and_confirmation_alone_releases():
    c=event(new_cycle())
    c=event(c,eid='REQUEST',state='CANCEL_PENDING')
    assert Decimal(room(c)['cycle_committed'])==37500 and Decimal(room(c)['cycle_room'])==0
    receipt={**c['intents']['I1']['receipt'],'release_confirmed':False}
    with pytest.raises(ValueError,match='RELEASE_CONFIRMATION'):
        event(c,eid='BAD',state='CANCELLED',remaining='0',receipt=receipt)
    c=event(c,eid='CONFIRMED',state='CANCELLED',remaining='0')
    assert Decimal(room(c)['cycle_room'])==37500
    c=event(c,iid='I2',eid='REUSE');assert Decimal(room(c)['cycle_room'])==0


def test_idempotent_intents_and_events_cannot_renew_daily_budget():
    c=new_cycle();first=event(c);assert event(first)==first
    with pytest.raises(ValueError,match='IDEMPOTENCY'):event(first,remaining='100')
    with pytest.raises(ValueError,match='EXCEEDS_ROOM'):event(first,iid='I2',eid='E2',remaining='1')
    assert cycle_id(owner=OWNER,session_id=SESSION,exchange='SYNTHETIC_X',asset_id='SYNTHETIC')==c['slice_cycle_id']
    # No run_id is accepted by the cycle identity function.
    assert 'run_id' not in c


def test_durable_store_same_session_target_increase_cannot_mutate_G0_or_B0(tmp_path):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True);c=new_cycle();store.save(c,expected_revision=None)
    assert CycleLedgerStore(store.path).get(c['slice_cycle_id'])==c
    raised=new_cycle('300000')
    with pytest.raises(ValueError,match='CAS_CONFLICT'):store.save(raised,expected_revision=None)
    raised['revision']=1
    with pytest.raises(ValueError,match='INITIAL_FACTS_IMMUTABLE'):store.save(raised,expected_revision=0)
    assert store.get(c['slice_cycle_id'])['G0']=='150000'
    committed=event(c);store.save(committed,expected_revision=0)
    with pytest.raises(ValueError,match='CAS_CONFLICT'):store.save(event(c,iid='OTHER'),expected_revision=0)


def test_ledger_fill_and_event_history_cannot_be_reset_by_direct_storage(tmp_path):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True);c=new_cycle('100');store.save(c,expected_revision=None)
    c=event(c,state='PARTIAL_FILL',filled='10',remaining='15');store.save(c,expected_revision=0)
    changed=deepcopy(c);changed['revision']+=1;changed['intents']['I1']['filled_amount']='0'
    with pytest.raises(ValueError,match='FILL_MUST_NOT_DECREASE'):store.save(changed,expected_revision=1)
    changed=deepcopy(c);changed['revision']+=1;changed['events']={}
    with pytest.raises(ValueError,match='HISTORY_CANNOT_BE_RESET'):store.save(changed,expected_revision=1)


def test_closed_session_keeps_gtc_and_next_session_cannot_steal_old_intent(tmp_path):
    store=CycleLedgerStore(tmp_path/'planning.sqlite',create=True);c=new_cycle();store.save(c,expected_revision=None)
    c=event(c);store.save(c,expected_revision=0)
    assert room(c,session_id='2026-11-02')['cycle_room']=='0'
    assert room(c,session_open=False)['cycle_committed']=='37500'
    next_cycle=new_cycle('112500',session='2026-11-02')
    # New G0 is supplied from the already reconciled global Active exposure.
    next_cycle=event(next_cycle,session_id='2026-11-02',remaining='100')
    with pytest.raises(ValueError,match='ANOTHER_CYCLE'):store.save(next_cycle,expected_revision=None)


def test_known_prohibition_keeps_unknown_speed_fields_but_new_room_zero():
    c=new_cycle();s=rates(macro_pressure='UNKNOWN')
    assert room(c,speed_result=s)['cycle_room'] is None
    assert room(c,speed_result=s,permission=False)['cycle_room']=='0'
    assert s['macro_multiplier'] is None
    with pytest.raises(ValueError,match='SOURCE_UNAVAILABLE'):CycleLedgerStore('/tmp/nonexistent-v82-source-20261030.sqlite')


def test_reconciliation_receipt_cannot_cross_owner_or_arrive_after_cutoff():
    c=new_cycle();r={'owner':{**OWNER,'account':'B'},'asset_id':'SYNTHETIC','source_reference':'SYNTHETIC',
        'source_hash':'SYNTHETIC','as_of':AT,'available_at':AT}
    with pytest.raises(ValueError,match='OWNER_ASSET'):event(c,receipt=r)
    r['owner']=OWNER;r['available_at']='2026-10-31T00:00:00Z'
    with pytest.raises(ValueError,match='NOT_AVAILABLE'):event(c,receipt=r)
