"""Verify only W5-authorized source and packaged direct dependency hashes."""
import hashlib
import json
import os
from pathlib import Path


def verify(repo_root):
    home=Path(__file__).resolve().parent
    rows=[]
    for filename in ('source_lock.json','dependency_lock.json'):
        lock=json.loads((home/filename).read_text())
        for row in lock['files'] if isinstance(lock,dict) else lock:
            rows.append((Path(repo_root)/row['path'],row['sha256']))
    for filename in ('w2_dependency_lock.json','frozen_schema_lock.json','c7_fixture_lock.json'):
        for row in json.loads((home/filename).read_text())['files']:
            rows.append((home/row['destination'],row['sha256']))
    for path,expected in rows:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('DEPENDENCY_HASH_MISMATCH:'+str(path))
    return len(rows)


if __name__=='__main__':
    root=os.environ.get('W5_SOURCE_ROOT',str(Path(__file__).resolve().parents[3]))
    print(f'{verify(root)} authorized source/dependency hashes PASS')
