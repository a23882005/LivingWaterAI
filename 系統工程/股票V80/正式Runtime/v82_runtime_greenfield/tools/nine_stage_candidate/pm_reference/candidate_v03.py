"""Review profile: early right uses independent R, never M maturity.
Reuse tested v0.2 RETEST_OR_MA20 lifecycle/confirmation. Production unchanged.
"""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from . import candidate as base
from . import candidate_v02 as comparison
from . import independent_right
VERSION='NINE_STAGE_INDEPENDENT_R_OR_0.3.0_REVIEW'

def right_episodes(fs):
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        results=_right_with_r(fs,'RETEST_OR_MA20')
    for f,r in zip(fs,results):r.update(entry_confirmation_source='R_OK_NOT_M_OK',R_ok=f['R_ok'])
    return results

def _right_with_r(fs,profile):
    active=None;out=[]
    for t,f in enumerate(fs):
        p=fs[t-1] if t else None
        event=base.AND(base.compare(p['C'] if p else None,'<=',f['P5']),
          base.compare(f['C'],'>',f['P5']),base.compare(f['C'],'>=',
          f['L5']*D('1.01') if f['L5'] is not None else None),f['R_ok'])
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

def replay(rows,inputs):
    if len(rows)!=len(inputs):raise ValueError('INPUT_LENGTH_MISMATCH')
    fs=independent_right.produce(rows);rs=right_episodes(fs);out=[]
    for i,(f,r,inp) in enumerate(zip(fs,rs,inputs)):
        for name in ('qp','qv'):
            if inp.get(name) is not None and not 0<=D(str(inp[name]))<=100:raise ValueError('PERCENTILE_OUT_OF_RANGE')
        flags=base.eligibility(f,fs[i-1] if i else None,r,**{k:inp.get(k) for k in
          ('depth','qp','qv','a_normal','valuation_legal','up')})
        up=inp.get('up');right=base.OR(r['early_right1'],r['early_right2'])
        left=base.OR(*(flags[s] for s in range(2,8)))
        mode=('TREND' if up is True else None if up is None else
              'RIGHT' if right is True else None if right is None else
              'LEFT' if left is True else None if left is None else 'BASE')
        stage=base.select(flags) if (inp.get('valuation_legal') is True and
            inp.get('fundamental') is True and mode is not None) else None
        out.append({'Date':f['Date'],'C':f['C'],'stage':stage,'rate_pct':base.RATES.get(stage),
          'eligibility':flags,'right':r,'M':f['M'],'M_ok':f['M_ok'],'R':f['R'],
          'R_ok':f['R_ok'],'R_count':f['R_count'],'R_unknown':f['R_unknown'],
          'normal_mode':mode,'profile':VERSION,'trade_action':'NO_TRADE'})
    return out
