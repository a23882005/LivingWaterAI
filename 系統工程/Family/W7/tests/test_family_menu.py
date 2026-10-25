import importlib.util
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from family_menu import FamilyMenu, render_menu, route, complete_work, report_handlers


class Auth:
    def __init__(self): self.active = False; self.login_user = 'JO'
    def require_login(self):
        if not self.active: raise PermissionError('LOGIN')
        return self.login_user
    def login(self, user, password):
        if (user not in {'JO', 'mou'} or password != 'synthetic'): raise PermissionError('LOGIN')
        self.login_user = user
        self.active = True
    def logout(self): self.active = False; return {'status': 'LOGGED_OUT'}


def make_menu(auth=None, *, project_name='Joseph', login_account='JO', handlers=None):
    return FamilyMenu(auth or Auth(), project_name=project_name,
                      login_account=login_account, handlers=handlers)


def test_welcome_prompts_without_business_call():
    ui = make_menu()
    assert ui.welcome()['status'] == 'LOGIN_REQUIRED'
    assert '請輸入您的密碼' in ui.welcome()['text']


@pytest.mark.parametrize(('project_name', 'login_account'), [('Joseph', 'JO'), ('MOU', 'mou')])
def test_project_identity_and_account_are_configuration(login_account, project_name):
    auth = Auth()
    ui = make_menu(auth, project_name=project_name, login_account=login_account)
    assert project_name in ui.welcome()['text']
    result = ui.login('synthetic')
    assert auth.login_user == login_account
    assert f'{project_name} 的活水 AI' in result['menu']


def test_private_intent_resumes_after_login_and_full_menu_follows():
    seen = []
    ui = make_menu(handlers={'deployment_pace': lambda p: seen.append(p) or 'DONE'})
    assert ui.select('04', payload={'value': 7})['status'] == 'LOGIN_REQUIRED'
    assert seen == []
    result = ui.login('synthetic')
    assert result['result'] == 'DONE' and seen == [{'value': 7}]
    assert result['menu'] == render_menu('Joseph') and ui.pending is None


def test_macro_direct_before_login_without_handler_or_database():
    result = make_menu().select(7)
    assert result['result']['url'] == 'https://happihelp.com/'
    assert result['menu'] == render_menu('Joseph')


def test_menu_mapping_and_direct_request_completion():
    assert [route(i)['operation'] for i in (4,5,6,11,12,13,14)] == [
        'deployment_pace','research_candidates','new_funding','record_event',
        'previous_report','generate_report','account']
    assert len([l for l in render_menu('Joseph').splitlines() if '｜' in l]) == 14
    assert complete_work('direct request', 'Joseph')['menu'] == render_menu('Joseph')


@pytest.mark.parametrize('selection', [True, 0, 15, '05.0', 5.0, '../02'])
def test_invalid_selection(selection):
    with pytest.raises(ValueError): route(selection)


def test_research_private_screenshot_scope_requires_auth():
    ui = make_menu(handlers={'research_candidates': lambda p:'RESEARCH'})
    assert ui.select(5)['result'] == 'RESEARCH'
    assert ui.select(5, payload={'use_private_portfolio':True})['status'] == 'LOGIN_REQUIRED'


def test_unbound_request_is_retained():
    auth = Auth(); auth.active = True
    ui = make_menu(auth)
    assert ui.select(13)['status'] == 'HANDLER_PENDING'
    assert ui.pending == (13, {})


def test_logout_then_private_request_reauthenticates():
    auth = Auth(); auth.active = True
    ui = make_menu(auth)
    assert ui.select(14, payload={'action':'logout'})['menu'] == render_menu('Joseph')
    assert ui.select(2)['status'] == 'LOGIN_REQUIRED'


def test_archive_binding_requires_renderer_qa():
    auth = Auth(); auth.active = True
    handlers = report_handlers(auth, object(), lambda p: {'qa_passed':False})
    with pytest.raises(ValueError, match='REPORT_QA_REQUIRED'):
        handlers['generate_report']({})


def test_swapped_04_05_routes_and_privacy_are_exact():
    assert route('04') == {
        'number':4, 'label':'評估現在各標的物投入速度',
        'operation':'deployment_pace','rule':'04_買賣與持倉調整.md','private':True}
    assert route('05') == {
        'number':5, 'label':'尋找新標的物',
        'operation':'research_candidates','rule':'04_尋找新標的物.md','private':False}
    menu = render_menu('Arthur')
    assert menu.index('04｜評估現在各標的物投入速度') < menu.index('05｜尋找新標的物')
    assert '選03/05' in menu


def test_swapped_04_deployment_still_requires_auth_and_05_public_research():
    ui = make_menu(handlers={'deployment_pace': lambda p:'DEPLOY', 'research_candidates':lambda p:'RESEARCH'})
    assert ui.select(4)['status'] == 'LOGIN_REQUIRED'
    assert ui.select(5)['result'] == 'RESEARCH'


@pytest.mark.parametrize('foreign', ['MOU', 'AR', 'LI'])
def test_w8_foreign_login_never_reads_joseph_private_handler(foreign):
    auth = Auth()
    auth.active, auth.login_user = True, foreign
    touched = []
    ui = make_menu(auth, handlers={'read_portfolio': lambda p:touched.append(p) or 'LEAK'})
    assert ui.welcome()['status'] == 'LOGIN_REQUIRED'
    attempt = ui.select(2)
    assert attempt['status'] == 'LOGIN_REQUIRED'
    assert attempt['pending_operation'] == 'read_portfolio'
    assert touched == []
    assert ui.select(7)['result']['url'] == 'https://happihelp.com/'


def test_w8_cross_project_logout_rejected_without_revoking_other_account():
    auth = Auth()
    auth.active, auth.login_user = True, 'AR'
    ui = make_menu(auth, project_name='Joseph', login_account='JO')
    result = ui.select(14, payload={'action':'logout'})
    assert result['status'] == 'LOGIN_REQUIRED'
    assert auth.active is True and auth.login_user == 'AR'


def test_w8_valid_project_login_and_own_handler_execution():
    auth = Auth()
    ui = make_menu(auth, project_name='Arthur', login_account='AR',
                   handlers={'read_portfolio': lambda _: {'owned_by': 'AR'}})
    assert ui.select(2)['status'] == 'LOGIN_REQUIRED'
    auth.active, auth.login_user = True, 'AR'
    result = ui.select(2)
    assert result['status'] == 'COMPLETED'
    assert result['result']['owned_by'] == 'AR'
    assert result['menu'] == render_menu('Arthur')


def test_w8_real_input_missing_does_not_claim_completed_execution():
    auth = Auth()
    auth.active = True
    auth.login_user = 'JO'
    ui = make_menu(auth, handlers={
        'deployment_pace': lambda _: {
            'status': 'DATA_UNAVAILABLE',
            'code': 'OFFICIAL_ANALYSIS_INPUT_INCOMPLETE',
            'missing': ['final_target_allocation']}})
    got = ui.select('04')
    assert got['status'] == 'DATA_UNAVAILABLE'
    assert got['result']['missing'] == ['final_target_allocation']
    assert got['pending_operation'] == 'deployment_pace'
    assert got['menu'] == render_menu('Joseph')
