"""Account job core for an Actions worker; transport and writer admission are external.

Call only after decrypting/authenticating a private request. Never pass plaintext
passwords via workflow_dispatch, issues, repository files or artifacts. The
adapter does not establish that admission or provision a Drive writer. A context
is assigned by the trusted ingress, not inferred from model text or project name.
"""
from dataclasses import dataclass
import hashlib
import json
import re


@dataclass(frozen=True, repr=False)
class JobContext:
    connection: str
    conversation: str

    def scope(self):
        for value in (self.connection, self.conversation):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value):
                raise ValueError('INVALID_JOB_CONTEXT')
        raw = json.dumps([self.connection, self.conversation], separators=(',', ':'))
        return 'chat-' + hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True, repr=False)
class JobResult:
    # receipt is intentionally free of credentials and personal account names.
    receipt: dict
    # Private response: encrypt to the requester; never upload as an artifact.
    private_response: dict


FIELDS = {
    'login': {'user', 'password'},
    'session': {'token'},
    'logout': {'token'},
    'change_password': {'token', 'current_password', 'new_password'},
}


def execute(manager, context, request):
    """Use existing AccountManager/B06 semantics, with conversation-scoped login.

No print, filesystem writes, network/Drive setup or business-data calls. A fresh
manager may be supplied per job with the same private key and persistent store.
Errors are scrubbed; worker retries must retain context and request_id.
"""
    operation = 'invalid'
    try:
        if type(context) is not JobContext or not isinstance(request, dict):
            raise ValueError()
        scope = context.scope()
        operation = request.get('operation')
        if not isinstance(operation, str) or operation not in FIELDS:
            raise ValueError()
        if set(request) != {'operation', 'request_id'} | FIELDS[operation]:
            raise ValueError()
        rid = request['request_id']
        if not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', rid):
            raise ValueError()
        # Avoid collisions across independent conversations and operation types.
        key = hashlib.sha256(json.dumps([scope, operation, rid]).encode()).hexdigest()
        if operation == 'login':
            response = manager.login(request['user'], request['password'], scope, key)
            state = 'PASSWORD_CHANGE_REQUIRED' if response['must_change'] else 'AUTHENTICATED'
        elif operation == 'session':
            principal = manager.authenticate(request['token'], scope)
            response = {'user_id': principal.subject.removeprefix('account:'),
                        'expires_at': principal.expires_at}
            state = 'AUTHENTICATED'
        elif operation == 'logout':
            response = manager.logout(request['token'], scope, key)
            state = 'LOGGED_OUT'
        else:
            response = manager.change_password(request['token'], scope,
                request['current_password'], request['new_password'], key)
            if response.get('error'):
                return JobResult({'status': 'AUTH_REJECTED'}, {})
            state = 'LOGIN_REQUIRED'
        return JobResult({'status': state}, response)
    except PermissionError:
        return JobResult({'status': 'AUTH_REQUIRED'}, {})
    except (ValueError, TypeError, KeyError):
        return JobResult({'status': 'REQUEST_REJECTED'}, {})
    except Exception:
        # Provider exceptions may contain credential-bearing response bodies.
        return JobResult({'status': 'SERVICE_RETRY'}, {})
