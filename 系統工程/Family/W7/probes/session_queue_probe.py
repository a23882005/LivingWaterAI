"""SYNTHETIC ONLY. Local contract prototype, not a deployed trust/Drive service.

An actual issuer must obtain Project identity outside user-controlled text.
This model deliberately has no Google credentials and cannot write formal DBs.
"""
import hashlib
import hmac
import json
import sqlite3

TTL=4*60*60
def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def issue(key, project, member, device, session, now):
    claims=dict(project=project,member=member,device=device,session=session,issued=now,expires=now+TTL)
    return claims,hmac.new(key,encode(claims),hashlib.sha256).hexdigest()

def verify(key, token, *, project, member, device, now):
    claims,signature=token
    if not hmac.compare_digest(hmac.new(key,encode(claims),hashlib.sha256).hexdigest(),signature):
        raise ValueError('INVALID_SIGNATURE')
    if (claims['project'],claims['member'],claims['device'])!=(project,member,device):
        raise ValueError('BINDING_MISMATCH')
    if claims['expires']!=claims['issued']+TTL or not claims['issued']<=now<claims['expires']:
        raise ValueError('SESSION_EXPIRED_OR_INVALID')
    return dict(claims)  # reading never slides expiry

class Queue:
    """One SQLite authority models FIFO, retries and fencing across connections.

    File must be server-local for a real queue; uploading copies to Drive does
    not create a distributed lock. No remote commit atomicity is claimed here.
    """
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10,isolation_level=None)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(seq INTEGER PRIMARY KEY, request TEXT UNIQUE,
          resource TEXT NOT NULL,payload_hash TEXT NOT NULL,state TEXT NOT NULL,
          fence INTEGER NOT NULL DEFAULT 0,expires INTEGER);
        CREATE TABLE IF NOT EXISTS resource_state(resource TEXT PRIMARY KEY,
          version INTEGER NOT NULL DEFAULT 0, fence INTEGER NOT NULL DEFAULT 0);
        ''')
    def close(self):self.db.close()
    def enqueue(self,request,resource,payload):
        digest=hashlib.sha256(encode(payload)).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT resource,payload_hash FROM jobs WHERE request=?',(request,)).fetchone()
            if row and row!=(resource,digest):raise ValueError('REQUEST_ID_COLLISION')
            self.db.execute("INSERT OR IGNORE INTO jobs(request,resource,payload_hash,state) VALUES(?,?,?,'QUEUED')",(request,resource,digest))
            self.db.execute('INSERT OR IGNORE INTO resource_state(resource) VALUES(?)',(resource,))
            self.db.commit()
        except BaseException:self.db.rollback();raise
    def acquire(self,resource,now,lease=30):
        if lease<=0:raise ValueError('INVALID_LEASE')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute("SELECT request,state,expires FROM jobs WHERE resource=? AND state!='DONE' ORDER BY seq LIMIT 1",(resource,)).fetchone()
            if not row or (row[1]=='ACTIVE' and row[2]>now):
                self.db.commit();return None
            self.db.execute('UPDATE resource_state SET fence=fence+1 WHERE resource=?',(resource,))
            version,fence=self.db.execute('SELECT version,fence FROM resource_state WHERE resource=?',(resource,)).fetchone()
            self.db.execute("UPDATE jobs SET state='ACTIVE',fence=?,expires=? WHERE request=?",(fence,now+lease,row[0]))
            self.db.commit();return (row[0],resource,fence,version)
        except BaseException:self.db.rollback();raise
    def commit(self,ticket,now):
        request,resource,fence,version=ticket
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT state,fence,expires FROM jobs WHERE request=? AND resource=?',(request,resource)).fetchone()
            current=self.db.execute('SELECT version,fence FROM resource_state WHERE resource=?',(resource,)).fetchone()
            if not row or row[0]!='ACTIVE' or row[1]!=fence or now>=row[2] or current!=(version,fence):
                raise ValueError('STALE_WORKER')
            self.db.execute('UPDATE resource_state SET version=version+1 WHERE resource=?',(resource,))
            self.db.execute("UPDATE jobs SET state='DONE' WHERE request=?",(request,));self.db.commit()
        except BaseException:self.db.rollback();raise
