"""Original 09h/11h Actions integration. Private candidates until PM enablement."""
from __future__ import annotations
import argparse,copy,csv,datetime as dt,hashlib,io,json,os,re,time,zipfile
from pathlib import Path
import requests
from v70_family_sources import collect,merge_candidate,write_registry,stamp,sha,canonical,EXPECTED,Fetcher
from v70_family_drive import Drive,checked_update,isolation_roundtrip,BASELINE_NAME,CANDIDATE_NAME,INTAKE_NAME

REPO='a23882005/LivingWaterAI'
FIXED_CUTOFF='2026-11-17T14:43:12+08:00'

def github_get(path,raw=False):
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    headers={'Accept':'application/vnd.github+json'}
    if token:headers['Authorization']='Bearer '+token
    r=requests.get('https://api.github.com/repos/'+REPO+'/'+path,headers=headers,timeout=(10,60))
    if not r.ok:raise RuntimeError('GITHUB_READ_FAILED_'+str(r.status_code))
    if len(r.content)>40*1024*1024:raise RuntimeError('GITHUB_RESPONSE_TOO_LARGE')
    return r.content if raw else r.json()

def verify_formal_basis(baseline,archive,feed=None):
    v=baseline.get('upstream_verification',{});p=baseline.get('upstream_publication',{})
    if baseline.get('schema_version')!='V70.3/family-macro-safety-v2' or baseline.get('score_status')!='FORMAL_VALID':raise ValueError('FORMAL_BASELINE_REQUIRED')
    if v.get('ready') is not True or v.get('requiredScoringIndicatorsValidated')!=22 or p.get('mode')!='FORMAL' or p.get('scoringAllowed') is not True:raise ValueError('FORMAL_22_GATE_REQUIRED')
    if feed is not None:
        raw=Path(feed).read_bytes();doc=json.loads(raw)
    else:
        runs=github_get('actions/runs?head_sha='+baseline['source_commit']+'&per_page=100')['workflow_runs']
        runs=[r for r in runs if r['name']=='LivingWaterAI 11h Verified V70.3 Site Deploy' and r['conclusion']=='success']
        matches=[]
        for run in runs:
            for a in github_get('actions/runs/'+str(run['id'])+'/artifacts')['artifacts']:
                if a['name'].startswith('v70-3-27-qa-') and not a.get('expired'):matches.append(a)
        raw=None
        for a in matches:
            blob=github_get('actions/artifacts/'+str(a['id'])+'/zip',raw=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for n in z.namelist():
                    if n.endswith('V70_macro_latest.json'):
                        candidate=z.read(n)
                        if sha(candidate)==baseline['feed_sha256']:raw=candidate;break
            if raw is not None:break
        if raw is None:raise ValueError('APPROVED_PUBLISHED_FEED_ARTIFACT_NOT_FOUND')
        doc=json.loads(raw)
    if sha(raw)!=baseline['feed_sha256'] or doc.get('asOf')!=baseline['feed_asof_utc']:raise ValueError('PUBLISHED_FEED_HASH_OR_BATCH_MISMATCH')
    if doc.get('verification',{}).get('ready') is not True or doc['verification'].get('requiredScoringIndicatorsValidated')!=22 or doc.get('publication',{}).get('mode')!='FORMAL':raise ValueError('PUBLISHED_FEED_GATE_FAILED')
    with Path(archive).open(encoding='utf-8-sig',newline='') as f:rows=[r for r in csv.DictReader(f) if r.get('daily_record_id')==baseline['daily_record_id']]
    if len(rows)!=1:raise ValueError('FORMAL_DAILY_RECORD_NOT_UNIQUE')
    row=rows[0]
    if row['feed_sha256']!=baseline['feed_sha256'] or row['score_status']!='FORMAL_VALID' or abs(float(row['health_score'])-baseline['health_score'])>1e-6:raise ValueError('FORMAL_DAILY_RECORD_MISMATCH')
    return {'status':'PUBLISHED_FEED_HASH_22_GATE_AND_DAILY_RECORD_PASS','feed_sha256':sha(raw),'daily_record_id':row['daily_record_id'],'source_commit':baseline['source_commit']}

def validate_candidate(candidate,baseline,intake):
    if candidate['v70_indicators']!=baseline['v70_indicators'] or candidate['v70_judgments']!=baseline['v70_judgments']:raise ValueError('ACCEPTED_ORIGINALS_CHANGED')
    for k in baseline['signals']:
        if k not in EXPECTED and candidate['signals'][k]!=baseline['signals'][k]:raise ValueError('APPROVED_SIGNAL_CHANGED')
    for k in EXPECTED:
        row=candidate['signals'][k]
        if row.get('value') is None:
            if row['data_quality']!='UNKNOWN' or not row.get('issue_detail'):raise ValueError('MISSING_REASON_REQUIRED')
            continue
        if row.get('level') is not None or row.get('direction') is not None or row.get('speed') is not None:raise ValueError('NEW_JUDGMENT_NOT_AUTHORIZED')
        if not row.get('source') or not row.get('as_of') or not row.get('unit') or not row.get('published_at'):raise ValueError('VALUE_PROVENANCE_REQUIRED')
        if row.get('publication_time_precision')=='DATE_ONLY':published=stamp(row['publication_eligibility_bound'])
        else:published=stamp(row['published_at'])
        if published>stamp(candidate['data_cutoff']):raise ValueError('VALUE_RELEASE_AFTER_CUTOFF')
    if candidate['extension_approval']['status']!='PENDING_HIGHEST_PM_ACCEPTANCE':raise ValueError('DO_NOT_FORGE_PM_APPROVAL')
    return True

def wait_intake(drive,parent,baseline,cutoff,wait_seconds,live=False):
    end=time.monotonic()+wait_seconds
    while True:
        meta=drive.find(INTAKE_NAME,parent)
        if meta:
            intake=json.loads(drive.read(meta['id']))
            expected=os.environ.get('GITHUB_SHA')
            date_match=stamp(intake['cutoff']).astimezone(dt.timezone(dt.timedelta(hours=8))).date()==stamp(cutoff).astimezone(dt.timezone(dt.timedelta(hours=8))).date()
            context_match=(intake.get('workflow_ref')=='refs/heads/main' and date_match and stamp(intake['cutoff'])<=stamp(cutoff)) if live else (intake.get('workflow_commit')==expected and stamp(intake['cutoff'])==stamp(cutoff))
            if context_match and intake.get('baseline_sha256')==sha(canonical(baseline)):
                run=intake.get('workflow_run_id')
                if run:
                    jobs=github_get('actions/runs/'+str(run)+'/jobs')['jobs']
                    relevant=[j for j in jobs if j['name']=='family-source-intake']
                    if relevant and relevant[0]['conclusion']=='success':return intake
                    if relevant and relevant[0]['conclusion'] in ('failure','cancelled','timed_out'):raise RuntimeError('SOURCE_INTAKE_JOB_FAILED')
                elif not expected:return intake
        if time.monotonic()>=end:raise RuntimeError('MATCHING_SUCCESSFUL_09H_INTAKE_NOT_AVAILABLE')
        if not live and os.environ.get('GITHUB_SHA'):
            runs=github_get('actions/runs?head_sha='+os.environ['GITHUB_SHA']+'&per_page=100')['workflow_runs']
            source_runs=[r for r in runs if r.get('path')=='.github/workflows/macro18-preflight.yml']
            if source_runs:
                latest=max(source_runs,key=lambda r:(r.get('run_attempt',1),r['id']))
                jobs=github_get('actions/runs/'+str(latest['id'])+'/jobs')['jobs']
                source_jobs=[j for j in jobs if j['name']=='family-source-intake']
                if source_jobs and source_jobs[0]['conclusion'] in ('failure','cancelled','timed_out'):raise RuntimeError('SOURCE_INTAKE_JOB_FAILED')
        time.sleep(10)

def read_baseline(drive):
    meta=drive.find(BASELINE_NAME,required=True)
    if len(meta.get('parents',[]))!=1:raise RuntimeError('SINGLE_PRIVATE_PARENT_REQUIRED')
    parent=meta['parents'][0];raw=drive.read(meta['id']);baseline=json.loads(raw)
    if baseline.get('schema_version')!='V70.3/family-macro-safety-v2':raise ValueError('UNEXPECTED_BASELINE_SCHEMA')
    return meta,parent,raw,baseline

def context_from_live_publication(baseline,feed_path,archive,site_url):
    """Project the original V70's own verified DOM results; never reimplement scoring."""
    from playwright.sync_api import sync_playwright
    raw=Path(feed_path).read_bytes();feed=json.loads(raw)
    if feed.get('publication',{}).get('mode')!='FORMAL' or feed.get('verification',{}).get('requiredScoringIndicatorsValidated')!=22:raise ValueError('CURRENT_FORMAL_GATE_REQUIRED')
    with Path(archive).open(encoding='utf-8-sig',newline='') as f:daily=[r for r in csv.DictReader(f) if r.get('feed_sha256')==sha(raw) and r.get('score_status')=='FORMAL_VALID']
    if not daily:raise ValueError('CURRENT_FORMAL_DAILY_CAPTURE_REQUIRED')
    row=max(daily,key=lambda r:r['run_timestamp_utc'])
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page();page.route('**/cdn.tailwindcss.com/**',lambda r:r.abort());page.route('**/fonts.googleapis.com/**',lambda r:r.abort())
            page.goto(site_url.rstrip('/')+'/?family-macro-context='+sha(raw)[:16],wait_until='domcontentloaded',timeout=45000)
            page.wait_for_function('window.v703FeedVerified===true && window.v703Latest && window.v703MacroSnapshot',timeout=45000)
            state=page.evaluate('''() => ({asOf:window.v703FeedDocument?.asOf,canPublish:window.v703CanPublishFormalAllocation(),judgments:window.v703MacroSnapshot,risk:Object.fromEntries([...document.querySelectorAll('[id^="sc_"]')].map(e=>[e.id.slice(3),Number.parseFloat(e.textContent)]))})''')
        finally:browser.close()
    if not state['canPublish'] or state['asOf']!=feed['asOf'] or abs(state['judgments']['mSafe_final']-float(row['health_score']))>1e-6:raise ValueError('CURRENT_LIVE_DAILY_CONTEXT_MISMATCH')
    out=copy.deepcopy(baseline);out.update(feed_asof_utc=feed['asOf'],data_cutoff=stamp(feed['asOf']).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(),snapshot_timestamp=feed['asOf'],feed_sha256=sha(raw),health_score=float(row['health_score']),daily_record_id=row['daily_record_id'],source_commit=row['source_commit'],v70_version=row['v70_version'],run_timestamp_utc=row['run_timestamp_utc'],upstream_publication=feed['publication'],upstream_verification=feed['verification'],source_snapshot=feed['sourceSnapshot'])
    out['v70_judgments']={k:state['judgments'][k] for k in baseline['v70_judgments']}
    for ident,prior in out['v70_indicators'].items():
        item=feed['indicators'].get(ident)
        if item is None:
            if ident=='m21' and 'm21' in feed.get('derived',{}):prior['value']=feed['derived']['m21']['value']
            else:raise ValueError('ORIGINAL_INDICATOR_MISSING_FROM_NEW_FORMAL_FEED')
            continue
        prior.update(value=item['value'],unit=item.get('unit') or prior.get('unit',''),as_of=item.get('dataDate'),source=item.get('source'),method=item.get('method'),upstream_status=item.get('status'),upstream_unit=item.get('unit',''),verification_as_of=item.get('lastVerifiedAt'),detail=item.get('detail',''),v70_risk_points=state['risk'].get(ident),data_quality='FALLBACK_USED' if item.get('carryForward') or item.get('status')=='USABLE' else 'OK')
        prior['issue_codes']=['FALLBACK_USED'] if prior['data_quality']=='FALLBACK_USED' else []
        if item.get('carryForward'):prior['carry_forward']=item['carryForward']
        else:prior.pop('carry_forward',None)
    for key,signal in out['signals'].items():
        if key in EXPECTED:continue
        ident=signal.get('v70_indicator_id')
        if ident not in out['v70_indicators']:raise ValueError('LEGACY_SIGNAL_MAPPING_MISSING')
        current=out['v70_indicators'][ident]
        for field in ('value','unit','as_of','source','method','upstream_status','upstream_unit','verification_as_of','detail','v70_risk_points','data_quality','issue_codes'):signal[field]=current.get(field)
        if 'observation_month' in signal:signal['observation_month']=str(signal['as_of'])[:7]
        if ident=='m06_rate':
            policy=feed['indicators'][ident]
            signal.update(target_range={'lower':policy.get('lowerBound'),'upper':policy.get('upperBound'),'unit':'%'},effective_date=policy.get('effectiveDate'),statement_date=policy.get('statementDate'))
        if current.get('carry_forward'):signal['carry_forward']=current['carry_forward']
        else:signal.pop('carry_forward',None)
    out['lei_history']=feed.get('leiHistory',[])
    out['automatic_context_validation']={'status':'FORMAL_LIVE_FEED_AND_DAILY_CAPTURE_MATCH','human_per_run_approval_claimed':False}
    return out

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['intake','publish']);parser.add_argument('--cutoff');parser.add_argument('--work',type=Path,default=Path('build/private-v70-family'));parser.add_argument('--archive',type=Path,default=Path('data/macro_safety_daily.csv'));parser.add_argument('--feed',type=Path);parser.add_argument('--live-site');parser.add_argument('--wait-seconds',type=int,default=900);parser.add_argument('--formal',action='store_true');args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True);drive=Drive();meta,parent,before,baseline=read_baseline(drive)
    if args.cutoff and stamp(args.cutoff)!=stamp(baseline['data_cutoff']):raise ValueError('FIXED_CUTOFF_MUST_MATCH_APPROVED_SNAPSHOT')
    cutoff=args.cutoff or (dt.datetime.now(dt.timezone.utc).isoformat() if args.phase=='intake' else baseline['data_cutoff'])
    if args.phase=='intake':
        evidence=args.work/'official-evidence';fetcher=Fetcher(evidence);intake=collect(baseline,cutoff,fetcher)
        intake.update(workflow_commit=os.environ.get('GITHUB_SHA'),workflow_ref=os.environ.get('GITHUB_REF'),workflow_run_id=os.environ.get('GITHUB_RUN_ID'),workflow_run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'))
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(evidence.glob('*')):z.write(p,p.name)
            z.writestr('source-http-receipts.json',json.dumps(intake['http_records'],ensure_ascii=False,indent=2))
        em=drive.create('V70_Family_Source_Evidence_'+os.environ.get('GITHUB_RUN_ID','local')+'_'+os.environ.get('GITHUB_RUN_ATTEMPT','1')+'.zip',parent,bio.getvalue(),mime_type='application/zip')
        intake['private_evidence_archive']={'file_id':em['id'],'sha256':sha(bio.getvalue()),'bytes':len(bio.getvalue())}
        result=checked_update(drive,INTAKE_NAME,parent,intake)
        (args.work/'source-intake.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2));write_registry(intake['source_registry'],args.work/'source-registry.csv')
        if drive.read(meta['id'])!=before:raise RuntimeError('FORMAL_BASELINE_CHANGED_DURING_INTAKE')
        print(json.dumps({'phase':'09h_source_intake','status':'PRIVATE_SOURCE_INTAKE_WRITTEN_AND_READ_BACK','source_slots':len(intake['source_registry']),'numeric_values':sum(x.get('value') is not None for x in intake['supplements'].values()),'sha256':result['sha256'],'formal_baseline_written':False}))
        return
    context=context_from_live_publication(baseline,args.feed,args.archive,args.live_site) if args.live_site else baseline
    cutoff=context['data_cutoff']
    basis=verify_formal_basis(context,args.archive,args.feed)
    intake=wait_intake(drive,parent,baseline,cutoff,args.wait_seconds,live=bool(args.live_site))
    if args.live_site:
        intake=copy.deepcopy(intake);intake['intake_cutoff_before_formal_context']=intake['cutoff'];intake['cutoff']=cutoff;intake['baseline_sha256']=sha(canonical(context))
    candidate=merge_candidate(context,intake);validate_candidate(candidate,context,intake)
    probe=isolation_roundtrip(drive,parent,candidate)
    target=BASELINE_NAME if args.formal else CANDIDATE_NAME
    if args.formal and os.environ.get('V70_FAMILY_FORMAL_ENABLED')!='true':raise RuntimeError('PM_FORMAL_ENABLEMENT_REQUIRED')
    result=checked_update(drive,target,parent,candidate,allow_formal=args.formal,verify=lambda raw:validate_candidate(json.loads(raw),context,intake))
    if not args.formal and drive.read(meta['id'])!=before:raise RuntimeError('FORMAL_BASELINE_CHANGED_DURING_CANDIDATE_PUBLISH')
    receipt={'schema':'V70.3/family-json-actions-receipt-v1','cutoff':cutoff,'phase':'11h_candidate_publish' if not args.formal else '11h_formal_publish','workflow_run_id':os.environ.get('GITHUB_RUN_ID'),'workflow_commit':os.environ.get('GITHUB_SHA'),'basis':basis,'intake_workflow_run_id':intake['workflow_run_id'],'isolation':probe,'write':result,'formal_baseline_file_id':meta['id'],'formal_baseline_sha256':sha(before),'formal_baseline_written':args.formal,'changes':candidate['round1_extension']['changes'],'private_source_evidence_archive':intake['private_evidence_archive']}
    checked_update(drive,'V70_Family_JSON_Round1_Actions_Receipt_20261117.json',parent,receipt)
    (args.work/'candidate.json').write_text(json.dumps(candidate,ensure_ascii=False,indent=2));(args.work/'private-write-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));write_registry(intake['source_registry'],args.work/'source-registry.csv')
    print(json.dumps({'phase':receipt['phase'],'status':result['status'],'sha256':result['sha256'],'bytes':result['bytes'],'isolation':'WRITE_READBACK_ROLLBACK_PASS','formal_gate':basis['status'],'formal_baseline_written':args.formal}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Deliberately avoid URLs, response bodies, tokens, identifiers and values in public logs.
        print(json.dumps({'status':'FAILED_PREVIOUS_FORMAL_RETAINED','error_type':type(exc).__name__,'reason_code':str(exc).split(':')[0][:160]}))
        raise SystemExit(1)
