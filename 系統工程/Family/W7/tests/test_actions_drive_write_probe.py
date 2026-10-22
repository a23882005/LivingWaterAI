import importlib.util
from pathlib import Path
import sqlite3
import pytest

spec = importlib.util.spec_from_file_location('probe', Path(__file__).parents[1] / 'probes/actions_drive_write_probe.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

@pytest.fixture
def original(tmp_path):
    path = tmp_path / 'source.db'
    with sqlite3.connect(path) as db:
        db.execute('create table source(value integer)')
        db.execute('insert into source values (58)')
    return path.read_bytes()

class Fake:
    def __init__(self, data):
        self.data = data
        self.saved = data
        self.props = {}
        self.writes = 0
        self.parent = p.TEMP_FOLDER
    def meta(self, file_id=p.TEST_ID):
        return {'id': file_id, 'parents': [self.parent if file_id == p.TEST_ID else p.BACKUP_FOLDER], 'appProperties': self.props}
    def read(self, file_id=p.TEST_ID):
        return self.data if file_id == p.TEST_ID else self.saved
    def write(self, data):
        self.writes += 1
        self.data = data
    def journal(self, values):
        self.props = dict(zip(p.KEYS, values))
    def prepare(self, candidate):
        self.journal(['backup-id', p.digest(self.saved), p.digest(candidate)])

@pytest.mark.parametrize('stage', ['prepared', 'uploaded', 'restored'])
def test_recovery_at_each_durable_boundary(original, stage):
    d = Fake(original)
    candidate = p.mutate(original)
    d.prepare(candidate)
    if stage == 'uploaded':
        d.data = candidate
    result = p.recover(d)
    assert result['status'] == 'RESTORED'
    assert d.data == original
    assert d.writes == (1 if stage == 'uploaded' else 0)
    assert p.recover(d)['status'] == 'CLEAN'

@pytest.mark.parametrize('fault', ['external-update', 'corrupt-backup', 'incomplete-journal', 'wrong-parent'])
def test_recovery_fails_closed(original, fault):
    d = Fake(original)
    candidate = p.mutate(original)
    d.prepare(candidate)
    d.data = candidate
    if fault == 'external-update': d.data = b'unrelated-change'
    elif fault == 'corrupt-backup': d.saved = b'corrupt'
    elif fault == 'incomplete-journal': d.props.pop(p.KEYS[1])
    else: d.parent = 'formal-db-folder'
    with pytest.raises(RuntimeError): p.recover(d)
    assert d.writes == 0
    assert d.props

def test_transaction_changes_only_probe_table(original, tmp_path):
    path = tmp_path / 'candidate.db'
    path.write_bytes(p.mutate(original))
    with sqlite3.connect(path) as db:
        assert db.execute('select * from source').fetchall() == [(58,)]
        assert db.execute('select value from b04_oauth_roundtrip_probe').fetchone() == ('synthetic-only',)

@pytest.mark.parametrize('data', [b'not-sqlite', b'SQLite format 3\0broken'])
def test_reject_invalid_database(data):
    with pytest.raises((RuntimeError, sqlite3.DatabaseError)): p.checked(data)
