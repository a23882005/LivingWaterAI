from copy import deepcopy
import pytest
from family_runner import FamilyRunner
from family_input import digest
from test_family_end_to_end import full_family_case
from test_technical_source_bridge import case
from technical_source_bridge import NAMES
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def integrated_case():
    r,c=full_family_case();rows,m=case()
    m.update(asset_id='QQQ',symbol='QQQ',exchange='NASDAQ',evaluation_mode='SNAPSHOT_AFTER_ACQUISITION')
    c['technical_source']={'client_id':r['client_id'],'family_owner':deepcopy(r['owner']),'history':rows,'metadata':m}
    c['technical_source']['synthetic_complete_predicates']={g:['TRUE' if g=='right_signals' else 'FALSE']*len(names) for g,names in NAMES.items()}
    c['technical_source']['synthetic_complete_predicates']['ma20_ok']='TRUE'
    r['technical_source_digest']=digest(c['technical_source'])
    r['native_bundle']['stock_evidence'].update(left_buy_point='TRUE',left_stage='L1')
    refresh(r,c)
    return r,c


def test_producer_adapter_actual_runtime_and_mentor():
    r,c=integrated_case();out=FamilyRunner(ROOT,context_provider=lambda:c).analyze(r)
    assert out['status']=='OK',out
    assert out['technical_intake']['td9']['high_count']==9
    assert out['technical_intake']['native_technical_aggregation']['runaway_up']=='UNKNOWN'
    assert out['native_result']['funding_aggregate']['bond_used']=='160.00'
    assert out['mentor'] and out['data_provenance']=='SYNTHETIC'
    assert 'V82.evaluate_core_rule_state' in out['call_trace']
    assert 'C8C9.Work9.build_unified_deployment' in out['call_trace']
    assert out['trade_action']=='NO_TRADE'


@pytest.mark.parametrize('cause',['split','calendar','source_swap','owner'])
def test_actual_producer_safe_rejection(cause):
    r,c=integrated_case()
    if cause=='split':c['technical_source']['metadata']['split_basis_verified']=None
    if cause=='calendar':c['technical_source']['metadata'].pop('calendar_sessions')
    if cause=='owner':c['technical_source']['client_id']='other-client'
    if cause!='source_swap':r['technical_source_digest']=digest(c['technical_source']);refresh(r,c)
    else:c['technical_source']['metadata']['source_reference']='changed'
    out=FamilyRunner(ROOT,context_provider=lambda:c).analyze(r)
    assert out['status'] in ('DATA_UNAVAILABLE','BLOCKED'),out
    assert out['mentor'] is None and out['trade_action']=='NO_TRADE'


def test_snapshot_uses_acquisition_boundary_without_historical_time_claim():
    from technical_source_bridge import build_partial_technical
    rows,m=case();m.update(evaluation_mode='SNAPSHOT_AFTER_ACQUISITION')
    for receipt in m['bar_receipts']:
        receipt.pop('close_at');receipt.pop('available_at')
    before=deepcopy(m)
    out=build_partial_technical(rows,metadata=m,evaluated_at='2026-04-02T00:00:00Z',repo_path=ROOT)
    assert out['status']=='PARTIAL_KNOWN' and out['historical_pit_verified'] is False
    assert out['td9']['events'][0]['available_at']==m['artifact_written_at']
    assert m==before and out['source_metadata']==m
    early=build_partial_technical(rows,metadata=m,evaluated_at='2026-03-01T00:00:00Z',repo_path=ROOT)
    assert early['status']=='DATA_UNAVAILABLE'
    assert 'SNAPSHOT_NOT_YET_AVAILABLE' in early['issue_codes']


def test_partial_known_signals_preserved_and_unknown_not_promoted():
    from family_technical_bridge import bind_technical_source,apply_technical_source
    r,c=integrated_case();c['technical_source'].pop('synthetic_complete_predicates')
    r['technical_source_digest']=digest(c['technical_source']);refresh(r,c)
    source=bind_technical_source(ROOT,r,c);bundle=apply_technical_source(r['native_bundle'],source)
    assert 'TRUE' in bundle['stock_evidence']['core']['right_signals']
    assert 'UNKNOWN' in bundle['stock_evidence']['core']['right_signals']
    assert bundle['stock_evidence']['core']['ma20_ok']=='UNKNOWN'
    result=FamilyRunner(ROOT,context_provider=lambda:c).analyze(r)
    assert result['status']!='OK' and result['mentor'] is None


@pytest.mark.parametrize('client',['SYNTHETIC_A','SYNTHETIC_B','SYNTHETIC_C','SYNTHETIC_D'])
def test_four_clients_reject_foreign_technical_source(client):
    r,c=integrated_case();c['technical_source']['family_owner']['client_id']=client
    r['technical_source_digest']=digest(c['technical_source']);refresh(r,c)
    runner=FamilyRunner(ROOT,context_provider=lambda:c);out=runner.analyze(r)
    assert out['status']=='BLOCKED' and out['issue_codes'][0]['code']=='TECHNICAL_SOURCE_OWNER_MISMATCH'
    assert out['mentor'] is None


def test_computed_result_rejects_technical_source_changed_on_replay():
    r,c=integrated_case();runner=FamilyRunner(ROOT,context_provider=lambda:c)
    assert runner.analyze(r)['status']=='OK'
    c['technical_source']['metadata']['source_reference']='REPLACED'
    result=runner.analyze(r)
    assert result['status']=='BLOCKED' and result['mentor'] is None


@pytest.mark.parametrize('region,boundary',[('global','2026-10-19T23:20:09Z'),('taiwan','2026-10-20T07:14:26Z')])
def test_real_snapshot_exact_boundary_and_unknown_metadata(region,boundary):
    from datetime import datetime,timedelta
    from technical_source_bridge import build_partial_technical
    rows,m=case();m.update(data_provenance='SOURCE_BACKED',evaluation_mode='SNAPSHOT_AFTER_ACQUISITION',market_region=region,split_basis_verified=None,artifact_written_at=boundary,fetch_completed_at=boundary)
    before=(datetime.fromisoformat(boundary.replace('Z','+00:00'))-timedelta(seconds=1)).isoformat()
    early=build_partial_technical(rows,metadata=m,evaluated_at=before,repo_path=ROOT)
    at=build_partial_technical(rows,metadata=m,evaluated_at=boundary,repo_path=ROOT)
    assert 'SNAPSHOT_NOT_YET_AVAILABLE' in early['issue_codes']
    assert 'SNAPSHOT_NOT_YET_AVAILABLE' not in at['issue_codes']
    assert at['sample_state']=='UNKNOWN' and at['snapshot_available_at']==boundary
    assert all(x['truth']=='UNKNOWN' for g in at['signals'].values() for x in g)
