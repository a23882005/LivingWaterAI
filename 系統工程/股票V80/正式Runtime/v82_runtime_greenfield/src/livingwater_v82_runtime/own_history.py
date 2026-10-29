"""Approved v1.0 PV2 own-listing qV / wealth / qP producers.

Input calendars and publication/revision receipts are source-owned facts.
No synthetic calendar, forward fill, adjusted-price dividend duplication,
cross-metric history, or replacement instrument is permitted here.
"""
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo
from .approved_profiles import number, METRICS, VERSION

IDENTITY=('asset_id','listing','share_class','currency','unit','provider','method_id','method_version')
RECEIPTS=('source_hash','revision_id','retrieved_at','as_of','available_at')


def time(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.utcoffset() is None:raise ValueError('HISTORY_TIMEZONE_REQUIRED')
    return t


def unknown(reason, **known):
    return {'value':None,'status':'UNKNOWN','reason_codes':[reason],'profile_version':VERSION,**known}


def midrank(current, reference):
    current=number(current);values=[number(x) for x in reference]
    if current is None or not values or None in values or len(set(values))==1:return None
    with localcontext() as ctx:
        ctx.prec=40
        return Decimal(100)*(sum(x<current for x in values)+Decimal('.5')*sum(x==current for x in values))/len(values)


def _calendar(calendar):
    if not calendar or calendar.get('approved') is not True or not calendar.get('calendar_id') or not calendar.get('version'):
        raise ValueError('CALENDAR_UNRESOLVED')
    try:return ZoneInfo(calendar['timezone'])
    except (KeyError,ValueError):raise ValueError('CALENDAR_UNRESOLVED')


def _identity(identity):
    if any(not isinstance(identity.get(k),str) or not identity[k].strip() for k in IDENTITY):
        raise ValueError('HISTORY_IDENTITY_REQUIRED')


def _valid(row, identity, cutoff, *, require_metric=False):
    if any(row.get(k)!=identity[k] for k in IDENTITY):raise ValueError('HISTORY_IDENTITY_OR_METHOD_CONFLICT')
    if require_metric and row.get('metric_name')!=identity.get('metric_name'):
        raise ValueError('HISTORY_METRIC_CONFLICT')
    if any(not row.get(k) for k in RECEIPTS):return False
    observed,available,retrieved=(time(row[k]) for k in ('as_of','available_at','retrieved_at'))
    if observed>available or available>retrieved or available>cutoff:return False
    return row.get('freshness')=='FRESH' and row.get('pit_status')=='VERIFIED'


def _year_ago(end, years):
    try:return end.replace(year=end.year-years)
    except ValueError:return end.replace(year=end.year-years,day=28)


def _periods(calendar, cadence, current_at):
    periods=calendar.get('completed_periods')
    if not isinstance(periods,list) or not periods:raise ValueError('CALENDAR_UNRESOLVED')
    result=[];seen=set();last=None
    for row in periods:
        if row.get('cadence')!=cadence:continue
        start,end=time(row['start']),time(row['end'])
        if start>=end or row['period_id'] in seen or (last is not None and start<last):
            raise ValueError('CALENDAR_PERIOD_CONFLICT')
        seen.add(row['period_id']);last=end
        if end<current_at:result.append({**row,'start_time':start,'end_time':end})
    if not result:raise ValueError('COMPLETED_REFERENCE_PERIODS_REQUIRED')
    local=current_at.astimezone(_calendar(calendar))
    current_start=date(local.year,local.month if cadence=='MONTHLY' else ((local.month-1)//3)*3+1,1)
    prior_end=current_start.fromordinal(current_start.toordinal()-1)
    expected_month=prior_end.month if cadence=='MONTHLY' else ((prior_end.month-1)//3)*3+1
    latest=result[-1]['start_time'].astimezone(_calendar(calendar))
    if (latest.year,latest.month)!=(prior_end.year,expected_month):
        raise ValueError('CALENDAR_LATEST_COMPLETED_PERIOD_MISSING')
    # Do not allow an omitted entire period to improve coverage statistics.
    keys=[(p['start_time'].year,p['start_time'].month) for p in result]
    width=3 if cadence=='QUARTERLY' else 1
    for (a,b),(c,d) in zip(keys,keys[1:]):
        if (c-a)*12+d-b!=width:raise ValueError('CALENDAR_PERIOD_COVERAGE_GAP')
    return result


def _window(periods, selected, identity, comparable_from, current_at):
    """10y -> 5y -> complete comparable listing regime, each quality checked."""
    start=time(comparable_from);last=periods[-1]['end_time'];attempts=[]
    candidates=[('10Y',_year_ago(last,10)),('5Y',_year_ago(last,5)),('COMPARABLE_SINCE_INCEPTION',start)]
    for label,begin in candidates:
        # A partial five-/ten-year window cannot masquerade as a full window.
        if label!='COMPARABLE_SINCE_INCEPTION' and periods[0]['start_time']>begin:continue
        rows=[p for p in periods if p['start_time']>=max(start,begin)]
        if not rows:continue
        values=[selected.get(p['period_id']) for p in rows];valid=[x for x in values if x is not None]
        missing_run=largest=0
        for value in values:
            missing_run=missing_run+1 if value is None else 0;largest=max(largest,missing_run)
        span_ok=rows[0]['start_time']<=_year_ago(rows[-1]['end_time'],2)
        coverage=Decimal(len(valid))/len(rows)
        reasons=[]
        if not span_ok:reasons.append('COMPARABLE_SPAN_LESS_THAN_TWO_YEARS')
        if coverage<Decimal('.9'):reasons.append('REFERENCE_COVERAGE_BELOW_90_PERCENT')
        if largest>2:reasons.append('REFERENCE_CONSECUTIVE_MISSING_OVER_TWO')
        if len(set(valid))<=1:reasons.append('REFERENCE_CONSTANT_OR_EMPTY')
        attempts.append({'window':label,'expected_periods':len(rows),'valid_periods':len(valid),
            'coverage':str(coverage),'maximum_missing_run':largest,'reason_codes':reasons})
        if not reasons:return valid,{'window':label,'attempts':attempts,
            'reference_periods':[p['period_id'] for p in rows if selected.get(p['period_id']) is not None]}
    return None,{'attempts':attempts,'reason_codes':['NO_RELIABLE_OWN_HISTORY_WINDOW']}


def valuation_percentile(*, identity, current, history, cadence, calendar, comparable_from, decision_at):
    try:
        _identity(identity);_calendar(calendar);cutoff=time(decision_at)
        metric=identity.get('metric_name')
        if metric not in METRICS:return unknown('NONVALUATION_PRIMARY_UNSUPPORTED')
        if cadence not in ('DAILY','WEEKLY','MONTHLY','QUARTERLY'):return unknown('UNSUPPORTED_CADENCE')
        if not _valid(current,identity,cutoff,require_metric=True) or current.get('economic_meaningful') is not True:
            return unknown('CURRENT_PRIMARY_NOT_LEGAL')
        value=number(current.get('value'))
        if value is None or (metric!='FCF_YIELD' and value<=0):return unknown('CURRENT_PRIMARY_VALUE_INVALID')
        interval='QUARTERLY' if cadence=='QUARTERLY' else 'MONTHLY'
        periods=_periods(calendar,interval,time(current['as_of']));selected={}
        for period in periods:
            candidates=[]
            for row in history:
                if period['start_time']<=time(row['as_of'])<period['end_time']:
                    if _valid(row,identity,min(cutoff,period['end_time']),require_metric=True) and row.get('economic_meaningful') is True:
                        v=number(row.get('value'))
                        if v is not None and (metric=='FCF_YIELD' or v>0):candidates.append(row)
            if candidates:
                candidates.sort(key=lambda r:(time(r['as_of']),time(r['available_at'])))
                latest=candidates[-1]
                same=[r for r in candidates if (r['as_of'],r['available_at'])==(latest['as_of'],latest['available_at'])]
                if len({str(r['value']) for r in same})>1:raise ValueError('AMBIGUOUS_VALUATION_REVISION')
                selected[period['period_id']]=number(latest['value'])
        values,audit=_window(periods,selected,identity,comparable_from,time(current['as_of']))
        if values is None:return unknown('NO_RELIABLE_OWN_HISTORY_WINDOW',audit=audit)
        rank=midrank(value,values)
        if rank is None:return unknown('REFERENCE_CONSTANT_OR_EMPTY',audit=audit)
        result=100-rank if metric=='FCF_YIELD' else rank
        return {'value':str(result),'status':'COMPLETE','reason_codes':[],'metric_name':metric,
            'direction':'LOWER_IS_CHEAPER','audit':audit,'current_in_reference':False,
            'identity':dict(identity),'profile_version':VERSION}
    except (KeyError,ValueError,TypeError) as error:return unknown(str(error))


def _wealth_series(identity, bars, actions, calendar, decision_at):
    _identity(identity);_calendar(calendar);cutoff=time(decision_at)
    if identity.get('price_basis')!='RAW_UNADJUSTED':raise ValueError('RAW_UNADJUSTED_PRICE_REQUIRED')
    sessions=calendar.get('sessions')
    if not isinstance(sessions,list) or not sessions:raise ValueError('CALENDAR_UNRESOLVED')
    if not calendar.get('coverage_cutoff') or time(calendar['coverage_cutoff'])<cutoff:
        raise ValueError('CALENDAR_NOT_COVERED_AT_CUTOFF')
    if (actions.get('coverage_verified') is not True or not actions.get('source_reference')
        or not actions.get('source_hash') or actions.get('pit_status')!='VERIFIED'
        or not actions.get('available_at') or time(actions['available_at'])>cutoff):
        raise ValueError('EVENT_COVERAGE_UNKNOWN')
    if any(actions.get(k)!=identity[k] for k in ('asset_id','listing','share_class','currency')):
        raise ValueError('CORPORATE_ACTION_IDENTITY_CONFLICT')
    coverage_start,coverage_end=date.fromisoformat(actions['coverage_start']),date.fromisoformat(actions['coverage_end'])
    by_date=defaultdict(list)
    for row in bars:by_date[row['session_id']].append(row)
    events=defaultdict(list);seen=set()
    for event in actions.get('events',[]):
        if not event.get('event_id') or event['event_id'] in seen:raise ValueError('DUPLICATE_OR_MISSING_CORPORATE_ACTION')
        seen.add(event['event_id']);events[event['ex_session']].append(event)
    rows=[];segment=0;prior=None;seen_sessions=set();last_close=None
    for session in sessions:
        sid=session['session_id'];close=time(session['close_at']);knowledge=time(session['knowledge_at'])
        if sid in seen_sessions or (last_close is not None and close<=last_close) or close>knowledge:
            raise ValueError('CALENDAR_SESSION_CONFLICT')
        seen_sessions.add(sid);last_close=close
        if knowledge>cutoff:continue
        problem=None
        if not coverage_start<=date.fromisoformat(sid)<=coverage_end:problem='EVENT_COVERAGE_UNKNOWN'
        available=[]
        for row in by_date.get(sid,[]):
            if _valid(row,identity,knowledge) and row.get('price_basis')=='RAW_UNADJUSTED':available.append(row)
        available.sort(key=lambda r:time(r['available_at']))
        row=available[-1] if available else None
        if row and any(r['available_at']==row['available_at'] and r.get('close')!=row.get('close') for r in available):
            raise ValueError('AMBIGUOUS_PRICE_REVISION')
        c=number(row.get('close'),'0') if row else None
        if c in (None,Decimal(0)):problem=problem or 'MISSING_OR_INVALID_EXPECTED_CLOSE'
        k=Decimal(1);cash=Decimal(0)
        for event in events.get(sid,[]):
            if event.get('currency')!=identity['currency'] or time(event['available_at'])>knowledge:
                problem='CORPORATE_ACTION_NOT_PIT_OR_CURRENCY_CONFLICT';break
            if event.get('kind')=='PURE_SPLIT':
                ratio=number(event.get('new_per_old'),'0')
                if ratio in (None,Decimal(0)):problem='INVALID_SPLIT_RATIO';break
                k*=ratio
            elif event.get('kind')=='FIXED_NONOPTIONAL_CASH':
                value=number(event.get('gross_cash_per_old_share'),'0')
                if value is None:problem='INVALID_DISTRIBUTION';break
                cash+=value
            else:problem='UNSUPPORTED_EVENT';break
        if problem:
            rows.append({'session_id':sid,'wealth':None,'reason':problem,'segment':segment});prior=None;segment+=1;continue
        if prior is None:w=Decimal(100);ret=None
        else:
            w=prior['wealth']*(k*c+cash)/prior['close']
            ret=(w/prior['wealth']).ln()
        current={'session_id':sid,'close':c,'wealth':w,'log_return':ret,'segment':segment,
            'knowledge_at':knowledge.isoformat(),'source_hash':row['source_hash']}
        rows.append(current);prior=current
    if not rows or calendar.get('last_completed_session')!=rows[-1]['session_id']:
        raise ValueError('CALENDAR_LATEST_COMPLETED_SESSION_MISMATCH')
    return rows


def own_wealth(*, identity, bars, actions, calendar, decision_at):
    try:
        with localcontext() as ctx:
            ctx.prec=40;rows=_wealth_series(identity,bars,actions,calendar,decision_at)
        return {'status':'COMPLETE_WITH_GAPS' if any(r.get('reason') for r in rows) else 'COMPLETE',
            'rows':[{k:str(v) if isinstance(v,Decimal) else v for k,v in r.items()} for r in rows],
            'seed':'100','method_id':'OWN_FUND_RAW_CLOSE_GROSS_CASH_EXDATE_CLOSE_REINVEST',
            'profile_version':VERSION}
    except (KeyError,ValueError,TypeError) as error:return unknown(str(error),rows=[])


def _stress(rows, index):
    current=rows[index]
    if current['wealth'] is None:return {'depth':None,'z':None,'reason':current['reason']}
    window=rows[max(0,index-251):index+1]
    if len(window)!=252 or any(r['wealth'] is None or r['segment']!=current['segment'] for r in window):
        return {'depth':None,'z':None,'reason':'CONTIGUOUS_252_SESSION_HIGH_REQUIRED'}
    high=max(r['wealth'] for r in window)
    anchor=max(i for i in range(index-251,index+1) if rows[i]['wealth']==high)
    depth=max(Decimal(0),(high/current['wealth']).ln())
    returns=rows[max(0,anchor-62):anchor+1]
    values=[r.get('log_return') for r in returns]
    if len(values)!=63 or None in values or any(r['segment']!=current['segment'] for r in returns):
        return {'depth':depth,'z':None,'anchor':rows[anchor]['session_id'],'reason':'PEAK_63_RETURN_SIGMA_REQUIRED'}
    mean=sum(values)/63;sigma=(sum((v-mean)**2 for v in values)/62).sqrt()
    z=depth/(sigma*Decimal(252).sqrt()) if sigma>0 else None
    return {'depth':depth,'z':z,'peak_sigma':sigma,'anchor':rows[anchor]['session_id'],
        'anchor_knowledge_at':rows[anchor]['knowledge_at'],'reason':None if z is not None else 'NONPOSITIVE_PEAK_SIGMA'}


def price_percentile(*, identity, bars, actions, calendar, comparable_from, decision_at, previous_anchor=None):
    try:
        with localcontext() as ctx:
            ctx.prec=40;rows=_wealth_series(identity,bars,actions,calendar,decision_at)
            if not rows:return unknown('NO_COMPLETED_PRICE_SESSION')
            current=_stress(rows,len(rows)-1);periods=_periods(calendar,'MONTHLY',time(rows[-1].get('knowledge_at',decision_at)))
            selected={};monthly=[]
            for period in periods:
                matches=[i for i,r in enumerate(rows) if period['start_time'].date()<=date.fromisoformat(r['session_id'])<=period['end_time'].date()]
                if not matches:continue
                observation=_stress(rows,matches[-1]);value=observation.get('z')
                selected[period['period_id']]=value
                monthly.append({'period_id':period['period_id'],**{k:str(v) if isinstance(v,Decimal) else v for k,v in observation.items()}})
            values,audit=_window(periods,selected,identity,comparable_from,time(decision_at))
            anchor=current.get('anchor');window_ids={r['session_id'] for r in rows[-252:]}
            known={'depth':str(current['depth']) if current.get('depth') is not None else None,
                'current_stress':{k:str(v) if isinstance(v,Decimal) else v for k,v in current.items()},
                'monthly_stress':monthly,'audit':audit,'anchor_changed':previous_anchor is not None and previous_anchor!=anchor and previous_anchor not in window_ids,
                'anchor_change_is_recovery_evidence':False,'current_in_reference':False,'identity':dict(identity)}
            if current.get('z') is None:return unknown(current['reason'],**known)
            if values is None:return unknown('NO_RELIABLE_OWN_HISTORY_WINDOW',**known)
            rank=midrank(current['z'],values)
            return {'value':str(rank) if rank is not None else None,'status':'COMPLETE' if rank is not None else 'UNKNOWN',
                'reason_codes':[] if rank is not None else ['REFERENCE_CONSTANT_OR_EMPTY'],'profile_version':VERSION,**known}
    except (KeyError,ValueError,TypeError) as error:return unknown(str(error),depth=None)
