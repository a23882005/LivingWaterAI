"""Public non-sensitive JSON outbox protocol, no HTTP/SMTP/credentials.
Backend contract: read() -> (GitHub content SHA, decoded document),
compare_and_swap(expected_sha, document) -> None or raises on *any* failure.
A transport MUST use Contents API PUT sha=expected_sha, not blind overwrite.
SHA/permission/uncertain failures abort sending. All writes use this protocol.
"""
import copy
import hashlib
import re

SCHEMA = 'PUBLIC_NOTICE_STATE_V1'
HEX = re.compile(r'^[0-9a-f]{64}$')


def validate(doc):
    if not isinstance(doc, dict) or set(doc) != {'schema', 'events'} or doc['schema'] != SCHEMA:
        raise ValueError('INVALID_PUBLIC_STATE')
    if not isinstance(doc['events'], dict) or len(doc['events']) > 100000:
        raise ValueError('INVALID_EVENTS')
    for key, value in doc['events'].items():
        if not isinstance(key, str) or not HEX.fullmatch(key) or value not in ('PENDING', 'SENT'):
            raise ValueError('PUBLIC_STATE_FIELDS_FORBIDDEN')
    return doc


def event_key(public_signal_id):
    # Input must identify a PUBLIC market signal, never account/holdings context.
    if not isinstance(public_signal_id, str) or not public_signal_id:
        raise ValueError('SIGNAL_ID_REQUIRED')
    return hashlib.sha256(public_signal_id.encode()).hexdigest()


class GithubJsonOutbox:
    def __init__(self, backend):
        self.backend = backend

    def reserve(self, key):
        if not HEX.fullmatch(key):
            raise ValueError('INVALID_KEY')
        sha, doc = self.backend.read()
        validate(doc)
        state = doc['events'].get(key)
        if state:
            return state
        candidate = copy.deepcopy(doc)
        candidate['events'][key] = 'PENDING'
        # No retry here. Only THIS successful compare-and-swap grants ownership.
        self.backend.compare_and_swap(sha, candidate)
        _, confirmed = self.backend.read()
        validate(confirmed)
        if confirmed['events'].get(key) != 'PENDING':
            raise RuntimeError('RESERVATION_READBACK_FAILED')
        return 'RESERVED'

    def mark_sent(self, key):
        sha, doc = self.backend.read()
        validate(doc)
        if doc['events'].get(key) != 'PENDING':
            raise RuntimeError('STATE_CONFLICT')
        candidate = copy.deepcopy(doc)
        candidate['events'][key] = 'SENT'
        self.backend.compare_and_swap(sha, candidate)
        _, confirmed = self.backend.read()
        validate(confirmed)
        if confirmed['events'].get(key) != 'SENT':
            raise RuntimeError('SENT_READBACK_FAILED')


def deliver_once(outbox, key, send):
    """send returns only after SMTP acceptance. No exactly-once claim.
    PENDING means no automatic resend; investigate Gmail before manual resolve.
    Never prune/reset keys automatically, or deduplication would be lost.
    """
    try:
        state = outbox.reserve(key)
    except Exception:
        return 'STATE_UNKNOWN_NO_SEND'
    if state == 'SENT':
        return 'ALREADY_SENT'
    if state == 'PENDING':
        return 'DELIVERY_UNKNOWN_RECONCILE_REQUIRED'
    try:
        send()
        outbox.mark_sent(key)
        return 'SENT_SMTP_ACCEPTED'
    except Exception:
        return 'DELIVERY_UNKNOWN_RECONCILE_REQUIRED'


class GithubContentsBackend:
    """Uses runner GITHUB_TOKEN; requires contents:write and allowed branch.
    Target JSON must be initialized separately to avoid unsafe create races.
    No requests run until called. Tokens, bodies and errors are never logged.
    """
    def __init__(self, *, token, repository, branch, path):
        import urllib.parse
        if not token or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('GITHUB_CONFIG_REQUIRED')
        if not branch or not path.endswith('.json') or path.startswith('/') or '..' in path.split('/'):
            raise ValueError('EXPLICIT_JSON_TARGET_REQUIRED')
        self.token=token
        self.branch=branch
        self.url='https://api.github.com/repos/'+repository+'/contents/'+urllib.parse.quote(path,safe='/')

    def _request(self, method, url, payload=None):
        import json
        import urllib.request
        data=None if payload is None else json.dumps(payload,allow_nan=False).encode()
        req=urllib.request.Request(url,data=data,method=method,headers={
            'Authorization':'Bearer '+self.token,
            'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28',
            'Content-Type':'application/json',
            'User-Agent':'v82-public-state'})
        with urllib.request.urlopen(req,timeout=30) as response:
            body=response.read(16*1024*1024+1)
        if len(body)>16*1024*1024:
            raise RuntimeError('RESPONSE_TOO_LARGE')
        return json.loads(body)

    def read(self):
        import base64
        import json
        import urllib.parse
        obj=self._request('GET',self.url+'?ref='+urllib.parse.quote(self.branch,safe=''))
        if obj.get('encoding')!='base64' or not obj.get('sha'):
            raise RuntimeError('GITHUB_CONTENT_ENCODING_INVALID')
        doc=json.loads(base64.b64decode(obj['content']))
        validate(doc)
        return obj['sha'],doc

    def compare_and_swap(self, expected_sha, document):
        import base64
        import json
        validate(document)
        if not expected_sha:
            raise ValueError('EXISTING_FILE_SHA_REQUIRED')
        encoded=base64.b64encode(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).decode()
        self._request('PUT',self.url,{'message':'state: update notification receipt',
            'branch':self.branch,'sha':expected_sha,'content':encoded})
