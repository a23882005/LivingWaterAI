"""A-flow requirement audit from the unchanged formal 49-field registry.

Native requiredness is preserved. B-only fields are outside this requested
flow, not relabelled inapplicable. Soft fields follow dependency propagation.
"""
from formal_analysis_signals import verify_rules

A_FIELDS=set(range(1,35))|{37}
OUTCOME_FIELDS={'latest_price','market_data_as_of','asset_behavior_classification','primary_framework',
    'fundamental_state','valuation_state','price_map','left_buy_point_state','right_confirmation_state',
    'runaway_state','daily_timeframe_state','weekly_timeframe_state','monthly_timeframe_state',
    'macro_state','credit_liquidity_state','material_news_policy_state','exposure_overlap','confirmed_position'}


def registry(source):
    text=verify_rules(source);rows=[]
    for line in text.splitlines():
        cells=[c.strip().strip('`') for c in line.strip().strip('|').split('|')]
        if len(cells)>=8 and cells[0].isdigit() and cells[1].replace('_','').isalnum() and cells[5] in ('Required','Optional'):
            n=int(cells[0])
            if 1<=n<=49:rows.append({'ordinal':n,'field':cells[1],'native_requirement':cells[5],
                'nullable':cells[6],'source_policy':cells[7]})
    by={r['ordinal']:r for r in rows}
    if set(by)!=set(range(1,50)):raise ValueError('FORMAL_ANALYSIS_REGISTRY_INCOMPLETE')
    return [by[n] for n in range(1,50)]


