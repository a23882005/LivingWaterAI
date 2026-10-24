"""Joseph v1.13 menu, conversation-local login resume and result presentation.

Business handlers are explicitly supplied by the trusted entry. Selecting an
unbound operation preserves it for the same conversation. No investment rules.
"""
VERSION = '1.13'
GREETING = 'Joseph，您好 🌿 我能協助您查看持倉、檢視配置、閱讀總經與新聞，以及產生配置報告。'
LOGIN_PROMPT = '請輸入您的密碼，登入您個人的活水 AI 系統。'
MACRO_URL = 'https://happihelp.com/'
ITEMS = (
    ('🌱', '第一次建倉', 'first_allocation', '01_第一次建倉.md', True),
    ('📋', '查看我的資料與持倉', 'read_portfolio', None, True),
    ('🧭', '檢視與調整目標配置', 'adjust_target', '03_目標配置調整.md', True),
    ('🎇', '尋找新標的物', 'research_candidates', '04_尋找新標的物.md', False),
    ('⚖️', '評估現在各標的物投入速度', 'deployment_pace', '04_買賣與持倉調整.md', True),
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


def render_menu():
    lines = ['🌿 Joseph 的活水 AI', '您的家人版專屬投資AI', '']
    lines += [f'{icon} {i:02}｜{label}' for i, (icon, label, *_) in enumerate(ITEMS, 1)]
    lines += ['', '💬 輸入編號，或直接說需求，若選03/04 可直接提供目前配置截圖，更為方便']
    return '\n'.join(lines)


def complete_work(result):
    """For menu and direct requests: deliver result first, then the full menu."""
    return {'status': 'COMPLETED', 'result': result, 'menu': render_menu()}


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


class JosephMenu:
    def __init__(self, auth, *, handlers=None):
        self.auth = auth
        self.handlers = dict(handlers or {})
        self.pending = None

    def welcome(self):
        try:
            self.auth.require_login()
        except PermissionError:
            return {'status': 'LOGIN_REQUIRED', 'text': GREETING + '\n' + LOGIN_PROMPT}
        return {'status': 'READY', 'text': GREETING, 'menu': render_menu()}

    def login(self, password):
        self.auth.login('JO', password)
        if self.pending is not None:
            number, payload = self.pending
            return self.select(number, payload=payload)
        return {'status': 'READY', 'menu': render_menu()}

    def select(self, number, *, payload=None):
        choice = route(number)
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError('INVALID_MENU_PAYLOAD')
        if choice['operation'] == 'macro_link':
            self.pending = None
            return complete_work({'text': '請直接查看活水 AI 總經網站', 'url': MACRO_URL})
        if choice['operation'] == 'account' and payload.get('action') == 'logout':
            self.pending = None
            return complete_work(self.auth.logout())
        if choice['private'] or payload.get('use_private_portfolio'):
            try:
                self.auth.require_login()
            except PermissionError:
                self.pending = (choice['number'], dict(payload))
                return {'status': 'LOGIN_REQUIRED', 'text': LOGIN_PROMPT,
                        'pending_operation': choice['operation']}
        handler = self.handlers.get(choice['operation'])
        if handler is None:
            self.pending = (choice['number'], dict(payload))
            return {'status': 'HANDLER_PENDING', 'operation': choice['operation'],
                    'rule': choice['rule'], 'menu': render_menu()}
        # Never cache passwords or any authentication payload in pending state.
        self.pending = None
        result = handler(payload)
        return complete_work(result)
