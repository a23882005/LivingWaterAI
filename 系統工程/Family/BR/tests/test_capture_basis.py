from copy import deepcopy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from replay import ReplayError, digest
from event_capture import capture, verify_capture
from market_basis import validate_basis


def fixture():
    owner={'client_id':'A','account':'ONE','funding_domain':'F1'}
    req={'client_id':'A','request_id':'Q','run_id':'R','evaluation_at':'2020-01-02T00:00:00Z',
        'owner':owner,'trade_authorization':'NONE','analysis_permission':'ANALYZE_ONLY',
        'expected_versions':{'engine':'1'},'client_snapshot':{'payload':{'client_id':'A','tables':{
        'portfolio_account':[{'client_id':'A','account_key':'ONE'},{'client_id':'A','account_key':'TWO'}],
        'portfolio_position':[{'client_id':'A','account_key':'ONE','quantity_decimal':'19.000'},
                              {'client_id':'A','account_key':'TWO','quantity_decimal':'0'}],
        'cash_balance_snapshot':[{'client_id':'A','state':'UNKNOWN','amount':None}]}}}}
    ctx={'client_id':'A','analysis_permission':'ANALYZE_ONLY','expected_versions':{'engine':'1'},'native_binding':{'data_provenance':'SYNTHETIC'}}
    out={'client_id':'A','request_id':'Q','run_id':'R','owner':owner,'status':'OK','trade_action':'NO_TRADE','proposal':'BUY'}
    return req,ctx,out


def test_capture_multiaccount_preserves_unknown_zero_and_no_trade():
    r,c,o=fixture();before=deepcopy((r,c,o))
    e=capture(r,c,o,source_lock_sha256='a'*64)
    proof=verify_capture(e,r,c,o,source_lock_sha256='a'*64)
    assert proof['accounts']==2 and proof['positions']==2
    assert e['portfolio_before']==e['portfolio_after']==r['client_snapshot']['payload']['tables']
    assert e['executed_trades']==[] and (r,c,o)==before
    assert capture(r,c,o,source_lock_sha256='a'*64)==e


@pytest.mark.parametrize('kind',['context_client','row_client','result_run','account','permission','version','trade'])
def test_capture_rejects_wrong_binding(kind):
    r,c,o=fixture()
    if kind=='context_client':c['client_id']='B'
    if kind=='row_client':r['client_snapshot']['payload']['tables']['portfolio_position'][0]['client_id']='B'
    if kind=='result_run':o['run_id']='OTHER'
    if kind=='account':r['client_snapshot']['payload']['tables']['portfolio_position'][0]['account_key']='OTHER'
    if kind=='permission':c['analysis_permission']='NONE'
    if kind=='version':c['expected_versions']['engine']='2'
    if kind=='trade':o['trade_action']='EXECUTE'
    with pytest.raises(ReplayError):capture(r,c,o,source_lock_sha256='a'*64)


def test_capture_preserves_block_reason():
    r,c,o=fixture();o={'request_id':'Q','run_id':'R','status':'DATA_UNAVAILABLE','issue_codes':[{'code':'MISSING'}]}
    e=capture(r,c,o,source_lock_sha256='a'*64)
    assert e['issue_codes']==o['issue_codes'] and e['result_status']=='DATA_UNAVAILABLE'


def test_capture_rejects_tamper_even_if_attacker_rehashes():
    r,c,o=fixture();e=capture(r,c,o,source_lock_sha256='a'*64)
    e['lineage']['result']['payload']['proposal']='SELL'
    n=e['lineage']['result'];n['sha256']=digest({k:v for k,v in n.items() if k!='sha256'})
    with pytest.raises(ReplayError,match='BINDING'):verify_capture(e,r,c,o,source_lock_sha256='a'*64)


def contract():
    return dict(price_basis='RAW',split_basis_verified=True,evidence_ref='SYNTHETIC',
        available_at='2020-01-02T00:00:00Z',dividend_mode='CASH_SEPARATE',quote_currency='USD',base_currency='TWD',
        max_fx_age_seconds=86400,fx=dict(from_currency='USD',to_currency='TWD',unit='TO_PER_FROM',rate='30',
        evidence_ref='SYNTHETIC',observed_at='2020-01-01T00:00:00Z',available_at='2020-01-01T01:00:00Z'))


def test_fx_age_inclusive_and_total_return_convention():
    x=contract();assert validate_basis(x,cutoff='2020-01-02T00:00:00Z')['status']=='PASS'
    x['price_basis']='TOTAL_RETURN';x['dividend_mode']='INCLUDED_IN_TOTAL_RETURN'
    assert validate_basis(x,cutoff='2020-01-02T00:00:00Z')['adjustments_applied']==0


@pytest.mark.parametrize('kind',['future','unknown_basis','unverified','dividend','fx_inverse','stale','nan','future_fx'])
def test_basis_errors(kind):
    x=contract()
    if kind=='future':x['available_at']='2020-01-03T00:00:00Z'
    if kind=='unknown_basis':x['price_basis']='UNKNOWN'
    if kind=='unverified':x['split_basis_verified']=None
    if kind=='dividend':x['price_basis']='TOTAL_RETURN'
    if kind=='fx_inverse':x['fx']['unit']='FROM_PER_TO'
    if kind=='stale':x['max_fx_age_seconds']=86399
    if kind=='nan':x['fx']['rate']='NaN'
    if kind=='future_fx':x['fx']['available_at']='2020-01-03T00:00:00Z'
    with pytest.raises(ReplayError):validate_basis(x,cutoff='2020-01-02T00:00:00Z')


def test_split_effective_date_ratio_and_double_adjustment():
    x=contract();x['splits']=[dict(new_shares_per_old_share='4',effective_at=x['available_at'],available_at=x['available_at'],evidence_ref='SYNTHETIC',apply_price_adjustment=True)]
    assert validate_basis(x,cutoff=x['available_at'])['status']=='PASS'
    x['price_basis']='SPLIT_ADJUSTED'
    with pytest.raises(ReplayError,match='DOUBLE'):validate_basis(x,cutoff=x['available_at'])
    x['splits'][0]['apply_price_adjustment']=False
    assert validate_basis(x,cutoff=x['available_at'])['status']=='PASS'
    x['splits'][0]['new_shares_per_old_share']='0'
    with pytest.raises(ReplayError,match='POSITIVE'):validate_basis(x,cutoff=x['available_at'])
