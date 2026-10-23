"""HTTPS OAuth end-to-end with synthetic accounts; no real client registration."""
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import b07_http_client as base
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from account_oauth import challenge,SCOPE


def build():
    base.build();private=base.ROOT/'private';public=base.ROOT/'public'
    p=private/'config.json';c=json.loads(p.read_text())
    c['account_base']='/family-b07-http-'+c['run']+'/index.php'
    c['oauth_clients']={'synthetic-https-client':['https://synthetic.invalid/callback']}
    p.write_text(json.dumps(c))
    p=private/'gateway.json';g=json.loads(p.read_text());g['account_base']=c['account_base'];p.write_text(json.dumps(g))
    for name in ['account_oauth.py','account_mcp.py','oauth_http.py','account_router.py']:
        shutil.copyfile(base.SOURCE/name,private/name)
    shutil.copyfile(base.SOURCE/'probes/b07_oauth_http_worker.py',private/'b07_oauth_http_worker.py')
    p=public/'index.php';s=p.read_text()
    s=s.replace("if (($_SERVER['QUERY_STRING']??'')!=='') fail_request(400,'QUERY_NOT_ALLOWED');","if (strlen($_SERVER['QUERY_STRING']??'')>8192) fail_request(400,'QUERY_TOO_LARGE');")
    s=s.replace("'Origin'=>'HTTP_ORIGIN'","'Authorization'=>'HTTP_AUTHORIZATION','Origin'=>'HTTP_ORIGIN'")
    s=s.replace("'path'=>($_SERVER['PATH_INFO']??'')?:'/'", "'path'=>$config['account_base'].(($_SERVER['PATH_INFO']??'')?:'/').((($_SERVER['QUERY_STRING']??'')!=='')?'?'.$_SERVER['QUERY_STRING']:'')")
    s=s.replace("/b07_http_worker.py'","/b07_oauth_http_worker.py'")
    anchor="http_response_code(202);echo json_encode(['pending'=>$id]);\n} catch"
    replacement="""if (preg_match('~^/(oauth(?:/|$)|mcp(?:/|$))~',$path)) {
        $deadline=microtime(true)+105;
        $result=$jobs.'/'.$id.'.result.json';
        while (microtime(true)<$deadline) {
            clearstatcache(true,$result);
            if (is_file($result)) send_reply(json_decode(file_get_contents($result),true));
            usleep(100000);
        }
        fail_request(504,'SERVICE_TIMEOUT');
    }
    http_response_code(202);echo json_encode(['pending'=>$id]);
} catch"""
    if anchor not in s:raise ValueError('GATEWAY_TEMPLATE_CHANGED')
    p.write_text(s.replace(anchor,replacement))


