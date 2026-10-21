"""Synthetic fault-injection tests; real source review is a separate runner step."""
import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_official_sources import compare, schedule, verify


def sample():
    review = {'retrieval_date': '2026-10-21', 'instrument': {'symbol': 'TEST'},
              'window': {'start': '2026-03-06', 'end': '2026-03-09'},
              'calendar': {'year': 2026, 'timezone': 'America/New_York',
                           'regular_close': '16:00', 'holidays': ['2026-12-25'],
                           'early_closes': {'2026-12-24': '13:00'}},
              'dividends': {'2026-03-09': '1.87'},
              'split_event': {'provider_event_date': '2013-10-24', 'new_per_old': '0.5'}}
    rows = [{'Date': '2013-10-24', 'Dividends': '0', 'Stock Splits': '0.5'},
            {'Date': '2026-03-06', 'Dividends': '0', 'Stock Splits': '0'},
            {'Date': '2026-03-09', 'Dividends': '1.872', 'Stock Splits': '0'}]
    return review, rows


def test_bounded_pass_retains_unverified_flags_and_dst():
    review, rows = sample()
    result = compare(rows, review)
    assert result['calendar_sessions_matched'] == 2
    assert [s['scheduled_close_at'] for s in result['scheduled_sessions']] == [
        '2026-03-06T21:00:00+00:00', '2026-03-09T20:00:00+00:00']
    assert result['decision_eligible'] is False
    assert result['historical_ready'] is False
    assert result['per_bar_publication_verified'] is False
    assert result['full_adjustment_basis_verified'] is False


def test_holiday_early_close_and_outside_coverage():
    review, _ = sample()
    assert schedule(review['calendar'], '2026-12-24', '2026-12-27') == [
        {'session': '2026-12-24', 'scheduled_close_at': '2026-12-24T18:00:00+00:00'}]
    with pytest.raises(ValueError, match='COVERAGE'):
        schedule(review['calendar'], '2025-12-31', '2026-01-02')


@pytest.mark.parametrize('fault,code', [('missing', 'SESSION_SET'), ('weekend', 'SESSION_SET'),
    ('duplicate', 'DUPLICATE'), ('dividend', 'PRECISION'), ('extra_dividend', 'EVENT_SET'), ('split', 'SPLIT_RATIO')])
def test_source_disagreements_rejected(fault, code):
    review, rows = sample()
    if fault == 'missing': rows.pop(1)
    elif fault == 'weekend': rows[1]['Date'] = '2026-03-07'
    elif fault == 'duplicate': rows.insert(1, deepcopy(rows[1]))
    elif fault == 'dividend': rows[-1]['Dividends'] = '1.89'
    elif fault == 'extra_dividend': rows[1]['Dividends'] = '1'
    elif fault == 'split': rows[0]['Stock Splits'] = '2'
    with pytest.raises(ValueError, match=code): compare(rows, review)


@pytest.mark.parametrize('fault,code', [('review', 'REVIEW_DIGEST'), ('csv', 'CSV_DIGEST'),
    ('artifact', 'ARTIFACT_CHANGED')])
def test_pinned_files_reject_tampering(tmp_path, fault, code):
    review, rows = sample()
    csv_path = tmp_path / 'history.csv'
    with csv_path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    artifact = tmp_path / 'source.txt'; artifact.write_text('synthetic fixture')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    review.update(csv_sha256=sha(csv_path), artifacts=[{'file': artifact.name, 'sha256': sha(artifact)}])
    config = tmp_path / 'review.json'; config.write_text(json.dumps(review)); pin = sha(config)
    assert verify(csv_path, tmp_path, pin)['status'] == 'PASS_BOUNDED_SOURCE_REVIEW'
    target = {'review': config, 'csv': csv_path, 'artifact': artifact}[fault]
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError, match=code): verify(csv_path, tmp_path, pin)
