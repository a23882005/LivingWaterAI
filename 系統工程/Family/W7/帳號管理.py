"""B07 account core. Trusted service only; no public enrollment/SQL/file IDs.

The deployment supplies B06 store, a persistent random server key and logical
connection scope. Scope is not a claim to native ChatGPT Project identity.
Passwords use the commander's specified reversible 1/2/3/4 character shift;
this is obfuscation, NOT encryption. Account images/backups stay private.
"""
import hashlib
import hmac
import importlib
import json
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from resource_headers import VerifiedPrincipal

TTL = 4 * 60 * 60
NAME = re.compile(r'[A-Za-z0-9_.-]{1,80}\Z')
SCHEMA = '''
CREATE TABLE account (
 user_id TEXT PRIMARY KEY, password_shift TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('member','manager')),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 must_change INTEGER NOT NULL CHECK(must_change IN (0,1)),
 credential_until INTEGER, generation INTEGER NOT NULL DEFAULT 1,
 failures INTEGER NOT NULL DEFAULT 0, blocked_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE login_session (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES account(user_id),
 scope TEXT NOT NULL, issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 generation INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
 CHECK(expires_at = issued_at + 14400), CHECK(revoked IN (0,1))
);
CREATE INDEX session_user ON login_session(user_id);
PRAGMA user_version=1;
'''

