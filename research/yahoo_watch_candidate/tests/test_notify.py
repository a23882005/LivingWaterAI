import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from safe_notify import PrivateOutbox,send_notice

R=dict(schema='LW_MARKET_NOTICE_V1',event_id='e1',symbol='TEST',source='fixture',observed_at='2026-11-10T00:00:00Z',data_status='UNKNOWN',reason='FIXTURE')
class SMTP:
    count=0
    fail=False
    def __init__(self,*a,**k):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def login(self,*a):pass
    def send_message(self,msg):
        SMTP.count+=1
        if SMTP.fail:raise RuntimeError('secret text must not escape')
        return {}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'outbox.sqlite';SMTP.count=0;SMTP.fail=False
        self.box=PrivateOutbox(self.path,private_storage_verified=True)
    def tearDown(self):self.box.close();self.tmp.cleanup()
    def send(self,r=None):return send_notice(r or R,outbox=self.box,sender='sender@example.invalid',recipient='recipient@example.invalid',app_password='synthetic',smtp_factory=SMTP)
    def test_sent_dedup(self):
        self.assertEqual(self.send(),'SENT_SMTP_ACCEPTED');self.assertEqual(self.send(),'ALREADY_SENT');self.assertEqual(SMTP.count,1)
    def test_unknown_never_blind_resend(self):
        SMTP.fail=True
        self.assertEqual(self.send(),'DELIVERY_UNKNOWN_RECONCILE_REQUIRED');SMTP.fail=False
        self.assertEqual(self.send(),'DELIVERY_UNKNOWN_RECONCILE_REQUIRED');self.assertEqual(SMTP.count,1)
    def test_private_fields_rejected(self):
        with self.assertRaises(ValueError):self.send({**R,'holdings':100})
        self.assertEqual(SMTP.count,0)
    def test_conflicting_event(self):
        self.send()
        with self.assertRaises(ValueError):self.send({**R,'reason':'OTHER'})
    def test_no_stdout_or_stderr(self):
        stream=io.StringIO();SMTP.fail=True
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):self.send()
        self.assertEqual(stream.getvalue(),'')
    def test_persistence_across_restart(self):
        self.send();self.box.close();self.box=PrivateOutbox(self.path,private_storage_verified=True)
        self.assertEqual(self.send(),'ALREADY_SENT');self.assertEqual(SMTP.count,1)
    def test_no_storage_attestation(self):
        with self.assertRaises(ValueError):PrivateOutbox(Path(self.tmp.name)/'other.sqlite')
    def test_public_path(self):
        with self.assertRaises(ValueError):PrivateOutbox(Path(self.tmp.name)/'public_html'/'state',private_storage_verified=True)
    def test_crash_after_sent_before_state(self):
        def broken(*a):raise OSError('write failed')
        self.box.mark_sent=broken
        self.assertEqual(self.send(),'DELIVERY_UNKNOWN_RECONCILE_REQUIRED')
        self.assertEqual(self.send(),'DELIVERY_UNKNOWN_RECONCILE_REQUIRED');self.assertEqual(SMTP.count,1)
