"""Read immutable captured history after its independently recorded upload.

This grants archival replay access only. It does not certify price adjustments,
the provider's earliest publication time, or permission for investment decisions.
The trusted receipt SHA belongs to release configuration, never tool arguments.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from replay import ReplayError, instant


def read_capture(archive, receipt_path, *, trusted_receipt_sha256, cutoff):
    raw_receipt = Path(receipt_path).read_bytes()
    if hashlib.sha256(raw_receipt).hexdigest() != trusted_receipt_sha256:
        raise ReplayError('CAPTURE_RECEIPT_CHANGED')
    receipt = json.loads(raw_receipt)
    if receipt.get('schema') != 'Family.BR.GitHubArtifactReceipt.v1':
        raise ReplayError('CAPTURE_RECEIPT_SCHEMA')
    artifact, job = receipt['artifact'], receipt['job']
    if artifact['workflow_run']['id'] != job['run_id']:
        raise ReplayError('CAPTURE_RUN_MISMATCH')
    if job['status'] != 'completed' or job['conclusion'] != 'success':
        raise ReplayError('CAPTURE_JOB_NOT_SUCCESSFUL')
    uploads = [s for s in job['steps'] if s['name'] == 'Run actions/upload-artifact@v4']
    if len(uploads) != 1 or uploads[0]['conclusion'] != 'success':
        raise ReplayError('CAPTURE_UPLOAD_UNPROVEN')
    upper = instant(receipt['available_at_upper_bound'])
    if not (instant(job['started_at']) <= instant(artifact['created_at'])
            <= instant(uploads[0]['completed_at']) <= instant(job['completed_at']) == upper):
        raise ReplayError('CAPTURE_TIME_ORDER')
    if instant(artifact['updated_at']) > upper:
        raise ReplayError('CAPTURE_REVISION_AFTER_BOUNDARY')
    if instant(cutoff) < upper:
        raise ReplayError('CAPTURE_NOT_AVAILABLE_AT_CUTOFF')
    raw = Path(archive).read_bytes()
    if len(raw) != artifact['size_in_bytes'] or 'sha256:' + hashlib.sha256(raw).hexdigest() != artifact['digest']:
        raise ReplayError('CAPTURE_ARCHIVE_CHANGED')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.namelist().count(receipt['member']) != 1 or z.testzip() is not None:
            raise ReplayError('CAPTURE_MEMBER_OR_CRC')
        member = z.read(receipt['member'])
    if hashlib.sha256(member).hexdigest() != receipt['member_sha256']:
        raise ReplayError('CAPTURE_MEMBER_CHANGED')
    rows = list(csv.DictReader(io.StringIO(member.decode('utf-8-sig'))))
    dates = [r['Date'] for r in rows]
    if not dates or dates != sorted(set(dates)):
        raise ReplayError('CAPTURE_ROW_ORDER')
    if dates[-1] > upper.date().isoformat():
        raise ReplayError('CAPTURE_FUTURE_OBSERVATION')
    return {'schema': 'Family.BR.CapturedHistory.v1', 'rows': rows,
            'available_at_upper_bound': receipt['available_at_upper_bound'],
            'artifact_id': artifact['id'], 'run_id': job['run_id'],
            'source_sha256': receipt['member_sha256'],
            'receipt_sha256': trusted_receipt_sha256,
            'availability_verified_for_capture_replay': True,
            'availability_scope': 'SNAPSHOT_AFTER_CAPTURE_ONLY',
            'earliest_per_bar_publication_verified': False,
            'decision_eligible': False, 'trade_authorization': 'NONE'}
