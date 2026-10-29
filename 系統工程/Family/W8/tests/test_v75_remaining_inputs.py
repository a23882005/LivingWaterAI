"""Calendar-qualified own-ETF cash yields and explicit unresolved quality."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json,sys
import pytest
import exchange_calendars as xc

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_remaining_inputs as M


def history(symbol='SGOV',start='2021-10-01'):
    cal=xc.get_calendar('XNYS',start=start,end='2026-11-01')
    sessions=cal.sessions_in_range(start,'2026-10-28');stamps=[];closes=[];dividends={};months=set()
    for i,day in enumerate(sessions):
        stamp=int(cal.session_open(day).timestamp());stamps.append(stamp);closes.append('100' if i<len(sessions)-1 else '80')
        month=day.strftime('%Y-%m')
        if month not in months:
            dividends[str(stamp)]={'date':stamp,'amount':'0.25'};months.add(month)
    return {'chart':{'error':None,'result':[{'meta':{'symbol':symbol,'currency':'USD','instrumentType':'ETF',
        'dataGranularity':'1d','exchangeTimezoneName':'America/New_York','exchangeName':'PCX'},
        'timestamp':stamps,'indicators':{'quote':[{'close':closes,'open':closes,
            'high':closes,'low':closes,'volume':[1000]*len(stamps)}],'adjclose':[{'adjclose':['1']*len(stamps)}]},
        'events':{'dividends':dividends}}]}}


def evaluate(raw,symbol='SGOV'):
    return M.cash_yield_history(json.dumps(raw).encode(),symbol,'2026-10-29T01:00:00Z')


def repo():
    rows=[]
    for number,(released,closed) in enumerate([('08:15','08:30'),('13:30','13:45')]):
        rows.append({'operationId':'SYNTHETIC:'+str(number),'auctionStatus':'Results','note':'',
            'operationType':'Repo','operationMethod':'Full Allotment','term':'Overnight',
            'settlementType':'Same Day','lastUpdated':'2026-10-28 '+closed+':05',
            'operationDate':'2026-10-28','settlementDate':'2026-10-28',
            'releaseTime':released,'closeTime':closed,'totalAmtAccepted':3000000,
            'details':[{'amtAccepted':1000000},{'amtAccepted':2000000}]})
    return {'repo':{'operations':rows}}


def test_same_etf_cash_yield_uses_full_trailing_year_and_unadjusted_close():
    metrics,proof=evaluate(history())
    assert metrics['formal_proxy'] is False and Decimal(metrics['history_years'])>=3
    assert metrics['yield_percentile_pct']=='100'
    assert Decimal(proof['latest_yield_pct'])==Decimal('3.75')
    assert proof['unadjusted_close']=='80'
    assert not proof['is_sec_yield'] and not proof['is_yield_to_maturity']
    assert not proof['distribution_quality_inferred'] and not proof['historical_publication_times_asserted']
    assert proof['calendar']['session_gaps']==[]
    assert proof['history_start']>='2022-10-01' # no partial-year annualization


def test_missing_session_and_future_or_wrong_instrument_cannot_pass():
    raw=history();root=raw['chart']['result'][0]
    root['timestamp'].pop(20);root['indicators']['quote'][0]['close'].pop(20)
    with pytest.raises(ValueError,match='SESSION_COVERAGE'):evaluate(raw)
    raw=history();raw['chart']['result'][0]['meta']['symbol']='SPSB'
    with pytest.raises(ValueError,match='IDENTITY'):evaluate(raw)
    raw=history();raw['chart']['result'][0]['events']['dividends']['future']={
        'date':int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp()),'amount':'1'}
    with pytest.raises(ValueError,match='FUTURE'):evaluate(raw)


def test_short_history_and_unreconciled_splits_are_not_treasury_proxies():
    with pytest.raises(ValueError,match='THREE_YEAR'):evaluate(history(start='2024-01-02'))
    raw=history();raw['chart']['result'][0]['events']['splits']={'1':{'splitRatio':'2:1'}}
    with pytest.raises(ValueError,match='CORPORATE_ACTION'):evaluate(raw)


def test_srf_daily_total_keeps_both_operations_and_never_becomes_ois():
    data=repo();metrics,basis=M.repo_usage(json.dumps(data).encode(),'2026-10-29T01:00:00Z')
    assert metrics=={'srf_usage_usd':'6000000'} and len(basis['operation_ids'])==2
    assert not basis['other_liquidity_signals_inferred']
    data['repo']['operations'].pop()
    with pytest.raises(ValueError,match='DAILY_COVERAGE'):M.repo_usage(json.dumps(data).encode(),'2026-10-29T01:00:00Z')
    data=repo();data['repo']['operations'][0]['totalAmtAccepted']=1
    with pytest.raises(ValueError,match='AMOUNT_CONFLICT'):M.repo_usage(json.dumps(data).encode(),'2026-10-29T01:00:00Z')


def test_small_value_exercises_and_non_repo_operations_are_excluded():
    data=repo();extra=deepcopy(data['repo']['operations'][0]);extra.update(operationId='EXERCISE',note='Small Value Exercise',totalAmtAccepted=9000000000)
    data['repo']['operations'].append(extra)
    metrics,basis=M.repo_usage(json.dumps(data).encode(),'2026-10-29T01:00:00Z')
    assert metrics['srf_usage_usd']=='6000000' and basis['excluded_operation_ids']==['EXERCISE']


def test_native_quality_unknown_is_explicit_and_one_liquidity_signal_stays_insufficient():
    from bond_advisory import candidates
    candidates(HERE.parents[2])
    from v75_runtime.predicates import pred007,pred008,pred010
    data={'NYFED_REPO':json.dumps(repo()).encode(),'YAHOO_SGOV':json.dumps(history()).encode()}
    proofs={k:{'available_at':'2026-10-29T01:00:00Z'} for k in data}
    pool=M.extend({'shared_metrics':{},'asset_metrics':{},'calculations':{},'unprovided_inputs':{}},data,proofs)
    at=M.time('2026-10-29T02:00:00Z')
    assert pred007(pool['shared_metrics']['PRED-007'],at,['SYNTHETIC']).assessment_status.value=='INSUFFICIENT_DATA'
    assert pred008(pool['asset_metrics']['SGOV']['PRED-008'],at,['SYNTHETIC']).assessment_status.value=='VALID'
    quality=pred010(pool['shared_metrics']['PRED-010'],at,['SYNTHETIC']).model_dump(mode='json')
    assert quality['assessment_status']=='VALID' and quality['sub_states']==['ETF_QUALITY_UNKNOWN']
    assert pool['unprovided_inputs']['PRED-010']
