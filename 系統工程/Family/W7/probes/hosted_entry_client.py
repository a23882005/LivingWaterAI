"""Build ephemeral probe, verify real HTTPS, emit only safe summary evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path('build/family-b04-hosted')
PRIVATE = ROOT / 'private-keys.json'


def build():
    run = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    if not re.fullmatch(r'[0-9]+-[0-9]+', run):
        raise ValueError('INVALID_RUN')
    keys = {k: secrets.token_urlsafe(32) for k in ('chatA', 'actionA', 'chatB')}
    principals = {hashlib.sha256(v.encode()).hexdigest():
                  dict(account='synthetic-B' if k == 'chatB' else 'synthetic-A',
                       kind='action' if k == 'actionA' else 'chat') for k, v in keys.items()}
    template = Path(__file__).with_name('hosted_entry_probe.php').read_text()
    output = ROOT / 'public'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.php').write_text(template.replace('__PRINCIPALS_JSON__', json.dumps(principals))
                                    .replace('__RUN_ID__', run))
    PRIVATE.write_text(json.dumps({'run': run, 'keys': keys}))
    PRIVATE.chmod(0o600)


def verify():
    config = json.loads(PRIVATE.read_text())
    keys, run = config['keys'], config['run']
    base = (os.environ.get('SITE_BASE_URL') or 'https://www.happihelp.com').rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('HTTPS_SITE_REQUIRED')
    url = base + '/family-w7-probe-' + run + '/index.php?op='
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # bearer keys never follow an unverified redirect
    opener = urllib.request.build_opener(NoRedirect())
    checks = []
    def call(who, operation, body=None):
        request = urllib.request.Request(url + operation,
            data=json.dumps(body or {}).encode(), headers={
                'Authorization': 'Bearer ' + keys.get(who, 'invalid-key'),
                'Content-Type': 'application/json', 'Cache-Control': 'no-cache'})
        try:
            with opener.open(request, timeout=30) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.load(e)
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    check('unauthenticated_rejected', call('invalid', 'login')[0] == 401)
    check('action_cannot_start_login', call('actionA', 'login')[0] == 403)
    first = call('chatA', 'login')[1]['result']
    check('fixed_four_hours', first['expires'] - first['issued'] == 14400)
    check('new_https_connection_resumes', call('chatA', 'resume')[1]['result'] == first)
    check('relogin_does_not_extend', call('chatA', 'login')[1]['result'] == first)
    call('chatB', 'login')
    check('account_field_rejected', call('chatA', 'read', {'account': 'synthetic-B'})[0] == 400)
    check('action_enqueue', call('actionA', 'submit', {'request_id': 'first', 'delta': 7})[0] == 200)
    check('cross_account_status_rejected', call('chatB', 'status', {'request_id': 'first'})[0] == 404)
    check('collision_rejected', call('chatA', 'submit', {'request_id': 'first', 'delta': 9})[0] == 409)
    check('chat_drains_action', call('chatA', 'drain')[1]['result']['value'] == 7)
    check('retry_returns_done', call('actionA', 'submit', {'request_id': 'first', 'delta': 7})[1]['result']['state'] == 'DONE')
    check('retry_not_applied_twice', call('actionA', 'drain')[1]['result']['value'] == 7)
    def submit(n):
        return call('chatA' if n % 2 else 'actionA', 'submit', {'request_id': 'parallel-' + str(n), 'delta': 1})
    with ThreadPoolExecutor(max_workers=3) as pool:
        result = list(pool.map(submit, list(range(8)) * 2))
    check('parallel_requests_accepted', all(r[0] == 200 for r in result))
    check('parallel_no_lost_or_duplicate_updates', call('actionA', 'drain')[1]['result']['value'] == 15)
    check('other_account_unchanged', call('chatB', 'read')[1]['result']['value'] == 0)
    call('chatA', 'submit', {'request_id': 'cancel', 'delta': 50})
    call('chatA', 'logout')
    check('logout_revokes_action_access', call('actionA', 'read')[0] == 401)
    call('chatA', 'login')
    check('logout_cancels_queued_work', call('chatA', 'status', {'request_id': 'cancel'})[1]['result']['state'] == 'CANCELLED')
    check('new_session_preserves_committed_data', call('chatA', 'drain')[1]['result']['value'] == 15)
    return {'schema': 'Family-B04-hosted-proof-v1', 'scope': 'SYNTHETIC_ONLY_HTTPS',
            'status': 'PASS', 'checks': checks, 'count': len(checks), 'run': run}


if __name__ == '__main__':
    os.umask(0o077)
    if sys.argv[1] == 'build':
        build()
    elif sys.argv[1] == 'verify':
        try:
            report = verify()
        except Exception as e:
            report = {'status': 'FAILED', 'error_type': type(e).__name__}
            # Only our static assertion labels are safe to return.
            if isinstance(e, AssertionError):
                report['check'] = str(e)
        (ROOT / 'hosted-proof.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        if report['status'] != 'PASS':
            raise SystemExit(1)
