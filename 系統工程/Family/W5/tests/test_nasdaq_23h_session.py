"""T01-T11 synthetic compatibility proofs; no live venue/account permission."""
from copy import deepcopy
from datetime import date,datetime,timedelta
from hashlib import sha256
from pathlib import Path
from decimal import Decimal as D
from zoneinfo import ZoneInfo
import json,sys
import pytest
from test_native_adapters import ROOT
sys.path[:0]=[str(ROOT/'系統工程/Family/W5'),str(ROOT/'系統工程/Family/W8'),str(ROOT/'系統工程/Family/W8/tests'),str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src')]
from market_session_source import read,prepare,GATES
from livingwater_v82_runtime.daily_slice import open_cycle,cycle_room,update_intent,CycleLedgerStore
from test_v10_daily_slice import OWNER,rates


def source(tmp_path,*,venue='NASDAQ',start='2026-12-03',end='2026-12-29',unknown_gate=None,transition=True):
    original=tmp_path/'SYNTHETIC_RULE_CALENDAR.txt';original.write_text('SYNTHETIC ONLY; not an activation, SIP, broker, data-feed or account qualification.')
    h=sha256(original.read_bytes()).hexdigest();proof=dict(assurance='SYNTHETIC',available_at='2026-01-01T00:00:00Z',source_hash=h)
    days=[];first=date.fromisoformat(start);last=date.fromisoformat(end)
    for i in range((last-first).days+1):
        day=first+timedelta(days=i);row=dict(date=str(day),state='CLOSED')
        if day.weekday()<5 and str(day) not in ('2026-12-25','2026-11-26'):
            prev=day-timedelta(days=1);offset=datetime(day.year,day.month,day.day,12,tzinfo=ZoneInfo('America/New_York')).strftime('%z');offset=offset[:3]+':'+offset[3:]
            row.update(state='OPEN',night_start_at=f'{prev}T{21 if venue=="NASDAQ" else 20}:00:00{offset}',
                night_end_at=f'{day}T'+('04:00:00' if venue=='NASDAQ' else '03:50:00')+offset,
                day_start_at=f'{day}T04:00:00{offset}',rth_open_at=f'{day}T09:30:00{offset}',
                rth_close_at=f'{day}T16:00:00{offset}',day_end_at=f'{day}T20:00:00{offset}')
            if transition:row['day_transition_end_at']=f'{day}T04:00:01{offset}'
        days.append(row)
    data=dict(schema_version='Family.W5.MarketSessionSource.v1',owner=OWNER,asset_id='QQQ',source_db_sha256='a'*64,
        source_reference='SYNTHETIC_OPERATOR_SOURCE',available_at='2026-01-01T00:00:00Z',execution_venue=venue,
        planning_exchange='NASDAQ',contract_id=123456,rules_profile='NASDAQ_23H_20261206' if venue=='NASDAQ' else 'IBKR_OVERNIGHT_CURRENT',
        originals=[dict(local_path=str(original),sha256=h,source_reference='SYNTHETIC_NO_REAL_ASSURANCE',retrieved_at='2026-01-01T00:00:00Z')],
        calendar=dict(**proof,venue=venue,timezone='America/New_York',calendar_id='SYNTHETIC_NASDAQ_23H',version='SYNTHETIC1',coverage_from=start,coverage_through=end,days=days),
        readiness={k:dict(**proof,status='UNKNOWN' if k==unknown_gate else 'VERIFIED',asset_id='QQQ',owner=OWNER,contract_id=123456,execution_venue=venue,rules_profile='NASDAQ_23H_20261206' if venue=='NASDAQ' else 'IBKR_OVERNIGHT_CURRENT') for k in GATES})
    return write(tmp_path,data),data


def write(tmp_path,data):
    p=tmp_path/'session.json';p.write_text(json.dumps(data));return dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest())


def resolve(descriptor,at,**kw):
    return read(descriptor,identity=dict(owner=OWNER,asset_id='QQQ',source_db_sha256='a'*64,evaluation_at=at),allow_synthetic=kw.pop('allow_synthetic',True),**kw)


