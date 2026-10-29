"""Own-ETF cash-yield histories and official SRF observations for V75.

TTM cash yield is compared with the same ETF and same definition throughout.
It is not SEC yield, YTM, a distribution-quality score or a Treasury proxy.
Missing ETF quality components are explicit native UNKNOWN states.
"""
from datetime import date,datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo
import json


def time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('V75_REMAINING_TIMEZONE_REQUIRED')
    return at


def number(value):
    if value is None or isinstance(value,bool):raise ValueError('V75_REMAINING_NUMBER_REQUIRED')
    value=Decimal(str(value))
    if not value.is_finite():raise ValueError('V75_REMAINING_NONFINITE')
    return value


def repo_usage(raw,available_at):
    operations=json.loads(raw,parse_float=Decimal)['repo']['operations']
    if not isinstance(operations,list) or not operations:raise ValueError('V75_SRF_OPERATIONS_REQUIRED')
    known=time(available_at);zone=ZoneInfo('America/New_York');by={};seen=set();excluded=[]
    for row in operations:
        oid=row['operationId']
        if oid in seen:raise ValueError('V75_SRF_DUPLICATE_OPERATION')
        seen.add(oid)
        if row.get('auctionStatus')!='Results':continue
        if ('small value' in row.get('note','').lower() or row.get('operationType')!='Repo'
            or row.get('operationMethod')!='Full Allotment' or row.get('term')!='Overnight'
            or row.get('settlementType')!='Same Day'):
            excluded.append(oid);continue
        updated=datetime.fromisoformat(row['lastUpdated']).replace(tzinfo=zone)
        day=date.fromisoformat(row['operationDate'])
        close=datetime.fromisoformat(day.isoformat()+'T'+row['closeTime']).replace(tzinfo=zone)
        if updated>known or close>known or updated<close or row['settlementDate']!=day.isoformat():
            raise ValueError('V75_SRF_FUTURE_OR_SETTLEMENT_CONFLICT')
        accepted=number(row['totalAmtAccepted'])
        parts=[number(r['amtAccepted']) for r in row['details']]
        details=sum(parts,Decimal(0))
        if accepted<0 or any(value<0 for value in parts) or accepted!=details:
            raise ValueError('V75_SRF_ACCEPTED_AMOUNT_CONFLICT')
        pair=(row['releaseTime'],row['closeTime'])
        if pair not in (('08:15','08:30'),('13:30','13:45')):
            excluded.append(oid);continue
        by.setdefault(day,{})
        if pair in by[day]:raise ValueError('V75_SRF_DUPLICATE_DAILY_SLOT')
        by[day][pair]=(accepted,oid)
    if not by:raise ValueError('V75_SRF_SCHEDULED_OPERATIONS_REQUIRED')
    day=max(by);latest=by[day]
    if len(latest)!=2:raise ValueError('V75_SRF_DAILY_COVERAGE_INCOMPLETE')
    value=sum((amount for amount,_ in latest.values()),Decimal(0))
    return {'srf_usage_usd':str(value)},{'observed_date':day.isoformat(),
        'operation_ids':[oid for _,oid in latest.values()],
        'formula':'SUM_ACCEPTED_USD_ACROSS_COMPLETED_MORNING_AND_AFTERNOON_OVERNIGHT_SRF_OPERATIONS',
        'scope':'DAILY_ACCEPTED_USD__NOT_REVERSE_REPO_OR_RESERVE_BALANCE',
        'excluded_operation_ids':excluded,'other_liquidity_signals_inferred':False}


def _year_ago(day):
    return day.replace(year=day.year-1) if (day.month,day.day)!=(2,29) else date(day.year-1,2,28)


