"""Map same-ETF numeric history to Work1 PRED-009's named inputs.

Numeric formulas are reused; V75 owns every threshold and event here. No
V82 voting rule or aggregate is used to construct a V75 technical state.
"""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path


def _and(*values):return False if False in values else None if None in values else True
def _or(*values):return True if True in values else None if None in values else False


def _test(values,fn):
    return None if any(v is None for v in values) else bool(fn(*[Decimal(str(v)) for v in values]))


def from_numeric(rows,history):
    current,previous,prior2,prior3=history;metrics={}
    mapping={'low_td_count':'low_td9_setup','high_td_count':'high_td9_setup',
        'k':'kd_k_9_3','d':'kd_d_9_3_3','rsi14':'rsi14','ma20':'ma20','ma50':'ma50','atr14':'atr14'}
    for field,key in mapping.items():metrics[field]=current.get(key)
    metrics['close']=rows[-1]['Close']
    metrics['rolling_20d_low']=min(r['Low'] for r in rows[-20:]) if len(rows)>=20 else None
    k,d,pk,pd=(current.get('kd_k_9_3'),current.get('kd_d_9_3_3'),previous.get('kd_k_9_3'),previous.get('kd_d_9_3_3'))
    metrics['kd_golden_cross_k_le_35']=_test([k,d,pk,pd],lambda k,d,pk,pd:pk<=pd and k>d and k<=35)
    metrics['kd_death_cross_k_ge_80']=_test([k,d,pk,pd],lambda k,d,pk,pd:pk>=pd and k<d and k>=80)
    hist=[h.get('macd_histogram') for h in history[:3]]
    metrics['macd_hist_improving_3d']=_test(hist,lambda a,b,c:a>b>c)
    # V75 base rule §31 specifies the bullish/positive MACD column.
    metrics['macd_hist_shrinking_3d']=_test(hist,lambda a,b,c:0<a<b<c)
    dif=[current.get('macd_12_26'),prior2.get('macd_12_26')]
    golden=[current.get('macd_12_26'),current.get('macd_signal_9'),
        previous.get('macd_12_26'),previous.get('macd_signal_9')]
    metrics['dif_slope_positive_or_macd_golden_cross']=_or(
        _test(dif,lambda a,c:a>c),_test(golden,lambda a,b,c,d:c<=d and a>b))
    reclaims=[]
    for offset in range(3):
        if len(rows)<offset+2:reclaims.append(None);continue
        reclaims.append(_test([rows[-1-offset]['Close'],history[offset].get('ma20'),
            rows[-2-offset]['Close'],history[offset+1].get('ma20')],lambda c,ma,p,pma:p<=pma and c>ma))
    metrics['reclaimed_ma20_last3d']=_or(*reclaims)
    metrics['higher_5d_low']=(min(r['Low'] for r in rows[-5:])>min(r['Low'] for r in rows[-10:-5])) if len(rows)>=10 else None
    metrics['rsi14_ge_70']=_test([current.get('rsi14')],lambda r:r>=70)
    ma20=sum(Decimal(str(r['Volume'])) for r in rows[-20:])/20 if len(rows)>=20 else None
    ma5=sum(Decimal(str(r['Volume'])) for r in rows[-5:])/5 if len(rows)>=5 else None
    up=_test([rows[-1]['Close'],rows[-2]['Close']],lambda a,b:a>b) if len(rows)>=2 else None
    quiet=_test([rows[-1]['Volume'],ma5,ma20],lambda daily,avg5,avg20:daily<avg20 or avg5<avg20) if ma20 is not None and ma20>0 else None
    metrics['price_up_volume_below_ma20']=_and(up,quiet)
    return metrics


def produce(rows,parameters):
    from formal_v75_parameters import VERSION,PARAMETER_SHA256,BASE_RULE_SHA256
    if parameters.get('parameter_version')!=VERSION or parameters.get('parameter_sha256')!=PARAMETER_SHA256:
        raise PermissionError('V75_TECHNICAL_PARAMETER_BINDING')
    import pandas as pd
    from technical_source_bridge import _originals
    _,numeric=_originals();frame=pd.DataFrame(rows)
    history=[numeric.technical(frame.iloc[:len(frame)-offset]) if len(frame)>offset else {} for offset in range(4)]
    metrics=from_numeric(rows,history)
    base_bound=parameters.get('base_rule_source',{}).get('source_sha256')==BASE_RULE_SHA256
    if not base_bound:metrics['macd_hist_shrinking_3d']=None
    missing=[k for k,v in metrics.items() if v is None]
    return {'metrics':metrics,'unprovided_inputs':missing,'complete_named_inputs':not missing,
        'parameter_version':VERSION,'parameter_sha256':PARAMETER_SHA256,
        'base_rule_source':parameters.get('base_rule_source'),
        'numeric_source_sha256':sha256(Path(numeric.__file__).read_bytes()).hexdigest(),
        'basis':'ORIGINAL_PRED_009_AND_V75_BASE_RULE_31__SAME_ETF_DAILY_HISTORY',
        'technical_threshold_owner':'V75_WORK1__NO_V82_RULE_SUBSTITUTION',
        'dif_3day_slope_basis':'THREE_EQUALLY_SPACED_OBSERVATIONS__SIGN_OF_CURRENT_MINUS_PRIOR2',
        'trim_histogram_basis':'THREE_POSITIVE_HISTOGRAM_COLUMNS_STRICTLY_SHRINKING' if base_bound else 'BASE_RULE_31_SOURCE_REQUIRED',
        'volume_divergence_basis':'PRICE_UP_AND_EITHER_DAILY_OR_5D_AVERAGE_VOLUME_BELOW_MA20',
        'observed_date':rows[-1]['Date'],'numeric_observation_dates':[rows[-1-i]['Date'] for i in range(min(4,len(rows)))]}
