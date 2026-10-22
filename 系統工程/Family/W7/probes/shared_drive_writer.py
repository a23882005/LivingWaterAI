"""TEMP-only single-host writer. Caller serializes queue; flock spans Drive I/O.

Data and request receipts commit in one uploaded SQLite image. A durable Drive
journal resolves uncertain upload acknowledgements before the next operation.
"""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from actions_drive_write_probe import Drive, API, TEST_ID, BACKUP_FOLDER, KEYS, target, checked, digest

PREFIX = 'b04s_'

def props(d):
    p = target(d)
    if any(p.get(k) for k in KEYS):
        raise RuntimeError('other_probe_pending')
    return p

def patch(d, values):
    d.call(API + TEST_ID, 'PATCH', {'appProperties': {PREFIX + k: v for k, v in values.items()}})

def resolve(d, run):
    p = props(d)
    if p.get(PREFIX+'run') != run:
        raise RuntimeError('run_owner_mismatch')
    payload = d.read()
    h = digest(payload)
    before, after = p.get(PREFIX+'before'), p.get(PREFIX+'after')
    if before or after:
        if not before or not after or h not in (before, after):
            raise RuntimeError('uncertain_external_change')
        patch(d, {'last': h, 'before': None, 'after': None})
    elif h != p.get(PREFIX+'last'):
        raise RuntimeError('external_change')
    return payload

def initialize(d, run):
    p = props(d)
    if p.get(PREFIX+'run'):
        if p[PREFIX+'run'] != run: raise RuntimeError('previous_run_needs_cleanup')
        resolve(d, run)
        return
    original = d.read()
    backup = d.backup()
    if d.read(backup) != original or d.read() != original:
        raise RuntimeError('backup_mismatch')
    patch(d, {'run': run, 'base': backup, 'basehash': digest(original), 'last': digest(original)})
    resolve(d, run)

def db_operation(data, account, request_id=None, delta=None):
    if account not in ('synthetic-A', 'synthetic-B'):
        raise RuntimeError('invalid_account')
    checked(data)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'working.db'
        path.write_bytes(data)
        db = sqlite3.connect(path)
        try:
            if request_id is None:
                exists = db.execute("select 1 from sqlite_master where type='table' and name='b04s_counters'").fetchone()
                row = db.execute('select value from b04s_counters where account=?', (account,)).fetchone() if exists else None
                return data, {'value': row[0] if row else 0}
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or type(delta) is not int or abs(delta) > 1000:
                raise RuntimeError('invalid_request')
            db.execute('begin immediate')
            db.execute('create table if not exists b04s_counters(account text primary key,value integer not null)')
            db.execute('create table if not exists b04s_receipts(account text,request_id text,delta integer,result integer,primary key(account,request_id))')
            old = db.execute('select delta,result from b04s_receipts where account=? and request_id=?', (account, request_id)).fetchone()
            if old:
                if old[0] != delta: raise RuntimeError('request_collision')
                db.rollback()
                return data, {'value': old[1], 'duplicate': True}
            db.execute('insert or ignore into b04s_counters values(?,0)', (account,))
            db.execute('update b04s_counters set value=value+? where account=?', (delta, account))
            value = db.execute('select value from b04s_counters where account=?', (account,)).fetchone()[0]
            db.execute('insert into b04s_receipts values(?,?,?,?)', (account,request_id,delta,value))
            db.commit()
        finally:
            db.close()
        return checked(path.read_bytes()), {'value': value, 'duplicate': False}

def deadline(body):
    expires = body.get('expires')
    if type(expires) is not int or time.time() >= expires:
        raise RuntimeError('session_expired')

def apply(d, run, body, crash=False):
    deadline(body)
    original = resolve(d, run)
    candidate, result = db_operation(original, body['account'], body.get('request_id'), body.get('delta'))
    if candidate == original: return result
    backup = d.backup()
    if d.read(backup) != original or d.read() != original:
        raise RuntimeError('prewrite_conflict')
    patch(d, {'before': digest(original), 'after': digest(candidate)})
    p = props(d)
    if p.get(PREFIX+'before') != digest(original) or p.get(PREFIX+'after') != digest(candidate) or d.read() != original:
        raise RuntimeError('journal_conflict')
    deadline(body)
    d.write(candidate)
    if crash: os._exit(73)
    if d.read() != candidate: raise RuntimeError('readback_mismatch')
    patch(d, {'last': digest(candidate), 'before': None, 'after': None})
    return result

def cleanup(d, run):
    p = props(d)
    if not p.get(PREFIX+'run'): return {'state':'CLEAN'}
    # Resolves an upload whose HTTP response was lost before doing any restore.
    resolve(d, run)
    p = props(d)
    meta = d.meta(p[PREFIX+'base'])
    if BACKUP_FOLDER not in meta.get('parents',[]) or meta.get('trashed'):
        raise RuntimeError('baseline_backup_missing')
    original = d.read(p[PREFIX+'base'])
    if digest(original) != p[PREFIX+'basehash']: raise RuntimeError('baseline_mismatch')
    # Restoration itself is journaled and safe to repeat after interruption.
    current = d.read()
    if digest(current) != p[PREFIX+'last']: raise RuntimeError('cleanup_conflict')
    patch(d, {'before': digest(current), 'after': digest(original)})
    d.write(original)
    if d.read() != original: raise RuntimeError('cleanup_readback_failed')
    backup = p[PREFIX+'base']
    patch(d, {k: None for k in ('run','base','basehash','last','before','after')})
    return {'state':'RESTORED','bytes':len(original),'sha256':digest(original),'backup_id':backup}

def main():
    # Secrets are loaded from mode-600 JSON outside public_html, never argv/logs.
    os.umask(0o077)
    private = Path(__file__).resolve().parent
    config = json.loads((private/'config.json').read_text())
    for k,v in config['oauth'].items(): os.environ[k]=v
    os.environ['GITHUB_RUN_ID']=config['run'].split('-')[0]
    os.environ['GITHUB_RUN_ATTEMPT']=config['run'].split('-')[1]
    with (private.parent/'.family-b04-drive-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        d = Drive()
        mode=sys.argv[1]
        if mode=='init': initialize(d,config['run']);result={'state':'READY'}
        elif mode=='cleanup': result=cleanup(d,config['run'])
        elif mode=='call':
            body=json.loads(sys.stdin.read(8193))
            # Controlled crash only for this disposable acceptance-test request.
            result=apply(d,config['run'],body,crash=body.get('request_id')=='crash-after-upload')
        else: raise RuntimeError('unknown_operation')
        print(json.dumps(result))

if __name__=='__main__':
    try: main()
    except Exception:
        print('{"error":"WRITER_RETRY_REQUIRED"}')
        raise SystemExit(1)
