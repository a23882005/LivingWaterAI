import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from github_json_outbox import *

class Backend:
    def __init__(self):
        self.sha = 0
        self.doc = {'schema': SCHEMA, 'events': {}}
        self.fail = None
    def read(self):
        return self.sha, copy.deepcopy(self.doc)
    def compare_and_swap(self, sha, doc):
        if self.fail == 'before': raise OSError()
        if sha != self.sha: raise RuntimeError('CAS_CONFLICT')
        self.doc = copy.deepcopy(doc)
        self.sha += 1
        if self.fail == 'after': raise OSError()

K = event_key('synthetic-public-signal')

def test_success_and_restart():
    b=Backend(); sent=[]
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='SENT_SMTP_ACCEPTED'
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='ALREADY_SENT'
    assert sent==[1]

def test_unknown_reservation_never_sends():
    b=Backend(); b.fail='after'; sent=[]
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='STATE_UNKNOWN_NO_SEND'
    b.fail=None
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    assert sent==[]

def test_smtp_uncertainty_never_retries():
    b=Backend(); sent=[]
    def send():
        sent.append(1); raise OSError()
    assert deliver_once(GithubJsonOutbox(b),K,send)=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    assert deliver_once(GithubJsonOutbox(b),K,send)=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    assert sent==[1]

def test_sent_write_failure_stays_pending():
    b=Backend(); sent=[]
    def send():
        sent.append(1); b.fail='before'
    assert deliver_once(GithubJsonOutbox(b),K,send)=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    b.fail=None
    assert deliver_once(GithubJsonOutbox(b),K,send)=='DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    assert sent==[1]

def test_interleaved_writers_only_one_reserves():
    b=Backend(); original=b.compare_and_swap; other=GithubJsonOutbox(b); winner=[]
    def race(sha,doc):
        b.compare_and_swap=original
        winner.append(other.reserve(K))
        original(sha,doc)
    b.compare_and_swap=race
    sent=[]
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='STATE_UNKNOWN_NO_SEND'
    assert winner==['RESERVED'] and sent==[]

def test_private_fields_rejected():
    b=Backend(); b.doc['account']='secret'; sent=[]
    assert deliver_once(GithubJsonOutbox(b),K,lambda:sent.append(1))=='STATE_UNKNOWN_NO_SEND'
    try: validate({'schema':SCHEMA,'events':{'VT':'SENT'}})
    except ValueError: pass
    else: raise AssertionError('private key accepted')
    assert sent==[]

def test_http_adapter_uses_expected_sha_and_explicit_branch():
    import base64, json
    b=GithubContentsBackend(token='synthetic',repository='owner/repo',branch='test-branch',path='state/test.json')
    calls=[]
    b._request=lambda method,url,payload=None: calls.append((method,url,payload)) or {}
    doc={'schema':SCHEMA,'events':{K:'PENDING'}}
    b.compare_and_swap('expected-old-sha',doc)
    method,url,payload=calls[0]
    assert method=='PUT' and payload['sha']=='expected-old-sha' and payload['branch']=='test-branch'
    assert json.loads(base64.b64decode(payload['content']))==doc

def test_http_adapter_refuses_blind_create():
    b=GithubContentsBackend(token='synthetic',repository='owner/repo',branch='test',path='state/test.json')
    try: b.compare_and_swap('',{'schema':SCHEMA,'events':{}})
    except ValueError: pass
    else: raise AssertionError('blind create permitted')
