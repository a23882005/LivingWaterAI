"""Fetch approved private mapping and provision state through existing host SSH.

Build outputs contain secrets and MUST NOT be uploaded as workflow artifacts.
"""
import json
import os
from pathlib import Path
import shutil
import sys
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from drive_service_transport import GoogleDriveTransport
from private_runtime import provision, read_private
from private_service_config import load_key

CONFIG_ID='1SSzUJxwhNxR-HS8jQXc3vQ_yfraM-P6v'
PRIVATE_PARENT='1Wa1u6rViRwcRTqf7hI4Rug8dA0sVCIPw'


def private_meta(d,id_,parent):
    m=d.call('https://www.googleapis.com/drive/v3/files/'+id_+'?fields=id,parents,trashed,permissions(type,role)')
    permissions=m.get('permissions',[])
    if m.get('trashed') or parent not in m.get('parents',[]) or not permissions or any(p.get('type')!='user' or p.get('role')!='owner' for p in permissions):
        raise ValueError('PRIVATE_DRIVE_LOCATION_REQUIRED')


def build():
    os.umask(0o077)
    creds={key:os.environ['FAMILY_DRIVE_'+env] for key,env in [('client_id','CLIENT_ID'),('client_secret','CLIENT_SECRET'),('refresh_token','REFRESH_TOKEN')]}
    d=GoogleDriveTransport(**creds)
    private_meta(d,CONFIG_ID,PRIVATE_PARENT)
    resource=json.loads(d.call('https://www.googleapis.com/drive/v3/files/'+CONFIG_ID+'?alt=media',raw=True))
    private_meta(d,resource['backup_folder'],PRIVATE_PARENT)
    resource['deployment']['lock_dir']='resource-locks'
    config={'schema':'Family-B07-private-runtime-v1','enabled':False,'source_commit':os.environ['GITHUB_SHA'],
        'resource_config':resource,'google_oauth':creds,'backup_access_verified':'OWNER_ONLY'}
    out=Path('build/family-b07-runtime/private');out.mkdir(parents=True,mode=0o700)
    (out/'input.json').write_text(json.dumps(config,ensure_ascii=False));(out/'input.json').chmod(0o600)
    for name in ('private_service_config.py','private_runtime.py'):
        shutil.copyfile(BASE/name,out/name)
    shutil.copyfile(Path(__file__),out/'provision_private_runtime.py')
    # Dependencies imported at module load also accompany the isolated installer.
    shutil.copyfile(BASE/'drive_service_transport.py',out/'drive_service_transport.py')
    print('PRIVATE_INPUT_PREPARED')


def install(root):
    here=Path(__file__).resolve().parent
    result=provision(root,here/'input.json')
    before=load_key(root);result2=provision(root,here/'input.json')
    if load_key(root)!=before or result2!=result:raise ValueError('REPROVISION_MISMATCH')
    # No token, key fingerprint, provider body, credentials or user data in logs.
    print('FAMILY_B07_PRIVATE_RUNTIME '+json.dumps(result))


if __name__=='__main__':
    try:
        if sys.argv[1]=='build':build()
        elif sys.argv[1]=='install':install(sys.argv[2])
        else:raise ValueError('MODE')
    except Exception as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__}))
        raise SystemExit(1)
