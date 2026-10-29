"""Owner-approved v1.0 technical SOURCE producer for the existing V82 Core.

No deployment, budget, news, company thesis or trading algorithm lives here.
All 32 slots stay visible, with their exact version and source dependencies.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal,InvalidOperation,localcontext,ROUND_HALF_EVEN
from pathlib import Path
from types import SimpleNamespace
import hashlib,json
from technical_source_bridge import NAMES,_originals
import approved_v04_numeric as n
D=Decimal
U='UNKNOWN';T='TRUE';F='FALSE'


def load_profile(path):
    path=Path(path);raw=path.read_bytes();p=json.loads(raw)
    if (p.get('schema_version')!='Family.W8.OwnerApprovedRules.v1' or
        p.get('approval_status')!='APPROVED_FOR_IMPLEMENTATION' or not p.get('spec_approved') or p.get('spec_version')!='1.0' or
        p.get('spec_sha256')!='29bf4491d77c390f6014208932e6a45f9d27cad25747e8c183be2502c95f5fea'):
        raise ValueError('V10_OWNER_APPROVAL_OR_VERSION_MISMATCH')
    config=path.parent/'v82_formal_implementation_v10.json'
    if hashlib.sha256(config.read_bytes()).hexdigest()!=p['formal_config_sha256']:
        raise ValueError('V10_FORMAL_CONFIG_CHANGED')
    if hashlib.sha256(Path(n.__file__).read_bytes()).hexdigest()!=p['numeric_producer_sha256']:
        raise ValueError('V10_NUMERIC_PRODUCER_CHANGED')
    return {**p,'approval_receipt_sha256':hashlib.sha256(raw).hexdigest()}


def truth(x):return U if x is None else T if x else F

def both(*xs):
    if False in xs:return False
    return None if None in xs else True

def either(*xs):
    if True in xs:return True
    return None if None in xs else False

def cmp(a,b,op):
    if a is None or b is None:return None
    return {'gt':lambda:a>b,'ge':lambda:a>=b,'lt':lambda:a<b,'le':lambda:a<=b,'eq':lambda:a==b}[op]()

def val(value):
    if isinstance(value,bool):return None
    try:r=D(str(value));return r if r.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None


def produce(rows,*,profile,is_etf=None,close_only=False):
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        result=_produce(rows,profile=profile,is_etf=is_etf,close_only=close_only)
        if len(rows)>1:
            # Recompute the prior snapshot from its own prefix, so a Swing
            # confirmed today cannot leak into yesterday's Up evidence.
            previous=_produce(rows[:-1],profile=profile,is_etf=is_etf,close_only=close_only)
            result['trend_timing_inputs']['previous_technical']={
                k:[r['truth'] for r in previous['signals'][k]] for k in ('up_price','up_confirm')}
            result['trend_timing_inputs']['previous_technical']['ma20_ok']=previous['ma20_ok']
        return result


def _produce(rows,*,profile,is_etf,close_only):
    if profile.get('approval_status')!='APPROVED_FOR_IMPLEMENTATION':raise ValueError('V10_APPROVAL_REQUIRED')
    count=len(rows);t=count-1
    if not rows:raise ValueError('V10_EMPTY_HISTORY')
    def series(key):
        return [None if close_only and key in ('Open','High','Low','Volume') else
            val(r.get('_source_decimal',{}).get(key,r.get(key))) for r in rows]
    c,h,l,v,o=[series(k) for k in ('Close','High','Low','Volume','Open')]
    def at(xs,i=None):
        i=t if i is None else i
        return xs[i] if 0<=i<len(xs) else None
    rsv,k,d=n.kd(h,l,c);_,_,dif,dea,hist=n.macd(c)
    _,_,rsi=n.rsi(c);_,atr=n.atr(h,l,c);_,_,emv=n.emv(h,l,v)
    ma={period:n.sma(c,period) for period in (5,10,20,50,60,200)}
    vma=n.sma(v,20)
    q=[None if i==0 or at(vma,i-1) in (None,D(0)) or at(v,i) is None else v[i]/vma[i-1] for i in range(count)]
    ret=[None if i==0 or at(c,i-1) in (None,D(0)) or c[i] is None else c[i]/c[i-1]-1 for i in range(count)]
    vectors={g:[{'name':name,'truth':U,'reason':'REQUIRED_DEPENDENCY_UNRESOLVED',
        'rule_profile':profile['profile_id'],'spec_sha256':profile['spec_sha256'],
        'approval_receipt_sha256':profile['approval_receipt_sha256'],
        'evaluated_session':rows[-1]['Date']} for name in names] for g,names in NAMES.items()}
    def put(group,name,result,deps,section):
        slot=next(x for x in vectors[group] if x['name']==name)
        slot.update(truth=truth(result),reason='APPROVED_V10_COMPUTED' if result is not None else
            'MISSING_REQUIRED_INPUT_OR_REFERENCE',dependencies=deps,rule_ref='v1.0 '+section)
    def chain(xs,indices,op='gt'):
        return both(*(cmp(at(xs,a),at(xs,b),op) for a,b in zip(indices,indices[1:])))
    legacy,_=_originals();pivots={'highs':[],'lows':[]}
    for side,xs,fn in [('highs',h,'confirmed_swing_highs'),('lows',l,'confirmed_swing_lows')]:
        # Never replace missing High/Low with another price. A missing entire
        # field affects only dependent primitives, retaining Close observations.
        if all(x is not None for x in xs):
            pivots[side]=[SimpleNamespace(index=p.index,value=xs[p.index]) for p in legacy[fn](xs)]
    def latest(side,s,w=20):
        candidates=[p for p in pivots[side] if p.index+2<=s and s-w<=p.index<=s]
        return candidates[-1] if candidates else None
    def crossing(side,i,significant=False):
        pivot=latest(side,i-1)
        if pivot is None:return None,None
        level=pivot.value*(D('.99') if significant else D(1))
        result=both(cmp(at(c,i-1),level,'le' if side=='highs' else 'ge'),
                    cmp(at(c,i),level,'gt' if side=='highs' else 'lt'))
        return result,pivot
    def normalized(w):
        ps=sorted([(p.index,'H',p.value) for p in pivots['highs'] if t-w<=p.index<=t-2]+
                  [(p.index,'L',p.value) for p in pivots['lows'] if t-w<=p.index<=t-2])
        if len({x[0] for x in ps})!=len(ps):return None
        out=[]
        for p in ps:
            if out and p[1]==out[-1][1]:
                if (p[1]=='H' and p[2]>=out[-1][2]) or (p[1]=='L' and p[2]<=out[-1][2]):out[-1]=p
            else:out.append(p)
        return out
    raw_lows=pivots['lows']
    higher_low=None
    if len(raw_lows)>=2:
        a,b=raw_lows[-2:]
        if t-a.index<=60 and t-b.index<=20:higher_low=b.value>a.value
    put('right_signals','higher_low',higher_low,['confirmed Low[-2:]','60/20-session validity'],'R1')
    put('right_signals','kd_golden_cross',n.cross(k,d),['KD SMA3/SMA3 current/prior'],'R2')
    shrink=both(cmp(at(hist),D(0),'lt'),cmp(at(hist,t-1),D(0),'lt'),
        cmp(abs(at(hist)) if at(hist) is not None else None,abs(at(hist,t-1)) if at(hist,t-1) is not None else None,'lt'))
    flip=both(cmp(at(hist,t-1),D(0),'le'),cmp(at(hist),D(0),'gt'))
    put('right_signals','macd_bear_hist_shrinking_or_positive',either(shrink,flip),['Hist[t-1:t]'],'R3')
    put('right_signals','dif_up',cmp(at(dif),at(dif,t-1),'gt'),['DIF[t-1:t]'],'R4')
    put('right_signals','emv_positive',both(cmp(at(emv,t-1),D(0),'le'),cmp(at(emv),D(0),'gt')),
        ['EMV_ARMS_SMA3_SMA3_SCALE1E8[t-1:t]'],'R5 turns-positive alias')
    near=both(cmp(at(rsi),D(45),'ge'),cmp(at(rsi),D(55),'le'))
    rise=both(cmp(at(rsi,t-3),D(30),'ge'),cmp(at(rsi),D(50),'le'),chain(rsi,[t,t-1,t-2,t-3]))
    put('right_signals','rsi_improving_or_near_50',either(near,rise),['RSI[t-3:t]','45/55'],'R6')
    reclaim=both(cmp(at(c,t-1),at(ma[20],t-1),'le'),cmp(at(c),at(ma[20]),'gt'))
    put('right_signals','above_ma20',reclaim,['Close/MA20[t-1:t]'],'R7 reclaim alias')
    line_result=None
    highs=[p for p in pivots['highs'] if p.index+2<=t-1]
    if len(highs)>=2:
        a,b=highs[-2:]
        if t-1-a.index<=60 and b.index-a.index>=5 and b.value<a.value:
            def line(i):return a.value+(b.value-a.value)*D(i-a.index)/D(b.index-a.index)
            untouched=both(*(cmp(at(c,i),line(i),'le') for i in range(b.index+2,t)))
            line_result=both(untouched,cmp(at(c,t-1),line(t-1),'le'),cmp(at(c),line(t),'gt'),cmp(at(q),D('1.5'),'ge'))
    put('right_signals','volume_breakout',line_result,['confirmed descending High pair','exclusive q20','60/5/1.5'],'R8')
    breakout,point=crossing('highs',t)
    put('right_signals','pressure_breakout',breakout,['latestHighAt(t-1,20)','Close cross'],'R9')
    episode_trace=[]
    def episode_vote(kind,window):
        results=[]
        if t<window+24:return None
        for b in range(t-window,t if kind!='NO_QUICK_RECLAIM' else t+1):
            parent,pivot=crossing('lows' if kind=='NO_QUICK_RECLAIM' else 'highs',b,kind=='NO_QUICK_RECLAIM')
            if parent is None:results.append(None);continue
            if not parent:continue
            P=pivot.value;state='PENDING';vote=None;touch=None
            for i in range(b if kind=='NO_QUICK_RECLAIM' else b+1,t+1):
                if at(c,i) is None:state='INVALIDATED_DATA';vote=None;break
                if kind=='NO_QUICK_RECLAIM':
                    if c[i]>=P:state='RECLAIMED';vote=False;break
                    if i==b+3:state='NO_RECLAIM_EVENT';vote=i==t;break
                elif kind=='FAILED_BREAKOUT':
                    if c[i]<D('.995')*P:state='FAILED_BREAKOUT_EVENT';vote=i==t;break
                    vote=False
                    if i==b+5:state='EXPIRED_NO_FAILURE';break
                else:
                    if any(x is None for x in (at(l,i),at(h,i))):state='INVALIDATED_DATA';vote=None;break
                    if c[i]<D('.99')*P:state='FAILED';vote=False;break
                    if touch is None and l[i]<=D('1.005')*P and h[i]>=D('.995')*P:touch=i
                    if touch is not None and i<=min(touch+2,b+10) and both(cmp(c[i],P,'ge'),cmp(c[i],at(c,i-1),'gt')):
                        state='SUCCESS_EVENT';vote=i==t;break
                    if i==b+10 or (touch is not None and i==touch+2):state='EXPIRED';vote=False;break
            episode_trace.append({'kind':kind,'parent_session':rows[b]['Date'],'reference_pivot':rows[pivot.index]['Date'],
                'immutable_level':str(P),'state':state,'truth':truth(vote)})
            results.append(vote)
        return either(*results)
    put('right_signals','breakout_retest_success',episode_vote('RETEST',10),['R9 parent','immutable P','10/2-session expiry'],'R10')
    newhigh=cmp(at(c),max(c[-21:-1]) if len(c)>=21 and None not in c[-21:] else None,'gt')
    put('up_price','new_20d_close_high',newhigh,['Close[t]','prior20 strict maximum'],'U1')
    put('up_price','break_confirmed_swing_high',breakout,['latestHighAt(t-1,20)','Close cross'],'U2')
    ps=normalized(60);hhl=None
    if ps is not None and len(ps)>=4 and t-ps[-1][0]<=20:
        tail=ps[-4:];hs=[p[2] for p in tail if p[1]=='H'];ls=[p[2] for p in tail if p[1]=='L']
        if len(hs)==len(ls)==2:hhl=hs[-1]>D('1.01')*hs[0] and ls[-1]>D('1.01')*ls[0]
    put('up_price','higher_high_higher_low',hhl,['four normalized confirmed pivots','60/20/1.01'],'U3')
    if ps is None:
        next(s for s in vectors['up_price'] if s['name']=='higher_high_higher_low')['reason']='AMBIGUOUS_INTRABAR_PIVOT_ORDER'
    high_kd=both(*(both(cmp(at(k,i),D(80),'gt'),cmp(at(d,i),D(80),'gt')) for i in range(t-2,t+1)),
        cmp(at(k),at(d),'ge'),cmp(at(k)-at(k,t-1) if None not in (at(k),at(k,t-1)) else None,D(-10),'ge'),
        cmp(at(d)-at(d,t-1) if None not in (at(d),at(d,t-1)) else None,D(-10),'ge'))
    put('up_confirm','kd_high_strong_not_breaking',high_kd,['KD last3','80/-10'],'C1')
    put('up_confirm','macd_bull_hist_expanding',both(cmp(at(hist),D(0),'gt'),cmp(at(hist,t-1),D(0),'gt'),cmp(at(hist),at(hist,t-1),'gt')),['Hist[t-1:t]'],'C2')
    put('up_confirm','ma5_gt_ma10_gt_ma20',both(cmp(at(ma[5]),at(ma[10]),'gt'),cmp(at(ma[10]),at(ma[20]),'gt')),['MA5/10/20'],'C3')
    put('up_confirm','emv_positive_or_improving',either(cmp(at(emv),D(0),'gt'),cmp(at(emv),at(emv,t-1),'gt')),['EMV3x3[t-1:t]'],'C4')
    health=None
    if t>=5 and all(at(ret,i) is not None for i in range(t-4,t+1)):
        ups=[i for i in range(t-4,t+1) if ret[i]>0];downs=[i for i in range(t-4,t+1) if ret[i]<0]
        enough_ups=len(ups)>=2
        balance=(sum((v[i] for i in ups),D(0))>=D('1.2')*sum((v[i] for i in downs),D(0))) if all(at(v,i) is not None for i in ups+downs) else None
        shocks=[both(cmp(ret[i],D('-.01'),'le'),cmp(q[i],D('1.5'),'ge')) for i in range(t-4,t+1)]
        shock=either(*shocks)
        health=both(enough_ups,balance,None if shock is None else not shock)
    put('up_confirm','price_volume_healthy',health,['last5 returns/volume','exclusive q20','2/1.2/-.01/1.5'],'C5')
    post=None
    if len(c)>=23 and None not in c[-23:]:
        firsts=[i for i in range(t-9,t+1) if n.td_first9(c[:i+1]) is True]
        if n.td_first9(c,1) is True or n.td_first9(c) is True:post=False
        elif not firsts:post=False
        else:
            e=firsts[-1]
            if any(n.td_first9(c[:i+1],1) is True for i in range(e+1,t+1)):post=False
            elif None not in h[e-8:e+1]:
                P=max(h[e-8:e+1]);success=next((i for i in range(e+1,t+1) if c[i]>P),None);post=success==t
    put('up_confirm','high_td9_then_new_high',post,['first-high9','post9-session window','setup High maximum'],'C6')
    pair=None
    hs=pivots['highs']
    if len(hs)>=2:
        a,b=hs[-2:]
        if t-a.index<=60 and t-b.index<=20 and b.index-a.index>=5 and b.value>a.value:
            pair=cmp(at(rsi,b.index),at(rsi,a.index),'gt')
    put('up_confirm','rsi_high_no_divergence',both(cmp(at(rsi),D(70),'gt'),pair),['RSI[t]','comparable confirmed high-pair RSI'],'C7')
    if is_etf is True:
        slot=next(x for x in vectors['up_confirm'] if x['name']=='eps_guidance_not_worse')
        slot.update(truth='NOT_APPLICABLE',effective_vote=F,applicability='ETF_NOT_ISSUER',
            reason='OWNER_APPROVED_V10_NONVOTING_SLOT__THRESHOLD_UNCHANGED',rule_ref='v1.0 TECH7')
    else:
        put('up_confirm','eps_guidance_not_worse',None,['same issuer/period/basis official guidance versions'],'C8')
    lows3=[]
    for i in range(t-2,t+1):
        lows3.append(cmp(at(c,i),min(c[i-20:i]) if i>=20 and None not in c[i-20:i] else None,'lt'))
    put('down_break','keeps_breaking_lows',both(*lows3),['three strict prior20 Close lows'],'D1')
    down,_=crossing('lows',t)
    put('down_break','break_confirmed_swing_low',down,['latestLowAt(t-1,20)','Close cross'],'D2')
    put('down_break','break_support_no_quick_reclaim',episode_vote('NO_QUICK_RECLAIM',3),['immutable support','1% break','3-session pending'],'D3')
    put('down_accel','macd_bear_hist_expanding',both(cmp(at(hist),D(0),'lt'),cmp(at(hist,t-1),D(0),'lt'),cmp(at(hist),at(hist,t-1),'lt')),['Hist[t-1:t]'],'A1')
    weak=both(*(both(cmp(at(k,i),D(20),'lt'),cmp(at(d,i),D(20),'lt')) for i in range(t-2,t+1)),
        chain(k,[t,t-1,t-2],'le'),chain(d,[t,t-1,t-2],'le'),cmp(at(k),at(d),'le'),
        either(cmp(at(k),at(k,t-2),'lt'),cmp(at(d),at(d,t-2),'lt')))
    put('down_accel','kd_low_weak',weak,['KD last3','20/strict total decline'],'A2')
    put('down_accel','emv_worsening',chain(emv,[t,t-1,t-2,t-3],'lt'),['EMV3x3 last4'],'A3')
    put('down_accel','rsi_falling',chain(rsi,[t,t-1,t-2,t-3],'lt'),['RSI last4'],'A4')
    put('down_accel','price_down_volume_up',both(cmp(at(c),at(c,t-1),'lt'),cmp(at(v),at(vma),'gt')),['Close[t-1:t]','Volume/inclusive20'],'A5')
    ratio=at(atr)/at(atr,t-5) if at(atr) is not None and at(atr,t-5) is not None and at(atr,t-5)>0 else None
    put('down_accel','atr_expanding_fast',both(cmp(ratio,D('1.20'),'ge'),cmp(at(atr),at(atr,t-1),'gt')),['ATR[t-5:t]','1.20'],'A6')
    old=at(c,t-5)/at(c,t-10)-1 if at(c,t-5) is not None and at(c,t-10) not in (None,D(0)) else None
    new=at(c)/at(c,t-5)-1 if at(c) is not None and at(c,t-5) not in (None,D(0)) else None
    accel=both(cmp(old,D(0),'lt'),cmp(new,D(0),'lt'),cmp(new,old-D('.02') if old is not None else None,'le'))
    put('down_accel','decline_accelerating',accel,['nonoverlapping 5+5-session Close returns','.02'],'A7')
    ps=normalized(90);weaker=None
    if ps is not None:
        if ps and ps[-1][1]=='L':ps=ps[:-1]
        tail=ps[-6:]
        if len(tail)==6 and [p[1] for p in tail]==['L','H']*3 and t-tail[-1][0]<=20:
            amps=[tail[i+1][2]/tail[i][2]-1 for i in (0,2,4)]
            if all(a>0 for a in amps):weaker=amps[2]<amps[1]<amps[0] and amps[2]<=D('.8')*amps[0]
    put('down_accel','rebounds_weaker',weaker,['three normalized completed Low->High legs','90/20/.8'],'A8')
    if ps is None:
        next(s for s in vectors['down_accel'] if s['name']=='rebounds_weaker')['reason']='AMBIGUOUS_INTRABAR_PIVOT_ORDER'
    ma20_ok=cmp(at(c),D('.99')*at(ma[20]) if at(ma[20]) is not None and at(ma[20])>0 else None,'ge')
    latest_low=latest('lows',t)
    off_low=cmp(at(c),D('1.01')*latest_low.value if latest_low else None,'ge')
    numeric={'kd_k':at(k),'kd_d':at(d),'emv_3_3':at(emv),'macd_dif':at(dif),'macd_dea':at(dea),
        'macd_histogram':at(hist),'rsi14':at(rsi),'atr14':at(atr),'ma20':at(ma[20])}
    td=n.td_count(c)
    breakdown=lambda period:both(cmp(at(c,t-1),at(ma[period],t-1),'ge'),cmp(at(c),at(ma[period]),'lt'))
    death=n.cross(d,k)
    contracting=both(chain(hist,[t-3,t-2,t-1,t]),cmp(at(hist),D(0),'gt'))
    # A known non-divergent comparable pair is FALSE for S5; no comparable
    # pair remains UNKNOWN, including the equality (divergent) boundary.
    divergence=None if pair is None else not pair
    high20=max(c[-21:-1]) if len(c)>=21 and None not in c[-21:-1] else None
    no_gain=both(cmp(at(q),D(2),'ge'),cmp(abs(at(ret)) if at(ret) is not None else None,D('.005'),'le'),
        cmp(at(c),D('.95')*high20 if high20 is not None else None,'ge'))
    extreme_weak=both(None,cmp(at(c),at(ma[50]),'lt'),cmp(at(ma[50]),at(ma[50],t-5),'lt'))
    reduction_values=[None if td is None else td[0] in (8,9),death,contracting,
        cmp(at(emv),at(emv,t-1),'lt'),divergence,no_gain,either(breakdown(10),breakdown(20)),
        episode_vote('FAILED_BREAKOUT',5),extreme_weak]
    turn=both(cmp(at(k,t-2),at(k,t-1),'ge'),cmp(at(d,t-2),at(d,t-1),'ge'),
        cmp(at(k),at(k,t-1),'gt'),cmp(at(d),at(d,t-1),'ge'))
    price_not_lower=both(chain(l,[t-2,t-1,t],'le'),cmp(at(c),at(c,t-2),'ge'))
    shrunk=both(cmp(at(c),at(c,t-1),'lt'),cmp(at(v),at(vma),'lt'))
    candle_range=at(h)-at(l) if None not in (at(h),at(l)) else None
    close_position=(at(c)-at(l))/candle_range if at(c) is not None and candle_range is not None and candle_range>0 else None
    prev5low=min(l[-6:-1]) if len(l)>=6 and None not in l[-6:-1] else None
    stop_candle=both(cmp(candle_range,D(0),'gt'),cmp(at(c),at(o),'ge'),
        cmp(close_position,D('.75'),'ge'),cmp(at(l),prev5low,'lt'))
    mature_values=[None if td is None else td[1] in (5,6,7,8,9),either(n.cross(k,d),turn),
        both(cmp(at(hist,t-1),at(hist),'lt'),cmp(at(hist),D(0),'lt')),
        cmp(at(dif),at(dif,t-1),'gt'),cmp(at(emv),at(emv,t-1),'gt'),cmp(at(rsi),at(rsi,t-1),'gt'),
        price_not_lower,either(shrunk,stop_candle)]
    reduction=[{'id':'S'+str(i),'truth':truth(value),'rule_ref':'V82 v1.0 TECH5.1',
        'reason':'FORMAL_EXTREME_VALUATION_REQUIRED' if i==9 and value is None else
        'REQUIRED_SOURCE_OR_REFERENCE_UNAVAILABLE' if value is None else 'COMPUTED'} for i,value in enumerate(reduction_values,1)]
    maturity=[{'id':'M'+str(i),'truth':truth(value),'rule_ref':'V82 v1.0 TECH5.2'} for i,value in enumerate(mature_values,1)]
    scores=[D(0),D('.5'),D('.8'),D(1),D('1.5'),D('1.8'),D(2),D('2.5'),D(3),D(4)]
    return {'schema_version':'Family.W8.ApprovedV10Technical.v1','profile_id':profile['profile_id'],
        'spec_sha256':profile['spec_sha256'],'approval_status':'APPROVED_FOR_IMPLEMENTATION','spec_version':'1.0','source_commit':profile['source_commit'],
        'approval_receipt_sha256':profile['approval_receipt_sha256'],'signals':vectors,
        'ma20_ok':truth(ma20_ok),'off_low':truth(off_low),
        'numeric_decimal':{key:str(value) if value is not None else None for key,value in numeric.items()},
        'technical_reduction_signals':reduction,'left_maturity_signals':maturity,
        'trend_timing_inputs':{'bars':[{key:str(series_[i]) if series_[i] is not None else None
            for key,series_ in (('Open',o),('High',h),('Low',l),('Close',c))}
            for i in range(max(0,count-5),count)],
            'ma5':str(at(ma[5])) if at(ma[5]) is not None else None,
            'ma10':str(at(ma[10])) if at(ma[10]) is not None else None,
            'ma20':str(at(ma[20])) if at(ma[20]) is not None else None,
            'previous_atr14':str(at(atr,t-1)) if at(atr,t-1) is not None else None,
            'previous_close':str(at(c,t-1)) if at(c,t-1) is not None else None,
            'breakout_retest_success':next(x['truth'] for x in vectors['right_signals'] if x['name']=='breakout_retest_success')},
        'low_td9_score_times4':str(scores[td[1]]*4) if td else None,
        'technical_reduction_scope':'CONDITIONS_ONLY__CLASSIFICATION_AND_SELL_PERMISSION_REMAIN_WITH_ORIGINAL_OWNER',
        'episode_trace':episode_trace,'timeframes':timeframes(rows,c),
        'call_trace':['OWNER_APPROVED_V04.reference_numeric','ORIGINAL.confirmed_swing_lows/highs','OWNER_APPROVED_V04.32_slot_source_producer'],
        'price_source_attestation':'SEPARATELY_REQUIRED__NOT_INFERRED_BY_RULE_APPROVAL',
        'canonical_fields_modified':False,'deployment_status':'NOT_RUN'}


def trend(closes):
    _,_,dif,dea,_=n.macd(closes);ma=n.sma(closes,20)
    if len(closes)<2:return {'state':U,'reason':'COMPLETED_PERIOD_SAMPLE_INSUFFICIENT'}
    bull=both(cmp(closes[-1],ma[-1],'gt'),cmp(ma[-1],ma[-2],'gt'),cmp(dif[-1],dea[-1],'gt'))
    bear=both(cmp(closes[-1],ma[-1],'lt'),cmp(ma[-1],ma[-2],'lt'),cmp(dif[-1],dea[-1],'lt'))
    state='BULLISH' if bull is True else 'BEARISH' if bear is True else 'MIXED_KNOWN' if bull is False and bear is False else U
    return {'state':state,'method_id':'TREND_C_MA20_SLOPE_MACD_V1','completed_periods':len(closes),
        'source_session_attestation':'SEPARATELY_REQUIRED'}


def timeframes(rows,closes):
    result={'daily':trend(closes)}
    for label in ('weekly','monthly'):
        groups=[]
        for row,value in zip(rows,closes):
            day=date.fromisoformat(row['Date'])
            key=tuple(day.isocalendar()[:2]) if label=='weekly' else (day.year,day.month)
            if not groups or groups[-1][0]!=key:groups.append([key,value])
            else:groups[-1][1]=value
        # Only periods whose successor is already observed are included.
        # No invented holiday calendar or claim of complete session coverage.
        completed=[g[1] for g in groups[:-1]]
        result[label]={**trend(completed),'aggregation':'LAST_OBSERVED_CLOSE_OF_PERIOD_WITH_OBSERVED_SUCCESSOR',
            'latest_period_excluded':list(groups[-1][0]) if groups else None,
            'calendar_coverage_verified':False,'status':'NUMERIC_OBSERVATION__SESSION_COVERAGE_UNVERIFIED'}
    return result
