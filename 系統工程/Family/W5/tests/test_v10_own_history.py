"""Own-asset PIT histories; synthetic calendars are explicitly labelled."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
import math
import sys
import pytest
from test_native_adapters import ROOT
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.own_history import valuation_percentile,price_percentile,own_wealth,midrank


def iso(d,hour=0):return datetime(d.year,d.month,d.day,hour,tzinfo=timezone.utc).isoformat()
def month(d):return date(d.year+(d.month==12),d.month%12+1,1)


def valuation_case(metric='FORWARD_PE'):
    identity=dict(asset_id='SYNTHETIC',listing='SYNTHETIC_X',share_class='SYNTHETIC_CLASS',currency='USD',
        unit='PERCENT' if metric=='FCF_YIELD' else 'MULTIPLE',provider='SYNTHETIC',method_id='OWN_METRIC',method_version='1',metric_name=metric)
    calendar={'approved':True,'calendar_id':'SYNTHETIC_UTC_MONTHS','version':'1','timezone':'UTC','completed_periods':[]}
    history=[];d=date(2015,1,1)
    for i in range(120):
        end=month(d);calendar['completed_periods'].append({'period_id':d.isoformat()[:7],'cadence':'MONTHLY','start':iso(d),'end':iso(end)})
        observed=d+timedelta(days=14)
        history.append({**identity,'source_hash':'SYNTHETIC_HASH','revision_id':'1','retrieved_at':iso(observed+timedelta(days=2)),
            'as_of':iso(observed),'available_at':iso(observed+timedelta(days=1)),
            'freshness':'FRESH','pit_status':'VERIFIED','economic_meaningful':True,'value':str(i+1)})
        d=end
    current={**history[-1],'as_of':'2025-02-15T00:00:00Z','available_at':'2025-02-16T00:00:00Z',
        'retrieved_at':'2025-02-16T01:00:00Z','value':'60.5'}
    return dict(identity=identity,current=current,history=history,cadence='DAILY',calendar=calendar,
        comparable_from='2015-01-01T00:00:00Z',decision_at='2025-02-17T00:00:00Z')


def test_midrank_ties_current_exclusion_and_yield_direction():
    assert midrank('2',['1','2','2','4'])==50
    a=valuation_case();before=deepcopy(a);out=valuation_percentile(**a)
    assert out['status']=='COMPLETE' and Decimal(out['value'])==50
    assert out['audit']['window']=='10Y' and out['audit']['attempts'][0]['valid_periods']==120
    assert out['current_in_reference'] is False and a==before
    a=valuation_case('FCF_YIELD');a['current']['value']='90.5'
    assert Decimal(valuation_percentile(**a)['value'])==25


def test_late_revision_does_not_rewrite_completed_period_or_add_a_sample():
    a=valuation_case();revision={**a['history'][50],'value':'999',
        'available_at':'2025-02-01T00:00:00Z','retrieved_at':'2025-02-02T00:00:00Z','revision_id':'2'}
    a['history']+=[revision,deepcopy(a['history'][50])]
    out=valuation_percentile(**a)
    assert Decimal(out['value'])==50 and out['audit']['attempts'][0]['valid_periods']==120


@pytest.mark.parametrize('change,reason',[
    ('calendar','CALENDAR_UNRESOLVED'),('metric','HISTORY_IDENTITY_OR_METHOD_CONFLICT'),
    ('cadence','UNSUPPORTED_CADENCE'),('pit','NO_RELIABLE_OWN_HISTORY_WINDOW'),
    ('constant','NO_RELIABLE_OWN_HISTORY_WINDOW'),('gaps','NO_RELIABLE_OWN_HISTORY_WINDOW'),
    ('calendar_gap','CALENDAR_PERIOD_COVERAGE_GAP')])
def test_invalid_or_incomplete_reference_remains_named_unknown(change,reason):
    a=valuation_case()
    if change=='calendar':a['calendar']['approved']=False
    elif change=='metric':a['history'][20]['method_id']='DIFFERENT_METHOD'
    elif change=='cadence':a['cadence']='IRREGULAR'
    elif change=='pit':
        for r in a['history']:r['pit_status']='UNVERIFIABLE'
    elif change=='constant':
        for r in a['history']:r['value']='10'
    elif change=='gaps':a['history']=a['history'][:85]+a['history'][88:]
    else:del a['calendar']['completed_periods'][50]
    out=valuation_percentile(**a)
    assert out['value'] is None and reason in out['reason_codes']


def test_unreliable_ten_year_window_can_use_its_own_reliable_five_year_window():
    a=valuation_case();a['history']=a['history'][:50]+a['history'][53:]
    result=valuation_percentile(**a)
    assert result['status']=='COMPLETE' and result['audit']['window']=='5Y'
    assert result['audit']['attempts'][0]['maximum_missing_run']==3


def test_current_legal_primary_is_not_replaced_when_history_is_insufficient():
    a=valuation_case();a['history']=[];out=valuation_percentile(**a)
    assert out['value'] is None and a['current']['metric_name']=='FORWARD_PE'
    a=valuation_case();a['identity']['metric_name']='PROFITABLE_COMPONENT_RATIO';a['current']['metric_name']='PROFITABLE_COMPONENT_RATIO'
    assert valuation_percentile(**a)['reason_codes']==['NONVALUATION_PRIMARY_UNSUPPORTED']


def price_case(count=3300):
    identity=dict(asset_id='SYNTHETIC',listing='SYNTHETIC_X',share_class='SYNTHETIC_CLASS',currency='USD',
        unit='CURRENCY_PER_SHARE',provider='SYNTHETIC',method_id='RAW_CLOSE',method_version='1',price_basis='RAW_UNADJUSTED')
    sessions=[];bars=[];d=date(2012,1,2)
    while len(sessions)<count:
        if d.weekday()<5:
            i=len(sessions);sid=d.isoformat()
            sessions.append({'session_id':sid,'close_at':iso(d,20),'knowledge_at':iso(d,21)})
            value=Decimal(100)+Decimal(i)/100+Decimal(str(round(10*math.sin(i/60),8)))
            bars.append({**identity,'session_id':sid,'close':str(value),'as_of':iso(d,20),
                'available_at':iso(d,21),'retrieved_at':iso(d,21),'source_hash':'SYNTHETIC_HASH','revision_id':'1',
                'freshness':'FRESH','pit_status':'VERIFIED'})
        d+=timedelta(days=1)
    periods=[];p=date(2012,1,1)
    while p<d:
        end=month(p);periods.append({'period_id':p.isoformat()[:7],'cadence':'MONTHLY','start':iso(p),'end':iso(end)})
        p=end
    return dict(identity=identity,bars=bars,actions={k:identity[k] for k in ('asset_id','listing','share_class','currency')},
        calendar={'approved':True,'calendar_id':'SYNTHETIC_WEEKDAYS_NOT_REAL_MARKET','version':'1','timezone':'UTC',
            'sessions':sessions,'completed_periods':periods},decision_at=iso(d,22))


def complete_price(count=3300):
    a=price_case(count);s=a['calendar']['sessions'];a['actions'].update(coverage_verified=True,
        coverage_start=s[0]['session_id'],coverage_end=s[-1]['session_id'],events=[])
    return a


def test_qp_is_own_completed_month_stress_with_frozen_peak_sigma_and_no_current_reference():
    a=complete_price();out=price_percentile(**a,comparable_from='2012-01-01T00:00:00Z')
    assert out['status']=='COMPLETE' and 0<=Decimal(out['value'])<=100
    assert out['current_in_reference'] is False
    assert Decimal(out['current_stress']['peak_sigma'])>0
    assert out['current_stress']['anchor_knowledge_at']
    assert out['audit']['window']=='10Y'
    assert out['monthly_stress'][-1]['period_id']!=a['calendar']['sessions'][-1]['session_id'][:7]


def test_wealth_split_dividend_and_payment_date_do_not_double_count():
    a=complete_price(4);days=[r['session_id'] for r in a['bars']]
    for r,c in zip(a['bars'],('100','50','49','49')):r['close']=c
    a['actions']['events']=[{'event_id':'SPLIT','kind':'PURE_SPLIT','ex_session':days[1],
        'new_per_old':'2','currency':'USD','available_at':a['bars'][1]['available_at']},
        {'event_id':'CASH','kind':'FIXED_NONOPTIONAL_CASH','ex_session':days[2],
        'gross_cash_per_old_share':'1','currency':'USD','available_at':a['bars'][2]['available_at'],
        'payment_date':days[3]}]
    out=own_wealth(**a)
    assert [Decimal(r['wealth']) for r in out['rows']]==[100,100,100,100]
    assert out['rows'][0]['log_return'] is None


def test_missing_session_breaks_wealth_and_sigma_instead_of_crossing_the_gap():
    a=complete_price(270);del a['bars'][-20]
    out=own_wealth(**a);assert out['status']=='COMPLETE_WITH_GAPS'
    assert out['rows'][-20]['wealth'] is None
    assert Decimal(out['rows'][-19]['wealth'])==100 and out['rows'][-19]['log_return'] is None
    result=price_percentile(**a,comparable_from='2012-01-01T00:00:00Z')
    assert result['value'] is None and result['depth'] is None


def test_adjusted_or_uncovered_events_are_not_an_implicit_total_return_series():
    a=complete_price(3);a['identity']['price_basis']='ADJUSTED'
    assert own_wealth(**a)['reason_codes']==['RAW_UNADJUSTED_PRICE_REQUIRED']
    a=complete_price(3);a['actions']['coverage_verified']=False
    assert own_wealth(**a)['reason_codes']==['EVENT_COVERAGE_UNKNOWN']
    a=complete_price(3);a['actions']['events']=[{'event_id':'COMPLEX','kind':'SPINOFF',
        'ex_session':a['bars'][1]['session_id'],'currency':'USD','available_at':a['bars'][1]['available_at']}]
    assert own_wealth(**a)['rows'][1]['reason']=='UNSUPPORTED_EVENT'


def test_latest_tie_is_peak_anchor_and_zero_drawdown_does_not_fabricate_sigma():
    a=complete_price(270)
    for row in a['bars']:row['close']='100'
    result=price_percentile(**a,comparable_from='2012-01-01T00:00:00Z')
    assert result['current_stress']['anchor']==a['bars'][-1]['session_id']
    assert result['depth']=='0' and result['value'] is None
    assert result['reason_codes']==['NONPOSITIVE_PEAK_SIGMA']
