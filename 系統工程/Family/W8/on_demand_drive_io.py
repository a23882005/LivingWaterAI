"""W8 on-demand connector bridge. No credentials, network calls or private IDs.

The ChatGPT executor calls Drive tools between prepare/authorize/verify steps.
A READY request is not a persistence receipt. Same-resource writes must be
serialized by the caller; source rechecking is not a distributed atomic lock.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import sqlite3

ACCOUNTS = frozenset(('MOU', 'JO', 'AR', 'LI'))
LIMIT = 64 * 1024 * 1024


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Binding:
    account: str
    client_id: str
    file_id: str
    family_alias: str

    def __post_init__(self):
        if self.account not in ACCOUNTS or not self.client_id.startswith('fam_') or len(self.client_id) != 36:
            raise ValueError('INVALID_FAMILY_BINDING')
        if not self.file_id or not self.family_alias:
            raise ValueError('INCOMPLETE_FAMILY_BINDING')


def inspect(path, binding):
    p = Path(path).resolve(strict=True)
    if not p.is_file() or p.stat().st_size > LIMIT:
        raise ValueError('INVALID_DATABASE_FILE')
    # Never upload only the main DB while committed data remains in WAL.
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(p) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError('UNSEALED_SQLITE_SIDECAR')
    with p.open('rb') as stream:
        header = stream.read(16)
    if header != b'SQLite format 3\0':
        raise ValueError('INVALID_SQLITE_HEADER')
    with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('INTEGRITY_FAILED')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('FOREIGN_KEYS_FAILED')
        rows = db.execute('SELECT client_id,family_alias FROM family_member_identity').fetchall()
        if rows != [(binding.client_id, binding.family_alias)]:
            raise PermissionError('FAMILY_IDENTITY_MISMATCH')
    return {'path': str(p), 'sha256': digest(p), 'size': p.stat().st_size}


def seal_working_copy(source, destination):
    """SQLite backup API includes committed WAL; caller must close its writer first.

    Destination is a NEW snapshot. This never modifies or copies over source.
    """
    src, dst = Path(source).resolve(strict=True), Path(destination).resolve()
    if dst.exists() or src == dst:
        raise ValueError('NEW_SEALED_DESTINATION_REQUIRED')
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src.as_uri() + '?mode=ro', uri=True) as a:
        with sqlite3.connect(dst) as b:
            a.backup(b)
            b.execute('PRAGMA journal_mode=DELETE')
    return str(dst)


class OnDemandWriteback:
    def __init__(self, binding, require_login):
        self.binding, self.require_login = binding, require_login
        if not callable(require_login):
            raise TypeError('LOGIN_GUARD_REQUIRED')

    def _admit(self):
        account = self.require_login()
        if not isinstance(account, str) or account.upper() != self.binding.account:
            raise PermissionError('FAMILY_PROJECT_ACCOUNT_MISMATCH')

    def prepare(self, original, candidate):
        self._admit()
        before, after = inspect(original, self.binding), inspect(candidate, self.binding)
        return {'status': 'STAGED_NOT_PERSISTED', 'account': self.binding.account,
                'client_id': self.binding.client_id, 'file_id': self.binding.file_id,
                'source': before, 'candidate': after}

    def _plan(self, plan):
        self._admit()
        if (plan['account'], plan['client_id'], plan['file_id']) != (
                self.binding.account, self.binding.client_id, self.binding.file_id):
            raise PermissionError('PLAN_BINDING_MISMATCH')
        for part in ('source', 'candidate'):
            current = inspect(plan[part]['path'], self.binding)
            if current != plan[part]:
                raise ValueError('LOCAL_FILE_CHANGED')

    def authorize_update(self, plan, fresh_remote, backup_remote, backup_file_id):
        """Call immediately before update_file after Drive backup and fresh downloads.

        Returned args use the verified absolute local path, NOT an invented URI.
        This is preflight only, not a guarantee against an independent writer.
        """
        self._plan(plan)
        if not backup_file_id or backup_file_id == self.binding.file_id:
            raise ValueError('DISTINCT_REMOTE_BACKUP_REQUIRED')
        for path in (fresh_remote, backup_remote):
            if inspect(path, self.binding)['sha256'] != plan['source']['sha256']:
                raise RuntimeError('STALE_SOURCE_OR_BACKUP_MISMATCH')
        return {'status': 'READY_NOT_PERSISTED', 'backup_file_id': backup_file_id,
                'update_file_args': {'fileId': self.binding.file_id,
                    'file_uri': plan['candidate']['path'],
                    'mime_type': 'application/vnd.sqlite3'}}

    def verify_readback(self, plan, remote, remote_file_id, checks):
        """checks are trusted developer SELECT statements and exact expected rows.

        The remote path MUST be freshly materialized by Drive fetch of file_id,
        not reused from the local candidate. Never call this after a failed fetch.
        """
        self._plan(plan)
        if remote_file_id != self.binding.file_id:
            raise PermissionError('REMOTE_ID_CHANGED')
        p = Path(remote).resolve(strict=True)
        if str(p) in (plan['source']['path'], plan['candidate']['path']):
            raise ValueError('FRESH_REMOTE_READBACK_REQUIRED')
        result = inspect(p, self.binding)
        if result['sha256'] != plan['candidate']['sha256']:
            raise RuntimeError('REMOTE_BYTES_MISMATCH')
        if not checks:
            raise ValueError('FIELD_CHECKS_REQUIRED')
        with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            for sql, params, expected in checks:
                if not sql.lstrip().upper().startswith('SELECT '):
                    raise ValueError('READONLY_FIELD_CHECK_REQUIRED')
                if db.execute(sql, params).fetchall() != [tuple(x) for x in expected]:
                    raise ValueError('REMOTE_FIELD_MISMATCH')
        return {'status': 'PERSISTED_REMOTE_VERIFIED', 'file_id': remote_file_id,
                'client_id': self.binding.client_id, 'sha256': result['sha256'],
                'size': result['size'], 'integrity_check': 'ok',
                'foreign_key_errors': 0, 'field_checks': len(checks),
                'trade_authorization': 'NONE'}


def for_project(auth, *, login_account, client_id, file_id, family_alias):
    """Use the same fixed Sources binding and FamilyLogin as read_progress()."""
    if auth.client_id != client_id or auth.user_id.upper() != login_account:
        raise PermissionError('AUTH_BINDING_MISMATCH')
    return OnDemandWriteback(Binding(login_account, client_id, file_id, family_alias), auth.require_login)
