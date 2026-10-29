"""PRED-010 component source adapter for the recovered Work1 contract.

Only the three component states are produced here. Top-level aggregation
and deployment precedence remain in the unchanged V75 evaluators/runtime.
"""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo
import json

from v75_remaining_inputs import number,time,_year_ago


def both(*values):
    return False if False in values else None if None in values else True


def either(*values):
    return True if True in values else None if None in values else False


def inverse(value):return None if value is None else not value


def compare(value,operator,threshold):
    if value is None:return None
    value=number(value);threshold=number(threshold)
    return {'le':value<=threshold,'gt':value>threshold,'ge':value>=threshold,'lt':value<threshold}[operator]


def classify(ok,abnormal,normal_state,abnormal_state):
    if abnormal is True:return abnormal_state
    if ok is True:return normal_state
    return 'REVIEW_REQUIRED' if abnormal is False and ok is False else 'UNKNOWN'


def components(facts,market):
    """Apply only PRED-010 A/B/C numeric windows and three-valued leaves."""
    missing=[]
    def get(key):
        value=facts.get(key)
        if value is None:missing.append(key)
        return value
    authorized=get('authorized_universe');termination=get('liquidation_or_termination_announced')
    methodology=get('unapproved_material_methodology_change')
    for value in (authorized,termination,methodology):
        if value is not None and type(value) is not bool:raise ValueError('V75_QUALITY_BOOLEAN_REQUIRED')
    latest=get('abs_latest_premium_discount_pct');pd20=get('median_20d_abs_premium_discount_pct')
    structure_ok=both(authorized,inverse(termination),inverse(methodology),compare(latest,'le','1'),compare(pd20,'le','.5'))
    structure_bad=either(termination,methodology,compare(latest,'gt','2'))
    spread=get('median_20d_bid_ask_spread_pct');ratio=get('order_to_median_dollar_volume_pct');aum=get('aum')
    exemption=facts.get('formal_market_maker_liquidity_exemption')
    if exemption is not None and type(exemption) is not bool:raise ValueError('V75_QUALITY_BOOLEAN_REQUIRED')
    if market not in ('US','TW'):raise ValueError('V75_QUALITY_MARKET_REQUIRED')
    spread_ok,spread_bad,min_aum=('0.30','1.00','100000000') if market=='US' else ('0.50','1.50','1000000000')
    liquidity_ok=both(compare(spread,'le',spread_ok),compare(ratio,'le','10'),compare(aum,'ge',min_aum))
    liquidity_bad=either(compare(spread,'gt',spread_bad),compare(ratio,'gt','25'),
        both(compare(aum,'lt',str(number(min_aum)/2)),inverse(exemption)))
    if compare(aum,'lt',str(number(min_aum)/2)) is not False and exemption is None:
        missing.append('formal_market_maker_liquidity_exemption')
    pays=facts.get('product_explicitly_non_distributing')
    if pays is not None and type(pays) is not bool:raise ValueError('V75_QUALITY_BOOLEAN_REQUIRED')
    roc=facts.get('trailing_12m_roc_pct')
    if pays is True:distribution='NOT_APPLICABLE'
    elif roc is None:distribution='UNKNOWN';missing.append('trailing_12m_roc_pct_with_complete_issuer_breakdown')
    else:
        roc=number(roc)
        if not 0<=roc<=100:raise ValueError('V75_QUALITY_ROC_PERCENT_DOMAIN')
        distribution='DISTRIBUTION_OK' if roc<=10 else 'DISTRIBUTION_ABNORMAL' if roc>25 else 'REVIEW_REQUIRED'
    return {'structure_state':classify(structure_ok,structure_bad,'STRUCTURE_OK','STRUCTURE_ABNORMAL'),
        'liquidity_state_etf':classify(liquidity_ok,liquidity_bad,'LIQUIDITY_OK','LIQUIDITY_ABNORMAL'),
        'distribution_quality_state':distribution},sorted(set(missing))


