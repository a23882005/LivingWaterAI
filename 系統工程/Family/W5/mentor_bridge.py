"""Read-only Traditional Chinese presentation of native Work9 source facts.

Work9 owns priorities and actions. W2's frozen reason catalog owns translations.
The trusted dispatcher supplies scope and result digest after authorization.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from runtime_loader import load_c_module

CATALOG_SHA256='2c19102d99d21824516069b9dd2db906776caf97d4c9b90b3d740e1b960368f7'


class MentorError(ValueError):
    pass


def distribution_source_text(symbol,distribution):
    text='已核對'+symbol+' '+str(distribution['periods'])+'次配息'
    partial=distribution.get('partial_components')
    if partial:
        return (text+'；其中'+str(partial['component_verified_payment_count'])+'次已對上正式稅表，合計每股 '+
            distribution['currency']+' '+partial['component_verified_distribution_per_share']+
            '、已知子集ROC '+partial['known_ROC_per_share']+'；其餘'+
            str(partial['total_payment_count']-partial['component_verified_payment_count'])+'次、每股 '+
            distribution['currency']+' '+partial['unknown_component_distribution_per_share']+
            '的成分仍未知，整體近12次ROC維持未知。')
    if distribution.get('complete_source_breakdown'):
        total=distribution.get('as_reported_total_distribution')
        income=distribution.get('as_reported_income_sum')
        if total is not None:text+='；每股總額 '+distribution.get('currency','USD')+' '+total
        if income is not None:text+='、收益 '+distribution.get('currency','USD')+' '+income
        text+='；發行商列示ROC '+str(distribution['as_reported_roc_pct'])+'%。'
        if distribution.get('provisional_issuer_components'):
            text+='2026稅務性質仍屬暫定，並非年度最終稅表。'
        return text
    return text+'金額；既有年度稅務分解與缺漏分列，未把缺少的ROC補0。'


def ready_data_evidence_notes(evidence,symbol,additional_delta=None,ib_qa=None):
    if not evidence:return []
    if symbol=='SGOV':
        coverage=evidence['bounded_event_coverage']
        notes=[];types={event['type'] for event in coverage['events']}
        if 'adopted_underlying_index_cash_flow_reinvestment_change' in types:
            notes.append('SGOV指數現金處理已於2025/10/31再平衡後改採 ICE US 1-Month Treasury Bill Index 收益累積；重大性及內部核准狀態另列未裁定，未自動新增買進禁令。')
        notes.append('SGOV事件查核範圍：'+coverage['review_period_start']+'至'+coverage['review_period_end']+
            '，'+str(coverage['filings_retrieved'])+'份 exact-form 497主文件查核索引；'+
            str(coverage['locally_retained_matched_primary_documents'])+'份相關公告原文已核對。未涵蓋所有SEC表單與未具名Trust影響。')
        if 'primary_listing_venue_change' in types:
            notes.append('另保留2026/01/16交易場所變更公告，公告預定於2026/02/23前後改掛NYSE。')
        return notes
    if symbol=='SPSB':
        history=(ib_qa or additional_delta or evidence)['sparse_yield_evidence'];counts=history['counts_by_metric']
        return ['SPSB另有'+str(counts.get('portfolio_ytm',0))+'筆組合YTM及'+str(counts.get('sec_yield_30day',0))+
            '筆30-Day SEC Yield存檔來源核對；各自保留資料日期，未冒充五年完整週序列，未補值或計算百分位。',
            'SPSB配息金額與QII預扣稅分類分列；QII不是ROC，未以100%減QII推算ROC。']
    return []


def official_reply_notes(status):
    if not status:return []
    return ['State Street已回覆無法提供本次要求的資料，本次詢問已結案，不再等待資料交付；沒有附件或付費方案。',
        'IB正式工單由本人送出，尚待答覆；目前未提供工單編號或客服答案，較早外掛回饋另列。']


def plugin_evidence_notes(evidence,symbol,ib_qa=None):
    if not evidence or symbol not in evidence['ibkr_weekly']:return []
    weekly=evidence['ibkr_weekly'][symbol];daily=evidence['massive_daily'][symbol]
    alpha=evidence['alpha_dividends'][symbol]
    notes=[symbol+'外掛交叉核對：IB '+str(weekly['raw_bar_count'])+'根週線、'+
        str(weekly['dividend_count'])+'筆配息事件；Massive '+str(daily['raw_bar_count'])+
        '根日線；Alpha Vantage '+str(alpha['row_count'])+'筆歷史配息。價格與配息分別核對，保留發行商主來源。']
    historical=[r for r in weekly['multiple_bars_per_iso_week'] if not r['latest_week']]
    notes.append('IB最新週尚未完成；'+('另有'+str(len(historical))+'個歷史週含多根標記，先保留查核；' if historical else '')+
        '完整且唯一的週資料共'+str(weekly['usable_unique_completed_weeks'])+'週。')
    if weekly['invalid_ohlcv_bars']:
        notes.append('另有'+str(len(weekly['invalid_ohlcv_bars']))+'根IB週線的OHLC不一致，保留原值並排除於完整週核對。')
    differences=evidence['issuer_dividend_comparisons'][symbol]['alpha']['differences']
    for row in differences:
        if row['field']=='amount':
            notes.append(symbol+' '+row['ex_date']+' Alpha配息與發行商差額為每股US$'+row['difference']+
                '；維持發行商原值US$'+row['issuer']+'。')
    if any(r['field']=='payment_date' for r in differences):
        notes.append(symbol+'第三方付款日缺漏／差異已另列，未改寫發行商付款日。')
    ambiguous=evidence['issuer_dividend_comparisons'][symbol]['ibkr']['ambiguous_provider_events']
    if ambiguous:
        notes.append(symbol+'另有'+str(len(ambiguous))+'個歷史除息日含多筆IB現金事件，金額分列，待來源定義核對。')
    if ib_qa:
        qa=ib_qa['ibkr_audit'][symbol];extended=ib_qa['massive_daily'][symbol]
        notes.append(symbol+'追加查核：IB日線共'+str(qa['daily_raw_bar_count'])+'根，其中'+
            str(len(qa['invalid_daily_bars']))+'根OHLC邊界異常，維持隔離，未修改high或close。')
        if qa['invalid_weekly_bars_reproduced']:
            notes.append(symbol+' '+str(len(qa['invalid_weekly_bars_reproduced']))+
                '根異常週線在原始回應與重抓資料中重現；已確認不是CSV轉檔造成，連接器後端根因尚未確定。')
        notes.append(symbol+' Massive追加日線共'+str(extended['raw_bar_count'])+'根，實際'+
            extended['first_session_date']+'至'+extended['last_session_date']+'；已對上原'+
            str(extended['previous_daily_bars_reconciled'])+'根，並非五年完整序列。拆股調整與配息再投資分開，成交量及時段口徑未擅自等同IB。')
        if extended['missing_session_dates_within_actual_range']:
            notes.append(symbol+' Massive實際區間仍缺'+str(len(extended['missing_session_dates_within_actual_range']))+'個交易日，未補造。')
        if symbol=='SPSB':
            derived=ib_qa['SPSB_derived_week']
            notes.append('SPSB '+derived['week_start']+'週已用完整日線衍生彙總，O'+str(derived['open'])+
                '／H'+str(derived['high'])+'／L'+str(derived['low'])+'／C'+str(derived['close'])+
                '／V'+str(derived['volume'])+'；不是IB官方修正版，原兩筆週列保留。')
    return notes


def explain_native(repo_path,work9_request,unified,*,trusted_context,llm_suggested_changes=(),bond_context=None):
    if llm_suggested_changes:raise MentorError('MODEL_FINANCIAL_MUTATION_REJECTED')
    req=deepcopy(work9_request);original=deepcopy(unified);context=deepcopy(trusted_context)
    if context.get('analysis_permission')!='ANALYZE_ONLY' or context.get('trade_authorization')!='NONE':
        raise MentorError('ANALYSIS_PERMISSION_REQUIRED')
    if context.get('runtime_mode')!='REAL_DETERMINISTIC':
        raise MentorError('REAL_RUNTIME_REQUIRED')
    if context.get('data_provenance') not in ('SYNTHETIC','SOURCE_BACKED'):
        raise MentorError('DATA_PROVENANCE_REQUIRED')
    if not isinstance(context.get('client_id'),str) or not context['client_id'].strip():
        raise MentorError('CLIENT_REQUIRED')
    for key in ('run_id','owner','currency'):
        if context.get(key)!=original.get(key):raise MentorError('CONTEXT_MISMATCH:'+key)
    native=load_c_module(repo_path,9)
    if context.get('expected_result_digest')!=native._digest(original):
        raise MentorError('RESULT_DIGEST_MISMATCH')
    # Reuse Work9 validation/normalization of the exact original source outputs.
    # This does not run a strategy or recompute an investment decision.
    rebuilt=native.build_unified_deployment(req)
    if native._digest(rebuilt)!=native._digest(original):
        raise MentorError('NATIVE_SOURCE_RESULT_MISMATCH')
    bond_facts=deepcopy(bond_context)
    if bond_facts is not None:
        if context.get('expected_bond_context_digest')!=native._digest(bond_facts):
            raise MentorError('BOND_CONTEXT_DIGEST_MISMATCH')
        for key in ('client_id','run_id','owner','currency'):
            if bond_facts.get(key)!=context.get(key):raise MentorError('BOND_CONTEXT_SCOPE_MISMATCH:'+key)
        assets={item['asset_id'] for item in original['canonical_deployment_result']['items']
                if item['source_engine']=='V75' and item.get('asset_id') is not None}
        if assets!=set(bond_facts['items']):raise MentorError('BOND_CONTEXT_COVERAGE_MISMATCH')
    elif context.get('expected_bond_context_digest') is not None:
        raise MentorError('BOND_CONTEXT_REQUIRED')
    catalog_bytes=(Path(__file__).parent/'reason_catalog.json').read_bytes()
    if hashlib.sha256(catalog_bytes).hexdigest()!=CATALOG_SHA256:
        raise MentorError('REASON_CATALOG_INTEGRITY')
    catalog=json.loads(catalog_bytes)['translations']
    rows=[];unknown=[]
    for item in original['canonical_deployment_result']['items']:
        reasons=[]
        for code in item['reason_codes']:
            known=code in catalog
            reasons.append({'code':code,'status':'EXPLAINED' if known else 'PENDING_EXPLANATION',
                'text':catalog[code] if known else '此代碼待對照正式說明；保留原代碼供檢視。'})
            if not known and code not in unknown:unknown.append(code)
        row={'item_id':item['item_id'],'source_facts':deepcopy(item),'reason_explanations':reasons,
             'summary':'原引擎動作與統一動作依來源分欄呈現。'}
        if item['source_engine']=='V82':
            raw=req['work4_v82_integration_result']['canonical_v82_output']
            row['field_evidence']=deepcopy(raw['canonical_analysis'])
            row['data_as_of']=deepcopy(raw['data_as_of'])
            row['evaluated_at']=raw['evaluated_at']
            row['risk_signal']=deepcopy(item['source_decision']['risk_signal_visibility'])
            row['client_action']=deepcopy(item['client_preference_action'])
            if item['client_preference_action']=='HOLD_PROTECTED':
                row['summary']='持倉保護後客戶動作為 HOLD_PROTECTED；請同時檢視原引擎風險訊號。'
        else:
            source=req['work5_v75_integration_result']
            # Keep the entire native binding, including source-owned timestamps.
            row['field_evidence']=deepcopy(source)
            row['client_action']=deepcopy(item['client_preference_action'])
            row['risk_signal']=deepcopy(item['source_action'])
            if bond_facts is not None:
                facts=bond_facts['items'][item['asset_id']]
                amount=item['deployment_amount']
                if facts['new_buy_candidate'] is False and (
                        amount.get('status')!='KNOWN' or
                        Decimal(str(amount['value']['amount']))!=0):
                    raise MentorError('BOND_PERMISSION_DEPLOYMENT_MISMATCH')
                row['family_policy_context']=deepcopy(facts)
                row['c7_client_action']=facts['c7_drift']['client_facing_action']
                row['client_action_resolution']=facts['client_action_resolution']
                row['summary']='原生風險、部署金額、家人政策與 C7 客戶動作分欄保留；跨引擎客戶動作待接口確認。'
        # Advice is the purpose of menu 04. NO_TRADE prohibits submission;
        # it does not suppress a native recommended amount or proportion.
        amount=deepcopy(item['deployment_amount']);ratio=deepcopy(item['deployment_ratio'])
        row['recommendation']={'action':item['canonical_action'],
            'client_preference_action':deepcopy(item['client_preference_action']),
            'amount':amount,'ratio':ratio,'source':'ORIGINAL_WORK9_CANONICAL_ITEM',
            'broker_submission_allowed':False}
        value=amount.get('value')
        amount_text=(str(value['amount'])+' '+value['currency'] if amount.get('status')=='KNOWN'
            else '金額未定' if amount.get('status')=='UNKNOWN' else '金額不適用')
        ratio_value=ratio.get('value')
        ratio_text=(str(ratio_value['value'])+'%' if ratio.get('status')=='KNOWN' else
            '比例未定' if ratio.get('status')=='UNKNOWN' else '比例不適用')
        row['recommendation_explanation']=f"{item['asset_id']}：原引擎建議 {item['canonical_action']}；{amount_text}，目標比例 {ratio_text}。"
        rows.append(row)
    return {'contract_name':'Family.W5.mentor.v1','language':'zh-Hant',
        'status':'EXPLAINED_WITH_PENDING_CODES' if unknown else 'EXPLAINED',
        'client_id':context['client_id'],'run_id':original['run_id'],'owner':deepcopy(original['owner']),
        'currency':original['currency'],'runtime_mode':context['runtime_mode'],
        'data_provenance':context['data_provenance'],'mentor_return':deepcopy(original['mentor_return']),
        'canonical_deployment_result':deepcopy(original['canonical_deployment_result']),
        'canonical_deployment_result_sha256':original['canonical_deployment_result_sha256'],
        'source_result_digest':native._digest(original),'source_bindings':deepcopy(original['source_bindings']),
        'items':rows,'unknown_reason_codes':unknown,'reason_catalog_sha256':CATALOG_SHA256,
        'production':'HOLD','trade_action':'NO_TRADE','execution_advice_allowed':True,'recommendations_allowed':True,'broker_execution_allowed':False}


def explain_holdings_recommendations(repo_path,work9_request,work9_result,*,trusted_context,llm_suggested_changes=()):
    """Explain the actual scoped Work9 return, retaining unresolved amounts."""
    if llm_suggested_changes:raise MentorError('MODEL_FINANCIAL_MUTATION_REJECTED')
    ctx=deepcopy(trusted_context);source=deepcopy(work9_result)
    if ctx.get('analysis_permission')!='ANALYZE_ONLY' or ctx.get('trade_authorization')!='NONE':
        raise MentorError('ANALYSIS_PERMISSION_REQUIRED')
    for key in ('client_id','run_id','owner','source_db_sha256'):
        if ctx.get(key)!=source.get(key):raise MentorError('CONTEXT_MISMATCH:'+key)
    native=load_c_module(repo_path,9)
    if ctx.get('expected_result_digest')!=native._digest(source):raise MentorError('RESULT_DIGEST_MISMATCH')
    rebuilt=native.build_holdings_recommendation_return(deepcopy(work9_request))
    if native._digest(rebuilt)!=native._digest(source):raise MentorError('NATIVE_SOURCE_RESULT_MISMATCH')
    rows=[]
    for item in source['items']:
        facts=item['native_component_delivery'];market=facts.get('market',{})
        valuation=facts.get('valuation',{}).get('native_result',{});tech=facts.get('technical',{}).get('native_result',{})
        target=item['cumulative_target_amount'];ratio=item['target_ratio']
        text=[f"{item['asset_id']}：來源持股 {facts['holding']['quantity']}；行情日期 {market.get('observed_date') or '未取得'}。"]
        if valuation:text.append(f"原生估值 {valuation.get('level','UNKNOWN')}。")
        if tech:text.append(f"原生技術：Right {tech.get('right_confirmation','UNKNOWN')}；Runaway Up／Down {tech.get('runaway_up','UNKNOWN')}／{tech.get('runaway_down','UNKNOWN')}。")
        if ratio['status']=='KNOWN':
            text.append(f"當下模式 {item['mode']}，{item['stage']}，累積目標比例 {Decimal(str(ratio['value']))*100}%。")
            if target['amount'] is not None:text.append(f"目標金額 {target['currency']} {target['amount']}。")
            else:text.append('Loop2逐檔長期目標尚未產製／綁定；這是程式接線待辦，不要求本人填比例。')
        else:text.append('原生資料尚無法選定模式及目標比例；保留已計算的個別訊號。')
        tactical=facts.get('v70_tactical_budget')
        if tactical:text.append(f"原V70重算股票戰術總額度 {tactical['allocation']['sTot']}%，{tactical['currency']} {tactical['amounts']['stock']}；這是總額度，並非本檔補倉金額。")
        component=facts.get('recommendation',{}).get('confirmed_holdings_component')
        if component:
            order_note='本人已確認無掛單；當輪階段參考' if facts['recommendation'].get('order_source',{}).get('status')=='VERIFIED' else '尚未扣除有效掛單'
            text.append(f"按已確認持股計算的缺口 {facts['recommendation']['position_currency']} {component['positive_gap_amount']}（{order_note}）。")
        if facts.get('recommendation',{}).get('approved_no_new_buy'):
            text.append('原C依既有完整核准配置算出長期目標0%，因此此配置基準不新增；不是重新最佳化的提案，也不代表必須立即賣出。' if facts['recommendation'].get('approved_no_new_buy_source',{}).get('basis')=='ORIGINAL_C6_COMPLETE_APPROVED_TARGET_LOOKUP' else '本人正式長期目標明訂0%，因此不新增；這是既有核准配置政策，不等於必須立即賣出，賣出金額仍需原生依據。')
        native_funding=facts.get('native_funding_advice',{})
        bond_source=facts.get('native_bond_source')
        if bond_source:
            text.append('原Work5／V75來源檢查：'+bond_source['status']+'；SGOV實體持股與債券桶／子彈桶分開，尚未產生完整債券部署建議。')
            symbol=facts.get('symbol',item['asset_id'])
            quality=bond_source.get('etf_quality_assessments',{}).get(symbol)
            if quality:
                states=quality['metrics'];labels={'UNKNOWN':'資料未齊','REVIEW_REQUIRED':'需複查',
                    'STRUCTURE_OK':'通過','STRUCTURE_ABNORMAL':'異常','LIQUIDITY_OK':'通過','LIQUIDITY_ABNORMAL':'異常',
                    'DISTRIBUTION_OK':'通過','DISTRIBUTION_ABNORMAL':'異常','NOT_APPLICABLE':'不適用'}
                text.append('V75 ETF品質：結構 '+labels[states['structure_state']]+'；流動性 '+
                    labels[states['liquidity_state_etf']]+'；配息品質 '+labels[states['distribution_quality_state']]+'。')
                missing_labels={'liquidation_or_termination_announced':'清算／終止公告的完整來源核對',
                    'unapproved_material_methodology_change':'重大方法變更與核准紀錄核對',
                    'median_20d_bid_ask_spread_pct':'20交易日買賣價差中位數',
                    'trailing_12m_roc_pct_with_complete_issuer_breakdown':'近12月配息來源與ROC分解'}
                missing=[missing_labels[k] for k in quality['unprovided_inputs'] if k in missing_labels]
                if missing:text.append('品質來源待補：'+'、'.join(missing)+'。')
                distribution=quality.get('calculations',{}).get('distribution_source')
                if distribution:
                    text.append(distribution_source_text(symbol,distribution))
            text.extend(ready_data_evidence_notes(bond_source.get('ready_data_evidence'),symbol,
                bond_source.get('additional_delta_evidence'),bond_source.get('ib_qa_evidence')))
            text.extend(plugin_evidence_notes(bond_source.get('plugin_data_cross_checks'),symbol,
                bond_source.get('ib_qa_evidence')))
            text.extend(official_reply_notes(bond_source.get('official_reply_status')))
            yield_source=bond_source.get('predicate_observations',{}).get(symbol,{}).get('PRED-008',{}).get('yield_reference')
            liquidity=bond_source.get('predicate_observations',{}).get(symbol,{}).get('PRED-007',{}).get('amendment_assessment')
            if liquidity:
                from v75_pred007_source import describe
                text.append(describe(liquidity))
            if yield_source:
                text.append('第008項採固定'+str(yield_source['selected_tenor_months'])+
                    'M Treasury久期匹配備援，週取最後公布值；官方基金YTM／SEC yield單點另列。')
            technical=bond_source.get('predicate_observations',{}).get(symbol,{}).get('PRED-009',{})
            state=technical.get('original_result',{}).get('aggregate_state')
            if technical.get('deployment_input_eligible') and state:
                label={'TRIM_WATCH':'技術減碼觀察','RIGHT_CONFIRM':'右側確認',
                    'LEFT_MATURE':'左側成熟','TECHNICAL_NEUTRAL':'技術中性'}[state]
                text.append('V75原生技術分類：'+label+'；須與完整安全條件及既有部位政策共同判斷。')
            audit=bond_source.get('policy_audit') or {}
            if audit.get('owner_role_policy')=='EXPLICIT_IBKR_STOCK_OPPORTUNITY_RESERVE':
                text.append('既有本人紀錄明訂IBKR SGOV為股票買點彈藥；歷史金額與長期目標均未套用為本輪角色餘額，可用現金仍須另核。')
            elif audit.get('owner_role_policy')=='SEPARATE_DEFENSIVE_AND_OPPORTUNITY_ROLES':
                text.append('既有正式紀錄要求SGOV防守核心與機動子彈分帳；尚未以歷史比例拆分本輪持倉，防守部位不作股票買進資金。')
            compatibility=bond_source.get('target_compatibility',{})
            if compatibility.get('status')=='APPROVED_TARGET_RULE_INCOMPATIBILITY':
                text.append('核准債券目標與V75通用長期配置地圖有差異；核准配置保留，V75可另提債券建議供參考，不推定本人禁止SPSB或公司債，也不要求補寫例外原因。')
            comparison=bond_source.get('advisory_comparison')
            if comparison:
                for line in comparison['lines']:
                    text.append(f"V75長期比較 {line['asset_id']}：原核准金額 {line['currency']} {line['approved_target_amount'] if line['approved_target_present'] else '未列'}；通用地圖建議 {line['proposed_long_term_amount']}，差額 {line['difference_amount']}。"+
                        ('超短公債提供低利率敏感度防守。' if line['asset_id']=='SGOV' else '短期投資級公司債補強收息，同時承擔信用風險。'))
                text.append('以上是長期配置比較，未改變核准目標；今天是否適合部署仍依V75來源、資格與部署條件判斷，不是立即買進或賣出指示。')
            fields=list(dict.fromkeys(i['field_path'] for i in bond_source['issues']))
            if fields:text.append('V75仍缺：'+'、'.join(fields)+'。')
        if native_funding.get('status')=='CASH_TRIAL_ADVICE_COMPUTED':
            plan=native_funding['native_plan']
            text.append(f"原Work3／Work4及V82金額規劃已執行：本輪缺漏可用現金按0試算，現金買入建議 {source['owner']['currency']} {plan['execution_amount']}；這不代表既有現金餘額或持股缺口為0，既有資產調整及扣掛單淨額另列。")
        amount=item['recommended_buy_amount']
        if amount['status']=='KNOWN':text.append(f"原生補倉缺口 {amount['currency']} {amount['amount']}。")
        elif item['remaining_amount_dependencies']:
            text.append('現有資產補倉建議金額未定，尚缺：'+'、'.join(item['remaining_amount_dependencies'])+'。')
        if item['new_external_funding_buy_amount']=='0':
            text.append('本輪不新增外部資金，新增資金買入建議為0；既有現金及資產調整另計，並未歸零。')
        rows.append({'item_id':item['item_id'],'asset_id':item['asset_id'],
            'recommendation':deepcopy({k:v for k,v in item.items() if k!='native_component_delivery'}),
            'explanation':'\n'.join(text),'source_result_digest':source['result_digest']})
    return {'contract_name':'Family.W5.HoldingsRecommendationMentor.v1','status':'EXPLAINED_WITH_LIMITATIONS'
        if source['status']=='NORMALIZED_WITH_LIMITATIONS' else 'EXPLAINED',
        'scope':source['scope'],'client_id':source['client_id'],'run_id':source['run_id'],
        'owner':deepcopy(source['owner']),'source_db_sha256':source['source_db_sha256'],
        'source_result_digest':native._digest(source),'mentor_return':deepcopy(source['mentor_return']),
        'items':rows,'execution_advice_allowed':True,'broker_execution_allowed':False,
        'full_native_deployment_mentor':False,'trade_action':'NO_TRADE'}
