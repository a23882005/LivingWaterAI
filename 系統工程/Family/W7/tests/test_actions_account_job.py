import json
import pytest
from test_accounts import env, activate
from actions_account_job import JobContext, execute

A = JobContext('connection_00000001', 'conversation_000001')
B = JobContext('connection_00000001', 'conversation_000002')
C = JobContext('connection_00000002', 'conversation_000001')

def job(m, ctx=A, operation='login', request_id='request_000000001', **values):
    if operation == 'login' and not values:
        values = dict(user='mou', password='secret-mou')
    return execute(m, ctx, dict(operation=operation, request_id=request_id, **values))

def test_new_chat_and_connection_require_login(env):
    m, make, now, _, _ = env
    activate(m)
    one = job(m)
    token = one.private_response['token']
    assert one.receipt['status'] == 'AUTHENTICATED'
    assert job(make(), operation='session', token=token).receipt['status'] == 'AUTHENTICATED'
    for ctx in (B, C):
        assert job(make(), ctx, 'session', token=token).receipt['status'] == 'AUTH_REQUIRED'
        assert job(make(), ctx).receipt['status'] == 'AUTHENTICATED'
    now[0] += 14400
    assert job(make(), operation='session', token=token).receipt['status'] == 'AUTH_REQUIRED'

def test_retry_and_logout(env):
    m, make, _, _, _ = env
    activate(m)
    one = job(m)
    assert job(make()).private_response == one.private_response
    token = one.private_response['token']
    assert job(m, operation='logout', token=token).receipt['status'] == 'LOGGED_OUT'
    assert job(make()).receipt['status'] == 'AUTH_REQUIRED'

def test_initial_password_change(env):
    m, _, _, _, _ = env
    initial = job(m, user='mou', password='initial-mou')
    assert initial.receipt['status'] == 'PASSWORD_CHANGE_REQUIRED'
    token = initial.private_response['token']
    assert job(m, operation='session', token=token).receipt['status'] == 'AUTH_REQUIRED'
    result = job(m, operation='change_password', token=token,
                 current_password='initial-mou', new_password='secret-mou')
    assert result.receipt['status'] == 'LOGIN_REQUIRED'
    assert job(m, request_id='request_000000002').receipt['status'] == 'AUTHENTICATED'

@pytest.mark.parametrize('extra', ['conversation', 'scope', 'file_id', 'sql'])
def test_untrusted_routing_fields_rejected(env, extra):
    m, _, _, _, _ = env
    result = job(m, user='mou', password='secret-mou', **{extra: 'injected'})
    assert result.receipt == {'status': 'REQUEST_REJECTED'}

def test_no_secret_output(env, capsys):
    m, _, _, _, _ = env
    activate(m)
    result = job(m)
    assert json.dumps(result.receipt) == '{"status": "AUTHENTICATED"}'
    assert 'secret-mou' not in repr(result)
    assert result.private_response['token'] not in repr(result)
    assert capsys.readouterr() == ('', '')

def test_provider_errors_scrubbed():
    class Broken:
        def login(self, *args):
            raise RuntimeError('secret-provider-token')
    result = job(Broken())
    assert result.receipt == {'status': 'SERVICE_RETRY'}
    assert result.private_response == {}

def test_invalid_context_rejected(env):
    m, _, _, _, _ = env
    assert job(m, JobContext('short', 'short')).receipt['status'] == 'REQUEST_REJECTED'
