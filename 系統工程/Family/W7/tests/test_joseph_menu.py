import importlib.util
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from joseph_menu import JosephMenu, render_menu, route, complete_work, report_handlers


class Auth:
    def __init__(self): self.active = False
    def require_login(self):
        if not self.active: raise PermissionError('LOGIN')
        return 'JO'
    def login(self, user, password):
        if (user, password) != ('JO', 'synthetic'): raise PermissionError('LOGIN')
        self.active = True
    def logout(self): self.active = False; return {'status': 'LOGGED_OUT'}


def test_welcome_prompts_without_business_call():
    ui = JosephMenu(Auth())
    assert ui.welcome()['status'] == 'LOGIN_REQUIRED'
    assert '請輸入您的密碼' in ui.welcome()['text']


def test_private_intent_resumes_after_login_and_full_menu_follows():
    seen = []
    ui = JosephMenu(Auth(), handlers={'deployment_pace': lambda p: seen.append(p) or 'DONE'})
    assert ui.select('05', payload={'value': 7})['status'] == 'LOGIN_REQUIRED'
    assert seen == []
    result = ui.login('synthetic')
    assert result['result'] == 'DONE' and seen == [{'value': 7}]
    assert result['menu'] == render_menu() and ui.pending is None


def test_macro_direct_before_login_without_handler_or_database():
    result = JosephMenu(Auth()).select(7)
    assert result['result']['url'] == 'https://happihelp.com/'
    assert result['menu'] == render_menu()


def test_menu_mapping_and_direct_request_completion():
    assert [route(i)['operation'] for i in (4,5,6,11,12,13,14)] == [
        'research_candidates','deployment_pace','new_funding','record_event',
        'previous_report','generate_report','account']
    assert len([l for l in render_menu().splitlines() if '｜' in l]) == 14
    assert complete_work('direct request')['menu'] == render_menu()


@pytest.mark.parametrize('selection', [True, 0, 15, '05.0', 5.0, '../02'])
def test_invalid_selection(selection):
    with pytest.raises(ValueError): route(selection)


def test_research_private_screenshot_scope_requires_auth():
    ui = JosephMenu(Auth(), handlers={'research_candidates': lambda p:'RESEARCH'})
    assert ui.select(4)['result'] == 'RESEARCH'
    assert ui.select(4, payload={'use_private_portfolio':True})['status'] == 'LOGIN_REQUIRED'


def test_unbound_request_is_retained():
    auth = Auth(); auth.active = True
    ui = JosephMenu(auth)
    assert ui.select(13)['status'] == 'HANDLER_PENDING'
    assert ui.pending == (13, {})


def test_logout_then_private_request_reauthenticates():
    auth = Auth(); auth.active = True
    ui = JosephMenu(auth)
    assert ui.select(14, payload={'action':'logout'})['menu'] == render_menu()
    assert ui.select(2)['status'] == 'LOGIN_REQUIRED'


def test_archive_binding_requires_renderer_qa():
    auth = Auth(); auth.active = True
    handlers = report_handlers(auth, object(), lambda p: {'qa_passed':False})
    with pytest.raises(ValueError, match='REPORT_QA_REQUIRED'):
        handlers['generate_report']({})
