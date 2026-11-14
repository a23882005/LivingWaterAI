"""Explicit research replay of the PM contract, with local dependency views.

The frozen PM producer owns M, R and eligibility. Only two named experimental
policies change it. No caller of the formal runtime imports this package.
"""
from copy import deepcopy
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from hashlib import sha256
from pathlib import Path
import json

from .pm_reference import candidate as base
from .pm_reference import candidate_v03 as v03
from .pm_reference import independent_right

DEFAULT_ENABLED = False
VERSION = 'FAMILY_NINE_STAGE_ISOLATED_1.0.0_REVIEW'
PROFILES = ('BASELINE_V03', 'PARTIAL_VIEW_ONLY', 'CONFIRMED_UNTIL_ORIGINAL_FAILURE',
            'LOW_PLATEAU_EXACT_EQUAL', 'COMBINED_CONFIRMED_AND_PLATEAU')
PERSIST = frozenset((PROFILES[2], PROFILES[4]))
PLATEAU = frozenset((PROFILES[3], PROFILES[4]))
IDENTITY = ('instrument', 'listing', 'currency', 'price_basis', 'calendar', 'vintage')
TRUTH = {True: 'TRUE', False: 'FALSE', None: 'UNKNOWN'}


def boolean(value):
    if value is None or type(value) is bool:
        return value
    if type(value) is str and value in ('TRUE', 'FALSE', 'UNKNOWN'):
        return {'TRUE': True, 'FALSE': False, 'UNKNOWN': None}[value]
    raise ValueError('STRICT_THREE_STATE_REQUIRED')


def number(value, *, minimum=None, maximum=None):
    if value is None:
        return None
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, D)):
        raise ValueError('EXACT_DECIMAL_REQUIRED')
    x = D(value)
    if not x.is_finite():
        raise ValueError('FINITE_DECIMAL_REQUIRED')
    if minimum is not None and x < D(minimum) or maximum is not None and x > D(maximum):
        raise ValueError('DECIMAL_DOMAIN_REQUIRED')
    return x


def _stamp(value):
    from datetime import datetime
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('EXPLICIT_TIMEZONE_REQUIRED')
    return result


def _inputs(inputs):
    out = []
    for original in inputs:
        x = deepcopy(original)
        for key in ('up', 'a_normal', 'valuation_legal', 'fundamental'):
            x[key] = boolean(x.get(key))
        for key in ('qp', 'qv'):
            x[key] = number(x.get(key), minimum=0, maximum=100)
        x['depth'] = number(x.get('depth'), minimum=0, maximum=1)
        out.append(x)
    return out


def _rows(rows, inputs, source):
    if any(not isinstance(source.get(k), str) or not source[k].strip() for k in IDENTITY):
        raise ValueError('EXPLICIT_MARKET_IDENTITY_REQUIRED')
    if source.get('data_provenance') not in ('SOURCE_BACKED', 'SYNTHETIC'):
        raise ValueError('DATA_PROVENANCE_REQUIRED')
    accepted = []; bound_inputs = []; previous = None; excluded_after_accepted = False
    for row, inp in zip(rows, inputs):
        if not isinstance(row.get('Date'), str) or previous is not None and row['Date'] <= previous:
            raise ValueError('DATES_NOT_STRICTLY_INCREASING')
        previous = row['Date']
        if source['data_provenance'] == 'SOURCE_BACKED':
            cutoff = inp.get('decision_cutoff') or source.get('decision_cutoff')
            available = row.get('available_at') or source.get('available_at')
            close = row.get('session_close_at')
            if not cutoff or not available or not close:
                raise ValueError('COMPLETED_SESSION_AND_AVAILABILITY_REQUIRED')
            if max(_stamp(available), _stamp(close)) > _stamp(cutoff):
                excluded_after_accepted = bool(accepted)
                continue
        clean = deepcopy(row)
        if excluded_after_accepted:
            clean['segment_break'] = True
            excluded_after_accepted = False
        for key in ('Open', 'High', 'Low', 'Close', 'Volume'):
            value = number(row.get(key), minimum=0)
            if key != 'Volume' and value is not None and value <= 0:
                raise ValueError('POSITIVE_PRICE_REQUIRED')
            clean[key] = value
        if all(clean[k] is not None for k in ('Open', 'High', 'Low', 'Close')):
            if not clean['Low'] <= min(clean['Open'], clean['Close']) <= max(clean['Open'], clean['Close']) <= clean['High']:
                raise ValueError('INVALID_OHLC')
        accepted.append(clean); bound_inputs.append(inp)
    return accepted, bound_inputs


