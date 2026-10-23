"""Synthetic identities only; run core through the actual B06 coordinator."""
import concurrent.futures
import dataclasses
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_headers import SCHEMA, VerifiedPrincipal
from test_resource_io import Disk, manager as business_manager, add
a = importlib.import_module('帳號管理')

@pytest.fixture
def env(tmp_path):
    now = [1000]
    clock = lambda: now[0]
    backend = Disk(tmp_path)
    backend._save('synthetic_accounts', a.create_database([
        dict(user_id=user, password='initial-' + user, role=role, credential_until=2000)
        for user, role in [('mou', 'member'), ('Arthur', 'member'), ('coach', 'manager')]]))
    h = dict(schema=SCHEMA, resource_key='accounts', binding='BOUND', file_id='synthetic_accounts',
             policy_ref='accounts', state='Close', readers=[], updater=None)
    def make(key=b'k' * 32):
        store = a.B06AccountStore({'accounts': h}, {'accounts': {'read': ['service:account-manager'],
             'update': ['service:account-manager']}}, backend, tmp_path/'locks', clock=clock)
        return a.AccountManager(store, key, clock)
    return make(), make, now, backend, tmp_path

def login(m, user='mou', password=None, scope='family-connection', **kw):
    return m.login(user, password or 'secret-' + user, scope, kw.pop('request_id', uuid.uuid4().hex), **kw)

def activate(m, user='mou'):
    first = login(m, user, 'initial-' + user)
    m.change_password(first['token'], 'family-connection', 'initial-' + user, 'secret-' + user, uuid.uuid4().hex)
    return login(m, user)

def test_initial_change_and_private_receipts(env):
    m, _, _, d, root = env
    first = login(m, password='initial-mou')
    assert first['must_change']
    with pytest.raises(PermissionError, match='CHANGE_REQUIRED'):
        m.authenticate(first['token'], 'family-connection')
    m.change_password(first['token'], 'family-connection', 'initial-mou', 'secret-mou', 'change')
    with pytest.raises(PermissionError): m.authenticate(first['token'], 'family-connection')
    active = login(m)
    assert m.authenticate(active['token'], 'family-connection').subject == 'account:mou'
    with sqlite3.connect(root/'synthetic_accounts') as db:
        receipts = str(db.execute('SELECT * FROM _family_io_receipts').fetchall())
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    for value in ['initial-mou', 'secret-mou', a.shift_password('secret-mou'), active['token']]:
        assert value not in receipts
    assert active['token'].encode() not in d.read('synthetic_accounts')

def test_fixed_expiry_and_fresh_worker_resume(env):
    m, make, now, _, _ = env
    token = activate(m)['token']
    before = m.authenticate(token, 'family-connection')
    now[0] += 14000
    assert make().authenticate(token, 'family-connection') == before
    now[0] = before.expires_at - 1
    assert m.session_guard(before)
    now[0] += 1
    assert not m.session_guard(before)

def test_independent_logins_and_switch_account(env):
    m, _, _, _, _ = env
    one = activate(m); activate(m, 'Arthur')
    two = login(m)
    new = login(m, 'Arthur', replace_token=one['token'])
    with pytest.raises(PermissionError): m.authenticate(one['token'], 'family-connection')
    assert m.authenticate(two['token'], 'family-connection').subject == 'account:mou'
    assert m.authenticate(new['token'], 'family-connection').subject == 'account:Arthur'

def test_invalid_switch_does_not_revoke(env):
    m, _, _, _, _ = env; one = activate(m)
    with pytest.raises(PermissionError): login(m, 'Arthur', 'wrong', replace_token=one['token'])
    assert m.authenticate(one['token'], 'family-connection')

def test_revocation_all_sessions_on_password_change(env):
    m, _, _, _, _ = env; one = activate(m); two = login(m)
    m.change_password(one['token'], 'family-connection', 'secret-mou', 'new-mou', 'change2')
    for token in (one['token'], two['token']):
        with pytest.raises(PermissionError): m.authenticate(token, 'family-connection')
    with pytest.raises(PermissionError): login(m)
    assert login(m, password='new-mou')

def test_login_retry_lost_ack_and_no_resurrection(env):
    m, make, _, d, _ = env; activate(m)
    d.fail = 'after-upload'
    with pytest.raises(OSError): login(m, request_id='retry')
    d.fail = None
    token = login(make(), request_id='retry')['token']
    assert login(make(), request_id='retry')['token'] == token
    m.logout(token, 'family-connection', 'logout')
    with pytest.raises(PermissionError): login(m, request_id='retry')

def test_request_collision(env):
    m, _, _, _, _ = env; activate(m)
    login(m, request_id='same')
    with pytest.raises(ValueError, match='COLLISION'): login(m, password='different', request_id='same')

