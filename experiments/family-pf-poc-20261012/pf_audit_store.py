"""Experimental persistent, hash-chained authorization audit sink (synthetic tests only).

SQLite persists across process restart. Hashes detect unintentional/unsanctioned
edits without the signing key, but are NOT independent tamper-proof evidence.
Production needs external immutable log retention, access controls and monitoring.
"""
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone

class AuditIntegrityError(RuntimeError):
    pass

class AuditStore:
    def __init__(self, db_path, integrity_key, pseudonym_key=None):
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise ValueError("Dedicated audit integrity key must contain >=32 bytes")
        if pseudonym_key is not None and (not isinstance(pseudonym_key, bytes) or len(pseudonym_key) < 32 or pseudonym_key == integrity_key):
            raise ValueError('Independent pseudonym key must contain >=32 bytes and differ from audit key')
        self.pseudonym_key = pseudonym_key if pseudonym_key is not None else integrity_key
        self.key = integrity_key
        self.db_path = str(db_path)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audit_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_ref TEXT NOT NULL,
                request_id TEXT NOT NULL,
                prev_mac TEXT NOT NULL,
                mac TEXT NOT NULL
            )""")
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        return db
    def pseudonymize(self, verified_subject):
        if not isinstance(verified_subject, str) or not verified_subject:
            raise ValueError("Verified subject required")
        digest=hmac.new(self.pseudonym_key,("family-pf-subject-v1:"+verified_subject).encode("utf-8"),hashlib.sha256).hexdigest()
        return "sub_"+digest[:32]
    def append(self, event):
        allowed = {"action","decision","reason","actor_ref","request_id"}
        if not isinstance(event, dict) or set(event) != allowed:
            raise ValueError("Only fixed redacted audit fields are accepted")
        if event["decision"] not in ("ALLOW","DENY"):
            raise ValueError("Invalid decision")
        for field in allowed:
            val=event[field]
            if not isinstance(val,str) or not val or len(val)>128 or any(ord(c)<32 for c in val):
                raise ValueError("Invalid audit field")
        stamp=datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior=db.execute("SELECT seq,mac FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            seq=1 if prior is None else prior[0]+1
            prev="GENESIS" if prior is None else prior[1]
            record={"seq":seq,"occurred_at":stamp,**event,"prev_mac":prev}
            mac=hmac.new(self.key,json.dumps(record,sort_keys=True,separators=(",",":")).encode(),hashlib.sha256).hexdigest()
            db.execute("""INSERT INTO audit_events
                (seq,occurred_at,action,decision,reason,actor_ref,request_id,prev_mac,mac)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (seq,stamp,event["action"],event["decision"],event["reason"],
                event["actor_ref"],event["request_id"],prev,mac))
        return seq
    def verify(self, _connection=None):
        prev="GENESIS"
        expected_seq=1
        if _connection is None:
            with self._connect() as db:
                return self.verify(_connection=db)
        rows=_connection.execute("""SELECT seq,occurred_at,action,decision,reason,
                actor_ref,request_id,prev_mac,mac FROM audit_events ORDER BY seq""").fetchall()
        for seq,stamp,action,decision,reason,actor,request_id,previous,mac in rows:
            if seq!=expected_seq or previous!=prev:
                raise AuditIntegrityError("Sequence or chain continuity failed")
            record={"seq":seq,"occurred_at":stamp,"action":action,"decision":decision,
                    "reason":reason,"actor_ref":actor,"request_id":request_id,"prev_mac":previous}
            expected=hmac.new(self.key,json.dumps(record,sort_keys=True,separators=(",",":")).encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac,expected):
                raise AuditIntegrityError("Audit record integrity failed")
            expected_seq+=1
            prev=mac
        return len(rows)

    def export_anchor(self):
        """A snapshot to store outside the DB via an independent trusted channel."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count=self.verify(_connection=db)
            latest=db.execute("SELECT mac FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            return {"event_count":count,"last_mac":latest[0] if latest else "GENESIS"}

    def verify_anchor(self, anchor):
        """Detect record loss against previously exported external evidence."""
        if not isinstance(anchor,dict) or set(anchor)!={"event_count","last_mac"}:
            raise AuditIntegrityError("Untrusted anchor shape")
        current=self.export_anchor()
        if current!=anchor:
            raise AuditIntegrityError("Audit anchor mismatch")
        return True
