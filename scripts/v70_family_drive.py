"""Private Drive JSON writer: exact-name discovery, backup, readback and recovery.

Uses the existing FAMILY_DRIVE OAuth secrets. No new credential or household DB.
Identifiers and payloads belong in private receipts, never Actions stdout.
"""
from __future__ import annotations
import copy,datetime as dt,hashlib,json,os,uuid
from urllib.parse import urlencode
import requests

API='https://www.googleapis.com/drive/v3/files'
UPLOAD='https://www.googleapis.com/upload/drive/v3/files'
BASELINE_NAME='V70_Family_Macro_Safety_Snapshot_20261117.json'
CANDIDATE_NAME='V70_Family_Macro_Safety_Snapshot_20261117_candidate.json'
INTAKE_NAME='V70_Family_Source_Intake_20261117_candidate.json'
ISOLATION_NAME='V70_Family_JSON_Round1_Isolation_20261117.json'
LIMIT=16*1024*1024

def digest(data):return hashlib.sha256(data).hexdigest()
def data_time(data):
    value=json.loads(data)
    s=value.get('feed_asof_utc') or value.get('cutoff')
    if not s:raise ValueError('DOCUMENT_CUTOFF_REQUIRED')
    stamp=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('DOCUMENT_TIMEZONE_REQUIRED')
    return stamp

