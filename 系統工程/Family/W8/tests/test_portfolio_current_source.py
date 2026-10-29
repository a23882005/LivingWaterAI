from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5')]
from portfolio_current_source import build, quote


def saved(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return {'local_path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}


def case(tmp_path):
    raw = saved(tmp_path/'raw.json', {'chart': {'result': [{'meta': {'symbol': '0050.TW',
        'currency': 'TWD', 'gmtoffset': 28800, 'currentTradingPeriod': {'regular': {'end': 1793246400}}},
        'timestamp': [1793235600], 'indicators': {'quote': [{'close': ['100']}]}}]}})
    receipt = saved(tmp_path/'receipt.json', {'sha256': raw['sha256'], 'http_status': 200,
        'retrieved_at': '2026-10-29T09:00:00Z', 'url': 'https://example.test/0050.TW'})
    instrument = {'instrument_key': 'TW0050', 'ticker': '0050', 'quote_currency': 'TWD'}
    market = {'schema_version': 'Family.W8.PortfolioMarketSource.v1', 'client_id': 'SYNTHETIC',
        'source_db_sha256': 'a'*64, 'items': {'TW0050': {'provider_symbol': '0050.TW',
            'raw': raw, 'receipt': receipt}}}
    descriptor = saved(tmp_path/'market.json', market)
    request = {'client_id': 'SYNTHETIC', 'run_id': 'RUN', 'evaluation_at': '2026-10-29T10:00:00Z',
        'owner': {'account': 'US', 'currency': 'USD'}, 'client_snapshot': {'payload': {
            'source_sha256': 'a'*64, 'tables': {'portfolio_account': [{'account_key': 'US'}, {'account_key': 'TW'}],
            'portfolio_instrument': [instrument], 'portfolio_position': [
                {'account_key': 'TW', 'instrument_key': 'TW0050', 'quantity_decimal': '1', 'as_of_utc': '2026-09-01T00:00:00Z'},
                {'account_key': 'TW', 'instrument_key': 'TW0050', 'quantity_decimal': '2', 'as_of_utc': '2026-10-01T00:00:00Z'}]}}}}
    selected = {'issues': [], 'positions': [{'instrument_id': 'US_ETF', 'symbol': 'ETF',
        'valuation': {'state': 'KNOWN', 'value': '20'}}], 'reported_cash': {'state': 'KNOWN', 'value': '3.10'},
        'portfolio_nav': {'state': 'UNKNOWN', 'value': None}}
    analysis = {'native_target_source': {'fx_observation': {'base_currency': 'USD', 'quote_currency': 'TWD',
        'quote_per_base': '10', 'as_of': '2026-10-28', 'source_url': 'https://example.test/fx'}},
        'cash_trial': {'scenario': {'authorization': {'missing_cash_value': '0', 'source_reference': 'SYNTHETIC_ZERO_TRIAL'}}}}
    sources = {'native_bundle': {'stock_request': {'c7_funding_context': {'contexts': [
        {'account': 'US'}, {'account': 'TW', 'brokerage_cash_state': {'total': 0}}]}}}}
    return request, analysis, selected, sources, descriptor, market, instrument


def test_latest_ledger_rows_fx_and_assumptions_are_conserved_without_a_nav_claim(tmp_path):
    args = case(tmp_path); before = deepcopy(args)
    out = build(*args[:5])
    assert out['denominator']['value'] == '43.10'
    assert len(out['positions']) == 4
    assert out['portfolio_nav']['state'] == 'UNKNOWN'
    assert len(out['cash_assumptions']) == 1
    assert out['cash_assumptions'][0]['scope'] == 'SIMULATION_ONLY__NOT_PROOF_OF_ZERO_CASH'
    assert not out['cross_account_funding_authorized']
    assert args == before


@pytest.mark.parametrize('kind', ['missing_quote', 'selected_gap'])
def test_missing_security_value_is_never_hidden_by_the_zero_cash_trial(tmp_path, kind):
    request, analysis, selected, sources, descriptor, market, instrument = case(tmp_path)
    if kind == 'missing_quote':
        market['items'] = {}; descriptor = saved(tmp_path/'market2.json', market)
    else: selected['issues'] = [{'code': 'PRICE_UNKNOWN'}]
    out = build(request, analysis, selected, sources, descriptor)
    assert out['denominator']['state'] == 'UNKNOWN' and out['issues']


@pytest.mark.parametrize('kind', ['identity', 'future', 'changed_bytes', 'account_scope'])
def test_wrong_identity_future_quote_bytes_or_account_scope_is_rejected(tmp_path, kind):
    request, analysis, selected, sources, descriptor, market, instrument = case(tmp_path)
    if kind == 'account_scope':
        sources['native_bundle']['stock_request']['c7_funding_context']['contexts'].pop()
        with pytest.raises(PermissionError, match='ACCOUNT_SCOPE'):
            build(request, analysis, selected, sources, descriptor)
        return
    if kind == 'identity': instrument['ticker'] = 'OTHER'
    elif kind == 'future': request['evaluation_at'] = '2026-10-28T00:00:00Z'
    else: Path(market['items']['TW0050']['raw']['local_path']).write_text('{}')
    with pytest.raises(PermissionError): quote(instrument, market, request['evaluation_at'])
