from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'runtime')]
from test_history_audit import fixture
from audit_existing_history import audit
from source_registry import build_registry, read_snapshot
from replay import digest, ReplayError


def prepared(tmp):
    fixture(tmp);out=tmp/'audit.json';audit(tmp,out)
    a=json.loads(out.read_text());r=build_registry(tmp,a,trusted_audit_sha256=digest(a))
    return a,r


def read(tmp,r,**overrides):
    args=dict(trusted_registry_sha256=digest(r),symbol='TEST',cutoff='2020-01-03T00:00:00Z',purpose='ARCHIVE_READ_ONLY')
    args.update(overrides);return read_snapshot(tmp,r,**args)


def test_capture_boundary_and_explicit_read_purpose(tmp_path):
    _,r=prepared(tmp_path);x=read(tmp_path,r)
    assert len(x['rows'])==2 and not x['decision_eligible'] and not x['historical_pit_verified']
    with pytest.raises(ReplayError,match='NO_SOURCE'):read(tmp_path,r,cutoff='2020-01-02T23:59:59.999999Z')
    assert read(tmp_path,r,cutoff='2020-01-03T08:00:00+08:00')['rows']==x['rows']


@pytest.mark.parametrize('purpose,code',[('DECISION_INPUT','BASIS'),('HISTORICAL_REPLAY','PUBLICATION'),('FREE','PURPOSE')])
def test_unknown_conventions_cannot_be_promoted(tmp_path,purpose,code):
    _,r=prepared(tmp_path)
    with pytest.raises(ReplayError,match=code):read(tmp_path,r,purpose=purpose)


def test_registry_rehash_cannot_replace_release_pin(tmp_path):
    _,r=prepared(tmp_path);pin=digest(r)
    r['entries'][0]['available_at']='1990-01-01T00:00:00Z'
    with pytest.raises(ReplayError,match='DIGEST'):read(tmp_path,r,trusted_registry_sha256=pin)


@pytest.mark.parametrize('name',['TEST.csv','TEST.csv.result.json','TEST.family_context.json'])
def test_source_changed_after_registration(tmp_path,name):
    _,r=prepared(tmp_path);p=tmp_path/name;p.write_text(p.read_text()+' ')
    with pytest.raises(ReplayError,match='SOURCE_CHANGED'):read(tmp_path,r)


def test_fake_audit_metadata_and_path_escape_rejected(tmp_path):
    a,r=prepared(tmp_path)
    with pytest.raises(ReplayError,match='AUDIT_DIGEST'):build_registry(tmp_path,a,trusted_audit_sha256='0'*64)
    a['entries'][0]['snapshot_available_at']='1990-01-01T00:00:00Z'
    with pytest.raises(ReplayError,match='METADATA'):build_registry(tmp_path,a,trusted_audit_sha256=digest(a))
    a['entries'][0]['file']='../outside.csv'
    with pytest.raises(ReplayError,match='PATH'):build_registry(tmp_path,a,trusted_audit_sha256=digest(a))


def test_gap_claims_derived_from_original_metadata(tmp_path):
    a,_=prepared(tmp_path);a['entries'][0]['historical_gaps']=[]
    r=build_registry(tmp_path,a,trusted_audit_sha256=digest(a))
    assert 'PER_BAR_PUBLICATION_UNPROVEN' in r['entries'][0]['history_gaps']


def test_revision_selection_and_tie_rejection(tmp_path):
    _,r=prepared(tmp_path);later=deepcopy(r['entries'][0]);later['available_at']='2020-01-04T00:00:00Z'
    r['entries'].append(later)
    assert read(tmp_path,r)['available_at']=='2020-01-03T00:00:00Z'
    assert read(tmp_path,r,cutoff='2020-01-04T00:00:00Z')['available_at']==later['available_at']
    r['entries'].append(deepcopy(later))
    with pytest.raises(ReplayError,match='AMBIGUOUS'):read(tmp_path,r,cutoff=later['available_at'])
