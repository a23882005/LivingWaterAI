"""Drive adapter for B06. Mapping and transport are server-owned configuration.

Journal is a separate private JSON file (not a lock or user-writable ACL).
The single-host coordinator lock spans every Drive call. Transport must enforce
timeouts/response size, renew its service token and redact errors at the edge.
"""
import json
import copy
from 資料存取管理 import checked, digest, canonical
from resource_headers import render_header, validate_header

API = 'https://www.googleapis.com/drive/v3/files/'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files/'

class DriveResourceBackend:
    def __init__(self, transport, resources, backup_folder):
        self.call = transport.call
        self.resources = copy.deepcopy(resources)
        self.backup_folder = backup_folder
        journals = [v['journal_id'] for v in self.resources.values()]
        if len(journals) != len(set(journals)) or set(journals) & set(resources):
            raise ValueError('INVALID_JOURNAL_MAPPING')
        header_ids = [v['header_id'] for v in self.resources.values()]
        if len(set(header_ids)) != len(header_ids) or set(header_ids) & (set(journals) | set(resources)):
            raise ValueError('INVALID_HEADER_MAPPING')
        for file_id, resource in self.resources.items():
            validate_header(resource['header_template'])
            if resource['header_template']['file_id'] != file_id:
                raise ValueError('HEADER_BINDING_MISMATCH')

    def _meta(self, file_id):
        return self.call(API + file_id + '?fields=id,parents,trashed,appProperties')

    def _target(self, file_id):
        resource = self.resources[file_id]
        for id_, parent in ((file_id, resource['parent_id']),
                            (resource['journal_id'], resource['journal_parent_id']),
                            (resource['header_id'], resource['parent_id'])):
            m = self._meta(id_)
            if m['id'] != id_ or m.get('trashed') or parent not in m.get('parents', []):
                raise RuntimeError('RESOURCE_LOCATION_CHANGED')
        return resource

    def read(self, file_id):
        if file_id in self.resources:
            self._target(file_id)
        else:
            self.backup_info(file_id)
        return checked(self.call(API + file_id + '?alt=media', raw=True))

    def write(self, file_id, data):
        self._target(file_id)
        self.call(UPLOAD + file_id + '?uploadType=media', 'PATCH', checked(data))

    def journal(self, file_id):
        resource = self._target(file_id)
        value = self.call(API + resource['journal_id'] + '?alt=media', raw=True)
        return json.loads(value)

    def save_journal(self, file_id, value):
        resource = self._target(file_id)
        self.call(UPLOAD + resource['journal_id'] + '?uploadType=media', 'PATCH', canonical(value).encode())
        header = dict(resource['header_template'])
        header.update(state=value['state'], readers=value['readers'], updater=value['updater'])
        data = render_header(header).encode()
        id_ = resource['header_id']
        before = self.call(API + id_ + '?alt=media', raw=True)
        if before != data:
            backup = self.call(API + id_ + '/copy?fields=id', 'POST', {
                'name': 'Family_B06_header_before_' + digest(before)[:16] + '.md',
                'parents': [self.backup_folder]})['id']
            if self.call(API + backup + '?alt=media', raw=True) != before:
                raise RuntimeError('HEADER_BACKUP_MISMATCH')
            self.call(UPLOAD + id_ + '?uploadType=media', 'PATCH', data)
            if self.call(API + id_ + '?alt=media', raw=True) != data:
                raise RuntimeError('HEADER_READBACK_FAILED')

    def backup(self, file_id):
        before = self.read(file_id)
        meta = self.call(API + file_id + '/copy?fields=id', 'POST', {
            'name': 'Family_B06_before_' + digest(before)[:16] + '.db',
            'parents': [self.backup_folder],
            'appProperties': {'b06_source': file_id, 'b06_sha256': digest(before)}})
        return meta['id']

    def backup_info(self, backup_id):
        m = self._meta(backup_id)
        props = m.get('appProperties', {})
        if (m.get('trashed') or self.backup_folder not in m.get('parents', [])
            or props.get('b06_source') not in self.resources
            or len(props.get('b06_sha256', '')) != 64):
            raise PermissionError('UNVERIFIED_BACKUP')
        return dict(source_id=props['b06_source'], sha256=props['b06_sha256'])