def daily_freshness(observed,evaluation_at):
    import exchange_calendars as xc
    at=time(evaluation_at);end=at.astimezone(ZoneInfo('America/New_York')).date();day=date.fromisoformat(observed)
    if day>end:raise ValueError('V75_QUALITY_FUTURE_DATE')
    cal=xc.get_calendar('XNYS',start=day-timedelta(days=7),end=end+timedelta(days=7))
    if not cal.is_session(str(day)):raise ValueError('V75_QUALITY_NONSESSION_OBSERVATION')
    sessions=cal.sessions_in_range(str(day),str(end))
    age=sum(s.date()>day and cal.session_close(s).to_pydatetime()<=at for s in sessions)
    return {'state':'FRESH' if age<=2 else 'STALE','completed_us_sessions_since_observation':age,
        'max_us_business_days':2,'basis':'ORIGINAL_WORK1_BLUEPRINT_9.3_AND_INPUT_OUTPUT_G4',
        'calendar':'XNYS','calendar_version':xc.__version__,'observed_date':observed}


def pd_window(rows,evaluation_at):
    import exchange_calendars as xc
    values={};ordered=[]
    for row in rows:
        day=date.fromisoformat(row['date']);value=number(row['value_pct'])
        if day in values:raise ValueError('V75_QUALITY_DUPLICATE_PD_DATE')
        values[day]=value;ordered.append(day)
    if ordered!=sorted(ordered) or not ordered:raise ValueError('V75_QUALITY_PD_ORDER')
    latest=ordered[-1];fresh=daily_freshness(str(latest),evaluation_at)
    cal=xc.get_calendar('XNYS',start=latest-timedelta(days=67),end=latest+timedelta(days=7))
    expected=[s.date() for s in cal.sessions_in_range(str(latest-timedelta(days=60)),str(latest))][-20:]
    missing=[str(d) for d in expected if d not in values]
    complete=not missing and len(expected)==20
    return {'abs_latest_premium_discount_pct':str(abs(values[latest])) if fresh['state']=='FRESH' else None,
        'median_20d_abs_premium_discount_pct':str(median(abs(values[d]) for d in expected)) if complete and fresh['state']=='FRESH' else None}, {
        'observed_date':str(latest),'window_start':str(expected[0]),'sessions':len(expected),'missing_sessions':missing,
        'formula':'MEDIAN(ABS(each daily premium_discount_pct))','freshness':fresh}


def dollar_volume(raw,contract):
    root=json.loads(raw,parse_float=Decimal)['chart']['result'][0];quote=root['indicators']['quote'][0]
    excluded=set(contract['excluded_quote_bars']);zone=ZoneInfo('America/New_York');rows=[]
    from datetime import datetime
    for i,stamp in enumerate(root['timestamp']):
        moment=datetime.fromtimestamp(stamp,zone)
        if moment.isoformat() in excluded or moment.date().isoformat()>contract['observed_date']:continue
        rows.append((moment.date().isoformat(),number(quote['close'][i])*number(quote['volume'][i])))
    if len(rows)<20:raise ValueError('V75_QUALITY_DOLLAR_VOLUME_WINDOW')
    value=median(r[1] for r in rows[-20:])
    if value<=0:raise ValueError('V75_QUALITY_NONPOSITIVE_DOLLAR_VOLUME')
    return str(value),{'observed_date':rows[-1][0],'window_start':rows[-20][0],'sessions':20,
        'formula':'MEDIAN(unadjusted_Close_USD * consolidated_Volume_shares)',
        'source_sha256':contract['source_sha256'],'market_contract_digest':contract['digest']}


