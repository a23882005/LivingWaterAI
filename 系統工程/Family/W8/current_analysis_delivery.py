"""Deliver available holding analysis independently of deployment readiness.

No new investment rule or transaction is introduced. Values and verdicts are
copied from the bound source producers and original V82 components.
"""
from copy import deepcopy
from family_input import digest
from decimal import Decimal
from approved_v04_technical import both,truth

LABELS={'kd_golden_cross':'KD黃金交叉','macd_bear_hist_shrinking_or_positive':'MACD空方柱縮短／翻正',
    'dif_up':'DIF上彎','rsi_improving_or_near_50':'RSI改善／接近50'}


def deliver(row,request,*,repo_root):
    market=row.get('market') or {};core=(row.get('core_observation') or {}).get('result',{})
    conclusion=row.get('formal_conclusion') or {};approved=market.get('approved_technical') or {}
    metrics=deepcopy(row.get('valuation_observations',[]));valuation=deepcopy(core.get('valuation',{}))
    tech=deepcopy(core.get('technical',market.get('v82_original_aggregation',{})))
    groups=market.get('observed_named_signals',{})
    right_true=[s['name'] for s in groups.get('right_signals',[]) if s['truth']=='TRUE']
    current=next((m for m in metrics if m.get('metric_name')==valuation.get('primary_metric')),None)
    judgment=current_judgment(row,repo_root)
    modes=deepcopy(conclusion.get('four_modes',{}));predicate=conclusion.get('market_predicates',{})
    dependencies={
        'Base':['fundamentals_long_term_viable','credit/safety','higher_priority_mode_resolution'],
        'Left':['fundamentals_long_term_viable','left_safety_negations_absent'],
        'Right':['fundamentals_long_term_viable','credit/safety'],
        'Trend':[] if predicate.get('runaway_up')=='FALSE' else ['applicable_trend_stage_inputs']}
    for name,mode in modes.items():
        state=mode.get('market_predicate',mode.get('selection_predicate','UNKNOWN'))
        mode['unresolved_dependencies']=dependencies[name] if state=='UNKNOWN' else []
    valuation_view={'native_result':valuation,'primary_observation':current,'other_available_observations':metrics,
        'current_analysis_source_acceptance':bool(current and current.get('current_source_accepted')),
        'historical_pit_verified':bool(current and current.get('historical_publication_time_verified')),
        'publication_time_missing_does_not_erase_value':True}
    facts=row.get('issuer_facts') or {}
    structure=deepcopy(conclusion.get('etf_viability_audit',{}))
    # Structural readiness does not delete dated issuer values/composition.
    structure['available_issuer_facts']={k:deepcopy(facts[k]) for k in
        ('as_of','source_url','stock_count','benchmark','top_ten_weight_pct','regions_pct','metrics') if k in facts}
    target=deepcopy(conclusion.get('approved_project_target'))
    policy_status=('NOT_SET_IN_BOUND_APPROVED_SOURCE' if not
        request.get('confirmed_target',{}).get('payload',{}).get('draft',{}).get('etf_constraints',{}).get(row['symbol'])
        else 'SEE_SOURCE_LEAF_RESULTS')
    has_data=bool(market.get('numeric') or metrics or facts)
    result={'schema_version':'Family.W8.CurrentHoldingDelivery.v1',
        'delivery_status':'ANALYSIS_DELIVERED_WITH_LIMITATIONS' if has_data else 'LIMITATION_REPORT_ONLY',
        'analysis_report_delivered':has_data,'native_readiness':row['status'],
        'symbol':row['symbol'],'owner':deepcopy(row['owner']),'holding':deepcopy(row['holding']),
        'classification':deepcopy(row['scenario_class']),'native_product_identity':deepcopy(row['native_product_identity']),
        'current_judgment':judgment,
        'valuation':valuation_view,'market':{k:deepcopy(market.get(k)) for k in
            ('observed_date','observed_close','provider','provider_verified_at','source_path','source_sha256','history_quality')},
        'native_component_observations':deepcopy(market.get('v75_original_predicates',{})),
        'technical':{'native_result':tech,'numeric':deepcopy(market.get('numeric',{})),
            'right_confirmation_signals_true':right_true,'ma20_ok':approved.get('ma20_ok','UNKNOWN'),
            'off_low':approved.get('off_low','UNKNOWN'),'timeframe_observations':deepcopy(approved.get('timeframes',{}))},
        'etf_structure':structure,'four_modes':modes,'formal_mode':conclusion.get('selected_mode','UNKNOWN'),
        'formal_stage':conclusion.get('formal_stage','UNKNOWN'),
        'stage_reasons':conclusion.get('stage_required_unknown_fields',[])+
            (['normal_deployment_mode'] if conclusion.get('selected_mode','UNKNOWN')=='UNKNOWN' else []),
        'approved_target':target,'owner_exposure_policy_status':policy_status,
        'cumulative_target':{'status':'UNKNOWN' if conclusion.get('canonical_target_rate') is None else 'SEE_FORMAL_STAGE',
            'rate':conclusion.get('canonical_target_rate'),'amount':None},
        'nine_stage_reference':deepcopy(conclusion.get('nine_stage_reference',[])),
        'deployment_gap':deepcopy(conclusion.get('deployment_gap',{'status':'NOT_RUN','missing_fields':['product_specific_deployment_inputs']})),
        'buy_permission':deepcopy(conclusion.get('buy_permission',core.get('permission',{}))),
        'execution_amount':{'status':'NOT_CALCULATED','amount':None,
            'reason':'Execution requires original budget, canonical target, FX, order/fill reconciliation and permission',
            'does_not_block':['valuation','technical','dated_issuer_facts','analysis_delivery']},
        'acceptance':{'analysis_report_delivered':has_data,
            'current_judgment_determined':judgment['mode']!='UNKNOWN',
            'formal_mode_determined':conclusion.get('selected_mode','UNKNOWN')!='UNKNOWN',
            'deployment_amount_calculable':conclusion.get('deployment_gap',{}).get('status')=='COMPUTED',
            'full_04_passed':False,'work9_completed':False},
        'source_refs':deepcopy(row['source_refs']),'call_trace':deepcopy(row['call_trace']),
        'trade_authorization':'NONE','trade_action':'NO_TRADE'}
    text=[f"{row['symbol']}｜{row['scenario_class']['name']}；正式來源持股 {row['holding']['quantity']}。",
        f"持倉原始日期：{row['holding']['observed_at'] or '原件未載明'}；行情日期：{market.get('observed_date','無可用來源')}。"]
    if market.get('numeric'):
        n=market['numeric'];text += [f"來源收盤 {market['observed_close']}；MA20 {n.get('ma20')}，RSI14 {n.get('rsi14')}，ATR14 {n.get('atr14')}。"]
    if current:
        text += [f"估值：{current['metric_name']} {current['current']}，資料日 {current.get('as_of')}，原V82判斷 {valuation['level']}。"]
        if current.get('current_source_accepted'):
            text += ['採用總經端已核對發布的近期輸入作當下分析；原始發布時間與有效期未補造，此結果不作歷史已知證據。']
    elif metrics:text += ['估值數值已列出；尚無能合法分級的主指標，未把Trailing PE當Forward PE或套用相同門檻。']
    if tech:
        text += [f"原技術判斷：Right確認 {tech.get('right_confirmation','UNKNOWN')}，Runaway Up {tech.get('runaway_up','UNKNOWN')}，Runaway Down {tech.get('runaway_down','UNKNOWN')}。"]
        if right_true:text += ['右側成立訊號：'+ '、'.join(LABELS.get(k,k) for k in right_true)+'。']
        if market.get('base_facts',{}).get('above_ma20') is False and approved.get('ma20_ok')=='TRUE':
            text += ['收盤仍低於MA20，但符合已批准的1%容差；MA20_OK成立不代表已站回MA20。']
        if approved.get('timeframes'):
            text += ['日／週／月觀測：'+ '／'.join(approved['timeframes'].get(k,{}).get('state','UNKNOWN') for k in ('daily','weekly','monthly'))+'；週月的正式日曆完整性限制另列。']
    if conclusion:
        text += [f"四模式：Base {modes['Base']['selection_predicate']}（Entry {modes['Base']['entry_eligibility']}）；Left {predicate['left']}（價格／估值OR {conclusion['left_inputs']['price_condition_at_least_one']}）；Right {predicate['right']}；Trend {predicate['runaway_up']}。",
            f"正式模式 {result['formal_mode']}／階段 {result['formal_stage']}。估值與技術結果已可用；基本面、信用及必要安全結論不足只限制所依賴的模式成立。",
            f"原安全層買進權限 {result['buy_permission'].get('value')}，原因 {','.join(result['buy_permission'].get('reason_codes',[]))}。"]
    text += ['核准目標及九階參考另列；正式累積目標、部署缺口與可執行金額分開，不以參考表當訂單。',
        '本人目標缺漏、未設曝險限制、掛單／成交不足不刪除本分析；不推定空掛單或新增上限。']
    result['analysis_details']='\n'.join(text)
    concise=[text[0]]
    if market.get('numeric'):
        n=market['numeric'];concise.append(f"{market['observed_date']}收盤 {market['observed_close']:.2f}；MA20 {n.get('ma20')}，RSI14 {n.get('rsi14')}，ATR14 {n.get('atr14')}。")
    if current:concise.append(f"{current['metric_name']} {current['current']}（{current.get('as_of')}），估值 {valuation['level']}。")
    if tech:concise.append(f"右側技術確認 {tech.get('right_confirmation','UNKNOWN')}（{len(right_true)}項成立）；Runaway Up／Down {tech.get('runaway_up','UNKNOWN')}／{tech.get('runaway_down','UNKNOWN')}。")
    if judgment['mode']!='UNKNOWN':
        concise.append(f"當下判斷 {judgment['mode']}；階段參考 {judgment['stage_reference']}（累積比例 {judgment['target_rate_reference']}）。")
        if judgment['target_amount_reference'] is not None:concise.append(f"目標參考 {judgment['currency']} {judgment['target_amount_reference']}；這是配置參考，不是本次訂單金額。")
    elif conclusion:concise.append(f"目前可用資料尚無法選定模式；核准目標 {target.get('currency')} {target.get('amount')}。")
    result['readable_analysis']='\n'.join(concise)
    result['delivery_digest']=digest(result)
    return result


