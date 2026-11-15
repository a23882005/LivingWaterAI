"""Read only SAHMREALTIME release, sources, vintages and initial-release evidence."""
import hashlib,json,os,sys,urllib.parse
from datetime import date
from pathlib import Path
from run_d01_sahm import ORIGIN,SERIES,now,redact,send

ALLOWED={'/fred/series/release','/fred/release/sources','/fred/series/vintagedates','/fred/series/observations'}

def capture(path,params,key,dest,name):
    if path not in ALLOWED:raise ValueError('Unapproved provenance endpoint')
    public={**params,'file_type':'json'}
    private={**public,**({'api_key':key} if key else {})}
    safe_url=ORIGIN+path+'?'+urllib.parse.urlencode(public)
    started=now();body=b'';headers={};error=None
    try:status,headers,body=send(ORIGIN+path+'?'+urllib.parse.urlencode(private))
    except Exception as exc:status=0;error={'type':type(exc).__name__,'message':redact(str(exc),key)[:500]}
    safe=redact(body.decode('utf-8',errors='replace'),key).encode()
    body_path=name+'_response.json';(dest/body_path).write_bytes(safe)
    record={'url':safe_url,'http_status':status,'started_at':started,'fetched_at':now(),'attempts':1,
            'credential_present':bool(key),'HTTP_body_sha256':hashlib.sha256(body).hexdigest(),
            'archived_body_sha256':hashlib.sha256(safe).hexdigest(),'body_path':body_path,
            'body_redacted':safe!=body,'error':error,
            'headers':{k.lower():redact(v,key) for k,v in headers.items() if k.lower() in ['date','content-type','last-modified','etag']}}
    (dest/(name+'_HTTP.json')).write_text(json.dumps(record,indent=2))
    try:obj=json.loads(safe)
    except ValueError:obj=None
    return record,obj

def main():
    dest=Path(sys.argv[1]);initial=json.loads((dest/'D01_execution_result.json').read_text())
    sample=initial.get('technical_sample')
    if not sample:raise SystemExit('No valid SAHMREALTIME technical sample to bind provenance')
    cutoff=initial['as_of'];period=sample['observation_date'];date.fromisoformat(cutoff)
    key=os.environ.get('FRED_API_KEY','').strip();requests=[];responses={}
    def get(name,path,params):
        record,obj=capture(path,params,key,dest,name);requests.append(record);responses[name]=obj;return record,obj
    release_record,release=get('SAHMREALTIME_release','/fred/series/release',{'series_id':SERIES,'realtime_start':cutoff,'realtime_end':cutoff})
    releases=(release or {}).get('releases',[])
    if release_record['http_status']==200 and len(releases)==1 and isinstance(releases[0].get('id'),int):
        get('SAHMREALTIME_sources','/fred/release/sources',{'release_id':releases[0]['id'],'realtime_start':cutoff,'realtime_end':cutoff})
    get('SAHMREALTIME_vintagedates','/fred/series/vintagedates',{'series_id':SERIES,'realtime_start':period,'realtime_end':cutoff,'sort_order':'desc','limit':1000})
    get('SAHMREALTIME_initial_release','/fred/series/observations',{'series_id':SERIES,'realtime_start':'1776-07-04','realtime_end':cutoff,'observation_start':period,'observation_end':period,'output_type':4,'sort_order':'desc','limit':1000})
    report={'series_id':SERIES,'as_of':cutoff,'observation_date':period,'requests':requests,'responses':responses,
            'status':'PROVENANCE_REQUESTS_PASS' if len(requests)==4 and all(r['http_status']==200 for r in requests) else 'PROVENANCE_PARTIAL_OR_BLOCKED',
            'credential_value_exported':False,'public_app_use_approved':False,'formal_state_modified':False,'completed_at':now()}
    (dest/'D01_provenance_result.json').write_text(redact(json.dumps(report,ensure_ascii=False,indent=2),key))
    print('D01 provenance status:',report['status']);print('Provenance HTTP statuses:',[r['http_status'] for r in requests])
    raise SystemExit(0 if report['status']=='PROVENANCE_REQUESTS_PASS' else 2)

if __name__=='__main__':main()
