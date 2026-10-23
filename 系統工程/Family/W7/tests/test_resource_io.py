import concurrent.futures
import copy
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid
import pytest
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
w=importlib.import_module('資料存取管理')
from resource_headers import SCHEMA, VerifiedPrincipal

class Disk:
    """Durable filesystem fake; atomic replacement, fresh instances see journal."""
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(exist_ok=True);self.fail=None;self.hook=None
    def _save(self, name, value):
        p=self.root/name;temp=p.with_name(p.name+'.'+uuid.uuid4().hex)
        with temp.open('wb') as f:f.write(value);f.flush();os.fsync(f.fileno())
        os.replace(temp,p)
    def read(self,id):return (self.root/id).read_bytes()
    def journal(self,id):
        p=self.root/(id+'.json');return json.loads(p.read_text()) if p.exists() else None
    def save_journal(self,id,value):
        if self.fail=='journal' and value['pending']:raise OSError('journal')
        self._save(id+'.json',json.dumps(value).encode())
    def backup(self,id):
        key='backup_'+uuid.uuid4().hex;data=self.read(id)
        self._save(key,data);self._save(key+'.meta',json.dumps(dict(source_id=id,sha256=w.digest(data))).encode())
        if self.hook:self.hook()
        return key
    def backup_info(self,id):return json.loads((self.root/(id+'.meta')).read_text())
    def write(self,id,data):
        if self.fail=='before-upload':raise OSError('before')
        self._save(id,data)
        if self.fail=='after-upload':raise OSError('after')
        if self.fail=='exit-after-upload':os._exit(73)

def add(db,payload):
    db.execute('update counter set n=n+?',(payload['delta'],))
    return db.execute('select n from counter').fetchone()[0]

def manager(root, backend=None, clock=time.time, handlers=None, guard=lambda p:True):
    h=dict(schema=SCHEMA,resource_key='family.mou',binding='BOUND',file_id='synthetic_database',policy_ref='private.mou',state='Close',readers=[],updater=None)
    return w.Coordinator({'family.mou':h},{'private.mou':{'read':['account:mou'],'update':['account:mou']}},
                         backend or Disk(root),Path(root)/'locks',handlers or {'add':add},clock,
                         restore_subjects=['account:mou'],session_guard=guard)

def principal():return VerifiedPrincipal('account:mou',int(time.time())+1000)

@pytest.fixture
def setup(tmp_path):
    d=Disk(tmp_path);p=tmp_path/'synthetic_database'
    with sqlite3.connect(p) as db:db.execute('create table counter(n integer)');db.execute('insert into counter values(0)')
    original=p.read_bytes();m=manager(tmp_path,d);s=m.snapshot('family.mou',principal())
    return tmp_path,d,m,s,original

def run_update(root,rid,epoch,fail=None):
    d=Disk(root);d.fail=fail
    manager(root,d).update('family.mou',principal(),rid,epoch,'add',{'delta':1})

def value(data,tmp_path):
    p=tmp_path/('read_'+uuid.uuid4().hex);p.write_bytes(data)
    with sqlite3.connect(p) as db:return db.execute('select n from counter').fetchone()[0]

def test_backup_same_id_and_duplicate(setup):
    root,d,m,s,original=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':3})
    assert d.read(r['backup_id'])==original
    assert m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':3})['duplicate']
    with pytest.raises(ValueError,match='COLLISION'):m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':4})
    assert value(m.snapshot('family.mou',principal())['data'],root)==3
    assert d.journal('synthetic_database')['state']=='Close'

@pytest.mark.parametrize('failure',['journal','before-upload','after-upload'])
def test_fresh_worker_resolves_uncertain_commit(setup,failure):
    root,d,m,s,_=setup;d.fail=failure
    with pytest.raises(OSError):m.update('family.mou',principal(),'retry',s['epoch'],'add',{'delta':7})
    fresh=manager(root)
    fresh.update('family.mou',principal(),'retry',s['epoch'],'add',{'delta':7})
    assert value(fresh.snapshot('family.mou',principal())['data'],root)==7

def test_real_process_exit_and_recovery(setup):
    root,d,m,s,_=setup
    p=multiprocessing.get_context('fork').Process(target=run_update,args=(root,'crash',s['epoch'],'exit-after-upload'))
    p.start();p.join(10);assert p.exitcode==73
    fresh=manager(root)
    assert fresh.update('family.mou',principal(),'crash',s['epoch'],'add',{'delta':1})['duplicate']
    assert value(fresh.snapshot('family.mou',principal())['data'],root)==1

def test_competing_processes_merge_latest(setup):
    root,d,m,s,_=setup
    ctx=multiprocessing.get_context('fork')
    ps=[ctx.Process(target=run_update,args=(root,str(i),s['epoch'])) for i in range(8)]
    for p in ps:p.start()
    for p in ps:p.join(15);assert p.exitcode==0
    assert value(m.snapshot('family.mou',principal())['data'],root)==8

def test_readers_get_complete_images(setup):
    root,d,m,s,_=setup
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs=[]
        for i in range(6):
            jobs.append(pool.submit(run_update,root,str(i),s['epoch']))
            jobs.append(pool.submit(lambda: value(manager(root).snapshot('family.mou',principal())['data'],root)))
        results=[j.result(timeout=20) for j in jobs]
    assert all(n is None or 0<=n<=6 for n in results)
    assert value(m.snapshot('family.mou',principal())['data'],root)==6

