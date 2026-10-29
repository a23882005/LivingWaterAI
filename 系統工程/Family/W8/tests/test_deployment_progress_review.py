"""C7 routing retains real data/funding progress without minting a Mentor."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest

HERE = Path(__file__).resolve().parents[1]; ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5'), str(HERE.parent/'W5/tests')]
from family_input import digest
from family_boundary import BoundaryError
from c7_engine import bind_c7_source
from deployment_progress_review import build
from test_deployment_c7_sources import blocked_source
from test_c7_engine import source_case


def case():
    request = {'client_id': 'SYNTHETIC', 'run_id': 'SYNTHETIC-RUN',
        'owner': {'account': 'SYNTHETIC', 'broker': 'SYNTHETIC', 'currency': 'USD'},
        'evaluation_at': '2026-10-29T18:00:00Z', 'client_snapshot': {'payload': {'source_sha256': '0'*64}},
        'confirmed_target': {'schema_version': 'SYNTHETIC'}}
    identity = {k: deepcopy(request[k]) for k in ('client_id', 'run_id', 'owner')}
    identity['source_db_sha256'] = '0'*64
    funding = {**deepcopy(identity), 'conservation_status': 'BLOCKED_MISSING_NATIVE_DECISIONS',
        'claims': [], 'unresolved_decisions': [{'symbol': 'SYNTHETIC', 'amount': None}],
        'full_native_canonical_complete': False, 'joint_execution_authorized': False}
    funding['output_digest'] = digest(funding)
    analysis = {**identity, 'account_funding_check': funding,
        'v75_macro_inputs': {'additional_delta_handoff': {'sparse_yield_evidence': {
            'distinct_observations': 78, 'counts_by_metric': {'portfolio_ytm': 39, 'sec_yield_30day': 39},
            'weekly_history_available': False, 'engine_input_eligible': False}}}}
    analysis['report_digest'] = digest(analysis)
    return request, analysis


def test_menu_progress_separates_existing_sources_funding_unknowns_and_contract_routing():
    request, analysis = case(); before = deepcopy(analysis)
    out = build(ROOT, request, analysis, {'loop_status': 'FINAL_TARGET_CONFIRMED'},
        {'status': 'RETURN_TO_V70', 'residual_allocation': {'buckets': []}, 'issues': []}, ['bond_request', 'asset_framework'])
    assert analysis == before
    assert out['data_evidence']['SPSB']['sparse_yields']['distinct_observations'] == 78
    assert not out['data_evidence']['SPSB']['sparse_yields']['weekly_history_available']
    assert out['account_funding_check']['unresolved_decisions'][0]['amount'] is None
    assert out['formal_contract_state'] == 'RETURN_TO_V70_RECONFIRMATION_REQUIRED'
    assert out['missing_data_and_contract_routing_kept_separate']
    assert not out['full_native_mentor_reached'] and not out['full_native_pipeline_complete']
    assert out['configuration']['approval_changed'] is False
    assert out['configuration']['rule_reference']['function'] == '_build_residual_allocation'


def test_progress_refuses_cross_account_and_changed_funding_even_if_outer_report_is_resigned():
    request, analysis = case()
    analysis['account_funding_check']['owner']['account'] = 'OTHER'
    analysis['report_digest'] = digest({k:v for k,v in analysis.items() if k != 'report_digest'})
    with pytest.raises(PermissionError, match='FUNDING_IDENTITY'):
        build(ROOT, request, analysis, {}, {}, [])
    request, analysis = case(); analysis['account_funding_check']['claims'] = [{'amount': '100'}]
    analysis['report_digest'] = digest({k:v for k,v in analysis.items() if k != 'report_digest'})
    with pytest.raises(PermissionError, match='FUNDING_DIGEST'):
        build(ROOT, request, analysis, {}, {}, [])


def test_native_c7_error_retains_progress_and_rejects_swapped_scope(monkeypatch):
    source = blocked_source(monkeypatch); req, ctx = source_case()
    req['client_snapshot'] = {'payload': {'source_sha256': '0'*64}}
    for key in ('schema_version', 'producer', 'version', 'source_reference', 'family_owner'):
        source[key] = deepcopy(ctx['c7_source'][key])
    progress = {'schema_version': 'Family.W8.DeploymentProgressReview.v1',
        **{k: deepcopy(req[k]) for k in ('client_id', 'run_id', 'owner', 'evaluation_at')},
        'source_db_sha256': req['client_snapshot']['payload']['source_sha256'],
        'full_native_pipeline_complete': False, 'full_native_mentor_reached': False, 'trade_action': 'NO_TRADE'}
    progress['digest'] = digest(progress); source['continuation_review'] = progress
    ctx['c7_source'] = source; req['c7_source_digest'] = digest(source)
    with pytest.raises(BoundaryError, match='C7_FRAMEWORK_NOT_READY') as error:
        bind_c7_source(ROOT, req, ctx)
    assert error.value.issue['configuration_review']['deployment_progress'] == progress
    progress['owner']['account'] = 'OTHER'
    progress['digest'] = digest({k:v for k,v in progress.items() if k != 'digest'})
    req['c7_source_digest'] = digest(source)
    with pytest.raises(BoundaryError, match='CONTINUATION_REVIEW_BINDING'):
        bind_c7_source(ROOT, req, ctx)