def audit(row,source):
    obs=row.get('market') or {};core=(row.get('core_observation') or {}).get('result',{})
    formal=obs.get('formal_analysis_signals',{});known={
        'latest_price':obs.get('observed_close') if obs.get('formal_identity_verified') else None,
        'market_data_as_of':obs.get('session_assessment',{}).get('verified_close_at'),
        'asset_behavior_classification':row['scenario_class'].get('formal_v82_class'),
        'primary_framework':row.get('primary_framework'),
        'confirmed_position':row['holding']['quantity'] if row['holding']['quantity_state']=='KNOWN' else None,
        'fundamental_state':core.get('fundamentals',{}).get('context'),
        'valuation_state':core.get('valuation',{}).get('level'),
        'right_confirmation_state':core.get('technical',obs.get('v82_original_aggregation',{})).get('right_confirmation'),
        'runaway_state':{k:v for k,v in core.get('technical',obs.get('v82_original_aggregation',{})).items()
            if k in ('runaway_up','runaway_down')},
        'td9_high_state':obs.get('td9',{}).get('high_count'),
        'td9_low_state':obs.get('td9',{}).get('low_count'),
        'macd_state':formal.get('macd'),'ma_state':formal.get('ma_price_relationships'),
        'rsi_state':formal.get('rsi'),'atr_value':obs.get('numeric',{}).get('atr14')}
    conclusion=row.get('formal_conclusion') or {}
    if conclusion.get('etf_viability_audit'):
        known['fundamental_state']={'scope':'ETF_VIABLE_01',
            'long_term_viable':conclusion['etf_viability_audit']['result']}
        known['left_buy_point_state']=conclusion['market_predicates']['left']
    for n in (1,2,3):
        lows=obs.get('swings',{}).get('lows',[])
        if len(lows)>=n:known['previous_swing_low_'+str(n)]=lows[-n]['value']
    approved=obs.get('approved_technical',{})
    if approved:
        nums=approved['numeric_decimal']
        known['kd_state']={k:nums.get(k) for k in ('kd_k','kd_d')}
        known['emv_state']=nums.get('emv_3_3')
        # Computable daily observation is independent of missing calendar
        # coverage. Weekly/monthly formal states retain the calendar gap.
        known['daily_timeframe_state']=approved['timeframes']['daily']['state']
    def resolved(value):
        if value is None or value=='UNKNOWN' or value=={}:return False
        if isinstance(value,dict):return all(resolved(x) for x in value.values())
        return True
    entries=[]
    for original in registry(source):
        field=original['field'];in_scope=original['ordinal'] in A_FIELDS
        level=('OUTSIDE_REQUESTED_FLOW_B_ONLY' if not in_scope else 'OPTIONAL'
            if original['native_requirement']=='Optional' else 'MODULE_REQUIRED')
        value=known.get(field);ready=resolved(value)
        entry={**original,'a_requirement_level':level,'global_outcome_required':
            in_scope and field in OUTCOME_FIELDS,'status':('OUTSIDE_REQUESTED_FLOW' if not in_scope else
            'RESOLVED' if ready else 'OPTIONAL_UNAVAILABLE' if level=='OPTIONAL' else 'UNRESOLVED'),
            'value':value,'sot_section':'V82 §65-B; §62-D/F/M; Owner A/B scope amendment',
            'blocks_independent_modules':False}
        if field=='confirmed_position':entry['basis']='OWNER_ACCEPTED_EXISTING_BASELINE__NOT_CURRENT_RECONCILIATION'
        if in_scope and not ready:
            cause={
                'latest_price':('SOURCE_ATTESTATION_MISSING','Provider Close is calculated; exchange/currency/price-basis attestation is not complete'),
                'market_data_as_of':('SOURCE_ATTESTATION_MISSING','Session date is known; verified timezone-aware final-close receipt is absent'),
                'valuation_state':('SOURCE_CONTRACT_MISSING','See per-candidate valuation_path_audit; own historical scale/freshness/PIT are unverified'),
                'fundamental_state':('SOURCE_CONTRACT_MISSING','Issuer levels are mapped; comparable-period direction is unverified'),
                'daily_timeframe_state':('PRODUCER_NOT_CONNECTED','Daily numeric/signals exist; formal timeframe-state producer is not connected'),
                'weekly_timeframe_state':('PRODUCER_NOT_CONNECTED','Completed-week aggregation and formal state producer are not connected'),
                'monthly_timeframe_state':('PRODUCER_NOT_CONNECTED','Completed-month aggregation and formal state producer are not connected'),
                'price_map':('DEPENDENCY_UNRESOLVED','Formal valuation and source-attested price/context inputs are unresolved'),
                'left_buy_point_state':('DEPENDENCY_UNRESOLVED','Formal price-map and safety predicate inputs are unresolved'),
                'right_confirmation_state':('DEPENDENCY_UNRESOLVED','See each named right signal; original threshold_truth cannot determine the threshold'),
                'runaway_state':('DEPENDENCY_UNRESOLVED','Each Up/Down value is retained; see unresolved named predicates and ma20_ok'),
                'macro_state':('PRODUCER_NOT_CONNECTED','Raw V70 feed is available; verified V82 level/direction/speed contract is not produced'),
                'credit_liquidity_state':('PRODUCER_NOT_CONNECTED','Existing raw observations do not yet produce the complete V82 safety contract'),
                'material_news_policy_state':('SOURCE_CONTRACT_MISSING','Same-run required-domain event coverage/checkpoint is not bound'),
                'exposure_overlap':('PRODUCER_NOT_CONNECTED','Issuer holdings facts are not mapped into the original look-through exposure contract')
            }.get(field,('DEPENDENCY_UNRESOLVED','Dependent original source or mapping is unresolved'))
            entry.update(gap_kind=cause[0],reason=cause[1],
                program_location='W8.holdings_analysis.build_analysis_report / W8.analysis_requirements.audit')
            if conclusion.get('etf_viability_audit') and field=='fundamental_state':
                entry.update(gap_kind='SOURCE_FACTS_MISSING',
                    reason='ETF_VIABLE_01 leaf algorithms executed; exact current-source gaps are retained per leaf',
                    source_observation=conclusion['etf_viability_audit'])
            if approved and field in ('weekly_timeframe_state','monthly_timeframe_state'):
                timeframe=field.split('_')[0]
                entry.update(gap_kind='SOURCE_SESSION_COVERAGE_UNVERIFIED',
                    reason='Approved classifier is computed in approved_technical.timeframes.'+timeframe+
                        '; official calendar/session completeness is not verified',
                    numeric_observation=approved['timeframes'][timeframe])
            if row.get('macro_observations') and field in ('macro_state','credit_liquidity_state'):
                entry.update(gap_kind='SOURCE_CONTRACT_MISSING',
                    reason='V1.0 V70 band/credit logic is computed; comparable prior/session history and official event coverage remain missing',
                    numeric_observation=row['macro_observations']['credit'])
        entries.append(entry)
    required=[r for r in entries if r['global_outcome_required'] and r['status']!='RESOLVED']
    inapplicable=[]
    if row['native_product_identity']['asset_type']=='BROAD_ETF':
        inapplicable.append({'field':'company_thesis_failure_score','requirement':'INAPPLICABLE',
            'basis':'V82 Work4 applicability / broad ETF exclusion; ETF structure safety remains required'})
    return {'schema_version':'Family.W8.AnalysisRequirements.v1','entries':entries,
        'required_missing':[r['field'] for r in required],
        'optional_unavailable':[r['field'] for r in entries if r['status']=='OPTIONAL_UNAVAILABLE'],
        'inapplicable':inapplicable,'complete':not required,
        'native_registry_modified':False,'full_native_canonical_complete':False}
