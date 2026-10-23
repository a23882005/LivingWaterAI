"""Bind the persistent account service to the approved private B06 mapping.

Construction performs no Drive calls, schema changes, seeding or cleanup.
Public activation and verified OAuth client registration are separate gates.
"""
import copy
import json
import os
import re
from pathlib import Path
from private_runtime import private_directory, read_private, validate
from private_service_config import load_key
from drive_service_transport import GoogleDriveTransport
from drive_resource_backend import DriveResourceBackend
from 帳號管理 import AccountManager, B06AccountStore
from account_http import AccountHTTP, RateLimiter
from account_oauth import OAuthService
from account_router import AccountRouter

ACCOUNT_POLICY = {'read': ['service:account-manager'],
                  'update': ['service:account-manager']}


def account_binding(resource):
    """Expose only accounts to the account coordinator, never business files."""
    header = copy.deepcopy(resource['headers']['accounts'])
    file_id = header['file_id']
    mapping = copy.deepcopy(resource['resources'][file_id])
    if (header.get('resource_key') != 'accounts' or
            header.get('policy_ref') != 'accounts' or
            header.get('binding') != 'BOUND' or
            mapping['header_template'] != header):
        raise ValueError('ACCOUNT_BINDING_MISMATCH')
    if resource.get('deployment', {}).get('single_writer_host') is not True:
        raise ValueError('SINGLE_WRITER_REQUIRED')
    if resource['deployment'].get('lock_dir') != 'resource-locks':
        raise ValueError('PRIVATE_LOCK_DIRECTORY_REQUIRED')
    return {'accounts': header}, {file_id: mapping}


def load_manager(root, *, transport_factory=GoogleDriveTransport):
    """Internal preparation only: does not enable HTTP or create a new key."""
    root = private_directory(Path(root))
    config = json.loads(read_private(root / 'runtime.json'))
    validate(config)
    key = load_key(root)
    locks = private_directory(root / 'resource-locks')
    resource = config['resource_config']
    headers, mapping = account_binding(resource)
    transport = transport_factory(**config['google_oauth'])
    backend = DriveResourceBackend(transport, mapping, resource['backup_folder'])
    store = B06AccountStore(headers, {'accounts': copy.deepcopy(ACCOUNT_POLICY)}, backend, locks)
    return AccountManager(store, key)


def load_router(root, *, transport_factory=GoogleDriveTransport):
    """Prepare exact routes from private operator configuration, not a request.

    The caller must keep public entry disabled until enrollment/acceptance.
    No migration is run here; ordinary startup must never mutate the database.
    """
    root = private_directory(Path(root))
    entry = json.loads(read_private(root / 'entry.json'))
    if entry.get('schema') != 'Family-B07-private-entry-v1':
        raise ValueError('ENTRY_SCHEMA')
    base, scope = entry['base'], entry['connection_scope']
    if not isinstance(base, str) or not re.fullmatch(r'/[a-z][a-z0-9-]{1,63}', base):
        raise ValueError('EXACT_BASE_REQUIRED')
    if not isinstance(scope, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', scope):
        raise ValueError('STABLE_CONNECTION_SCOPE_REQUIRED')
    manager = load_manager(root, transport_factory=transport_factory)
    # Validate any existing SQLite path before handing it to the limiter.
    rate = root / 'rate.db'
    if rate.exists() or rate.is_symlink(): read_private(rate)
    limiter = RateLimiter(rate, load_key(root))
    account = AccountHTTP(manager, entry['origin'], scope, limiter)
    oauth = OAuthService(manager, entry['origin'] + base + '/oauth',
                         entry['origin'] + base + '/mcp', entry['oauth_clients'], scope)
    try:
        fd = os.open(rate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        read_private(rate)
    else:
        os.close(fd)
    return AccountRouter(oauth, account, base)
