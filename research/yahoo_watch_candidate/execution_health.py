"""GitHub execution facts only; no inferred scheduled slot or missed-run count."""
import json,urllib.request

FIELDS={'scheduled_slot','schedule_expression','event_name','actual_started_at','last_success_at',
        'last_success_run_id','last_success_url','status','actual_started_at_source','last_success_at_source'}

def unknown(event_name='UNKNOWN'):
    return dict(scheduled_slot=None,schedule_expression=None,event_name=event_name,
        actual_started_at=None,last_success_at=None,last_success_run_id=None,last_success_url=None,
        status='UNKNOWN',actual_started_at_source=None,last_success_at_source=None)

def validate(value):
    if not isinstance(value,dict) or set(value)!=FIELDS:raise ValueError('INVALID_EXECUTION_METADATA')
    if value['scheduled_slot'] is not None:raise ValueError('SCHEDULED_SLOT_NOT_PROVIDED_BY_GITHUB')
    if any(v is not None and (not isinstance(v,str) or len(v)>512 or any(ord(c)<32 for c in v)) for v in value.values()):
        raise ValueError('INVALID_EXECUTION_VALUE')
    return value

def collect(repo,run_id,token,event_name='UNKNOWN',get=None):
    value=unknown(event_name)
    if repo!='a23882005/LivingWaterAI' or not str(run_id).isdigit():return value
    base='https://api.github.com/repos/'+repo
    def request(path):
        req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'watch-execution-health'})
        with urllib.request.urlopen(req,timeout=15) as response:raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('RESPONSE_TOO_LARGE')
        return json.loads(raw)
    get=get or request
    try:
        current=get('/actions/runs/'+str(run_id))
        if current.get('path')!='.github/workflows/yahoo-reference-monitor.yml' or current.get('head_branch')!='main':return value
        value.update(event_name=current.get('event','UNKNOWN'),actual_started_at=current.get('run_started_at'),actual_started_at_source='GitHub workflow run_started_at')
        runs=get('/actions/workflows/yahoo-reference-monitor.yml/runs?branch=main&status=success&per_page=10')['workflow_runs']
        for run in runs:
            if str(run.get('id'))==str(run_id) or run.get('conclusion')!='success' or run.get('status')!='completed' or run.get('head_branch')!='main':continue
            jobs=get('/actions/runs/'+str(run['id'])+'/jobs')['jobs']
            ends=[j['completed_at'] for j in jobs if j.get('name')=='reference' and j.get('conclusion')=='success' and j.get('completed_at')]
            if ends:
                value.update(last_success_at=max(ends),last_success_run_id=str(run['id']),last_success_url='https://github.com/'+repo+'/actions/runs/'+str(run['id']),last_success_at_source='GitHub reference job completed_at')
                break
        # Cron expression is known configuration, NOT the delayed event's original slot.
        value['schedule_expression']='3,13,23,33,43,53 * * * *'
        value['status']='VERIFIED_GITHUB_EXECUTION_FACTS' if value['actual_started_at'] else 'UNKNOWN'
        return validate(value)
    except Exception:
        return unknown(event_name)
