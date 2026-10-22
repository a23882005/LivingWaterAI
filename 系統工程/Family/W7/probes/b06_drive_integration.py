"""Exercise the generic B06 coordinator against the approved TEMP database.

Durable resource pointers on that DB permit fresh-worker cleanup after failure.
Only synthetic tables/identities; restore original bytes before removing pointers.
"""
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from actions_drive_write_probe import Drive, API, TEST_ID, TEMP_FOLDER, BACKUP_FOLDER, target, KEYS
from resource_headers import SCHEMA, VerifiedPrincipal, render_header, parse_header
from drive_resource_backend import DriveResourceBackend, UPLOAD
w=importlib.import_module('資料存取管理')
FIELDS=('b06_journal','b06_header','b06_base','b06_basehash')
BUILD=Path('build/family-b06')

def header():
    return dict(schema=SCHEMA,resource_key='test.b06',binding='BOUND',file_id=TEST_ID,
                policy_ref='test.b06',state='Close',readers=[],updater=None)

def principal():return VerifiedPrincipal('account:synthetic',int(time.time())+1800)

def create(d,name,mime,data):
    id_=d.call(API.rstrip('/')+'?fields=id','POST',{'name':name,'mimeType':mime,'parents':[TEMP_FOLDER]})['id']
    d.call(UPLOAD+id_+'?uploadType=media','PATCH',data)
    if d.call(API+id_+'?alt=media',raw=True)!=data:raise RuntimeError('create_readback')
    return id_

def initialize(d):
    p=target(d)
    if any(p.get(k) for k in KEYS) or p.get('b04s_run'):raise RuntimeError('other_probe_pending')
    if any(p.get(k) for k in FIELDS):
        if not all(p.get(k) for k in FIELDS):raise RuntimeError('incomplete_b06_pointer')
        return p
    original=d.read()
    base=d.call(API+TEST_ID+'/copy?fields=id','POST',{'name':'Family_B06_TEMP_baseline.db','parents':[BACKUP_FOLDER],
        'appProperties':{'b06_source':TEST_ID,'b06_sha256':w.digest(original)}})['id']
    if d.read(base)!=original or d.read()!=original:raise RuntimeError('baseline_mismatch')
    journal=create(d,'Family_B06_TEMP_journal.json','application/json',b'null')
    hdr=create(d,'Family_B06_TEMP_header.md','text/markdown',render_header(header()).encode())
    values=dict(zip(FIELDS,(journal,hdr,base,w.digest(original))))
    d.call(API+TEST_ID,'PATCH',{'appProperties':values})
    p=target(d)
    if any(p.get(k)!=v for k,v in values.items()):raise RuntimeError('pointer_readback')
    return p

def add(db,p):
    db.execute('create table if not exists b06_test_counter(n integer not null)')
    if not db.execute('select count(*) from b06_test_counter').fetchone()[0]:db.execute('insert into b06_test_counter values(0)')
    db.execute('update b06_test_counter set n=n+?',(p['delta'],))
    return db.execute('select n from b06_test_counter').fetchone()[0]

def coordinator(d,p,crash=False):
    backend=DriveResourceBackend(d,{TEST_ID:dict(parent_id=TEMP_FOLDER,journal_id=p['b06_journal'],
        journal_parent_id=TEMP_FOLDER,header_id=p['b06_header'],header_template=header())},BACKUP_FOLDER)
    if crash:
        original_write=backend.write
        def write(id_,data):original_write(id_,data);os._exit(73)
        backend.write=write
    return w.Coordinator({'test.b06':header()},{'test.b06':{'read':['account:synthetic'],'update':['account:synthetic']}},
        backend,BUILD/'locks',{'add':add},restore_subjects=['account:synthetic'])

