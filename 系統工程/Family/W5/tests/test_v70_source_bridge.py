from copy import deepcopy
from decimal import Decimal
import pytest
from family_runner import FamilyRunner
from family_input import digest
from v70_source_bridge import project_v70_context
from stock_engine import run_stock_engine
from bond_engine import run_bond_engine
from test_family_runner import runner_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def apply_source(req,ctx):
    projected=project_v70_context(ctx['v70_source']['context'],req['run_id'])
    for branch in ('stock_request','bond_request'):
        req['native_bundle'][branch]['work3_handoff']['v70_runtime_context']=deepcopy(projected)
    snapshot=req['native_bundle']['bond_request']['v75_source_context']['v70_snapshot']
    snapshot.update(payload=deepcopy(projected['payload']),data_timestamp=projected['snapshot_as_of'],
                    source_lineage=deepcopy(projected['source_reference_ids']))
    req['v70_source_digest']=digest(ctx['v70_source']);refresh(req,ctx)


@pytest.mark.parametrize('blocked',[False,True])
def test_upstream_run_is_preserved_while_actual_engines_use_family_envelope(blocked):
    req,ctx=runner_case();raw=ctx['v70_source']['context']
    raw['run_id']=raw['payload']['run_id']='SYNTHETIC_UPSTREAM_PREVIOUS_BATCH'
    if blocked:raw['payload']['issue_codes']=['EXCEEDS_CAP']
    before=deepcopy(raw);apply_source(req,ctx)
    prepared,_=FamilyRunner(ROOT,context_provider=lambda:ctx)._validate(req)
    bound=prepared.payload['family_sources']['v70'];b=req['native_bundle']
    stock=run_stock_engine(ROOT,b['stock_request'],b['stock_evidence'],b['producer_contract'])
    bond=run_bond_engine(ROOT,b['bond_request'],b['bond_evidence'],prepared.payload['family_sources']['bond'])
    assert stock['execution'].execution_amount==Decimal(0 if blocked else 450)
    assert sum(Decimal(x['deploy_amount']['amount']) for x in bond['runtime_ready']['output']['per_asset_decisions'])==Decimal(0 if blocked else 350)
    assert bound['source_run_id']=='SYNTHETIC_UPSTREAM_PREVIOUS_BATCH'
    assert bound['analysis_run_id']==req['run_id']
    assert raw==before==bound['original_source']['context']
    assert bound['projected_context']['payload']['issue_codes']==raw['payload']['issue_codes']
    assert bound['tactical_caps']['equity']['source_amount']=='450.00'


@pytest.mark.parametrize('kind,code',[
    ('missing','V70_TACTICAL_SOURCE_REQUIRED'),('version','V70_SOURCE_DIGEST_MISMATCH'),
    ('producer','V70_SOURCE_PROVENANCE_REQUIRED'),('owner','V70_SOURCE_OWNER_MISMATCH'),
    ('run','V70_SOURCE_RUN_MISMATCH'),('snapshot','V70_SOURCE_LINEAGE_REQUIRED'),
    ('future','V70_FUTURE_SOURCE'),('stock_amount','V70_NATIVE_PROJECTION_MISMATCH'),
    ('bond_copy','V70_BOND_SNAPSHOT_MISMATCH'),('quality','TACTICAL_VALUE_NOT_KNOWN')])
def test_source_problems_stop_native_dispatch(kind,code,monkeypatch):
    req,ctx=runner_case();source=ctx['v70_source'];raw=source['context']
    if kind=='missing':ctx.pop('v70_source')
    elif kind=='version':source['version']='2'
    elif kind=='producer':source['producer']=''
    elif kind=='owner':source['family_owner']['account']='OTHER'
    elif kind=='run':raw['payload']['run_id']='OTHER'
    elif kind=='snapshot':raw['upstream_v70_snapshot_id']=''
    elif kind=='future':raw['snapshot_as_of']='2027-01-01T00:00:00Z'
    elif kind=='stock_amount':req['native_bundle']['stock_request']['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']='999'
    elif kind=='bond_copy':req['native_bundle']['bond_request']['v75_source_context']['v70_snapshot']['payload']['bond_tactical_amount']='999'
    else:raw['payload']['value_state']='UNKNOWN';apply_source(req,ctx)
    if kind not in ('missing','version'):req['v70_source_digest']=digest(source)
    refresh(req,ctx);calls=[]
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *a:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['issue_codes'][0]['code']==code and calls==[]


def test_staging_replay_revalidates_current_v70_source_before_cached_publication():
    req,ctx=runner_case();runner=FamilyRunner(ROOT,context_provider=lambda:ctx);calls=[]
    def compute(r):calls.append(1);return {'marker':'SYNTHETIC_CACHE_TEST','trade_action':'NO_TRADE'}
    first=runner.store.analyze(req,validate=runner._validate,compute=compute)
    assert first['result']=={'marker':'SYNTHETIC_CACHE_TEST','trade_action':'NO_TRADE'}
    ctx['v70_source']['version']='REPLACED_SOURCE_VERSION'
    from family_boundary import BoundaryError
    with pytest.raises(BoundaryError,match='V70_SOURCE_DIGEST_MISMATCH'):
        runner.store.analyze(req,validate=runner._validate,compute=compute)
    assert calls==[1]
