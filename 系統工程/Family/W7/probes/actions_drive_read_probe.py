"""B04: read exactly the approved TEMP synthetic DB using service OAuth.

Credential names below are the explicit Family integration contract, not a
claim about every credential that might exist elsewhere. Never log tokens.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request

TEST_FILE_ID = '1SDnOCLoHpX-XfJ9v838o84VJmzdmoPzI'
NAMES = ('FAMILY_DRIVE_CLIENT_ID', 'FAMILY_DRIVE_CLIENT_SECRET', 'FAMILY_DRIVE_REFRESH_TOKEN')


def run():
    present = {name: bool(os.environ.get(name)) for name in NAMES}
    result = {'schema': 'Family-B04-actions-drive-probe-v1', 'scope': 'TEMP_SYNTHETIC_READ_ONLY',
              'credential_contract': present, 'status': 'AWAITING_FAMILY_DRIVE_CONNECTION'}
    if not all(present.values()):
        return result
    body = urllib.parse.urlencode({
        'client_id': os.environ[NAMES[0]], 'client_secret': os.environ[NAMES[1]],
        'refresh_token': os.environ[NAMES[2]], 'grant_type': 'refresh_token'}).encode()
    stage = 'oauth_refresh'
    try:
        request = urllib.request.Request('https://oauth2.googleapis.com/token', data=body)
        with urllib.request.urlopen(request, timeout=30) as response:
            token = json.load(response)['access_token']
        stage = 'synthetic_drive_read'
        request = urllib.request.Request(
            'https://www.googleapis.com/drive/v3/files/' + TEST_FILE_ID + '?alt=media',
            headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024 or not payload.startswith(b'SQLite format 3\0'):
            result.update(status='UNEXPECTED_SYNTHETIC_RESOURCE')
            return result
        stage = 'sqlite_integrity'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.db'
            path.write_bytes(payload)
            db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
            try:
                integrity = db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
                foreign_keys = not db.execute('PRAGMA foreign_key_check').fetchall()
            finally:
                db.close()
        result.update(status='PASS' if integrity and foreign_keys else 'INTEGRITY_FAILED',
                      bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                      integrity_ok=integrity, foreign_keys_ok=foreign_keys)
    except urllib.error.HTTPError as exc:
        result.update(status='CONNECTION_FAILED', stage=stage, http_status=exc.code)
    except Exception:
        # Do not serialize exceptions containing request bodies or credentials.
        result.update(status='CONNECTION_FAILED', stage=stage)
    return result


if __name__ == '__main__':
    output = Path('build/family-b04/drive-read.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = run()
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    if report['status'] not in ('PASS', 'AWAITING_FAMILY_DRIVE_CONNECTION'):
        raise SystemExit(1)
