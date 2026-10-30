"""Observation reuse cannot outlive identical members/cutoffs/source bytes."""
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from same_run_market_cache import SameRunMarketCache


def case(tmp_path):
    folder=tmp_path/'data/market_history/global';folder.mkdir(parents=True)
    csv=folder/'SYNTHETIC.csv';csv.write_text('Date,Close\n2026-10-29,1\n')
    arguments={'repo_root':tmp_path,'snapshot':{'client_id':'SYNTHETIC_MEMBER','source_db_sha256':'a'*64},
        'evaluation_at':'2026-10-30T00:00:00Z'}
    seen=[]
    def builder(**kwargs):seen.append(kwargs);return {'source_bytes':csv.read_text(),'formal_deployment_eligible':False,'values':[1]}
    return arguments,csv,seen,builder


def test_original_result_is_reused_and_caller_mutation_does_not_change_it(tmp_path):
    a,p,seen,b=case(tmp_path);cache=SameRunMarketCache();out=cache.build(b,a);out['values'].append(2)
    assert cache.build(b,a)['values']==[1] and len(seen)==1
    assert cache.build(b,a)['formal_deployment_eligible'] is False


@pytest.mark.parametrize('change',['member','db','cutoff','bytes','new_file'])
def test_changed_source_or_scope_requires_original_recomputation(tmp_path,change):
    a,p,seen,b=case(tmp_path);cache=SameRunMarketCache();cache.build(b,a)
    if change=='member':a['snapshot']['client_id']='SYNTHETIC_OTHER'
    elif change=='db':a['snapshot']['source_db_sha256']='b'*64
    elif change=='cutoff':a['evaluation_at']='2026-10-31T00:00:00Z'
    elif change=='bytes':p.write_text('Date,Close\n2026-10-29,2\n')
    else:p.with_name('SYNTHETIC_OTHER.csv').write_text('NEW SOURCE')
    cache.build(b,a);assert len(seen)==2


def test_source_changing_during_original_calculation_is_not_cached(tmp_path):
    a,p,seen,b=case(tmp_path);cache=SameRunMarketCache()
    def changed(**kwargs):p.write_text('CHANGED');return {'not_qualified':True}
    with pytest.raises(PermissionError,match='CHANGED_DURING_ORIGINAL_BUILD'):cache.build(changed,a)


def test_original_approved_arithmetic_is_identical_with_scoped_reuse_and_context_is_released():
    from copy import deepcopy
    from datetime import date,timedelta
    from approved_v04_technical import produce,load_profile
    from same_run_market_cache import active_cache
    profile=load_profile(HERE/'owner_approved_v10.json')
    rows=[{'Date':str(date(2025,1,1)+timedelta(days=i)),'Open':100+i%10,'High':101+i%10,
        'Low':99+i%10,'Close':100+i%10,'Volume':1000} for i in range(65)]
    expected=produce(rows,profile=profile,is_etf=True);cache=SameRunMarketCache()
    with cache.activate():
        first=produce(rows,profile=profile,is_etf=True)
        assert produce(deepcopy(rows),profile=profile,is_etf=True)==first==expected
        assert len(cache._arithmetic)==1
    assert active_cache() is None
