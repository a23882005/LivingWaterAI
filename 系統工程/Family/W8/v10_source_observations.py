"""Map existing W3 facts to v1.0 observations, without inventing validity.

Missing release calendars, comparable priors and event coverage remain explicit.
Numeric bands are not Hard Gate decisions, funding, or trading authorization.
"""
from copy import deepcopy
from datetime import date,datetime
from decimal import Decimal
from family_input import digest
from approved_v04_technical import both,either,cmp,truth


def checked_payload(snapshot,evaluated_at):
    raw=snapshot['payload']
    if raw.get('schema')!='V70.3/family-macro-feed-v3' or digest(raw)!=snapshot.get('digest'):
        raise ValueError('V10_MACRO_SOURCE_BINDING_MISMATCH')
    at=datetime.fromisoformat(evaluated_at.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('V10_EVALUATION_TIMEZONE_REQUIRED')
    if datetime.fromisoformat(raw['asOf'].replace('Z','+00:00'))>at:
        raise ValueError('V10_MACRO_SOURCE_IN_FUTURE')
    return raw,at


def field(raw,key,unit,at):
    row=raw.get('indicators',{}).get(key)
    if raw.get('verification',{}).get('ready') is not True or not row:return None
    if row.get('status')!='OK' or row.get('unit')!=unit or not row.get('source'):return None
    if isinstance(row.get('value'),bool):raise ValueError('V10_MACRO_INVALID_VALUE:'+key)
    value=Decimal(str(row.get('value')))
    if not value.is_finite():raise ValueError('V10_MACRO_INVALID_VALUE:'+key)
    if date.fromisoformat(row['dataDate'])>at.date():raise ValueError('V10_MACRO_OBSERVATION_IN_FUTURE:'+key)
    for key_time in ('lastVerifiedAt','retrievalTime'):
        if row.get(key_time) and datetime.fromisoformat(row[key_time].replace('Z','+00:00'))>at:
            raise ValueError('V10_MACRO_RECEIPT_IN_FUTURE:'+key)
    return value,row


def forward_observations(snapshot,symbol,evaluated_at):
    if symbol!='VT':return []
    raw,at=checked_payload(snapshot,evaluated_at);found=field(raw,'m03_vt','倍 Forward',at)
    if found is None:return []
    value,row=found;evidence=row.get('sourceEvidence',{})
    if (evidence.get('label')!='Forward PE' or Decimal(str(evidence.get('value')))!=value
            or evidence.get('source_url')!=row['source'] or value<=0):
        raise ValueError('V10_FORWARD_PE_DEFINITION_OR_SOURCE_MISMATCH')
    # This operational range is authorized only for the independently verified
    # VT/VWRA-type route. A trailing multiple never enters this mapper.
    level=('CHEAP' if value<14 else 'NORMAL' if value<18 else 'PRICEY' if value<20
        else 'EXPENSIVE' if value<23 else 'EXTREME_CANDIDATE')
    freshness,pit,missing=valuation_validity(row,at)
    return [{'metric_name':'FORWARD_PE','current':str(value),'unit':'multiple',
        'valuation_level':level,'classification_scope':'AUTHORIZED_RANGE_OBSERVATION__VALIDITY_REQUIRED',
        'source_reference':row['source'],'source_sha256':snapshot['source_sha256'],
        'source_field':'V70.indicators.m03_vt','source_row':deepcopy(row),
        'as_of':row['dataDate'],'observed_date_text':row['dataDate'],'data_quality':'OK',
        'freshness':freshness,'pit_status':pit,'frequency':row.get('frequency'),
        'available_at':row.get('available_at'),'published_at':row.get('published_at'),
        'valid_until':row.get('valid_until'),'method':row.get('method'),
        'missing_contracts':missing,
        'scope':'EXISTING_VERIFIED_V70_FORWARD_VALUE__NO_INVENTED_FRESHNESS',
        'range_rule':'V82 §32.3 VT/VWRA forward-only 14/18/20/23'}]


def valuation_validity(row,at):
    """Use explicit source contracts, never turn retrieval time into PIT."""
    missing=[];freshness='UNKNOWN';pit='UNVERIFIABLE'
    def timestamp(key):
        value=row.get(key)
        if value is None:return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.utcoffset() is not None else None
        except (TypeError,ValueError,AttributeError):return None
    until=timestamp('valid_until');available=timestamp('available_at');published=timestamp('published_at')
    order_valid=(available is not None and available<=at and
        (published is None or published<=available) and date.fromisoformat(row['dataDate'])<=available.date())
    if until is not None and row.get('frequency') and order_valid:
        freshness='FRESH' if available<=until and at<=until else 'STALE'
    if freshness=='UNKNOWN':missing.append('frequency/valid_until_or_max_age')
    if order_valid:pit='VERIFIED'
    else:missing.append('field_available_at/PIT')
    return freshness,pit,missing


def credit_logic(hy,vix,move,*,rapid=None,treasury=None,repo=None,official=None,direction_widening=None):
    c3=either(official,both(cmp(hy,Decimal(600),'gt'),rapid,
        either(cmp(vix,Decimal(35),'gt'),cmp(move,Decimal(120),'gt')),either(treasury,repo)))
    c2=either(both(cmp(hy,Decimal(500),'gt'),rapid),
        both(cmp(move,Decimal(120),'gt'),treasury,repo,direction_widening))
    c1=either(cmp(hy,Decimal(300),'ge'),cmp(vix,Decimal(25),'gt'),cmp(move,Decimal(120),'gt'),rapid)
    established=[level for level,c in ((1,c1),(2,c2),(3,c3)) if c is True]
    possible=[level for level,c in ((1,c1),(2,c2),(3,c3)) if c is not False]
    lower=max(established,default=0);upper=max(possible,default=0)
    return {'C1':truth(c1),'C2':truth(c2),'C3':truth(c3),
        'risk_level':lower if lower==upper else 'UNKNOWN',
        'proven_lower_bound':lower,'possible_upper_bound':upper,
        'rule_ref':'V82 v1.0 CMR4.2','hard_gate':'NOT_EVALUATED_BY_NUMERIC_BANDS'}


def macro_observations(snapshot,evaluated_at):
    raw,at=checked_payload(snapshot,evaluated_at);observed={};values={}
    for key,name,unit,factor in [('m02','hy_oas','%',100),('m07','vix','',1),('m12','move','',1)]:
        found=field(raw,key,unit,at)
        if found is None:values[name]=None;continue
        value,row=found;value*=factor;values[name]=value
        if name=='hy_oas':band='HEALTHY' if value<300 else 'NORMAL_TO_TIGHT' if value<=500 else 'STRESS_ELEVATED'
        elif name=='vix':band='LOW' if value<15 else 'NORMAL_TO_ELEVATED' if value<=25 else 'RISK_AVERSION' if value<=35 else 'HIGH_PANIC'
        else:band='CALM' if value<90 else 'ELEVATED' if value<=120 else 'SIGNIFICANTLY_ELEVATED'
        observed[name]={'value':str(value),'unit':'bp' if name=='hy_oas' else 'index_points',
            'band':band,'as_of':row['dataDate'],'source_row':deepcopy(row),
            'direction':'UNKNOWN','speed':'UNKNOWN','freshness':'UNKNOWN',
            'missing_contracts':['comparable prior and 5/20-session observations','expected release/session coverage'],
            'source_sha256':snapshot['source_sha256']}
    return {'schema_version':'Family.W8.FormalV10MacroObservations.v1','observed':observed,
        'credit':credit_logic(values.get('hy_oas'),values.get('vix'),values.get('move')),
        'source_digest':snapshot['digest'],'source_as_of':raw['asOf'],
        'remaining_inputs':['HY comparable prior/5/20 sessions','Treasury spread/depth basket history',
            'Repo benchmark and comparable official corridor','official systemic-event assertion/coverage'],
        'full_safety_contract_complete':False}
