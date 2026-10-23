"""Provision private B07 state without enabling HTTP or enrolling people."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from private_service_config import load_key, provision_key


def private_directory(path):
    p = Path(path)
    if p.is_symlink() or not p.is_dir() or p.stat().st_uid != os.geteuid() or stat.S_IMODE(p.stat().st_mode) & 0o077:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    return p


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise ValueError('PRIVATE_FILE_REQUIRED')
        data = os.read(fd, 1048577)
        if len(data) > 1048576: raise ValueError('CONFIG_TOO_LARGE')
        return data
    finally: os.close(fd)


def atomic_private(path, data):
    path = Path(path)
    temp = path.parent / ('.pending-' + secrets.token_hex(16))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temp.exists(): temp.unlink()


def validate(config):
    if config.get('schema') != 'Family-B07-private-runtime-v1': raise ValueError('SCHEMA')
    if config.get('enabled') is not False: raise ValueError('NOT_READY_FOR_PUBLIC_ENTRY')
    resource = config['resource_config']
    if resource.get('schema') != 'Family-B06-private-resource-config-v1' or len(resource['resources']) != 6:
        raise ValueError('RESOURCE_CONFIG')
    if not resource.get('backup_folder') or resource.get('pending'): raise ValueError('UNBOUND_RESOURCE')
    if config.get('backup_access_verified') != 'OWNER_ONLY': raise ValueError('BACKUP_ACCESS')
    oauth = config['google_oauth']
    if set(oauth) != {'client_id','client_secret','refresh_token'} or not all(isinstance(v,str) and v for v in oauth.values()):
        raise ValueError('SERVICE_CREDENTIALS_REQUIRED')
    if not isinstance(config.get('source_commit'),str) or len(config['source_commit']) != 40: raise ValueError('SOURCE_COMMIT')


def provision(root, source):
    config = json.loads(read_private(source)); validate(config)
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=True)
    private_directory(root)
    fd = os.open(root/'runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = root/'runtime.json'
        # Once configured, missing/corrupt key must never silently mint a new identity.
        if current.exists() or current.is_symlink():
            old = read_private(current); validate(json.loads(old)); key = load_key(root)
            backup = root/'backups'; backup.mkdir(mode=0o700, exist_ok=True); private_directory(backup)
            target = backup/('runtime-'+hashlib.sha256(old).hexdigest()+'.json')
            if not target.exists(): atomic_private(target,old)
            if read_private(target) != old: raise ValueError('BACKUP_MISMATCH')
        else: key = provision_key(root)
        data = (json.dumps(config,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
        atomic_private(current,data)
        locks=root/'resource-locks';locks.mkdir(mode=0o700,exist_ok=True);private_directory(locks)
        if read_private(current)!=data or load_key(root)!=key: raise ValueError('READBACK_MISMATCH')
        return {'status':'PASS','runtime':'PRIVATE_PERSISTENT_DISABLED','stable_key':True,
                'config_readback':True,'private_permissions':True,'source_commit':config['source_commit']}
    finally: os.close(fd)