def test_expiry_after_backup_prevents_upload(setup):
    root,d,m,s,original=setup;now=[10];m=manager(root,d,clock=lambda:now[0])
    d.hook=lambda:now.__setitem__(0,20)
    with pytest.raises(PermissionError):m.update('family.mou',VerifiedPrincipal('account:mou',20),'expired',s['epoch'],'add',{'delta':1})
    assert d.read('synthetic_database')==original
    assert manager(root).snapshot('family.mou',principal())['data']==original

@pytest.mark.parametrize('p',[VerifiedPrincipal('account:Arthur',9999999999),{'subject':'account:mou'},VerifiedPrincipal('account:mou',0)])
def test_identity_before_io(setup,p):
    root,d,m,s,original=setup
    with pytest.raises(PermissionError):m.update('family.mou',p,'bad',s['epoch'],'add',{'delta':1})
    assert d.read('synthetic_database')==original

def test_handler_exception_and_early_commit_rollback(setup):
    root,d,m,s,original=setup
    def broken(db,p):db.execute('update counter set n=99');raise ValueError('handler')
    def early(db,p):db.commit()
    for handler in (broken,early):
        with pytest.raises((ValueError,sqlite3.DatabaseError)):manager(root,d,handlers={'bad':handler}).update('family.mou',principal(),'bad',s['epoch'],'bad',{})
        assert d.read('synthetic_database')==original

def test_restore_exact_bytes_rejects_old_work(setup):
    root,d,m,s,original=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':5})
    result=m.restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore1')
    assert d.read('synthetic_database')==original
    assert result['epoch']!=s['epoch']
    assert m.restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore1')['duplicate']
    with pytest.raises(RuntimeError,match='STALE_EPOCH'):m.update('family.mou',principal(),'queued',s['epoch'],'add',{'delta':1})
    m.update('family.mou',principal(),'new',result['epoch'],'add',{'delta':2})
    assert value(m.snapshot('family.mou',principal())['data'],root)==2

@pytest.mark.parametrize('failure',['before-upload','after-upload'])
def test_restore_interrupted_retry(setup,failure):
    root,d,m,s,original=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':5});d.fail=failure
    with pytest.raises(OSError):m.restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore1')
    manager(root).restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore1')
    assert d.read('synthetic_database')==original

def test_external_change_not_overwritten(setup):
    root,d,m,s,_=setup
    with sqlite3.connect(root/'synthetic_database') as db:db.execute('update counter set n=42')
    external=d.read('synthetic_database')
    with pytest.raises(RuntimeError,match='EXTERNAL_CHANGE'):m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':1})
    assert d.read('synthetic_database')==external

def test_backup_tamper_and_wrong_resource(setup):
    root,d,m,s,_=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':5})
    b=r['backup_id'];d._save(b+'.meta',json.dumps(dict(source_id='other',sha256='0'*64)).encode())
    with pytest.raises(PermissionError):m.restore('family.mou',principal(),b,s['epoch'],'restore')

def test_logout_during_backup_stops_commit(setup):
    root,d,m,s,original=setup;active=[True]
    d.hook=lambda:active.__setitem__(0,False)
    with pytest.raises(PermissionError,match='SESSION_REVOKED'):
        manager(root,d,guard=lambda p:active[0]).update('family.mou',principal(),'logout',s['epoch'],'add',{'delta':9})
    assert d.read('synthetic_database')==original

def test_no_maintenance_role_cannot_restore(setup):
    root,d,m,s,_=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':1})
    m.restore_subjects=frozenset()
    with pytest.raises(PermissionError,match='MAINTENANCE_ROLE'):
        m.restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore')

def test_restore_backup_failure_releases_display_state(setup):
    root,d,m,s,_=setup
    r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':1})
    current=d.read('synthetic_database')
    def failed(id):raise OSError('backup service unavailable')
    d.backup=failed
    with pytest.raises(OSError):m.restore('family.mou',principal(),r['backup_id'],s['epoch'],'restore')
    assert d.journal('synthetic_database')['state']=='Close'
    assert d.read('synthetic_database')==current


def test_python39_authorizer_commit_rollback_and_guard(tmp_path, monkeypatch):
    original_connect=sqlite3.connect
    class LegacyConnection(sqlite3.Connection):
        def set_authorizer(self, callback):
            if callback is None: raise TypeError('Python 3.9 requires callable')
            return super().set_authorizer(callback)
    def connect(*args, **kwargs):
        kwargs['factory']=LegacyConnection
        return original_connect(*args, **kwargs)
    monkeypatch.setattr(sqlite3,'connect',connect)
    # Exercise actual SQLite writes and a forbidden transaction, not a stub.
    image_path=tmp_path/'legacy.db'
    with original_connect(image_path) as db:
        db.execute('create table counter(n integer)')
        db.execute('insert into counter values(0)')
        db.commit()
    image=image_path.read_bytes()
    changed,result,_=w.transaction(image,'user','legacy-ok','add',{'delta':2},add)
    assert result==2 and changed!=image
    def forbidden(db,payload):
        db.execute('update counter set n=999')
        db.execute('COMMIT')
    with pytest.raises(sqlite3.DatabaseError):
        w.transaction(image,'user','legacy-denied','bad',{},forbidden)
    _,result,_=w.transaction(image,'user','legacy-after','add',{'delta':1},add)
    assert result==1