def assess(issuer,contract,raw,parameters,evaluation_at,*,authorized_universe,
           intended_order_amount=None,order_source=None):
    facts=issuer['facts'];flat={'authorized_universe':authorized_universe};proof={}
    pd,pd_proof=pd_window(facts['premium_discount_history'],evaluation_at);flat.update(pd);proof['premium_discount']=pd_proof
    aum=facts['aum'];aum_fresh=daily_freshness(aum['observed_date'],evaluation_at)
    if aum['unit']!=issuer['currency']:raise ValueError('V75_QUALITY_AUM_CURRENCY')
    flat['aum']=aum['value'] if aum_fresh['state']=='FRESH' else None;proof['aum_freshness']=aum_fresh
    volume=None
    if contract and contract['eligible']:
        volume,proof['dollar_volume']=dollar_volume(raw,contract)
    if intended_order_amount is not None:
        amount=number(intended_order_amount)
        if amount<0 or not order_source:raise PermissionError('V75_QUALITY_BOUND_ORDER_AMOUNT_REQUIRED')
        if volume is not None:flat['order_to_median_dollar_volume_pct']=str(amount/number(volume)*100)
    distribution=facts.get('distribution_source_observation')
    if distribution:
        proof['distribution_source']=deepcopy(distribution)
        if distribution.get('complete_source_breakdown'):
            flat['trailing_12m_roc_pct']=distribution['as_reported_roc_pct']
    if facts.get('bounded_event_coverage'):
        proof['bounded_event_coverage']=deepcopy(facts['bounded_event_coverage'])
    # The captured issuer reports 30 CALENDAR days, not the required 20
    # trading days. A reconciled issuer distribution breakdown can be used
    # under PRED-010.C while its annual tax characterization stays provisional.
    states,missing=components(flat,issuer['market'])
    fresh=all(p['state']=='FRESH' for p in (pd_proof['freshness'],aum_fresh))
    available=max([issuer['available_at']]+[p['source_available_at'] for p in
        (distribution,facts.get('bounded_event_coverage')) if p and p.get('source_available_at')],key=time)
    return {'schema_version':'Family.W8.V75ETFQualityInputs.v1','symbol':issuer['symbol'],
        'parameter_version':parameters['parameter_version'],'parameter_sha256':parameters['parameter_sha256'],
        'metrics':states,'normalized_facts':flat,'calculations':proof,'unprovided_inputs':missing,
        'assessment_at':evaluation_at,'input_freshness_verified':fresh,
        'raw_evidence_complete':not missing,'unknown_is_quality_pause':True,
        'intended_order_amount':str(number(intended_order_amount)) if intended_order_amount is not None else None,
        'order_source':deepcopy(order_source),'issuer_source_reference':issuer['source_reference'],
        'issuer_source_sha256':issuer['source_sha256'],'source_available_at':available,
        'known_auxiliary_observations':{'bid_ask_spread_30_calendar_days':deepcopy(facts.get('bid_ask_spread_30_calendar_days')),
            'distribution_characterization':deepcopy(facts.get('distribution_characterization')),
            'distribution_source_observation':deepcopy(distribution)},
        'component_producer':'ORIGINAL_PRED_010_A_B_C_THRESHOLDS_SOURCE_ADAPTER',
        'top_level_aggregation_owner':'UNCHANGED_V75_RUNTIME_PRED_010','trade_action':'NO_TRADE'}


def extend(pool,data,issuers,evaluation_at):
    parameters=pool.get('formal_parameters')
    if not parameters:return pool
    from bond_advisory import candidates
    from pathlib import Path
    universe=candidates(Path(__file__).resolve().parents[3])
    pool['issuer_observations']=issuers;pool['etf_quality_assessments']={}
    for symbol,issuer in issuers.items():
        contract=pool.get('qualified_bond_markets',{}).get(symbol)
        assessment=assess(issuer,contract,data.get('YAHOO_'+symbol),parameters,evaluation_at,
            authorized_universe=symbol in universe)
        pool['etf_quality_assessments'][symbol]=assessment
        pool['asset_metrics'].setdefault(symbol,{})['PRED-010']=assessment['metrics']
        pool['calculations'][symbol+'.PRED-010']=assessment
        pool.setdefault('asset_unprovided_inputs',{}).setdefault(symbol,{})['PRED-010']=assessment['unprovided_inputs']
        # Point-in-time canonical yield is now available. A current YTM is
        # not a five-year weekly history; do not infer a percentile from it.
        selected=issuer['facts'].get('portfolio_ytm')
        basis='OFFICIAL_PORTFOLIO_YTM'
        if not selected or selected.get('value') is None:
            selected=issuer['facts'].get('sec_yield_30d');basis='OFFICIAL_30_DAY_SEC_YIELD'
        pool.setdefault('canonical_yield_observations',{})[symbol]={'basis':basis,'current':deepcopy(selected),
            'source_reference':issuer['source_reference'],'source_sha256':issuer['source_sha256'],
            'weekly_history_available':False,'percentile_inferred_from_cash_yield':False}
        pool['asset_unprovided_inputs'][symbol]['PRED-008']=[
            'same-definition trailing 5-year weekly '+basis+' history (>=3 years only since inception)']
    return pool


