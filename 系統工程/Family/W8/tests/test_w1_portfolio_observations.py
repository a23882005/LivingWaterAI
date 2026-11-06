"""W1 source normalization regressions; all fixtures are synthetic business facts."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from w1_portfolio_observations import normalize, latest_rows, major_amount


def case():
    client='SYNTHETIC_CLIENT'
    req={'client_id':client,'evaluation_at':'2026-10-30T20:00:00Z',
        'confirmed_target':{'target_version':1},
        'client_snapshot':{'payload':{'client_id':client,'source_sha256':'a'*64,
            'tables':{'portfolio_account':[{'client_id':client,'account_key':'SYNTHETIC_US',
                'account_label':'IBKR USD INVESTMENT', 'account_currency':None}],
                'cash_balance_snapshot':[], 'portfolio_position':[]}}}}
    row={'client_id':client,'account_key':'SYNTHETIC_US','currency_code':'USD',
        'as_of_utc':'2026-10-20T12:00:00Z','version':1,'reported_cash_minor':12345,
        'normalized_settled_minor':10000,'reserved_minor':1000,'pending_payable_minor':500,
        'source_reference':'SYNTHETIC_CASH','data_state':'NEEDS_REVIEW','reported_cash_basis':'UNKNOWN'}
    return req,row


def test_cash_uses_one_latest_snapshot_and_does_not_resurrect_old_nonnull_fields():
    req,old=case();new={**old,'as_of_utc':'2026-10-21T12:00:00Z',
        'normalized_settled_minor':None,'reserved_minor':None,'pending_payable_minor':0}
    req['client_snapshot']['payload']['tables']['cash_balance_snapshot']=[new,old]
    before=deepcopy(req);out=normalize(req);cash=out['accounts'][0]['cash_observations'][0]
    assert cash['amounts']=={'reported_cash':'123.45','settled_cash':None,
        'pending_receivable':None,'pending_payable':'0','reserved_cash':None}
    assert 'unsettled_cash' not in cash['amounts']
    assert cash['original_row']==new and cash['available_at'] is None
    assert cash['available_cash'] is None and cash['authorized_incremental_amount'] is None
    assert cash['qualified_funding'] is False and req==before


@pytest.mark.parametrize('value,expected',[(0,'0'),(10000000,'100000'),(4890,'48.9'),
    (9000000000000000001,'90000000000000000.01'),(None,None)])
def test_w1_integer_hundredths_convert_exactly_including_twd(value,expected):
    assert major_amount(value)==expected


@pytest.mark.parametrize('value',[True,1.5,'100'])
def test_wrong_minor_unit_types_are_rejected(value):
    with pytest.raises(ValueError,match='INTEGER_MINOR_UNITS_REQUIRED'):major_amount(value)


def test_cash_currencies_stay_separate_and_unknown_settlement_is_not_zero():
    req,row=case()
    req['client_snapshot']['payload']['tables']['cash_balance_snapshot']=[row,
        {**row,'currency_code':'TWD','normalized_settled_minor':None,'reported_cash_minor':10000000}]
    out=normalize(req);cash=out['accounts'][0]['cash_observations']
    assert {r['currency']:r['amounts']['reported_cash'] for r in cash}=={'USD':'123.45','TWD':'100000'}
    assert next(r for r in cash if r['currency']=='TWD')['amounts']['settled_cash'] is None
    assert out['qualified_funding'] is False and out['accounts'][0]['net_asset_value'] is None


def test_missing_times_and_future_recording_are_excluded_without_fabricated_time():
    req,row=case()
    req['client_snapshot']['payload']['tables']['cash_balance_snapshot']=[row,
        {**row,'as_of_utc':None},
        {**row,'as_of_utc':'2026-10-22T12:00:00Z','reconciled_at_utc':'2026-10-31T00:00:00Z'}]
    out=normalize(req)
    assert len(out['accounts'][0]['cash_observations'])==1
    assert {r['reason'] for r in out['excluded_cash_rows']}=={
        'ORIGINAL_OBSERVATION_TIME_REQUIRED','ORIGINAL_ROW_AFTER_CUTOFF'}


def test_latest_version_and_timezone_are_compared_chronologically():
    req,row=case();cutoff=datetime(2026,10,30,tzinfo=timezone.utc)
    newer={**row,'as_of_utc':'2026-10-20T14:00:00+02:00','version':2,'reserved_minor':2000}
    rows,_=latest_rows([newer,row],('account_key','currency_code'),cutoff)
    assert rows==[newer]


def test_conflicting_same_snapshot_is_rejected_and_identical_duplicates_do_not_add_cash():
    req,row=case();tables=req['client_snapshot']['payload']['tables']
    tables['cash_balance_snapshot']=[row,deepcopy(row)]
    assert len(normalize(req)['accounts'][0]['cash_observations'])==1
    tables['cash_balance_snapshot'].append({**row,'reported_cash_minor':1})
    with pytest.raises(ValueError,match='SAME_SNAPSHOT_CONFLICT'):normalize(req)


def test_position_snapshots_select_latest_quantity_without_summing_history():
    req,_=case();tables=req['client_snapshot']['payload']['tables']
    old={'client_id':req['client_id'],'account_key':'SYNTHETIC_US','instrument_key':'SYNTHETIC_VT',
        'as_of_utc':'2026-10-20T12:00:00Z','quantity_decimal':'10'}
    new={**old,'as_of_utc':'2026-10-21T12:00:00Z','quantity_decimal':'12'}
    tables['portfolio_position']=[old,new]
    account=normalize(req)['accounts'][0]
    assert account['positions']==[new] and account['positions_complete'] is None
    tables['portfolio_position']=[]
    assert normalize(req)['accounts'][0]['positions_complete'] is None


def test_account_labels_cannot_supply_missing_broker_currency_or_funding_domain():
    req,_=case();out=normalize(req);account=out['accounts'][0]
    assert account['missing_binding_fields']==['broker','currency','funding_domain']
    assert account['binding_qualification'] is None and out['qualified_account_count']==0


def test_binding_reuses_original_w5_proofs_and_does_not_clear_cash_or_book():
    req,_=case();tables=req['client_snapshot']['payload']['tables'];client=req['client_id']
    base={'client_id':client,'account_key':'SYNTHETIC_US','created_at_utc':'2026-10-20T12:00:00Z',
          'source_reference':'SYNTHETIC_OWNER_PROOF'}
    tables['portfolio_account'][0].update(account_currency='USD',account_state='KNOWN',**base)
    tables['account_ownership']=[dict(base,owner_client_id=client,ownership_state='VERIFIED')]
    tables['account_broker_link']=[dict(base,broker_key='SYNTHETIC_BROKER',link_state='ACTIVE')]
    tables['funding_account_domain_link']=[dict(base,currency_code='USD',
        funding_domain_key='SYNTHETIC_INVESTMENT',link_state='VERIFIED')]
    tables['funding_domain']=[{'funding_domain_key':'SYNTHETIC_INVESTMENT',
        'domain_state':'ACTIVE','purpose_code':'INVESTMENT_CANDIDATE',
        'created_at_utc':base['created_at_utc']}]
    out=normalize(req)
    assert out['qualified_account_count']==1 and out['qualified_funding'] is False
    assert out['accounts'][0]['orders_complete'] is None
    tables['account_ownership'][0]['owner_client_id']='OTHER_PERSON'
    out=normalize(req)
    assert out['qualified_account_count']==0
    assert 'ACCOUNT_OWNER_MISMATCH' in out['accounts'][0]['missing_binding_fields'][0]


@pytest.mark.parametrize('change',['client','account'])
def test_foreign_cash_cannot_be_mapped_to_a_family_member(change):
    req,row=case();row['client_id' if change=='client' else 'account_key']='OTHER'
    req['client_snapshot']['payload']['tables']['cash_balance_snapshot']=[row]
    with pytest.raises(PermissionError,match='OBSERVATION_ACCOUNT_MISMATCH'):normalize(req)
