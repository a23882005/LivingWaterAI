"""Actual B07 -> B06 -> Drive test on approved synthetic TEMP only."""
import importlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from actions_drive_write_probe import Drive, TEST_ID, TEMP_FOLDER, BACKUP_FOLDER
from b06_drive_integration import initialize, clean, header
from drive_service_transport import GoogleDriveTransport, ServiceTransportError
from drive_resource_backend import DriveResourceBackend
a = importlib.import_module('帳號管理')
BUILD = Path('build/family-b07-oauth-live')
from account_oauth import OAuthService, challenge, SCOPE, OAuthError
from account_mcp import AccountMCP

class ServiceProbe(Drive):
    def __init__(self):
        self.transport = GoogleDriveTransport(*(os.environ[k] for k in
            ('FAMILY_DRIVE_CLIENT_ID','FAMILY_DRIVE_CLIENT_SECRET','FAMILY_DRIVE_REFRESH_TOKEN')))
    def call(self, *args, **kwargs):
        return self.transport.call(*args, **kwargs)

def main(mode):
    BUILD.mkdir(parents=True, exist_ok=True)
    report = {'schema':'Family-B07-oauth-live-v1', 'scope':'APPROVED_TEMP_SYNTHETIC_ONLY',
              'status':'FAIL', 'stage':'oauth'}
    try:
        d = ServiceProbe()
        if mode == 'cleanup':
            report['cleanup'] = clean(d)
        else:
            report['stage'] = 'prepare'
            report['prior_cleanup'] = clean(d)
            pointers = initialize(d)
            h = dict(header(), resource_key='accounts', policy_ref='accounts')
            backend = DriveResourceBackend(d, {TEST_ID:dict(parent_id=TEMP_FOLDER,
                journal_id=pointers['b06_journal'], journal_parent_id=TEMP_FOLDER,
                header_id=pointers['b06_header'], header_template=h)}, BACKUP_FOLDER)
            policy = {'accounts':{'read':['service:account-manager'],'update':['service:account-manager']}}
            def store(): return a.B06AccountStore({'accounts':h},policy,backend,BUILD/'locks')
            def seed(db):
                for statement in a.SCHEMA.split(';'):
                    if statement.strip() and not statement.strip().startswith('PRAGMA'):
                        db.execute(statement)
                a._insert(db,'synthetic_b07','synthetic-activation','member',int(time.time())+1800)
                return {'seeded':True}
            store().mutate('b07-seed','synthetic-b07-seed-v1',seed)
            key = secrets.token_bytes(32)
            manager = a.AccountManager(store(), key)
            report['stage'] = 'initial-login'
            initial = manager.login('synthetic_b07','synthetic-activation','synthetic-connection','b07-initial')
            if not initial['must_change']: raise RuntimeError('INITIAL_CHANGE_NOT_REQUIRED')
            report['stage'] = 'change-password'
            manager.change_password(initial['token'],'synthetic-connection','synthetic-activation',
                                    'synthetic-new-password','b07-change')
            report['stage'] = 'normal-login-and-resume'
            session = manager.login('synthetic_b07','synthetic-new-password','synthetic-connection','b07-login')
            fresh = a.AccountManager(store(),key)
            principal = fresh.authenticate(session['token'],'synthetic-connection')
            if principal.subject != 'account:synthetic_b07': raise RuntimeError('WRONG_SUBJECT')
            if not fresh.session_guard(principal): raise RuntimeError('GUARD_FAILED')
            report['fixed_four_hours'] = store().read(lambda db: all(
                row[0] == 14400 for row in db.execute('SELECT expires_at-issued_at FROM login_session')))
            report['stage'] = 'oauth-migration'
            def oauth():
                return OAuthService(a.AccountManager(store(),key),'https://synthetic.invalid/oauth',
                    'https://synthetic.invalid/mcp',{'synthetic-client':['https://synthetic.invalid/callback']},'synthetic-connection')
            service=oauth(); service.migrate()
            report['stage']='oauth-code-issue'
            verifier=secrets.token_urlsafe(48)
            code=service.issue(session['token'],'synthetic-client','https://synthetic.invalid/callback',
                'https://synthetic.invalid/mcp',SCOPE,'S256',challenge(verifier))
            report['stage']='oauth-code-exchange'
            started=time.monotonic()
            pair=oauth().exchange(code,'synthetic-client','https://synthetic.invalid/callback','https://synthetic.invalid/mcp',verifier)
            report['token_exchange_seconds']=round(time.monotonic()-started,3)
            report['stage']='mcp-fresh-instance'
            request=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'family_session','arguments':{}}}).encode()
            status,_,body=AccountMCP(oauth()).handle('POST',{'Content-Type':'application/json','Authorization':'Bearer '+pair['access_token']},request)
            if status!=200 or json.loads(body)['result']['structuredContent']['user_id']!='synthetic_b07':raise RuntimeError('MCP_IDENTITY')
            report['stage']='oauth-refresh'
            pair=oauth().refresh(pair['refresh_token'],'synthetic-client','https://synthetic.invalid/mcp')
            oauth_principal=oauth().authenticate(pair['access_token'])
            report['oauth_checks']=['durable_migration','pkce_code_exchange','fresh_service_mcp_identity','refresh']
            report['stage'] = 'logout'
            fresh.logout(session['token'],'synthetic-connection','b07-logout')
            if oauth().session_guard(oauth_principal):raise RuntimeError('OAUTH_LOGOUT_NOT_REVOKED')
            report['oauth_checks'].append('logout_revokes_oauth')
            if manager.session_guard(principal): raise RuntimeError('LOGOUT_NOT_REVOKED')
            report['checks'] = ['initial_change','password_change','login','fresh_manager_resume',
                                'b06_session_guard','fixed_four_hours','logout_revocation']
            report['stage'] = 'restore'
            report['cleanup'] = clean(d)
        report.update(status='PASS',stage='complete')
    except Exception as error:
        # Never emit exception text, token, provider body, password or DB image.
        report['error_type'] = type(error).__name__
        if isinstance(error, ServiceTransportError):
            safe = str(error)
            if safe in {'PROVIDER_REJECTED','PROVIDER_RESPONSE_TOO_LARGE','PROVIDER_UNAVAILABLE','INVALID_TOKEN_RESPONSE','INVALID_PROVIDER_JSON'} or (safe.startswith('PROVIDER_HTTP_') and safe[14:].isdigit()):
                report['provider_error'] = safe
    (BUILD/(mode+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status']=='PASS' else 1

if __name__ == '__main__': raise SystemExit(main(sys.argv[1]))
