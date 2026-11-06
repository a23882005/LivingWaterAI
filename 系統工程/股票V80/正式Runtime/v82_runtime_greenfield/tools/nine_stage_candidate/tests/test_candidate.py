"""Safe synthetic differential, boundary and causal acceptance examples."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
from pathlib import Path
import importlib
import math
import sys
import pytest

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(TOOLS))
from nine_stage_candidate import engine as E
from nine_stage_candidate.pm_reference import candidate as B
from nine_stage_candidate.pm_reference import candidate_v03 as PM

SOURCE = dict(instrument='SYNTHETIC',listing='SYNTHETIC_LISTING',currency='USD',
    price_basis='SYNTHETIC_RAW',calendar='SYNTHETIC',vintage='SYNTHETIC_V1',data_provenance='SYNTHETIC')


def rows(points=((60,30),(100,25))):
    prices=[100+.4*math.sin(i*.73) for i in range(220)]
    for price,count in points:
        start=prices[-1];prices.extend(start+(price-start)*i/count for i in range(1,count+1))
    return [{'Date':f'{i:05d}','Open':str(prices[i-1] if i else p),
        'High':str(max(prices[i-1] if i else p,p)+.3),
        'Low':str(min(prices[i-1] if i else p,p)-.3),'Close':str(p),
        'Volume':str(1000000+i%7*10000)} for i,p in enumerate(prices)]


def inputs(bars):
    return [dict(depth=max(D(0),1-D(r['Close'])/100),
        qp=min(D(100),max(D(0),(100-D(r['Close']))*D('2.5'))),
        qv=min(D(100),max(D(0),(D(r['Close'])-50)*2)),a_normal=True,
        valuation_legal=True,up=False,fundamental=True) for r in bars]


def replay(bars, inp=None, profile='BASELINE_V03'):
    return E.replay(bars,inputs(bars) if inp is None else inp,source=SOURCE,profile=profile,enabled=True)


def episode_features(count=15):
    return [dict(Date=str(i),C=D(99) if i==0 else D(101+i)/1,
        O=D(100),H=D(120),L=D(100),P5=D(100),L5=D(90),
        MA5=D(100+i),MA10=D(99),MA20=D(98+i)/1,M_ok=False,R_ok=True) for i in range(count)]


@pytest.mark.parametrize('points',[
    ((60,30),(100,25)),((65,28),(73,8),(62,9),(68,5),(65,4),(100,24)),
    ((65,30),)+tuple((65+2*math.sin(i*1.1),1) for i in range(45))+((100,28),),
    ((65,30),(78,12),(50,16),(55,6),(48,5),(78,20))])
def test_frozen_reference_decisions_are_reproduced_field_for_field(points):
    bars=rows(points);inp=inputs(bars);expected=PM.replay(bars,inp);actual=replay(bars,inp)
    for a,b in zip(expected,actual):
        assert {k:b[k] for k in a if k not in ('profile','right')} == {k:v for k,v in a.items() if k not in ('profile','right')}
        assert a['right']==b['right']


def test_default_off_and_formal_source_has_no_candidate_import():
    assert E.replay([],[])['status']=='DISABLED'
    src=TOOLS.parent/'src/livingwater_v82_runtime'
    assert not any('nine_stage_candidate' in p.read_text() for p in src.rglob('*.py'))
    with pytest.raises(ValueError,match='BOOLEAN_ENABLE'):E.replay([],[],enabled='true')


@pytest.mark.parametrize('value',['false','True','UNKNOWN_OTHER',0,1,[],{}])
def test_no_truthy_flags(value):
    with pytest.raises(ValueError,match='THREE_STATE'):E.boolean(value)


@pytest.mark.parametrize('key,value',[('qv','NaN'),('qp','Infinity'),('qv','100.001'),
    ('qv','-.001'),('depth','1.00001'),('depth','-.1'),('qp',75.0),('up','false')])
def test_input_domains_are_strict(key,value):
    bars=rows()[-1:];inp=inputs(bars);inp[0][key]=value
    with pytest.raises(ValueError):replay(bars,inp)


def test_decimal_comparisons_ignore_callers_low_precision():
    bars=rows();inp=inputs(bars)
    with localcontext() as ctx:
        ctx.prec=6;a=replay(bars,inp)
    with localcontext() as ctx:
        ctx.prec=50;b=replay(bars,inp)
    assert a==b


def test_partial_view_is_decision_and_financially_identical():
    bars=rows();out=E.compare_profiles(bars,inputs(bars),source=SOURCE,enabled=True)
    assert not any(d['profile']=='PARTIAL_VIEW_ONLY' for d in out['differences'])
    digests={out['profiles'][p][-1]['rules_digest'] for p in E.PROFILES};assert len(digests)==5


def test_m_does_not_vote_for_right():
    f=episode_features(3);a=E.right_episodes(f);f[1]['M_ok']=True
    assert E.right_episodes(f)==a and a[1]['early_right1'] is True
    f[1]['R_ok']=False;assert E.right_episodes(f)[1]['early_right1'] is False


def test_breakout_equal_boundary_and_first_bar_no_confirmation():
    f=episode_features(3);f[1]['C']=D(100)
    assert E.right_episodes(f)[1]['event'] is False
    f[1]['C']=D(101);r=E.right_episodes(f)[1]
    assert r['early_right1'] is True and r['early_right2'] is False


def test_original_expiry_and_persistent_confirmed_lifetime_are_distinct():
    f=episode_features();a=E.right_episodes(f);b=E.right_episodes(f,persistent=True)
    assert a[3]['early_right2'] is True
    assert a[11]['early_right2'] is True and a[12]['reason']=='EXPIRED'
    assert b[12]['early_right2'] is True
    assert b[12]['episode']['confirmation_session']=='3'


def test_unconfirmed_expires_even_for_persistent_profile():
    f=episode_features()
    for x in f:x['MA5']=x['MA10']=None
    a=E.right_episodes(f,persistent=True)
    assert a[11]['early_right2'] is None and a[12]['reason']=='EXPIRED'


def test_failure_precedes_success_and_fixed_line_equality_does_not_fail():
    f=episode_features();f[12].update(C=D(99),L=D(90))
    assert E.right_episodes(f,persistent=True)[12]['reason']=='CONFIRMED'
    f[12]['C']=D('98.99999999999999999999999999')
    assert E.right_episodes(f,persistent=True)[12]['reason']=='FAILED'
    f[12].update(C=D(150),L=D('89.999999999999999999'))
    assert E.right_episodes(f,persistent=True)[12]['reason']=='FAILED'


def test_retest_true_other_path_unknown_confirms_without_ma20_gate():
    f=episode_features(5);f[2].update(C=D('100.5'),L=D('100.5'),H=D('101'))
    f[3].update(C=D('100.6'),MA20=None)
    a=E.right_episodes(f,persistent=True)
    assert a[2]['retest_path'] is False and a[2]['early_right2'] is False
    assert a[3]['retest_path'] is True and a[3]['continuous_path'] is None
    assert a[3]['early_right2'] is True


def test_confirmation_on_day10_and_no_new_confirmation_on_day11():
    f=episode_features(13)
    for x in f[2:11]:x['MA5']=None
    f[10].update(MA5=D(108),MA10=D(99),MA20=D(107))
    f[9]['MA5']=D(107)
    a=E.right_episodes(f);assert a[11]['early_right2'] is True
    for x in f[2:12]:x['MA5']=None
    assert E.right_episodes(f,persistent=True)[12]['reason']=='EXPIRED'


def test_gap_invalidates_confirmed_event_and_replay_rebuilds_it():
    f=episode_features();expected=E.right_episodes(f,persistent=True)
    f[12]['C']=None;a=E.right_episodes(f,persistent=True)
    assert a[12]['reason']=='INVALIDATED_MISSING_BAR' and a[12]['early_right2'] is None
    f[12]['C']=D(113);assert E.right_episodes(f,persistent=True)==expected


def low_rows(lows):
    return [dict(Date=f'{i:05d}',Open=D(x)+1,Close=D(x)+1,High=D(x)+2,Low=D(x),Volume=D(100))
        for i,x in enumerate(lows)]


def test_plateau_publishes_once_only_after_two_completed_right_bars():
    bars=low_rows([7,6,3,3,3,5,6]);refs=E.low_references(bars)
    assert len(refs)==1 and refs[0]['pivot_index']==4 and refs[0]['confirmed_at']==6
    for end in range(1,7):assert E.low_references(bars[:end])==[]
    assert E.low_references(low_rows([7,6,3,4,3,5,6]))==[]


def test_full_window_no_reference_is_false_only_in_plateau_proposal():
    bars=low_rows([10+i for i in range(70)])
    baseline=replay(bars);proposal=replay(bars,profile='LOW_PLATEAU_EXACT_EQUAL')
    assert baseline[-1]['OffLow'] is None
    assert proposal[-1]['OffLow'] is False
    assert proposal[-1]['low_reference_status']=='COMPLETE_WINDOW_NO_CONFIRMED_LOW'
    assert proposal[-1]['low_reference'] is None
    assert proposal[-1]['R'][9]==baseline[-1]['R'][9]


def test_left_boundary_and_still_forming_plateau_are_unknown():
    bars=low_rows([3]*30+[5,6]);out=replay(bars,profile='LOW_PLATEAU_EXACT_EQUAL')
    assert out[-1]['OffLow'] is None
    bars=low_rows([10+i for i in range(28)]+[3,3,5]);out=replay(bars,profile='LOW_PLATEAU_EXACT_EQUAL')
    assert out[-1]['OffLow'] is None


@pytest.mark.parametrize('profile',E.PROFILES)
def test_future_bars_never_rewrite_past(profile):
    bars=low_rows([20,19,12,12,12,17,18]+[18+i%5 for i in range(30)])
    full=replay(bars,profile=profile)
    for end in (4,5,6,7,10,25,len(bars)-1):
        assert replay(bars[:end],profile=profile)==full[:end]
    changed=deepcopy(bars);changed[-1]['High']+=D(100)
    assert replay(changed,profile=profile)[:-1]==full[:-1]


def test_short_circuit_and_known_bottom_do_not_override_unknown_up():
    f=dict(C=D(101),MA5=D(100),MA10=D(99),M=[True]*8,M_ok=True)
    p=dict(MA5=D(99),MA10=D(99));r=dict(early_right1=False,early_right2=False)
    inp=dict(valuation_legal=True,depth=D('.1'),qv=D(50),qp=D(75),a_normal=True,up=None)
    view=E.condition_view(f,p,r,inp,SOURCE)
    assert view[6]['value'] is True and view[8]['value'] is None
    f['M'][6]=False;inp.update(qv=None,depth=None)
    view=E.condition_view(f,p,r,inp,SOURCE)
    for s in (5,6,7):assert view[s]['value'] is False and view[s]['minimal_missing']==[]


@pytest.mark.parametrize('qv,qp,expected',[
    ('60','75',(False,False,False)),('59','74.99999999999999',(True,False,False)),
    ('40','75',(True,True,False)),('39.999999999999999','75',(True,True,True))])
def test_valuation_and_price_percentile_boundaries(qv,qp,expected):
    f=dict(C=D(101),MA5=D(100),MA10=D(99),M=[False]*8,M_ok=False)
    inp=dict(valuation_legal=True,depth=D('.1'),qv=D(qv),qp=D(qp),a_normal=True,up=False)
    v=E.condition_view(f,f,dict(early_right1=False,early_right2=False),inp,SOURCE)
    assert tuple(v[s]['value'] for s in (2,3,4))==expected


def test_nine_targets_gap_retreat_and_cash_are_independent():
    inp={'financial':dict(project_target='1000',confirmed='600',active_buy='30',active_sell='10')}
    assert [E.financial_view(s,'LEFT',inp)['Target']['value'] for s in range(1,10)]==list(map(D,
        ['100','200','300','400','550','700','850','950','1000']))
    out=E.financial_view(5,'LEFT',inp)
    assert out['Projected']['value']==D(620) and out['Gap']['value']==D(-70)
    assert out['final_amount']['value']==0 and not out['automatic_sell']
    out=E.financial_view(6,'LEFT',inp)
    assert out['Target']['value']==700 and out['final_amount']['value'] is None
    inp['financial']['permission']=False
    assert E.financial_view(9,'TREND',inp)['final_amount']['value']==0


def test_market_availability_excludes_future_rows_without_synthesizing_pit():
    bars=low_rows([5,6,7]);inp=inputs(bars)
    source={**SOURCE,'data_provenance':'SOURCE_BACKED','available_at':'2026-01-03T22:00:00Z',
        'decision_cutoff':'2026-01-03T23:00:00Z'}
    for i,r in enumerate(bars):r['session_close_at']=f'2026-01-0{i+1}T21:00:00Z'
    bars[-1]['available_at']='2026-01-04T00:00:00Z'
    out=E.replay(bars,inp,source=source,enabled=True)
    assert len(out)==2
    source.pop('available_at')
    with pytest.raises(ValueError,match='AVAILABILITY'):E.replay(bars,inp,source=source,enabled=True)


def test_missing_bar_and_identity_boundary_restart_windows():
    bars=rows();inp=inputs(bars);bars[-3]['Close']=None
    a=replay(bars,inp);assert a[-3]['right']['reason']=='INVALIDATED_MISSING_BAR'
    assert a[-1]['primitive_values']['MA5'] is None
    bars=rows();bars[-2]['currency']='EUR';bars[-1]['currency']='EUR'
    a=replay(bars);assert a[-2]['right']['reason']=='INVALIDATED_SEGMENT_BOUNDARY'
    assert a[-1]['primitive_values']['MA20'] is None


def test_dated_issuer_value_does_not_invent_validity_forward_metric_or_qv():
    from nine_stage_candidate.source_view import reference_chain
    identity=dict(instrument='SYNTHETIC',listing='SYNTHETIC',currency='USD',metric='ISSUER_PE',price_basis='ISSUER_DEFINED')
    source={**identity,'value':'20.4','as_of':'2026-09-30',
        'available_at':'2026-11-02T21:00:00Z','source_reference':'SYNTHETIC_ISSUER',
        'source_digest':'a'*64,'source_role':'ORIGINAL_PRODUCER'}
    a=reference_chain([source],decision_cutoff='2026-11-02T22:00:00Z',expected_identity=identity)
    assert a['dated_views'][0]['value']=='20.4' and a['dated_views'][0]['reference_state'].endswith('VALIDITY_UNDEFINED')
    assert a['historical_qV'] is None and a['selected_qualified_source'] is None
    source.update(valid_until='2026-11-03T21:00:00Z',validity_contract_reference='SYNTHETIC_ORIGINAL_CONTRACT')
    b=reference_chain([source],decision_cutoff='2026-11-02T22:00:00Z',expected_identity=identity)
    assert b['selected_qualified_source']['as_of']=='2026-09-30'
    c=reference_chain([source],decision_cutoff='2026-11-04T22:00:00Z',expected_identity=identity)
    assert c['dated_views'][0]['reference_state']=='EXPIRED' and c['selected_qualified_source'] is None


def test_only_named_same_basis_approved_fallback_can_be_selected():
    from nine_stage_candidate.source_view import reference_chain
    identity=dict(instrument='SYNTHETIC',listing='SYNTHETIC',currency='USD',metric='PB',price_basis='ISSUER_DEFINED')
    source={**identity,'value':'3.4','available_at':'2026-11-02T21:00:00Z',
        'valid_until':'2026-11-03T00:00:00Z','source_reference':'SYNTHETIC',
        'source_digest':'b'*64,'validity_contract_reference':'SYNTHETIC_ORIGINAL_CONTRACT','source_role':'APPROVED_FALLBACK'}
    out=reference_chain([source],decision_cutoff='2026-11-02T22:00:00Z',expected_identity=identity)
    assert out['selected_qualified_source'] is None
    source['fallback_approval_reference']='SYNTHETIC_APPROVAL'
    assert reference_chain([source],decision_cutoff='2026-11-02T22:00:00Z',expected_identity=identity)['selected_qualified_source']
    source['metric']='FORWARD_PE'
    with pytest.raises(ValueError,match='METRIC_CONFLICT'):reference_chain([source],decision_cutoff='2026-11-02T22:00:00Z',expected_identity=identity)


def test_offlow_exact_one_percent_and_no_epsilon():
    bars=low_rows([12,11,10,11,12]);bars[-1].update(Open=D('10.1'),Close=D('10.1'),Low=D(10),High=D(13))
    # Keep the required two strictly higher right lows while the close remains
    # at the exact boundary by using a lower reference and consistent OHLC.
    bars=low_rows([12,11,10, D('10.01'),D('10.02')])
    bars[-1].update(Open=D('10.1'),Close=D('10.1'),High=D('10.2'))
    assert replay(bars)[-1]['OffLow'] is True
    bars[-1]['Close']=D('10.099999999999999999999999999')
    assert replay(bars)[-1]['OffLow'] is False


def test_up_true_selects_trend_even_when_only_right1_supports_stage8():
    bars=low_rows([10,11,12]);inp=inputs(bars)
    for x in inp:x.update(up=True,qv=D(60),fundamental=True)
    out=replay(bars,inp)[-1]
    assert out['final_mode']=='TREND' and out['final_stage']==8


def test_replay_retains_proved_bottom_when_up_is_unknown():
    bars=rows();inp=inputs(bars)
    for x in inp:x['up']=None
    out=replay(bars,inp)
    proved=[r for r in out if r['condition_results']['B2']['value'] is True]
    assert proved and all(r['final_stage'] is None and r['final_mode'] is None for r in proved)
    assert all(r['financial_result']['Target']['value'] is None for r in proved)


def test_equal_closes_different_ohlc_have_different_m7_and_unique_slots():
    bars=low_rows([10,11,12,13,14]);a=replay(bars)
    changed=deepcopy(bars);changed[-1]['Low']=D(1);b=replay(changed)
    assert [r['C'] for r in a]==[r['C'] for r in b] and a[-1]['M'][6] is True and b[-1]['M'][6] is False
    assert len({s['dedup_id'] for s in b[-1]['slot_results']['R']})==10


def test_lower_touch_band_equality_and_continuation_only_path():
    f=episode_features(5);a=E.right_episodes(f,persistent=True)
    assert a[3]['continuous_path'] is True and a[3]['retest_path'] is False
    f[2].update(C=D('99.5'),H=D('99.5'),L=D('99.4'))
    f[3].update(C=D('100.6'),MA20=None)
    assert E.right_episodes(f,persistent=True)[3]['retest_path'] is True
    f[2]['H']=D('99.499999999999999999999999')
    assert E.right_episodes(f,persistent=True)[3]['retest_path'] is False


def test_compact_daily_keeps_decisions_and_latest_full_lineage():
    bars=rows();inp=inputs(bars)
    full=replay(bars,inp)
    compact=E.replay(bars,inp,source=SOURCE,enabled=True,compact_daily=True)
    for a,b in zip(full,compact):
        assert all(a[k]==b[k] for k in ('Date','M','R','right','eligibility','stage','normal_mode','financial_result'))
    assert full[-1]==compact[-1]


def availability_case():
    # Synthetic QA exercises the SOURCE_BACKED availability branch. None of
    # these prices, quantiles or calendar dates is customer market evidence.
    days=('05','06','07','08','09','12','13','14')
    bars=[dict(Date='2026-01-'+d,Open='100',High='101',Low='99',Close='100',Volume='1000',
        session_close_at='2026-01-'+d+'T21:00:00Z',available_at='2026-01-'+d+'T22:00:00Z') for d in days]
    inp=[dict(depth='0.1',qp='80',qv='30',valuation_legal=True,fundamental=True,
        up=False,a_normal=True) for _ in bars]
    source={**SOURCE,'data_provenance':'SOURCE_BACKED','decision_cutoff':'2026-01-14T23:00:00Z'}
    return bars,inp,source


@pytest.mark.parametrize('profile',E.PROFILES)
@pytest.mark.parametrize('excluded,interior',[
    ((3,),True),((2,3),True),((6,7),False),((0,1),False)])
def test_filtered_availability_preserves_real_segment_boundaries(profile,excluded,interior):
    bars,inp,source=availability_case()
    for index in excluded:bars[index]['available_at']='2026-01-16T00:00:00Z'
    original=deepcopy(bars)
    out=E.replay(bars,inp,source=source,profile=profile,enabled=True)
    accepted=[b for i,b in enumerate(bars) if i not in excluded]
    bound_inputs=[x for i,x in enumerate(inp) if i not in excluded]
    assert [r['Date'] for r in out]==[r['Date'] for r in accepted]
    assert bars==original
    if not interior:
        assert out==E.replay(accepted,bound_inputs,source=source,profile=profile,enabled=True)
        assert out[-1]['primitive_values']['MA5']==D(100)
        assert not any(r['right']['reason']=='INVALIDATED_SEGMENT_BOUNDARY' for r in out)
        return
    first_post=max(excluded)+1
    suffix=E.replay(bars[first_post:],inp[first_post:],source=source,profile=profile,enabled=True)
    assert out[-1]['primitive_values']['MA5'] is None
    for actual,reference in zip(out[-len(suffix):],suffix):
        assert actual['primitive_values']==reference['primitive_values']
        assert actual['M']==reference['M'] and actual['R']==reference['R']
        assert actual['low_reference']==reference['low_reference']
    assert out[-len(suffix)]['right']['reason']=='INVALIDATED_SEGMENT_BOUNDARY'


@pytest.mark.parametrize('profile',E.PROFILES)
def test_incomplete_interior_session_also_restarts_windows(profile):
    bars,inp,source=availability_case()
    bars[3]['session_close_at']='2026-01-15T21:00:00Z'
    out=E.replay(bars,inp,source=source,profile=profile,enabled=True)
    assert out[-1]['primitive_values']['MA5'] is None
    assert out[3]['right']['reason']=='INVALIDATED_SEGMENT_BOUNDARY'


@pytest.mark.parametrize('profile',E.PROFILES)
def test_filtered_gap_invalidates_live_episode_and_causal_pivot_r10_history(profile):
    bars=rows();inp=inputs(bars)
    # A strict trough (rather than the equal adjacent lows of rows()) must
    # establish a live baseline episode before testing its invalidation.
    for b in bars:
        close=D(b['Close'])
        b.update(Open=b['Close'],High=str(close+D('.3')),Low=str(close-D('.3')))
    from datetime import date,timedelta
    day=date(2024,1,2)
    for b in bars:
        while day.weekday()>4:day+=timedelta(days=1)
        b.update(Date=day.isoformat(),session_close_at=day.isoformat()+'T21:00:00Z',
            available_at=day.isoformat()+'T22:00:00Z')
        day+=timedelta(days=1)
    source={**SOURCE,'data_provenance':'SOURCE_BACKED','decision_cutoff':'2026-01-14T23:00:00Z'}
    original=E.replay(bars,inp,source=source,profile=profile,enabled=True)
    live=next(i for i,r in enumerate(original[:-3]) if r['right']['episode'] is not None)
    gap=live+1;bars[gap]['available_at']='2026-01-16T00:00:00Z'
    out=E.replay(bars,inp,source=source,profile=profile,enabled=True)
    post=out[gap:];fresh=E.replay(bars[gap+1:],inp[gap+1:],source=source,profile=profile,enabled=True)
    assert post[0]['right']['reason']=='INVALIDATED_SEGMENT_BOUNDARY'
    assert post[0]['right']['episode'] is None
    for i,(actual,reference) in enumerate(zip(post,fresh)):
        assert actual['M']==reference['M'] and actual['R']==reference['R']
        assert actual['low_reference']==reference['low_reference']
        if i<34:assert actual['R'][9] is None
        episode=actual['right']['episode']
        if episode is not None:assert episode['b']>=gap
