"""CMR6.3 ETF_VIABLE_01 production from bound issuer facts and owner policy.

Each fact remains independently usable. A listing, an empty news list or a
positive accounting ratio cannot stand in for current structural evidence.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,InvalidOperation,localcontext
from urllib.parse import urlparse
from approved_v04_technical import both,truth

LEAVES=('fund_legally_operating','current_mandate_within_client_approved_mandate',
    'nav_reporting_and_creation_redemption_function_valid','termination_or_disqualification_absent',
    'lookthrough_disposition_allows_long_term_holding')


def boolean(value):return value if type(value) is bool else None

def number(value):
    if isinstance(value,bool):return None
    try:
        d=Decimal(str(value));return d if d.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None


def timestamp(value):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'));return d if d.utcoffset() is not None else None
    except (ValueError,TypeError,AttributeError):return None


def source_record(facts,key,at):
    record=facts.get(key);missing=[]
    if not isinstance(record,dict):return None,[key]
    source=record.get('source_reference',facts.get('source_url'))
    host=urlparse(source or '').hostname or ''
    allowed=('vanguard.com','sec.gov','nyse.com')
    if not any(host==d or host.endswith('.'+d) for d in allowed):missing.append(key+'.official_source')
    if not facts.get('source_sha256'):missing.append(key+'.bound_source_sha256')
    available=timestamp(record.get('available_at'));until=timestamp(record.get('valid_until'))
    observed=timestamp(record.get('as_of'))
    if available is None or available>at:missing.append(key+'.available_at')
    validity=record.get('source_validity',{})
    checked=timestamp(validity.get('checked_at'))
    state_valid=(validity.get('state')=='VALID' and validity.get('method_version')
        and validity.get('basis') in ('ORIGINAL_EVENT_LIFECYCLE','ORIGINAL_RELEASE_CALENDAR','AUTHORITATIVE_CURRENT_STATE')
        and checked is not None and checked<=at
        and (available is None or available<=checked))
    # A source-owned lifecycle/release contract need not invent a wall-clock
    # expiry. A supplied expiry remains binding and cannot be overridden.
    if (until is not None and until<at) or (until is None and not state_valid):
        missing.append(key+'.source_validity_or_valid_until')
    if observed is None or observed>at or (available and observed>available):missing.append(key+'.as_of')
    if available and until and until<available:missing.append(key+'.validity_order')
    if record.get('data_quality')!='OK':missing.append(key+'.data_quality')
    return (None if missing else record),missing


def mandate_subset(current,allowed):
    if not isinstance(current,list) or not current or not all(isinstance(x,str) and x for x in current):return None
    if not isinstance(allowed,list) or not all(isinstance(x,str) and x for x in allowed):return None
    return set(current)<=set(allowed)


def lookthrough_intervals(composition,limits):
    with localcontext() as context:
        context.prec=50
        return _lookthrough_intervals(composition,limits)


def _lookthrough_intervals(composition,limits):
    """Approved interval rule; no renormalization or invented exposure caps."""
    if not isinstance(limits,list) or not limits:return {'truth':'UNKNOWN','issues':['approved_exposure_limits'],'limits':[]}
    if not composition or composition.get('universe_complete') is not True or composition.get('weight_unit')!='fraction':
        return {'truth':'UNKNOWN','issues':['lookthrough.universe/weight_basis'],'limits':[]}
    total=number(composition.get('total_weight'));rows=composition.get('components');weights=[];ids=[]
    if total is None or total<=0 or not isinstance(rows,list) or not rows:
        return {'truth':'UNKNOWN','issues':['lookthrough.denominator/components'],'limits':[]}
    for row in rows:
        weight=number(row.get('weight'));ident=row.get('component_id')
        if weight is None or weight<0 or not ident or ident in ids:
            return {'truth':'UNKNOWN','issues':['lookthrough.component_identity_or_weight'],'limits':[]}
        ids.append(ident);weights.append(weight)
    if sum(weights,Decimal(0))!=total:
        return {'truth':'UNKNOWN','issues':['lookthrough.incomplete_weight_denominator'],'limits':[]}
    out=[];votes=[];seen=set()
    for limit in limits:
        domain=limit.get('risk_domain');cap=number(limit.get('allowed_exposure'))
        if not domain or domain in seen or cap is None or not 0<=cap<=1 or not limit.get('authority_reference'):
            return {'truth':'UNKNOWN','issues':['approved_exposure_limit_definition'],'limits':out}
        seen.add(domain);affected=unknown=Decimal(0)
        for row,weight in zip(rows,weights):
            state=boolean(row.get('risk_status',{}).get(domain))
            if state is True:affected+=weight
            elif state is None:unknown+=weight
        low=affected/total;high=(affected+unknown)/total
        value=True if affected+unknown<=cap*total else False if affected>cap*total else None
        votes.append(value);out.append({'risk_domain':domain,'known_affected_weight':str(affected),
            'unknown_relevant_weight':str(unknown),'total_weight':str(total),'lower':str(low),'upper':str(high),
            'allowed_exposure':str(cap),'truth':truth(value),'authority_reference':limit['authority_reference']})
    return {'truth':truth(both(*votes)),'issues':[],'limits':out,'weights_renormalized':False}


def evaluate_etf_structure(facts,request,symbol,product_evidence=None):
    facts=facts or {};at=timestamp(request['evaluation_at'])
    if at is None:raise ValueError('ETF_STRUCTURE_EVALUATION_TIME_INVALID')
    if facts and facts.get('symbol')!=symbol:raise ValueError('ETF_STRUCTURE_SYMBOL_MISMATCH')
    draft=request.get('confirmed_target',{}).get('payload',{}).get('draft',{})
    policy=draft.get('etf_constraints',{}).get(symbol)
    if policy and (policy.get('client_id')!=request['client_id'] or policy.get('symbol')!=symbol):
        raise PermissionError('ETF_STRUCTURE_OWNER_POLICY_MISMATCH')
    policy=policy or {};leaves={};trace=[]
    def put(name,value,fields,detail=None,applicability='APPLICABLE'):
        leaves[name]={'truth':truth(value),'missing_fields':fields,'detail':detail,
            'applicability':applicability,'gap_kind':'SOURCE_FACT_MISSING' if fields else
                'SOURCE_DEPENDENCY_UNRESOLVED' if value is None else 'COMPUTED_FROM_BOUND_SOURCE'}
    status,missing=source_record(facts,'fund_status',at)
    state=status.get('operating_status') if status else None
    value=True if state=='OPERATING' else False if state in ('CEASED','SUSPENDED','DISQUALIFIED') else None
    put(LEAVES[0],value,missing+(['fund_status.operating_status'] if status and value is None else []),state)
    trace.append('ETF_VIABLE_01.operating_status')
    mandate,missing=source_record(facts,'mandate',at)
    allowed=policy.get('allowed_mandate_components')
    value=mandate_subset(mandate.get('components') if mandate else None,allowed)
    if mandate and not isinstance(mandate.get('components'),list):missing.append('mandate.components')
    if allowed is None:missing.append('approved_target.etf_constraints.'+symbol+'.allowed_mandate_components')
    if mandate and not mandate.get('method_version'):missing.append('mandate.method_version');value=None
    put(LEAVES[1],value if not missing else None,missing,
        {'issuer_components':mandate.get('components') if mandate else None,'approved_components':allowed})
    trace.append('ETF_VIABLE_01.mandate_subset')
    nav,missing=source_record(facts,'nav_redemption_status',at)
    nav_ok=boolean(nav.get('nav_reporting_valid')) if nav else None
    redemption=boolean(nav.get('creation_redemption_function_valid')) if nav else None
    if nav and nav_ok is None:missing.append('nav_redemption_status.nav_reporting_valid')
    if nav and redemption is None:missing.append('nav_redemption_status.creation_redemption_function_valid')
    put(LEAVES[2],both(nav_ok,redemption),missing)
    trace.append('ETF_VIABLE_01.nav_and_creation_redemption')
    event,missing=source_record(facts,'termination_event',at)
    failure=boolean(event.get('confirmed_termination')) if event else None
    disqualified=boolean(event.get('permanent_disqualification')) if event else None
    required={'FUND_TERMINATION','PERMANENT_OPERATIONAL_DISQUALIFICATION'}
    declared=set(event.get('required_domains',[])) if event else set()
    checked=set(event.get('checked_domains',[])) if event else set()
    coverage=bool(event and required<=declared and required<=checked and event.get('checkpoint_id') and event.get('coverage_complete') is True)
    absent=False if failure is True or disqualified is True else True if failure is False and disqualified is False and coverage else None
    if event and absent is None:missing.append('termination_event.complete_required_domain_coverage_and_assertions')
    put(LEAVES[3],absent,missing,{'coverage_verified':coverage,'absence_asserted':absent is True})
    trace.append('ETF_VIABLE_01.termination_and_coverage')
    if policy.get('lookthrough_restrictions')=='EXPLICIT_APPROVED_NONE' and policy.get('authority_reference'):
        put(LEAVES[4],True,[],{'authority_reference':policy['authority_reference']},'NOT_APPLICABLE_EXPLICIT_APPROVED_NONE')
    else:
        composition,missing=source_record(facts,'lookthrough',at)
        audit=lookthrough_intervals(composition,policy.get('exposure_limits'))
        put(LEAVES[4],True if audit['truth']=='TRUE' else False if audit['truth']=='FALSE' else None,missing+audit['issues'],audit)
    trace.append('ETF_VIABLE_01.lookthrough_weight_intervals')
    value=both(*(True if r['truth']=='TRUE' else False if r['truth']=='FALSE' else None for r in leaves.values()))
    return {'rule_ref':'V82 v1.0 CMR6.3 ETF_VIABLE_01','result':truth(value),'leaves':leaves,
        'producer_complete':True,'source_ready_count':sum(r['truth']!='UNKNOWN' for r in leaves.values()),
        'source_inputs_complete':all(not r['missing_fields'] for r in leaves.values()),
        'checked_sources':{'product_evidence':deepcopy(product_evidence),'issuer_url':facts.get('source_url'),
            'issuer_date':facts.get('as_of'),'available_fields':sorted(facts),
            'target_allocation_version':draft.get('original_allocation_version')},
        'call_trace':trace,'existing_metrics_are_not_viability_assertions':True}
