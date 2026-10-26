"""Family v1.14 menu, conversation-local login resume and result presentation.

Business handlers are explicitly supplied by the trusted entry. Selecting an
unbound operation preserves it for the same conversation. No investment rules.
"""
VERSION = '1.14'
LOGIN_PROMPT = '請輸入您的密碼，登入您個人的活水 AI 系統。'
MACRO_URL = 'https://happihelp.com/'
ITEMS = (
    ('🌱', '第一次建倉', 'first_allocation', '01_第一次建倉.md', True),
    ('📋', '查看我的資料與持倉', 'read_portfolio', None, True),
    ('🧭', '檢視與調整目標配置', 'adjust_target', '03_目標配置調整.md', True),
    ('⚖️', '評估現在各標的物投入速度', 'deployment_pace', '04_買賣與持倉調整.md', True),
    ('🎇', '尋找新標的物', 'research_candidates', '04_尋找新標的物.md', False),
    ('💰', '安排新增投資資金', 'new_funding', '05_新增資金安排.md', True),
    ('🌐', '查看目前總體經濟情況', 'macro_link', '07_總經網站.md', False),
    ('📰', '查看今日重大財經新聞', 'market_news', None, False),
    ('🔎', '查看我的投資標的相關新聞', 'holding_news', None, True),
    ('🌿', '更新生活狀況與投資需求', 'update_profile', None, True),
    ('📝', '記錄交易與資金變動', 'record_event', None, True),
    ('📑', '查看上次我的配置報告', 'previous_report', '12_查看配置報告.md', True),
    ('📑', '產生我的最新配置報告', 'generate_report', '11_產生配置報告.md', True),
    ('🔐', '帳號：登出／修改密碼', 'account', '14_帳號管理.md', True),
)


def render_menu(project_name):
    lines = [f'🌿 {project_name} 的活水 AI', '您的家人版專屬投資AI', '']
    lines += [f'{icon} {i:02}｜{label}' for i, (icon, label, *_) in enumerate(ITEMS, 1)]
    lines += ['', '💬 輸入編號，或直接說需求，若選03/05 可直接提供目前配置截圖，更為方便']
    return '\n'.join(lines)


def complete_work(result, project_name):
    """For menu and direct requests: deliver result first, then the full menu."""
    return {'status': 'COMPLETED', 'result': result, 'menu': render_menu(project_name)}


def route(number):
    if isinstance(number, bool) or not isinstance(number, (str, int)):
        raise ValueError('INVALID_MENU_SELECTION')
    text = str(number)
    if text not in {str(i) for i in range(1, 15)} | {f'{i:02}' for i in range(1, 15)}:
        raise ValueError('INVALID_MENU_SELECTION')
    index = int(text)
    _, label, operation, rule, private = ITEMS[index - 1]
    return dict(number=index, label=label, operation=operation, rule=rule, private=private)