def bind_native(request,source,pool,run):
    """Bind a zero bond-budget order ceiling to this account, never SGOV value.

    A positive budget does not establish an intended order amount. That
    remains unavailable until an original amount producer supplies it.
    """
    if not pool.get('formal_parameters') or not pool.get('issuer_observations'):return
    from pathlib import Path
    from hashlib import sha256
    from family_input import digest
    from v75_runtime.predicates import EVALUATORS
    from v75_runtime.work3 import US_LISTED_ASSETS
    if run.broker_account_id!=request['owner']['account'] or run.currency!=request['owner']['currency']:
        raise PermissionError('V75_QUALITY_ACCOUNT_BINDING')
    budget=run.bond_executable_budget.amount
    amount='0' if budget==0 else None
    order_source=({'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
        'bond_executable_budget':{'amount':str(budget),'currency':run.currency},
        'adapter_request_digest':digest(source['adapter_request']),
        'basis':'ORIGINAL_V75_SAME_ACCOUNT_BOND_BUDGET_ZERO_CEILING',
        'sgov_physical_or_approved_target_used_as_cash':False} if amount is not None else None)
    assessments={}
    for symbol,issuer in pool['issuer_observations'].items():
        if symbol not in source['predicate_observations']:continue
        contract=pool.get('qualified_bond_markets',{}).get(symbol);raw=None
        if contract:
            raw=Path(contract['source_descriptor']['local_path']).read_bytes()
            if sha256(raw).hexdigest()!=contract['source_sha256']:raise PermissionError('V75_QUALITY_MARKET_BYTES_CHANGED')
        assessment=assess(issuer,contract,raw,pool['formal_parameters'],request['evaluation_at'],
            authorized_universe=symbol in US_LISTED_ASSETS,intended_order_amount=amount,order_source=order_source)
        assessments[symbol]=assessment
        result=EVALUATORS['PRED-010'](assessment['metrics'],time(request['evaluation_at']),
            [issuer['source_reference'],issuer['source_sha256'],'ACCOUNT_BOND_INPUT:'+digest(order_source)])
        source['predicate_observations'][symbol]['PRED-010']={
            'metrics':deepcopy(assessment['metrics']),'original_result':result.model_dump(mode='json'),
            'input_coverage':'SOURCE_BOUND_COMPONENT_STATES__RAW_EVIDENCE_PARTIAL' if assessment['unprovided_inputs'] else 'COMPLETE_RAW_METRICS',
            'unprovided_inputs':deepcopy(assessment['unprovided_inputs']),
            'source_pool_digest':digest(pool),'account_quality_assessment_digest':digest(assessment),
            'source_available_at':pool['available_at'],'input_freshness_verified':assessment['input_freshness_verified'],
            'deployment_input_eligible':assessment['input_freshness_verified'] and result.assessment_status.value=='VALID',
            'original_default_freshness_is_not_attestation':True,
            'original_result_as_of_basis':'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE'}
    source['etf_quality_assessments']=assessments
    if pool.get('ready_data_handoff'):
        source['ready_data_evidence']=deepcopy(pool['ready_data_handoff'])
    if pool.get('additional_delta_handoff'):
        source['additional_delta_evidence']=deepcopy(pool['additional_delta_handoff'])
