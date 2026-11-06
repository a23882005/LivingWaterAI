"""Frozen comparison of EARLY RIGHT confirmation paths, research-only.

All variants keep the v0.1 left/bottom/target inputs unchanged. This file
does not alter the production rule set or infer actual cash/authorization.
"""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from . import candidate as base

VERSION='NINE_STAGE_CONFIRMATION_COMPARISON_0.2.0_CANDIDATE'
PROFILES=('BASELINE','RETEST_ONLY','MA20_ONLY','RETEST_OR_MA20')
FROZEN_PARAMETERS={'breakout_lookback':5,'off_low_factor':'1.01','failure_factor':'.99',
 'retest_lower':'.995','retest_upper':'1.005','episode_sessions':10,
 'retest_rebound_sessions':2,'continuous_closes':3,'slope_ma':20}

def right_episodes(fs,profile):
    if profile not in PROFILES:raise ValueError('UNKNOWN_PROFILE')
    if profile=='BASELINE':return base.right_episodes(fs)
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        return _right(fs,profile)

def _right(fs,profile):
    active=None;out=[]
    for t,f in enumerate(fs):
        p=fs[t-1] if t else None
        event=base.AND(base.compare(p['C'] if p else None,'<=',f['P5']),
          base.compare(f['C'],'>',f['P5']),base.compare(f['C'],'>=',
          f['L5']*D('1.01') if f['L5'] is not None else None),f['M_ok'])
        reason='NO_EPISODE';r1=False;r2=False;pullback=False;continuous=False
        if active is not None:
            age=t-active['b'];level=active['level'];anchor=active['anchor']
            if any(f[k] is None for k in ('H','L','C')) or p is None or p['C'] is None:
                active=None;r1=r2=None;reason='INVALIDATED_MISSING_BAR'
            elif f['C']<D('.99')*level or f['L']<anchor:
                active=None;reason='FAILED'
            elif age>10:
                active=None;reason='EXPIRED'
            else:
                # A retest needs an actual declining close AFTER the breakout,
                # a touch of the frozen level, then a later rising close.
                # Mere next-day overlap without a pullback is not a retest.
                touch=f['L']<=D('1.005')*level and f['H']>=D('.995')*level
                if active['touch_day'] is not None:
                    j=active['touch_day']
                    pullback=(j+1<=t<=min(j+2,active['b']+10)
                              and f['C']>=level and f['C']>p['C'])
                    if t>=j+2:active['touch_day']=None
                if active['touch_day'] is None and f['C']<p['C'] and touch:
                    active['touch_day']=t
                closes=[fs[i]['C'] for i in range(max(0,t-2),t+1)]
                three=base.AND(*(base.compare(x,'>=',level) for x in closes)) if t>=active['b']+2 else False
                continuous=base.AND(three,base.compare(f['C'],'>=',f['MA20']),
                    base.compare(f['MA20'],'>',p['MA20']))
                structure=base.AND(base.compare(f['C'],'>=',f['MA10']),
                    base.compare(f['MA5'],'>',f['MA10']),base.compare(f['MA5'],'>',p['MA5']))
                path={'RETEST_ONLY':pullback,'MA20_ONLY':continuous,
                      'RETEST_OR_MA20':base.OR(pullback,continuous)}[profile]
                success=base.AND(path,structure)
                if success is True:
                    active['confirmed']=True
                    active['confirmed_path']=('RETEST' if pullback and profile!='MA20_ONLY' else 'MA20_CONTINUATION')
                r1=True;r2=True if active['confirmed'] else success
                reason='CONFIRMED' if active['confirmed'] else 'LIVE'
        if active is None and reason not in ('FAILED','EXPIRED','INVALIDATED_MISSING_BAR'):
            if event is True:
                active={'b':t,'level':f['P5'],'anchor':f['L5'],'touch_day':None,
                  'confirmed':False,'confirmed_path':None}
                r1=True;r2=False;reason='BREAKOUT'
            elif event is None:r1=None;r2=False;reason='EVENT_UNKNOWN'
        out.append({'event':event,'early_right1':r1,'early_right2':r2,'reason':reason,
          'retest_path':pullback,'continuous_path':continuous,
          'episode':None if active is None else dict(active)})
    return out

def replay(rows,inputs,profile):
    fs=base.features(rows);rs=right_episodes(fs,profile);out=[]
    if len(rows)!=len(inputs):raise ValueError('INPUT_LENGTH_MISMATCH')
    for i,(f,r,inp) in enumerate(zip(fs,rs,inputs)):
        for key in ('qp','qv'):
            if inp.get(key) is not None and not 0<=D(str(inp[key]))<=100:raise ValueError('PERCENTILE_OUT_OF_RANGE')
        flags=base.eligibility(f,fs[i-1] if i else None,r,**{k:inp.get(k) for k in
          ('depth','qp','qv','a_normal','valuation_legal','up')})
        stage=base.select(flags) if inp.get('valuation_legal') is True else None
        out.append({'Date':f['Date'],'C':f['C'],'stage':stage,'rate_pct':base.RATES.get(stage),
          'eligibility':flags,'right':r,'profile':profile,'trade_action':'NO_TRADE'})
    return out
