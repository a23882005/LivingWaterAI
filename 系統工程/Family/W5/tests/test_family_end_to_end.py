"""Synthetic historical-source fixture through the actual Family entry point."""
import json
from copy import deepcopy
import pytest
from test_target_units import bound_case
from test_family_runner import runner_case
from test_stock_source_bridge import refresh
from family_input import digest
from family_boundary import prepare_input
from family_runner import FamilyRunner
from c7_engine import run_c7_engine
from test_native_adapters import ROOT


def full_family_case():
    r,c=runner_case(); b,s=bound_case()
    r=json.loads(json.dumps(r).replace('client-w5','qa-client').replace('w5-run-001','qa-run-3').replace('C-W6-FINAL-W5-001','C-W6-FINAL-QA-003'))
    c=json.loads(json.dumps(c).replace('client-w5','qa-client').replace('w5-run-001','qa-run-3').replace('C-W6-FINAL-W5-001','C-W6-FINAL-QA-003'))
    s=json.loads(json.dumps(s).replace('2026-09-24T11:45:00+08:00',b['stock_evidence']['as_of']))
    s['work6_result']['drift_snapshot']['as_of']=b['stock_evidence']['as_of']
    s['evaluated_at']=r['evaluation_at']
    s.update(schema_version='Family.W5.C7Source.v1',producer='SYNTHETIC_C_WORK6',version='1',source_reference='SYNTHETIC_FULL_FAMILY',family_owner=deepcopy(r['owner']))
    b['asset_framework']=run_c7_engine(ROOT,s)['result']
    r['native_bundle']=b
    final=s['work6_result']['final_target']['snapshot']
    draft=r['confirmed_target']['payload']['draft']
    draft['target_lines']=[{'instrument_id':x['instrument_id'],'ticker':x['ticker'],'weight':deepcopy(x['weight']),'target_amount':deepcopy(x['portfolio_amount']),'source_reference_ids':['SYNTHETIC_FULL_FAMILY']} for x in final['positions']]
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    r['confirmed_target']['target_hash']=r['confirmed_target']['payload']['target_hash']=c['target_hash']=draft['draft_hash']
    proof=r['confirmed_target']['payload']['confirmation_evidence']
    for branch in ('stock_request','bond_request'):
     w=b[branch]['work3_handoff'];w['temporal']['as_of']=r['evaluation_at'];w['shared_decision_context']['as_of']=r['evaluation_at']
     for bind in w['engine_bindings'].values():bind['shared_context_digest_sha256']=digest(w['shared_decision_context'])
     w['final_target']['confirmation_proof']={k:proof[k] for k in ('confirmed_at','confirmed_by')}
    b['stock_evidence']['evaluated_at']=r['evaluation_at']
    r['client_snapshot']['payload']['tables']['portfolio_position'][0]['quantity_decimal']='10'
    c['valuation_source']['prices']['SGOV']['value']='40'
    c['funding_source']['c7_funding_context']=deepcopy(s['funding_context'])
    for asset,mapping in c['native_binding']['bond_instruments'].items():mapping['target_instrument_id']=asset
    c['v70_source']['context']=deepcopy(b['stock_request']['work3_handoff']['v70_runtime_context'])
    r['v70_source_digest']=digest(c['v70_source'])
    c['c7_source']=s;r['c7_source_digest']=digest(s)
    r['confirmed_target']['payload']['confirmation_evidence_hash']=digest(proof)
    refresh(r,c)
    c['native_binding']['target_binding_digest']=prepare_input(r,trusted_context=c).payload['target_binding']['binding_digest']
    return r,c


def test_family_real_engines_mentor_replay_and_historical_confirmation():
    req,ctx=full_family_case();before=deepcopy((req,ctx))
    runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    first=runner.analyze(req);second=runner.analyze(req)
    assert first['status']=='OK',first
    assert first['replay_status']=='COMPUTED' and second['replay_status']=='REPLAYED'
    assert {k:v for k,v in first.items() if k!='replay_status'}=={k:v for k,v in second.items() if k!='replay_status'}
    assert first['target_binding']['confirmation_run_id']=='OLD_CONFIRMATION_RUN'
    assert first['target_binding']['analysis_run_id']=='qa-run-3'
    assert first['native_result']['funding_aggregate']['bond_used']=='160.00'
    assert first['mentor'] and first['trade_action']=='NO_TRADE'
    entry=next(iter(runner.store._entries.values()))
    assert entry['publication_count']==1 and entry['attempts']==1
    json.dumps(runner.store.snapshot(),allow_nan=False)
    assert (req,ctx)==before


@pytest.mark.parametrize('kind',['permission','version','source'])
def test_completed_real_result_revalidates_authority_and_sources(kind):
    req,ctx=full_family_case();runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    assert runner.analyze(req)['status']=='OK'
    if kind=='permission':ctx['analysis_permission']='NONE'
    elif kind=='version':ctx['expected_versions']['funding']='NEW_VERSION'
    else:ctx['c7_source']['version']='2'
    replay=runner.analyze(req)
    assert replay['status']=='BLOCKED' and replay['mentor'] is None
    assert next(iter(runner.store._entries.values()))['publication_count']==1


def test_real_mentor_partial_interruption_resumes_without_duplicate_publication():
    req,ctx=full_family_case();runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    original=runner._compute;results=[]
    def interrupted(request):
        result=original(request);results.append(result)
        if len(results)==1:raise ValueError('SYNTHETIC_AFTER_MENTOR_INTERRUPTION')
        return result
    runner._compute=interrupted
    assert runner.analyze(req)['status']=='ERROR'
    entry=next(iter(runner.store._entries.values()))
    assert entry['publication_count']==0 and entry['result'] is None
    out=runner.analyze(req)
    assert out['status']=='OK' and results[0]==results[1]
    assert entry['attempts']==2 and entry['publication_count']==1
    assert runner.analyze(req)['replay_status']=='REPLAYED'


def test_real_late_result_cannot_replace_retry_publication():
    from threading import Event
    req,ctx=full_family_case();runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    original=runner._compute;release=Event();finished=Event();calls=[]
    def delayed(request):
        calls.append(len(calls)+1);attempt=calls[-1]
        result=original(request)
        if attempt==1:
            release.wait(20);finished.set()
        return result
    runner._compute=delayed
    try:
        out=runner.analyze(req,timeout_seconds=5)
        assert out['status']=='OK',out
        entry=next(iter(runner.store._entries.values()))
        assert entry['timeouts']==1 and entry['attempts']==2 and entry['publication_count']==1
        published=deepcopy(entry['result'])
        release.set();assert finished.wait(5)
        assert entry['result']==published and entry['publication_count']==1
        assert runner.analyze(req)['replay_status']=='REPLAYED'
    finally:release.set()


def test_real_competing_requests_publish_once():
    from concurrent.futures import ThreadPoolExecutor
    req,ctx=full_family_case();runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(runner.analyze,deepcopy(req)) for _ in range(2)]
        outputs=[f.result(timeout=30) for f in futures]
    assert all(x['status']=='OK' for x in outputs)
    assert {x['replay_status'] for x in outputs}=={'COMPUTED','REPLAYED'}
    entry=next(iter(runner.store._entries.values()))
    assert entry['publication_count']==entry['attempts']==1
