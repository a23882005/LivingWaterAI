import copy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import pytest
from report_archive import DriveReportStore, publish_report, previous_report, report_basename


class Auth:
    active = True
    def require_login(self):
        if not self.active: raise PermissionError('LOGIN')
        return 'JO'


class Drive:
    def __init__(self):
        self.files = {}; self.seq = 0; self.calls = []; self.fail_upload = False
        self.public = False; self.corrupt = False; self.fail_manifest = False
    def call(self, url, method='GET', data=None, raw=False):
        self.calls.append((url, method))
        parts=urlsplit(url); path=parts.path; q=parse_qs(parts.query)
        if path.endswith('/generateIds'):
            self.seq += 1; return {'ids':[f'file_{self.seq}']}
        if path.endswith('/folder/permissions'):
            return {'permissions':[{'type':'anyone' if self.public else 'user','role':'owner'}]}
        if path.endswith('/folder'):
            return {'id':'folder','mimeType':'application/vnd.google-apps.folder'}
        if path.endswith('/files') and method=='POST':
            self.files[data['id']] = dict(copy.deepcopy(data), content=b'')
            return {'id':data['id']}
        if path.endswith('/files'):
            query=q['q'][0]
            kind='manifest' if "value='manifest'" in query else None
            rows=[{k:v for k,v in f.items() if k!='content'} for f in self.files.values()
                  if not kind or f['appProperties']['family_kind']==kind]
            return {'files':rows}
        fid=path.rsplit('/',1)[1]; f=self.files[fid]
        if method=='PATCH':
            if isinstance(data,dict): f.update(copy.deepcopy(data)); return {}
            if self.fail_manifest and f['appProperties']['family_kind']=='staged_manifest':
                raise RuntimeError('MANIFEST_UPLOAD_FAILED')
            if self.fail_upload: raise RuntimeError('UPLOAD_FAILED')
            f['content']=data; return {}
        if q.get('alt')==['media']:
            return b'bad-readback' if self.corrupt else f['content']
        return {k:v for k,v in f.items() if k!='content'}


@pytest.fixture
def env(tmp_path):
    lock=tmp_path/'writer.lock'; lock.touch()
    drive=Drive(); auth=Auth()
    return DriveReportStore(drive, folder_id='folder', lock_path=lock), auth, drive


def publish(store,auth,run='r1',when=None,artifacts=None):
    return publish_report(store,auth,run_id=run, artifacts=artifacts or {'report.pdf':b'completed-renderer'},
        data_as_of='2026-10-23',analysis_version='test-only',
        created_at=when or datetime(2026,10,24,0,0,0,tzinfo=timezone.utc))


def test_taiwan_date_boundary_and_timezone_required():
    assert report_basename(datetime(2026,10,23,20,tzinfo=timezone.utc)) == 'Joseph_配置報告_20261024_040000_TW'
    with pytest.raises(ValueError): report_basename(datetime(2026,10,24))


def test_saved_single_report_uses_exact_taiwan_timestamp_filename_and_bound_folder(env):
    store,auth,drive=env
    manifest=publish(store,auth,when=datetime(2026,10,24,7,30,45,tzinfo=timezone.utc))
    artifact=manifest['files'][0]
    assert artifact['name']=='Joseph_配置報告_20261024_153045_TW.pdf'
    assert drive.files[artifact['id']]['parents']==[store.folder_id]


def test_multiple_same_extension_outputs_keep_timestamp_and_distinct_suffixes(env):
    store,auth,drive=env
    manifest=publish(store,auth,artifacts={
        'report.pdf':b'pdf', 'page_01.png':b'page1', 'page_02.png':b'page2'})
    names={f['name'] for f in manifest['files']}
    assert 'Joseph_配置報告_20261024_080000_TW.pdf' in names
    assert 'Joseph_配置報告_20261024_080000_TW_page_01.png' in names
    assert 'Joseph_配置報告_20261024_080000_TW_page_02.png' in names


def test_preserves_old_files_same_second_collision_and_previous(env):
    store,auth,drive=env
    first=publish(store,auth); before=copy.deepcopy(drive.files)
    second=publish(store,auth,'r2')
    assert second['files'][0]['name']=='Joseph_配置報告_20261024_080000_TW_02.pdf'
    for fid,value in before.items(): assert drive.files[fid] == value
    assert previous_report(store,auth)['run_id']=='r2'
    assert previous_report(store,auth,date='2026-10-24')['run_id']=='r2'
    assert previous_report(store,auth,date='2026-10-22') is None
    assert first['created_at'].endswith('+08:00')


def test_replay_same_run_deduplicates_and_payload_conflict_rejects(env):
    store,auth,drive=env
    first=publish(store,auth); size=len(drive.files)
    assert publish(store,auth)==first and len(drive.files)==size
    with pytest.raises(ValueError,match='REPORT_RUN_CONFLICT'):
        publish(store,auth,artifacts={'report.pdf':b'different'})


def test_failed_upload_never_publishes_manifest_or_changes_previous(env):
    store,auth,drive=env; publish(store,auth)
    drive.fail_upload=True
    with pytest.raises(RuntimeError,match='UPLOAD_FAILED'): publish(store,auth,'r2')
    assert previous_report(store,auth)['run_id']=='r1'
    assert len(store.list('manifest'))==1


def test_artifact_integrity_checked_on_retrieval(env):
    store,auth,drive=env; m=publish(store,auth)
    drive.files[m['files'][0]['id']]['content']=b'changed'
    with pytest.raises(RuntimeError,match='REPORT_MANIFEST_INVALID'): previous_report(store,auth)


def test_shared_folder_rejected_before_write(env):
    store,auth,drive=env; drive.public=True
    with pytest.raises(PermissionError): publish(store,auth)
    assert drive.files=={}


def test_unauthenticated_access_rejected_before_drive_call(env):
    store,auth,drive=env; auth.active=False
    with pytest.raises(PermissionError): previous_report(store,auth)
    assert drive.calls==[]


def test_cross_folder_file_rejected(env):
    store,auth,drive=env; m=publish(store,auth)
    drive.files[m['files'][0]['id']]['parents']=['different']
    with pytest.raises(PermissionError): store.read(m['files'][0]['id'])


@pytest.mark.parametrize('artifacts',[{'../report.pdf':b'x'},{'report.exe':b'x'},{'report.pdf':''}])
def test_bad_artifacts_rejected_before_drive(env,artifacts):
    store,auth,drive=env
    with pytest.raises(ValueError): publish(store,auth,artifacts=artifacts)
    assert drive.calls==[]


def test_upload_readback_mismatch_never_completes(env):
    store,auth,drive=env; drive.corrupt=True
    with pytest.raises(RuntimeError,match='REPORT_READBACK_FAILED'): publish(store,auth)
    assert len(store.list('manifest'))==0


def test_incomplete_manifest_is_not_visible_and_previous_is_preserved(env):
    store,auth,drive=env; publish(store,auth,'z_first')
    drive.fail_manifest=True
    with pytest.raises(RuntimeError,match='MANIFEST_UPLOAD_FAILED'):
        publish(store,auth,'a_second')
    assert previous_report(store,auth)['run_id']=='z_first'
    assert len(store.list('manifest'))==1


def test_same_timestamp_previous_uses_collision_sequence_not_run_name(env):
    store,auth,drive=env; publish(store,auth,'z_first'); publish(store,auth,'a_second')
    assert previous_report(store,auth)['run_id']=='a_second'
