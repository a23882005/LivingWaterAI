"""Read-only SAHMREALTIME diagnostic using an existing injected FRED_API_KEY.

No formal crawler, runtime source registry or last-valid state is modified.
The credential is used in memory and never written to reports or subprocesses.
Exit 0: data read/identity checks passed, usage qualification remains separate.
Exit 2: connection, authentication, data or identity check blocked.
"""
import argparse,hashlib,json,os,re,ssl,sys,urllib.error,urllib.parse,urllib.request
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='https://api.stlouisfed.org'
SERIES='SAHMREALTIME'

def now():return datetime.now(timezone.utc).isoformat()

def redact(text,key):
    if key:
        for token in {key,urllib.parse.quote(key,safe=''),urllib.parse.quote_plus(key)}:
            text=text.replace(token,'[REDACTED]')
    return re.sub(r'([?&]api_key=)[^&\s\"<>]+',r'\1[REDACTED]',text,flags=re.I)

class OfficialRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlsplit(newurl)
        if p.scheme!='https' or p.hostname!='api.stlouisfed.org':
            raise ValueError('Non-official redirect refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def send(url):
    opener=urllib.request.build_opener(OfficialRedirectsOnly(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(url,headers={'User-Agent':'V70-D01-SAHM-ReadOnly/1.0','Accept':'application/json'})
    try:
        with opener.open(req,timeout=30) as response:return response.status,dict(response.headers),response.read(4*1024*1024)
    except urllib.error.HTTPError as exc:return exc.code,dict(exc.headers),exc.read(4*1024*1024)

def request_json(path,params,key,dest,name,sender=send):
    if path not in ['/fred/series','/fred/series/observations']:raise ValueError('Unsupported official endpoint')
    public={**params,'series_id':SERIES,'file_type':'json'}
    safe_url=ORIGIN+path+'?'+urllib.parse.urlencode(public)
    private={**public,**({'api_key':key} if key else {})}
    url=ORIGIN+path+'?'+urllib.parse.urlencode(private)
    started=now();headers={};body=b'';transport_error=None
    try:status,headers,body=sender(url)
    except Exception as exc:status=0;transport_error={'type':type(exc).__name__,'message':redact(str(exc),key)[:500]}
    decoded=body.decode('utf-8',errors='replace');safe_body=redact(decoded,key).encode('utf-8')
    response_path=dest/(name+'_response.json');response_path.write_bytes(safe_body)
    record={'source_id':name,'url':safe_url,'credential_environment_variable':'FRED_API_KEY','credential_present':bool(key),
            'http_status':status,'started_at':started,'fetched_at':now(),'attempts':1,
            'HTTP_body_bytes':len(body),'HTTP_body_sha256':hashlib.sha256(body).hexdigest(),
            'archived_body_bytes':len(safe_body),'archived_body_sha256':hashlib.sha256(safe_body).hexdigest(),
            'body_redacted':safe_body!=body,'body_path':response_path.name,
            'headers':{k.lower():redact(v,key) for k,v in headers.items() if k.lower() in ['date','content-type','last-modified','etag','retry-after']},
            'transport_error':transport_error,'no_retry_for_400_401_403':True}
    (dest/(name+'_HTTP.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
    try:obj=json.loads(safe_body)
    except ValueError:obj=None
    return record,obj

def blocked_status(record,obj,key):
    message=(obj or {}).get('error_message','') if isinstance(obj,dict) else ''
    if record['http_status']==400 and not key and 'api_key is not set' in message:
        return 'BLOCKED_MISSING_CONTROLLED_FRED_API_KEY_INJECTION'
    if record['http_status'] in [400,401,403]:return 'BLOCKED_CREDENTIAL_OR_API_ACCESS'
    if record['http_status']==429:return 'BLOCKED_RATE_LIMIT_NO_IMMEDIATE_RETRY'
    if record['http_status']!=200:return 'BLOCKED_HTTP_OR_TRANSPORT'
    return 'BLOCKED_INVALID_OFFICIAL_RESPONSE'

def validate_data(metadata,observations,asof):
    series=(metadata or {}).get('seriess',[])
    if len(series)!=1 or series[0].get('id')!=SERIES:raise ValueError('Exact SAHMREALTIME identity required; SAHMCURRENT not accepted')
    meta=series[0]
    if meta.get('frequency')!='Monthly' or meta.get('units')!='Percentage Points':raise ValueError('Published frequency/unit mismatch')
    if 'real' not in meta.get('title','').lower():raise ValueError('Real-time series title required')
    rows=(observations or {}).get('observations',[])
    if (observations or {}).get('count')!=len(rows):raise ValueError('Incomplete observations page')
    eligible=[r for r in rows if date.fromisoformat(r['date'])<=asof]
    if not eligible:raise ValueError('No published observation at cutoff')
    newest=max(eligible,key=lambda r:r['date'])
    if newest.get('value') in [None,'','.']:raise ValueError('Latest published observation is missing; no older value relabelled current')
    value=Decimal(newest['value'])
    if not value.is_finite():raise ValueError('Nonfinite published value')
    for r in [observations,newest]:
        a=date.fromisoformat(r['realtime_start']);b=date.fromisoformat(r['realtime_end'])
        if not a<=asof<=b:raise ValueError('Returned vintage does not cover requested as-of')
    return {'series_id':SERIES,'value':str(value),'observation_date':newest['date'],'unit':meta['units'],
            'frequency':meta['frequency'],'seasonal_adjustment':meta.get('seasonal_adjustment'),
            'realtime_start':newest['realtime_start'],'realtime_end':newest['realtime_end'],
            'source_last_updated':meta.get('last_updated'),'publication_date':None,
            'publication_note':'Series last_updated is not substituted for first publication date.',
            'notes':meta.get('notes'),'source_title':meta.get('title')}

def run(asof,dest,*,environ=None,sender=send):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    env=os.environ if environ is None else environ;key=env.get('FRED_API_KEY','').strip()
    params={'realtime_start':asof.isoformat(),'realtime_end':asof.isoformat()}
    record,metadata=request_json('/fred/series',params,key,dest,'SAHMREALTIME_metadata',sender)
    report={'task':'D01_ACTUAL_READ_ONLY_EXECUTION','series_id':SERIES,'as_of':asof.isoformat(),
            'credential_present':bool(key),'credential_variable':'FRED_API_KEY','requests':[record],
            'metadata':metadata,'observations_request':'NOT_ATTEMPTED_METADATA_OR_AUTH_BLOCK','technical_sample':None,
            'runtime_sample_admitted':False,'public_app_use_approved':False,'formal_state_modified':False,
            'minimum_missing_setting':None,'uses_assessment':'Technical read and seven-use qualification remain separate.'}
    if record['http_status']!=200 or not isinstance(metadata,dict) or metadata.get('error_code'):
        report['status']=blocked_status(record,metadata,key)
    else:
        obs_params={**params,'observation_start':'2025-01-01','observation_end':asof.isoformat(),'sort_order':'desc','limit':1000}
        obs_record,obs=request_json('/fred/series/observations',obs_params,key,dest,'SAHMREALTIME_observations',sender)
        report['requests'].append(obs_record);report['observations_request']='ATTEMPTED'
        if obs_record['http_status']!=200 or not isinstance(obs,dict) or obs.get('error_code'):report['status']=blocked_status(obs_record,obs,key)
        else:
            try:report['technical_sample']=validate_data(metadata,obs,asof);report['status']='TECHNICAL_READ_PASS_USE_AND_PUBLICATION_QUALIFICATION_PENDING'
            except (KeyError,ValueError,TypeError,InvalidOperation) as exc:report['status']='BLOCKED_SERIES_DATA_OR_VINTAGE_QUALITY';report['quality_error']=str(exc)
    if report['status']=='BLOCKED_MISSING_CONTROLLED_FRED_API_KEY_INJECTION':
        report['minimum_missing_setting']={'name':'FRED_API_KEY','where':'Controlled runtime-secret injection into this selected Codex candidate environment, or an approved isolated D01 runner',
            'existing_source':'Use the already approved credential binding; no value in chat, logs or ZIP',
            'PM_action':'Provide the existing controlled binding or approved isolated runner; read authorization is already granted and is not being requested again.'}
    report['completed_at']=now();safe=redact(json.dumps(report,ensure_ascii=False,indent=2),key)
    (dest/'D01_execution_result.json').write_text(safe)
    return json.loads(safe)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--as-of',default=date.today().isoformat());ap.add_argument('--output',type=Path);args=ap.parse_args()
    asof=date.fromisoformat(args.as_of)
    if asof>date.today():raise SystemExit('Future cutoff refused')
    output=args.output or ROOT/'evidence'/'d01_runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result=run(asof,output)
    print(json.dumps({'status':result['status'],'series_id':SERIES,'credential_present':result['credential_present'],
        'HTTP_statuses':[r['http_status'] for r in result['requests']],'technical_sample':result['technical_sample'],
        'runtime_sample_admitted':False,'output':str(output),'minimum_missing_setting':result['minimum_missing_setting']},ensure_ascii=False))
    raise SystemExit(0 if result['status'].startswith('TECHNICAL_READ_PASS') else 2)

if __name__=='__main__':main()
