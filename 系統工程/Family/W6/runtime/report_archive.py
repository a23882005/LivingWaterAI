"""Immutable dated report publishing and retrieval through a private Drive folder.

The trusted entry supplies the authenticated owner, server-owned folder and
single-host lock. Publish only completed renderer outputs; a manifest written
last makes a group visible. No investment computation, overwrite or deletion.
"""
import fcntl
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

API = 'https://www.googleapis.com/drive/v3/files'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files/'
TAIPEI = timezone(timedelta(hours=8))
CLIENT_ID = 'fam_2c96026b72544e828b98be640399432e'
EXTENSIONS = {'html', 'pdf', 'xlsx', 'zip', 'png', 'json'}
MIMES = {'html': 'text/html', 'pdf': 'application/pdf',
         'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'zip': 'application/zip', 'png': 'image/png', 'json': 'application/json'}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def report_basename(created_at):
    if not isinstance(created_at, datetime) or created_at.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return 'Joseph_配置報告_' + created_at.astimezone(TAIPEI).strftime('%Y%m%d_%H%M%S_TW')


def _artifact_filename(base, artifact, extension_counts):
    stem, extension = artifact.rsplit('.', 1)
    # A single primary output uses the requested canonical form exactly:
    # Joseph_配置報告_YYYYMMDD_HHMMSS_TW.pdf. When several artifacts share an
    # extension (for example page images), retain each one with a clear suffix.
    suffix = '' if extension_counts[extension] == 1 else '_' + stem
    return f'{base}{suffix}.{extension}'


class DriveReportStore:
    def __init__(self, transport, *, folder_id, lock_path, client_id=CLIENT_ID):
        if client_id != CLIENT_ID or not re.fullmatch(r'[A-Za-z0-9_-]+', folder_id):
            raise ValueError('INVALID_REPORT_BINDING')
        self.call, self.folder_id, self.client_id = transport.call, folder_id, client_id
        self.lock_path = Path(lock_path)
        if not self.lock_path.is_absolute():
            raise ValueError('ABSOLUTE_SERVER_LOCK_REQUIRED')

    @contextmanager
    def locked(self, auth):
        if auth.require_login() != 'JO':
            raise PermissionError('REPORT_OWNER_MISMATCH')
        # Reuse the configured single-host writer lock. It must already exist.
        with self.lock_path.open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if auth.require_login() != 'JO':
                    raise PermissionError('REPORT_OWNER_MISMATCH')
                meta = self.call(API + '/' + self.folder_id + '?fields=id,mimeType,trashed')
                if (meta.get('id') != self.folder_id or meta.get('trashed')
                    or meta.get('mimeType') != 'application/vnd.google-apps.folder'):
                    raise PermissionError('REPORT_FOLDER_CHANGED')
                permissions = self.call(API + '/' + self.folder_id + '/permissions?fields=permissions(type,role)')
                if not permissions.get('permissions') or any(p.get('type') != 'user'
                    or p.get('role') != 'owner' for p in permissions['permissions']):
                    raise PermissionError('PRIVATE_OWNER_ONLY_FOLDER_REQUIRED')
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def list(self, kind=None):
        query = "'" + self.folder_id + "' in parents and trashed=false and appProperties has { key='family_client' and value='" + self.client_id + "' }"
        if kind:
            query += " and appProperties has { key='family_kind' and value='" + kind + "' }"
        rows, token = [], None
        while True:
            params = dict(q=query, fields='nextPageToken,files(id,name,parents,appProperties)', pageSize=100)
            if token:
                params['pageToken'] = token
            result = self.call(API + '?' + urlencode(params))
            rows.extend(result.get('files', []))
            token = result.get('nextPageToken')
            if not token:
                return rows

    def read(self, file_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
            raise ValueError('INVALID_REPORT_FILE_ID')
        meta = self.call(API + '/' + file_id + '?fields=id,parents,trashed,appProperties')
        if (meta.get('trashed') or self.folder_id not in meta.get('parents', [])
            or meta.get('appProperties', {}).get('family_client') != self.client_id):
            raise PermissionError('REPORT_FILE_BINDING_MISMATCH')
        return self.call(API + '/' + file_id + '?alt=media', raw=True)

    def create(self, name, data, kind, report_key):
        # A preallocated ID isolates a failed upload. Do not automatically retry.
        file_id = self.call(API + '/generateIds?count=1&space=drive')['ids'][0]
        properties = {'family_client': self.client_id,
                      'family_kind': 'staged_manifest' if kind == 'manifest' else kind,
                      'family_report_key': report_key}
        self.call(API, 'POST', {'id': file_id, 'name': name, 'parents': [self.folder_id],
            'mimeType': MIMES[name.rsplit('.', 1)[1]], 'appProperties': properties})
        self.call(UPLOAD + file_id + '?uploadType=media', 'PATCH', data)
        if self.read(file_id) != data:
            raise RuntimeError('REPORT_READBACK_FAILED')
        if kind == 'manifest':
            properties['family_kind'] = 'manifest'
            self.call(API + '/' + file_id, 'PATCH', {'appProperties': properties})
        return {'id': file_id, 'name': name, 'sha256': _sha(data),
                'url': 'https://drive.google.com/file/d/' + file_id + '/view'}


def _verified_manifest(store, row):
    try:
        m = json.loads(store.read(row['id']))
        if (m['schema'] != 'Family.ReportArchive.v1' or m['client_id'] != store.client_id
            or m['state'] != 'COMPLETE' or not m['files']):
            raise ValueError()
        for file in m['files']:
            if _sha(store.read(file['id'])) != file['sha256']:
                raise ValueError()
        return m
    except (KeyError, TypeError, ValueError, PermissionError) as error:
        raise RuntimeError('REPORT_MANIFEST_INVALID') from error


def publish_report(store, auth, *, run_id, artifacts, data_as_of, analysis_version,
                   created_at=None):
    if not isinstance(run_id, str) or not run_id.strip() or not data_as_of or not analysis_version:
        raise ValueError('REPORT_METADATA_REQUIRED')
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError('REPORT_ARTIFACTS_REQUIRED')
    for key, data in artifacts.items():
        if (not re.fullmatch(r'[a-z][a-z0-9_-]*\.[a-z0-9]+', key)
            or key.rsplit('.', 1)[1] not in EXTENSIONS
            or not isinstance(data, bytes) or not data or len(data) > 64 * 1024 * 1024):
            raise ValueError('INVALID_REPORT_ARTIFACT')
    created_at = created_at or datetime.now(timezone.utc)
    base = report_basename(created_at)
    key = _sha((store.client_id + '\0' + run_id).encode())
    fingerprint = _sha(_canonical({'artifacts': {k: _sha(v) for k, v in artifacts.items()},
                                    'data_as_of': data_as_of, 'analysis_version': analysis_version}))
    with store.locked(auth):
        existing = [r for r in store.list('manifest')
                    if r.get('appProperties', {}).get('family_report_key') == key]
        if existing:
            if len(existing) != 1:
                raise RuntimeError('DUPLICATE_REPORT_RECEIPTS')
            manifest = _verified_manifest(store, existing[0])
            if manifest['fingerprint'] != fingerprint:
                raise ValueError('REPORT_RUN_CONFLICT')
            return manifest
        names = {r['name'] for r in store.list()}
        suffix, candidate = 1, base
        def used(stem):
            return any(n.startswith(stem + '_') or n.startswith(stem + '.') for n in names)
        while used(candidate):
            suffix += 1
            candidate = base + f'_{suffix:02}'
        files = []
        extension_counts = {}
        for artifact in artifacts:
            extension = artifact.rsplit('.', 1)[1]
            extension_counts[extension] = extension_counts.get(extension, 0) + 1
        for artifact, data in sorted(artifacts.items()):
            if auth.require_login() != 'JO':
                raise PermissionError('REPORT_OWNER_MISMATCH')
            files.append(store.create(_artifact_filename(candidate, artifact, extension_counts),
                                      data, 'artifact', key))
        manifest = {'schema': 'Family.ReportArchive.v1', 'state': 'COMPLETE',
            'client_id': store.client_id, 'run_id': run_id, 'fingerprint': fingerprint,
            'created_at': created_at.astimezone(TAIPEI).isoformat(), 'sequence': suffix,
            'data_as_of': data_as_of, 'analysis_version': analysis_version, 'files': files}
        if auth.require_login() != 'JO':
            raise PermissionError('REPORT_OWNER_MISMATCH')
        store.create(candidate + '.manifest.json', _canonical(manifest), 'manifest', key)
        return manifest


def previous_report(store, auth, *, date=None):
    if date is not None:
        datetime.strptime(date, '%Y-%m-%d')
    with store.locked(auth):
        manifests = [_verified_manifest(store, r) for r in store.list('manifest')]
        if date:
            manifests = [m for m in manifests if m['created_at'][:10] == date]
        return max(manifests, key=lambda m: (datetime.fromisoformat(m['created_at']), m['sequence']), default=None)
