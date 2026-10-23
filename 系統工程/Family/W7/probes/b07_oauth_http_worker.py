"""Isolated HTTPS OAuth worker; shares the existing TEMP cleanup lock."""
import json
import sys
from pathlib import Path
import b07_http_worker as worker
from account_oauth import OAuthService
from account_router import AccountRouter

original=worker.main

def app(c,d,p):
    manager=worker.a.AccountManager(worker.store(d,p),bytes.fromhex(c['server_key']))
    account=worker.AccountHTTP(manager,c['origin'],'b07-http-'+c['run'],worker.RateLimiter(worker.BASE/'rate.db',manager.key))
    oauth=OAuthService(manager,c['origin']+c['account_base']+'/oauth',c['origin']+c['account_base']+'/mcp',c['oauth_clients'],'b07-http-'+c['run'])
    return oauth,account


def main(mode,request=None):
    if mode in ('init','cleanup'):
        original(mode)
        if mode=='init':
            c=worker.configuration();d=worker.ServiceProbe();p=json.loads((worker.BASE/'runtime.json').read_text())
            app(c,d,p)[0].migrate()
            print('OAUTH_SCHEMA_INITIALIZED')
        return
    if mode!='call':raise ValueError('MODE')
    c=worker.configuration();d=worker.ServiceProbe();d.transport.timeout=60
    p=json.loads((worker.BASE/'runtime.json').read_text());oauth,account=app(c,d,p)
    if request is None:request=json.loads(sys.stdin.buffer.read(20000))
    router=AccountRouter(oauth,account,c['account_base'])
    status,headers,body=router.handle(request['method'],request['path'],request['headers'],request['body'].encode(),request['peer'])
    print(json.dumps({'status':status,'headers':headers,'body':body.decode()}))

worker.main=main
if __name__=='__main__':
    try:worker.run_mode(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None)
    except Exception as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__}));raise SystemExit(1)
