"""Verify a remotely retrieved, commit-pinned archive against W5 intake.

This verifies artifact identity only. Git timestamps are claims, not proof
of provider publication time; no eligibility flags are promoted here.
"""
from pathlib import Path
import csv
import hashlib
import io
import json
import sys


def verify(archive, intake):
    archive, intake = Path(archive), Path(intake)
    binding = json.loads((archive / 'remote_binding.json').read_text())
    verified = {}
    for entry in binding['files']:
        name = entry['path']
        if name not in ('VOO.csv', 'manifest.json'):
            raise ValueError('UNEXPECTED_ARCHIVE_FILE')
        raw = (archive / name).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if blob != entry['git_blob_sha1']:
            raise ValueError('REMOTE_GIT_BLOB_MISMATCH')
        verified[name] = {'bytes': len(raw), 'git_blob_sha1': blob,
                          'sha256': hashlib.sha256(raw).hexdigest()}
    raw = (archive / 'VOO.csv').read_bytes()
    if raw != (intake / 'VOO.csv').read_bytes():
        raise ValueError('W5_ARCHIVE_BYTES_DIFFER')
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    manifest = json.loads((archive / 'manifest.json').read_text())
    item = manifest['items']['VOO']
    if item['status'] != 'OK' or item['rows'] != len(rows) or item['latest_observation'] != rows[-1]['Date']:
        raise ValueError('REMOTE_MANIFEST_MISMATCH')
    receipt = json.loads((intake / 'VOO.csv.result.json').read_text())
    if receipt['source_history'] != rows:
        raise ValueError('W5_RECEIPT_ROWS_DIFFER')
    return {'status': 'PASS', 'scope': 'REMOTE_COMMIT_TO_W5_ARTIFACT_IDENTITY',
            'commit': binding['commit'], 'files': verified, 'rows': len(rows),
            'first_observation': rows[0]['Date'], 'last_observation': rows[-1]['Date'],
            'capture_completion_claim': receipt['source_metadata']['artifact_written_at'],
            'commit_time_claim': binding['commit_time_claim'],
            'publication_time_verified': False, 'decision_eligible': False,
            'historical_ready': False, 'trade_authorization': 'NONE'}


if __name__ == '__main__':
    result = verify(sys.argv[1], sys.argv[2])
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text)
    print(text)
