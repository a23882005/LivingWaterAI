"""Approved V70 evidence -> existing V82 credit and macro consumers.

No new risk thresholds, score-to-safety mapping, calendar or event assertion.
Raw observations and qualified decision operands are reported separately.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
from approved_v04_technical import both, either, cmp, truth
from v10_source_observations import credit_logic


def _time(value):
    out=datetime.fromisoformat(value.replace('Z','+00:00'))
    if out.utcoffset() is None:raise ValueError('V70_DECISION_TIMEZONE_REQUIRED')
    return out


def _number(value):
    if value is None or isinstance(value,bool):return None
    try:
        out=Decimal(str(value));return out if out.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None


def _leaf(name,value):
    return {'value':value,'required':{name},'unknown':{name} if value is None else set()}


def _combine(operator,*nodes):
    result=(both if operator=='AND' else either)(*(n['value'] for n in nodes))
    decisive=False if operator=='AND' else True
    witnesses=[n for n in nodes if n['value'] is decisive]
    used=witnesses[:1] if witnesses else nodes
    return {'value':result,'required':set().union(*(n['required'] for n in used)),
        'unknown':set().union(*(n['unknown'] for n in used)) if result is None else set()}


def _audit(node,rule):
    return {'truth':truth(node['value']),'rule_reference':rule,
        'required_input_ids':sorted(node['required']),
        'decision_relevant_unknown_ids':sorted(node['unknown'])}


def _credit_nodes(values):
    H,V,M,W,T,R,O,D=[_leaf(k,values.get(k)) for k in ('hy_oas','vix','move',
        'hy_rapid_widening','treasury_function_deterioration','repo_function_deterioration',
        'official_systemic_interruption','hy_direction_widening')]
    def test(node,bound,op):return {**node,'value':cmp(node['value'],Decimal(bound),op)}
    c3=_combine('OR',O,_combine('AND',test(H,600,'gt'),W,
        _combine('OR',test(V,35,'gt'),test(M,120,'gt')),_combine('OR',T,R)))
    c2=_combine('OR',_combine('AND',test(H,500,'gt'),W),
        _combine('AND',test(M,120,'gt'),T,R,D))
    c1=_combine('OR',test(H,300,'ge'),test(V,25,'gt'),test(M,120,'gt'),W)
    # Keep the original credit producer as the sole numeric/tri-state arbiter.
    result=credit_logic(values.get('hy_oas'),values.get('vix'),values.get('move'),
        rapid=values.get('hy_rapid_widening'),treasury=values.get('treasury_function_deterioration'),
        repo=values.get('repo_function_deterioration'),official=values.get('official_systemic_interruption'),
        direction_widening=values.get('hy_direction_widening'))
    nodes={'C1':c1,'C2':c2,'C3':c3}
    for key,node in nodes.items():assert result[key]==truth(node['value'])
    # Lower levels cannot affect an already established higher level.
    used=[]
    for key in ('C3','C2','C1'):
        used.append(nodes[key])
        if nodes[key]['value'] is True:break
    result['required_input_ids']=sorted(set().union(*(n['required'] for n in used)))
    result['decision_relevant_unknown_ids']=sorted(set().union(*(n['unknown'] for n in used)))
    result['dependency_audit']={k:_audit(v,'V82 v1.22.2 CMR4.2 '+k) for k,v in nodes.items()}
    return result


def _observation(snapshot,name,evaluation_at):
    row=deepcopy(snapshot['signals'][name]);issues=[];value=_number(row.get('value'))
    if row.get('value') is None:issues.append('MISSING')
    elif value is None and name not in ('fed_policy_bias','liquidity_regime','material_macro_events'):
        issues.append('INVALID_VALUE')
    available=row.get('available_at') or row.get('publication_eligibility_bound')
    if available is None and row.get('published_at') and len(row['published_at'])>10:
        available=row['published_at']
    # A date is not a precise posting instant. Preserve the provider's explicit
    # conservative bound/approximate schedule without changing its precision.
    precision=row.get('publication_time_precision') or (
        'DATE_ONLY' if row.get('published_at') and len(row['published_at'])==10 else
        'PROVIDER_TIMESTAMP' if row.get('published_at') else 'UNKNOWN')
    availability_basis='PROVIDER_AVAILABILITY_OR_PUBLICATION_BOUND'
    if precision=='SCHEDULED_APPROXIMATE':
        # A scheduled release is not a proven posting instant or upper bound.
        # The captured original is known by retrieval, without certifying when
        # it first became public. Keep published_at and its precision intact.
        available=row.get('available_at') or row.get('retrieved_at')
        availability_basis='KNOWN_BY_CAPTURE__NOT_EXACT_PUBLICATION_TIME'
    if available is None:issues.append('PUBLICATION_AVAILABILITY_UNKNOWN')
    elif _time(available)>_time(evaluation_at):issues.append('NOT_YET_AVAILABLE')
    contract=row.get('freshness_contract') or {}
    fresh='UNKNOWN'
    if (contract.get('release_calendar_reference') and contract.get('revision_rule_reference')
        and contract.get('expected_release_id') and contract.get('release_id')
        and contract.get('evaluated_at')==evaluation_at):
        fresh='FRESH' if contract['release_id']==contract['expected_release_id'] else 'STALE'
        if fresh=='STALE':issues.append('STALE')
    else:issues.append('EXPECTED_RELEASE_COVERAGE_UNKNOWN')
    eligible=(row.get('value') is not None and 'INVALID_VALUE' not in issues
        and row.get('data_quality') in ('OK','FALLBACK_USED')
        and bool(row.get('source')) and bool(row.get('method')) and fresh=='FRESH'
        and available is not None and _time(available)<=_time(evaluation_at))
    return {**row,'json_pointer':'/signals/'+name,'snapshot_sha256':snapshot['sha256'],
        'rule_reference':'V82 v1.22.2 CMR3.1 / §37.1 / §38.1 / §62',
        'snapshot_source_reference':snapshot['source_reference'],'available_at_bound':available,
        'availability_basis':availability_basis,
        'availability_precision':precision,'exact_publication_time_verified':precision=='PROVIDER_TIMESTAMP',
        'freshness':fresh,'decision_input_eligible':eligible,'qualification_issue_codes':issues,
        'required_input_ids':[name+'.value',name+'.publication_availability',name+'.expected_release_coverage'],
        'decision_relevant_unknown_ids':([name+'.'+x for x in issues] if not eligible else []),
        'carry_forward_policy':deepcopy(row.get('carry_forward'))}


def _window_series(series, key, expected_url, captured):
    original = series.get(key) or {}
    if original.get('unit') != 'percent' or original.get('source_url') != expected_url:
        return {}, None
    published = original.get('published_as_displayed')
    if key != 'TREASURY_REAL_10Y':
        try:
            stamp, zone = published.rsplit(' ', 1)
            local = datetime.strptime(stamp, '%Y-%m-%d %I:%M %p').replace(tzinfo=ZoneInfo('America/Chicago'))
            if local.tzname() != zone or local > captured:
                return {}, None
        except (AttributeError, ValueError):
            return {}, None
    values = {}
    for day, raw in original.get('observations', []):
        day = date.fromisoformat(day)
        if day in values or values and day <= next(reversed(values)):
            raise ValueError('V70_SOURCE_WINDOW_OBSERVATION_ORDER')
        values[day] = None if raw == '.' else _number(raw)
    return values, published


def _source_difference(values, end, periods, closed_days):
    if end not in values or not values:
        return None
    days = []
    day = end
    earliest = next(iter(values))
    while day >= earliest and len(days) <= periods:
        # A provider may publish a month-end observation on a weekend.
        if day not in closed_days and (day.weekday() < 5 or day in values):
            days.append(day)
        day -= timedelta(days=1)
    if len(days) != periods + 1 or any(values.get(d) is None for d in days):
        return None
    first = days[-1]
    return {'latest_day': end.isoformat(), 'prior_day': first.isoformat(),
            'latest_percent': str(values[end]), 'prior_percent': str(values[first]),
            'difference_bp': str((values[end] - values[first]) * 100)}


def read_source_window(source, snapshot, request):
    if not source or snapshot is None:
        return None
    if (source['client_id'] != request['client_id']
            or source['source_db_sha256'] != request['client_snapshot']['payload']['source_sha256']):
        raise PermissionError('V70_SOURCE_WINDOW_MEMBER_MISMATCH')
    if source['snapshot_sha256'] != snapshot['sha256']:
        return None
    from member_market_source import read_json
    data = read_json(source)
    captured = _time(data['captured_at'])
    evaluated = _time(request['evaluation_at'])
    cutoff = _time(snapshot['data_cutoff'])
    if captured > evaluated or cutoff > evaluated or evaluated.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat() != source['evaluation_day']:
        return None
    series = data['series']
    items = {}
    releases = {}
    for key in ('BAMLH0A0HYM2','DFII10','T5YIE'):
        items[key], releases[key] = _window_series(series,key,'https://fred.stlouisfed.org/data/'+key,min(cutoff,captured))
    treasury_key = 'TREASURY_REAL_10Y'
    treasury_url = ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView'
                    '?type=daily_treasury_real_yield_curve&field_tdr_date_value=' + str(cutoff.year))
    items[treasury_key], releases[treasury_key] = _window_series(series,treasury_key,treasury_url,captured)
    # A cross-published no-observation day on both FRED rate series and the original
    # Treasury curve is outside the rate observation windows. Uncorroborated holes stay unknown.
    closed = {d for d,v in items['T5YIE'].items() if v is None and d in items['DFII10']
              and items['DFII10'][d] is None and d not in items[treasury_key] and items[treasury_key]}
    diffs = {}
    anchors = {}
    def aligned(key, signal, series_id):
        row = snapshot['signals'][signal]
        days = items[key]
        if not days or row.get('series_id') != series_id or row.get('unit') != '%':
            return None
        end = next(reversed(days))
        if (end.isoformat() != row.get('as_of') or end > cutoff.date()
                or days[end] is None or days[end] != _number(row.get('value'))):
            return None
        return end
    hy = aligned('BAMLH0A0HYM2','hy_oas','BAMLH0A0HYM2')
    real = aligned(treasury_key,'real_yield','U.S. Treasury 10-Year Real CMT')
    be = next(reversed(items['T5YIE']), None)
    # The supplement is tied to the latest completed rate session of this V70 capture.
    expected_rate_day = snapshot['signals']['real_yield'].get('as_of')
    if be and (be.isoformat() != expected_rate_day or be > cutoff.date()):
        be = None
    for key, end, periods in [('BAMLH0A0HYM2',hy,(1,5,20)), (treasury_key,real,(20,)), ('T5YIE',be,(20,))]:
        anchors[key] = end.isoformat() if end is not None else None
        diffs[key] = {str(n): _source_difference(items[key],end,n,set() if key=='BAMLH0A0HYM2' else closed)
                      if end is not None else None for n in periods}
    return {'source_sha256':source['sha256'], 'snapshot_sha256':snapshot['sha256'], 'captured_at':data['captured_at'],
            'economic_cutoff':snapshot['data_cutoff'], 'available_for_this_run_at':data['captured_at'],
            'source_urls':{k:s.get('source_url') for k,s in series.items()}, 'provider_release_as_displayed':releases,
            'anchors':anchors, 'differences':diffs, 'hy_bp':str(items['BAMLH0A0HYM2'][hy]*100) if hy else None,
            'corroborated_non_observation_days':sorted(str(d) for d in closed),
            'scope':'CURRENT_CAPTURE_ONLY__NO_HISTORICAL_PUBLICATION_TIME_INFERRED'}


def _window_test(window, series, length, threshold, operator):
    item = ((window or {}).get('differences', {}).get(series) or {}).get(str(length))
    return cmp(_number(item['difference_bp']) if item else None, Decimal(threshold), operator)


def produce(snapshot,evaluation_at,window=None):
    observed={k:_observation(snapshot,k,evaluation_at) for k in snapshot['signals']}
    raw_values={};qualified={}
    for name,units in [('hy_oas',('%','bp')),('vix',('index points','index_points')),('move',('index points','index_points'))]:
        row=observed[name];value=_number(row['value'])
        if row.get('unit') not in units:value=None
        if name=='hy_oas' and row.get('unit')=='%':value=value*100 if value is not None else None
        raw_values[name]=value;qualified[name]=value if row['decision_input_eligible'] else None
    # Existing v2 signals do not contain the formal 5/20-session source window,
    # Treasury spread/depth basket, comparable repo corridor or event assertion.
    # Keep each missing producer separate; SOFR/RRP/SRF values do not prove R.
    missing_producers={
        'hy_rapid_widening':'HY comparable 5/20 completed source-session observations; CMR3.2',
        'hy_direction_widening':'Same-series comparable prior HY observation; CMR3.2',
        'treasury_function_deterioration':'Registered Treasury spread/depth basket 3/60 sessions; CMR4.2',
        'repo_function_deterioration':'Two source business days and comparable official corridor; CMR4.2',
        'official_systemic_interruption':'Applicable official systemic assertion and event coverage; CMR4.2 / CMR5'}
    for name in missing_producers:raw_values[name]=qualified[name]=None
    if window:
        if window['snapshot_sha256'] != snapshot['sha256'] or _time(window['captured_at']) > _time(evaluation_at):
            raise PermissionError('V70_SOURCE_WINDOW_SNAPSHOT_OR_TIME')
        fresh = {'hy_rapid_widening':either(_window_test(window,'BAMLH0A0HYM2',5,50,'ge'),
                                            _window_test(window,'BAMLH0A0HYM2',20,100,'ge')),
                 'hy_direction_widening':_window_test(window,'BAMLH0A0HYM2',1,0,'gt')}
        if window.get('hy_bp') is not None:
            fresh['hy_oas'] = _number(window['hy_bp'])
        qualified.update(fresh)
        raw_values.update(fresh)
    credit=_credit_nodes(qualified);numeric_credit=_credit_nodes(raw_values)
    # Macro pressure is the existing CMR3.2 OR/AND, not a generic score band.
    inflation=_leaf('inflation_chain_accelerating',None)
    real=_leaf('real_yield_rising_fast',_window_test(window,'TREASURY_REAL_10Y',20,50,'ge'))
    if window:
        inflation = _combine('AND', _leaf('ppi_yoy_accelerating',None), _leaf('core_cpi_yoy_accelerating',None),
                             _leaf('core_pce_yoy_accelerating',None),
                             _leaf('breakeven_5y_20_session_up_25bp',_window_test(window,'T5YIE',20,25,'ge')))
    bias_row=observed['fed_policy_bias']
    bias=(bias_row['value'] if bias_row['decision_input_eligible'] and bias_row['value'] in ('HAWKISH','DOVISH','NEUTRAL') else None)
    hawkish=_leaf('policy_bias',None if bias is None else bias=='HAWKISH')
    pressure=_combine('OR',inflation,_combine('AND',real,hawkish))
    macro=_audit(pressure,'V82 v1.22.2 CMR3.2 / CMR8')
    macro['missing_dependencies']={
        'inflation_chain_accelerating':'Comparable PPI/Core CPI/Core PCE prior releases and 5Y breakeven 20-session change',
        'real_yield_rising_fast':'Comparable real-yield 20 completed source-session change',
        'policy_bias':'Qualified adopted V70 policy-bias classification'}
    if window:
        descriptions = {'ppi_yoy_accelerating':'Comparable previous PPI year-on-year release',
            'core_cpi_yoy_accelerating':'Comparable previous Core CPI year-on-year release',
            'core_pce_yoy_accelerating':'Comparable previous Core PCE year-on-year release',
            'breakeven_5y_20_session_up_25bp':'Complete 5Y breakeven published observation window'}
        descriptions.update(macro['missing_dependencies'])
        macro['missing_dependencies'] = {k:descriptions[k] for k in macro['decision_relevant_unknown_ids']}
    if window:
        cooling = _combine('AND', _leaf('ppi_yoy_cooling',None), _leaf('core_cpi_yoy_cooling',None),
                           _leaf('core_pce_yoy_cooling',None),
                           _leaf('breakeven_5y_20_session_down_25bp',_window_test(window,'T5YIE',20,-25,'le')))
        macro['published_window_audit'] = {'acceleration': _audit(inflation,'V82 CMR3.2'),
            'cooling': _audit(cooling,'V82 CMR3.2'),
            'real_yield_falling_fast':truth(_window_test(window,'TREASURY_REAL_10Y',20,-50,'le'))}
    unknown=credit['decision_relevant_unknown_ids']
    reasons={k:missing_producers.get(k,'Current value publication availability / expected-release qualification missing') for k in unknown}
    return {'schema_version':'Family.W8.V70SafetyDecisions.v1','source_sha256':snapshot['sha256'],
        'source_reference':snapshot['source_reference'],'evaluated_at':evaluation_at,
        'observed':observed,'credit':credit,'observational_credit':numeric_credit,
        'macro_pressure':macro,'macro_pressure_inputs':{'inflation_chain_accelerating':inflation['value'],
            'real_yield_rising_fast':real['value'],'policy_bias':bias},
        **({'published_source_window':window,'credit_window_inputs':{k:truth(qualified[k]) for k in ('hy_direction_widening','hy_rapid_widening')}} if window else {}),
        'remaining_dependencies':reasons,'raw_unknown_signal_ids':list(snapshot['unknown_signals']),
        'core_safety_dependencies':{
            'safety.macro':{'required_input_ids':macro['required_input_ids'],
                'decision_relevant_unknown_ids':macro['decision_relevant_unknown_ids'],
                'reason':'MACRO_SAFETY_AGGREGATION_NOT_ASSERTED; '+ '; '.join(macro['missing_dependencies'].values())},
            'safety.credit_liquidity':{'required_input_ids':credit['required_input_ids'],
                'decision_relevant_unknown_ids':unknown,'reason':'; '.join(k+': '+v for k,v in reasons.items())}},
        'call_trace':['W8.v70_safety_decisions.produce','W8.v10_source_observations.credit_logic'],
        'full_safety_contract_complete':False,'score_used_as_safety':False}


def bind_core(arguments,gaps,projection):
    """Bind source-specific UNKNOWN to the original sufficiency arbiter.

    Independent qualified Core-source assertions retain their original owner;
    this partial snapshot cannot erase them or claim their qualification.
    """
    from livingwater_v82_runtime.core_rules import EvidenceFact
    from livingwater_v82_runtime.enums import RequirementLevel,DataQuality,Freshness,PitStatus
    owned=projection['core_safety_dependencies'];result=[];bound=set()
    for fact in arguments['safety_facts']:
        if fact.name not in owned or fact.data_quality not in (DataQuality.UNKNOWN,DataQuality.INSUFFICIENT):
            result.append(fact);continue
        dep=owned[fact.name];bound.add(fact.name)
        result.append(EvidenceFact(name=fact.name,value='UNKNOWN',requirement=RequirementLevel.SAFETY_REQUIRED,
            data_quality=DataQuality.UNKNOWN,freshness=Freshness.UNKNOWN,pit_status=PitStatus.UNVERIFIABLE,
            source_reference=projection['source_reference']+'#'+projection['source_sha256'],
            issue_codes=tuple(dep['decision_relevant_unknown_ids']) or ('METHODOLOGY_UNAVAILABLE',)))
    arguments['safety_facts']=result
    for gap in gaps:
        if gap['field_path'] in bound:
            dep=owned[gap['field_path']]
            gap.update(reason=dep['reason'],required_input_ids=dep['required_input_ids'],
                decision_relevant_unknown_ids=dep['decision_relevant_unknown_ids'],source_sha256=projection['source_sha256'])
    return arguments,gaps
