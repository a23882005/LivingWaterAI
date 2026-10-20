from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
from threading import Event,Lock
import pytest
from recovery_bridge import StagingAnalysisStore,RecoveryError,input_digest


@pytest.fixture
def store():
    import os
    base=Path(os.environ.get('W5_W2_ROOT','w2'))
    path=base/'runtime/c_configuration_core/work21/recovery.py'
    spec=importlib.util.spec_from_file_location('w5_original_w2_recovery',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return StagingAnalysisStore(module)


def request():
    return {'client_id':'SYNTHETIC-A','request_id':'REQ-1','run_id':'RUN-1',
        'owner':{'account_id':'SYNTHETIC-ACCOUNT'},'expected_versions':{'target':1,'funding':1},
        'evaluation_at':'2026-10-20T00:00:00Z','amount':Decimal('1.00000000000000001')}


def result(r):return {'trade_action':'NO_TRADE','amount':r['amount']}


def test_replay_conflict_and_original_journal_once(store):
    r=request();calls=[]
    def compute(r):calls.append(1);return result(r)
    first=store.analyze(r,validate=lambda r:None,compute=compute)
    first['result']['amount']=0
    second=store.analyze(r,validate=lambda r:None,compute=compute)
    assert second['status']=='REPLAYED' and second['result']['amount']==r['amount']
    assert calls==[1]
    altered=deepcopy(r);altered['amount']+=1
    with pytest.raises(RecoveryError,match='IDEMPOTENCY_CONFLICT'):
        store.analyze(altered,validate=lambda r:None,compute=compute)
    entry=next(iter(store._entries.values()))
    assert entry['journal']['mutation_count']==entry['publication_count']==1
    json.dumps(store.snapshot(),allow_nan=False)


@pytest.mark.parametrize('phase',['cached','during_compute'])
@pytest.mark.parametrize('change',['permission','version'])
def test_current_authority_rechecked_before_delivery(store,phase,change):
    current={'permission':True,'version':1}
    def validate(r):
        if not current['permission']:raise RecoveryError('PERMISSION_REVOKED')
        if current['version']!=r['expected_versions']['funding']:raise RecoveryError('STALE_VERSION')
    def compute(r):
        if phase=='during_compute':current[change]=False if change=='permission' else 2
        return result(r)
    if phase=='cached':
        store.analyze(request(),validate=validate,compute=compute)
        current[change]=False if change=='permission' else 2
    with pytest.raises(RecoveryError,match='PERMISSION_REVOKED|STALE_VERSION'):
        store.analyze(request(),validate=validate,compute=compute)
    assert next(iter(store._entries.values()))['publication_count']==(1 if phase=='cached' else 0)


def test_real_timeout_retry_and_late_result_cannot_replace(store):
    release=Event();late_finished=Event();lock=Lock();calls=[]
    def compute(r):
        with lock:calls.append(1);number=len(calls)
        if number==1:
            assert release.wait(2)
            late_finished.set()
            return {'trade_action':'NO_TRADE','amount':'LATE'}
        return result(r)
    try:
        answer=store.analyze(request(),validate=lambda r:None,compute=compute,timeout_seconds=.02)
        assert answer['result']['amount']==request()['amount']
    finally:release.set()
    assert late_finished.wait(2)
    cached=store.analyze(request(),validate=lambda r:None,compute=compute)
    assert cached['result']==answer['result'] and len(calls)==2
    entry=next(iter(store._entries.values()))
    assert entry['timeouts']==entry['publication_count']==1


def test_two_timeouts_stop_after_one_retry(store):
    release=Event();finished=[Event(),Event()];lock=Lock();calls=[]
    def compute(r):
        with lock:n=len(calls);calls.append(1)
        try:assert release.wait(2);return result(r)
        finally:finished[n].set()
    try:
        with pytest.raises(RecoveryError,match='COMPUTATION_TIMEOUT'):
            store.analyze(request(),validate=lambda r:None,compute=compute,timeout_seconds=.02)
    finally:release.set()
    assert all(e.wait(2) for e in finished)
    assert len(calls)==2 and next(iter(store._entries.values()))['publication_count']==0
    with pytest.raises(RecoveryError,match='COMPUTATION_RETRY_EXHAUSTED'):
        store.analyze(request(),validate=lambda r:None,compute=compute)
    assert len(calls)==2


def test_concurrent_same_request_commits_once(store):
    entered=Event();release=Event();calls=[]
    def compute(r):calls.append(1);entered.set();assert release.wait(2);return result(r)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(store.analyze,request(),validate=lambda r:None,compute=compute)
        assert entered.wait(2)
        b=pool.submit(store.analyze,request(),validate=lambda r:None,compute=compute)
        release.set()
        assert {a.result()['status'],b.result()['status']}=={'COMPUTED','REPLAYED'}
    assert calls==[1]


@pytest.mark.parametrize('error',[RecoveryError('CONTRACT_ERROR'),TimeoutError('ENGINE_TIMEOUT_ERROR')])
def test_contract_error_not_retried_and_partial_result_not_cached(store,error):
    calls=[]
    def compute(r):calls.append(1);raise error
    with pytest.raises(type(error),match=str(error)):
        store.analyze(request(),validate=lambda r:None,compute=compute)
    assert len(calls)==1 and next(iter(store._entries.values()))['result'] is None


def test_digest_preserves_precision_types_order_and_versions():
    r=request();changed=deepcopy(r);changed['amount']=Decimal('1.00000000000000002')
    assert input_digest(r)!=input_digest(changed)
    assert input_digest({'a':[1,2]})!=input_digest({'a':[2,1]})
    assert input_digest({'a':True})!=input_digest({'a':1})
    assert input_digest({'a':Decimal('1')})!=input_digest({'a':{'decimal':'1'}})
    with pytest.raises(RecoveryError,match='NONFINITE'):input_digest({'a':float('nan')})
