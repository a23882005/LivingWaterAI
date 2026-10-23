"""Build/test isolated hosted account entry. Secrets never enter artifacts."""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import time

ROOT=Path('build/family-b07-http')
SOURCE=Path(__file__).resolve().parents[1]

def build():
    os.umask(0o077)
    run=os.environ['LW_RUN']+'-'+os.environ['LW_ATTEMPT']
    if not re.fullmatch(r'[0-9]+-[0-9]+',run): raise ValueError('RUN')
    origin=(os.environ.get('SITE_BASE_URL') or 'https://www.happihelp.com').rstrip('/')
    parsed=urllib.parse.urlsplit(origin)
    if parsed.scheme!='https' or parsed.path or parsed.username:raise ValueError('ORIGIN')
    private=ROOT/'private';public=ROOT/'public'
    private.mkdir(parents=True,exist_ok=True);public.mkdir(parents=True,exist_ok=True)
    key=secrets.token_hex(32);initial=secrets.token_urlsafe(24);new=secrets.token_urlsafe(24)
    config={'run':run,'origin':origin,'server_key':secrets.token_hex(32),
            'seeds':[{'user_id':'synthetic_manager','password':initial,'role':'manager'}],
            'oauth':{n:os.environ[n] for n in ('FAMILY_DRIVE_CLIENT_ID','FAMILY_DRIVE_CLIENT_SECRET','FAMILY_DRIVE_REFRESH_TOKEN')}}
    (private/'config.json').write_text(json.dumps(config))
    (private/'gateway.json').write_text(json.dumps({'probe_key_hash':hashlib.sha256(key.encode()).hexdigest()}))
    (ROOT/'test-keys.json').write_text(json.dumps({'run':run,'origin':origin,'key':key,'initial':initial,'new':new}))
    (public/'index.php').write_text((SOURCE/'probes/b07_account_gateway.php').read_text().replace('__RUN_ID__',run))
    for name in ['帳號管理.py','資料存取管理.py','resource_headers.py','drive_resource_backend.py',
                 'drive_service_transport.py','account_http.py','account_login.html']:
        shutil.copyfile(SOURCE/name,private/name)
    for name in ['b07_http_worker.py','b07_account_integration.py','b06_drive_integration.py','actions_drive_write_probe.py']:
        shutil.copyfile(SOURCE/'probes'/name,private/name)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def verify():
    c=json.loads((ROOT/'test-keys.json').read_text());jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPCookieProcessor(jar))
    url=c['origin']+'/family-b07-http-'+c['run']+'/index.php'
    checks=[];csrf='';last_status=None;transient_statuses=[]
    def call(path='',body=None,extra=None,authenticated=True,transport=None):
        nonlocal last_status
        headers={'X-Family-Test-Key':c['key']} if authenticated else {}
        if body is not None:
            headers.update({'Content-Type':'application/json','Origin':c['origin'],'X-Family-CSRF':csrf})
            body=json.dumps(dict(body,request_id=body.get('request_id',uuid.uuid4().hex))).encode()
        headers.update(extra or {})
        req=urllib.request.Request(url+path,data=body,headers=headers)
        # The same serialized request ID is retained after an unknown response.
        # B06 reconciles its journal/receipt before another write is attempted.
        for attempt in range(3):
            try:
                with (transport or opener).open(req,timeout=300) as r:result=(r.status,r.headers,r.read(32768))
            except urllib.error.HTTPError as e:
                with e:result=(e.code,e.headers,e.read(32768))
            deadline=time.monotonic()+600
            while result[0]==202:
                job=json.loads(result[2])['pending']
                if not re.fullmatch('[a-f0-9]{48}',job) or time.monotonic()>=deadline:
                    raise RuntimeError('INVALID_OR_EXPIRED_JOB')
                time.sleep(2)
                poll=urllib.request.Request(url+'/_result/'+job,headers={'X-Family-Test-Key':c['key']})
                try:
                    with (transport or opener).open(poll,timeout=30) as r:result=(r.status,r.headers,r.read(32768))
                except urllib.error.HTTPError as e:
                    with e:result=(e.code,e.headers,e.read(32768))
            last_status=result[0]
            if last_status not in (500,502,503,504) or attempt==2:return result
            transient_statuses.append(last_status)
            print(json.dumps({'retry_http_status':last_status,'attempt':attempt+1}),flush=True)
            time.sleep(2)
    def check(name,condition):
        if not condition:raise AssertionError(name+':http='+str(last_status))
        checks.append(name)
        print(json.dumps({'passed_check':name}),flush=True)
    check('isolated_test_gate',call(authenticated=False)[0]==401)
    status,headers,page=call()
    check('login_page',status==200 and 'text/html' in headers.get('Content-Type','') and 'Family 帳號登入'.encode() in page)
    csrf=re.search(rb'name="family-csrf" content="([^"]+)"',page).group(1).decode()
    check('page_csp',"frame-ancestors 'none'" in headers.get('Content-Security-Policy',''))
    check('origin_rejected',call('/login',{'user_id':'synthetic_manager','password':c['initial']},extra={'Origin':'https://evil.example'})[0]==403)
    check('csrf_rejected',call('/login',{'user_id':'synthetic_manager','password':c['initial']},extra={'X-Family-CSRF':'wrong'})[0]==403)
    check('identity_override_rejected',call('/login',{'user_id':'synthetic_manager','password':c['initial'],'role':'manager'})[0]==400)
    status,headers,body=call('/login',{'user_id':'synthetic_manager','password':c['initial']})
    check('initial_login',status==200 and json.loads(body)['result']['must_change'])
    cookie=headers.get('Set-Cookie','')
    check('secure_cookie',all(x in cookie for x in ['Secure','HttpOnly','SameSite=Strict','Path=/']))
    check('token_not_json',b'"token"' not in body and c['initial'].encode() not in body)
    status,_,body=call('/change-password',{'current_password':c['initial'],'new_password':c['new']})
    check('first_password_change',status==200 and json.loads(body)['result']['login_required'])
    body={'user_id':'synthetic_manager','password':c['new'],'request_id':'http-idempotent-login-0001'}
    status,_,data=call('/login',body)
    check('normal_login',status==200)
    deadline=json.loads(data)['result']['expires_at']
    check('session_cookie_replay',call('/login',body)[0]==200)
    other=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPCookieProcessor(jar))
    status,_,data=call('/session',transport=other)
    check('new_http_connection_resume',status==200 and json.loads(data)['result']=={'user_id':'synthetic_manager','expires_at':deadline})
    status,_,_=call('/manage',{'operation':'create','user_id':'synthetic_child','password':secrets.token_urlsafe(24),'role':'member','until':int(time.time())+1800})
    check('manager_create',status==200)
    check('logout',call('/logout',{})[0]==200)
    check('logout_revocation',call('/session')[0]==401)
    return {'schema':'Family-B07-https-proof-v1','status':'PASS','scope':'ISOLATED_HTTPS_TO_APPROVED_DRIVE_TEMP',
            'checks':checks,'count':len(checks),'run':c['run'],'transient_http_statuses':transient_statuses}

if __name__=='__main__':
    if sys.argv[1]=='build':build()
    else:
        try: report=verify()
        except Exception as error:
            report={'status':'FAIL','error_type':type(error).__name__}
            if isinstance(error,AssertionError):report['check']=str(error)
        (ROOT/'proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        if report['status']!='PASS':raise SystemExit(1)
