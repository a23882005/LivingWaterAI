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
        'production':'HOLD','trade_action':'NO_TRADE','execution_advice_allowed':False}