def low_references(rows):
    """Strict low plus maximal exact-equal plateau. No future publication."""
    lows = [r['Low'] for r in rows]; refs = []
    for i in range(2, len(lows)-2):
        w = lows[i-2:i] + lows[i+1:i+3]
        if lows[i] is not None and None not in w and lows[i] < min(w):
            refs.append({'pivot_index':i, 'confirmed_at':i+2, 'value':lows[i], 'kind':'STRICT_LOW'})
    a = 0
    while a < len(lows):
        b = a
        while b+1 < len(lows) and lows[a] is not None and lows[b+1] == lows[a]:
            b += 1
        if b > a and a >= 2 and b+2 < len(lows):
            surround = lows[a-2:a] + lows[b+1:b+3]
            if None not in surround and all(x > lows[a] for x in surround):
                refs.append({'pivot_index':b, 'confirmed_at':b+2, 'value':lows[a],
                    'kind':'PLATEAU_LOW', 'start_index':a})
        a = b+1
    # A plateau and strict pivot cannot share an index; enforce single identity.
    return sorted({r['pivot_index']:r for r in refs}.values(), key=lambda r:r['pivot_index'])


def _pending_plateau(lows, t):
    a = 0
    while a <= t:
        b = a
        while b+1 <= t and lows[b+1] == lows[a]:
            b += 1
        if b > a and b >= t-20:
            if a < 2 and (b+2 > t or all(x > lows[a] for x in lows[b+1:b+3])):
                return True
            if a >= 2 and all(x > lows[a] for x in lows[a-2:a]) and b+2 > t:
                if all(x > lows[a] for x in lows[b+1:t+1]):
                    return True
        a = b+1
    return False


