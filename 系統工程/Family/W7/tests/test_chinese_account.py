import uuid
import pytest
from test_accounts import env, activate, login, a
from resource_headers import SUBJECT
from account_oauth import OAuthService, challenge, SCOPE


def test_chinese_manager_password_session_and_oauth(env):
    m, make, now, disk, root = env
    manager = activate(m, 'coach')
    name = '活水AI管理者'
    m.manage(manager['token'], 'family-connection', uuid.uuid4().hex,
             'create', name, password='initial-test-only', role='manager', until=2000)
    first = login(m, name, 'initial-test-only')
    assert first['must_change']
    m.change_password(first['token'], 'family-connection', 'initial-test-only',
                      'changed-test-only', uuid.uuid4().hex)
    active = login(make(), name, 'changed-test-only')
    principal = make().authenticate(active['token'], 'family-connection')
    assert principal.subject == 'account:' + name
    assert SUBJECT.fullmatch(principal.subject)
    oauth = OAuthService(make(), 'https://family.example/oauth',
                         'https://family.example/mcp',
                         {'test-client': ['https://client.example/callback']}, 'family-connection')
    oauth.migrate()
    verifier = 'v' * 43
    code = oauth.issue(active['token'], 'test-client', 'https://client.example/callback',
                       'https://family.example/mcp', SCOPE, 'S256', challenge(verifier))
    token = oauth.exchange(code, 'test-client', 'https://client.example/callback',
                           'https://family.example/mcp', verifier)
    assert oauth.authenticate(token['access_token']).subject == principal.subject


@pytest.mark.parametrize('name', ['', '活水 AI', '活水/AI', '活水:管理者',
                                  '活水\n', '活水\u200bAI', '活水\u202eAI', '水' * 81])
def test_reject_ambiguous_or_path_names(name):
    with pytest.raises(ValueError): a._name(name)
    assert not SUBJECT.fullmatch('account:' + name)


def test_existing_service_names_stay_ascii():
    assert SUBJECT.fullmatch('service:account-manager')
    assert not SUBJECT.fullmatch('service:活水AI管理者')
