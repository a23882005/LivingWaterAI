"""USD PRED-007 delegated amendment; independent R/C names and thresholds.

This policy is V75-PRED007-20261029-01 v1.0, not an interpretation of the
retired SOFR-OIS/FRA-OIS fields. Other frozen predicates remain unchanged.
"""
from datetime import date,timedelta
from decimal import Decimal,InvalidOperation,ROUND_CEILING,localcontext
import re

AMENDMENT_ID='V75-PRED007-20261029-01'
AMENDMENT_VERSION='1.0'
BASE_VERSION='V75_PREDICATE_PARAMS_v1.0.3'
RULESET_SHA256='75730eaf6f11de60aa5d914c67cbfd29e0af4772f3ba51445c48648fb6cad870'
EFFECTIVE_AT='2026-10-29T09:03:48+00:00'
EFFECTIVE_VERSION=BASE_VERSION+'+'+AMENDMENT_ID+'@'+AMENDMENT_VERSION+'#'+RULESET_SHA256
FIELDS={'R':'sofr_iorb_spread_bps','C':'aa_financial_cp90d_tbill3m_discount_spread_bps',
    'S':'SRF_usage_usd','D':'treasury_market_depth_percentile_3y'}


class InvalidInput(ValueError):pass
class ReviewRequired(ValueError):pass


def exact(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,Decimal)):
        raise InvalidInput('EXACT_DECIMAL_REQUIRED')
    if isinstance(value,str) and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',value):
        raise InvalidInput('MALFORMED_DECIMAL')
    try:result=Decimal(value)
    except InvalidOperation as error:raise InvalidInput('MALFORMED_DECIMAL') from error
    if not result.is_finite():raise InvalidInput('NONFINITE_DECIMAL')
    return result


def spread(left,right):
    left=None if left is None else exact(left);right=None if right is None else exact(right)
    if left is None or right is None:return None
    with localcontext() as ctx:
        ctx.prec=max(50,sum(len(v.as_tuple().digits)+abs(v.as_tuple().exponent) for v in (left,right))+5)
        return (left-right)*100


def start_date(day):
    try:return day.replace(year=day.year-3)
    except ValueError:return day.replace(year=day.year-3,day=28)


def unique(rows):
    out={}
    for day,value in rows:
        if type(day) is not date:raise InvalidInput('OBSERVATION_DATE_REQUIRED')
        value=None if value is None else exact(value)
        if day in out and out[day]!=value:raise ReviewRequired('CONFLICTING_DUPLICATE_DATE')
        out[day]=value
    return out


def nearest_rank(values,p):
    values=sorted(exact(v) for v in values);p=exact(p)
    if not values or not 0<p<=1:raise InvalidInput('QUANTILE_INPUT')
    return values[int((p*len(values)).to_integral_value(rounding=ROUND_CEILING))-1]


def calibrated(kind,rows,observed,rules):
    points=unique(rows);selected=sorted((d,v) for d,v in points.items()
        if start_date(observed)<=d<observed and v is not None)
    span=(selected[-1][0]-selected[0][0]).days if selected else 0
    out={'history_n':len(selected),'history_span_days':span,
        'history_start_inclusive':start_date(observed).isoformat(),
        'history_end_exclusive':observed.isoformat(),'Q95':None,'Q99':None,'A':None,'S':None}
    if len(selected)<rules['R_C_history']['min_n'] or span<rules['R_C_history']['min_span_calendar_days']:
        return out
    values=[v for _,v in selected];definition=rules['signals'][kind]
    q95=nearest_rank(values,rules['R_C_history']['q_abnormal']);q99=nearest_rank(values,rules['R_C_history']['q_severe'])
    a=max(exact(definition['abnormal_floor_bps']),q95)
    severe=max(exact(definition['severe_floor_bps']),q99,a+1)
    return {**out,'Q95':str(q95),'Q99':str(q99),'A':str(a),'S':str(severe)}


def level(value,abnormal,severe):
    value=exact(value);a=exact(abnormal);s=exact(severe)
    if s<=a:raise InvalidInput('SEVERE_THRESHOLD_MUST_EXCEED_ABNORMAL')
    return 'SEVERE' if value>=s else 'ABNORMAL' if value>=a else 'NORMAL'


def aggregate(signals,quality=()):
    if set(signals)!=set(FIELDS):raise InvalidInput('FOUR_CANDIDATES_REQUIRED')
    states=[signals[k].get('state') for k in FIELDS]
    if any(s not in (None,'NORMAL','ABNORMAL','SEVERE') for s in states):raise InvalidInput('CANDIDATE_STATE')
    if any(q not in ('INVALID_INPUT','REVIEW_REQUIRED') for q in quality):raise InvalidInput('QUALITY_VETO')
    n=sum(s is not None for s in states);a=sum(s in ('ABNORMAL','SEVERE') for s in states);v=states.count('SEVERE')
    state=None
    if 'INVALID_INPUT' in quality:status='INVALID_INPUT'
    elif 'REVIEW_REQUIRED' in quality:status='REVIEW_REQUIRED'
    elif v>=2:status,state='VALID','SEVERE_ABNORMAL'
    elif a>=2:status,state='VALID','ABNORMAL'
    elif n<3:status='INSUFFICIENT_DATA'
    else:status,state='VALID','MIXED' if a else 'NORMAL'
    warnings=[]
    if status=='VALID' and n<4:warnings.append('PARTIAL_COVERAGE')
    if v==1:warnings.append('SINGLE_SEVERE_SIGNAL')
    if signals['C'].get('held_recent_cp_pair'):warnings.append('HELD_RECENT_CP_PAIR')
    return {'assessment_status':status,'aggregate_state':state,'sub_states':[state] if state else [],
        'N':n,'A':a,'V':v,'coverage':str(Decimal(n)/4),'coverage_count':str(n)+'/4',
        'missing_candidates':[{'candidate':k,'reason':signals[k].get('reason')} for k,s in zip(FIELDS,states) if s is None],
        'warnings':warnings,'single_severe_warning':v==1,'partial_coverage':status=='VALID' and n<4}