class Drive:
    def __init__(self):
        keys=('FAMILY_DRIVE_CLIENT_ID','FAMILY_DRIVE_CLIENT_SECRET','FAMILY_DRIVE_REFRESH_TOKEN')
        if any(not os.environ.get(k) for k in keys):raise RuntimeError('EXISTING_DRIVE_OAUTH_SECRETS_UNAVAILABLE')
        r=requests.post('https://oauth2.googleapis.com/token',data=dict(zip(('client_id','client_secret','refresh_token'),(os.environ[k] for k in keys)),grant_type='refresh_token'),timeout=30)
        if r.status_code!=200:raise RuntimeError('DRIVE_OAUTH_REFRESH_FAILED_'+str(r.status_code))
        self.session=requests.Session();self.session.headers['Authorization']='Bearer '+r.json()['access_token']

    def request(self,method,url,**kwargs):
        r=self.session.request(method,url,timeout=(10,40),**kwargs)
        if not r.ok:raise RuntimeError('DRIVE_HTTP_'+str(r.status_code))
        if len(r.content)>LIMIT:raise RuntimeError('DRIVE_RESPONSE_TOO_LARGE')
        return r

    def meta(self,file_id):
        return self.request('GET',API+'/'+file_id,params={'fields':'id,name,mimeType,parents,shared,ownedByMe,trashed,size,version'}).json()

    def find(self,name,parent=None,required=False):
        safe=name.replace("'","\\'")
        query="trashed = false and name = '"+safe+"'"
        if parent:query+=" and '"+parent+"' in parents"
        r=self.request('GET',API,params={'q':query,'fields':'files(id,name,mimeType,parents,shared,ownedByMe,trashed),nextPageToken','pageSize':100}).json()
        if r.get('nextPageToken') or len(r.get('files',[]))>1:raise RuntimeError('AMBIGUOUS_PRIVATE_TARGET')
        if not r.get('files'):
            if required:raise RuntimeError('PRIVATE_BASELINE_NOT_FOUND')
            return None
        meta=r['files'][0];self.private(meta,parent);return meta

    @staticmethod
    def private(meta,parent=None,mime_type='application/json'):
        if meta.get('shared') is not False or meta.get('ownedByMe') is not True or meta.get('trashed'):raise RuntimeError('TARGET_NOT_PRIVATE_OWNED_FILE')
        if parent and parent not in meta.get('parents',[]):raise RuntimeError('PRIVATE_PARENT_MISMATCH')
        if meta.get('mimeType')!=mime_type:raise RuntimeError('TARGET_MIME_MISMATCH')

    def read(self,file_id):return self.request('GET',API+'/'+file_id,params={'alt':'media'}).content

    def create(self,name,parent,data,mime_type='application/json'):
        if len(data)>LIMIT:raise ValueError('PAYLOAD_TOO_LARGE')
        marker='v70_'+uuid.uuid4().hex
        metadata=json.dumps({'name':name,'parents':[parent],'mimeType':mime_type}).encode()
        body=(('--'+marker+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n').encode()+metadata+
              ('\r\n--'+marker+'\r\nContent-Type: '+mime_type+'\r\n\r\n').encode()+data+('\r\n--'+marker+'--\r\n').encode())
        meta=self.request('POST',UPLOAD,params={'uploadType':'multipart','fields':'id,name,mimeType,parents,shared,ownedByMe,trashed'},data=body,headers={'Content-Type':'multipart/related; boundary='+marker}).json()
        self.private(meta,parent,mime_type)
        if self.read(meta['id'])!=data:raise RuntimeError('CREATE_READBACK_MISMATCH')
        return meta

    def backup(self,meta,parent):
        name=meta['name']+'.before_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+os.environ.get('GITHUB_RUN_ID','local')+'.json'
        backup=self.request('POST',API+'/'+meta['id']+'/copy',json={'name':name,'parents':[parent]},params={'fields':'id,name,mimeType,parents,shared,ownedByMe,trashed'}).json()
        self.private(backup,parent);return backup

    def replace(self,file_id,data):
        self.request('PATCH',UPLOAD+'/'+file_id,params={'uploadType':'media'},data=data,headers={'Content-Type':'application/json'})

def checked_update(drive,name,parent,payload,*,allow_formal=False,verify=None):
    if name==BASELINE_NAME and not allow_formal:raise RuntimeError('FORMAL_TARGET_REQUIRES_PM_ENABLEMENT')
    data=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode();data_time(data)
    current=drive.find(name,parent)
    if current is None:
        meta=drive.create(name,parent,data)
        if verify:verify(drive.read(meta['id']))
        return {'status':'CREATED_AND_READ_BACK','file_id':meta['id'],'bytes':len(data),'sha256':digest(data)}
    drive.private(current,parent);before=drive.read(current['id']);prior=json.loads(before)
    if data_time(data)<data_time(before):raise RuntimeError('OLDER_SNAPSHOT_REJECTED')
    if data==before or (payload.get('publication_identity') and prior.get('publication_identity')==payload['publication_identity']):
        return {'status':'UNCHANGED_IDEMPOTENT','file_id':current['id'],'bytes':len(before),'sha256':digest(before)}
    backup=drive.backup(current,parent)
    if drive.read(backup['id'])!=before or drive.read(current['id'])!=before:raise RuntimeError('PREWRITE_BACKUP_OR_CONFLICT_CHECK_FAILED')
    try:
        drive.replace(current['id'],data)
        after=drive.read(current['id'])
        if after!=data:raise RuntimeError('UPDATE_READBACK_MISMATCH')
        if verify:verify(after)
    except Exception:
        # Do not overwrite an unrelated concurrent writer. Preserve the verified
        # backup; recover only a recognized before/after state owned by this update.
        now=drive.read(current['id'])
        if now==data:
            drive.replace(current['id'],before)
            if drive.read(current['id'])!=before:raise RuntimeError('ROLLBACK_READBACK_FAILED')
        elif now!=before:raise RuntimeError('UNEXPECTED_EXTERNAL_CHANGE_BACKUP_RETAINED')
        raise
    return {'status':'UPDATED_BACKED_UP_AND_READ_BACK','file_id':current['id'],'backup_id':backup['id'],'bytes':len(data),'sha256':digest(data),'previous_sha256':digest(before)}

def isolation_roundtrip(drive,parent,payload):
    before=copy.deepcopy(payload);before.pop('publication_identity',None);before['isolation_probe']='before'
    checked_update(drive,ISOLATION_NAME,parent,before)
    meta=drive.find(ISOLATION_NAME,parent,required=True);original=drive.read(meta['id'])
    after=copy.deepcopy(before);after['isolation_probe']='after'
    def fail(_):raise RuntimeError('EXPECTED_ISOLATION_FAILURE')
    try:checked_update(drive,ISOLATION_NAME,parent,after,verify=fail)
    except RuntimeError as exc:
        if str(exc)!='EXPECTED_ISOLATION_FAILURE':raise
    else:raise RuntimeError('EXPECTED_FAILURE_NOT_OBSERVED')
    if drive.read(meta['id'])!=original:raise RuntimeError('ISOLATION_RECOVERY_NOT_IDENTICAL')
    result=checked_update(drive,ISOLATION_NAME,parent,after)
    if drive.read(meta['id'])!=(json.dumps(after,ensure_ascii=False,indent=2)+'\n').encode():raise RuntimeError('ISOLATION_FINAL_READBACK_FAILED')
    return {'status':'WRITE_READBACK_FAILURE_RECOVERY_PASS','file_id':meta['id'],'recovered_previous_sha256':digest(original),'final_sha256':result['sha256']}
