"""One read-only view of available native returns while deployment is routed.

This consumes the scoped original Work9 return already replayed by the
holdings boundary. It cannot create the full deployment Work9 result.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest


def build(request,analysis,work6,c7,blockers):
    source=analysis.get('work9_result');mentor=analysis.get('mentor')
    if source is None or mentor is None:return None
    identity={'client_id':request['client_id'],'run_id':request['run_id'],
        'owner':request['owner'],'source_db_sha256':request['client_snapshot']['payload']['source_sha256']}
    for key,value in identity.items():
        if source.get(key)!=value or mentor.get(key)!=value:
            raise PermissionError('CONTINUATION_MENTOR_SOURCE_IDENTITY:'+key)
    if (source.get('contract_name')!='LivingWaterAI.C8C9.Work9.HoldingsRecommendationReturn'
            or source.get('full_canonical_deployment_complete') is not False
            or mentor.get('full_native_deployment_mentor') is not False
            or mentor.get('source_result_digest')!=digest(source)):
        raise PermissionError('CONTINUATION_MENTOR_ORIGINAL_WORK9_BINDING')
    expected=[r['item_id'] for r in source['items']]
    actual=[r['item_id'] for r in mentor['items']]
    if expected!=actual or len(set(actual))!=len(actual):
        raise PermissionError('CONTINUATION_MENTOR_COVERAGE')
    items=[]
    for original,row in zip(source['items'],mentor['items']):
        if original['asset_id']!=row['asset_id'] or row.get('source_result_digest')!=source['result_digest']:
            raise PermissionError('CONTINUATION_MENTOR_ITEM_BINDING')
        if row.get('recommendation')!={k:v for k,v in original.items() if k!='native_component_delivery'}:
            raise PermissionError('CONTINUATION_MENTOR_FINANCIAL_MUTATION')
        items.append({k:deepcopy(row[k]) for k in ('item_id','asset_id','recommendation','explanation')})
    out={'schema_version':'Family.W5.ContinuationMentor.v1',**deepcopy(identity),
        'evaluation_at':request['evaluation_at'],'status':'EXPLAINED_WITH_DEPLOYMENT_LIMITATIONS',
        'scope':'AVAILABLE_NATIVE_COMPONENTS_AND_CONFIGURATION_REVIEW__NOT_FULL_DEPLOYMENT_MENTOR',
        'configuration_status':c7['status'],'work6_status':work6['loop_status'],
        'holdings_work9_scope':source['scope'],'holdings_work9_status':source['status'],
        'items':items,'blockers':deepcopy(blockers),
        'funding_review':deepcopy((analysis.get('account_funding_check') or {}).get('shared_cash_ledger')),
        'source_bindings':{'analysis_report_digest':analysis['report_digest'],
            'work9_result_digest':digest(source),'work6_result_digest':digest(work6),
            'c7_result_digest':digest(c7),
            'funding_check_digest':(analysis.get('account_funding_check') or {}).get('output_digest')},
        'formal_deployment_ready':False,'full_native_pipeline_complete':False,
        'full_native_mentor_reached':False,'canonical_result':None,
        'broker_execution_allowed':False,'financial_mutation_allowed':False,'trade_action':'NO_TRADE'}
    text=['可用分析已回傳；完整部署仍受原生配置／資金條件限制。',
        '既有長期核准配置保留；沒有據此核准新的當輪戰術權重。',
        'C7狀態：'+c7['status']+'。']
    for row in blockers['contract_reconfirmation']:
        a=Decimal(str(row['confirmed_weight']))*100;b=Decimal(str(row['same_run_v70_weight']))*100
        text.append(row['bucket']+'：既有核准 '+format(a,'.4f')+'%；同輪V70 '+format(b,'.4f')+'%。')
    status=blockers.get('support_inquiries')
    if status:
        text.append('State Street本次詢問已回覆無法提供，已結案，不再等待資料交付。')
        text.append('IB工單由本人送出，尚待答覆；目前未提供工單編號或客服答案。')
    text.append('已知原生金額共用同一帳戶現金，不把SGOV實體、角色參考或未定金額加成可用現金。')
    v75=blockers.get('v75_original_contract') or {}
    if v75.get('runtime_rule_version'):
        text.append('正式V75沿用'+v75['runtime_rule_version']+'：通用美國債券子桶長期SGOV70%／SPSB30%；客戶核准配置另行保留。')
        text.append('完成評估後的WAIT／本輪0新增與必要資料不足分開處理；後者未冒充WAIT或通過。未部署額度並不自動構成SGOV買進建議。')
    if v75.get('structural_issues'):
        text.append('原生V75目標契約：'+'；'.join(str(r.get('code')) for r in v75['structural_issues'])+'。核准目標沒有被通用模板覆蓋。')
    for row in v75.get('predicate_input_limitations',[]):
        text.append(row['asset_id']+' '+row['predicate_id']+'：原判定 '+str(row['original_assessment_status'])+
            '／'+str(row['original_aggregate_state'])+'，正式輸入新鮮度已驗證='+str(row['input_freshness_verified'])+'。')
    for item in items:text.append(item['explanation'])
    out['readable_review']='\n\n'.join(text)
    out['digest']=digest(out)
    return out