@pytest.mark.parametrize('at',['2026-12-06T21:00:00-05:00','2026-12-06T23:59:59-05:00','2026-12-07T00:00:01-05:00','2026-12-07T10:00:00+08:00','2026-12-07T02:00:00Z'])
def test_T01_T02_night_next_trade_date_and_timezone_invariance(tmp_path,at):
    desc,_=source(tmp_path);s,v=resolve(desc,at)
    assert s['session_id']=='2026-12-07' and s['exchange']=='NASDAQ' and s['open_for_planning']
    assert v['phase']=='NIGHT' and not v['daily_bar_date_relabelled']


def test_T01_announced_launch_does_not_mean_live_or_account_authorization(tmp_path):
    desc,_=source(tmp_path)
    s,v=resolve(desc,'2026-12-07T02:00:00Z',allow_synthetic=False)
    assert not s['open_for_planning'] and v['status']=='UNKNOWN'
    desc,_=source(tmp_path,start='2026-11-04',end='2026-11-10')
    s,v=resolve(desc,'2026-11-06T10:00:00-05:00')
    assert not s['open_for_planning'] and 'NASDAQ_23H_NOT_STARTED' in v['reason_codes']


@pytest.mark.parametrize('clock,phase,opened',[
    ('03:59:59','NIGHT',True),('04:00:00','DAY_TRANSITION',False),('04:00:01','PRE_MARKET',True),
    ('09:29:59','PRE_MARKET',True),('09:30:00','REGULAR',True),('09:30:01','REGULAR',True),
    ('15:59:59','REGULAR',True),('16:00:00','POST_MARKET',True),('16:00:01','POST_MARKET',True),
    ('19:59:59','POST_MARKET',True),('20:00:00','CLOSED',False),('20:00:01','CLOSED',False),
    ('20:59:59','CLOSED',False),('21:00:00','NIGHT',True),('21:00:01','NIGHT',True)])
def test_T03_half_open_boundaries(tmp_path,clock,phase,opened):
    desc,_=source(tmp_path);s,v=resolve(desc,'2026-12-07T'+clock+'-05:00')
    assert v['phase']==phase and s['open_for_planning']==opened
    if clock>='21:00:00':assert s['session_id']=='2026-12-08'


def test_T03_missing_4am_transition_is_unknown_and_IB_ATS_does_not_inherit_nasdaq_pause(tmp_path):
    desc,_=source(tmp_path,transition=False);s,v=resolve(desc,'2026-12-07T04:10:00-05:00')
    assert not s['open_for_planning'] and v['phase']=='TRANSITION_UNKNOWN'
    desc,_=source(tmp_path,venue='IBKR_ATS');s,v=resolve(desc,'2026-12-07T20:30:00-05:00')
    assert s['open_for_planning'] and v['phase']=='NIGHT' and s['session_id']=='2026-12-08'
    s,v=resolve(desc,'2026-12-08T03:50:00-05:00');assert not s['open_for_planning']


@pytest.mark.parametrize('at,opened',[
    ('2026-12-11T19:59:59-05:00',True),('2026-12-11T20:00:00-05:00',False),
    ('2026-12-11T21:00:00-05:00',False),('2026-12-12T10:00:00-05:00',False),
    ('2026-12-13T20:59:59-05:00',False),('2026-12-13T21:00:00-05:00',True),
    ('2026-12-24T21:00:00-05:00',False),('2026-12-25T10:00:00-05:00',False),('2026-12-27T21:00:00-05:00',True)])
def test_T04_weekends_and_explicit_holidays(tmp_path,at,opened):
    desc,_=source(tmp_path);s,_=resolve(desc,at);assert s['open_for_planning']==opened


