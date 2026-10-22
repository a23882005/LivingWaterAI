"""Bounded TEMP-only roundtrip; durable recovery journal survives worker exit.

The Actions concurrency group serializes this probe only. This is NOT the
production shared writer or a claim of distributed locking against other apps.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

TEST_ID = '1SDnOCLoHpX-XfJ9v838o84VJmzdmoPzI'
TEMP_FOLDER = '1wJyRyfaMXJN7h4zXTk3RmfK329V6s3OA'
BACKUP_FOLDER = '177jkgL-0q-u64wW0rIRuw8SrfxSy_tmw'
API = 'https://www.googleapis.com/drive/v3/files/'
KEYS = ('b04_backup', 'b04_before', 'b04_after')
LIMIT = 2 * 1024 * 1024

def digest(data):
    return hashlib.sha256(data).hexdigest()

def checked(data):
    if len(data) > LIMIT or not data.startswith(b'SQLite format 3\0'):
        raise RuntimeError('invalid_synthetic_database')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'check.db'
        path.write_bytes(data)
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('pragma integrity_check').fetchall() != [('ok',)] or db.execute('pragma foreign_key_check').fetchall():
                raise RuntimeError('invalid_integrity')
    return data

def mutate(data):
    checked(data)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'candidate.db'
        path.write_bytes(data)
        with sqlite3.connect(path) as db:
            # Existing source tables and their values remain untouched.
            db.execute('CREATE TABLE b04_oauth_roundtrip_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('INSERT INTO b04_oauth_roundtrip_probe VALUES (1, ?)', ('synthetic-only',))
        return checked(path.read_bytes())

class Drive:
    def __init__(self):
        names = ('FAMILY_DRIVE_CLIENT_ID','FAMILY_DRIVE_CLIENT_SECRET','FAMILY_DRIVE_REFRESH_TOKEN')
        body = urllib.parse.urlencode(dict(zip(('client_id','client_secret','refresh_token'), (os.environ[n] for n in names)), grant_type='refresh_token')).encode()
        req = urllib.request.Request('https://oauth2.googleapis.com/token', data=body)
        with urllib.request.urlopen(req, timeout=30) as response:
            self.token = json.load(response)['access_token']

    def call(self, url, method='GET', data=None, raw=False):
        headers = {'Authorization': 'Bearer ' + self.token}
        if data is not None:
            headers['Content-Type'] = 'application/octet-stream' if isinstance(data, bytes) else 'application/json'
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read(LIMIT + 1)
        if len(payload) > LIMIT:
            raise RuntimeError('response_too_large')
        return payload if raw else json.loads(payload)

    def meta(self, file_id=TEST_ID):
        return self.call(API + file_id + '?fields=id,parents,trashed,appProperties')

    def read(self, file_id=TEST_ID):
        return checked(self.call(API + file_id + '?alt=media', raw=True))

    def write(self, data):
        checked(data)
        self.call('https://www.googleapis.com/upload/drive/v3/files/' + TEST_ID + '?uploadType=media', 'PATCH', data)

    def journal(self, values):
        self.call(API + TEST_ID, 'PATCH', {'appProperties': dict(zip(KEYS, values))})

    def backup(self):
        name = 'Family_B04_TEMP_before_' + os.environ.get('GITHUB_RUN_ID', 'manual') + '_' + os.environ.get('GITHUB_RUN_ATTEMPT', '1') + '.db'
        return self.call(API + TEST_ID + '/copy?fields=id', 'POST', {'name': name, 'parents': [BACKUP_FOLDER], 'appProperties': {k: None for k in KEYS}})['id']

def target(drive):
    meta = drive.meta()
    if meta['id'] != TEST_ID or meta.get('trashed') or TEMP_FOLDER not in meta.get('parents', []):
        raise RuntimeError('target_not_approved_temp')
    return meta.get('appProperties', {})

def recover(drive):
    props = target(drive)
    values = [props.get(k) for k in KEYS]
    if not any(values):
        return {'status': 'CLEAN'}
    if not all(values):
        raise RuntimeError('incomplete_journal')
    backup_id, before, after = values
    backup_meta = drive.meta(backup_id)
    if BACKUP_FOLDER not in backup_meta.get('parents', []) or backup_meta.get('trashed'):
        raise RuntimeError('backup_location_changed')
    original = drive.read(backup_id)
    if digest(original) != before:
        raise RuntimeError('backup_digest_mismatch')
    current = drive.read()
    if digest(current) not in (before, after):
        # Never overwrite an unrelated external update.
        raise RuntimeError('external_change_recovery_blocked')
    if current != original:
        drive.write(original)
    if drive.read() != original:
        raise RuntimeError('restore_readback_failed')
    drive.journal([None] * 3)
    if any(target(drive).get(k) for k in KEYS):
        raise RuntimeError('journal_clear_failed')
    return {'status': 'RESTORED', 'backup_id': backup_id, 'sha256': before, 'bytes': len(original)}

def write_then_exit(drive):
    if any(target(drive).get(k) for k in KEYS):
        raise RuntimeError('pending_recovery')
    original = drive.read()
    candidate = mutate(original)
    backup_id = drive.backup()
    if drive.read(backup_id) != original:
        raise RuntimeError('backup_readback_failed')
    if drive.read() != original:
        raise RuntimeError('source_changed_before_journal')
    drive.journal([backup_id, digest(original), digest(candidate)])
    props = target(drive)
    if [props.get(k) for k in KEYS] != [backup_id, digest(original), digest(candidate)]:
        raise RuntimeError('journal_readback_failed')
    if drive.read() != original:
        raise RuntimeError('source_changed_before_write')
    drive.write(candidate)
    if drive.read() != candidate:
        raise RuntimeError('write_readback_failed')
    # Abrupt worker exit: no finally, no local journal reused by recovery.
    os._exit(73)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'verify'
    report = {'schema': 'Family-B04-drive-roundtrip-v1', 'scope': 'FIXED_TEMP_SYNTHETIC_ONLY', 'status': 'FAIL', 'mode': mode}
    try:
        drive = Drive()
        if mode == 'interrupt':
            write_then_exit(drive)
        elif mode == 'recover':
            report['recovery'] = recover(drive)
            report['status'] = 'PASS'
        elif mode == 'verify':
            report['prior_recovery'] = recover(drive)
            original = drive.read()
            worker = subprocess.run([sys.executable, __file__, 'interrupt'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
            report['worker_exit'] = worker.returncode
            # Use a fresh client, no worker memory/files, and durable Drive journal.
            fresh = Drive()
            props = target(fresh)
            changed = fresh.read()
            report['write_readback'] = digest(changed) == props.get('b04_after') and changed != original
            report['recovery'] = recover(fresh)
            report['restored_exact_bytes'] = fresh.read() == original
            if worker.returncode != 73 or not report['write_readback'] or not report['restored_exact_bytes'] or report['recovery']['status'] != 'RESTORED':
                raise RuntimeError('roundtrip_incomplete')
            report['status'] = 'PASS'
        else:
            raise RuntimeError('unknown_mode')
    except Exception as exc:
        # Never serialize request body, exception text, OAuth responses or tokens.
        report['error_type'] = type(exc).__name__
    path = Path('build/family-b04/drive-' + mode + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