def verify():
    c=json.loads((base.ROOT/'test-keys.json').read_text());jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(base.NoRedirect(),urllib.request.HTTPCookieProcessor(jar))
    url=c['origin']+'/family-b07-http-'+c['run']+'/index.php';csrf='';checks=[];timings={}
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name);print(json.dumps({'passed_check':name}),flush=True)
    def request(path,raw=None,headers=None,poll=False):
        h={'X-Family-Test-Key':c['key']};h.update(headers or {})
        req=urllib.request.Request(url+path,data=raw,headers=h)
        def once(req):
            try:
                with opener.open(req,timeout=120) as r:return r.status,r.headers,r.read(65536)
            except urllib.error.HTTPError as e:
                with e:return e.code,e.headers,e.read(65536)
        result=once(req);end=time.monotonic()+600
        if not poll and result[0]==202:raise AssertionError('oauth_must_not_return_poll_job')
        while poll and result[0]==202:
            job=json.loads(result[2])['pending']
            if not re.fullmatch('[a-f0-9]{48}',job) or time.monotonic()>end:raise AssertionError('poll_timeout')
            time.sleep(2)
            result=once(urllib.request.Request(url+'/_result/'+job,headers={'X-Family-Test-Key':c['key']}))
        return result
    def account(path,payload):
        return request(path,json.dumps(dict(payload,request_id=uuid.uuid4().hex)).encode(),{'Content-Type':'application/json','Origin':c['origin'],'X-Family-CSRF':csrf},True)
    status,_,page=request('',poll=True);check('account_page',status==200)
    csrf=re.search(rb'name="family-csrf" content="([^"]+)"',page).group(1).decode()
    check('initial_login',account('/login',{'user_id':'synthetic_manager','password':c['initial']})[0]==200)
    check('first_password_change',account('/change-password',{'current_password':c['initial'],'new_password':c['new']})[0]==200)
    check('normal_login',account('/login',{'user_id':'synthetic_manager','password':c['new']})[0]==200)
    status,_,body=request('/oauth/.well-known/oauth-authorization-server')
    check('oauth_discovery',status==200 and json.loads(body)['issuer']==url+'/oauth')
    status,_,body=request('/mcp/.well-known/oauth-protected-resource')
    check('resource_discovery',status==200 and json.loads(body)['resource']==url+'/mcp')
    verifier=secrets.token_urlsafe(48)
    p={'response_type':'code','client_id':'synthetic-https-client','redirect_uri':'https://synthetic.invalid/callback','resource':url+'/mcp','scope':SCOPE,'state':'synthetic-state','code_challenge':challenge(verifier),'code_challenge_method':'S256'}
    path='/oauth/authorize?'+urllib.parse.urlencode(p)
    status,_,page=request(path);check('explicit_consent_page',status==200 and b'id="consent"' in page)
    csrf=re.search(rb'name="family-csrf" content="([^"]+)"',page).group(1).decode()
    status,_,body=request(path,b'{"consent":true}',{'Content-Type':'application/json','Origin':c['origin'],'X-Family-CSRF':csrf})
    check('authorization_direct_reply',status==200)
    redirect=urllib.parse.urlsplit(json.loads(body)['redirect']);params=urllib.parse.parse_qs(redirect.query)
    check('exact_redirect_state_issuer',redirect.netloc=='synthetic.invalid' and params['state']==['synthetic-state'] and params['iss']==[url+'/oauth'])
    form={'grant_type':'authorization_code','client_id':p['client_id'],'redirect_uri':p['redirect_uri'],'resource':p['resource'],'code':params['code'][0],'code_verifier':verifier}
    start=time.monotonic();status,_,body=request('/oauth/token',urllib.parse.urlencode(form).encode(),{'Content-Type':'application/x-www-form-urlencoded'});timings['token_exchange_seconds']=round(time.monotonic()-start,3)
    check('standard_token_response',status==200);pair=json.loads(body)
    def mcp(token):
        return request('/mcp',json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'family_session','arguments':{}}}).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+token})
    status,_,body=mcp(pair['access_token']);check('mcp_session_identity',status==200 and json.loads(body)['result']['structuredContent']['user_id']=='synthetic_manager')
    form={'grant_type':'refresh_token','client_id':p['client_id'],'resource':p['resource'],'refresh_token':pair['refresh_token']}
    status,_,body=request('/oauth/token',urllib.parse.urlencode(form).encode(),{'Content-Type':'application/x-www-form-urlencoded'});check('refresh_direct_response',status==200);pair=json.loads(body)
    check('logout',account('/logout',{})[0]==200)
    check('mcp_revoked_after_logout',mcp(pair['access_token'])[0]==401)
    return {'schema':'Family-B07-oauth-https-proof-v1','status':'PASS','scope':'SYNTHETIC_HTTPS_DRIVE_ONLY','checks':checks,'count':len(checks),'timings':timings}

if __name__=='__main__':
    if sys.argv[1]=='build':build()
    else:
        try:report=verify()
        except Exception as e:
            report={'status':'FAIL','error_type':type(e).__name__}
            if isinstance(e,AssertionError):report['check']=str(e)
        (base.ROOT/'oauth-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        if report['status']!='PASS':raise SystemExit(1)
