from copy import deepcopy
import json
import pytest
from test_native_adapters import ROOT,FIXTURES
from runtime_loader import load_c_module
from mentor_bridge import explain_native,MentorError


def mentor_case():
    req=json.loads((FIXTURES/'work9_mentor_request.json').read_text())
    native=load_c_module(ROOT,9);unified=native.build_unified_deployment(req)
    context={'client_id':'SYNTHETIC-MENTOR','run_id':unified['run_id'],'owner':deepcopy(unified['owner']),
        'currency':unified['currency'],'runtime_mode':'REAL_DETERMINISTIC','data_provenance':'SYNTHETIC',
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE',
        'expected_result_digest':native._digest(unified)}
    return req,unified,context


def test_native_mentor_preserves_numbers_protected_risk_and_sources():
    req,unified,ctx=mentor_case();before=deepcopy((req,unified,ctx))
    out=explain_native(ROOT,req,unified,trusted_context=ctx)
    assert out['language']=='zh-Hant'
    assert out['mentor_return']==unified['mentor_return']
    assert out['canonical_deployment_result']==unified['canonical_deployment_result']
    assert out['items'][0]['risk_signal']['raw_execution_action']=='REDUCE_RISK'
    assert out['items'][0]['client_action']=='HOLD_PROTECTED'
    assert out['items'][1]['source_facts']['canonical_action']=='BUY'
    assert out['items'][1]['source_facts']['deployment_amount']['value']['amount']=='70.00'
    assert out['items'][2]['source_facts']['deployment_amount']['value']['amount']=='0'
    assert out['unknown_reason_codes'] and all(x['status']=='PENDING_EXPLANATION' for x in out['items'][0]['reason_explanations'])
    assert out['trade_action']=='NO_TRADE' and out['data_provenance']=='SYNTHETIC'
    assert (req,unified,ctx)==before
    out['canonical_deployment_result']['items'][0]['canonical_action']='BUY'
    assert unified==before[1]


@pytest.mark.parametrize('field,value',[('run_id','OTHER'),('owner',{}),('currency','TWD'),
    ('analysis_permission','DENY'),('trade_authorization','TRADE'),('runtime_mode','MOCK_ONLY')])
def test_mentor_rejects_wrong_scope_or_permission(field,value):
    req,u,c=mentor_case();c[field]=value
    with pytest.raises(MentorError):explain_native(ROOT,req,u,trusted_context=c)


def test_llm_mutation_rejected_before_render():
    req,u,c=mentor_case()
    with pytest.raises(MentorError,match='MODEL_FINANCIAL_MUTATION_REJECTED'):
        explain_native(ROOT,req,u,trusted_context=c,llm_suggested_changes=[{'amount':999}])


@pytest.mark.parametrize('resign',[False,True])
def test_changed_result_cannot_be_presented_as_native(resign):
    req,u,c=mentor_case();u['canonical_deployment_result']['items'][1]['deployment_amount']['value']['amount']='999'
    if resign:c['expected_result_digest']=load_c_module(ROOT,9)._digest(u)
    with pytest.raises(MentorError,match='DIGEST_MISMATCH|NATIVE_SOURCE_RESULT_MISMATCH'):
        explain_native(ROOT,req,u,trusted_context=c)


def test_recovery_replays_native_work9_and_mentor_without_republishing():
    import importlib.util,os
    from pathlib import Path
    from recovery_bridge import StagingAnalysisStore
    path=Path(os.environ.get('W5_W2_ROOT','w2'))/'runtime/c_configuration_core/work21/recovery.py'
    spec=importlib.util.spec_from_file_location('original_w2_mentor_recovery',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    journal=StagingAnalysisStore(module);req,u,c=mentor_case();calls=[]
    payload={'client_id':c['client_id'],'request_id':'MENTOR-REQ','run_id':c['run_id'],
        'work9_request':req,'unified':u,'context':c}
    def compute(r):
        calls.append(1)
        return explain_native(ROOT,r['work9_request'],r['unified'],trusted_context=r['context'])
    first=journal.analyze(payload,validate=lambda r:None,compute=compute)
    second=journal.analyze(payload,validate=lambda r:None,compute=compute)
    assert first['result']==second['result'] and second['status']=='REPLAYED' and calls==[1]


def test_source_output_change_is_checked_against_frozen_work9_binding():
    req,u,c=mentor_case()
    req['work4_v82_integration_result']['canonical_v82_output']['canonical_analysis']['execution_action']['value']='BUY'
    with pytest.raises(ValueError):explain_native(ROOT,req,u,trusted_context=c)


def test_partial_mentor_failure_recomputes_same_snapshot_without_partial_publication():
    import importlib.util,os
    from pathlib import Path
    from recovery_bridge import StagingAnalysisStore
    path=Path(os.environ.get('W5_W2_ROOT','w2'))/'runtime/c_configuration_core/work21/recovery.py'
    spec=importlib.util.spec_from_file_location('original_w2_partial_recovery',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    journal=StagingAnalysisStore(module);req,u,c=mentor_case();calls=[]
    payload={'client_id':c['client_id'],'request_id':'PARTIAL-REQ','run_id':c['run_id'],
             'work9_request':req,'unified':u,'context':c}
    def compute(r):
        out=explain_native(ROOT,r['work9_request'],r['unified'],trusted_context=r['context'])
        calls.append(out['canonical_deployment_result_sha256'])
        if len(calls)==1:raise RuntimeError('INTERRUPTED_BEFORE_PUBLICATION')
        return out
    with pytest.raises(RuntimeError,match='INTERRUPTED'):
        journal.analyze(payload,validate=lambda r:None,compute=compute)
    entry=next(iter(journal._entries.values()))
    assert entry['result'] is None and entry['publication_count']==0
    answer=journal.analyze(payload,validate=lambda r:None,compute=compute)
    assert calls[0]==calls[1]==answer['result']['canonical_deployment_result_sha256']
    assert entry['publication_count']==entry['journal']['mutation_count']==1
