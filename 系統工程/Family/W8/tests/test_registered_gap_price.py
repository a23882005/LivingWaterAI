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


def test_observed_runaway_down_needs_current_registered_source_and_distinct_votes():
    from member_v82_analysis import normal_buy_pause
    def vote(name): return {'name': name, 'truth': 'TRUE', 'reason': 'APPROVED_V10_COMPUTED'}
    row = {'symbol':'TEST', 'holding':{'current_broker_position':{'quantity':'2'}},
           'same_run_gap_price':{'source_sha256':'original', 'run_id':'run', 'evaluation_at':'2026-11-21T12:00:00Z',
                                 'session':'2026-11-20', 'currency':'USD'},
           'core_observation':{'source_sha256':'original', 'result':{'technical':{'runaway_down':'TRUE'}}},
           'market':{'approved_technical':{'signals':{'down_break':[vote('D1')], 'down_accel':[vote('A1'),vote('A2')]}}}}
    pause = normal_buy_pause(row)
    assert pause['quantity'] == '0' and pause['target_and_gap_preserved'] and not pause['sell_intent_created']
    row['core_observation']['result']['technical']['runaway_down']='UNKNOWN'
    assert normal_buy_pause(row) is None
    row['core_observation']['result']['technical']['runaway_down']='TRUE'
    row['market']['approved_technical']['signals']['down_accel']=[vote('A1'),vote('A1')]
    assert normal_buy_pause(row) is None


def test_scoped_broker_quantity_preserves_unmapped_book_and_rejects_wrong_connection(tmp_path):
    import json
    from hashlib import sha256
    from current_market_contract import compare_broker_quantity
    def saved(name,data):
        f=tmp_path/name
        f.write_text(json.dumps(data))
        return {'local_path':str(f),'sha256':sha256(f.read_bytes()).hexdigest()}
    owner={'client_id':'client','broker':'IBKR','account':'one','currency':'USD'}
    auth=saved('auth.json',{'client_id':'client','owner':owner,'scope':'READ_ONLY_RECONCILIATION_AND_ADVICE',
                            'trade_authorization':'NONE','recorded_at':'2026-11-01T12:00:00Z'})
    positions=saved('original.json',{'tool':'interactive_brokers_ibkr_get_account_positions','arguments':{},
        'retrieval_recorded_at':'2026-11-21T10:00:00Z','response':{'positions':[{'contract_id':99,
        'contract_description':'TEST','currency':'USD','asset_class':'STK','position':60}]}})
    source={'client_id':'client','source_db_sha256':'db','contract_ids':{'TEST':99},'owner_authorization':auth,
            'current_positions':{**positions,'owner_authorization_sha256':auth['sha256']}}
    request={'client_id':'client','evaluation_at':'2026-11-21T10:03:00Z','client_snapshot':{'payload':{'source_sha256':'db'}}}
    result=compare_broker_quantity(source,{'quantity':'17','quantity_state':'KNOWN'},'TEST',request)
    assert result['current_broker_position']['quantity']=='60' and result['current_broker_position']['owner']==owner
    assert result['quantity'] is None and result['prior_reported_quantity']=='17'
    source['current_positions']['owner_authorization_sha256']='foreign'
    with pytest.raises(PermissionError):
        compare_broker_quantity(source,{'quantity':'17'},'TEST',request)
