"""P02: one normal read of each exact Yahoo chart; no auth, retries or cookies.

Only HTTP status is printed. Raw bodies remain inside the encrypted artifact.
The separate finance history page is read only after the same symbol chart
returns HTTP200, to bind the contract label and dated historical close.
"""
import hashlib,json,ssl,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

DEST=Path('build/v70-p02');DEST.mkdir(parents=True,exist_ok=True)
MAX=8*1024*1024

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urlsplit(newurl)
        if u.scheme!='https' or u.hostname not in {'query1.finance.yahoo.com','finance.yahoo.com'} or any(s in u.path.lower() for s in ['login','signin','consent','oauth']):
            raise ValueError('Login or nonapproved redirect stopped')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def capture(name,url):
    started=datetime.now(timezone.utc).isoformat();status=0;body=b'';headers={};error=None
    opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(url,headers={'User-Agent':'V70SourceCandidate/1.0 (source verification)','Accept':'application/json,text/html'})
    try:
        with opener.open(req,timeout=30) as response:
            status=response.status;headers=dict(response.headers);body=response.read(MAX+1)
    except urllib.error.HTTPError as exc:
        status=exc.code;headers=dict(exc.headers);body=exc.read(MAX+1);error='HTTP_'+str(status)
    except Exception as exc:error=type(exc).__name__
    if len(body)>MAX:error='RESPONSE_SIZE_LIMIT';body=body[:MAX]
    receipt={'schema':'V70_P02_AUTHORIZED_RUNNER_HTTP_1','url':url,'final_url':url,'http_status':status,
        'fetched_at':datetime.now(timezone.utc).isoformat(),'started_at':started,'attempts':1,
        'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'path':name+'.body',
        'body_complete':error!='RESPONSE_SIZE_LIMIT','error':error,'transport_ok':status==200 and error is None,
        'headers':{k.lower():v for k,v in headers.items() if k.lower() in {'date','content-type','last-modified','etag','age'}},
        'cost_status':'EXISTING_AUTHORIZED_RUNNER_NO_PURCHASE_OR_NEW_ACCOUNT','credentials_used':False,
        'provenance':'NORMAL_HTTPS_GET_ON_EXISTING_GITHUB_RUNNER_NO_AUTH_OR_RETRY'}
    (DEST/(name+'.body')).write_bytes(body)
    (DEST/(name+'.receipt.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(name,'HTTP',status,'error',error)
    return receipt

def main():
    rows=[]
    for name,symbol in [('dxy','DX-Y.NYB'),('wti','CL%3DF')]:
        chart=capture(name+'_chart','https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?range=1mo&interval=1d&includePrePost=false')
        rows.append(chart)
        if chart['transport_ok']:
            rows.append(capture(name+'_history','https://finance.yahoo.com/quote/'+symbol+'/history/'))
    (DEST/'request_index.json').write_text(json.dumps({'series':['DX-Y.NYB','CL=F'],'requests':rows,
        'retry_after_429':False,'formal_state_modified':False,'public_use_permission_granted':False},indent=2))

if __name__=='__main__':main()
