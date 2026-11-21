import pytest
from funding_guard import check_aggregate, FundingError, amount

OWNER=dict(client_id='SYNTHETIC', funding_domain='US_BROKER', broker='TEST',account='A',currency='USD')
def claim(i,kind,v):
    return dict(claim_id=i,asset_class=kind,amount=v,owner=OWNER,run_id='R')
def run(claims, **kw):
    args=dict(owner=OWNER,run_id='R',available='100',equity_budget='60',bond_budget='60',claims=claims)
    args.update(kw)
    return check_aggregate(**args)
def test_combined_cap():
    with pytest.raises(FundingError,match='AGGREGATE'):run([claim('a','EQUITY','60'),claim('b','BOND','60')])
def test_multi_asset_cap():
    with pytest.raises(FundingError,match='AGGREGATE'):run([claim('a','EQUITY','40'),claim('b','EQUITY','40')])
def test_exact_sum():
    assert run([claim('a','EQUITY','0.1'),claim('b','BOND','0.2')])['available_remaining']=='99.7'
def test_zero():
    assert run([],available='0')['available_remaining']=='0'
@pytest.mark.parametrize('bad',[None,True,False,1.2,'NaN','Infinity','-1','invalid'])
def test_reject_amount(bad):
    with pytest.raises(FundingError):amount(bad)
@pytest.mark.parametrize('field',['client_id','funding_domain','broker','account','currency'])
def test_owner_isolation(field):
    c=claim('a','EQUITY','1');c['owner']={**OWNER,field:'OTHER'}
    with pytest.raises(FundingError,match='OWNER'):run([c])
def test_duplicate():
    with pytest.raises(FundingError,match='DUPLICATE'):run([claim('a','EQUITY','1')]*2)
def test_run_isolation():
    c=claim('a','EQUITY','1');c['run_id']='OTHER'
    with pytest.raises(FundingError,match='RUN'):run([c])
def test_unknown_available():
    with pytest.raises(FundingError,match='DATA_UNAVAILABLE'):run([],available=None)

def test_different_labels_cannot_duplicate_one_underlying_native_decision():
    first={**claim('first','EQUITY','10'),'source_engine':'V82','asset_id':'SYNTHETIC'}
    renamed={**first,'claim_id':'renamed'}
    with pytest.raises(FundingError,match='DUPLICATE_NATIVE_DECISION'):run([first,renamed])

def test_independent_native_assets_use_one_shared_balance():
    rows=[{**claim('a','EQUITY','10'),'source_engine':'V82','asset_id':'ONE'},
          {**claim('b','BOND','20'),'source_engine':'V75','asset_id':'TWO'}]
    assert run(rows)['available_remaining']=='70'

def test_partially_supplied_native_decision_identity_is_not_accepted():
    with pytest.raises(FundingError,match='NATIVE_DECISION_IDENTITY_REQUIRED'):
        run([{**claim('a','EQUITY','10'),'source_engine':'V82'}])
