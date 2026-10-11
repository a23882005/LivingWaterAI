"""Deterministic PRED-001..010 evaluators for V75_PREDICATE_PARAMS_v1.0.3.
Inputs are explicit normalized raw metrics; adapters own source retrieval/unit conversion.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any
from .constants import PREDICATE_VERSION, PREDICATE_STATE_PRECEDENCE
from .enums import FreshnessState, PredicateAssessmentStatus
from .models import PredicateResult

D=lambda x: Decimal(str(x))

def _result(pid, states, *, as_of, lineage, reasons=()):
    precedence=PREDICATE_STATE_PRECEDENCE[pid]
    ordered=[s for s in precedence if s in states]
    return PredicateResult(predicate_id=pid,predicate_version=PREDICATE_VERSION,aggregate_state=ordered[0],sub_states=ordered,
        assessment_status=PredicateAssessmentStatus.VALID,as_of=as_of,source_lineage=lineage,input_freshness_state=FreshnessState.FRESH,reason_codes=list(reasons),required_input_missing=[])

def _missing(pid, fields, *, as_of, lineage, status=PredicateAssessmentStatus.INSUFFICIENT_DATA, reason="MISSING_REQUIRED_INPUT"):
    return PredicateResult(predicate_id=pid,predicate_version=PREDICATE_VERSION,aggregate_state=None,sub_states=[],assessment_status=status,
        as_of=as_of,source_lineage=lineage,input_freshness_state=FreshnessState.FRESH,reason_codes=[reason],required_input_missing=list(fields))

def pred001(x:dict, as_of:datetime, lineage:list[str]):
    vals=[]
    if x.get('effr_10y_percentile_pct') is not None: vals.append(('pct',D(x['effr_10y_percentile_pct'])))
    if x.get('effr_pct') is not None and x.get('sep_long_run_median_pct') is not None: vals.append(('neutral',D(x['effr_pct'])-D(x['sep_long_run_median_pct'])))
    if x.get('effr_pct') is not None and x.get('core_pce_yoy_pct') is not None: vals.append(('real',D(x['effr_pct'])-D(x['core_pce_yoy_pct'])))
    if len(vals)<2: return _missing('PRED-001',['at least 2 comparable dimensions'],as_of=as_of,lineage=lineage)
    def count(kind):
        f={'EXTREME':lambda k,v:(k=='pct' and v>=90)or(k!='pct' and v>=2), 'HIGH':lambda k,v:(k=='pct' and v>=75)or(k!='pct' and v>=1), 'LOW':lambda k,v:(k=='pct' and v<=25)or(k=='neutral' and v<=D('-.5'))or(k=='real' and v<=0)}[kind]
        return sum(f(k,v) for k,v in vals)
    states=[]
    if count('EXTREME')>=2: states.append('EXTREME')
    if count('HIGH')>=2: states.append('HIGH')
    if count('LOW')>=2: states.append('LOW')
    if not states:
        if len(vals)==2: return _missing('PRED-001',['third dimension or concordant non-neutral state'],as_of=as_of,lineage=lineage)
        states=['NEUTRAL']
    return _result('PRED-001',states,as_of=as_of,lineage=lineage)

def pred002(x,as_of,lineage):
    rate=[D(v) for k,v in x.items() if k in {'next_fomc_expected_rate_delta_5bd_bps','second_next_fomc_expected_rate_delta_5bd_bps','expected_policy_rate_6m_delta_5bd_bps'} and v is not None]
    prob=[D(v) for k,v in x.items() if k in {'next_fomc_higher_rate_probability_delta_5bd_pp','second_next_fomc_higher_rate_probability_delta_5bd_pp'} and v is not None]
    if not rate and not prob:return _missing('PRED-002',['comparable meeting or 6m horizon delta'],as_of=as_of,lineage=lineage)
    states=[]
    if any(v>=50 for v in rate) or any(v>=40 for v in prob):states.append('EXTREME_HAWKISH_REPRICING')
    if any(v>=25 for v in rate) or any(v>=25 for v in prob):states.append('LARGE_HAWKISH_REPRICING')
    if not states:states=['NO_HAWKISH_REPRICING']
    return _result('PRED-002',states,as_of=as_of,lineage=lineage)

def pred003(x,as_of,lineage):
    req=['yield_delta_5bd_bps','yield_delta_10bd_bps','yield_up_days_last5']
    if any(x.get(k) is None for k in req):return _missing('PRED-003',req,as_of=as_of,lineage=lineage)
    d5,d10,up=D(x[req[0]]),D(x[req[1]]),int(x[req[2]]); states=[]
    if d5>=35 or d10>=60:states.append('EXTREME_RISE')
    if d5>=20 and d10>=35 and up>=3:states.append('SUSTAINED_SHARP_RISE')
    if d5<=0 and d10<=10:states.append('NORMALIZING')
    if not states:states=['MIXED_STABLE']
    return _result('PRED-003',states,as_of=as_of,lineage=lineage)

def pred004(x,as_of,lineage):
    if x.get('hy_oas_bps') is None:return _missing('PRED-004',['hy_oas_bps'],as_of=as_of,lineage=lineage)
    hy=D(x['hy_oas_bps']); rapid=[]
    thresholds={'hy':(50,100),'ig':(15,30),'bbb':(20,40),'a':(15,30)}
    for k,(t5,t20) in thresholds.items():
        v5=x.get(f'{k}_oas_delta_5bd_bps');v20=x.get(f'{k}_oas_delta_20bd_bps')
        rapid.append(False if v5 is None and v20 is None else ((v5 is not None and D(v5)>=t5) or (v20 is not None and D(v20)>=t20)))
    states=[]
    if hy>=800 or (x.get('hy_oas_delta_20bd_bps') is not None and D(x['hy_oas_delta_20bd_bps'])>=200 and any(rapid[1:])):states.append('CREDIT_CRISIS')
    if hy>=600 or sum(rapid)>=2:states.append('CREDIT_STRESS')
    if hy>=800:states.append('HY_CRISIS')
    elif hy>=600:states.append('HY_RECESSION_STRESS')
    elif hy>=400:states.append('HY_WATCH')
    else:states.append('HY_NORMAL')
    return _result('PRED-004',states,as_of=as_of,lineage=lineage)

def pred005(x,as_of,lineage):
    if x.get('move') is None or x.get('move_pct_change_5bd') is None:return _missing('PRED-005',['move','move_pct_change_5bd'],as_of=as_of,lineage=lineage)
    m,c=D(x['move']),D(x['move_pct_change_5bd']);states=[]
    if m>=150 or c>=35:states.append('EXTREME')
    if m>=120 or c>=20:states.append('SURGE')
    if not states:states=['NORMAL']
    return _result('PRED-005',states,as_of=as_of,lineage=lineage)

def pred006(x,as_of,lineage):
    sig=[]; core4=[]
    for k in ('core_pce','core_cpi','core_ppi'):
        a3=x.get(f'{k}_ann3_pct');a6=x.get(f'{k}_ann6_pct')
        sig.append(False if a3 is None or a6 is None else D(a3)>=3 and D(a3)-D(a6)>=D('.5'))
        core4.append(False if a3 is None else D(a3)>=4)
    be20=x.get('breakeven_5y_delta_20bd_bps'); be=x.get('breakeven_5y_pct'); oil=x.get('oil_price_change_20bd_pct')
    sig.append(False if be20 is None else D(be20)>=25)
    reacc=sum(sig)>=2 and any(sig[:3])
    loss_items=[*core4, False if be is None and be20 is None else ((be is not None and D(be)>=3) or (be20 is not None and D(be20)>=50)), False if oil is None else D(oil)>=20]
    loss=sum(loss_items)>=2 and any(core4[:2])
    if not any(x.get(k) is not None for k in ('core_pce_ann3_pct','core_cpi_ann3_pct','core_ppi_ann3_pct')):return _missing('PRED-006',['realized core inflation'],as_of=as_of,lineage=lineage)
    states=[]
    if loss:states.append('LOSS_OF_CONTROL')
    if reacc:states.append('INFLATION_REACCELERATION')
    if not states:states=['NO_INFLATION_ALERT']
    return _result('PRED-006',states,as_of=as_of,lineage=lineage)

def pred007(x,as_of,lineage):
    vals=[]
    specs=[('sofr_ois_bps',20,50,False),('fra_ois_bps',30,75,False),('srf_usage_usd',5_000_000_000,20_000_000_000,False),('treasury_market_depth_percentile_3y',20,5,True)]
    for k,a,s,lower in specs:
        if x.get(k) is not None:
            v=D(x[k]); vals.append(((v<=a) if lower else (v>=a),(v<=s) if lower else (v>=s)))
    severe=sum(b for _,b in vals); abnormal=sum(a for a,_ in vals)
    if severe>=2:return _result('PRED-007',['SEVERE_ABNORMAL'],as_of=as_of,lineage=lineage)
    if abnormal>=2:return _result('PRED-007',['ABNORMAL'],as_of=as_of,lineage=lineage)
    if len(vals)<3:return _missing('PRED-007',['>=3 valid liquidity signals'],as_of=as_of,lineage=lineage)
    return _result('PRED-007',['NORMAL' if abnormal==0 else 'MIXED'],as_of=as_of,lineage=lineage)

def pred008(x,as_of,lineage):
    p=x.get('yield_percentile_pct'); hist=x.get('history_years'); proxy=bool(x.get('formal_proxy',False))
    if p is None or hist is None:return _missing('PRED-008',['yield_percentile_pct','history_years'],as_of=as_of,lineage=lineage)
    if D(hist)<3 and not proxy:return _missing('PRED-008',['>=3y history or formal proxy'],as_of=as_of,lineage=lineage)
    p=D(p); reasons=['SHORT_HISTORY'] if D(hist)<5 else []
    s='LOW_ATTRACTIVENESS' if p<=25 else 'FAIR' if p<75 else 'ATTRACTIVE' if p<90 else 'VERY_ATTRACTIVE'
    return _result('PRED-008',[s],as_of=as_of,lineage=lineage,reasons=reasons)

def pred009(x,as_of,lineage):
    available=sum(x.get(k) is not None for k in ('low_td_count','k','d','rsi14','close','ma20','ma50','rolling_20d_low','atr14'))
    if available<3:return _missing('PRED-009',['>=3 core technical indicators'],as_of=as_of,lineage=lineage)
    left=0
    if x.get('low_td_count') is not None:left+=int(x['low_td_count'])>=5
    if x.get('k') is not None or x.get('d') is not None:left+=(x.get('k') is not None and D(x['k'])<=20) or (x.get('d') is not None and D(x['d'])<=20)
    if x.get('rsi14') is not None:left+=D(x['rsi14'])<=30
    if all(x.get(k) is not None for k in ('close','ma20','ma50')):left+=D(x['close'])<=D(x['ma20']) and D(x['close'])<=D(x['ma50'])
    if all(x.get(k) is not None for k in ('close','rolling_20d_low','atr14')):left+=D(x['close'])<=D(x['rolling_20d_low'])+D(x['atr14'])
    right=sum(bool(x.get(k,False)) for k in ('kd_golden_cross_k_le_35','macd_hist_improving_3d','dif_slope_positive_or_macd_golden_cross','reclaimed_ma20_last3d','higher_5d_low'))
    trim=0
    if x.get('high_td_count') is not None and int(x['high_td_count'])>=8:
        trim=sum(bool(x.get(k,False)) for k in ('kd_death_cross_k_ge_80','rsi14_ge_70','macd_hist_shrinking_3d','price_up_volume_below_ma20'))
    states=[]
    if trim>=2:states.append('TRIM_WATCH')
    if right>=3:states.append('RIGHT_CONFIRM')
    if left>=3:states.append('LEFT_MATURE')
    if not states:states=['TECHNICAL_NEUTRAL']
    return _result('PRED-009',states,as_of=as_of,lineage=lineage)

def pred010(x,as_of,lineage):
    # adapters provide deterministic component states after applying the frozen structure/liquidity/distribution thresholds.
    comps=[x.get('structure_state'),x.get('liquidity_state_etf'),x.get('distribution_quality_state')]
    if any(c is None for c in comps):return _missing('PRED-010',['structure_state','liquidity_state_etf','distribution_quality_state'],as_of=as_of,lineage=lineage)
    if any(str(c).endswith('_ABNORMAL') for c in comps):s='ETF_QUALITY_ABNORMAL'
    elif 'REVIEW_REQUIRED' in comps:s='ETF_QUALITY_REVIEW_REQUIRED'
    elif 'UNKNOWN' in comps:s='ETF_QUALITY_UNKNOWN'
    else:s='ETF_QUALITY_NORMAL'
    return _result('PRED-010',[s],as_of=as_of,lineage=lineage)

EVALUATORS={'PRED-001':pred001,'PRED-002':pred002,'PRED-003':pred003,'PRED-004':pred004,'PRED-005':pred005,'PRED-006':pred006,'PRED-007':pred007,'PRED-008':pred008,'PRED-009':pred009,'PRED-010':pred010}