def _password(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError('INVALID_PASSWORD')
    if any(ord(c) < 32 or 0xD7FC <= ord(c) <= 0xDFFF or ord(c) > 0x10FFFB for c in value):
        raise ValueError('INVALID_PASSWORD')
    return value

def shift_password(value):
    return ''.join(chr(ord(c) + 1 + i % 4) for i, c in enumerate(_password(value)))

def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()

def _scope(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError('INVALID_SCOPE')
    return value

def _name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('INVALID_ACCOUNT')
    return value

def _insert(db, user, password, role, until):
    _name(user)
    if role not in ('member', 'manager') or type(until) is not int:
        raise ValueError('INVALID_ACCOUNT_CONFIG')
    db.execute('INSERT INTO account(user_id,password_shift,role,enabled,must_change,credential_until) '
               'VALUES(?,?,?,1,1,?)', (user, shift_password(password), role, until))

def create_database(seeds):
    """Offline bootstrap ONLY. Seeds from secure deployment, never HTTP payload.

    Empty images are permitted for staging. No built-in user/password/admin.
    Each seed: user_id, password, role, credential_until (short activation TTL).
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'accounts.db'
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA)
            for seed in seeds:
                _insert(db, seed['user_id'], seed['password'], seed['role'], seed['credential_until'])
        return path.read_bytes()

class B06AccountStore:
    """No account->business lock nesting. Bootstrap principal is never exposed.

    A separate Coordinator per call avoids cross-request handler mutation.
    Business session_guard may read this store while holding a business lock;
    account handlers never acquire business locks. Driver errors fail closed.
    """
    def __init__(self, headers, policies, backend, lock_dir, clock=time.time):
        self.args = (headers, policies, backend, lock_dir)
        self.clock = clock

    def _coordinator(self, handler=None):
        principal = VerifiedPrincipal('service:account-manager', int(self.clock()) + 300)
        coordinator = importlib.import_module('資料存取管理').Coordinator(
            *self.args, {'account': handler} if handler else {}, clock=self.clock,
            session_guard=lambda p: p is principal)
        return coordinator, principal

    def read(self, reader):
        c, p = self._coordinator()
        image = c.snapshot('accounts', p)['data']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.db'
            path.write_bytes(image)
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                db.row_factory = sqlite3.Row
                return reader(db)

    def mutate(self, request_id, fingerprint, handler):
        def dispatch(db, payload):
            db.row_factory = sqlite3.Row
            return handler(db)
        c, p = self._coordinator(dispatch)
        epoch = c.snapshot('accounts', p)['epoch']
        return c.update('accounts', p, request_id, epoch, 'account',
                        {'fingerprint': fingerprint})['result']

@dataclass(frozen=True)
class SessionPrincipal(VerifiedPrincipal):
    session_id: str
    scope: str
    proof: str = field(repr=False, compare=False)

class AccountManager:
    def __init__(self, store, server_key, clock=time.time):
        if not isinstance(server_key, bytes) or len(server_key) < 32:
            raise ValueError('PERSISTENT_RANDOM_KEY_REQUIRED')
        self.store, self.key, self.clock = store, server_key, clock

    def _mac(self, purpose, value):
        text = json.dumps([purpose, value], ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        return hmac.new(self.key, text.encode(), hashlib.sha256).hexdigest()

    def _write(self, request_id, arguments, handler):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('INVALID_REQUEST_ID')
        # Receipt stores keyed fingerprint, never plaintext/shift/token/password.
        result = self.store.mutate(request_id, self._mac('request', arguments), handler)
        if 'error' in result:
            raise PermissionError(result['error'])
        return result

    def _session(self, db, token, scope, allow_change=False):
        if not isinstance(token, str) or len(token) != 64:
            raise PermissionError('INVALID_SESSION')
        now = int(self.clock())
        row = db.execute('SELECT s.*, a.role, a.enabled, a.must_change, '
                         'a.generation AS current_generation, a.credential_until '
                         'FROM login_session s JOIN account a USING(user_id) WHERE token_hash=?',
                         (self._mac('stored-token', token),)).fetchone()
        if (not row or row['scope'] != scope or row['revoked'] or not row['enabled']
            or row['generation'] != row['current_generation']
            or not row['issued_at'] <= now < row['expires_at']
            or (row['credential_until'] is not None and now >= row['credential_until'])):
            raise PermissionError('INVALID_SESSION')
        if row['must_change'] and not allow_change:
            raise PermissionError('PASSWORD_CHANGE_REQUIRED')
        return row

    def login(self, user, password, scope, request_id, replace_token=None):
        _name(user); _password(password); _scope(scope)
        # Deterministic only for retry of same private request receipt, with a
        # secret server key. Returned bearer is never persisted in receipts.
        token = self._mac('session-token', [request_id, user, scope])
        def run(db):
            now = int(self.clock())
            row = db.execute('SELECT * FROM account WHERE user_id=?', (user,)).fetchone()
            if not row or not row['enabled'] or now < row['blocked_until']:
                return {'error': 'LOGIN_REJECTED'}
            if row['credential_until'] is not None and now >= row['credential_until']:
                return {'error': 'LOGIN_REJECTED'}
            if not hmac.compare_digest(_hash(shift_password(password)), _hash(row['password_shift'])):
                count = row['failures'] + 1
                db.execute('UPDATE account SET failures=?,blocked_until=? WHERE user_id=?',
                           (count % 5, now + 60 if count >= 5 else 0, user))
                return {'error': 'LOGIN_REJECTED'}
            if replace_token is not None:
                old = self._session(db, replace_token, scope, allow_change=True)
                db.execute('UPDATE login_session SET revoked=1 WHERE token_hash=?', (old['token_hash'],))
            db.execute('UPDATE account SET failures=0,blocked_until=0 WHERE user_id=?', (user,))
            db.execute('INSERT INTO login_session VALUES(?,?,?,?,?,?,0)',
                       (self._mac('stored-token', token), user, scope, now, now + TTL, row['generation']))
            return {'expires_at': now + TTL, 'must_change': bool(row['must_change'])}
        result = self._write(request_id, ['login', user, password, scope, replace_token], run)
        # A replay after logout/password change/expiry must not resurrect login.
        self.store.read(lambda db: self._session(db, token, scope, allow_change=True))
        return dict(result, token=token)

    def authenticate(self, token, scope):
        _scope(scope)
        row = self.store.read(lambda db: dict(self._session(db, token, scope)))
        return SessionPrincipal('account:' + row['user_id'], row['expires_at'], row['token_hash'], scope, token)

    def session_guard(self, principal):
        if not isinstance(principal, SessionPrincipal):
            return False
        try:
            return self.authenticate(principal.proof, principal.scope) == principal
        except PermissionError:
            return False

    def logout(self, token, scope, request_id):
        def run(db):
            row = self._session(db, token, scope, allow_change=True)
            db.execute('UPDATE login_session SET revoked=1 WHERE token_hash=?', (row['token_hash'],))
            return {'logged_out': True}
        return self._write(request_id, ['logout', token, scope], run)

    def change_password(self, token, scope, current_password, new_password, request_id):
        _password(current_password); _password(new_password)
        if current_password == new_password:
            raise ValueError('NEW_PASSWORD_REQUIRED')
        def run(db):
            row = self._session(db, token, scope, allow_change=True)
            account = db.execute('SELECT * FROM account WHERE user_id=?', (row['user_id'],)).fetchone()
            now = int(self.clock())
            if now < account['blocked_until']:
                return {'error': 'PASSWORD_REJECTED'}
            if not hmac.compare_digest(_hash(shift_password(current_password)), _hash(account['password_shift'])):
                count = account['failures'] + 1
                db.execute('UPDATE account SET failures=?,blocked_until=? WHERE user_id=?',
                           (count % 5, now + 60 if count >= 5 else 0, row['user_id']))
                return {'error': 'PASSWORD_REJECTED'}
            db.execute('UPDATE account SET password_shift=?,must_change=0,credential_until=NULL,'
                       'generation=generation+1,failures=0,blocked_until=0 WHERE user_id=?',
                       (shift_password(new_password), row['user_id']))
            db.execute('UPDATE login_session SET revoked=1 WHERE user_id=?', (row['user_id'],))
            return {'password_changed': True, 'login_required': True}
        return self._write(request_id, ['change', token, scope, current_password, new_password], run)

    def manage(self, token, scope, request_id, operation, user, password=None, role='member', until=None):
        _name(user)
        if operation not in ('create', 'disable', 'enable', 'reset'):
            raise ValueError('UNKNOWN_MANAGEMENT_OPERATION')
        if operation in ('create', 'reset'):
            _password(password)
            if type(until) is not int or not int(self.clock()) < until <= int(self.clock()) + 86400:
                raise ValueError('SHORT_ACTIVATION_REQUIRED')
        def run(db):
            actor = self._session(db, token, scope)
            if actor['role'] != 'manager':
                raise PermissionError('MANAGER_REQUIRED')
            if operation == 'create':
                _insert(db, user, password, role, until)
            else:
                target = db.execute('SELECT * FROM account WHERE user_id=?', (user,)).fetchone()
                if not target:
                    raise ValueError('UNKNOWN_ACCOUNT')
                if target['role'] == 'manager' and target['enabled'] and operation == 'disable':
                    if db.execute("SELECT count(*) FROM account WHERE role='manager' AND enabled=1").fetchone()[0] <= 1:
                        raise ValueError('LAST_MANAGER')
                if operation == 'disable':
                    db.execute('UPDATE account SET enabled=0,generation=generation+1 WHERE user_id=?', (user,))
                elif operation == 'enable':
                    db.execute('UPDATE account SET enabled=1,generation=generation+1 WHERE user_id=?', (user,))
                else:
                    db.execute('UPDATE account SET password_shift=?,must_change=1,credential_until=?,'
                               'generation=generation+1,failures=0,blocked_until=0 WHERE user_id=?',
                               (shift_password(password), until, user))
                db.execute('UPDATE login_session SET revoked=1 WHERE user_id=?', (user,))
            return {'operation': operation, 'user_id': user}
        return self._write(request_id, ['manage', token, scope, operation, user, password, role, until], run)