def cash_yield_history(raw,symbol,available_at):
    import exchange_calendars as xc
    from pathlib import Path
    chart=json.loads(raw,parse_float=Decimal)['chart']
    if chart.get('error') or len(chart.get('result') or [])!=1:raise ValueError('V75_YIELD_CHART_RESULT')
    root=chart['result'][0];meta=root['meta'];known=time(available_at)
    if (meta.get('symbol')!=symbol or meta.get('currency')!='USD' or meta.get('instrumentType')!='ETF'
        or meta.get('dataGranularity')!='1d' or meta.get('exchangeTimezoneName')!='America/New_York'
        or meta.get('exchangeName') not in ('NYQ','PCX','NMS','NGM','NCM')):
        raise ValueError('V75_YIELD_ETF_IDENTITY_OR_BASIS')
    zone=ZoneInfo('America/New_York');stamps=root['timestamp'];closes=root['indicators']['quote'][0]['close']
    if not stamps or len(stamps)!=len(closes) or stamps!=sorted(set(stamps)):
        raise ValueError('V75_YIELD_HISTORY_ORDER')
    first=datetime.fromtimestamp(stamps[0],zone).date()
    cal=xc.get_calendar('XNYS',start=first-timedelta(days=7),end=known.date()+timedelta(days=7))
    points={};excluded=[]
    for stamp,raw_close in zip(stamps,closes):
        moment=datetime.fromtimestamp(stamp,zone);day=moment.date()
        if moment>known:raise ValueError('V75_YIELD_FUTURE_BAR')
        if not cal.is_session(day.isoformat()):raise ValueError('V75_YIELD_NONSESSION_BAR')
        opened=cal.session_open(day.isoformat()).to_pydatetime()
        closed=cal.session_close(day.isoformat()).to_pydatetime()
        if moment!=opened:
            excluded.append(moment.isoformat());continue
        if closed>known:
            excluded.append(moment.isoformat());continue
        if day in points:raise ValueError('V75_YIELD_DUPLICATE_SESSION')
        value=number(raw_close)
        if value<=0:raise ValueError('V75_YIELD_NONPOSITIVE_CLOSE')
        points[day]=value
    if not points:raise ValueError('V75_YIELD_COMPLETED_BARS_REQUIRED')
    last=max(points)
    expected=cal.sessions_in_range(str(first),str(known.astimezone(zone).date()))
    expected=[d.date() for d in expected if cal.session_close(d).to_pydatetime()<=known]
    if not expected or last!=expected[-1] or set(points)!=set(expected):
        raise ValueError('V75_YIELD_SESSION_COVERAGE_OR_RECENCY')
    events=root.get('events',{})
    if events.get('splits') or events.get('capitalGains'):
        raise ValueError('V75_YIELD_CORPORATE_ACTION_BASIS_RECONCILIATION_REQUIRED')
    dividends=[]
    for event in events.get('dividends',{}).values():
        ex_at=datetime.fromtimestamp(event['date'],zone);cash=number(event['amount'])
        if ex_at>known or cash<0:raise ValueError('V75_YIELD_FUTURE_OR_INVALID_DISTRIBUTION')
        if not cal.is_session(ex_at.date().isoformat()):raise ValueError('V75_YIELD_DISTRIBUTION_NONSESSION')
        dividends.append((ex_at.date(),cash))
    if not dividends:raise ValueError('V75_YIELD_DISTRIBUTION_HISTORY_REQUIRED')
    sample=[];cash_by_day={}
    for day,price in sorted(points.items()):
        start=_year_ago(day)
        if start<first:continue # full trailing-year warmup, never partial annualization
        cash=sum((value for ex,value in dividends if start<ex<=day),Decimal(0))
        sample.append((day,cash/price*100));cash_by_day[day]=cash
    if len(sample)<2:raise ValueError('V75_YIELD_WARM_HISTORY_REQUIRED')
    years=Decimal((sample[-1][0]-sample[0][0]).days)/Decimal('365.2425')
    if years<3:raise ValueError('V75_YIELD_THREE_YEAR_SAME_BASIS_REQUIRED')
    current=sample[-1][1];rank=sum(value<=current for _,value in sample)
    metrics={'yield_percentile_pct':str(Decimal(rank)*100/len(sample)),
        'history_years':str(years),'formal_proxy':False}
    proof={'symbol':symbol,'yield_basis':'TRAILING_12_CALENDAR_MONTH_CASH_DISTRIBUTIONS_DIV_UNADJUSTED_CLOSE',
        'yield_unit':'PERCENT','latest_yield_pct':str(current),'latest_ttm_cash_per_share':str(cash_by_day[last]),
        'unadjusted_close':str(points[last]),'price_field':'indicators.quote.Close__NOT_ADJCLOSE',
        'observed_date':last.isoformat(),'history_start':sample[0][0].isoformat(),
        'history_end':sample[-1][0].isoformat(),'history_years':str(years),'sample_count':len(sample),
        'rank_count_le_current':rank,'percentile_method':'EMPIRICAL_CDF_WEAK_RANK',
        'distribution_window':'(same_calendar_date_prior_year, current_session]__FEB29_USES_FEB28',
        'calendar':{'name':'XNYS','version':xc.__version__,
            'package_source_sha256':sha256(Path(xc.__file__).read_bytes()).hexdigest(),
            'completed_sessions_checked':len(expected),'session_gaps':[]},
        'excluded_forming_or_quote_bars':excluded,'is_sec_yield':False,'is_yield_to_maturity':False,
        'distribution_quality_inferred':False,'historical_publication_times_asserted':False}
    return metrics,proof


def extend(pool,data,proofs):
    if 'NYFED_REPO' in data:
        metrics,proof=repo_usage(data['NYFED_REPO'],proofs['NYFED_REPO']['available_at'])
        pool['shared_metrics']['PRED-007']=metrics;pool['calculations']['PRED-007']=proof
        pool['unprovided_inputs']['PRED-007']=['sofr_ois_bps','fra_ois_bps','treasury_market_depth_percentile_3y']
    for symbol in ('SGOV','SPSB'):
        key='YAHOO_'+symbol
        if key not in data:continue
        metrics,proof=cash_yield_history(data[key],symbol,proofs[key]['available_at'])
        pool['asset_metrics'].setdefault(symbol,{})['PRED-008']=metrics
        pool['calculations'][symbol+'.PRED-008']=proof
    # UNKNOWN is the frozen component state, not an all-clear default. The
    # original evaluator emits ETF_QUALITY_UNKNOWN, which retains PAUSE.
    if any(key.startswith('YAHOO_') for key in data):
        pool['shared_metrics']['PRED-010']={'structure_state':'UNKNOWN',
            'liquidity_state_etf':'UNKNOWN','distribution_quality_state':'UNKNOWN'}
        pool['calculations']['PRED-010']={'component_producer':'EXPLICIT_UNRESOLVED_SOURCE_ASSESSMENT',
            'normal_state_inferred':False,'missing_component_evidence':[
                'frozen structure threshold assessment','qualified ETF liquidity and NAV premium/discount assessment',
                'distribution coverage/ROC and income quality assessment'],
            'scope':'NATIVE_UNKNOWN_COMPONENT_STATES__NO_QUALITY_CLEARANCE'}
        pool['unprovided_inputs']['PRED-010']=list(pool['calculations']['PRED-010']['missing_component_evidence'])
    return pool
