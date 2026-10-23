"""Temporary hosted B07 test worker; private config, fixed approved TEMP only."""
import importlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
import fcntl
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from account_http import AccountHTTP,RateLimiter
from b07_account_integration import ServiceProbe
from b06_drive_integration import initialize,clean,header
from actions_drive_write_probe import TEST_ID,TEMP_FOLDER,BACKUP_FOLDER
from drive_resource_backend import DriveResourceBackend
from drive_service_transport import ServiceTransportError
a=importlib.import_module('帳號管理')

def configuration():
    c=json.loads((BASE/'config.json').read_text())
    for key,value in c['oauth'].items():os.environ[key]=value
    return c

def store(d,p):
    h=dict(header(),resource_key='accounts',policy_ref='accounts')
    b=DriveResourceBackend(d,{TEST_ID:dict(parent_id=TEMP_FOLDER,journal_id=p['b06_journal'],
        journal_parent_id=TEMP_FOLDER,header_id=p['b06_header'],header_template=h)},BACKUP_FOLDER)
    policy={'accounts':{'read':['service:account-manager'],'update':['service:account-manager']}}
    return a.B06AccountStore({'accounts':h},policy,b,BASE/'locks')

def main(mode):
    os.umask(0o077)
    c=configuration();d=ServiceProbe()
    d.transport.timeout=60  # Hosted outbound requests retain a finite bound.
    if mode=='cleanup':
        result=clean(d);print(json.dumps({'cleanup':result}));return
    if mode=='init':
        clean(d);p=initialize(d)
        (BASE/'runtime.json').write_text(json.dumps(p))
        def seed(db):
            for statement in a.SCHEMA.split(';'):
                if statement.strip() and not statement.strip().startswith('PRAGMA'):db.execute(statement)
            for item in c['seeds']:
                a._insert(db,item['user_id'],item['password'],item['role'],int(time.time())+3600)
            return {'seeded':True}
        for attempt in range(3):
            try:
                store(d,p).mutate('b07-http-seed','b07-http-synthetic-v1',seed)
                break
            except ServiceTransportError:
                if attempt==2:raise
                # Re-enter Coordinator recovery using the same receipt ID;
                # never blindly replay a provider PATCH with unknown outcome.
                time.sleep(2)
        print(json.dumps({'status':'INITIALIZED_SYNTHETIC_TEMP'}));return
    if mode!='call':raise ValueError('MODE')
    request=json.loads(sys.stdin.buffer.read(20000))
    p=json.loads((BASE/'runtime.json').read_text());key=bytes.fromhex(c['server_key'])
    manager=a.AccountManager(store(d,p),key)
    app=AccountHTTP(manager,c['origin'],'b07-http-'+c['run'],RateLimiter(BASE/'rate.db',key))
    status,headers,body=app.handle(request['method'],request['path'],request['headers'],request['body'].encode(),request['peer'])
    print(json.dumps({'status':status,'headers':headers,'body':body.decode()}))

if __name__=='__main__':
    try:
        # A web-server timeout may leave its child finishing a durable write.
        # Cleanup must wait for that child, including after a lost HTTP reply.
        with (BASE/'call.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            main(sys.argv[1])
    except Exception as error:
        # Provider/credential/request exception details never reach logs.
        report={'error':'SERVICE_RETRY'}
        if sys.argv[1] != 'call':
            report['error_type']=type(error).__name__
            report['frames']=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno}
                              for f in traceback.extract_tb(error.__traceback__)
                              if Path(f.filename).parent==BASE]
        print(json.dumps(report));raise SystemExit(1)
