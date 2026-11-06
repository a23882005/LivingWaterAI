"""Original IB Last daily observations; no inverse split or wealth/PIT input.

The independent listing snapshot and original contract query must agree.
OHLC defects reach the existing component-dependent intake unchanged. Even a
complete date window and reported actions do not attest raw prices or PIT.
"""
from copy import deepcopy
import csv,json,re
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo
from datetime import datetime
from family_input import digest

PRICE_BASIS='SPLIT_ADJUSTED_OR_UNATTESTED_PROVIDER_OHLC__NOT_PIT_WEALTH'


def load(source,evaluation_at):
    from pm_source_document import history
    from member_market_source import time
    from historical_source_qualification import pinned
    data,receipt=history(source);symbol=source['symbol'];retrieved=time(source['retrieved_at'])
    if (source.get('provider')!='IBKR_LAST_DAILY_OBSERVATION' or source.get('provider_symbol')!=symbol
        or source.get('currency')!='USD' or source.get('timezone')!='America/New_York'
        or retrieved>time(evaluation_at) or not source.get('source_reference')
        or {'NASDAQ':'XNAS','NYSE ARCA':'ARCX','NYSE':'XNYS'}.get(source['provider_exchange'])!=source['exchange']):
        raise PermissionError('MEMBER_MARKET_IBKR_IDENTITY_OR_TIME')
    identity=source['identity_source']
    if not identity.get('source_reference') or time(identity['retrieved_at'])>time(evaluation_at):
        raise PermissionError('MEMBER_MARKET_IBKR_REFERENCE_TIME_REQUIRED')
    text=pinned(identity)
    if identity.get('format')=='MASSIVE_REFERENCE_CSV':
        rows=list(csv.DictReader(StringIO(text)))
        if len(rows)!=1:raise PermissionError('MEMBER_MARKET_IBKR_REFERENCE_IDENTITY')
        r=rows[0]
        if (r.get('ticker')!=symbol or r.get('market')!='stocks' or r.get('locale')!='us'
            or r.get('currency_name')!='usd' or r.get('active')!='true'
            or r.get('primary_exchange')!=source['exchange'] or r.get('type') not in ('ETF','CS')
            or not re.fullmatch('BBG[A-Z0-9]{9}',r.get('share_class_figi',''))):
            raise PermissionError('MEMBER_MARKET_IBKR_REFERENCE_IDENTITY')
        kind='ETF' if r['type']=='ETF' else 'EQUITY'
    elif identity.get('format')=='YAHOO_CHART':
        chart=json.loads(text)['chart']
        if chart.get('error') or len(chart.get('result') or [])!=1:raise PermissionError('MEMBER_MARKET_IBKR_REFERENCE_IDENTITY')
        r=chart['result'][0]['meta'];kind=r.get('instrumentType')
        if (r.get('symbol')!=symbol or r.get('currency')!='USD' or r.get('exchangeTimezoneName')!=source['timezone']
            or {'NYQ':'XNYS','PCX':'ARCX','NMS':'XNAS'}.get(r.get('exchangeName'))!=source['exchange']
            or kind not in ('ETF','EQUITY')):raise PermissionError('MEMBER_MARKET_IBKR_REFERENCE_IDENTITY')
    else:raise PermissionError('MEMBER_MARKET_IBKR_ORIGINAL_REFERENCE_REQUIRED')
    if data.get('source')!='Last' or type(data.get('chart_step')) is not int or data['chart_step']!=86400:
        raise ValueError('MEMBER_MARKET_IBKR_DAILY_LAST_REQUIRED')
    stamps=[time(t) for t in data['time']]
    if not stamps or stamps!=sorted(set(stamps)):raise ValueError('MEMBER_MARKET_IBKR_TIMESTAMP_ORDER')
    if any(not time(data['chart_start'])<=t<time(data['chart_end']) or t>retrieved for t in stamps):
        raise ValueError('MEMBER_MARKET_IBKR_CHART_COVERAGE_OR_FUTURE')
    dates=[t.astimezone(ZoneInfo(source['timezone'])).date().isoformat() for t in stamps]
    if dates!=sorted(set(dates)):raise ValueError('MEMBER_MARKET_IBKR_DUPLICATE_SESSION')
    quotes={k:deepcopy(data[k]) for k in ('open','high','low','close','volume')}
    if any(len(v)!=len(stamps) for v in quotes.values()):raise ValueError('MEMBER_MARKET_IBKR_ARRAY_COVERAGE')
    for values in quotes.values():
        for v in values:
            if isinstance(v,bool) or v is None or not Decimal(str(v)).is_finite():
                raise ValueError('MEMBER_MARKET_IBKR_FINITE_ORIGINAL_NUMBER_REQUIRED')
    actions=data.get('corp_actions')
    if not isinstance(actions,list):raise ValueError('MEMBER_MARKET_IBKR_ACTION_OBSERVATIONS_REQUIRED')
    seen=set()
    for a in actions:
        key=(a.get('type'),a.get('date'))
        if key in seen or key[0] not in ('Splits','CashDividends'):
            raise ValueError('MEMBER_MARKET_IBKR_ACTION_IDENTITY_CONFLICT')
        seen.add(key)
        for k in ('date','announce_date','payment_date'):
            if a.get(k):datetime.strptime(a[k],'%Y%m%d')
        value=Decimal(a['value'])
        if not value.is_finite() or value<0 or a['type']=='Splits' and value==0:
            raise ValueError('MEMBER_MARKET_IBKR_ACTION_VALUE_CONFLICT')
        if a['type']=='CashDividends' and a.get('currency')!='USD':
            raise PermissionError('MEMBER_MARKET_IBKR_ACTION_CURRENCY_CONFLICT')
    meta=dict(symbol=symbol,currency='USD',exchangeTimezoneName=source['timezone'],
        exchangeName=source['provider_exchange'],instrumentType=kind)
    evidence=dict(provider='IBKR_LAST_DAILY_OBSERVATION',**receipt,price_basis=PRICE_BASIS,
        independent_identity_sha256=identity['sha256'],independent_identity_retrieved_at=identity['retrieved_at'],
        returned_start=dates[0],returned_end=dates[-1],returned_rows=len(dates),
        raw_unadjusted_request_verified=False,historical_PIT_attested=False,corporate_action_coverage_attested=False,
        historical_identity_coverage_attested=False,price_adjustment_reversed=False,split_quantity_reapplied=False,
        corporate_action_observations=deepcopy(actions),corporate_action_dates_are_not_publication_times=True,
        availability_basis='OBSERVED_AT_PM_CAPTURE__NOT_HISTORICAL_PUBLICATION',
        ohlcv_from_single_original_response=True,other_provider_price_repairs=False)
    return meta,quotes,[int(t.timestamp()) for t in stamps],evidence


