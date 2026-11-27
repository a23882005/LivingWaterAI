"""Owner M1/M8 G1–G8: synthetic boundaries, not a performance backtest."""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal as D
from pathlib import Path
import hashlib,json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
import approved_v04_technical as A
import approved_v04_numeric as N


def bars(count=30):
    start=date(2026,1,1)
    return [dict(Date=str(start+timedelta(days=i)),Open='105',High='110',Low='100',Close='105',Volume='1000') for i in range(count)]


def output(rows):return A.produce(rows,profile=A.load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
def votes(out):return {r['id']:r['truth'] for r in out['left_maturity_signals']}
def branch(out):return out['maturity_rule_amendment']['M8_components']


def low_count_rows(count):
    rows=bars(13);closes=[D(100)]*13
    for i in range(13-count,13):closes[i]=closes[i-4]-1
    for r,c in zip(rows,closes):r.update(Close=str(c),Open=str(c),Low=str(c-1),High=str(c+1))
    return rows


@pytest.mark.parametrize('count',range(9))
def test_G1_low_TD_zero_through_eight_are_not_M1_votes(count):
    rows=low_count_rows(count);out=output(rows)
    assert N.td_count([D(r['Close']) for r in rows])==(0,count)
    assert votes(out)['M1']=='FALSE'
    scores=['0','0.5','0.8','1','1.5','1.8','2','2.5','3','4']
    assert D(out['low_td9_score_times4'])==D(scores[count])*4


def test_G1_first_and_sustained_nine_are_votes_even_when_first9_is_unknown_or_false():
    c=[D(300-x) for x in [100,101,102,103,99,104,105,106,107,108,109,110,111,112,113,114]]
    assert N.td_first9(c[:14],1) is True and N.td_first9(c[:15],1) is False
    for closes in (c[:14],c[:15],c[:16],[D(113-i) for i in range(13)]):
        rows=bars(len(closes))
        for r,value in zip(rows,closes):r.update(Close=str(value),Open=str(value),High=str(value+1),Low=str(value-1))
        out=output(rows);assert votes(out)['M1']=='TRUE' and out['low_td9_score_times4']=='16'
    assert N.td_first9([D(113-i) for i in range(13)],1) is None


def test_G1_reset_and_high_TD9_do_not_keep_a_low_TD_vote():
    rows=low_count_rows(9);rows[-1]['Close']=rows[-5]['Close']
    assert votes(output(rows))['M1']=='FALSE'
    rows=bars(13)
    for i,r in enumerate(rows):r.update(Close=str(100+i),Open=str(100+i),High=str(101+i),Low=str(99+i))
    out=output(rows);assert votes(out)['M1']=='FALSE'
    assert out['technical_reduction_signals'][0]['truth']=='TRUE'


@pytest.mark.parametrize('missing',['short','close','source_decimal'])
def test_G1_required_thirteen_closes_and_missing_source_stay_unknown(missing):
    rows=low_count_rows(9)
    if missing=='short':rows=rows[1:]
    elif missing=='close':rows[0]['Close']=None
    else:rows[0]['_source_decimal']={'Close':None}
    out=output(rows);assert votes(out)['M1']=='UNKNOWN' and out['low_td9_score_times4'] is None


def a_rows(volume='600',count=30):
    rows=bars(count);rows[-2].update(Close='106');rows[-1].update(Close='104.5',Open='105',Volume=volume)
    return rows


@pytest.mark.parametrize('volume,expected',[('601','FALSE'),('600','TRUE'),('599','TRUE'),('900','FALSE')])
def test_G2_exact_volume_reduction_boundaries(volume,expected):
    out=output(a_rows(volume));assert branch(out)=={'A':expected,'B':'FALSE'} and votes(out)['M8']==expected


def test_G2_prior_twenty_excludes_today_and_equal_average_is_not_below():
    rows=a_rows();prior=rows[-21:-1]
    for r in prior:r['Volume']='600'
    prior[0]['Volume']='200';prior[-1]['Volume']='1000'
    assert sum(D(r['Volume']) for r in prior)/20==600
    assert sum(D(r['Volume']) for r in rows[-20:])/20==620
    assert branch(output(rows))['A']=='FALSE'


@pytest.mark.parametrize('count,expected',[(20,'UNKNOWN'),(21,'TRUE')])
def test_G2_no_shortened_twenty_session_average(count,expected):assert branch(output(a_rows(count=count)))['A']==expected


@pytest.mark.parametrize('known_false',['equal_close','too_much_volume'])
def test_G2_known_false_short_circuits_missing_other_A_inputs(known_false):
    rows=a_rows();rows[-3]['Volume']=None
    if known_false=='equal_close':rows[-1]['Close']=rows[-2]['Close']
    else:rows[-1]['Volume']='601'
    assert branch(output(rows))['A']=='FALSE'


def b_rows(position='0.45',low='100',count=30):
    rows=bars(count);lo=D(low);close=lo+D(position)*10
    rows[-2]['Close']='104';rows[-1].update(Low=str(lo),High=str(lo+10),Close=str(close),Open=str(close),Volume='1000')
    return rows


@pytest.mark.parametrize('position,expected',[('0.449','FALSE'),('0.45','TRUE'),('0.451','TRUE')])
def test_G3_exact_close_location_and_equal_open(position,expected):
    out=output(b_rows(position));assert branch(out)=={'A':'FALSE','B':expected} and votes(out)['M8']==expected


@pytest.mark.parametrize('low,expected',[('99','FALSE'),('100','TRUE'),('101','TRUE')])
def test_G3_prior_five_low_is_exclusive_and_equality_is_allowed(low,expected):assert branch(output(b_rows(low=low)))['B']==expected


@pytest.mark.parametrize('count,expected',[(5,'UNKNOWN'),(6,'TRUE')])
def test_G3_complete_prior_five_are_required(count,expected):assert branch(output(b_rows(count=count)))['B']==expected


def test_G3_flat_candle_is_false_without_division_even_with_unknown_open():
    rows=b_rows();rows[-1].update(High='100',Low='100',Close='100',Open=None)
    assert branch(output(rows))['B']=='FALSE'


def test_G3_missing_prior_low_is_unknown_unless_other_B_condition_is_false():
    rows=b_rows();rows[-3]['Low']=None
    assert branch(output(rows))['B']=='UNKNOWN'
    rows[-1]['Open']='106'
    assert branch(output(rows))['B']=='FALSE'


@pytest.mark.parametrize('a,b,expected',[
    ('TRUE','TRUE','TRUE'),('TRUE','FALSE','TRUE'),('TRUE','UNKNOWN','TRUE'),
    ('FALSE','TRUE','TRUE'),('FALSE','FALSE','FALSE'),('FALSE','UNKNOWN','UNKNOWN'),
    ('UNKNOWN','TRUE','TRUE'),('UNKNOWN','FALSE','UNKNOWN'),('UNKNOWN','UNKNOWN','UNKNOWN')])
def test_G4_all_three_value_branch_pairs_and_single_M8_slot(a,b,expected):
    rows=b_rows();rows[-2]['Close']='106'
    rows[-1]['Volume']='600' if a=='TRUE' else '601' if a=='FALSE' else None
    if b=='FALSE':rows[-1]['Open']='106'
    elif b=='UNKNOWN':rows[-1]['Open']=None
    out=output(rows);assert branch(out)=={'A':a,'B':b} and votes(out)['M8']==expected
    assert len(out['left_maturity_signals'])==8 and sum(s['id']=='M8' for s in out['left_maturity_signals'])==1


def market_fixture(tmp_path,at,*,omit=(),delayed=False):
    import exchange_calendars as xc
    from member_market_source import time
    cal=xc.get_calendar('XNYS',start='2026-08-01',end='2026-12-02')
    sessions=[dict(session_id=str(s.date()),open_at=cal.session_open(s).isoformat(),close_at=cal.session_close(s).isoformat()) for s in cal.sessions]
    opened=[s for s in sessions if time(s['open_at'])<=time(at)]
    completed=[s for s in opened if time(s['close_at'])<=time(at)]
    chosen=[s for s in opened[-32:] if s['session_id'] not in omit]
    n=len(chosen);closes=[200-i for i in range(n)];quotes=dict(open=closes,close=closes,high=[c+1 for c in closes],low=[c-1 for c in closes],volume=[1000]*n)
    if time(chosen[-1]['close_at'])>time(at):
        for key in ('open','close','high','low'):quotes[key][-1]=999
    stamp=int((time(at) if delayed else time(completed[-1]['close_at'])).timestamp())
    raw=dict(chart=dict(error=None,result=[dict(meta=dict(symbol='TEST',currency='USD',exchangeTimezoneName='America/New_York',
        exchangeName='NYQ',instrumentType='ETF',regularMarketTime=stamp),timestamp=[int(time(s['open_at']).timestamp()) for s in chosen],
        indicators={'quote':[quotes]})]))
    def save(name,value):
        p=tmp_path/name;p.write_text(json.dumps(value));return dict(local_path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    source=dict(**save('source.json',raw),provider='YAHOO_CHART',symbol='TEST',provider_symbol='TEST',currency='USD',
        exchange='XNYS',provider_exchange='NYQ',timezone='America/New_York',retrieved_at=at,source_reference='SYNTHETIC_COMPLETED_SESSION_INPUT',
        calendar_source=save('calendar.json',dict(exchange='XNYS',timezone='America/New_York',provider='exchange_calendars',version=xc.__version__,
            coverage_cutoff=sessions[-1]['close_at'],sessions=sessions)))
    return source,completed[-1]['session_id']


def read_market(source,at):
    from member_market_source import read_market
    return read_market(source,symbol='TEST',evaluation_at=at,repo_root=ROOT,
        profile=A.load_profile(HERE/'owner_approved_v10.json'),is_etf=True)


@pytest.mark.parametrize('at,day',[
    ('2026-11-03T15:00:00Z','2026-11-02'), # Tuesday intraday: Monday, not Friday.
    ('2026-11-03T07:00:00+08:00','2026-11-02'), # Taiwan Tuesday / New York Monday.
    ('2026-11-07T12:00:00Z','2026-11-06'), # Saturday: Friday remains s.
    ('2026-09-07T15:00:00Z','2026-09-04'), # Labor Day, not an invented Monday bar.
    ('2026-11-27T18:01:00Z','2026-11-27')]) # US half day completed before 21:00Z.
def test_G5_actual_session_calendar_intraday_holiday_timezone_weekend_and_halfday(tmp_path,at,day):
    source,expected=market_fixture(tmp_path,at);out=read_market(source,at)
    assert out['observed_date']==expected==day==out['latest_expected_completed_session']
    assert out['approved_technical']['maturity_rule_amendment']['as_of_session']==day
    assert votes(out['approved_technical'])['M1']=='TRUE'
    assert not out['history_quality']['formal_deployment_eligible']


def test_G5_completed_last_input_is_not_shifted_again_and_provisional_is_excluded(tmp_path):
    at='2026-11-03T15:00:00Z';source,_=market_fixture(tmp_path,at);out=read_market(source,at)
    assert out['observed_date']=='2026-11-02' and out['observed_close']!=999
    assert out['history_quality']['excluded_uncompleted_rows'][-1]['date']=='2026-11-03'
    at='2026-11-02T22:00:00Z';source,_=market_fixture(tmp_path,at);out=read_market(source,at)
    assert out['observed_date']=='2026-11-02' and not out['history_quality']['excluded_uncompleted_rows']


def test_G5_missing_adjacent_session_cannot_borrow_an_older_bar_for_M_inputs(tmp_path):
    at='2026-11-03T22:00:00Z';source,_=market_fixture(tmp_path,at,omit=('2026-11-02',));out=read_market(source,at)
    assert out['rows']==1 and out['observed_date']=='2026-11-03'
    assert votes(out['approved_technical'])['M1']=='UNKNOWN' and votes(out['approved_technical'])['M8']=='UNKNOWN'
    assert out['history_quality']['discarded_before_last_gap']>0


def test_G5_missing_latest_completed_session_remains_dated_stale_observation(tmp_path):
    at='2026-11-03T15:00:00Z';source,_=market_fixture(tmp_path,at,omit=('2026-11-02',));out=read_market(source,at)
    assert out['observed_date']=='2026-10-30' and out['latest_expected_completed_session']=='2026-11-02'
    assert out['approved_technical']['maturity_rule_amendment']['as_of_session']=='2026-10-30'
    assert not out['history_quality']['formal_deployment_eligible']


def selected_maturity(count='9'):
    # Real amended M1/M7/M8 with explicitly FALSE independent legacy slots.
    closes=['110']*4+['105']*4+['100','100','99','99.5','99.8']
    rows=bars(13)
    for r,c in zip(rows,closes):r.update(Close=c,Open=c,Low='95',High='120')
    rows[-1].update(Open='99.8',High='105')
    if count=='8':rows[4]['Close']='110'
    elif count=='unknown':rows[0]['Close']=None
    out=output(rows);assert votes(out)['M7']==votes(out)['M8']=='TRUE'
    slots=[deepcopy(s) if s['id'] in ('M1','M7','M8') else {**s,'truth':'FALSE'} for s in out['left_maturity_signals']]
    return slots,out


def test_G6_M7_and_M8_are_independent_votes_in_the_original_eight_slot_aggregator():
    from livingwater_v82_runtime.daily_slice import maturity
    _,out=selected_maturity();signals=out['left_maturity_signals'];result=maturity(signals)
    assert result['canonical_slots']['M7']==result['canonical_slots']['M8']=='TRUE'
    assert result['true_count']==sum(s['truth']=='TRUE' for s in signals)


def test_G8_amendment_provenance_does_not_relabel_the_other_six_M_slots_or_trading():
    out=output(bars());assert out['maturity_rule_amendment']['scope']==['M1','M8']
    assert out['maturity_rule_amendment']['performance_validation']=='NOT_CLAIMED'
    assert all(s['rule_ref']=='V82 v1.0 TECH5.2' for s in out['left_maturity_signals'][1:7])
    assert out['deployment_status']=='NOT_RUN' and out['canonical_fields_modified'] is False
