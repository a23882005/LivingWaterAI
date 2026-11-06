"""Nine-stage DESIGN CANDIDATE 0.1.0. Research only; no broker/DB writes.

New early-right parameters are proposals, not an approved change to V82.
qP/qV/safety are typed upstream inputs, never inferred from price here.
"""
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from . import approved_v04_numeric as n

VERSION='NINE_STAGE_EARLY_RIGHT_0.1.0_CANDIDATE'
RATES={1:10,2:20,3:30,4:40,5:55,6:70,7:85,8:95,9:100}
PARAMS={'breakout_lookback':5,'off_low_factor':'1.01','failure_factor':'.99',
        'retest_lower':'.995','retest_upper':'1.005','episode_sessions':10,
        'confirmation_closes':2,'maturity_votes':3,'qv_entry':'60','qp_left2':'75','qv_left3':'40'}

def AND(*xs):
    if any(x is False for x in xs): return False
    return None if any(x is None for x in xs) else True
def OR(*xs):
    if any(x is True for x in xs): return True
    return None if any(x is None for x in xs) else False
def NOT(x):return None if x is None else not x
def compare(a,op,b):
    if a is None or b is None:return None
    a,b=D(str(a)),D(str(b))
    if not a.is_finite() or not b.is_finite():return None
    return {'>':lambda:a>b,'>=':lambda:a>=b,'<':lambda:a<b,'<=':lambda:a<=b}[op]()
def votes(xs,k):
    t=sum(x is True for x in xs);u=sum(x is None for x in xs)
    return True if t>=k else False if t+u<k else None
def select(flags):
    # Uncertain higher eligibility never becomes executable lower eligibility.
    for s in range(9,1,-1):
        if flags[s] is None:return None
        if flags[s] is True:return s
    return 1

def features(rows):
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        return _features(rows)
def _features(rows):
    keys=('Open','High','Low','Close','Volume')
    arrays={k:[D(str(r[k])) if r.get(k) is not None else None for r in rows] for k in keys}
    o,h,l,c,v=(arrays[k] for k in keys)
    for i,r in enumerate(rows):
        if i and r['Date']<=rows[i-1]['Date']:raise ValueError('DATES_NOT_STRICTLY_INCREASING')
        if any(x is not None and not x.is_finite() for x in (o[i],h[i],l[i],c[i],v[i])):raise ValueError('NONFINITE_BAR')
        if any(x is not None and x<=0 for x in (o[i],h[i],l[i],c[i])):raise ValueError('NONPOSITIVE_PRICE')
        if v[i] is not None and v[i]<0:raise ValueError('NEGATIVE_VOLUME')
        if None not in (o[i],h[i],l[i],c[i]) and not l[i]<=min(o[i],c[i])<=max(o[i],c[i])<=h[i]:raise ValueError('INVALID_OHLC')
    ma={k:n.sma(c,k) for k in (5,10,20)}
    _,k,kd=n.kd(h,l,c);_,_,dif,dea,hist=n.macd(c)
    _,_,rsi=n.rsi(c);_,_,emv=n.emv(h,l,v);vm=n.sma(v,20)
    out=[]
    def a(xs,i):return xs[i] if i>=0 else None
    def cm(xs,i,op,ys,j):return compare(a(xs,i),op,a(ys,j))
    def mn(xs,i,j):
        w=xs[i:j+1] if i>=0 else []
        return min(w) if len(w)==j-i+1 and w and None not in w else None
    def mx(xs,i,j):
        w=xs[i:j+1] if i>=0 else []
        return max(w) if len(w)==j-i+1 and w and None not in w else None
    for t in range(len(rows)):
        td=n.td_count(c[:t+1]);gold=AND(cm(k,t-1,'<=',kd,t-1),cm(k,t,'>',kd,t))
        span=None if h[t] is None or l[t] is None else h[t]-l[t]
        frac=(c[t]-l[t])/span if span and c[t] is not None else None
        m=[None if td is None else 5<=td[1]<=9,
           OR(gold,AND(cm(k,t-2,'>=',k,t-1),cm(kd,t-2,'>=',kd,t-1),cm(k,t,'>',k,t-1),cm(kd,t,'>=',kd,t-1))),
           AND(cm(hist,t-1,'<',hist,t),compare(hist[t],'<',0)),
           cm(dif,t,'>',dif,t-1),cm(emv,t,'>',emv,t-1),cm(rsi,t,'>',rsi,t-1),
           AND(cm(l,t-2,'<=',l,t-1),cm(l,t-1,'<=',l,t),cm(c,t,'>=',c,t-2)),
           OR(AND(cm(c,t,'<',c,t-1),compare(v[t],'<',vm[t])),
              AND(compare(span,'>',0),cm(c,t,'>=',o,t),compare(frac,'>=','.75'),compare(l[t],'<',mn(l,t-5,t-1))))]
        out.append({'Date':rows[t]['Date'],'C':c[t],'O':o[t],'H':h[t],'L':l[t],
                    'MA5':ma[5][t],'MA10':ma[10][t],'MA20':ma[20][t],
                    'M':m,'M_ok':votes(m,3),'M_count':sum(x is True for x in m),
                    'P5':mx(h,t-5,t-1),'L5':mn(l,t-5,t-1),
                    'low3':mn(l,t-2,t),'DIF':dif[t],'Hist':hist[t],'RSI':rsi[t]})
    return out