def test_T04_early_close_and_DST_are_source_owned_not_weekday_guesses(tmp_path):
    desc,data=source(tmp_path);row=next(r for r in data['calendar']['days'] if r['date']=='2026-12-24')
    row.update(rth_close_at='2026-12-24T13:00:00-05:00',day_end_at='2026-12-24T17:00:00-05:00',early_close_source_reference='SYNTHETIC_EXPLICIT_EARLY_END')
    desc=write(tmp_path,data);assert resolve(desc,'2026-12-24T17:00:00-05:00')[1]['status']=='CLOSED'
    desc,_=source(tmp_path,start='2027-03-10',end='2027-03-17');s,_=resolve(desc,'2027-03-15T01:00:00Z')
    assert s['session_id']=='2027-03-15' and s['open_for_planning']
    s,v=resolve(desc,'2027-03-18T01:00:00Z');assert v['status']=='UNKNOWN' and not s['open_for_planning']


@pytest.mark.parametrize('gate',GATES)
def test_T07_T10_each_missing_real_layer_stays_unknown(tmp_path,gate):
    desc,_=source(tmp_path,unknown_gate=gate);s,v=resolve(desc,'2026-12-07T02:00:00Z')
    assert not s['open_for_planning'] and v['readiness_verified'][gate] is False


