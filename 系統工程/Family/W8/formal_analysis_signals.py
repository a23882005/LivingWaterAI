"""Map existing native numerics to explicit V82 23/24/25 source contracts.

No reduction Candidate, new period, threshold or trading decision is introduced.
"""
from pathlib import Path
from decimal import Decimal
import hashlib


def verify_rules(source):
    raw=Path(source['local_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source['sha256']:
        raise ValueError('FORMAL_ANALYSIS_RULE_SOURCE_CHANGED')
    text=raw.decode('utf-8-sig')
    for clause in ('MA_RECLAIM_N','HISTOGRAM_CONTRACTING','RSI<30','20日收盤新高'):
        if clause not in text:raise ValueError('FORMAL_ANALYSIS_CLAUSE_MISSING:'+clause)
    return text


def map_formal_observations(rows,current,previous,base_facts,swings,vectors,source):
    verify_rules(source)
    mapped=[]
    def put(group,name,value,section,deps):
        item=next(x for x in vectors[group] if x['name']==name)
        item.update(truth='TRUE' if value else 'FALSE',reason='FORMAL_SOURCE_RULE_MAPPED',
            sot_section=section,dependencies=deps,source_sha256=source['sha256'])
        mapped.append(group+'.'+name)
    a,b=previous.get('macd_histogram'),current.get('macd_histogram')
    macd={}
    if a is not None and b is not None:
        same_side=a*b>0
        macd={'histogram_expanding':same_side and abs(b)>abs(a),
            'histogram_contracting':same_side and abs(b)<abs(a),
            'histogram_crossed_zero':(a<0<b) or (a>0>b)}
        put('right_signals','macd_bear_hist_shrinking_or_positive',
            b>0 or (a<0 and b<0 and abs(b)<abs(a)),
            'V82 §24-B / §14 right confirmation',['Histogram[t]','Histogram[t-1]'])
    if 'reclaim_ma20' in base_facts:
        put('right_signals','above_ma20',base_facts['reclaim_ma20'],
            'V82 §24-C MA_RECLAIM_N / §14 站回MA20',['Close[t-1]','MA20[t-1]','Close[t]','MA20[t]'])
    closes=[r['Close'] for r in rows]
    if len(closes)>=21:
        # Definite outcomes across boundary conventions. A tie or the extra
        # boundary session can remain UNKNOWN; neither convention is invented.
        current_close=closes[-1];high19=max(closes[-20:-1]);high20=max(closes[-21:-1])
        if current_close<high19 or current_close>high20:
            put('up_price','new_20d_close_high',current_close>high20,
                'V82 §43-A existing 20-day close high; non-boundary result',
                ['Close[t]','prior19_max','prior20_max'])
    for side,group,name,comparison in [('highs','up_price','break_confirmed_swing_high',lambda c,v:c>v),
            ('lows','down_break','break_confirmed_swing_low',lambda c,v:c<v)]:
        points=swings.get(side,[])
        if points:
            put(group,name,comparison(closes[-1],points[-1]['value']),
                'V82 §43-A / §44-A confirmed swing close break',
                ['Close[t]','last_confirmed_'+side])
    highs=swings.get('highs',[]);lows=swings.get('lows',[])
    if len(highs)>=2 and len(lows)>=2:
        put('up_price','higher_high_higher_low',
            highs[-1]['value']>highs[-2]['value'] and lows[-1]['value']>lows[-2]['value'],
            'V82 §43-A Higher High + Higher Low',['last_two_confirmed_highs','last_two_confirmed_lows'])
    ma={}
    for period in (5,10,20,50,60,200):
        value=current.get('ma'+str(period))
        if value is not None:
            ma[str(period)]='ABOVE' if closes[-1]>value else 'BELOW' if closes[-1]<value else 'AT'
    rsi=current.get('rsi14');rsi_state=None
    if rsi is not None:
        rsi_state={'value':rsi,'range':'OVERSOLD' if rsi<30 else 'OVERBOUGHT' if rsi>70 else
            'BETWEEN_30_AND_50' if rsi<50 else 'BETWEEN_50_AND_70',
            'direction':('RISING' if rsi>previous['rsi14'] else 'FALLING' if rsi<previous['rsi14'] else 'UNCHANGED')
                if previous.get('rsi14') is not None else 'UNKNOWN',
            'sot_section':'V82 §25-B','not_a_trade_instruction':True}
    return {'schema_version':'Family.W8.FormalAnalysisSignals.v1','mapped_predicates':mapped,
        'macd':macd,'ma_price_relationships':ma,'rsi':rsi_state,
        'ma60_requirement':'OPTIONAL_FOR_NON_TW_ALIGNMENT_PER_24C',
        'volume50_requirement':'CONDITIONAL_PER_25C',
        'rule_source_sha256':source['sha256'],'reduction_candidates_used':False}