def audit(source,evaluation_at):
    meta,quotes,stamps,evidence=load(source,evaluation_at)
    from member_market_source import time,read_json
    calendar=read_json(source['calendar_source']);sessions=calendar.get('sessions',[])
    if (calendar.get('exchange')!=source['exchange'] or calendar.get('timezone')!=source['timezone']
        or not calendar.get('provider') or not calendar.get('version')
        or time(calendar['coverage_cutoff'])<time(evaluation_at)):
        raise PermissionError('MEMBER_MARKET_IBKR_CALENDAR_SCOPE')
    days=[r['session_id'] for r in sessions]
    if days!=sorted(set(days)) or any(time(r['open_at'])>=time(r['close_at']) for r in sessions):
        raise ValueError('MEMBER_MARKET_IBKR_CALENDAR_ORDER')
    cutoff=min(time(evaluation_at),time(source['retrieved_at']))
    completed={r['session_id'] for r in sessions if time(r['close_at'])<=cutoff}
    bars=[];invalid=[]
    for i,stamp in enumerate(stamps):
        day=datetime.fromtimestamp(stamp,ZoneInfo(source['timezone'])).date().isoformat()
        nums={k:Decimal(str(v[i])) for k,v in quotes.items()}
        valid=(min(nums[k] for k in ('open','high','low','close'))>0 and nums['volume']>=0
            and nums['low']<=min(nums['open'],nums['close']) and nums['high']>=max(nums['open'],nums['close']))
        if not valid:invalid.append(day)
        bars.append(dict(session_id=day,original_values={k:str(v) for k,v in nums.items()},
            OHLC_valid=valid,completed_session_observed=day in completed,available_at=None,historical_PIT_verified=False))
    expected=sorted(d for d in completed if bars[0]['session_id']<=d<=bars[-1]['session_id'])
    missing=sorted(set(expected)-{r['session_id'] for r in bars});outside=sorted({r['session_id'] for r in bars}-completed)
    result=dict(schema_version='Family.W8.IbkrHistoryQualification.v1',symbol=source['symbol'],
        source_descriptor=deepcopy(source),evaluation_at=evaluation_at,raw_observed_bars=bars,returned_bar_count=len(bars),
        provider_completion_evidence=evidence,invalid_OHLC_sessions=invalid,missing_calendar_sessions=missing,
        uncompleted_or_outside_calendar_sessions=outside,calendar_date_coverage_observed=not missing and not outside,
        actions_observed_count=len(evidence['corporate_action_observations']),qualified_native_price_history=None,
        qP_history_qualified=False,qV_history_qualified=False,historical_price_PIT_verified=False,
        issues=['IBKR_LAST_PRICES_NOT_ATTESTED_RAW_UNADJUSTED','ACTION_LIST_NOT_COMPLETE_PIT_EVENT_BOOK',
            'OBSERVED_CAPTURE_NOT_HISTORICAL_PUBLICATION_OR_REVISION','OWN_PRIMARY_VALUATION_HISTORY_REQUIRED'],trade_action='NO_TRADE')
    result['digest']=digest(result)
    return result
