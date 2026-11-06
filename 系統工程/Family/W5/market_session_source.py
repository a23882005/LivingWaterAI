"""Pinned venue sessions for the existing native daily-cycle key.

Exchange event trade dates, provider daily-bar labels and quote timestamps are
separate facts. This reader creates no calendar, trading permission or ledger.
"""
from copy import deepcopy
from datetime import datetime,date,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from family_input import digest

NY=ZoneInfo('America/New_York')
LAUNCH=datetime(2026,12,7,2,tzinfo=timezone.utc)  # announced, not activation proof
US_PLANNING_EXCHANGES=frozenset(('NASDAQ','XNAS','NYSE','XNYS','NYSEARCA','NYSE_ARCA','ARCA','ARCX','AMEX','XASE'))
GATES=('exchange_operational','sip_ready','data_feed_ready','broker_route_ready','account_permission')


def instant(value):
    if not isinstance(value,str):raise ValueError('MARKET_SESSION_TIME_REQUIRED')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None:raise ValueError('MARKET_SESSION_TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def _pinned(descriptor,at):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:raise PermissionError('MARKET_SESSION_SOURCE_BYTES_CHANGED')
    if descriptor.get('retrieved_at') and instant(descriptor['retrieved_at'])>at:
        raise PermissionError('MARKET_SESSION_SOURCE_ACQUIRED_AFTER_CUTOFF')
    return json.loads(raw)


def _assured(item,allow_synthetic):
    return item.get('assurance')=='SOURCE_VERIFIED' or (allow_synthetic and item.get('assurance')=='SYNTHETIC')


def requires_source(session,evaluation_at):
    """Requiring new proof after the announced date does not assert go-live."""
    return session.get('exchange') in US_PLANNING_EXCHANGES and instant(evaluation_at)>=LAUNCH


def read(descriptor,*,identity,allow_synthetic=False):
    at=instant(identity['evaluation_at']);data=_pinned(descriptor,at)
    if (data.get('schema_version')!='Family.W5.MarketSessionSource.v1'
        or any(data.get(k)!=identity[k] for k in ('owner','asset_id','source_db_sha256'))
        or not data.get('source_reference') or instant(data['available_at'])>at):
        raise PermissionError('MARKET_SESSION_OWNER_ASSET_DB_OR_TIME_MISMATCH')
    venue=data.get('execution_venue');profile=data.get('rules_profile');exchange=data.get('planning_exchange')
    if ((venue,profile) not in (('NASDAQ','NASDAQ_23H_20261206'),('IBKR_ATS','IBKR_OVERNIGHT_CURRENT'))
        or not isinstance(exchange,str) or not exchange.strip()):
        raise ValueError('MARKET_SESSION_VENUE_OR_RULE_PROFILE_UNKNOWN')
    # Verify every referenced original before using a claimed assurance.
    references={}
    for ref in data.get('originals',[]):
        raw=Path(ref['local_path']).read_bytes();key=sha256(raw).hexdigest()
        if (key!=ref['sha256'] or not ref.get('source_reference')
            or instant(ref['retrieved_at'])>at):raise PermissionError('MARKET_SESSION_ORIGINAL_PROOF_MISMATCH')
        references[key]=deepcopy(ref)
    def proof(item):
        return (item.get('source_hash') in references and _assured(item,allow_synthetic)
            and item.get('available_at') is not None and instant(item['available_at'])<=at)
    cal=data.get('calendar') or {};rows=cal.get('days') or []
    diagnostic=dict(schema_version='Family.W5.MarketSessionReadback.v1',execution_venue=venue,
        rules_profile=profile,source_descriptor=deepcopy(descriptor),source_reference=data['source_reference'],
        evaluation_at=identity['evaluation_at'],assurance_mode='SYNTHETIC_ONLY' if allow_synthetic else 'SOURCE_ONLY',
        broker_order_release_inferred=False,broker_submission_performed=False,production='HOLD',trade='NONE')
    session=dict(session_id=None,exchange=exchange,calendar_id=cal.get('calendar_id'),calendar_version=cal.get('version'),
        planning_start_at=None,planning_end_at=None,open_for_planning=False)
    def result(status,reasons,**fields):
        view={**diagnostic,'status':status,'reason_codes':reasons,**fields,'session':deepcopy(session)}
        view['digest']=digest(view);return deepcopy(session),view
    if not (proof(cal) and cal.get('venue')==venue and cal.get('timezone')=='America/New_York'
        and cal.get('calendar_id') and cal.get('version') and rows):
        return result('UNKNOWN',['QUALIFIED_VENUE_CALENDAR_REQUIRED'])
    first=date.fromisoformat(cal['coverage_from']);last=date.fromisoformat(cal['coverage_through'])
    if first>last:raise ValueError('MARKET_SESSION_CALENDAR_RANGE')
    expected=[(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    if [r.get('date') for r in rows]!=expected:raise ValueError('MARKET_SESSION_CALENDAR_DAY_COVERAGE')
    local=at.astimezone(NY);today=local.date();tomorrow=today+timedelta(days=1)
    if not first<=today<=last or (local.hour>=20 and tomorrow>last):
        return result('UNKNOWN',['VENUE_CALENDAR_CUTOFF_NOT_COVERED'])
    windows=[]
    for row in rows:
        if row.get('state')=='CLOSED':continue
        if row.get('state')!='OPEN':return result('UNKNOWN',['VENUE_CALENDAR_DAY_STATE_UNKNOWN'])
        day=date.fromisoformat(row['date'])
        if day.weekday()>4:raise ValueError('MARKET_SESSION_WEEKEND_BUSINESS_DAY_CONFLICT')
        def stamp(key):return instant(row[key])
        def wall(key,offset,hour,minute=0):
            value=stamp(key).astimezone(NY)
            if (value.date()!=day+timedelta(days=offset) or (value.hour,value.minute,value.second,value.microsecond)!=(hour,minute,0,0)):
                raise ValueError('MARKET_SESSION_SOURCE_WALL_TIME_CONFLICT:'+key)
            return stamp(key)
        if venue=='IBKR_ATS' and stamp('night_start_at').astimezone(NY).hour!=20:
            return result('UNKNOWN',['IBKR_HOLIDAY_ATS_RULE_SOURCE_REQUIRED'])
        night_start=wall('night_start_at',-1,21 if venue=='NASDAQ' else 20)
        night_end=wall('night_end_at',0,4 if venue=='NASDAQ' else 3,0 if venue=='NASDAQ' else 50)
        day_start=wall('day_start_at',0,4);regular_start=wall('rth_open_at',0,9,30)
        regular_end=stamp('rth_close_at');day_end=stamp('day_end_at')
        if (not night_start<night_end<=day_start<regular_start<regular_end<=day_end
            or regular_end.astimezone(NY).date()!=day or day_end.astimezone(NY).date()!=day
            or regular_end.astimezone(NY).time().replace(tzinfo=None)>datetime.min.replace(hour=16).time()
            or day_end.astimezone(NY).time().replace(tzinfo=None)>datetime.min.replace(hour=20).time()):raise ValueError('MARKET_SESSION_INTERVAL_ORDER')
        if regular_end.astimezone(NY).hour<16 and not row.get('early_close_source_reference'):
            return result('UNKNOWN',['EARLY_CLOSE_SOURCE_REQUIRED'])
        transition=row.get('day_transition_end_at')
        transition_end=instant(transition) if transition else None
        if transition_end is not None and not day_start<=transition_end<=regular_start:
            raise ValueError('MARKET_SESSION_TRANSITION_INTERVAL')
        windows.append((night_start,night_end,'NIGHT',row,night_start,day_end))
        if venue=='IBKR_ATS':continue  # SMART daytime needs its own verified route; ATS is night-only.
        if venue=='NASDAQ' and transition_end is None:
            windows.append((day_start,regular_start,'TRANSITION_UNKNOWN',row,night_start,day_end))
        else:
            if transition_end and transition_end>day_start:windows.append((day_start,transition_end,'DAY_TRANSITION',row,night_start,day_end))
            windows.append((transition_end or day_start,regular_start,'PRE_MARKET',row,night_start,day_end))
        windows.extend([(regular_start,regular_end,'REGULAR',row,night_start,day_end),
            (regular_end,day_end,'POST_MARKET',row,night_start,day_end)])
    active=[w for w in windows if w[0]<=at<w[1]]
    if len(active)>1:raise ValueError('MARKET_SESSION_AMBIGUOUS_VENUE_INTERVAL')
    if not active:return result('CLOSED',[],phase='CLOSED',candidate_trade_date=None)
    start,end,phase,row,planning_start,planning_end=active[0]
    session.update(session_id=row['date'],planning_start_at=planning_start.isoformat(),planning_end_at=planning_end.isoformat())
    reasons=[]
    if venue=='NASDAQ' and at<LAUNCH:reasons.append('NASDAQ_23H_NOT_STARTED')
    gates=data.get('readiness') or {};required=GATES if venue=='NASDAQ' else tuple(k for k in GATES if k!='sip_ready')
    def ready(key):
        item=gates.get(key,{})
        if not (item.get('status')=='VERIFIED' and proof(item)
            and item.get('execution_venue')==venue and item.get('rules_profile')==profile):return False
        if key in ('data_feed_ready','broker_route_ready','account_permission') and item.get('asset_id')!=data['asset_id']:return False
        if key in ('broker_route_ready','account_permission'):
            contract=data.get('contract_id')
            if (type(contract) is not int or contract<=0 or item.get('contract_id')!=contract
                or item.get('owner')!=data['owner']):return False
        return True
    verified={key:ready(key) for key in required}
    if not all(verified.values()):reasons.extend(key.upper()+'_UNVERIFIED' for key,v in verified.items() if not v)
    if phase in ('TRANSITION_UNKNOWN','DAY_TRANSITION'):reasons.append(phase)
    session['open_for_planning']=not reasons
    return result('VERIFIED_SESSION' if not reasons else 'SOURCE_REVIEW',reasons,phase=phase,
        candidate_trade_date=row['date'],event_phase_start_at=start.isoformat(),event_phase_end_at=end.isoformat(),
        readiness_verified=verified,exchange_book_end_at=row['night_end_at'] if phase=='NIGHT' else row['day_end_at'],
        daily_bar_date_relabelled=False,night_quote_promoted_to_daily=False)


def prepare(source,*,allow_synthetic=False):
    """Resolve a bound source before existing cycle lookup; no B0 math here."""
    out=deepcopy(source);descriptor=out.get('session_source')
    if descriptor is None:return out
    identity=out['identity'];scope=dict(owner=identity['owner'],asset_id=identity['asset_id'],
        source_db_sha256=identity['snapshot_id'],evaluation_at=identity['evaluation_at'])
    out['session'],out['session_source_readback']=read(descriptor,identity=scope,allow_synthetic=allow_synthetic)
    return out
