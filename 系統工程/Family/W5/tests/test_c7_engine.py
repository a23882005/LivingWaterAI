from copy import deepcopy
import json
from pathlib import Path
import pytest
from c7_engine import run_c7_engine, bind_c7_source
from family_input import digest
from family_boundary import BoundaryError
from family_runner import FamilyRunner
from test_family_runner import runner_case
from test_native_adapters import ROOT


def original_case():
    base=Path(__file__).parent/'fixtures/c7'
    read=lambda n:json.loads((base/n).read_text())
    expected=read('W13_C_WORK7_ASSET_FRAMEWORK_RESULT_QA_RUN3.json')
    source={'canonical_input':read('W13_C_WORK7_CANONICAL_INPUT_QA_RUN3.json'),
            'work6_result':read('W13_C_WORK6_SOURCE_QA_RUN3.json'),
            'funding_context':read('W13_LOOP2_C7_FUNDING_CONTEXT_US_HAPPY.json'),
            'evaluated_at':expected['created_at']}
    return source,expected


def test_original_engine_exact_work21_golden_and_determinism():
    source,expected=original_case();before=deepcopy(source)
    first=run_c7_engine(ROOT,source)
    assert first['result']==expected
    assert first==run_c7_engine(ROOT,source)
    assert source==before and first['trade_action']=='NO_TRADE'


@pytest.mark.parametrize('kind',['stale','drift','funding','identity'])
def test_original_contract_rejects_or_routes_invalid_source(kind):
    source,_=original_case()
    if kind=='stale':source['canonical_input']['v70_asset_framework']['freshness']='STALE'
    elif kind=='drift':source['work6_result']['drift_snapshot']['denominator']['amount']+=1
    elif kind=='funding':source['funding_context']['total_new_investment_amount']+=1
    else:source['work6_result']['identity']['client_id']='OTHER'
    try:result=run_c7_engine(ROOT,source)['result']
    except ValueError as exc:
        assert getattr(exc,'issues',None)
    else:
        assert result['status'] in ('BLOCKED','RETURN_TO_V70')
        assert result['issues']


def source_case():
    source,result=original_case()
    owner={'client_id':result['identity']['client_id'],'domain':'INVESTMENT',
           'broker':'BROKER','account':'ACCOUNT','currency':'USD'}
    source.update(schema_version='Family.W5.C7Source.v1',producer='SYNTHETIC_WORK21',
                  version='QA_RUN3',source_reference='WORK21_MANIFEST_SHA256.txt',family_owner=owner)
    req={'owner':owner,'client_id':result['identity']['client_id'],'run_id':result['identity']['run_id'],
         'evaluation_at':source['evaluated_at'],'native_bundle':{'asset_framework':result},
         'c7_source_digest':digest(source)}
    return req,{'native_binding':{'data_provenance':'SYNTHETIC'},'c7_source':source}


def test_binding_uses_computed_original_result():
    req,ctx=source_case()
    assert bind_c7_source(ROOT,req,ctx)['result']==req['native_bundle']['asset_framework']


@pytest.mark.parametrize('kind,code',[
    ('digest','C7_SOURCE_DIGEST_MISMATCH'),('result','C7_COMPUTED_FRAMEWORK_MISMATCH'),
    ('owner','C7_SOURCE_OWNER_MISMATCH'),('run','C7_SOURCE_IDENTITY_MISMATCH')])
def test_binding_rejects_source_or_output_substitution(kind,code):
    req,ctx=source_case()
    if kind=='digest':ctx['c7_source']['version']='REPLACED'
    elif kind=='result':req['native_bundle']['asset_framework']['work7_snapshot_id']='FAKE'
    elif kind=='owner':req['owner']={**req['owner'],'account':'OTHER'}
    else:req['run_id']='OTHER'
    with pytest.raises(BoundaryError,match=code):bind_c7_source(ROOT,req,ctx)


def test_source_backed_family_cannot_bypass_actual_c7():
    req,ctx=runner_case();ctx['native_binding']['data_provenance']='SOURCE_BACKED'
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['status']=='DATA_UNAVAILABLE'
    assert result['issue_codes'][0]['code']=='C7_SOURCE_REQUIRED'
    assert result['mentor'] is None
