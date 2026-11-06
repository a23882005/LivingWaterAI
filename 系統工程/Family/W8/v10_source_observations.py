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


def forward_level(value,bands):
    return next((name for limit,name in zip(bands,('CHEAP','NORMAL','PRICEY','EXPENSIVE'))
        if value<limit),'EXTREME_CANDIDATE')


def current_forward_observations(facts,asset_class,rule_source):
    """Use an explicitly labelled current observation with its own product class.

    The owner authorizes recent current-analysis sources. This is not a PIT,
    original financial publication-date, execution or macro-producer assertion.
    """
    if not facts or not facts.get('current_forward_observation'):return []
    proof=facts['current_forward_observation'];record=facts.get('metrics',{}).get('FORWARD_PE',{})
    if (proof.get('label')!='Forward PE' or proof.get('metric_name')!='FORWARD_PE'
        or proof.get('purpose')!='OWNER_AUTHORIZED_RECENT_CURRENT_ANALYSIS_ONLY'
        or facts.get('symbol')!=asset_class.get('symbol')
        or record.get('unit')!='multiple' or asset_class.get('primary_class')!='全球股票ETF'
        or asset_class.get('asset_type')!='BROAD_ETF'):return []
    from formal_analysis_signals import verify_rules
    text=verify_rules(rule_source)
    row=next((line for line in text.splitlines() if line.startswith('| VT／VWRA型 |')),None)
    if row is None or not all(token in row for token in ('<14','>=14 且 <18','>=18 且 <20','>=20 且 <23','>=23')):
        return []
    if isinstance(record.get('value'),bool):raise ValueError('CURRENT_FORWARD_PE_INVALID')
    value=Decimal(str(record.get('value')))
    if not value.is_finite() or value<=0:raise ValueError('CURRENT_FORWARD_PE_INVALID')
    return [{'metric_name':'FORWARD_PE','current':str(value),'unit':'multiple',
        'valuation_level':forward_level(value,(14,18,20,23)),
        'source_reference':facts['source_url'],'source_sha256':facts['source_sha256'],
        'as_of':facts['as_of'],'as_of_basis':facts.get('as_of_basis'),
        'observed_date_text':facts['as_of'],'source_original_data_date':facts.get('source_original_data_date'),
        'data_quality':'OK','freshness':'NOT_APPLICABLE','pit_status':'NOT_APPLICABLE',
        'current_source_accepted':True,'historical_publication_time_verified':False,
        'execution_input_eligible':False,'purpose':'CURRENT_HOLDINGS_ANALYSIS',
        'range_rule':'V82 §32.3 verified global stock ETF class; own Forward PE source',
        'scope':'DIRECT_CURRENT_PROVIDER_OBSERVATION__NOT_V70_OR_HISTORICAL_PIT'}]


def forward_observations(snapshot,symbol,evaluated_at,*,purpose='STRICT_NATIVE_INPUT'):
    if purpose not in ('STRICT_NATIVE_INPUT','CURRENT_HOLDINGS_ANALYSIS'):
        raise ValueError('VALUATION_PURPOSE_INVALID')
    rules={'VT':('m03_vt',(14,18,20,23),'VT/VWRA'),
        'QQQ':('m03_qqq',(18,24,28,33),'QQQ/Nasdaq-100')}
    if symbol not in rules:return []
    source_key,bands,family=rules[symbol]
    raw,at=checked_payload(snapshot,evaluated_at);found=field(raw,source_key,'倍 Forward',at)
    if found is None:return []
    value,row=found;evidence=row.get('sourceEvidence',{})
    if (evidence.get('label')!='Forward PE' or Decimal(str(evidence.get('value')))!=value
            or evidence.get('source_url')!=row['source'] or value<=0):
        raise ValueError('V10_FORWARD_PE_DEFINITION_OR_SOURCE_MISMATCH')
    # Each independently verified product route has its own authorized range.
    # A trailing multiple never enters this mapper.
    level=forward_level(value,bands)
    freshness,pit,missing=valuation_validity(row,at)
    source_validity={'freshness':freshness,'pit_status':pit,'missing_contracts':list(missing)}
    current_accepted=purpose=='CURRENT_HOLDINGS_ANALYSIS'
    if current_accepted:
        # Owner directs that the verified published V70 producer qualifies its
        # input for current A analysis. Historical publication metadata is not
        # required in this scope; no timestamp or expiry is manufactured.
        freshness='NOT_APPLICABLE';pit='NOT_APPLICABLE';missing=[]
    capture=snapshot.get('capture_receipt',{})
    capture_verified=False
    if row.get('available_at') is None and capture.get('schema_version')=='Family.W5.SourceCaptureBound.v1':
        bound=datetime.fromisoformat(capture['captured_at'].replace('Z','+00:00'))
        capture_verified=(bound.utcoffset() is not None and bound<=at
            and capture.get('source_sha256')==snapshot.get('source_sha256')
            and capture.get('payload_digest')==snapshot.get('digest')
            and capture.get('basis')=='EXACT_SOURCE_BYTES_READ_AND_HASH_CHECKED')
        # A checked capture proves these bytes existed before this analysis.
        # It does not establish the field's release/revision availability, so
        # it cannot replace available_at or promote formal PIT validity.
    return [{'metric_name':'FORWARD_PE','current':str(value),'unit':'multiple',
        'valuation_level':level,'classification_scope':'AUTHORIZED_RANGE_OBSERVATION__VALIDITY_REQUIRED',
        'source_reference':row['source'],'source_sha256':snapshot['source_sha256'],
        'source_field':'V70.indicators.'+source_key,'source_row':deepcopy(row),
        'as_of':row['dataDate'],'observed_date_text':row['dataDate'],'data_quality':'OK',
        'freshness':freshness,'pit_status':pit,'frequency':row.get('frequency'),
        'available_at':row.get('available_at'),'published_at':row.get('published_at'),
        'availability_bound':deepcopy(capture) if capture_verified else None,
        'known_by_capture_verified':capture_verified,
        'pit_scope':'CURRENT_V70_PRODUCER_ACCEPTANCE__NO_HISTORICAL_PUBLICATION_CLAIM' if current_accepted else 'SOURCE_AVAILABILITY_CONTRACT__CAPTURE_IS_NOT_A_PIT_SUBSTITUTE',
        'valid_until':row.get('valid_until'),'method':row.get('method'),
        'purpose':purpose,'strict_contract_validity':source_validity,
        'current_source_accepted':current_accepted,
        'source_acceptance_basis':'OWNER_20261028_V70_PUBLISHED_INPUT_QUALIFIES_FOR_CURRENT_ANALYSIS' if current_accepted else None,
        'historical_publication_time_verified':False if current_accepted else pit=='VERIFIED',
        'execution_input_eligible':False if current_accepted else None,
        'missing_contracts':missing,
        'scope':'VERIFIED_PUBLISHED_V70_CURRENT_ANALYSIS_ONLY' if current_accepted else 'EXISTING_VERIFIED_V70_FORWARD_VALUE__NO_INVENTED_FRESHNESS',
        'range_rule':'V82 §32.3 '+family+' forward-only '+ '/'.join(map(str,bands))}]


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
