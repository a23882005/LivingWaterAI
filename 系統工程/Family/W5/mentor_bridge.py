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
                    text.append('已核對發行商'+str(distribution['periods'])+'期配息明細；'+
                        ('2026成分仍屬暫定，保留品質未定。' if distribution['provisional_issuer_components'] else
                         '2025稅務分解與2026缺漏分列，未把缺少的ROC補0。'))
            yield_source=bond_source.get('predicate_observations',{}).get(symbol,{}).get('PRED-008',{}).get('yield_reference')
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
