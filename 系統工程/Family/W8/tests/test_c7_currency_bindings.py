from copy import deepcopy
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from deployment_c7_sources import reference_currencies


def case():
    request={'owner':{'currency':'USD'},'client_snapshot':{'payload':{'tables':{
        'portfolio_instrument':[{'ticker':'HELD','quote_currency':'USD'},{'ticker':'VT','quote_currency':None}]}}}}
    analysis={'qualified_equity_inputs':{'items':{'VT':{'symbol':'VT',
        'technical_source_template':{'metadata':{'currency':'USD'}}}}},
        'v75_macro_inputs':{'qualified_bond_markets':{'SPSB':{'symbol':'SPSB','currency':'USD'}}}}
    return request,analysis


def test_unheld_targets_use_existing_verified_market_reference_units():
    request,analysis=case();before=deepcopy((request,analysis));values,bindings=reference_currencies(request,analysis)
    assert values=={'HELD':'USD','VT':'USD','SPSB':'USD'}
    assert (request,analysis)==before
    assert bindings['SPSB']['source_fields'][0]['field_path'].endswith('SPSB.currency')
    assert not bindings['VT']['registry_written']


def test_account_currency_cannot_fill_unknown_assets_and_conflicts_remain_explicit():
    request,analysis=case();request['client_snapshot']['payload']['tables']['portfolio_instrument'].append({'ticker':'UNKNOWN'})
    values,_=reference_currencies(request,analysis);assert 'UNKNOWN' not in values
    request['client_snapshot']['payload']['tables']['portfolio_instrument'][1]['quote_currency']='TWD'
    values,bindings=reference_currencies(request,analysis)
    assert values['VT'] is None and bindings['VT']['status']=='CONFLICT'
