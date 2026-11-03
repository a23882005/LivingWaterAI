"""Synthetic PIT snapshots: explanations must never alter native finance."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import math
import sys
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '系統工程/Family/W8'))
sys.path.insert(0, str(ROOT / '系統工程/Family/W5'))
sys.path.insert(0, str(ROOT / '系統工程/Family/W5/tests'))
from test_v10_own_history import complete_price
from qp_anchor_diagnostic import capture_snapshot, diagnose, digest, price_percentile, time


def save(path, artifact):
    path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    return dict(local_path=str(path), sha256=sha256(path.read_bytes()).hexdigest())


def seal(artifact):
    artifact['snapshot_digest'] = digest({k: v for k, v in artifact.items() if k != 'snapshot_digest'})
    return artifact


def pair(case='A01', source=None):
    current = deepcopy(source) if source is not None else complete_price()
    current['comparable_from'] = '2012-01-01T00:00:00Z'
    bars = current['bars']
    for i, row in enumerate(bars[-253:]):
        row['close'] = str(85 + round(2 * math.sin(i / 7), 8))
    bars[-253]['close'] = '100'
    bars[-200]['close'] = '92'
    bars[-2]['close'] = '84' if case == 'A04' else '85'
    bars[-1]['close'] = '85'
    if case not in ('A03', 'A04'):
        bars[-150]['close'] = '100'
    if case == 'A02':
        bars[-1]['close'] = '105'
    if case in ('A05', 'A12'):
        bars[-1]['close'] = '100'
    if case == 'A12':
        bars[-100]['close'] = bars[-50]['close'] = '100'
    previous = deepcopy(current)
    previous['bars'] = previous['bars'][:-1]
    previous['calendar']['sessions'] = previous['calendar']['sessions'][:-1]
    previous['decision_at'] = (time(previous['calendar']['sessions'][-1]['knowledge_at'])
                               + timedelta(minutes=30)).isoformat()
    previous['calendar'].update(coverage_cutoff=previous['decision_at'],
                                last_completed_session=previous['bars'][-1]['session_id'])
    previous['actions'].update(available_at=previous['decision_at'],
                              coverage_end=previous['bars'][-1]['session_id'])
    current['previous_anchor'] = price_percentile(**previous)['current_stress']['anchor']
    # A separately captured later run has different acquisition hashes, while
    # its already-known history remains numerically and temporally identical.
    for row in current['bars']:
        row['source_hash'] = 'SYNTHETIC_LATER_ACQUISITION_HASH'
        row['retrieved_at'] = current['decision_at']
    return previous, current


def snapshots(tmp_path, case='A01', source=None):
    p, c = pair(case, source)
    previous = capture_snapshot(p, run_id='SYNTHETIC_PREVIOUS', saved_at=p['decision_at'],
                                source_reference='SYNTHETIC_NOT_MARKET_EVIDENCE:previous')
    current = capture_snapshot(c, run_id='SYNTHETIC_CURRENT', saved_at=c['decision_at'],
                               source_reference='SYNTHETIC_NOT_MARKET_EVIDENCE:current')
    return p, c, previous, current


def scenario(tmp_path, case, source=None):
    p, c, previous, current = snapshots(tmp_path, case, source)
    if case == 'A06':
        current['qP_result']['current_stress']['anchor'] = c['bars'][-3]['session_id']
        seal(current)
    elif case == 'A08':
        for item in (p['identity'], p['actions'], *p['bars']):
            item['listing'] = 'OTHER_SYNTHETIC_LISTING'
        previous = capture_snapshot(p, run_id='SYNTHETIC_PREVIOUS', saved_at=p['decision_at'], source_reference='SYNTHETIC')
    elif case == 'A09':
        previous['price_history_input']['calendar']['version'] = 'OTHER_CALENDAR_VERSION'
        previous['input_digest'] = digest(previous['price_history_input'])
        seal(previous)
    elif case == 'A10':
        p['bars'][-1]['available_at'] = c['decision_at']
        p['bars'][-1]['retrieved_at'] = c['decision_at']
        previous = capture_snapshot(p, run_id='SYNTHETIC_PREVIOUS', saved_at=c['decision_at'], source_reference='SYNTHETIC_LATE_REVISION')
    if case == 'A07':
        c.pop('previous_anchor')
        current = capture_snapshot(c, run_id='SYNTHETIC_CURRENT', saved_at=c['decision_at'], source_reference='SYNTHETIC')
    return p, c, previous, current


@pytest.mark.parametrize('case,reason,status,warnings', [
    ('A01', 'UNCHANGED', 'KNOWN', []),
    ('A02', 'NEW_HIGH', 'KNOWN', []),
    ('A03', 'OLD_HIGH_EXPIRED_ROLLDOWN', 'KNOWN', ['NO_PRICE_RECOVERY_OBSERVED']),
    ('A04', 'OLD_HIGH_EXPIRED_ROLLDOWN', 'KNOWN', []),
    ('A05', 'EQUAL_HIGH_REANCHOR', 'KNOWN', []),
    ('A06', 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE', 'UNKNOWN', []),
    ('A07', 'PREVIOUS_ANCHOR_UNKNOWN', 'UNKNOWN', []),
    ('A08', 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE', 'UNKNOWN', []),
    ('A09', 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE', 'UNKNOWN', []),
    ('A10', 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE', 'UNKNOWN', []),
    ('A11', 'UNCHANGED', 'KNOWN', []),
    ('A12', 'EQUAL_HIGH_REANCHOR', 'KNOWN', []),
])
def test_pm_golden_and_native_value_invariance(tmp_path, case, reason, status, warnings):
    p, c, previous, current = scenario(tmp_path, case)
    before = deepcopy(c)
    native_before = price_percentile(**c)
    assert native_before['status'] == 'COMPLETE'
    cd = save(tmp_path / 'current.json', current)
    pd = None if case == 'A07' else save(tmp_path / 'previous.json', previous)
    original_files = {x['local_path']: Path(x['local_path']).read_bytes() for x in (cd, pd) if x}
    result = diagnose(cd, pd)
    assert result == diagnose(cd, pd)
    assert (result['reason_code'], result['status'], result['warning_codes']) == (reason, status, warnings)
    assert result['anchor_change_is_recovery_evidence'] is False
    assert c == before and price_percentile(**c) == native_before
    assert all(Path(path).read_bytes() == content for path, content in original_files.items())
    if case in ('A03', 'A04'):
        assert Decimal(result['previous']['H']) == 100
        assert Decimal(result['current']['H']) == 92
        assert Decimal(result['current']['W']) == 85
        assert '含息財富W' in result['interpretation'] and '市價C' in result['interpretation']
    if case == 'A07':
        assert result['legacy_anchor_changed'] is False
    if case == 'A11':
        assert result['previous']['source_digest'] != result['current']['source_digest']
    if case == 'A12':
        assert result['current']['anchor_session'] == c['bars'][-1]['session_id']
    save(tmp_path / 'verified_result.json', dict(case=case, expected_reason=reason,
         expected_status=status, diagnostic=result, native_before=native_before,
         native_after=price_percentile(**c), native_exact_equal=True, source_files_unchanged=True))


@pytest.mark.parametrize('problem', [
    'file_hash', 'body_hash', 'input_hash', 'missing_history', 'missing_events',
    'gap', 'method', 'currency', 'share_class', 'calendar', 'regime',
    'revision', 'saved_after_current', 'retrieved_after_saved', 'cutoff',
])
def test_pinned_lineage_rejects_conflicts_without_business_mutation(tmp_path, problem):
    p, c, previous, current = snapshots(tmp_path)
    if problem == 'missing_history':
        current = capture_snapshot(None, run_id='SYNTHETIC', saved_at=c['decision_at'], source_reference='SYNTHETIC')
    elif problem in ('missing_events', 'gap'):
        if problem == 'missing_events': c['actions']['coverage_verified'] = False
        else: c['bars'].pop(-20)
        current = capture_snapshot(c, run_id='SYNTHETIC', saved_at=c['decision_at'], source_reference='SYNTHETIC')
    elif problem in ('method', 'currency', 'share_class'):
        key = dict(method='method_version', currency='currency', share_class='share_class')[problem]
        for row in (p['identity'], *p['bars']): row[key] = 'OTHER'
        if key in p['actions']: p['actions'][key] = 'OTHER'
        previous = capture_snapshot(p, run_id='SYNTHETIC', saved_at=p['decision_at'], source_reference='SYNTHETIC')
    elif problem in ('calendar', 'regime', 'revision'):
        if problem == 'calendar': p['calendar']['timezone'] = 'Etc/UTC'
        elif problem == 'regime': p['comparable_from'] = '2012-01-02T00:00:00Z'
        else: p['bars'][-40]['close'] = '91'
        previous = capture_snapshot(p, run_id='SYNTHETIC', saved_at=p['decision_at'], source_reference='SYNTHETIC')
    elif problem == 'saved_after_current':
        previous['saved_at'] = (time(c['decision_at']) + timedelta(seconds=1)).isoformat(); seal(previous)
    elif problem == 'retrieved_after_saved':
        previous['price_history_input']['bars'][-1]['retrieved_at'] = c['decision_at']
        previous['input_digest'] = digest(previous['price_history_input']); seal(previous)
    elif problem == 'cutoff':
        previous = deepcopy(current)
    elif problem == 'body_hash':
        previous['run_id'] = 'TAMPERED'
    elif problem == 'input_hash':
        previous['input_digest'] = 'bad'; seal(previous)
    cd, pd = save(tmp_path / 'current.json', current), save(tmp_path / 'previous.json', previous)
    if problem == 'file_hash': pd['sha256'] = '0' * 64
    before = deepcopy((p, c, previous, current))
    result = diagnose(cd, pd)
    assert result['status'] == 'UNKNOWN' and result['reason_code'] == 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE'
    assert result['missing_inputs']
    assert (p, c, previous, current) == before


@pytest.mark.parametrize('change', ['receipt_only', 'event_fact_revision', 'calendar_receipt_only'])
def test_receipts_may_change_but_historical_event_facts_may_not(tmp_path, change):
    p, c = pair()
    # Use a unique high: cash reinvestment has exact native Decimal rounding,
    # so two equal raw closes are not assumed to be equal wealth values.
    old_sid = c['bars'][-253]['session_id']
    for source in (p, c):
        next(row for row in source['bars'] if row['session_id'] == old_sid)['close'] = '99'
    event = dict(event_id='SYNTHETIC_CASH', kind='FIXED_NONOPTIONAL_CASH',
                 ex_session=p['bars'][-300]['session_id'], gross_cash_per_old_share='0.25',
                 currency='USD', available_at=p['bars'][-300]['available_at'],
                 retrieved_at=p['decision_at'], source_hash='SYNTHETIC_PREVIOUS_HASH')
    p['actions']['events'] = [deepcopy(event)]
    c['actions']['events'] = [deepcopy(event)]
    c['actions']['events'][0].update(retrieved_at=c['decision_at'], source_hash='SYNTHETIC_CURRENT_HASH')
    if change == 'event_fact_revision':
        c['actions']['events'][0]['gross_cash_per_old_share'] = '0.5'
    if change == 'calendar_receipt_only':
        for row in c['calendar']['sessions']:
            row['retrieved_at'] = c['decision_at']
    pd = save(tmp_path / 'previous.json', capture_snapshot(p, run_id='SYNTHETIC_PREVIOUS',
              saved_at=p['decision_at'], source_reference='SYNTHETIC'))
    cd = save(tmp_path / 'current.json', capture_snapshot(c, run_id='SYNTHETIC_CURRENT',
              saved_at=c['decision_at'], source_reference='SYNTHETIC'))
    result = diagnose(cd, pd)
    assert result['reason_code'] == ('INSUFFICIENT_OR_INCOMPARABLE_SOURCE'
                                    if change == 'event_fact_revision' else 'UNCHANGED')


@pytest.mark.parametrize('case', ['A%02d' % i for i in range(1, 13)])
def test_full_stock_stage_target_gap_permission_and_49_13_are_identical(tmp_path, case):
    from test_v10_stock_integration import adopted_case, bind_context
    from test_stock_engine import source_fields
    from stock_engine import run_stock_engine, assemble_stock_output, _plain
    req, facts, contract = adopted_case()
    source = complete_price(4000)
    cutoff = facts['evaluated_at']
    source['bars'] = [r for r in source['bars'] if time(r['available_at']) <= time(cutoff)]
    source['calendar']['sessions'] = [r for r in source['calendar']['sessions'] if time(r['knowledge_at']) <= time(cutoff)]
    for row in (source['identity'], source['actions'], *source['bars']):
        row.update(asset_id='QQQ', share_class='SYNTHETIC')
    source['decision_at'] = cutoff
    source['actions'].update(available_at=cutoff, coverage_end=source['bars'][-1]['session_id'])
    source['calendar'].update(coverage_cutoff=cutoff, last_completed_session=source['bars'][-1]['session_id'])
    source['comparable_from'] = '2012-01-01T00:00:00Z'
    p, source, previous, artifact = scenario(tmp_path, case, source)
    assert price_percentile(**source)['status'] == 'COMPLETE'
    facts['approved_v10_context']['price_history'] = source
    bind_context(facts, contract)
    inputs_before = deepcopy((req, facts, contract))
    before = run_stock_engine(ROOT, req, facts, contract)
    wire_before = assemble_stock_output(ROOT, before, source_fields())
    out = diagnose(save(tmp_path / 'stock.json', artifact),
                   None if case == 'A07' else save(tmp_path / 'previous.json', previous))
    after = run_stock_engine(ROOT, req, facts, contract)
    wire_after = assemble_stock_output(ROOT, after, source_fields())
    assert _plain(before) == _plain(after) and wire_before == wire_after
    canonical = wire_after['canonical_v82_output']
    assert len(canonical['canonical_analysis']) == 49 and len(canonical['fields_1_to_13']) == 13
    assert (req, facts, contract) == inputs_before
    save(tmp_path / 'business_invariant.json', dict(case=case, diagnostic=out,
         business_before=_plain(before), business_after=_plain(after),
         canonical_before=wire_before, canonical_after=wire_after,
         full_business_exact_equal=True, canonical_49_13_exact_equal=True))