def test_login_throttling_persisted_on_failed_login(env):
    m, make, now, _, _ = env; activate(m)
    for i in range(5):
        with pytest.raises(PermissionError): login(m, password='wrong')
    with pytest.raises(PermissionError): login(make())
    now[0] += 60
    assert login(make())

def test_password_change_throttle(env):
    m, _, now, _, _ = env; token = activate(m)['token']
    for i in range(5):
        with pytest.raises(PermissionError):
            m.change_password(token, 'family-connection', 'wrong', 'replacement', str(i))
    with pytest.raises(PermissionError):
        m.change_password(token, 'family-connection', 'secret-mou', 'replacement', 'blocked')
    now[0] += 60
    assert m.change_password(token, 'family-connection', 'secret-mou', 'replacement', 'unblocked')

@pytest.mark.parametrize('operation', ['create', 'disable', 'enable', 'reset'])
def test_member_cannot_manage_accounts(env, operation):
    m, _, _, _, _ = env; token = activate(m)['token']
    with pytest.raises(PermissionError, match='MANAGER_REQUIRED'):
        m.manage(token, 'family-connection', 'admin', operation, 'Arthur', password='activation', until=1500)

def test_manager_reset_disable_enable_and_last_manager(env):
    m, _, _, _, _ = env
    user = activate(m); manager = activate(m, 'coach')
    args = manager['token'], 'family-connection'
    m.manage(*args, 'reset', 'reset', 'mou', password='reset-once', until=1500)
    with pytest.raises(PermissionError): m.authenticate(user['token'], 'family-connection')
    assert login(m, password='reset-once')['must_change']
    m.manage(*args, 'disable', 'disable', 'mou')
    with pytest.raises(PermissionError): login(m, password='reset-once')
    m.manage(*args, 'enable', 'enable', 'mou')
    assert login(m, password='reset-once')
    with pytest.raises(ValueError, match='LAST_MANAGER'): m.manage(*args, 'last', 'disable', 'coach')

def test_manager_create_and_activation_expiry(env):
    m, _, now, _, _ = env; manager = activate(m, 'coach')
    m.manage(manager['token'], 'family-connection', 'new', 'create', 'new-user', password='activate', until=1500)
    assert login(m, 'new-user', 'activate')['must_change']
    now[0] = 1500
    with pytest.raises(PermissionError): login(m, 'new-user', 'activate')

def test_forged_principal_scope_and_key_rotation(env):
    m, make, _, _, _ = env; token = activate(m)['token']
    p = m.authenticate(token, 'family-connection')
    assert token not in repr(p)
    assert not m.session_guard({'subject': 'account:mou'})
    assert not m.session_guard(VerifiedPrincipal('account:mou', p.expires_at))
    assert not m.session_guard(dataclasses.replace(p, subject='account:Arthur'))
    assert not m.session_guard(dataclasses.replace(p, expires_at=p.expires_at+1))
    with pytest.raises(PermissionError): m.authenticate(token, 'other-connection')
    with pytest.raises(PermissionError): make(b'z'*32).authenticate(token, 'family-connection')

def test_parallel_login_independent_sessions(env):
    m, make, _, _, _ = env; activate(m)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: login(make()), range(4)))
    assert len({x['token'] for x in results}) == 4
    for item in results: assert m.authenticate(item['token'], 'family-connection')

def test_b06_business_write_rejects_logout_during_backup(env):
    m, _, now, d, root = env; token = activate(m)['token']
    p = m.authenticate(token, 'family-connection')
    with sqlite3.connect(root/'synthetic_database') as db:
        db.execute('create table counter(n integer)'); db.execute('insert into counter values(0)')
    business = business_manager(root, d, clock=lambda: now[0], guard=m.session_guard)
    snap = business.snapshot('family.mou', p)
    def revoke():
        d.hook = None  # avoid recursively triggering the test hook for account backup
        m.logout(token, 'family-connection', 'logout-before-write')
    d.hook = revoke
    with pytest.raises(PermissionError, match='REVOKED'):
        business.update('family.mou', p, 'business-write', snap['epoch'], 'add', {'delta': 1})
    assert d.read('synthetic_database') == snap['data']

def test_other_family_cannot_read_business_database(env):
    m, _, now, d, root = env; token = activate(m, 'Arthur')['token']
    business = business_manager(root, d, clock=lambda: now[0], guard=m.session_guard)
    with pytest.raises(PermissionError, match='ACCESS_DENIED'):
        business.snapshot('family.mou', m.authenticate(token, 'family-connection'))

def test_reversible_codec_explicit_and_no_default_accounts():
    assert a.shift_password('abcdabcd') == 'bdfhbdfh'
    image = a.create_database([])
    assert image.startswith(b'SQLite format 3')