def _features(rows, source, plateau):
    """Restart the existing numeric producer at each identity/gap boundary."""
    fs = []; begin = 0; identity = None; boundaries = []
    for i, row in enumerate(rows):
        current = tuple(row.get(k, source[k]) for k in IDENTITY)
        missing = any(row[k] is None for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
        split = missing or row.get('segment_break') is True or identity is not None and current != identity
        if split and begin < i:
            boundaries.append((begin, i))
        if missing:
            boundaries.append((i, i+1)); begin = i+1
        elif split:
            begin = i
        identity = current
    if begin < len(rows):
        boundaries.append((begin, len(rows)))
    for start, stop in boundaries:
        segment = rows[start:stop]
        produced = independent_right.produce(segment)
        close = [r['Close'] for r in segment]; high = [r['High'] for r in segment]
        low = [r['Low'] for r in segment]; volume = [r['Volume'] for r in segment]
        rsv,k,d = base.n.kd(high,low,close)
        _,_,emv = base.n.emv(high,low,volume)
        volma = base.n.sma(volume,20)
        lows = [r['Low'] for r in segment]
        refs = low_references(segment) if plateau else []
        for t, f in enumerate(produced):
            td = base.n.td_count(close[:t+1])
            f.update(K=k[t],D=d[t],RSV=rsv[t],EMV=emv[t],Volume=volume[t],VolMA20=volma[t],
                low_td9=None if td is None else td[1])
            f['_segment_start'] = start
            f['_segment_break'] = t == 0 and start != 0
            if plateau:
                confirmed = [r for r in refs if r['confirmed_at'] <= t]
                window = [r for r in confirmed if t-20 <= r['pivot_index'] <= t]
                ref = window[-1] if window else None
                complete = t >= 22 and all(x is not None for x in lows[max(0,t-22):t+1])
                pending = _pending_plateau(lows, t)
                off = base.compare(f['C'], '>=', ref['value']*D('1.01')) if ref else (
                    False if complete and not pending else None)
                higher = None
                if len(confirmed) >= 2:
                    a, b = confirmed[-2:]
                    higher = t-a['pivot_index'] <= 60 and t-b['pivot_index'] <= 20 and b['value'] > a['value']
                elif t >= 62 and not pending:
                    higher = False
                f['R'][0] = higher; f['OffLow'] = off
                f['R_count'] = sum(x is True for x in f['R'])
                f['R_unknown'] = sum(x is None for x in f['R'])
                f['R_votes_ok'] = base.votes(f['R'], 3)
                f['R_ok'] = base.AND(off, f['R_votes_ok'])
                f['low_reference'] = deepcopy(ref)
                f['low_reference_status'] = ('CONFIRMED_REFERENCE' if ref else
                    'COMPLETE_WINDOW_NO_CONFIRMED_LOW' if complete and not pending else 'INCOMPLETE_REFERENCE_WINDOW')
                f['confirmed_low_references'] = deepcopy(confirmed)
            fs.append(f)
    return fs


def right_episodes(fs, *, persistent=False):
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        return _right_episodes(fs,persistent=persistent)


def _right_episodes(fs, *, persistent=False):
    if not persistent and not any(f.get('_segment_break') for f in fs):
        return v03.right_episodes(fs)
    # Keep the reference predicates/precedence. The only lifetime change is the
    # explicit confirmed-state exception to age>10; R10 is never modified.
    active = None; out = []
    for t, f in enumerate(fs):
        p = fs[t-1] if t else None
        event = base.AND(base.compare(p['C'] if p else None, '<=', f['P5']),
            base.compare(f['C'], '>', f['P5']), base.compare(f['C'], '>=',
                f['L5']*D('1.01') if f['L5'] is not None else None), f['R_ok'])
        reason = 'NO_EPISODE'; r1 = r2 = pullback = continuous = False
        if any(f[k] is None for k in ('H','L','C')):
            active = None; reason = 'INVALIDATED_MISSING_BAR'; r1 = r2 = None
        elif f.get('_segment_break'):
            active = None; reason = 'INVALIDATED_SEGMENT_BOUNDARY'; r1 = r2 = None
        elif active is not None:
            b = active['b']; level = active['level']; anchor = active['anchor']
            if any(f[k] is None for k in ('H','L','C')) or p is None or p['C'] is None:
                active = None; r1 = r2 = None; reason = 'INVALIDATED_MISSING_BAR'
            elif f['C'] < D('.99')*level or f['L'] < anchor:
                active = None; reason = 'FAILED'
            elif t-b > 10 and not (persistent and active['confirmed']):
                active = None; reason = 'EXPIRED'
            else:
                # Never admit a new confirmation after the original window.
                if t-b <= 10:
                    touch = f['L'] <= D('1.005')*level and f['H'] >= D('.995')*level
                    j = active['touch_day']
                    if j is not None:
                        pullback = j+1 <= t <= min(j+2,b+10) and f['C'] >= level and f['C'] > p['C']
                        if t >= j+2:
                            active['touch_day'] = None
                    if active['touch_day'] is None and f['C'] < p['C'] and touch:
                        active['touch_day'] = t
                    three = base.AND(*(base.compare(fs[i]['C'],'>=',level)
                        for i in range(t-2,t+1))) if t >= b+2 else False
                    continuous = base.AND(three,base.compare(f['C'],'>=',f['MA20']),
                        base.compare(f['MA20'],'>',p['MA20']))
                    structure = base.AND(base.compare(f['C'],'>=',f['MA10']),
                        base.compare(f['MA5'],'>',f['MA10']),base.compare(f['MA5'],'>',p['MA5']))
                    success = base.AND(base.OR(pullback,continuous),structure)
                    if success is True:
                        if not active['confirmed']:
                            active['confirmation_session'] = f.get('Date',t)
                        active['confirmed'] = True
                        active['confirmed_path'] = 'RETEST' if pullback else 'MA20_CONTINUATION'
                else:
                    success = True  # Only a previously confirmed event reaches here.
                r1 = True; r2 = True if active['confirmed'] else success
                reason = 'CONFIRMED' if active['confirmed'] else 'LIVE'
        if active is None and reason == 'NO_EPISODE':
            if event is True:
                active = {'b':t,'level':f['P5'],'anchor':f['L5'],'touch_day':None,
                    'confirmed':False,'confirmed_path':None,'confirmation_session':None}
                r1 = True; r2 = False; reason = 'BREAKOUT'
            elif event is None:
                r1 = None; r2 = False; reason = 'EVENT_UNKNOWN'
        out.append({'event':event,'early_right1':r1,'early_right2':r2,'reason':reason,
            'retest_path':pullback,'continuous_path':continuous,'episode':deepcopy(active),
            'entry_confirmation_source':'R_OK_NOT_M_OK','R_ok':f['R_ok']})
    return out


def fact(name, value, *, dependencies=(), numeric_inputs=None, source=None, reason=None):
    value = boolean(value)
    return {'name':name,'value':value,'truth':TRUTH[value],
        'dependencies':sorted(set(dependencies)),
        'minimal_missing':sorted(set(dependencies)) if value is None else [],
        'numeric_inputs':deepcopy(numeric_inputs or {}),'source':deepcopy(source or {}),
        'reason_codes':[reason or ('DEPENDENCY_UNKNOWN' if value is None else 'CONDITION_PROVED')]}


def _join(name, op, *nodes):
    value = (base.AND if op == 'AND' else base.OR)(*(n['value'] for n in nodes))
    deps = sorted({d for n in nodes for d in n['dependencies']})
    missing = sorted({d for n in nodes for d in n['minimal_missing']}) if value is None else []
    return {**fact(name,value,dependencies=deps),'minimal_missing':missing,'operator':op,
            'operands':deepcopy(list(nodes))}


def condition_view(f, p, r, inp, source):
    unset = object()
    def flag(k, value=unset):
        return fact(k,inp.get(k) if value is unset else value,dependencies=[k],source=source)
    def cmp(name, a, op, b, deps):
        return fact(name,base.compare(a,op,b),dependencies=deps,
            numeric_inputs={'left':a,'operator':op,'right':b},source=source)
    def AND(name,*xs):return _join(name,'AND',*xs)
    def OR(name,*xs):return _join(name,'OR',*xs)
    legal = flag('valuation_legal'); depth = cmp('depth>0',inp['depth'],'>',0,['depth'])
    q60 = cmp('qV<60',inp['qv'],'<',60,['qv']); normal = flag('a_normal')
    l1 = AND('L1',legal,depth,q60)
    l2 = AND('L2',l1,cmp('qP>=75',inp['qp'],'>=',75,['qp']),normal)
    l3 = AND('L3',l2,cmp('qV<40',inp['qv'],'<',40,['qv']))
    b1 = AND('B1',legal,depth,q60,flag('M7',f['M'][6]),flag('M_ok',f['M_ok']))
    b2 = AND('B2',b1,cmp('C>=MA5',f['C'],'>=',f['MA5'],['C','MA5']),
        cmp('MA5 rising',f['MA5'],'>',p['MA5'] if p else None,['MA5','prior.MA5']))
    b3 = AND('B3',b2,cmp('C>=MA10',f['C'],'>=',f['MA10'],['C','MA10']),
        cmp('MA5>MA10',f['MA5'],'>',f['MA10'],['MA5','MA10']),
        cmp('MA10 nondecreasing',f['MA10'],'>=',p['MA10'] if p else None,['MA10','prior.MA10']))
    right1 = AND('RIGHT1',legal,OR('E1 OR Up',flag('E1',r['early_right1']),flag('up')))
    right2 = AND('RIGHT2',legal,OR('E2 OR Up',flag('E2',r['early_right2']),flag('up')),q60,normal)
    nodes = dict(zip(range(2,10),(l1,l2,l3,b1,b2,b3,right1,right2)))
    expected = base.eligibility(f,p,r,**{k:inp[k] for k in ('depth','qp','qv','a_normal','valuation_legal','up')})
    assert {k:n['value'] for k,n in nodes.items()} == expected, 'REFERENCE_CONDITION_DRIFT'
    return nodes


def financial_view(stage, mode, inp):
    """Candidate arithmetic only. Original slice/MIN/lot stays upstream-owned."""
    raw = inp.get('financial') or {}
    project = number(raw.get('project_target'),minimum=0)
    target = project*D(base.RATES[stage])/100 if project is not None and stage else None
    amounts = [number(raw.get(k),minimum=0) for k in ('confirmed','active_buy','active_sell')]
    projected = amounts[0]+amounts[1]-amounts[2] if None not in amounts else None
    gap = target-projected if target is not None and projected is not None else None
    permission = boolean(raw.get('permission'))
    known_zero = permission is False or gap is not None and gap <= 0
    return {'scope':'ISOLATED_CANDIDATE_DIAGNOSTIC__NOT_A_FORMAL_ORDER_OR_CYCLE',
        'Target':{'value':target,'minimal_missing':[] if target is not None else
            (['project_target'] if project is None else [])+(['final_stage'] if stage is None else [])},
        'Projected':{'value':projected,'minimal_missing':[k for k,v in zip(
            ('confirmed','active_buy','active_sell'),amounts) if v is None]},
        'Gap':{'value':gap,'minimal_missing':([] if target is not None else ['Target'])+
            ([] if projected is not None else ['Projected'])},
        'Permission':{'value':permission,'minimal_missing':[] if permission is not None else ['original_buy_permission']},
        'slice':{'value':None,'minimal_missing':['original_cycle_ledger_and_daily_slice']},
        'final_amount':{'value':D(0) if known_zero else None,'minimal_missing':[] if known_zero else
            ['original_slice_shared_MIN_fees_lot_cash_caps']},
        'mode_for_original_speed':mode,'automatic_sell':False,'broker_execution_authorized':False,
        'trade_action':'NO_TRADE'}


def _replay(rows, inputs, *, source, profile, compact_daily=False):
    inputs = _inputs(inputs); rows, inputs = _rows(rows, inputs, source)
    fs = _features(rows, source, profile in PLATEAU)
    rs = right_episodes(fs,persistent=profile in PERSIST); out = []
    rule_files = [Path(__file__),Path(__file__).with_name('source_view.py'),
        *sorted(Path(__file__).with_name('pm_reference').glob('*.py'))]
    rules = sha256(b''.join(p.name.encode()+p.read_bytes() for p in rule_files)+profile.encode()).hexdigest()
    for i,(f,r,inp) in enumerate(zip(fs,rs,inputs)):
        p = fs[i-1] if i and f['_segment_start'] == fs[i-1]['_segment_start'] else None
        conditions = condition_view(f,p,r,inp,source)
        flags = {k:n['value'] for k,n in conditions.items()}
        up = inp['up']; right = base.OR(r['early_right1'],r['early_right2'])
        left = base.OR(*(flags[s] for s in range(2,8)))
        mode = ('TREND' if up is True else None if up is None else
            'RIGHT' if right is True else None if right is None else
            'LEFT' if left is True else None if left is None else 'BASE')
        stage = base.select(flags) if (inp['valuation_legal'] is True and
            inp['fundamental'] is True and mode is not None) else None
        possible = []
        for s in range(9,1,-1):
            if flags[s] is not False:possible.append(s)
            if flags[s] is True:break
        else:possible.append(1)
        primitives = {k:deepcopy(f.get(k)) for k in ('O','H','L','C','MA5','MA10','MA20',
            'K','D','RSV','EMV','Volume','VolMA20','low_td9','DIF','Hist','RSI','P5','L5')}
        dependencies = {'M': [('low_td9',),('K','D','prior.K','prior.D','prior2.K','prior2.D'),
            ('Hist','prior.Hist'),('DIF','prior.DIF'),('EMV','prior.EMV'),('RSI','prior.RSI'),
            ('L','prior.L','prior2.L','C','prior2.C'),('C','prior.C','Volume','VolMA20','O','H','L','prior5.L')],
            'R': [('confirmed_low_references',),('K','D','prior.K','prior.D'),('Hist','prior.Hist'),
            ('DIF','prior.DIF'),('EMV','prior.EMV'),('RSI','prior3.RSI'),('C','MA20','prior.C','prior.MA20'),
            ('confirmed_highs','Volume','prior.VolMA20','C','prior.C'),('confirmed_highs','C','prior.C'),
            ('original_R9_event','fixed_P','subsequent_OHLC','prior.C')]}
        slot_inputs = {**primitives,'prior':{k:p.get(k) for k in primitives} if p else None}
        slots = {group:[{**fact(group+str(j+1),value,dependencies=dependencies[group][j],
            numeric_inputs=slot_inputs,source=source),'dedup_id':group+str(j+1),
            'method':'FROZEN_PM_V03_APPROVED_NUMERIC','version':VERSION,
            'as_of':f['Date']} for j,value in enumerate(f[group])] for group in ('M','R')}
        minimal = set()
        if up is None:minimal.add('up')
        for key in ('valuation_legal','fundamental'):
            if inp[key] is None:minimal.add(key)
        for s in range(9,1,-1):
            if flags[s] is None:minimal.update(conditions[s]['minimal_missing'])
            if flags[s] is True:break
        record = {'Date':f['Date'],'C':f['C'],'stage':stage,'rate_pct':base.RATES.get(stage),
            'normal_mode':mode,'final_stage':stage,'final_mode':mode,'possible_stage_range':sorted(possible),
            'eligibility':flags,'condition_results':{n['name']:n for n in conditions.values()},
            'proven_conditions':[n['name'] for n in conditions.values() if n['value'] is not None],
            'minimal_final_selection_missing':sorted(minimal) if stage is None else [],
            'known_final_selection_blocks':[k for k in ('valuation_legal','fundamental') if inp[k] is False],
            'right':r,'M':f['M'],'M_ok':f['M_ok'],'R':f['R'],'R_ok':f['R_ok'],
            'R_count':f['R_count'],'R_unknown':f['R_unknown'],'OffLow':f['OffLow'],
            'primitive_values':primitives,'slot_results':slots,
            'primitive_results':{k:{'value_state':'KNOWN' if v is not None else 'UNKNOWN',
                'value':v,'source':deepcopy(source),'as_of':f['Date'],
                'dependencies':['same_segment.completed_OHLCV'],
                'reason_codes':[] if v is not None else ['REQUIRED_WINDOW_OR_BAR_UNAVAILABLE']}
                for k,v in primitives.items()},
            'valuation_primitives':deepcopy(inp.get('valuation_primitives',[])),
            'qP':inp['qp'],'qV':inp['qv'],'depth':inp['depth'],
            'low_reference':deepcopy(f.get('low_reference')),
            'low_reference_status':f.get('low_reference_status','STRICT_V03_NO_REFERENCE_IS_UNKNOWN'),
            'confirmed_low_references':deepcopy(f.get('confirmed_low_references',[])),
            'financial_result':financial_view(stage,mode,inp),
            'profile':profile,'profile_id':VERSION+':'+profile,'rules_digest':rules,
            'data_provenance':source['data_provenance'],'formal_strategy_enabled':False,
            'strategy_effectiveness_claimed':False,'trade_action':'NO_TRADE'}
        if compact_daily and i != len(fs)-1:
            # Keep daily numbers, named slots, dependencies, reasons and event
            # state. Full nested proof trees are reproducible from the bound
            # input and remain included for the current query's final session.
            record['condition_results']={k:{a:v for a,v in n.items() if a!='operands'}
                for k,n in record['condition_results'].items()}
            for values in record['slot_results'].values():
                for n in values:
                    n['numeric_inputs_reference']='primitive_values / previous daily primitive_values'
                    n.pop('numeric_inputs')
            record.pop('primitive_results')
        out.append(record)
    return out


def replay(rows, inputs, *, source=None, profile='BASELINE_V03', enabled=DEFAULT_ENABLED, compact_daily=False):
    if type(enabled) is not bool:
        raise ValueError('EXPLICIT_BOOLEAN_ENABLE_REQUIRED')
    if not enabled:
        return {'status':'DISABLED','formal_strategy_enabled':False,'trade_action':'NO_TRADE'}
    if profile not in PROFILES:
        raise ValueError('UNKNOWN_PROFILE')
    if len(rows) != len(inputs):
        raise ValueError('INPUT_LENGTH_MISMATCH')
    with localcontext() as ctx:
        ctx.prec = 50; ctx.rounding = ROUND_HALF_EVEN
        return _replay(rows,inputs,source=source or {},profile=profile,compact_daily=compact_daily)


def compare_profiles(rows, inputs, *, source, enabled=DEFAULT_ENABLED):
    if not enabled:return replay(rows,inputs)
    runs = {p:replay(rows,inputs,source=source,profile=p,enabled=True) for p in PROFILES}
    fields = ('stage','normal_mode','rate_pct','eligibility','OffLow','R','R_ok','financial_result')
    differences = []
    baseline = runs['BASELINE_V03']
    for name, run in runs.items():
        if name == 'BASELINE_V03':continue
        for old,new in zip(baseline,run):
            changed = [k for k in fields if old[k] != new[k]]
            def event_semantics(row):
                r=row['right'];e=r.get('episode')
                return {k:r.get(k) for k in ('event','early_right1','early_right2','reason')} | {
                    'episode':{k:e.get(k) for k in ('b','level','anchor','confirmed','touch_day','confirmed_path')}
                        if e else None}
            if event_semantics(old) != event_semantics(new):changed.append('right')
            if changed:
                differences.append({'Date':old['Date'],'profile':name,'changed_fields':changed,
                    'policy_causes':(['CONFIRMED_LIFETIME'] if name in PERSIST else [])+
                        (['LOW_REFERENCE_POLICY'] if name in PLATEAU else [])})
    assert not any(d['profile']=='PARTIAL_VIEW_ONLY' for d in differences), 'PRESENTATION_CHANGED_DECISION'
    return {'profiles':runs,'differences':differences,'formal_strategy_enabled':False,
        'known_persistence_tradeoff':'Confirmation can survive a large drawdown until the ORIGINAL fixed P/A failure line.',
        'trade_action':'NO_TRADE'}
