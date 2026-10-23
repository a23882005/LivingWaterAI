"""B06 single-host shared SQLite coordinator.

All callers use ONE persistent lock directory on ONE writer host. B04/B21's
durable request queue invokes this module; callers never write Drive directly.
Catalog, ACL, handlers, clock and backend are trusted server configuration.
No network identity is constructed here; B07 supplies verified principals.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from resource_headers import authorize, validate_header, validate_policies

LIMIT = 64 * 1024 * 1024
RECEIPTS = '_family_io_receipts'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)

def checked(data):
    if not isinstance(data, bytes) or len(data) > LIMIT or not data.startswith(b'SQLite format 3\0'):
        raise ValueError('INVALID_DATABASE')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'check.db'
        path.write_bytes(data)
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('pragma integrity_check').fetchall() != [('ok',)]:
                raise ValueError('INTEGRITY_FAILED')
            if db.execute('pragma foreign_key_check').fetchall():
                raise ValueError('FOREIGN_KEYS_FAILED')
    return data

def transaction(data, subject, request_id, operation, payload, handler):
    fingerprint = digest(canonical([operation, payload]).encode())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'working.db'
        path.write_bytes(checked(data))
        db = sqlite3.connect(path, isolation_level=None)
        try:
            db.execute('pragma foreign_keys=on')
            db.execute('begin immediate')
            db.execute(f'create table if not exists {RECEIPTS} '
                       '(subject text, request_id text, fingerprint text not null, '
                       'result text not null, primary key(subject, request_id))')
            old = db.execute(f'select fingerprint,result from {RECEIPTS} where subject=? and request_id=?',
                             (subject, request_id)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise ValueError('REQUEST_COLLISION')
                db.rollback()
                return data, json.loads(old[1]), True
            # Trusted handlers still cannot accidentally commit early, attach a
            # second database, alter pragmas or manipulate the receipt ledger.
            def guard(action, arg1, arg2, database, trigger):
                if (action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
                               sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA)
                    or arg1 == RECEIPTS or arg2 == RECEIPTS):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(guard)
            result = handler(db, copy.deepcopy(payload))
            encoded = canonical(result)
            if len(encoded.encode()) > 1024 * 1024:
                raise ValueError('RESULT_TOO_LARGE')
            # Python 3.9 on the writer host requires a callable; None is only
            # supported from 3.11. Handlers have already returned here.
            db.set_authorizer(lambda *args: sqlite3.SQLITE_OK)
            db.execute(f'insert into {RECEIPTS} values(?,?,?,?)',
                       (subject, request_id, fingerprint, encoded))
            if db.execute('pragma foreign_key_check').fetchall():
                raise ValueError('FOREIGN_KEYS_FAILED')
            db.commit()
        except BaseException:
            db.set_authorizer(lambda *args: sqlite3.SQLITE_OK)
            db.rollback()
            raise
        finally:
            db.close()
        return checked(path.read_bytes()), json.loads(encoded), False

class Coordinator:
    """Backend methods: read, journal, save_journal, backup, backup_info, write.

    read/write always address a bound file ID. Journal is durable per resource;
    save_journal replaces its complete value. write replaces bytes at SAME ID.
    backup returns a verified, immutable copy with source ID/hash metadata.
    """
    def __init__(self, headers, policies, backend, lock_dir, handlers, clock=time.time,
                 restore_subjects=(), *, session_guard):
        self.headers = copy.deepcopy(headers)
        self.policies = copy.deepcopy(validate_policies(policies))
        for key, h in self.headers.items():
            validate_header(h)
            if key != h['resource_key']:
                raise ValueError('RESOURCE_KEY_MISMATCH')
        ids = [h['file_id'] for h in self.headers.values() if h['file_id']]
        if len(set(ids)) != len(ids):
            raise ValueError('DUPLICATE_FILE_ID')
        self.backend, self.handlers, self.clock = backend, dict(handlers), clock
        if not callable(session_guard):
            raise TypeError('SESSION_GUARD_REQUIRED')
        self.session_guard = session_guard
        self.restore_subjects = frozenset(restore_subjects)
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _admit(self, resource, principal, operation):
        file_id = authorize(self.headers[resource], self.policies, principal, operation, int(self.clock()))
        # B07 supplies the authoritative session lookup, including revocation.
        # It may accept its VerifiedPrincipal subclass containing a session ID.
        if self.session_guard(principal) is not True:
            raise PermissionError('SESSION_REVOKED')
        return file_id

    @contextmanager
    def _lock(self, file_id):
        # Never unlink: all processes must keep using the same inode.
        path = self.lock_dir / (digest(file_id.encode()) + '.lock')
        with path.open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _save(self, file_id, journal):
        self.backend.save_journal(file_id, copy.deepcopy(journal))
        if self.backend.journal(file_id) != journal:
            raise RuntimeError('JOURNAL_READBACK_FAILED')

    def _recover(self, file_id):
        data = checked(self.backend.read(file_id))
        journal = self.backend.journal(file_id)
        if journal is None:
            journal = dict(epoch=uuid.uuid4().hex, last=digest(data), pending=None,
                           state='Close', readers=[], updater=None, last_restore=None)
            self._save(file_id, journal)
        confirmed = copy.deepcopy(journal)
        pending = journal['pending']
        if pending:
            actual = digest(data)
            if actual not in (pending['before'], pending['after']):
                raise RuntimeError('EXTERNAL_CHANGE')
            if actual == pending['after']:
                journal['epoch'] = pending['next_epoch']
                if pending.get('restore'):
                    journal['last_restore'] = pending['restore']
            journal.update(last=actual, pending=None)
        elif digest(data) != journal['last']:
            raise RuntimeError('EXTERNAL_CHANGE')
        journal.update(state='Close', readers=[], updater=None)
        # The freshly read journal is already durable when unchanged. Avoid a
        # redundant Drive write/readback while preserving every state transition.
        if journal != confirmed:
            self._save(file_id, journal)
        return data, journal

    def _state(self, file_id, journal, state, subject=None):
        target = dict(state=state, readers=[subject] if state == 'Read' else [],
                      updater=subject if state == 'Update' else None)
        if all(journal.get(k) == v for k, v in target.items()):
            return
        journal.update(target)
        self._save(file_id, journal)

    def snapshot(self, resource, principal):
        file_id = self._admit(resource, principal, 'read')
        with self._lock(file_id):
            self._admit(resource, principal, 'read')
            data, journal = self._recover(file_id)
            self._state(file_id, journal, 'Read', principal.subject)
            try:
                self._admit(resource, principal, 'read')
                return dict(data=data, sha256=digest(data), epoch=journal['epoch'])
            finally:
                self._state(file_id, journal, 'Close')

    def _commit(self, file_id, original, candidate, journal, principal, resource,
                next_epoch, restore=None):
        backup_id = self.backend.backup(file_id)
        info = self.backend.backup_info(backup_id)
        if (info['source_id'] != file_id or info['sha256'] != digest(original)
            or self.backend.read(backup_id) != original or self.backend.read(file_id) != original):
            raise RuntimeError('BACKUP_OR_SOURCE_MISMATCH')
        journal['pending'] = dict(before=digest(original), after=digest(candidate),
                                  backup_id=backup_id, next_epoch=next_epoch, restore=restore)
        self._save(file_id, journal)
        if self.backend.read(file_id) != original:
            raise RuntimeError('PREWRITE_CONFLICT')
        self._admit(resource, principal, 'update')
        self.backend.write(file_id, candidate)
        if self.backend.read(file_id) != candidate:
            raise RuntimeError('COMMIT_READBACK_FAILED')
        journal.update(last=digest(candidate), pending=None, epoch=next_epoch)
        if restore:
            journal['last_restore'] = restore
        self._state(file_id, journal, 'Close')
        return backup_id

    def update(self, resource, principal, request_id, epoch, operation, payload):
        file_id = self._admit(resource, principal, 'update')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('INVALID_REQUEST_ID')
        if operation not in self.handlers:
            raise ValueError('UNKNOWN_OPERATION')
        # Validate JSON before queue/lock or backend changes.
        payload = copy.deepcopy(payload)
        canonical(payload)
        with self._lock(file_id):
            self._admit(resource, principal, 'update')
            original, journal = self._recover(file_id)
            if epoch != journal['epoch']:
                raise RuntimeError('STALE_EPOCH')
            self._state(file_id, journal, 'Update', principal.subject)
            try:
                candidate, result, duplicate = transaction(original, principal.subject,
                    request_id, operation, payload, self.handlers[operation])
                if duplicate:
                    self._admit(resource, principal, 'update')
                    return dict(result=result, duplicate=True, epoch=epoch)
                backup_id = self._commit(file_id, original, candidate, journal, principal,
                                         resource, epoch)
                return dict(result=result, duplicate=False, epoch=epoch, backup_id=backup_id)
            finally:
                # A pending journal is retained on uncertainty. Next holder
                # resolves actual bytes before admitting any new operation.
                if journal['pending'] is None:
                    self._state(file_id, journal, 'Close')

    def restore(self, resource, principal, backup_id, expected_epoch, request_id):
        file_id = self._admit(resource, principal, 'update')
        if principal.subject not in self.restore_subjects:
            raise PermissionError('MAINTENANCE_ROLE_REQUIRED')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('INVALID_REQUEST_ID')
        with self._lock(file_id):
            self._admit(resource, principal, 'update')
            original, journal = self._recover(file_id)
            prior = journal.get('last_restore')
            key = dict(subject=principal.subject, request_id=request_id,
                       backup_id=backup_id, old_epoch=expected_epoch)
            if prior and all(prior.get(k) == v for k, v in key.items()):
                return dict(epoch=journal['epoch'], duplicate=True)
            if expected_epoch != journal['epoch']:
                raise RuntimeError('STALE_EPOCH')
            info = self.backend.backup_info(backup_id)
            if info['source_id'] != file_id:
                raise PermissionError('WRONG_RESOURCE_BACKUP')
            candidate = checked(self.backend.read(backup_id))
            if digest(candidate) != info['sha256']:
                raise RuntimeError('BACKUP_HASH_MISMATCH')
            next_epoch = uuid.uuid4().hex
            self._state(file_id, journal, 'Update', principal.subject)
            try:
                saved = self._commit(file_id, original, candidate, journal, principal, resource,
                                     next_epoch, restore=key)
                return dict(epoch=next_epoch, duplicate=False, before_restore_backup=saved)
            finally:
                if journal['pending'] is None:
                    self._state(file_id, journal, 'Close')
