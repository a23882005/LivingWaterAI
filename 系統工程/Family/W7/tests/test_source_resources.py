import copy
import hashlib
import json
import sys
from pathlib import Path
import pytest
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from source_resources import *

def setup():
    return (json.loads((BASE/'B05_SOURCE_CATALOG.json').read_text()),
            json.loads((BASE/'B03_ACCESS_INVENTORY.json').read_text()),
            json.loads((BASE/'source_policies.json').read_text()))

def test_complete_inventory_and_colocated_headers():
    c,i,p=setup(); rows=validate_source_catalog(c,i,p)
    assert len(rows)==169
    assert sum(r['category']=='readonly_resource' for r in rows.values())==40
    root=BASE.parents[2]
    for r in rows.values():
        if r['header_path']:
            h=json.loads((root/r['header_path']).read_text())
            assert r in h['resources']
            assert h['policy_catalog']=='系統工程/Family/W7/source_policies.json'

@pytest.mark.parametrize('bad',['missing','duplicate','write','misplaced','traversal'])
def test_corrupt_catalog_rejected(bad):
    c,i,p=setup();r=next(r for r in c['entries'] if r['category']=='readonly_resource')
    if bad=='missing': c['entries'].pop()
    if bad=='duplicate': c['entries'].append(c['entries'][0])
    if bad=='write': p['source.runtime']['update']=['account:mou']
    if bad=='misplaced': r['header_path']='elsewhere/header.json'
    if bad=='traversal': r['path']='../bad'; i['rows'][next(n for n,x in enumerate(i['rows']) if x['path']== 'config/ib_global_symbols.txt')]['path']='../bad'
    with pytest.raises(ValueError): validate_source_catalog(c,i,p)

def test_readonly_bytes_and_tamper_detection():
    c,i,p=setup(); r=copy.deepcopy(next(r for r in c['entries'] if r['category']=='readonly_resource'))
    data=b'synthetic';r['git_blob']=hashlib.sha1(b'blob 9\0'+data).hexdigest()
    for who in p['source.runtime']['read']:
        assert verified_source_bytes(r,p,VerifiedPrincipal(who,100),'read',99,data)==data
    with pytest.raises(ValueError):verified_source_bytes(r,p,VerifiedPrincipal('account:mou',100),'read',99,b'changed')
    with pytest.raises(PermissionError):verified_source_bytes(r,p,VerifiedPrincipal('account:mou',100),'update',99,data)
    with pytest.raises(PermissionError):verified_source_bytes(r,p,VerifiedPrincipal('account:mou',99),'read',99,data)
    with pytest.raises(PermissionError):verified_source_bytes(r,p,{'subject':'account:mou'},'read',99,data)
    with pytest.raises(PermissionError):verified_source_bytes(r,p,VerifiedPrincipal('account:outsider',100),'read',99,data)

def test_qa_and_code_not_runtime_data():
    c,i,p=setup()
    for r in c['entries']:
        if r['category']!='readonly_resource':
            with pytest.raises(PermissionError):verified_source_bytes(r,p,VerifiedPrincipal('service:family-runtime',100),'read',99,b'')