def current_judgment(row,repo_root):
    """Owner-scoped current judgment; source safety is outside this A request.

    The original selector/stage functions are reused. This output never grants
    execution permission or replaces the original complete deployment contract.
    """
    from formal_mode_analysis import native,tri
    if not row.get('core_observation'):
        return {'scope':'PRODUCT_SPECIFIC_COMPONENT_ANALYSIS',
            'mode':'UNKNOWN','stage_reference':'UNKNOWN','target_rate_reference':None,
            'target_amount_reference':None,'currency':None,'formal_deployment_decision':False,
            'execution_authorized':False,'reason_codes':['ORIGINAL_PRODUCT_ROUTE_RETAINED'],'call_trace':[]}
    dep,P,_=native(repo_root)
    core=(row.get('core_observation') or {}).get('result',{})
    tech=core.get('technical') or (row.get('market') or {}).get('v82_original_aggregation',{})
    approved=(row.get('market') or {}).get('approved_technical',{})
    down=tri(tech.get('runaway_down'));not_down=None if down is None else not down
    legal=True if core.get('valuation',{}).get('formal_output_eligible') else None
    right=both(tri(tech.get('right_confirmation')),tri(approved.get('off_low')),legal,not_down)
    c=row.get('formal_conclusion') or {}
    price=tri(c.get('left_inputs',{}).get('price_condition_at_least_one'))
    left=both(price,legal,not_down)
    mode=dep.select_deployment_mode(runaway_up=P(tech.get('runaway_up','UNKNOWN')),
        right_add=P(truth(right)),left_buy_point=P(truth(left)))
    stage=dep.resolve_deployment_stage(mode=mode)
    target=c.get('approved_project_target') or {}
    amount=(str(Decimal(target['amount'])*stage.target_rate) if target.get('value_state')=='KNOWN' and stage.target_rate is not None else None)
    return {'scope':'CURRENT_HOLDINGS_JUDGMENT__OWNER_REQUESTED_EXISTING_PUBLISHED_INPUTS',
        'mode':mode.value,'stage_reference':stage.stage,
        'target_rate_reference':str(stage.target_rate) if stage.target_rate is not None else None,
        'target_amount_reference':amount,'currency':target.get('currency'),
        'formal_deployment_decision':False,'execution_authorized':False,
        'reason_codes':list(stage.reason_codes),
        'call_trace':['V82.select_deployment_mode','V82.resolve_deployment_stage']}
