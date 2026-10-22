import copy
import json
from pathlib import Path
import sys
from urllib.parse import urlparse, parse_qs
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from drive_resource_backend import DriveResourceBackend
from resource_headers import render_header, parse_header
from test_resource_io import setup, principal, manager

class Transport:
    def __init__(self,data,header):
        self.bytes={'synthetic_database':data,'journal':b'null','header':render_header(header).encode()}
        self.meta={k:dict(id=k,parents=['temp'],trashed=False,appProperties={}) for k in self.bytes}
        self.writes=[]
    def call(self,url,method='GET',data=None,raw=False):
        path=urlparse(url).path.split('/files/')[1];query=parse_qs(urlparse(url).query)
        if path.endswith('/copy'):
            source=path[:-5];key='copy_'+str(len(self.bytes));self.bytes[key]=self.bytes[source]
            self.meta[key]=dict(id=key,parents=data['parents'],trashed=False,appProperties=data.get('appProperties',{}))
            return {'id':key}
        if method=='PATCH':
            assert query['uploadType']==['media'];self.bytes[path]=data;self.writes.append(path)
            return {'id':path}
        if query.get('alt')==['media']:return self.bytes[path]
        return copy.deepcopy(self.meta[path])

def backend(setup):
    root,d,m,s,original=setup;h=m.headers['family.mou'];t=Transport(original,h)
    mapping={'synthetic_database':dict(parent_id='temp',journal_id='journal',journal_parent_id='temp',header_id='header',header_template=h)}
    return t,DriveResourceBackend(t,mapping,'backup'),mapping

def test_adapter_same_id_backup_and_header_readback(setup):
    root,_,_,_,original=setup;t,b,_=backend(setup);m=manager(root,b)
    s=m.snapshot('family.mou',principal());r=m.update('family.mou',principal(),'one',s['epoch'],'add',{'delta':2})
    assert b.read(r['backup_id'])==original
    assert b.backup_info(r['backup_id'])['source_id']=='synthetic_database'
    assert parse_header(t.bytes['header'].decode())['state']=='Close'
    assert set(t.writes)<={'synthetic_database','journal','header'}
    assert len([x for x in t.meta.values() if x['parents']==['backup']])>=3

@pytest.mark.parametrize('key',['synthetic_database','journal','header'])
def test_moved_resource_rejected_before_write(setup,key):
    t,b,_=backend(setup);t.meta[key]['parents']=['wrong']
    with pytest.raises(RuntimeError,match='LOCATION_CHANGED'):b.write('synthetic_database',t.bytes['synthetic_database'])
    assert t.writes==[]

def test_bad_binding_and_alias_rejected(setup):
    t,b,mapping=backend(setup)
    mapping['synthetic_database']['header_template']['file_id']='wrong_database'
    with pytest.raises(ValueError,match='BINDING_MISMATCH'):DriveResourceBackend(t,mapping,'backup')
    # Existing backend owns its independent trusted configuration.
    assert b.read('synthetic_database')==t.bytes['synthetic_database']
    mapping['synthetic_database']['header_id']='journal'
    with pytest.raises(ValueError,match='HEADER_MAPPING'):DriveResourceBackend(t,mapping,'backup')
