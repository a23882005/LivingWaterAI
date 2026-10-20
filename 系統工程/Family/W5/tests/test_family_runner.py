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
    # Explicit synthetic W2 target content; the original golden and real records
    # remain unchanged. Historical target amounts are distinct from new funding.
    draft['target_lines']=[{'instrument_id':row['instrument_id'],
        'weight':{'value':row['work6_final_target_weight'],'value_state':'KNOWN'},
        'target_amount':{'amount':str(row['work6_final_target_weight']*20000),
            'currency':'USD','value_state':'KNOWN'},
        'source_reference_ids':['SYNTHETIC_CONFIRMED_TARGET']}
        for row in bundle['asset_framework']['integrated_asset_framework']['instrument_targets']]
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    target['target_hash']=target['payload']['target_hash']=ctx['target_hash']=draft['draft_hash']
    evidence=target['payload']['confirmation_evidence']
    for branch in ('stock_request','bond_request'):
        bundle[branch]['work3_handoff']['temporal']['as_of']=req['evaluation_at']
        shared=bundle[branch]['work3_handoff']['shared_decision_context']
        shared['as_of']=req['evaluation_at']
        for engine in ('v82','v75'):
            bundle[branch]['work3_handoff']['engine_bindings'][engine]['shared_context_digest_sha256']=digest(shared)
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
    tables['portfolio_position'][0].update(quantity_decimal='0',as_of_utc='2026-09-25T00:00:00Z')
    for asset,quantity in [('SGOV','1'),('SPSB','0')]:
        tables['portfolio_instrument'].append({'client_id':req['client_id'],'instrument_key':asset+'_KEY',
            'ticker':asset,'exchange_code':'ARCA','quote_currency':'USD'})
        tables['portfolio_position'].append({'client_id':req['client_id'],'account_key':req['owner']['account'],
            'instrument_key':asset+'_KEY','quantity_decimal':quantity,'as_of_utc':'2026-09-25T00:00:00Z'})
        for name in ('universe_membership','universe_confirmation','permission_policy'):
            rows=deepcopy([r for r in tables[name] if r.get('instrument_key')=='VT_KEY'])
            for row in rows:
                row['instrument_key']=asset+'_KEY'
                if name=='permission_policy':row['policy_key']=asset+'_POLICY'
            tables[name].extend(rows)
        tables['permission_confirmation'].append({'client_id':req['client_id'],'policy_key':asset+'_POLICY',
            'version_no':1,'confirmed_at_utc':'2026-10-01T00:00:00Z'})
    raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-09-25T00:00:00Z','verification':{'ready':True},
        'indicators':{'m12':{'value':80,'status':'OK','source':'https://finance.yahoo.com/quote/%5EMOVE/',
            'unit':'','dataDate':'2026-09-24','method':'SYNTHETIC_TEST_ONLY'}}}
    req['macro_snapshot'].update(payload=raw,asOf=raw['asOf'],digest=digest(raw))
    req['expected_versions']['market']=ctx['expected_versions']['market']=digest(raw)
    tables['holding_policy_proposal']=[{'client_id':req['client_id'],'account_key':req['owner']['account'],
        'instrument_key':'VT_KEY','version_no':1,'policy_code':'ADJUSTABLE','evidence_state':'VERIFIED',
        'effective_at_utc':'2026-10-01T00:00:00Z','source_reference':'SYNTHETIC_W1_POLICY'}]
    tables['holding_policy_confirmation']=[{'client_id':req['client_id'],'account_key':req['owner']['account'],
        'instrument_key':'VT_KEY','version_no':1,'confirmed_at_utc':'2026-10-01T00:00:00Z'}]
    framework=bundle['asset_framework'];asset=bundle['stock_request']['asset_context']['asset']['asset_id']
    framework['protected_locked_weights']=[r for r in framework['protected_locked_weights'] if r['instrument_id']!=asset]
    for row in framework['integrated_asset_framework']['instrument_targets']:
        if row['instrument_id']==asset:row.update(ticker=asset,protected=False,allocation_rule='PROPORTIONAL_RESIDUAL_FROM_CONFIRMED_FINAL_TARGET')
    for bucket in framework['residual_allocation']['buckets']:
        for row in bucket['items']:
            if row['instrument_id']==asset:row.update(ticker=asset,protected=False,allocation_rule='PROPORTIONAL_RESIDUAL_FROM_CONFIRMED_FINAL_TARGET')
    for row in framework['drift_snapshot']['items']:
        if row['instrument_id']==asset:
            row.update(ticker=asset,protected=False,client_facing_action='HOLD')
            row['current_weight']['value']=0
            row['drift']['value']=row['final_target_weight']['value']
    when=bundle['stock_evidence']['as_of']
    framework['drift_snapshot']['as_of']=when
    framework['drift_snapshot']['denominator'].update(amount=1000,currency='USD',as_of=when)
    refresh_snapshot(req,ctx)
    prepared=prepare_input(req,trusted_context=ctx)
    ctx['native_binding']={'schema_version':'Family.W5.NativeBinding.v1','request_digest':prepared.input_digest,
        'bundle_digest':digest(bundle),'target_binding_digest':prepared.payload['target_binding']['binding_digest'],
        'family_owner':deepcopy(req['owner']),'native_owner':deepcopy(w3['owner']),
        'data_provenance':'SYNTHETIC','source_reference':'SYNTHETIC_DISPATCH_TEST_ONLY'}
    ctx['native_binding']['stock_instrument']={'instrument_key':'VT_KEY','asset_id':'QQQ',
        'account_key':req['owner']['account'],'native_owner':deepcopy(w3['owner']),
        'source_reference':'SYNTHETIC_W1_INSTRUMENT'}
    ctx['native_binding']['bond_instruments']={asset:{'instrument_key':asset+'_KEY',
        'account_key':req['owner']['account'],'native_owner':deepcopy(w3['owner']),
        'exchange':'ARCA','source_reference':'SYNTHETIC_W1_BOND'} for asset in ('SGOV','SPSB')}
    ctx['funding_source']={'c7_funding_context':deepcopy(bundle['stock_request']['c7_funding_context']),
        'owner_binding':{'family_owner':deepcopy(req['owner']),'native_owner':deepcopy(w3['owner']),
            'currency':'USD','version':req['expected_versions']['funding'],'source_reference':'SYNTHETIC_C7_SOURCE'}}
    ctx['valuation_source']={'prices':{
        'QQQ':{'instrument_key':'VT_KEY','value':'10','currency':'USD','state':'KNOWN','unit':'CURRENCY_PER_SHARE',
            'as_of':bundle['stock_evidence']['as_of'],'source_reference':'SYNTHETIC_QQQ_QUOTE'},
        'SGOV':{'instrument_key':'SGOV_KEY','value':'120','currency':'USD','state':'KNOWN','unit':'CURRENCY_PER_SHARE',
            'as_of':bundle['physical_sgov']['as_of'],'source_reference':'SYNTHETIC_SGOV_QUOTE'},
        'SPSB':{'instrument_key':'SPSB_KEY','value':'50','currency':'USD','state':'KNOWN','unit':'CURRENCY_PER_SHARE',
            'as_of':bundle['physical_sgov']['as_of'],'source_reference':'SYNTHETIC_SPSB_QUOTE'}},
        'portfolio_nav':{'value':'1000','currency':'USD','state':'KNOWN','as_of':when,'source_reference':'SYNTHETIC_C_NAV'}}
    req['valuation_digest']=digest(ctx['valuation_source'])
    ctx['native_binding']['request_digest']=digest(req)
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
