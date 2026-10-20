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
