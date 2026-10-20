from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from family_input import digest
from family_boundary import prepare_input
from family_runner import FamilyRunner
from test_family_boundary import fixture,refresh_snapshot
from test_family_bridges import policy_fixture
from test_native_pipeline import pipeline_case
from test_native_adapters import ROOT


def runner_case():
    bundle=pipeline_case();w3=bundle['stock_request']['work3_handoff']
    req,ctx=fixture(w3['client_state_context']['payload']['client_id'])
    req['run_id']=w3['run_id']
    target=req['confirmed_target'];draft=target['payload']['draft']
    draft['allocation_id']=w3['final_target']['allocation_id']
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    target['target_hash']=target['payload']['target_hash']=ctx['target_hash']=draft['draft_hash']
    evidence=target['payload']['confirmation_evidence']
    for branch in ('stock_request','bond_request'):
        bundle[branch]['work3_handoff']['final_target']['confirmation_proof']={k:evidence[k] for k in ('confirmed_at','confirmed_by')}
    bundle['asset_framework']['work6_final_target_reference'].update({k:evidence[k] for k in ('confirmed_at','confirmed_by')})
    bundle['stock_evidence']['evaluated_at']=req['evaluation_at']
    req['native_bundle']=bundle
    snapshot=policy_fixture()
    for rows in snapshot['tables'].values():
        for row in rows:row['client_id']=req['client_id']
    # Synthetic stock identity and position are explicit W1 facts, not inferred aliases.
    tables=req['client_snapshot']['payload']['tables']
    for name in ('universe_membership','universe_confirmation','permission_policy','permission_confirmation'):
        tables[name]=snapshot['tables'][name]
    tables['portfolio_instrument'][0].update(ticker='QQQ',exchange_code='NASDAQ')
    tables['portfolio_position'][0]['quantity_decimal']='0'
    refresh_snapshot(req,ctx)
    prepared=prepare_input(req,trusted_context=ctx)
    ctx['native_binding']={'schema_version':'Family.W5.NativeBinding.v1','request_digest':prepared.input_digest,
        'bundle_digest':digest(bundle),'target_binding_digest':prepared.payload['target_binding']['binding_digest'],
        'family_owner':deepcopy(req['owner']),'native_owner':deepcopy(w3['owner']),
        'data_provenance':'SYNTHETIC','source_reference':'SYNTHETIC_DISPATCH_TEST_ONLY'}
    ctx['native_binding']['stock_instrument']={'instrument_key':'VT_KEY','asset_id':'QQQ',
        'account_key':req['owner']['account'],'native_owner':deepcopy(w3['owner']),
        'source_reference':'SYNTHETIC_W1_INSTRUMENT'}
    return req,ctx


@pytest.mark.parametrize('client',['SYNTHETIC_A','SYNTHETIC_B','SYNTHETIC_C','SYNTHETIC_D'])
def test_missing_native_mapping_produces_explicit_unavailable(client,monkeypatch):
    req,ctx=fixture(client);calls=[]
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *a:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['status']=='DATA_UNAVAILABLE'
    assert out['issue_codes'][0]['code']=='NATIVE_INPUT_MAPPING_REQUIRED'
    assert calls==[] and out['trade_action']=='NO_TRADE'


@pytest.mark.parametrize('kind',['client','permission','versions','bundle','binding','owner'])
def test_invalid_authority_or_binding_stops_before_dispatch(kind,monkeypatch):
    req,ctx=runner_case();calls=[]
    if kind=='client':req['client_id']='OTHER'
    elif kind=='permission':ctx['analysis_permission']='NONE'
    elif kind=='versions':ctx['expected_versions']['funding']='NEW'
    elif kind=='bundle':req['native_bundle']['stock_evidence']['valuation_price']='999'
    elif kind=='binding':ctx['native_binding']['target_binding_digest']='wrong'
    else:ctx['native_binding']['family_owner']['account']='OTHER'
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *a:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['status']=='BLOCKED' and calls==[] and out['canonical_result'] is None


def test_real_dispatch_preserves_known_native_gap_without_partial_publication(monkeypatch):
    import family_runner
    req,ctx=runner_case();before=deepcopy((req,ctx));original=family_runner.run_native_pipeline;calls=[]
    def spy(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(family_runner,'run_native_pipeline',spy)
    runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    out=runner.analyze(req)
    assert calls==[1]
    assert out['status']=='ERROR' and out['issue_codes'][0]['code']=='C8C9.W8.FINAL_TARGET_BINDING'
    assert out['canonical_result'] is None and out['mentor'] is None
    assert next(iter(runner.store._entries.values()))['publication_count']==0
    assert (req,ctx)==before


def test_native_confirmation_must_equal_preserved_historical_evidence():
    req,ctx=runner_case();req['native_bundle']['stock_request']['work3_handoff']['final_target']['confirmation_proof']['confirmed_by']='OTHER'
    ctx['native_binding']['request_digest']=digest(req)
    ctx['native_binding']['bundle_digest']=digest(req['native_bundle'])
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']=='NATIVE_CONFIRMATION_PROOF_MISMATCH'


@pytest.mark.parametrize('with_context',[False,True])
def test_cli_writes_structured_result_and_preserves_inputs(tmp_path,with_context):
    req,ctx=fixture();source=tmp_path/'request.json';authority=tmp_path/'context.json';output=tmp_path/'output.json'
    source.write_text(json.dumps(req));authority.write_text(json.dumps(ctx));before=(source.read_bytes(),authority.read_bytes())
    command=[sys.executable,str(Path(__file__).resolve().parents[1]/'run_analysis.py'),
        '--request',str(source),'--output',str(output),'--repo-root',str(ROOT)]
    if with_context:command+=['--trusted-context',str(authority)]
    env=dict(os.environ);env.pop('W5_TRUSTED_CONTEXT',None)
    result=subprocess.run(command,env=env,text=True,capture_output=True)
    assert result.returncode==2
    out=json.loads(output.read_text())
    assert out['status']==('DATA_UNAVAILABLE' if with_context else 'BLOCKED')
    assert out['trade_action']=='NO_TRADE'
    assert before==(source.read_bytes(),authority.read_bytes())
