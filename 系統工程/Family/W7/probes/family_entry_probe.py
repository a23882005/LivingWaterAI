"""B04 HTTP capability probe; synthetic data only, loopback by default.

Authenticated connection keys map to synthetic family accounts. Conversation
and Project labels never choose an account. Business sessions last four hours.
This executable demonstrates the common entry contract, not Drive deployment.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TTL = 14400
MAX_BODY = 8192


class Rejected(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class Entry:
    def __init__(self, path, principals, clock=time.time):
        self.path, self.clock = path, clock
        self.principals = dict(principals)
        if not principals or any(
            not isinstance(k, str) or len(k) != 64
            or any(c not in '0123456789abcdef' for c in k)
            or not isinstance(v, dict) or set(v) != {'account', 'kind'}
            or not isinstance(v['account'], str) or not v['account'].startswith('synthetic-')
            or v['kind'] not in ('chat', 'action') for k, v in principals.items()
        ):
            raise ValueError('SYNTHETIC_PRINCIPAL_CONFIG_REQUIRED')
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and ('meta' not in tables or db.execute("SELECT value FROM meta WHERE name='scope'").fetchone() != ('SYNTHETIC_ONLY',)):
                raise ValueError('EXISTING_NON_PROBE_DB_REJECTED')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS sessions(account TEXT PRIMARY KEY,
                  issued INTEGER NOT NULL, expires INTEGER NOT NULL, generation TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(seq INTEGER PRIMARY KEY,
                  account TEXT NOT NULL, request_id TEXT NOT NULL,
                  delta INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'QUEUED',
                  result INTEGER, generation TEXT NOT NULL, UNIQUE(account, request_id));
                CREATE TABLE IF NOT EXISTS counters(account TEXT PRIMARY KEY, value INTEGER NOT NULL);
            ''')
            row = db.execute("SELECT value FROM meta WHERE name='scope'").fetchone()
            if row and row[0] != 'SYNTHETIC_ONLY':
                raise ValueError('INVALID_STATE_SCOPE')
            db.execute("INSERT OR IGNORE INTO meta VALUES('scope','SYNTHETIC_ONLY')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def principal(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
            raise Rejected(401, 'AUTH_REQUIRED')
        key = authorization[7:]
        if len(key) < 32 or len(key) > 512:
            raise Rejected(401, 'AUTH_REQUIRED')
        digest = hashlib.sha256(key.encode()).hexdigest()
        for expected, principal in self.principals.items():
            if hmac.compare_digest(digest, expected):
                return principal
        raise Rejected(401, 'AUTH_REQUIRED')

    def session(self, db, account, now):
        row = db.execute('SELECT issued,expires,generation FROM sessions WHERE account=?', (account,)).fetchone()
        if not row or not row[0] <= now < row[1] or row[1] - row[0] != TTL:
            raise Rejected(401, 'LOGIN_REQUIRED')
        return {'account': account, 'issued': row[0], 'expires': row[1], 'generation': row[2]}

    def call(self, authorization, route, body):
        p = self.principal(authorization)
        if not isinstance(body, dict):
            raise Rejected(400, 'INVALID_BODY')
        allowed = {'/login': set(), '/resume': set(), '/logout': set(),
                   '/read': set(), '/submit': {'request_id', 'delta'},
                   '/status': {'request_id'}, '/drain': set()}
        if route not in allowed:
            raise Rejected(404, 'UNKNOWN_OPERATION')
        if set(body) != allowed[route]:
            raise Rejected(400, 'INVALID_FIELDS')
        if p['kind'] == 'action' and route in ('/login', '/logout'):
            raise Rejected(403, 'CHAT_LOGIN_REQUIRED')
        if route in ('/submit', '/status'):
            rid = body['request_id']
            if not isinstance(rid, str) or not 1 <= len(rid) <= 128:
                raise Rejected(400, 'INVALID_REQUEST_ID')
        if route == '/submit' and (type(body['delta']) is not int or not -1000 <= body['delta'] <= 1000):
            raise Rejected(400, 'INVALID_DELTA')
        account = p['account']
        # One authority owns the whole synthetic commit. No lease can expire
        # between validation and commit, and readers see a committed snapshot.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now = int(self.clock())  # checked after obtaining the writer lock
            if route == '/login':
                try:
                    return self.session(db, account, now)
                except Rejected:
                    db.execute("UPDATE jobs SET state='CANCELLED' WHERE account=? AND state='QUEUED'", (account,))
                    db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',
                               (account, now, now + TTL, secrets.token_hex(16)))
                    return self.session(db, account, now)
            session = self.session(db, account, now)
            if route == '/resume':
                return session
            if route == '/logout':
                db.execute('DELETE FROM sessions WHERE account=?', (account,))
                db.execute("UPDATE jobs SET state='CANCELLED' WHERE account=? AND state='QUEUED'", (account,))
                return {'logged_out': True}
            if route == '/submit':
                old = db.execute('SELECT delta FROM jobs WHERE account=? AND request_id=?',
                                 (account, rid)).fetchone()
                if old and old[0] != body['delta']:
                    raise Rejected(409, 'REQUEST_ID_COLLISION')
                db.execute('INSERT OR IGNORE INTO jobs(account,request_id,delta,generation) VALUES(?,?,?,?)',
                           (account, rid, body['delta'], session['generation']))
            if route == '/drain':
                db.execute('INSERT OR IGNORE INTO counters VALUES(?,0)', (account,))
                for seq, delta in db.execute("SELECT seq,delta FROM jobs WHERE account=? AND generation=? AND state='QUEUED' ORDER BY seq", (account, session['generation'])).fetchall():
                    db.execute('UPDATE counters SET value=value+? WHERE account=?', (delta, account))
                    value = db.execute('SELECT value FROM counters WHERE account=?', (account,)).fetchone()[0]
                    db.execute("UPDATE jobs SET state='DONE',result=? WHERE seq=?", (value, seq))
            if route in ('/submit', '/status'):
                row = db.execute('SELECT seq,state,result FROM jobs WHERE account=? AND request_id=?', (account, rid)).fetchone()
                if not row:
                    raise Rejected(404, 'REQUEST_NOT_FOUND')
                return dict(request_id=rid, sequence=row[0], state=row[1], result=row[2])
            row = db.execute('SELECT value FROM counters WHERE account=?', (account,)).fetchone()
            pending = db.execute("SELECT count(*) FROM jobs WHERE account=? AND state='QUEUED'", (account,)).fetchone()[0]
            return dict(account=account, value=row[0] if row else 0, pending=pending)


def handler(entry):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # never log credentials or request bodies

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def do_POST(self):
            try:
                if self.headers.get('Transfer-Encoding'):
                    raise Rejected(400, 'UNSUPPORTED_TRANSFER')
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise Rejected(400, 'INVALID_LENGTH')
                length = int(lengths[0])
                if length > MAX_BODY:
                    raise Rejected(413, 'BODY_TOO_LARGE')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise Rejected(400, 'INCOMPLETE_BODY')
                body = json.loads(raw)
                result = entry.call(self.headers.get('Authorization'), self.path, body)
                status, payload = 200, {'scope': 'SYNTHETIC_ONLY', 'result': result}
            except Rejected as e:
                status, payload = e.status, {'error': e.code}
            except (ValueError, UnicodeError):
                status, payload = 400, {'error': 'INVALID_JSON'}
            except sqlite3.OperationalError:
                status, payload = 503, {'error': 'RETRY_SAME_REQUEST_ID'}
            except Exception:
                status, payload = 500, {'error': 'INTERNAL_ERROR'}
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True, help='Synthetic state only; never a formal family DB')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    os.umask(0o077)
    principals = json.loads(os.environ['FAMILY_PROBE_PRINCIPALS_JSON'])
    entry = Entry(args.state, principals)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(entry))
    print(json.dumps({'port': server.server_port, 'scope': 'SYNTHETIC_ONLY'}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
