import importlib.util
from pathlib import Path
import sqlite3
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'probes'))
import shared_drive_writer as w

@pytest.fixture
def data(tmp_path):
    p=tmp_path/'source.db'
    with sqlite3.connect(p) as db:
        db.execute('create table original(value integer)');db.execute('insert into original values(58)')
    return p.read_bytes()

class Fake:
    def __init__(self,data):self.data=data;self.p={};self.copies={};self.count=0;self.fail=None
    def meta(self,file_id=w.TEST_ID):return {'id':file_id,'parents':[w.BACKUP_FOLDER] if file_id!=w.TEST_ID else [w.target.__globals__['TEMP_FOLDER']],'appProperties':self.p}
    def read(self,file_id=w.TEST_ID):return self.data if file_id==w.TEST_ID else self.copies[file_id]
    def backup(self):
        key='backup'+str(len(self.copies));self.copies[key]=self.data;return key
    def call(self,url,method='GET',data=None):
        if self.fail=='before-journal' and 'b04s_before' in data['appProperties']:raise OSError()
        self.p.update(data['appProperties'])
    def write(self,data):
        if self.fail=='before-upload':raise OSError()
        self.data=data;self.count+=1
        if self.fail=='after-upload':raise OSError()

def body(rid='one',account='synthetic-A',delta=7):return dict(account=account,request_id=rid,delta=delta)

@pytest.mark.parametrize('boundary',['before-journal','before-upload','after-upload'])
def test_retry_each_failure_boundary(data,boundary):
    d=Fake(data);w.initialize(d,'run');d.fail=boundary
    with pytest.raises(OSError):w.apply(d,'run',body())
    d.fail=None
    assert w.apply(d,'run',body())['value']==7
    assert w.apply(d,'run',body())=={'value':7,'duplicate':True}
    assert w.apply(d,'run',{'account':'synthetic-B'})['value']==0
    assert w.cleanup(d,'run')['state']=='RESTORED';assert d.data==data

@pytest.mark.parametrize('boundary',['before-upload','after-upload'])
def test_cleanup_interruption_retries(data,boundary):
    d=Fake(data);w.initialize(d,'run');w.apply(d,'run',body());d.fail=boundary
    with pytest.raises(OSError):w.cleanup(d,'run')
    d.fail=None
    assert w.cleanup(d,'run')['state']=='RESTORED';assert d.data==data

def test_duplicate_and_collision(data):
    d=Fake(data);w.initialize(d,'run');w.apply(d,'run',body())
    n=d.count
    assert w.apply(d,'run',body())['duplicate'];assert d.count==n
    with pytest.raises(RuntimeError):w.apply(d,'run',body(delta=8))
    assert d.count==n

def test_external_change_preserved(data):
    d=Fake(data);w.initialize(d,'run');d.data=b'external'
    with pytest.raises(RuntimeError):w.apply(d,'run',body())
    with pytest.raises(RuntimeError):w.cleanup(d,'run')
    assert d.data==b'external';assert d.count==0

def test_other_run_blocked(data):
    d=Fake(data);w.initialize(d,'run')
    with pytest.raises(RuntimeError):w.initialize(d,'other')
    with pytest.raises(RuntimeError):w.cleanup(d,'other')

def test_identity_guard(data):
    d=Fake(data);w.initialize(d,'run')
    with pytest.raises(RuntimeError):w.apply(d,'run',body(account='formal-Arthur'))
    assert d.count==0

def test_ack_lost_retry_preserves_later_receipt(data):
    d=Fake(data);w.initialize(d,'run');w.apply(d,'run',body());w.apply(d,'run',body('two',delta=3))
    assert w.apply(d,'run',body())['value']==7
    assert w.apply(d,'run',{'account':'synthetic-A'})['value']==10
