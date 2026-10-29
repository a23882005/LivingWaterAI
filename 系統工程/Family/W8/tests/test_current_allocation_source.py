from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
from current_allocation_source import build


def case():
    owner = {'client_id': 'SYNTHETIC', 'account': 'A', 'currency': 'USD'}
    at = '2026-10-29T10:00:00Z'
    request = {'client_id': 'SYNTHETIC', 'run_id': 'RUN', 'owner': owner, 'evaluation_at': at,
        'client_snapshot': {'payload': {'source_sha256': 'a' * 64,
            'tables': {'portfolio_account': [{'account_key': 'A'}, {'account_key': 'B'}]}}}}
    position = {'instrument_key': 'ETF', 'quantity': '2', 'quantity_state': 'KNOWN',
        'source_position': {'as_of_utc': '2026-10-28T20:00:00Z'},
        'source_instrument': {'ticker': 'ETF', 'quote_currency': 'USD'}}
    report = {k: deepcopy(request[k]) for k in ('client_id', 'run_id', 'owner')}
    report.update(source_db_sha256='a' * 64,
        analysis_result={'positions': [{'instrument_id': 'ETF', 'symbol': 'ETF', 'owner': owner,
            'position_valuation_allowed': True, 'market': {'instrument_key': 'ETF',
                'observed_close': '10.25', 'observed_date': '2026-10-28', 'source_sha256': 'b' * 64,
                'provider_verified_at': '2026-10-29T09:00:00Z'}}]},
        cash_trial={'owner': owner, 'decimal_values': {'total': '3.10'},
            'formal_sources': {'total': {'source_reference': 'SYNTHETIC_CASH'}}, 'assumptions': []})
    return request, report, SimpleNamespace(payload={'positions': [position]}), {}


def test_dated_exact_account_values_never_masquerade_as_global_nav_or_available_cash():
    args = case(); before = deepcopy(args)
    out = build(*args)
    assert out['known_security_subtotal'] == '20.50'
    assert out['account_asset_reference']['value'] == '23.60'
    assert out['other_accounts'] == ['B']
    assert out['portfolio_nav']['state'] == 'UNKNOWN'
    assert not out['reported_cash']['executable_budget']
    assert not out['latest_market_freshness_asserted']
    assert out['positions'][0]['price']['price_observation_as_of'] == '2026-10-28T00:00:00Z'
    assert args == before


@pytest.mark.parametrize('kind', ['quantity', 'price', 'currency', 'cash', 'fx'])
def test_missing_value_or_zero_trial_cannot_create_a_complete_denominator(kind):
    request, report, prepared, ctx = case()
    if kind == 'quantity': prepared.payload['positions'][0]['quantity_state'] = 'UNKNOWN'
    elif kind == 'price': report['analysis_result']['positions'][0]['market']['observed_close'] = None
    elif kind == 'currency': prepared.payload['positions'][0]['source_instrument']['quote_currency'] = None
    elif kind == 'fx': prepared.payload['positions'][0]['source_instrument']['quote_currency'] = 'TWD'
    else: report['cash_trial']['assumptions'] = [{'field_path': 'cash_state.total'}]
    out = build(request, report, prepared, ctx)
    assert out['account_asset_reference']['state'] == 'UNKNOWN'
    assert out['issues'] and out['portfolio_nav']['value'] is None


@pytest.mark.parametrize('kind', ['owner', 'duplicate', 'future', 'negative'])
def test_identity_coverage_time_and_numeric_substitution_is_rejected(kind):
    request, report, prepared, ctx = case()
    if kind == 'owner': report['owner']['account'] = 'OTHER'
    elif kind == 'duplicate': report['analysis_result']['positions'] *= 2
    elif kind == 'future': report['analysis_result']['positions'][0]['market']['provider_verified_at'] = '2026-10-30T00:00:00Z'
    else: report['analysis_result']['positions'][0]['market']['observed_close'] = '-1'
    with pytest.raises((PermissionError, ValueError)):
        build(request, report, prepared, ctx)