def test_T10_calendar_missing_day_hash_and_cross_household_are_rejected(tmp_path):
    desc,data=source(tmp_path);data['calendar']['days'].pop(2)
    with pytest.raises(ValueError,match='DAY_COVERAGE'):resolve(write(tmp_path,data),'2026-12-07T02:00:00Z')
    desc,data=source(tmp_path);Path(desc['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):resolve(desc,'2026-12-07T02:00:00Z')
    desc,data=source(tmp_path);data['owner']={**OWNER,'client_id':'OTHER'}
    with pytest.raises(PermissionError,match='OWNER_ASSET'):resolve(write(tmp_path,data),'2026-12-07T02:00:00Z')


def test_T05_original_cycle_lookup_restart_target_change_across_midnight_uses_one_B0(tmp_path):
    from v82_slice_bridge import ensure_cycle
    desc,_=source(tmp_path);store=CycleLedgerStore(tmp_path/'ledger.sqlite',create=True)
    identity=dict(owner=OWNER,asset_id='QQQ',snapshot_id='a'*64,evaluation_at='2026-12-06T23:59:59-05:00')
    base=dict(identity=identity,session_source=desc,planning_ledger_source=dict(owner=OWNER,planning_write_authorized=True,local_path=str(store.path),source_reference='SYNTHETIC'))
    analysis=dict(speed=rates(),trend_timing={'truth':'TRUE'})
    first=ensure_cycle(base,analysis,gap='100',permission=True,exposure_reconciled=True,execution_inputs_qualified=True,allow_synthetic_session=True)
    cycle=first['cycle_snapshot']['cycle'];assert D(cycle['B0'])==25;store.save(cycle,expected_revision=None)
    base['identity']['evaluation_at']='2026-12-07T00:00:01-05:00'
    later=ensure_cycle(base,analysis,gap='125',permission=True,exposure_reconciled=True,execution_inputs_qualified=True,allow_synthetic_session=True)
    assert later['cycle_snapshot']['cycle']==cycle and later['session']['session_id']=='2026-12-07'
    assert CycleLedgerStore(store.path).get(cycle['slice_cycle_id'])==cycle


def test_T06_T11_exchange_end_does_not_release_IB_commitment_or_resubmit(tmp_path):
    desc,_=source(tmp_path);s,v=resolve(desc,'2026-12-07T03:59:59-05:00')
    c=open_cycle(owner=OWNER,asset_id='QQQ',session_id=s['session_id'],exchange=s['exchange'],opened_at='2026-12-07T02:00:00Z',gap='100',speed_result=rates(),permission=True,exposure_reconciled=True,session_open=True)
    def event(c,e,state,filled,left,release=False):
        return update_intent(c,event_id=e,intent_id='SAME_IB_ORDER',state=state,filled_amount=filled,remaining_amount=left,
            receipt=dict(owner=OWNER,asset_id='QQQ',source_reference='SYNTHETIC_IB',source_hash='x',as_of='2026-12-07T08:00:00Z',available_at='2026-12-07T08:00:00Z',release_confirmed=release),
            evaluation_at='2026-12-07T08:00:00Z',speed_result=rates(),permission=True,session_id=s['session_id'],session_open=True)
    c=event(c,'open','OPEN','0','25');c=event(c,'partial','PARTIAL_FILL','10','15');pending=event(c,'pending','CANCEL_PENDING','10','15')
    assert cycle_room(pending,speed_result=rates(),permission=True,trend_allowed=True,session_id=s['session_id'],session_open=True)['cycle_committed']=='15'
    assert not resolve(desc,'2026-12-07T04:00:00-05:00')[0]['open_for_planning'] and not v['broker_order_release_inferred']
    with pytest.raises(ValueError,match='RELEASE'):event(pending,'exchange_end','CANCELLED','10','0')
    released=event(pending,'broker_ack','CANCELLED','10','0',True)
    assert event(released,'broker_ack','CANCELLED','10','0',True)==released
    assert len(released['intents'])==1


def test_T03_IB_ATS_does_not_require_Nasdaq_night_SIP_or_claim_SMART_daytime(tmp_path):
    desc,_=source(tmp_path,venue='IBKR_ATS',unknown_gate='sip_ready')
    assert resolve(desc,'2026-12-07T20:30:00-05:00')[0]['open_for_planning']
    assert not resolve(desc,'2026-12-07T10:00:00-05:00')[0]['open_for_planning']


def test_T05_T10_bound_family_session_replay_rejects_forged_wall_date(tmp_path):
    from v82_slice_bridge import bind
    from test_v10_family_cycle import family_case
    from test_v10_stock_integration import bind_context
    req,ctx,store,cycle=family_case(tmp_path)
    facts=req['native_bundle']['stock_evidence'];old=facts['approved_v10_context']
    # Keep the existing native identity, and only provide synthetic venue facts.
    desc,data=source(tmp_path);data.update(owner=req['owner'],source_db_sha256=old['identity']['snapshot_id'])
    
    for gate in data['readiness'].values():gate['owner']=req['owner']
    desc=write(tmp_path,data);old['identity']['evaluation_at']='2026-12-06T23:59:59-05:00';req['evaluation_at']=old['identity']['evaluation_at']
    old['session_source']=desc;old.update({k:v for k,v in prepare(old,allow_synthetic=True).items() if k in ('session','session_source_readback')})
    old['cycle_snapshot']={'status':'UNAVAILABLE','cycle':None};bind_context(facts,req['native_bundle']['producer_contract'])
    assert bind(ROOT,req,ctx)['session']['session_id']=='2026-12-07'
    old['session']['session_id']='2026-12-06'
    with pytest.raises(Exception,match='SESSION_SOURCE_REPLAY_MISMATCH'):bind(ROOT,req,ctx)


@pytest.mark.parametrize('kind',['NIGHT_QUOTE','INTRADAY_CHART'])
def test_T09_full_valid_daily_input_rejects_night_or_intraday_relabelling(tmp_path,kind):
    from types import SimpleNamespace
    from test_member_v82_analysis import MemberV82Tests
    from member_market_source import read_market
    fixture=SimpleNamespace(folder=tmp_path,at='2026-10-29T23:00:00Z')
    src=MemberV82Tests.market(fixture,symbol='QQQ')
    args=dict(symbol='QQQ',evaluation_at=fixture.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
    assert len(read_market(src,**args)['completed_rows'])==260
    if kind=='NIGHT_QUOTE':
        src['observation_kind']='NIGHT_QUOTE';reason='NIGHT_QUOTE_IS_NOT_DAILY'
    else:
        p=Path(src['local_path']);data=json.loads(p.read_text());data['chart']['result'][0]['meta']['dataGranularity']='1m'
        p.write_text(json.dumps(data));src['sha256']=sha256(p.read_bytes()).hexdigest();reason='INTRADAY_IS_NOT_COMPLETED_DAILY'
    with pytest.raises(ValueError,match=reason):read_market(src,**args)


def test_T06_local_planned_release_still_uses_original_local_confirmation():
    from test_v10_daily_slice import new_cycle,event,room
    c=event(new_cycle(gap='100'),remaining='25')
    out=event(c,eid='localrelease',state='LOCAL_RELEASED',remaining='0')
    assert room(out)['cycle_committed']=='0' and room(out)['cycle_room']=='25.00'


def test_T10_post_announcement_US_planning_keys_cannot_open_a_legacy_cycle_without_venue_source(tmp_path):
    from v82_slice_bridge import ensure_cycle
    for exchange in ('NASDAQ','ARCX','XNYS'):
        path=tmp_path/(exchange+'.sqlite');store=CycleLedgerStore(path,create=True)
        source=dict(identity=dict(owner=OWNER,asset_id='QQQ',snapshot_id='a'*64,evaluation_at='2026-12-07T02:00:00Z'),
            session=dict(session_id='2026-12-06',exchange=exchange,open_for_planning=True),
            planning_ledger_source=dict(owner=OWNER,planning_write_authorized=True,local_path=str(path),source_reference='SYNTHETIC'))
        out=ensure_cycle(source,dict(speed=rates(),trend_timing={'truth':'TRUE'}),gap='100',permission=True,exposure_reconciled=True,execution_inputs_qualified=True)
        assert out['cycle_snapshot']['cycle'] is None and out['cycle_snapshot']['status']=='QUALIFIED_SESSION_CALENDAR_REQUIRED'


def test_T10_post_launch_unknown_yahoo_granularity_is_not_assumed_daily(tmp_path):
    from types import SimpleNamespace
    from test_member_v82_analysis import MemberV82Tests
    from member_market_source import read_market
    src=MemberV82Tests.market(SimpleNamespace(folder=tmp_path,at='2026-10-29T23:00:00Z'),symbol='QQQ')
    with pytest.raises(ValueError,match='INTRADAY_IS_NOT_COMPLETED_DAILY'):
        read_market(src,symbol='QQQ',evaluation_at='2026-12-07T02:00:00Z',repo_root=ROOT,profile=None,is_etf=True)


def test_T06_out_of_order_native_fill_cannot_decrease_spent_or_release_commitment():
    from test_v10_daily_slice import new_cycle,event,room
    c=event(new_cycle(gap='100'),remaining='25');c=event(c,eid='partial',state='PARTIAL_FILL',filled='10',remaining='15')
    with pytest.raises(ValueError,match='FILL_MUST_NOT_DECREASE'):event(c,eid='late_fill',state='PARTIAL_FILL',filled='5',remaining='20')
    assert room(c)['cycle_spent']=='10' and room(c)['cycle_committed']=='15'


def test_T02_timezone_variants_produce_the_same_original_cycle_identity_and_B0(tmp_path):
    desc,_=source(tmp_path);cycles=[]
    for at in ('2026-12-06T21:00:00-05:00','2026-12-07T02:00:00Z','2026-12-07T10:00:00+08:00'):
        s,_=resolve(desc,at)
        cycles.append(open_cycle(owner=OWNER,asset_id='QQQ',session_id=s['session_id'],exchange=s['exchange'],opened_at=at,gap='100',speed_result=rates(),permission=True,exposure_reconciled=True,session_open=s['open_for_planning']))
    assert len({c['slice_cycle_id'] for c in cycles})==1 and all(D(c['B0'])==25 for c in cycles)


@pytest.mark.parametrize('field,value',[('asset_id','OTHER'),('owner',{**OWNER,'account':'OTHER'}),('contract_id',999),('rules_profile','IBKR_OVERNIGHT_CURRENT')])
def test_T07_old_route_other_asset_or_account_cannot_qualify_new_night(tmp_path,field,value):
    desc,data=source(tmp_path);data['readiness']['broker_route_ready'][field]=value
    s,v=resolve(write(tmp_path,data),'2026-12-07T02:00:00Z')
    assert not s['open_for_planning'] and not v['readiness_verified']['broker_route_ready']
