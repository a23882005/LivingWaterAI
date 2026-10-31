"""Approved CMR8 daily slice and durable, owner-scoped planning ledger.

Cycle commitments constrain the daily strategy budget. They are not cash
reservations and are never subtracted again from active-order exposure.
This module has no broker, network, exchange, or order-placement adapter.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from .approved_profiles import P,VERSION,number,truth,negate,compare
from .core_rules import tri_and,threshold_truth
from .enums import NormalDeploymentMode

LIVE=frozenset(('PLANNED','SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'))
RELEASED=frozenset(('CANCELLED','EXPIRED','REJECTED','LOCAL_RELEASED','FILLED'))
LEDGER_IMPLEMENTATION_VERSION='V82_DAILY_SLICE_LEDGER_1.0.1'


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _or(*values):
    values=[truth(v) for v in values]
    return P.TRUE if P.TRUE in values else P.UNKNOWN if P.UNKNOWN in values else P.FALSE


def maturity(signals):
    slots={};conflicts=[]
    for row in signals:
        slot=row.get('canonical_slot',row.get('id'))
        if slot not in {'M'+str(i) for i in range(1,9)}:raise ValueError('UNREGISTERED_MATURITY_SLOT')
        value=truth(row.get('truth'))
        if slot in slots and slots[slot] is not value:
            slots[slot]=P.UNKNOWN;conflicts.append(slot)
        else:slots[slot]=value
    values=[slots.get('M'+str(i),P.UNKNOWN) for i in range(1,9)]
    state=threshold_truth(values,3)
    return {'state':'MATURE' if state is P.TRUE else 'IMMATURE' if state is P.FALSE else 'UNKNOWN',
        'true_count':values.count(P.TRUE),'unknown_count':values.count(P.UNKNOWN),
        'canonical_slots':{'M'+str(i+1):v.value for i,v in enumerate(values)},
        'duplicate_conflicts':sorted(set(conflicts)),'rule':'TECH5.2 / CMR8'}


def speed(*, mode, maturity_result, credit_level, core_etf, high_beta, macro_pressure, extreme_valuation):
    mode=NormalDeploymentMode(mode);state=maturity_result['state']
    rates={NormalDeploymentMode.BASE_DEPLOYMENT:('0.1','0.2'),
        NormalDeploymentMode.LEFT_OVERWEIGHT:('0.15','0.25'),
        NormalDeploymentMode.RIGHT_CONFIRMATION:('0.25','0.25'),
        NormalDeploymentMode.TREND_DEPLOYMENT:('0.2','0.2')}
    a,b=rates.get(mode,(None,None))
    rate=a if a==b or state=='IMMATURE' else b if state=='MATURE' else None
    credit=None
    if type(credit_level) is int:
        if credit_level==0:credit=Decimal(1)
        elif credit_level==1:credit=Decimal('.75')
        elif credit_level in (2,3):
            if credit_level==3 or mode in (NormalDeploymentMode.RIGHT_CONFIRMATION,NormalDeploymentMode.TREND_DEPLOYMENT):credit=Decimal(0)
            else:
                eligible=tri_and(truth(core_etf),negate(high_beta))
                credit=Decimal('.5') if eligible is P.TRUE else Decimal(0) if eligible is P.FALSE else None
    pressure=truth(macro_pressure)
    macro=Decimal('.75') if pressure is P.TRUE else Decimal(1) if pressure is P.FALSE else None
    if mode in (NormalDeploymentMode.LEFT_OVERWEIGHT,NormalDeploymentMode.RIGHT_CONFIRMATION):valuation=Decimal(1)
    else:
        valuation=Decimal('.5') if extreme_valuation in ('ON','TRUE',True) else Decimal(1) if extreme_valuation in ('OFF','FALSE',False,'NOT_APPLICABLE') else None
    raw={'mode_rate':Decimal(rate) if rate is not None else None,'credit_multiplier':credit,
        'macro_multiplier':macro,'valuation_multiplier':valuation}
    return {**{k:str(v) if v is not None else None for k,v in raw.items()},
        'required_unknown_fields':[k for k,v in raw.items() if v is None],
        'maturity':deepcopy(maturity_result),'rule':'CMR-SLICE-01 / CMR8','profile_version':VERSION}


def trend_timing(*, bars, ma5, ma10, ma20, previous_atr14, previous_close,
                 breakout_retest_success, current_up, previous_up=None, previous_technical=None):
    """CMR-TREND-CHASE-01; completed raw bars and pre-current ATR only."""
    last=bars[-1] if bars else {};o,h,l,c=(number(last.get(k)) for k in ('Open','High','Low','Close'))
    prior=number(previous_close);atr=number(previous_atr14,'0')
    valid=None not in (o,h,l,c) and h>=max(o,l,c) and l<=min(o,h,c)
    if not valid:
        return {'truth':'UNKNOWN','extreme_bull_bar':'UNKNOWN','entry_structure':'UNKNOWN',
            'entry_components':{},'reason_codes':['INVALID_OR_MISSING_COMPLETED_OHLC'],
            'mode_stage_target_gap_changed':False}
    tr=max(h-l,abs(h-prior),abs(l-prior)) if valid and prior is not None else None
    bull=compare(c,'GT',o)
    if tr==0:extreme=P.FALSE
    else:
        extreme=tri_and(bull,compare(tr,'GE',2*atr if atr is not None and atr>0 else None),
            compare((c-o)/tr if valid and tr is not None and tr>0 else None,'GE','.8'))
    def retest(ma):
        ma=number(ma,'0')
        if ma==0:ma=None
        return tri_and(compare(l,'LE',ma),compare(c,'GE',ma),compare(c,'LE',Decimal('1.01')*ma if ma else None))
    trailing=bars[-5:];highs=[number(r.get('High')) for r in trailing];lows=[number(r.get('Low')) for r in trailing]
    width=(max(highs)-min(lows)) if len(trailing)==5 and None not in highs+lows else None
    narrow=tri_and(compare(width,'LE',2*atr if atr is not None and atr>0 else None),compare(c,'GE',number(ma20)))
    if previous_up is None and previous_technical is not None:
        previous_up=tri_and(threshold_truth([truth(v) for v in previous_technical['up_price']],1),
            threshold_truth([truth(v) for v in previous_technical['up_confirm']],3),truth(previous_technical['ma20_ok']))
    components={'ma5_retest':retest(ma5),'ma10_retest':retest(ma10),
        'breakout_retest_success':truth(breakout_retest_success),'narrow_consolidation':narrow,
        'successive_up':tri_and(truth(current_up),truth(previous_up))}
    entry=_or(*components.values());timing=tri_and(negate(extreme),entry)
    return {'truth':timing.value,'extreme_bull_bar':extreme.value,'entry_structure':entry.value,
        'entry_components':{k:v.value for k,v in components.items()},
        'true_range':str(tr) if tr is not None else None,'previous_atr14':str(atr) if atr is not None else None,
        'rule':'CMR-TREND-CHASE-01','mode_stage_target_gap_changed':False}


def cycle_id(*, owner, session_id, exchange, asset_id, profile_version=VERSION):
    if (not owner or any(not isinstance(owner.get(k),str) or not owner[k] for k in ('client_id','broker','account','currency'))
            or not (owner.get('funding_domain') or owner.get('domain'))
            or any(not isinstance(v,str) or not v for v in (session_id,exchange,asset_id,profile_version))):
        raise ValueError('CYCLE_IDENTITY_REQUIRED')
    return 'V82-SLICE-'+digest({'owner':owner,'session_id':session_id,'exchange':exchange,
        'asset_id':asset_id,'profile_version':profile_version})


def _amount(value):
    result=number(value,'0')
    if result is None:raise ValueError('CYCLE_AMOUNT_UNKNOWN_OR_INVALID')
    return result


def _factor(speed_result):
    values=[number(speed_result.get(k),'0') for k in ('mode_rate','credit_multiplier','macro_multiplier','valuation_multiplier')]
    if Decimal(0) in values:return Decimal(0)
    if None in values:return None
    result=Decimal(1)
    for value in values:result*=value
    return result


def open_cycle(*, owner, session_id, exchange, asset_id, opened_at, gap, speed_result,
               permission, trend_allowed=True, exposure_reconciled, session_open, profile_version=VERSION):
    if permission is not True or truth(trend_allowed) is not P.TRUE or exposure_reconciled is not True or session_open is not True:
        return None
    factor=_factor(speed_result)
    if factor is None:return None
    g0=_amount(gap);b0=g0*factor
    if g0<=0 or b0<=0:return None
    t=datetime.fromisoformat(opened_at.replace('Z','+00:00'))
    if t.utcoffset() is None:raise ValueError('CYCLE_OPEN_TIMEZONE_REQUIRED')
    return {'schema_version':'V82.DailySliceCycle.v1',
        'slice_cycle_id':cycle_id(owner=owner,session_id=session_id,exchange=exchange,asset_id=asset_id,profile_version=profile_version),
        'owner':deepcopy(owner),'session_id':session_id,'exchange':exchange,'asset_id':asset_id,
        'profile_version':profile_version,'opened_at':opened_at,'G0':str(g0),'B0':str(b0),
        'initial_speed':deepcopy(speed_result),'state':'OPEN','intents':{},'events':{},'revision':0,
        'cash_reservation_created':False,'trade_action':'NO_TRADE'}


def _validate_intent_transition(before,after):
    """Live commitments move to spent on fills; only confirmed terminals release."""
    if after['state'] in RELEASED and after.get('receipt',{}).get('release_confirmed') is not True:
        raise ValueError('CYCLE_RELEASE_CONFIRMATION_REQUIRED')
    if before is None:return
    old_filled,new_filled=(_amount(r['filled_amount']) for r in (before,after))
    if new_filled<old_filled:raise ValueError('CYCLE_FILL_MUST_NOT_DECREASE')
    if before['state'] in RELEASED and after['state'] in LIVE:
        raise ValueError('TERMINAL_INTENT_CANNOT_REOPEN')
    if after['state'] in LIVE:
        old_remaining,new_remaining=(_amount(r['remaining_amount']) for r in (before,after))
        values=(old_filled,new_filled,old_remaining,new_remaining)
        with localcontext() as ctx:
            ctx.prec=max(80,max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+2)
            if new_filled+new_remaining<old_filled+old_remaining:
                raise ValueError('CYCLE_UNCONFIRMED_COMMITMENT_REDUCTION')


def validate_cycle(cycle):
    if cycle.get('schema_version')!='V82.DailySliceCycle.v1':raise ValueError('CYCLE_SCHEMA_MISMATCH')
    expected=cycle_id(**{k:cycle[k] for k in ('owner','session_id','exchange','asset_id','profile_version')})
    if cycle['slice_cycle_id']!=expected:raise ValueError('CYCLE_IDENTITY_MISMATCH')
    factor=_factor(cycle['initial_speed'])
    if factor is None or _amount(cycle['B0'])!=_amount(cycle['G0'])*factor:raise ValueError('CYCLE_INITIAL_BUDGET_MUTATED')
    spent=committed=Decimal(0)
    for iid,item in cycle['intents'].items():
        if not iid or item['intent_id']!=iid or item['state'] not in LIVE|RELEASED:raise ValueError('CYCLE_INTENT_IDENTITY_OR_STATE')
        _validate_intent_transition(None,item)
        spent+=_amount(item['filled_amount'])
        if item['state'] in LIVE:committed+=_amount(item['remaining_amount'])
        elif _amount(item['remaining_amount'])!=0:raise ValueError('TERMINAL_INTENT_HAS_COMMITMENT')
    if spent+committed>_amount(cycle['B0']):raise ValueError('CYCLE_SPENT_COMMITTED_EXCEED_INITIAL_BUDGET')
    return spent,committed


def cycle_room(cycle, *, speed_result, permission, trend_allowed, session_id, session_open):
    spent,committed=validate_cycle(cycle);factor=_factor(speed_result)
    current=min(_amount(cycle['B0']),_amount(cycle['G0'])*factor) if factor is not None else None
    room=max(current-spent-committed,Decimal(0)) if current is not None else None
    # Known prohibition short-circuits the new amount; original missing inputs
    # remain visible in speed_result, never converted into observed zero cash.
    if permission is False or truth(trend_allowed) is P.FALSE or session_open is False or session_id!=cycle['session_id'] or cycle['state']!='OPEN':room=Decimal(0)
    elif permission is not True or truth(trend_allowed) is P.UNKNOWN or session_open is not True:room=None
    return {'slice_cycle_id':cycle['slice_cycle_id'],'G0':cycle['G0'],'B0':cycle['B0'],
        'B_current':str(current) if current is not None else None,'cycle_spent':str(spent),
        'cycle_committed':str(committed),'cycle_room':str(room) if room is not None else None,
        'fixed_initial_gap_used':True,'cash_reservation_subtracted':False,'profile_version':VERSION}


def update_intent(cycle, *, event_id, intent_id, state, filled_amount, remaining_amount,
                  receipt, evaluation_at, speed_result, permission, trend_allowed=True, session_id, session_open):
    out=deepcopy(cycle);validate_cycle(out)
    if not event_id or not intent_id or state not in LIVE|RELEASED:raise ValueError('CYCLE_INTENT_EVENT_REQUIRED')
    if not receipt.get('source_reference') or not receipt.get('source_hash') or not receipt.get('available_at'):
        raise ValueError('CYCLE_LIFECYCLE_RECEIPT_REQUIRED')
    if receipt.get('owner')!=out['owner'] or receipt.get('asset_id')!=out['asset_id']:
        raise ValueError('CYCLE_RECEIPT_OWNER_ASSET_MISMATCH')
    def time(v):
        t=datetime.fromisoformat(v.replace('Z','+00:00'))
        if t.utcoffset() is None:raise ValueError('CYCLE_RECEIPT_TIMEZONE_REQUIRED')
        return t
    if not time(receipt['as_of'])<=time(receipt['available_at'])<=time(evaluation_at):
        raise ValueError('CYCLE_RECEIPT_NOT_AVAILABLE_AT_CUTOFF')
    if state in RELEASED and receipt.get('release_confirmed') is not True:
        raise ValueError('CYCLE_RELEASE_CONFIRMATION_REQUIRED')
    event={'event_id':event_id,'intent_id':intent_id,'state':state,'filled_amount':str(_amount(filled_amount)),
        'remaining_amount':str(_amount(remaining_amount)),'receipt':deepcopy(receipt)}
    if event_id in out['events']:
        if out['events'][event_id]!=digest(event):raise ValueError('CYCLE_EVENT_IDEMPOTENCY_CONFLICT')
        return out
    before=out['intents'].get(intent_id)
    _validate_intent_transition(before,event)
    if before:
        if datetime.fromisoformat(receipt['available_at'].replace('Z','+00:00'))<datetime.fromisoformat(before['receipt']['available_at'].replace('Z','+00:00')):
            raise ValueError('CYCLE_LIFECYCLE_TIME_REVERSED')
    if state in RELEASED and _amount(remaining_amount)!=0:raise ValueError('TERMINAL_INTENT_HAS_COMMITMENT')
    old_total=(_amount(before['filled_amount'])+(_amount(before['remaining_amount']) if before['state'] in LIVE else 0)) if before else Decimal(0)
    new_total=_amount(filled_amount)+(_amount(remaining_amount) if state in LIVE else 0)
    incremental=max(new_total-old_total,Decimal(0))
    room=cycle_room(out,speed_result=speed_result,permission=permission,trend_allowed=trend_allowed,
        session_id=session_id,session_open=session_open)['cycle_room']
    if incremental>0 and (room is None or incremental>_amount(room)):raise ValueError('CYCLE_NEW_COMMITMENT_EXCEEDS_ROOM')
    out['intents'][intent_id]={'intent_id':intent_id,'state':state,'filled_amount':event['filled_amount'],
        'remaining_amount':event['remaining_amount'],'receipt':deepcopy(receipt)}
    out['events'][event_id]=digest(event);out['revision']+=1;validate_cycle(out)
    return out


class CycleLedgerStore:
    """Durable CAS storage, supplied by the operator, separate from broker cash.

    Reads never create an empty account ledger. Creation is explicit and only
    establishes a planning ledger, not an assertion about actual broker orders.
    """
    def __init__(self,path,*,create=False):
        self.path=Path(path)
        if not self.path.is_file() and not create:raise ValueError('CYCLE_LEDGER_SOURCE_UNAVAILABLE')
        if create:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(self.path) as db:
                db.execute('CREATE TABLE IF NOT EXISTS cycles (cycle_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS intent_owner (scope TEXT PRIMARY KEY, cycle_id TEXT NOT NULL)')

    def get(self,key):
        with sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM cycles WHERE cycle_id=?',(key,)).fetchone()
        out=json.loads(row[0]) if row else None
        if out is not None:validate_cycle(out)
        return out

    def save(self,cycle,*,expected_revision,validate_shared=None):
        validate_cycle(cycle);key=cycle['slice_cycle_id'];payload=json.dumps(cycle,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        with sqlite3.connect(self.path,isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT revision,payload FROM cycles WHERE cycle_id=?',(key,)).fetchone()
                if row and row[1]==payload:db.execute('COMMIT');return
                if (None if row is None else row[0])!=expected_revision:raise ValueError('CYCLE_LEDGER_CAS_CONFLICT')
                if row:
                    previous=json.loads(row[1])
                    for field in ('G0','B0','initial_speed','owner','session_id','asset_id','exchange','profile_version','opened_at'):
                        if previous[field]!=cycle[field]:raise ValueError('CYCLE_INITIAL_FACTS_IMMUTABLE:'+field)
                    if cycle['revision']<=row[0]:raise ValueError('CYCLE_REVISION_MUST_ADVANCE')
                    if any(cycle['events'].get(k)!=v for k,v in previous['events'].items()):raise ValueError('CYCLE_HISTORY_CANNOT_BE_RESET')
                    for iid,item in previous['intents'].items():
                        current=cycle['intents'].get(iid)
                        if current is None:raise ValueError('CYCLE_FILL_MUST_NOT_DECREASE')
                        _validate_intent_transition(item,current)
                for iid in cycle['intents']:
                    scope=digest({'owner':cycle['owner'],'asset_id':cycle['asset_id'],'intent_id':iid})
                    old=db.execute('SELECT cycle_id FROM intent_owner WHERE scope=?',(scope,)).fetchone()
                    if old and old[0]!=key:raise ValueError('INTENT_ALREADY_BELONGS_TO_ANOTHER_CYCLE')
                    db.execute('INSERT OR IGNORE INTO intent_owner VALUES (?,?)',(scope,key))
                if validate_shared is not None:
                    others=[json.loads(r[0]) for r in db.execute('SELECT payload FROM cycles WHERE cycle_id<>?',(key,))]
                    validate_shared(others,cycle)
                db.execute('INSERT INTO cycles VALUES (?,?,?) ON CONFLICT(cycle_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',
                    (key,cycle['revision'],payload));db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