def clean(d):
    p=target(d)
    if not any(p.get(k) for k in FIELDS):return {'state':'CLEAN'}
    if not all(p.get(k) for k in FIELDS):raise RuntimeError('incomplete_b06_pointer')
    m=coordinator(d,p);s=m.snapshot('test.b06',principal())
    base=d.read(p['b06_base'])
    if w.digest(base)!=p['b06_basehash']:raise RuntimeError('baseline_hash')
    if s['data']!=base:m.restore('test.b06',principal(),p['b06_base'],s['epoch'],'cleanup-'+s['epoch'])
    if d.read()!=base:raise RuntimeError('restore_bytes')
    # Keep immutable backups. Temporary metadata is trashed only after restore.
    d.call(API+TEST_ID,'PATCH',{'appProperties':{k:None for k in FIELDS}})
    if any(target(d).get(k) for k in FIELDS):raise RuntimeError('pointer_cleanup')
    for k in ('b06_journal','b06_header'):d.call(API+p[k],'PATCH',{'trashed':True})
    return {'state':'RESTORED','bytes':len(base),'sha256':w.digest(base),'baseline_backup':p['b06_base']}

def main(mode):
    BUILD.mkdir(parents=True,exist_ok=True)
    report={'scope':'APPROVED_TEMP_SYNTHETIC_ONLY','mode':mode,'status':'FAIL','stage':'oauth'}
    try:
        d=Drive()
        if mode=='cleanup':report['cleanup']=clean(d)
        elif mode in ('worker','crash'):
            p=target(d);m=coordinator(d,p,mode=='crash')
            m.update('test.b06',principal(),sys.argv[2],sys.argv[3],'add',{'delta':int(sys.argv[4])})
            return 0
        else:
            report['stage']='initialize'
            report['prior_cleanup']=clean(d)
            p=initialize(d);m=coordinator(d,p);s=m.snapshot('test.b06',principal())
            report['stage']='crash-and-retry'
            worker=subprocess.run([sys.executable,__file__,'crash','crash-one',s['epoch'],'2'],timeout=240)
            if worker.returncode!=73:raise RuntimeError('crash_not_observed')
            report['crash_exit']=worker.returncode
            fresh=coordinator(Drive(),p)
            retry=fresh.update('test.b06',principal(),'crash-one',s['epoch'],'add',{'delta':2})
            if not retry['duplicate'] or retry['result']!=2:raise RuntimeError('retry_failed')
            report['lost_ack_dedup']=True
            report['stage']='parallel'
            workers=[subprocess.Popen([sys.executable,__file__,'worker','parallel-'+str(i),s['epoch'],'1']) for i in range(2)]
            for worker in workers:
                if worker.wait(timeout=240)!=0:raise RuntimeError('parallel_failed')
            snapshot=fresh.snapshot('test.b06',principal())
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'read.db';path.write_bytes(snapshot['data'])
                with sqlite3.connect(path) as db:
                    value=db.execute('select n from b06_test_counter').fetchone()[0]
                    receipts=db.execute('select count(*) from _family_io_receipts').fetchone()[0]
            if value!=4 or receipts!=3:raise RuntimeError('merge_failed')
            report.update(parallel_value=value,unique_receipts=receipts)
            report['stage']='restore'
            restored=fresh.restore('test.b06',principal(),p['b06_base'],s['epoch'],'restore-baseline')
            if d.read()!=s['data']:raise RuntimeError('restore_not_exact')
            report['exact_restore']=True
            try:fresh.update('test.b06',principal(),'old-work',s['epoch'],'add',{'delta':50})
            except RuntimeError as exc:
                if str(exc)!='STALE_EPOCH':raise
                report['old_epoch_rejected']=True
            else:raise RuntimeError('old_epoch_accepted')
            hdr=parse_header(d.call(API+p['b06_header']+'?alt=media',raw=True).decode())
            if hdr['state']!='Close' or hdr['updater'] is not None:raise RuntimeError('header_not_closed')
            report['header_closed']=True
            report['stage']='cleanup'
            report['cleanup']=clean(d)
        report['status']='PASS'
        report['stage']='complete'
    except Exception as exc:
        report['error_type']=type(exc).__name__
        if hasattr(exc,'code'):report['http_status']=exc.code
    (BUILD/('drive-'+mode+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else 'verify'))
