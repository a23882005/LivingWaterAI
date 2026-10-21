from copy import deepcopy
import hashlib
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from replay import ReplayError, digest, instant, verify_files, select_vintage, verify_lineage, validate_event, replay


def event():
    return dict(schema_version='Family.BR.Event.v1',event_id='E1',client_id='TEST-A',
        account_id='ACCOUNT-A',funding_domain_id='FUND-A',event_time='2020-01-02T00:00:00Z',
        snapshot_id='S1',data_kind='SYNTHETIC',versions={'engine':'locked-v1'},
        input={'quantity':'10'},input_sha256=digest({'quantity':'10'}),
        portfolio_before=[],portfolio_after=[],value_state='KNOWN',issue_codes=[],
        sources=[dict(source_id='SRC',payload={'p':'20'},sha256=digest({'p':'20'}),
            basis='RAW',evidence_ref='synthetic-fixture')])


def check(e,mode='SYNTHETIC'):
    return validate_event(e,'TEST-A',{'engine':'locked-v1'},mode)


def test_empty_portfolio_is_explicit_and_input_unchanged():
    e=event(); before=deepcopy(e)
    assert check(e)==before and e==before


@pytest.mark.parametrize('key,value,reason',[
    ('client_id','TEST-B','CLIENT_MISMATCH'),('account_id','','EVENT_IDENTITY'),
    ('versions',{'engine':'new'},'ENGINE_VERSION'),('data_kind','HISTORICAL','DATA_KIND'),
    ('input',{'quantity':'11'},'INPUT_HASH'),('value_state','UNKNOWN','QUALITY'),
    ('issue_codes',['STALE'],'QUALITY'),('event_time','2020-01-02','TIMEZONE')])
def test_invalid_event(key,value,reason):
    e=event();e[key]=value
    with pytest.raises(ReplayError,match=reason):check(e)


def test_missing_field():
    e=event();del e['snapshot_id']
    with pytest.raises(ReplayError,match='FIELDS'):check(e)


@pytest.mark.parametrize('field',['client_id','account_id','funding_domain_id'])
def test_cross_scope(field):
    e=event(); row={k:e[k] for k in ('client_id','account_id','funding_domain_id')}
    row[field]='OTHER';e['portfolio_before']=[row]
    with pytest.raises(ReplayError,match='SCOPE'):check(e)


@pytest.mark.parametrize('kind',['hash','basis','evidence'])
def test_sources(kind):
    e=event();s=e['sources'][0]
    if kind=='hash':s['payload']['p']='21'
    elif kind=='basis':s['basis']='UNKNOWN'
    else:s['evidence_ref']=''
    with pytest.raises(ReplayError):check(e)


def test_historical_requires_time_evidence_and_blocks_future():
    e=event();e['data_kind']='HISTORICAL'
    with pytest.raises(ReplayError,match='UNPROVEN'):check(e,'HISTORICAL')
    s=e['sources'][0];s.update(available_at=e['event_time'],publication_evidence='fixture-proof')
    assert check(e,'HISTORICAL')==e
    s['available_at']='2020-01-02T00:00:01Z'
    with pytest.raises(ReplayError,match='LOOK_AHEAD'):check(e,'HISTORICAL')


def vintage(available,value=1):
    return dict(series_id='X',available_at=available,observation_at='2020-01-01T00:00:00Z',
        revision=str(value),evidence_ref='SYNTHETIC',value=value)


def test_revision_cutoff_and_timezone():
    rows=[vintage('2020-01-02T00:00:00Z'),vintage('2020-01-03T00:00:00Z',2)]
    assert select_vintage(rows,'2020-01-02T08:00:00+08:00')['X']['value']==1
    assert select_vintage(rows,'2020-01-03T00:00:00Z')['X']['value']==2
    assert select_vintage(rows,'2020-01-01T00:00:00Z')=={}
    assert select_vintage([],'2020-01-01T00:00:00Z')=={}


def test_conflicting_same_time_revision():
    with pytest.raises(ReplayError,match='AMBIGUOUS'):
        select_vintage([vintage('2020-01-02T00:00:00Z'),vintage('2020-01-02T00:00:00Z',2)],'2020-01-03T00:00:00Z')


def node(payload,parents):
    body=dict(payload=payload,parents=parents)
    return dict(**body,sha256=digest(body))


def test_shared_lineage_ancestor():
    nodes={'s':node({'raw':1},[]),'a':node(2,['s']),'b':node(3,['s']),'r':node(4,['a','b'])}
    assert verify_lineage(nodes,'r')==4
    nodes['s']['payload']['raw']=2
    with pytest.raises(ReplayError,match='HASH'):verify_lineage(nodes,'r')


@pytest.mark.parametrize('nodes,reason',[
    ({'r':node(1,['absent'])},'BROKEN'),
    ({'r':node(1,['r'])},'CYCLE'),
    ({'r':node(1,[]),'orphan':node(2,[])},'UNREFERENCED')])
def test_invalid_lineage(nodes,reason):
    with pytest.raises(ReplayError,match=reason):verify_lineage(nodes,'r')


def test_file_lock_and_path_escape(tmp_path):
    p=tmp_path/'engine.py';p.write_text('fixed')
    lock={'engine.py':hashlib.sha256(p.read_bytes()).hexdigest()}
    assert verify_files(tmp_path,lock)==1
    p.write_text('changed')
    with pytest.raises(ReplayError,match='HASH'):verify_files(tmp_path,lock)
    with pytest.raises(ReplayError,match='OUTSIDE'):verify_files(tmp_path,{'../outside':'0'})
    with pytest.raises(ReplayError,match='EMPTY'):verify_files(tmp_path,{})


def test_replay_recomputes_and_reports_field_diff(tmp_path):
    p=tmp_path/'engine.py';p.write_text('fixed');lock={'engine.py':hashlib.sha256(p.read_bytes()).hexdigest()}
    calls=[]
    def compute(x):calls.append(1);return {'amount':'20','action':'HOLD'}
    args=dict(engine=compute,expected_client='TEST-A',expected_versions={'engine':'locked-v1'},source_root=tmp_path,source_lock=lock)
    r=replay(event(),golden={'amount':'20','action':'HOLD'},**args)
    assert r['status']=='PASS' and len(calls)==2
    r=replay(event(),golden={'amount':'21','action':'HOLD'},**args)
    assert r['status']=='FAIL' and r['golden_diff'][0]['path']=='$["amount"]'
    args['engine']=lambda x: {'counter':len(calls)} if calls.append(1) is None else None
    assert replay(event(),golden={},**args)['repeat_diff']


def test_invalid_input_never_calls_engine(tmp_path):
    p=tmp_path/'engine.py';p.write_text('fixed');lock={'engine.py':hashlib.sha256(p.read_bytes()).hexdigest()}
    e=event();e['client_id']='OTHER';calls=[]
    with pytest.raises(ReplayError):
        replay(e,engine=lambda x:calls.append(x),expected_client='TEST-A',expected_versions={'engine':'locked-v1'},source_root=tmp_path,source_lock=lock,golden={})
    assert calls==[]
