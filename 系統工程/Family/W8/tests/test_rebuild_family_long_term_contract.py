"""Exercise the actual engineering generator in isolated public-source copies."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[4]
BASE=Path('系統工程/C-配置決策引擎＋Mentor整合/正式Runtime')
MANIFEST=BASE/'contracts_c7/Family_LongTerm_V70Ceiling_v1.manifest.json'
TOOL=Path('系統工程/Family/W8/tools/rebuild_family_long_term_contract.py')
DEPENDENCIES=Path('系統工程/Family/W5/dependency_lock.json')
SOURCE_LOCK=Path('系統工程/Family/W5/source_lock.json')

def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

@pytest.fixture
def isolated(tmp_path):
    paths={MANIFEST,TOOL,DEPENDENCIES,SOURCE_LOCK,
        BASE/'contracts_c7/57_C_Work6_Mentor_Adjustment_Result.schema.json',
        BASE/'contracts_c7/68_C_Work7_V70_Asset_Framework_Result.schema.json'}
    lock=read(ROOT/DEPENDENCIES)
    paths.update(Path(r['path']) for r in (lock['files'] if isinstance(lock,dict) else lock))
    paths.update(Path(r['path']) for r in read(ROOT/SOURCE_LOCK)['files'])
    paths.update((ROOT/BASE/r['path']).resolve().relative_to(ROOT) for r in read(ROOT/MANIFEST)['files'])
    for path in paths:
        dst=tmp_path/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/path,dst)
    return tmp_path

def run(root):
    return subprocess.run([sys.executable,'-B',str(root/TOOL)],capture_output=True,text=True)

def snapshot(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_rebuild_retains_every_registered_file_order_and_contract(isolated):
    root=isolated;before=read(root/MANIFEST);source=(root/SOURCE_LOCK).read_bytes()
    schemas={p:p.read_bytes() for p in (root/BASE/'contracts_c7').glob('8[345]_*.schema.json')}
    result=run(root);assert result.returncode==0,result.stderr
    after=read(root/MANIFEST)
    assert [r['path'] for r in after['files']]==[r['path'] for r in before['files']]
    assert {k:v for k,v in after.items() if k!='files'}=={k:v for k,v in before.items() if k!='files'}
    assert all(sha256((root/BASE/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in after['files'])
    assert (root/SOURCE_LOCK).read_bytes()==source
    assert all(p.read_bytes()==raw for p,raw in schemas.items())
    lock=read(root/DEPENDENCIES);rows=lock['files'] if isinstance(lock,dict) else lock
    assert all(sha256((root/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in rows)
    once=snapshot(root);assert run(root).returncode==0;assert snapshot(root)==once

def test_future_registration_and_row_metadata_survive_in_original_order(isolated):
    root=isolated;m=read(root/MANIFEST)
    extra=root/'系統工程/Family/W8/SYNTHETIC_FUTURE_SOURCE.py';extra.write_text('# synthetic source registration\n')
    row={'path':'../../Family/W8/SYNTHETIC_FUTURE_SOURCE.py','sha256':'0'*64,'reason':'SYNTHETIC_REGISTRATION_METADATA'}
    m['files'].insert(1,row);m['registration_metadata']='SYNTHETIC_METADATA';write(root/MANIFEST,m)
    result=run(root);assert result.returncode==0,result.stderr
    after=read(root/MANIFEST)
    assert [r['path'] for r in after['files']]==[r['path'] for r in m['files']]
    assert after['registration_metadata']=='SYNTHETIC_METADATA'
    assert after['files'][1]=={**row,'sha256':sha256(extra.read_bytes()).hexdigest()}
    rows=read(root/DEPENDENCIES);rows=rows['files'] if isinstance(rows,dict) else rows
    assert next(r for r in rows if r['path']==str(extra.relative_to(root)))['sha256']==after['files'][1]['sha256']

@pytest.mark.parametrize('change,code',[
    ('approval','APPROVAL_MISMATCH'),('profile','APPROVAL_MISMATCH'),
    ('missing','REGISTERED_FILE_MISSING'),('escape','INVALID_REGISTERED_PATH'),
    ('absolute','INVALID_REGISTERED_PATH'),('duplicate_alias','INVALID_REGISTERED_PATH')])
def test_invalid_registration_fails_before_any_generated_file_is_written(isolated,change,code):
    root=isolated;m=deepcopy(read(root/MANIFEST))
    if change=='approval':m['approval_sha256']='0'*64
    elif change=='profile':m['profile']='SYNTHETIC_WRONG_PROFILE'
    elif change=='missing':m['files'].append({'path':'../../Family/W8/SYNTHETIC_MISSING.py','sha256':'0'*64})
    elif change=='escape':m['files'].append({'path':'../../../../SYNTHETIC_OUTSIDE.py','sha256':'0'*64})
    elif change=='absolute':m['files'].append({'path':str((root/TOOL).resolve()),'sha256':'0'*64})
    else:m['files'].append({**m['files'][0],'path':'./'+m['files'][0]['path']})
    write(root/MANIFEST,m);before=snapshot(root)
    result=run(root);assert result.returncode!=0 and code in result.stderr
    assert snapshot(root)==before
