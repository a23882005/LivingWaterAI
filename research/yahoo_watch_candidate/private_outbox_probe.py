"""Synthetic persistent-filesystem probe. No mail/network/real accounts or DBs.
Run only on an authorized server in a verified non-public parent directory.
Creates a NEW dedicated private folder and retains its synthetic recovery state.
"""
import argparse
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
from safe_notify import PrivateOutbox


def validate_private_directory(root):
    resolved=root.resolve(strict=True)
    if root.is_symlink() or any(p.lower() in {'public_html','www','htdocs'} for p in resolved.parts):
        raise ValueError('PUBLIC_OR_SYMLINK_PATH_FORBIDDEN')
    mode=resolved.stat()
    if not stat.S_ISDIR(mode.st_mode) or mode.st_uid!=os.geteuid() or stat.S_IMODE(mode.st_mode)&0o077:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    return resolved


def worker(root,event,crash=False):
    root=validate_private_directory(root)
    lock_path=root/'outbox.lock'
    fd=os.open(lock_path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        if stat.S_IMODE(os.fstat(fd).st_mode)&0o077:
            raise ValueError('LOCK_ACCESS_TOO_BROAD')
        with os.fdopen(fd,'r+') as lock:
            fd=None
            fcntl.flock(lock,fcntl.LOCK_EX)
            box=PrivateOutbox(root/'outbox.sqlite',private_storage_verified=True)
            state=box.reserve(event,'synthetic-fixed-body')
            if crash:
                os._exit(19)  # after durable commit, before simulated confirmation
            if state=='RESERVED':
                box.mark_sent(event)
            box.close()
            return state
    finally:
        if fd is not None:os.close(fd)


def run_probe(parent,run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',run_id):raise ValueError('INVALID_RUN_ID')
    parent=parent.resolve(strict=True)
    if any(p.lower() in {'public_html','www','htdocs'} for p in parent.parts):raise ValueError('PUBLIC_PARENT_FORBIDDEN')
    root=parent/('.v82-watch-synthetic-'+run_id)
    root.mkdir(mode=0o700)  # fail if existing; never reuse another DB or alter its permissions
    validate_private_directory(root)
    command=[sys.executable,str(Path(__file__).resolve()),'worker','--root',str(root),'--event','concurrent']
    def launch(_):
        p=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if p.returncode:raise ValueError('WORKER_FAILED')
        return p.stdout.strip()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(launch,range(12)))
    if results.count('RESERVED')!=1 or results.count('SENT')!=11:raise ValueError('CONCURRENCY_FAILED')
    crash=subprocess.run([sys.executable,str(Path(__file__).resolve()),'worker','--root',str(root),'--event','interrupted','--crash'],capture_output=True,timeout=30)
    if crash.returncode!=19:raise ValueError('INTERRUPTION_FAILED')
    if worker(root,'interrupted')!='PENDING':raise ValueError('UNSAFE_AUTOMATIC_RETRY')
    if worker(root,'concurrent')!='SENT':raise ValueError('RESTART_DEDUP_FAILED')
    db=sqlite3.connect(root/'outbox.sqlite')
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    count=db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0];db.close()
    if integrity!='ok' or count!=2:raise ValueError('READBACK_FAILED')
    for p in root.iterdir():
        if p.is_symlink() or stat.S_IMODE(p.stat().st_mode)&0o077:raise ValueError('FILE_ACCESS_TOO_BROAD')
    return dict(schema='V82_SYNTHETIC_OUTBOX_PROBE_V1',passed=True,
                workers=12,reservations=1,deduplicated=11,
                interruption_pending_preserved=True,restart_dedup=True,
                sqlite_integrity='ok',synthetic_rows=2,
                smtp_called=False,production_db_touched=False)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('probe');a.add_argument('--parent',required=True,type=Path);a.add_argument('--run-id',required=True)
    a=sub.add_parser('worker');a.add_argument('--root',required=True,type=Path);a.add_argument('--event',required=True);a.add_argument('--crash',action='store_true')
    args=p.parse_args()
    try:
        if args.mode=='worker':print(worker(args.root,args.event,args.crash))
        else:print(json.dumps(run_probe(args.parent,args.run_id),sort_keys=True))
    except Exception:
        print('SYNTHETIC_OUTBOX_PROBE_FAILED',file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