def right_episodes(fs):
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        return _right_episodes(fs)

def _right_episodes(fs):
    """Prefix-only state. Fixed level from t-5..t-1; never future pivot low.
    Breakout event needs close cross AND 1% off prior5 low AND >=3 M votes.
    Live episode: invalidation first; retest/two-close confirm second; expiry last.
    New breakout evaluated only if no live episode; success latched for lifespan.
    Old success does not imply Safety recovery. Missing episode H/L/C poisons state.
    """
    active=None;out=[]
    for t,f in enumerate(fs):
        prior=fs[t-1] if t else None
        event=AND(compare(prior['C'] if prior else None,'<=',f['P5']),
                  compare(f['C'],'>',f['P5']),compare(f['C'],'>=',None if f['L5'] is None else f['L5']*D('1.01')),f['M_ok'])
        reason='NO_EPISODE';r1=False;r2=False
        if active is not None:
            age=t-active['b'];level=active['level'];anchor=active['anchor']
            if any(f[x] is None for x in ('H','L','C')) or prior is None or prior['C'] is None:
                reason='INVALIDATED_MISSING_BAR';active=None;r1=r2=None
            elif f['C']<D('.99')*level or f['L']<anchor:
                reason='FAILED';active=None
            else:
                touch=f['L']<=D('1.005')*level and f['H']>=D('.995')*level
                active['touched']=active['touched'] or touch
                two=(age>=1 and prior['C']>=level and f['C']>=level)
                retest=(age>=1 and active['touched'] and f['C']>=level and f['C']>prior['C'])
                structure=AND(compare(f['C'],'>=',f['MA10']),compare(f['MA5'],'>',f['MA10']),
                              compare(f['MA5'],'>',prior['MA5']))
                success=AND(OR(two,retest),structure)
                if success is True:active['confirmed']=True
                r1=True;r2=True if active['confirmed'] else success
                reason='CONFIRMED' if active['confirmed'] else 'LIVE'
                if age>10:
                    active=None;r1=False;r2=False;reason='EXPIRED'
        if active is None and reason not in ('FAILED','INVALIDATED_MISSING_BAR','EXPIRED'):
            if event is True:
                active={'b':t,'level':f['P5'],'anchor':f['L5'],'touched':False,'confirmed':False}
                r1=True;r2=False;reason='BREAKOUT'
            elif event is None:r1=None;r2=False;reason='EVENT_UNKNOWN'
        out.append({'event':event,'early_right1':r1,'early_right2':r2,'reason':reason,
                    'episode':None if active is None else dict(active)})
    return out

def eligibility(f,prior,r,*,depth,qp,qv,a_normal,valuation_legal,up):
    legal=valuation_legal
    l1=AND(legal,compare(depth,'>',0),compare(qv,'<',60))
    l2=AND(l1,compare(qp,'>=',75),a_normal)
    l3=AND(l2,compare(qv,'<',40))
    b1=AND(legal,compare(depth,'>',0),compare(qv,'<',60),f['M'][6],f['M_ok'])
    b2=AND(b1,compare(f['C'],'>=',f['MA5']),compare(f['MA5'],'>',None if prior is None else prior['MA5']))
    b3=AND(b2,compare(f['C'],'>=',f['MA10']),compare(f['MA5'],'>',f['MA10']),
           compare(f['MA10'],'>=',None if prior is None else prior['MA10']))
    right1=AND(legal,OR(r['early_right1'],up))
    right2=AND(legal,OR(r['early_right2'],up),compare(qv,'<',60),a_normal)
    return {2:l1,3:l2,4:l3,5:b1,6:b2,7:b3,8:right1,9:right2}

def replay(rows,inputs):
    if len(rows)!=len(inputs):raise ValueError('INPUT_LENGTH_MISMATCH')
    fs=features(rows);rs=right_episodes(fs);out=[]
    for i,(f,r,inp) in enumerate(zip(fs,rs,inputs)):
        flags=eligibility(f,fs[i-1] if i else None,r,**{k:inp.get(k) for k in
            ('depth','qp','qv','a_normal','valuation_legal','up')})
        for k in ('qp','qv'):
            if inp.get(k) is not None and not 0<=D(str(inp[k]))<=100:raise ValueError('PERCENTILE_OUT_OF_RANGE')
        stage=select(flags) if inp.get('valuation_legal') is True else None
        # All externally required safety/authorization inputs must be explicit.
        base_safety=AND(*(inp.get(k) for k in ('data_pass','authorized','fundamental','gate_clear','down_clear','higher_risk_clear')))
        level=inp.get('credit_level');credit=None if level is None else (
            level<=1 or level==2 and inp.get('core_etf') is True and inp.get('high_beta') is False)
        if stage is not None and stage>=8:credit=None if level is None else level<=1
        if stage is None and level==2 and credit is True:credit=None
        safety=AND(base_safety,credit)
        out.append({'Date':f['Date'],'C':f['C'],'stage':stage,'rate_pct':RATES.get(stage),
            'eligibility':flags,'right':r,'M':f['M'],'M_count':f['M_count'],'M_ok':f['M_ok'],
            'buy_permission':safety,'trade_action':'NO_TRADE','profile':VERSION})
    return out
