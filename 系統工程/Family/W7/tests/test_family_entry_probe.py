"""Real HTTP connections + process restart; only generated synthetic identities."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'probes/family_entry_probe.py'
spec = importlib.util.spec_from_file_location('entry_probe', SOURCE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def identities():
    keys = {k: secrets.token_urlsafe(32) for k in ('chatA', 'actionA', 'chatB')}
    principals = {hashlib.sha256(v.encode()).hexdigest():
                  {'account': 'synthetic-B' if k == 'chatB' else 'synthetic-A',
                   'kind': 'action' if k == 'actionA' else 'chat'} for k, v in keys.items()}
    return keys, principals


class Running:
    def __init__(self, state, principals):
        self.state, self.principals = state, principals
        self.start()

    def start(self):
        env = dict(os.environ, FAMILY_PROBE_PRINCIPALS_JSON=json.dumps(self.principals))
        self.proc = subprocess.Popen([sys.executable, str(SOURCE), '--state', str(self.state)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        line = self.proc.stdout.readline()
        assert line, self.proc.stderr.read()
        self.url = 'http://127.0.0.1:' + str(json.loads(line)['port'])

    def stop(self):
        self.proc.kill()
        self.proc.wait(timeout=5)
        self.proc.stdout.close()
        self.proc.stderr.close()

    def call(self, key, route, body=None, raw=None):
        data = raw if raw is not None else json.dumps({} if body is None else body).encode()
        req = Request(self.url + route, data=data,
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=20) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            with e:
                return e.code, json.load(e)


@pytest.fixture
def live(tmp_path, identities):
    keys, principals = identities
    server = Running(tmp_path / 'probe.db', principals)
    try:
        yield server, keys
    finally:
        server.stop()


def test_http_cross_connection_restart_and_action_queue(live):
    s, k = live
    assert s.call(k['chatA'], '/read')[0] == 401
    session = s.call(k['chatA'], '/login')[1]['result']
    assert s.call(k['chatA'], '/resume')[1]['result'] == session
    assert s.call(k['actionA'], '/submit', {'request_id': 'action-1', 'delta': 7})[0] == 200
    s.stop()
    s.start()
    assert s.call(k['chatA'], '/resume')[1]['result'] == session
    assert s.call(k['chatA'], '/drain')[1]['result']['value'] == 7
    assert s.call(k['actionA'], '/status', {'request_id': 'action-1'})[1]['result']['state'] == 'DONE'
    s.stop()
    s.start()
    assert s.call(k['actionA'], '/submit', {'request_id': 'action-1', 'delta': 7})[1]['result']['state'] == 'DONE'
    assert s.call(k['chatA'], '/drain')[1]['result']['value'] == 7


def test_http_parallel_chat_action_no_lost_updates(live):
    s, k = live
    s.call(k['chatA'], '/login')
    def submit(n):
        return s.call(k['chatA' if n % 2 else 'actionA'], '/submit', {'request_id': str(n), 'delta': 1})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(submit, list(range(20)) * 2))
    assert all(r[0] == 200 for r in results)
    with ThreadPoolExecutor(max_workers=4) as pool:
        drained = list(pool.map(lambda _: s.call(k['actionA'], '/drain'), range(4)))
    assert all(r[1]['result']['value'] == 20 for r in drained)
    assert s.call(k['chatA'], '/read')[1]['result']['pending'] == 0


def test_http_account_isolation_and_input_errors(live):
    s, k = live
    assert s.call('x' * 40, '/login')[0] == 401
    assert s.call(k['actionA'], '/login')[0] == 403
    s.call(k['chatA'], '/login')
    s.call(k['chatB'], '/login')
    assert s.call(k['chatA'], '/submit', {'request_id': 'private', 'delta': 3})[0] == 200
    assert s.call(k['chatB'], '/status', {'request_id': 'private'})[0] == 404
    assert s.call(k['chatB'], '/read')[1]['result']['value'] == 0
    assert s.call(k['chatA'], '/submit', {'request_id': 'private', 'delta': 4})[0] == 409
    assert s.call(k['chatA'], '/read', {'account': 'synthetic-B'})[0] == 400
    assert s.call(k['chatA'], '/read', {'project': 'other'})[0] == 400
    assert s.call(k['chatA'], '/submit', {'request_id': 'bool', 'delta': True})[0] == 400
    assert s.call(k['chatA'], '/unknown')[0] == 404
    assert s.call(k['chatA'], '/read', raw=b'{')[0] == 400
    assert s.call(k['chatA'], '/read', raw=b'x' * 8193)[0] == 413


def test_four_hour_boundary_no_sliding_and_cancel_stale(tmp_path, identities):
    k, principals = identities
    now = [100]
    e = p.Entry(tmp_path / 'probe.db', principals, clock=lambda: now[0])
    def call(route, body=None):
        return e.call('Bearer ' + k['chatA'], route, {} if body is None else body)
    first = call('/login')
    call('/submit', {'request_id': 'old', 'delta': 9})
    now[0] = 14499
    assert call('/login') == first
    assert call('/resume')['expires'] == 14500
    now[0] = 14500
    with pytest.raises(p.Rejected) as expired:
        call('/drain')
    assert expired.value.code == 'LOGIN_REQUIRED'
    second = call('/login')
    assert second['generation'] != first['generation']
    assert call('/drain')['value'] == 0
    assert call('/status', {'request_id': 'old'})['state'] == 'CANCELLED'
    call('/submit', {'request_id': 'new', 'delta': 4})
    call('/logout')
    call('/login')
    assert call('/drain')['value'] == 0


def test_fifo_result_and_rollback(tmp_path, identities):
    keys, principals = identities
    e = p.Entry(tmp_path / 'probe.db', principals)
    def call(route, body=None):
        return e.call('Bearer ' + keys['chatA'], route, body or {})
    call('/login')
    call('/submit', {'request_id': 'one', 'delta': 2})
    call('/submit', {'request_id': 'two', 'delta': 3})
    with sqlite3.connect(e.path) as db:
        db.execute("CREATE TRIGGER fail_second BEFORE UPDATE ON jobs WHEN NEW.request_id='two' BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        call('/drain')
    assert call('/read')['value'] == 0
    assert call('/read')['pending'] == 2
    with sqlite3.connect(e.path) as db:
        db.execute('DROP TRIGGER fail_second')
    assert call('/drain')['value'] == 5
    assert call('/status', {'request_id': 'one'})['result'] == 2
    assert call('/status', {'request_id': 'two'})['result'] == 5


def test_formal_database_guard(tmp_path, identities):
    path = tmp_path / 'unrelated.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE customer(value TEXT)')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='NON_PROBE'):
        p.Entry(path, identities[1])
    assert path.read_bytes() == before


def test_config_requires_synthetic_accounts(tmp_path):
    with pytest.raises(ValueError, match='SYNTHETIC'):
        p.Entry(tmp_path / 'probe.db', {'a' * 64: {'account': 'real-family', 'kind': 'chat'}})


def test_killed_writer_transaction_recovers(live):
    s, k = live
    s.call(k['chatA'], '/login')
    s.call(k['chatA'], '/submit', {'request_id': 'interrupted', 'delta': 6})
    code = """
import sqlite3,sys,time
db=sqlite3.connect(sys.argv[1]);db.execute('BEGIN IMMEDIATE')
db.execute("INSERT OR REPLACE INTO counters VALUES('synthetic-A',999)")
db.execute("UPDATE jobs SET state='DONE',result=999")
print('uncommitted',flush=True)
time.sleep(60)
"""
    writer = subprocess.Popen([sys.executable, '-c', code, str(s.state)], stdout=subprocess.PIPE, text=True)
    try:
        assert writer.stdout.readline().strip() == 'uncommitted'
    finally:
        writer.kill()
        writer.wait(timeout=5)
        writer.stdout.close()
    assert s.call(k['chatA'], '/read')[1]['result']['value'] == 0
    assert s.call(k['actionA'], '/drain')[1]['result']['value'] == 6
    assert s.call(k['chatA'], '/drain')[1]['result']['value'] == 6
