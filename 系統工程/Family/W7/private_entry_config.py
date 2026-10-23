"""Install the operator-confirmed ChatGPT client without activating HTTP."""
import fcntl
import hashlib
import json
import os
from private_runtime import private_directory, read_private, atomic_private, validate
from private_service_config import load_key


def confirmed_entry():
    return {'schema': 'Family-B07-private-entry-v1',
            'origin': 'https://www.happihelp.com', 'base': '/family-connect',
            'connection_scope': 'family-chatgpt',
            'oauth_clients': {'family-chatgpt': [
                'https://chatgpt.com/connector_platform_oauth_redirect']}}


def install_entry(root):
    root = private_directory(root)
    fd = os.open(root / 'runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        read_private(root / 'runtime.lock')
        runtime = read_private(root / 'runtime.json')
        validate(json.loads(runtime))
        key = load_key(root)
        target = root / 'entry.json'
        data = (json.dumps(confirmed_entry(), sort_keys=True, indent=2) + '\n').encode()
        if target.exists() or target.is_symlink():
            old = read_private(target)
            # Changing a connection identity or client requires an explicit migration.
            if json.loads(old) != confirmed_entry():
                raise ValueError('ENTRY_MIGRATION_REQUIRED')
            backup = root / 'backups'
            backup.mkdir(mode=0o700, exist_ok=True)
            private_directory(backup)
            saved = backup / ('entry-' + hashlib.sha256(old).hexdigest() + '.json')
            if not saved.exists() and not saved.is_symlink():
                atomic_private(saved, old)
            if read_private(saved) != old:
                raise ValueError('ENTRY_BACKUP_MISMATCH')
        atomic_private(target, data)
        if (read_private(target) != data or load_key(root) != key or
                read_private(root / 'runtime.json') != runtime):
            raise ValueError('ENTRY_READBACK_MISMATCH')
        return {'status': 'PASS', 'entry': 'CONFIRMED_CLIENT_INSTALLED',
                'public_enabled': False, 'stable_key': True, 'runtime_unchanged': True}
    finally:
        os.close(fd)