def report_handlers(auth, store, renderer=None):
    """Bind menu 12/13 to W6 archive; renderer is the approved W6/QA entry."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'W6' / 'runtime' / 'report_archive.py'
    spec = importlib.util.spec_from_file_location('family_dated_report_archive', path)
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)

    def previous(payload):
        return archive.previous_report(store, auth, date=payload.get('date'))

    handlers = {'previous_report': previous}
    if renderer is not None:
        def generate(payload):
            auth.require_login()
            rendered = renderer(payload)
            if rendered.get('qa_passed') is not True:
                raise ValueError('REPORT_QA_REQUIRED')
            return archive.publish_report(store, auth, run_id=rendered['run_id'],
                artifacts=rendered['artifacts'], data_as_of=rendered['data_as_of'],
                analysis_version=rendered['analysis_version'])
        handlers['generate_report'] = generate
    return handlers


class FamilyMenu:
    def __init__(self, auth, *, project_name, login_account, handlers=None, completion_checks=None):
        self.auth = auth
        self.project_name = project_name
        self.login_account = login_account
        self.handlers = dict(handlers or {})
        # Trusted entry verifies the 01 current-holdings/cash/interview save receipt.
        # Long-term targets and Loop 2 deployment are separate menu workflows.
        self.completion_checks = dict(completion_checks or {})
        self.pending = None

    def _require_own_session(self):
        """An authenticated session must belong to this exact Family project."""
        actual = self.auth.require_login()
        if (not isinstance(actual, str)
            or actual.casefold() != self.login_account.casefold()):
            raise PermissionError('FAMILY_PROJECT_ACCOUNT_MISMATCH')
        return actual

    def welcome(self):
        try:
            self._require_own_session()
        except PermissionError:
            return {'status': 'LOGIN_REQUIRED',
                    'text': f'{self.project_name}，您好 🌿 我能協助您查看持倉、檢視配置、閱讀總經與新聞，以及產生配置報告。\n{LOGIN_PROMPT}'}
        return {'status': 'READY',
                'text': f'{self.project_name}，您好 🌿 我能協助您查看持倉、檢視配置、閱讀總經與新聞，以及產生配置報告。',
                'menu': render_menu(self.project_name)}

    def login(self, password):
        self.auth.login(self.login_account, password)
        self._require_own_session()
        if self.pending is not None:
            number, payload = self.pending
            return self.select(number, payload=payload)
        return {'status': 'READY', 'menu': render_menu(self.project_name)}

    def select(self, number, *, payload=None):
        choice = route(number)
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError('INVALID_MENU_PAYLOAD')
        if choice['operation'] == 'macro_link':
            self.pending = None
            return complete_work({'text': '請直接查看活水 AI 總經網站', 'url': MACRO_URL},
                                 self.project_name)
        if choice['private'] or payload.get('use_private_portfolio'):
            try:
                self._require_own_session()
            except PermissionError:
                self.pending = (choice['number'], dict(payload))
                return {'status': 'LOGIN_REQUIRED', 'text': LOGIN_PROMPT,
                        'pending_operation': choice['operation']}
        if choice['operation'] == 'account' and payload.get('action') == 'logout':
            self.pending = None
            return complete_work(self.auth.logout(), self.project_name)
        handler = self.handlers.get(choice['operation'])
        if handler is None:
            self.pending = (choice['number'], dict(payload))
            if choice['operation'] == 'first_allocation':
                return {'status': 'FIRST_ALLOCATION_ENGINE_NOT_CONNECTED',
                        'pending_operation': 'first_allocation', 'rule': choice['rule'],
                        'next_stage': 'CONNECT_TRUSTED_FIRST_ALLOCATION_HANDLER'}
            return {'status': 'HANDLER_PENDING', 'operation': choice['operation'],
                    'rule': choice['rule'], 'menu': render_menu(self.project_name)}
        # Never cache passwords or any authentication payload in pending state.
        self.pending = None
        try:
            result = handler(payload)
        except Exception:
            if choice['operation'] == 'first_allocation':
                self.pending = (choice['number'], dict(payload))
            raise
        if (choice['operation'] == 'deployment_pace'
            and isinstance(result, dict) and result.get('status') == 'DATA_UNAVAILABLE'):
            return {'status': 'DATA_UNAVAILABLE', 'result': result,
                    'pending_operation': 'deployment_pace',
                    'menu': render_menu(self.project_name)}
        # A locally rendered report is not a completed Drive publication.
        # The ChatGPT tool executor must upload/read back every artifact,
        # publish the manifest last and verify its remote bytes.
        if (choice['operation'] == 'generate_report'
            and isinstance(result, dict)
            and result.get('status') == 'STAGED_NOT_PERSISTED'):
            return {'status': 'REPORT_UPLOAD_REQUIRED', 'result': result,
                    'pending_operation': 'generate_report',
                    'menu': render_menu(self.project_name)}
        if (choice['operation'] == 'previous_report'
            and isinstance(result, dict)
            and result.get('status') == 'DRIVE_LOOKUP_REQUIRED'):
            return {'status': 'REPORT_LOOKUP_REQUIRED', 'result': result,
                    'pending_operation': 'previous_report',
                    'menu': render_menu(self.project_name)}
        # For ChatGPT one-shot execution, a locally written SQLite candidate
        # is not the authoritative Google Drive database. Never call it saved
        # until the original remote file was updated and read back.
        if (choice['operation'] in ('first_allocation','adjust_target',
                                    'new_funding','update_profile','record_event')
            and isinstance(result, dict)
            and result.get('status') in ('STAGED_NOT_PERSISTED',
                                          'READY_NOT_PERSISTED',
                                          'CONNECTOR_FILE_REFERENCE_REQUIRED')):
            return {'status':'DB_WRITEBACK_REQUIRED','result':result,
                    'pending_operation':choice['operation'],
                    'menu':render_menu(self.project_name)}
        if choice['operation'] == 'first_allocation':
            verifier = self.completion_checks.get('first_allocation')
            # The trusted verifier checks an actual first-allocation save/readback.
            # No target allocation or Loop 2 run is necessary for menu 01.
            if verifier is None or verifier(result) is not True:
                self.pending = (choice['number'], dict(payload))
                return {'status': 'FIRST_ALLOCATION_IN_PROGRESS',
                        'pending_operation': 'first_allocation', 'result': result,
                        'next_stage': 'VERIFY_CURRENT_HOLDINGS_CASH_AND_INTERVIEW_SAVE'}
        return complete_work(result, self.project_name)
