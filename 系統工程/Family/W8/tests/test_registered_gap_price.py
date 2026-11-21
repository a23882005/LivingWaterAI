from copy import deepcopy
import pytest
from current_market_contract import gap_price


def source():
    request = {'client_id': 'member', 'run_id': 'run', 'evaluation_at': '2026-11-21T09:50:00Z'}
    instrument = {'client_id': 'member', 'ticker': 'TEST', 'instrument_key': 'approved-etf',
                  'identity_state': 'KNOWN', 'instrument_type': 'ETF', 'quote_currency': 'USD'}
    market = {'market_identity': {'provider_symbol': 'TEST', 'provider_type': 'ETF',
                                  'currency': 'USD', 'exchange': 'XNAS'}, 'source_sha256': 'pinned',
              'observed_close': 14, 'observed_date': '2026-11-20', 'latest_expected_completed_session': '2026-11-20',
              'completed_session_close_at': '2026-11-20T21:00:00Z', 'provider_verified_at': '2026-11-21T09:33:00Z'}
    registration = {'evaluation_day': '2026-11-21', 'instrument_key': 'approved-etf',
                    'source_sha256': 'pinned', 'exchange': 'XNAS', 'currency': 'USD'}
    contract = {'source_descriptor': {'gap_price_registrations': {'TEST': registration}},
                'official_bank_original_result': {'as_of': '2026-11-21'}}
    return contract, market, instrument, request


def test_latest_registered_close_separates_money_and_order_price():
    contract, market, instrument, request = source()
    proof = gap_price(contract, market, instrument, 'TEST', request)
    assert proof['scope'] == 'CURRENT_POSITION_EXPOSURE_ONLY'
    assert proof['observed_close'] == 14 and proof['run_id'] == request['run_id']
    assert gap_price(contract, market, instrument, 'OTHER', request) is None


@pytest.mark.parametrize('field,value', [('observed_date','2026-11-19'),
    ('provider_verified_at','2026-11-20T20:59:59Z'), ('provider_verified_at','2026-11-21T13:00:00Z')])
def test_stale_intraday_and_future_are_unqualified(field,value):
    contract, market, instrument, request = source()
    market[field] = value
    assert gap_price(contract,market,instrument,'TEST',request) is None


def test_same_ticker_listing_and_original_hash_are_bound():
    contract, market, instrument, request = source()
    for field,value in [('exchange','XLON'),('currency','GBP')]:
        other = deepcopy(market)
        other['market_identity'][field] = value
        with pytest.raises(PermissionError):
            gap_price(contract,other,instrument,'TEST',request)
    with pytest.raises(PermissionError):
        gap_price(contract,{**market,'source_sha256':'different'},instrument,'TEST',request)
    request['evaluation_at']='2026-11-22T09:50:00Z'
    assert gap_price(contract,market,instrument,'TEST',request) is None
