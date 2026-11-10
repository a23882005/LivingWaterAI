"""Private durable outbox + SMTP boundary. No logs, CLI, credentials or schedule.
Caller must provide an access-verified persistent private filesystem. Ephemeral
GitHub runners/cache/artifacts do NOT satisfy that deployment requirement.
Uncertain sends require reconciliation, never blind automatic retries.
"""
import hashlib
import json
import os
from pathlib import Path
import smtplib
import sqlite3
import stat
from email.message import EmailMessage

FIELDS = {'schema','event_id','symbol','source','observed_at','bar_start_utc',
          'bar_end_utc','age_seconds','session','data_status','reason',
          'rule_sha256','snapshot_id','valid_until','monitor_status'}


def canonical(report):
    if not isinstance(report, dict) or set(report) - FIELDS:
        raise ValueError('UNAPPROVED_REPORT_FIELDS')
    if report.get('schema') != 'LW_MARKET_NOTICE_V1':
        raise ValueError('NOTICE_SCHEMA_REQUIRED')
    for k in ('event_id','symbol','source','observed_at','data_status','reason'):
        if not isinstance(report.get(k),str) or not report[k] or len(report[k]) > 256 or any(ord(c)<32 for c in report[k]):
            raise ValueError('NOTICE_FIELDS_INVALID')
    # Values are typed primitive metadata, not arbitrary embedded account objects.
    if any(not isinstance(v,(str,int,float,bool,type(None))) for v in report.values()):
        raise ValueError('NESTED_REPORT_DATA_FORBIDDEN')
    return json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class PrivateOutbox:
    def __init__(self, path, *, private_storage_verified=False):
        if not private_storage_verified:
            raise ValueError('PRIVATE_PERSISTENT_STORAGE_NOT_VERIFIED')
        path=Path(path)
        if any(part.lower() in {'public_html','www','htdocs'} for part in path.parts) or path.is_symlink():
            raise ValueError('PUBLIC_OR_SYMLINK_OUTBOX_FORBIDDEN')
        # Existing access is checked, not broadened or silently altered.
        if path.exists():
            if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError('OUTBOX_ACCESS_TOO_BROAD')
        else:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS outbox (event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL)')
        self.db.commit()

    def reserve(self,event_id,body):
        digest=hashlib.sha256(body.encode()).hexdigest()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            found=self.db.execute('SELECT digest,state FROM outbox WHERE event_id=?',(event_id,)).fetchone()
            if found:
                if found[0]!=digest: raise ValueError('EVENT_ID_PAYLOAD_CONFLICT')
                return found[1]
            self.db.execute('INSERT INTO outbox VALUES (?,?,?)',(event_id,digest,'PENDING'))
        return 'RESERVED'

    def mark_sent(self,event_id):
        with self.db:
            result=self.db.execute("UPDATE outbox SET state='SENT' WHERE event_id=? AND state='PENDING'",(event_id,))
            if result.rowcount!=1: raise ValueError('OUTBOX_STATE_CONFLICT')

    def close(self): self.db.close()


def send_notice(report,*,outbox,sender,recipient,app_password,smtp_factory=smtplib.SMTP_SSL):
    body=canonical(report)
    # Recipient and credentials come only from authorized private configuration.
    if not sender or not recipient or any(c in sender+recipient for c in '\r\n') or not app_password:
        raise ValueError('MAIL_CONFIGURATION_REQUIRED')
    state=outbox.reserve(report['event_id'],body)
    if state=='SENT': return 'ALREADY_SENT'
    if state=='PENDING': return 'DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    msg=EmailMessage()
    msg['From']=sender;msg['To']=recipient
    msg['Subject']='[V82-WATCH] Market observation (not a buy instruction)'
    msg['Message-ID']='<'+hashlib.sha256(report['event_id'].encode()).hexdigest()+'@v82-watch.invalid>'
    msg.set_content('唯讀市場觀察，非完整V82運算、買進建議或交易授權。\n'+body)
    try:
        with smtp_factory('smtp.gmail.com',465,timeout=30) as smtp:
            smtp.login(sender,app_password)
            refused=smtp.send_message(msg)
            if refused: return 'DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
        outbox.mark_sent(report['event_id'])
        return 'SENT_SMTP_ACCEPTED'
    except Exception:
        # Do not print SMTP exceptions; they may contain identities or message text.
        # PENDING is deliberately retained, including after a confirmed server send
        # followed by local persistence failure. No exactly-once claim is made.
        return 'DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
