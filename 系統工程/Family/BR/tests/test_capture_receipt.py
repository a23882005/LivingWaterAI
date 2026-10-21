import hashlib
import json
from pathlib import Path
import sys
import zipfile
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from capture_receipt import read_capture
from replay import ReplayError


def prepared(tmp_path):
    raw = b'Date,Close\n2020-01-02,100\n'
    archive = tmp_path / 'capture.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('TEST.csv', raw)
    receipt = {'schema': 'Family.BR.GitHubArtifactReceipt.v1',
        'artifact': {'id': 1, 'workflow_run': {'id': 2}, 'size_in_bytes': archive.stat().st_size,
                     'digest': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
                     'created_at': '2020-01-03T00:00:01Z', 'updated_at': '2020-01-03T00:00:02Z'},
        'job': {'run_id': 2, 'status': 'completed', 'conclusion': 'success',
                'started_at': '2020-01-03T00:00:00Z', 'completed_at': '2020-01-03T00:00:03Z',
                'steps': [{'name': 'Run actions/upload-artifact@v4', 'conclusion': 'success',
                           'completed_at': '2020-01-03T00:00:02Z'}]},
        'member': 'TEST.csv', 'member_sha256': hashlib.sha256(raw).hexdigest(),
        'available_at_upper_bound': '2020-01-03T00:00:03Z'}
    path = tmp_path / 'receipt.json'; path.write_text(json.dumps(receipt))
    return archive, path, receipt


def read(a, p, **kwargs):
    args = {'trusted_receipt_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'cutoff': '2020-01-03T00:00:03Z'}
    args.update(kwargs)
    return read_capture(a, p, **args)


def test_true_capture_boundary_and_purpose(tmp_path):
    a, p, _ = prepared(tmp_path)
    out = read(a, p)
    assert out['rows'][0]['Close'] == '100'
    assert out['availability_verified_for_capture_replay'] is True
    assert not out['earliest_per_bar_publication_verified'] and not out['decision_eligible']
    with pytest.raises(ReplayError, match='NOT_AVAILABLE'):
        read(a, p, cutoff='2020-01-03T00:00:02.999999Z')
    assert read(a, p, cutoff='2020-01-03T08:00:03+08:00') == out


@pytest.mark.parametrize('fault,code', [('run','RUN_MISMATCH'), ('job','JOB_NOT_SUCCESSFUL'),
    ('upload','UPLOAD_UNPROVEN'), ('boundary','TIME_ORDER'), ('revision','REVISION_AFTER'),
    ('member','MEMBER_CHANGED')])
def test_inconsistent_receipt_rejected(tmp_path, fault, code):
    a, p, r = prepared(tmp_path)
    if fault == 'run': r['job']['run_id'] = 99
    elif fault == 'job': r['job']['conclusion'] = 'failure'
    elif fault == 'upload': r['job']['steps'] = []
    elif fault == 'boundary': r['available_at_upper_bound'] = '2020-01-03T00:00:01Z'
    elif fault == 'revision': r['artifact']['updated_at'] = '2020-01-04T00:00:00Z'
    elif fault == 'member': r['member_sha256'] = '0' * 64
    p.write_text(json.dumps(r))
    with pytest.raises(ReplayError, match=code): read(a, p)


def test_receipt_and_archive_tampering(tmp_path):
    a, p, _ = prepared(tmp_path)
    pin = hashlib.sha256(p.read_bytes()).hexdigest()
    p.write_bytes(p.read_bytes() + b' ')
    with pytest.raises(ReplayError, match='RECEIPT_CHANGED'):
        read(a, p, trusted_receipt_sha256=pin)
    a.write_bytes(a.read_bytes() + b' ')
    with pytest.raises(ReplayError, match='ARCHIVE_CHANGED'): read(a, p)
