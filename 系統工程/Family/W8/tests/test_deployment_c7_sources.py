"""Original Work6/Work7 refusals and lineage survive the source boundary."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5'), str(HERE.parent/'W5/tests')]
import configuration_source
import family_runner
from c7_engine import run_c7_engine, bind_c7_source
from family_boundary import BoundaryError
from family_input import digest
from test_c7_engine import original_case, source_case
from test_family_runner import runner_case
from deployment_c7_sources import current_sgov_roles


def blocked_source(monkeypatch):
    source, _ = original_case()
    canonical = deepcopy(source['canonical_input'])
    canonical['allocations']['current_allocation'] = {
        'value_state': 'UNKNOWN', 'snapshot': None, 'reason': 'Other account source not acquired'}
    adjustment = {'contract_name': 'LivingWaterAI.C.Work6.AdjustmentRequest',
        'contract_version': 'C-W6-v1.0.0', 'adjustment_id': 'SYNTHETIC-REVIEW',
        'requested_change_types': ['REVIEW_ONLY'], 'weight_overrides': [], 'preference_decisions': [],
        'confirmation': {'action': 'KEEP_PENDING', 'client_explicit_decision': 'UNKNOWN',
            'confirmed_at': None, 'confirmed_by': None, 'source_reference_ids': []},
        'radar_scores': [], 'source_references': [], 'source_reference_ids': []}
    # The missing Current branch must stop inside the original Work6 before
    # Work5 reads a workbook. This is a labelled synthetic contract test.
    monkeypatch.setattr(configuration_source, 'benchmark_source', lambda *args: {'binding': {}})
    work6_source = {'canonical_input': canonical, 'adjustment_request': adjustment,
        'benchmark_source': {'local_path': 'SYNTHETIC_NOT_READ.xlsx'},
        'evaluated_at': source['evaluated_at']}
    computed = configuration_source.run_work6_engine(ROOT, work6_source)
    source.update(canonical_input=canonical, work6_source=work6_source, work6_result=computed['result'])
    return source


def test_missing_global_current_reaches_original_work6_and_full_c7_without_a_fabricated_final(monkeypatch):
    source = blocked_source(monkeypatch)
    assert source['work6_result']['loop_status'] == 'BLOCKED'
    assert source['work6_result']['confirmation_status'] == 'PENDING'
    assert source['work6_result']['drift_snapshot']['value_state'] == 'NONE'
    result = run_c7_engine(ROOT, source)['result']
    assert result['status'] == 'BLOCKED'
    assert result['integrated_asset_framework']['value_state'] == 'NONE'
    assert 'C_W7_UPSTREAM_WORK6_BLOCKED' in {x['code'] for x in result['issues']}


def test_changed_work6_result_cannot_become_a_source_backed_c7_input(monkeypatch):
    source = blocked_source(monkeypatch)
    source['work6_result']['confirmation_status'] = 'CONFIRMED'
    with pytest.raises(BoundaryError, match='C7_WORK6_REPLAY_MISMATCH'):
        run_c7_engine(ROOT, source)


def test_source_backed_c7_requires_work6_replay_source():
    req, ctx = source_case()
    ctx['native_binding']['data_provenance'] = 'SOURCE_BACKED'
    with pytest.raises(BoundaryError, match='C7_WORK6_SOURCE_REQUIRED'):
        bind_c7_source(ROOT, req, ctx)


def test_original_c7_refusal_precedes_consumers_of_missing_target_and_drift(monkeypatch):
    req, ctx = runner_case()
    def refused(*args):
        raise BoundaryError('C7_FRAMEWORK_NOT_READY', 'c7.status', status='DATA_UNAVAILABLE')
    def downstream(*args):
        pytest.fail('Protection must not consume an unavailable C7 target')
    monkeypatch.setattr(family_runner, 'bind_c7_source', refused)
    monkeypatch.setattr(family_runner, 'bind_stock_protection', downstream)
    result = family_runner.FamilyRunner(ROOT, context_provider=lambda: ctx).analyze(req)
    assert result['status'] == 'DATA_UNAVAILABLE'
    assert result['issue_codes'][0]['code'] == 'C7_FRAMEWORK_NOT_READY'
    assert result['mentor'] is None


def test_an_unpinned_workbook_cannot_authorize_its_own_source_contract(tmp_path):
    path = tmp_path/'標的績效基準資料.xlsx'
    path.write_bytes(b'SYNTHETIC_INVALID_WORKBOOK')
    with pytest.raises(PermissionError, match='CONFIGURATION_BENCHMARK_SOURCE_MISMATCH'):
        configuration_source.benchmark_source(ROOT, {'local_path': str(path),
            'drive_file_id': '1vbaPznrzrDwZ17AeLXSLJErMrXwxPl1-', 'sha256': digest('fake')},
            '2026-10-29T10:00:00Z')


def test_single_role_sgov_can_be_revalued_without_shifting_any_shares_between_roles():
    roles = {'sgov_bond_bucket_amount': {'amount': '0'}, 'sgov_dry_powder_bucket_amount': {'amount': '1409.94'}}
    result = current_sgov_roles(roles, '1409.94', Decimal('1409.80'))
    assert result == [('SGOV_BOND', 'bond ETF', Decimal(0)), ('SGOV_DRY', 'cash', Decimal('1409.80'))]
    assert roles['sgov_dry_powder_bucket_amount']['amount'] == '1409.94'


def test_mixed_sgov_roles_cannot_be_split_using_weights_or_price_ratios():
    roles = {'sgov_bond_bucket_amount': {'amount': '600'}, 'sgov_dry_powder_bucket_amount': {'amount': '400'}}
    with pytest.raises(ValueError, match='MIXED_SGOV_ROLE_QUANTITIES_REQUIRED'):
        current_sgov_roles(roles, '1000', Decimal('1100'))
    with pytest.raises(PermissionError, match='SGOV_ROLE_VALUE_MISMATCH'):
        current_sgov_roles(roles, '999', Decimal('1100'))


def test_c7_refusal_retains_native_drift_review_without_claiming_unified_mentor(monkeypatch):
    source = blocked_source(monkeypatch)
    req, ctx = source_case()
    for key in ('schema_version', 'producer', 'version', 'source_reference', 'family_owner'):
        source[key] = deepcopy(ctx['c7_source'][key])
    ctx['c7_source'] = source; req['c7_source_digest'] = digest(source)
    with pytest.raises(BoundaryError, match='C7_FRAMEWORK_NOT_READY') as error:
        bind_c7_source(ROOT, req, ctx)
    result = family_runner.FamilyRunner._error(req, error.value.status, error.value.issue)
    assert result['mentor'] is None and result['canonical_result'] is None
    review = result['configuration_review']
    assert review['full_native_mentor_reached'] is False
    assert review['drift_snapshot'] == source['work6_result']['drift_snapshot']
    assert review['original_work6_mentor_contract'] == source['work6_result']['mentor_result_contract']
