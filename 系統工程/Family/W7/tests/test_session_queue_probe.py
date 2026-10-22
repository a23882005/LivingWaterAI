import importlib.util
from pathlib import Path
import secrets
from concurrent.futures import ThreadPoolExecutor
import pytest
spec=importlib.util.spec_from_file_location('session_queue_probe',Path(__file__).resolve().parents[1]/'probes/session_queue_probe.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def test_fixed_four_hours_and_cross_conversation():
    key=secrets.token_bytes(32);token=p.issue(key,'project-A','member-A','device-A','s1',100)
    for now in (100,200,14499):
        assert p.verify(key,token,project='project-A',member='member-A',device='device-A',now=now)['expires']==14500
    with pytest.raises(ValueError):p.verify(key,token,project='project-A',member='member-A',device='device-A',now=14500)

@pytest.mark.parametrize('field,value',[('project','project-B'),('member','member-B'),('device','device-B')])
def test_wrong_binding(field,value):
    key=secrets.token_bytes(32);t=p.issue(key,'project-A','member-A','device-A','s1',0)
    kw=dict(project='project-A',member='member-A',device='device-A',now=10);kw[field]=value
    with pytest.raises(ValueError,match='BINDING'):p.verify(key,t,**kw)

def test_untrusted_text_cannot_modify_signed_claims():
    key=secrets.token_bytes(32);t=p.issue(key,'project-A','member-A','device-A','s1',0);t[0]['project']='project-B'
    with pytest.raises(ValueError,match='SIGNATURE'):p.verify(key,t,project='project-B',member='member-A',device='device-A',now=1)

def test_fifo_restart_and_idempotent_enqueue(tmp_path):
    path=tmp_path/'synthetic.db';q=p.Queue(path)
    q.enqueue('chat-1','shared',{'n':1});q.enqueue('action-1','shared',{'n':2});q.enqueue('chat-1','shared',{'n':1});q.close()
    q=p.Queue(path);first=q.acquire('shared',0);assert first[0]=='chat-1';assert q.acquire('shared',1) is None
    q.commit(first,1);second=q.acquire('shared',2);assert second[0]=='action-1';assert second[3]==1
    q.commit(second,3);assert q.acquire('shared',4) is None;q.close()

def test_stale_fence_and_request_collision(tmp_path):
    q=p.Queue(tmp_path/'synthetic.db');q.enqueue('r','x',{'n':1})
    with pytest.raises(ValueError,match='COLLISION'):q.enqueue('r','x',{'n':2})
    old=q.acquire('x',0,lease=2);new=q.acquire('x',2)
    with pytest.raises(ValueError,match='STALE'):q.commit(old,3)
    q.commit(new,3);q.close()

def test_competing_connections_only_one_holder(tmp_path):
    path=tmp_path/'synthetic.db';q=p.Queue(path);q.enqueue('r','shared',{});q.close()
    def acquire(_):
        worker=p.Queue(path)
        try:return worker.acquire('shared',0)
        finally:worker.close()
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(acquire,range(4)))
    assert sum(x is not None for x in results)==1
