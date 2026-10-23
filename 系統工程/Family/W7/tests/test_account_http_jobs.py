import importlib
import json
from pathlib import Path
import sys
import pytest
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
sys.path.insert(0,str(BASE/'probes'))
worker=importlib.import_module('b07_http_worker')

@pytest.mark.parametrize('failed',[False,True])
def test_private_job_result_is_atomic_and_removes_request(tmp_path,monkeypatch,failed):
    monkeypatch.setattr(worker,'BASE',tmp_path)
    jobs=tmp_path/'jobs';jobs.mkdir()
    job='a'*48;request=jobs/(job+'.request.json')
    request.write_text(json.dumps({'body':'synthetic-private-password'}))
    calls=[]
    def run(mode,payload=None):
        calls.append(payload)
        if failed:raise RuntimeError('synthetic-private-password')
        print(json.dumps({'status':200,'headers':[],'body':'done'}))
    monkeypatch.setattr(worker,'main',run)
    with pytest.raises(RuntimeError):worker.wait_jobs(timeout=0)
    worker.run_mode('job',job)
    result=jobs/(job+'.result.json');value=json.loads(result.read_text())
    assert value['status']==(503 if failed else 200)
    assert 'synthetic-private-password' not in result.read_text()
    assert result.stat().st_mode&0o777==0o600 and not request.exists()
    worker.wait_jobs(timeout=0)
    worker.run_mode('job',job)
    assert len(calls)==1

def test_job_identifier_cannot_select_a_path(tmp_path,monkeypatch):
    monkeypatch.setattr(worker,'BASE',tmp_path)
    for name in ['../config','b'*49,'A'*48,None]:
        with pytest.raises(ValueError):worker.run_mode('job',name)
    assert not list(tmp_path.iterdir())
