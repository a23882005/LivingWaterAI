"""Private stable service key provisioning. Never print credentials.

Deploy outside public_html. Missing key is provisioned explicitly once;
normal startup only reads, so a lost key cannot silently renew all sessions.
"""
import json
import os
from pathlib import Path
import secrets
import stat


def load_key(directory):
    root=Path(directory)
    if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode)&0o077:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    fd=os.open(root/'server.key',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)&0o077 or st.st_uid!=os.geteuid():
            raise ValueError('PRIVATE_KEY_REQUIRED')
        data=os.read(fd,65)
        if len(data)!=32:raise ValueError('INVALID_KEY')
        return data
    finally:os.close(fd)


def provision_key(directory):
    root=Path(directory)
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.is_symlink() or stat.S_IMODE(root.stat().st_mode)&0o077:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    # Exclusive creation under fixed flock prevents partial reads by provisioners.
    import fcntl
    fd=os.open(root/'provision.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        if (root/'server.key').exists():return load_key(root)
        tmp=root/('key-'+secrets.token_hex(16)+'.tmp')
        key=secrets.token_bytes(32)
        kfd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:os.write(kfd,key);os.fsync(kfd)
        finally:os.close(kfd)
        try:os.link(tmp,root/'server.key')
        finally:tmp.unlink()
        dfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
        return load_key(root)
    finally:os.close(fd)
