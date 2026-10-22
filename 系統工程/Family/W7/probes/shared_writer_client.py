"""Build temporary authenticated bridge; verify hosted queue -> Drive receipts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import hosted_entry_client as hosted
from actions_drive_write_probe import Drive

ROOT=Path('build/family-b04-shared')

def build():
    hosted.build()
    config=json.loads(hosted.PRIVATE.read_text())
    run=config['run']
    public=ROOT/'public'; private=ROOT/'private'
    public.mkdir(parents=True,exist_ok=True);private.mkdir(parents=True,exist_ok=True)
    bridge='''
set_time_limit(300);
function drive_call($body) {
    $script=dirname(__DIR__,2).'/.family-b04-shared-__RUN_ID__/shared_drive_writer.py';
    $pipes=[];
    $process=proc_open(['python3',$script,'call'],[0=>['pipe','r'],1=>['pipe','w'],2=>['file','/dev/null','a']],$pipes);
    if (!is_resource($process)) throw new Exception('WRITER_UNAVAILABLE');
    fwrite($pipes[0],json_encode($body));fclose($pipes[0]);
    $reply=stream_get_contents($pipes[1],8192);fclose($pipes[1]);
    $code=proc_close($process);
    $result=json_decode($reply,true);
    if ($code!==0 || !is_array($result) || !isset($result['value'])) throw new Exception('WRITER_RETRY');
    return (int)$result['value'];
}
'''.replace('__RUN_ID__',run)
    php=(hosted.ROOT/'public/index.php').read_text()
    php=php.replace("$db=null;",bridge+"\n$db=null;")
    php=php.replace('SELECT seq,delta FROM jobs','SELECT seq,delta,request_id FROM jobs')
    old="""$query('UPDATE counters SET value=value+? WHERE account=?',[$job['delta'],$account]);
                    $v=$query('SELECT value FROM counters WHERE account=?',[$account])->fetchColumn();"""
    new="""$v=drive_call(['account'=>$account,'request_id'=>$job['request_id'],'delta'=>(int)$job['delta']]);"""
    assert old in php;php=php.replace(old,new)
    old="$v=$query('SELECT value FROM counters WHERE account=?',[$account])->fetchColumn();"
    assert old in php;php=php.replace(old,"$v=drive_call(['account'=>$account]);")
    php=php.replace('.family-w7-probe-', '.family-b04-shared-')
    (public/'index.php').write_text(php)
    for name in ['shared_drive_writer.py','actions_drive_write_probe.py']:
        shutil.copyfile(Path(__file__).with_name(name),private/name)
    names=('FAMILY_DRIVE_CLIENT_ID','FAMILY_DRIVE_CLIENT_SECRET','FAMILY_DRIVE_REFRESH_TOKEN')
    private_config={'run':run,'oauth':{n:os.environ[n] for n in names}}
    (private/'config.json').write_text(json.dumps(private_config));(private/'config.json').chmod(0o600)
    (ROOT/'test-keys.json').write_text(json.dumps(config));(ROOT/'test-keys.json').chmod(0o600)

def verify():
    config=json.loads((ROOT/'test-keys.json').read_text());keys=config['keys'];run=config['run']
    base=(os.environ.get('SITE_BASE_URL') or 'https://www.happihelp.com').rstrip('/')
    if not base.startswith('https://'): raise ValueError('HTTPS_REQUIRED')
    url=base+'/family-b04-shared-'+run+'/index.php?op='
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect());checks=[]
    def call(who,op,body=None):
        req=urllib.request.Request(url+op,data=json.dumps(body or {}).encode(),headers={'Authorization':'Bearer '+keys.get(who,'invalid'),'Content-Type':'application/json'})
        try:
            with opener.open(req,timeout=180) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            with e:return e.code,json.load(e)
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    check('unauthenticated_rejected',call('bad','read')[0]==401)
    check('action_cannot_login',call('actionA','login')[0]==403)
    first=call('chatA','login')[1]['result'];call('chatB','login')
    check('fixed_four_hours',first['expires']-first['issued']==14400)
    check('separate_connection_resume',call('chatA','resume')[1]['result']==first)
    check('identity_override_rejected',call('chatA','read',{'account':'synthetic-B'})[0]==400)
    check('action_queues_for_chat',call('actionA','submit',{'request_id':'one','delta':7})[0]==200)
    check('chat_drains_to_drive',call('chatA','drain')[1]['result']['value']==7)
    check('duplicate_receipt',call('actionA','submit',{'request_id':'one','delta':7})[1]['result']['state']=='DONE')
    check('collision_rejected',call('actionA','submit',{'request_id':'one','delta':9})[0]==409)
    def submit(n):return call('chatA' if n%2 else 'actionA','submit',{'request_id':'parallel-'+str(n),'delta':1})
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(submit,[0,1,2,3,0,1,2,3]))
    check('parallel_chat_action_queue',all(x[0]==200 for x in results))
    check('parallel_exact_once',call('actionA','drain')[1]['result']['value']==11)
    call('actionA','submit',{'request_id':'crash-after-upload','delta':5})
    check('lost_commit_ack_returns_retry',call('chatA','drain')[0]==503)
    check('restart_recovers_without_double_apply',call('actionA','drain')[1]['result']['value']==16)
    check('queue_receipt_after_recovery',call('chatA','status',{'request_id':'crash-after-upload'})[1]['result']['state']=='DONE')
    check('other_account_unchanged',call('chatB','read')[1]['result']['value']==0)
    check('other_account_receipt_denied',call('chatB','status',{'request_id':'one'})[0]==404)
    call('chatA','submit',{'request_id':'cancel','delta':90});call('chatA','logout')
    check('logout_revokes_action',call('actionA','read')[0]==401)
    call('chatA','login')
    check('logout_cancels_pending',call('chatA','status',{'request_id':'cancel'})[1]['result']['state']=='CANCELLED')
    check('relogin_preserves_drive_data',call('chatA','read')[1]['result']['value']==16)
    payload=Drive().read()
    with tempfile.TemporaryDirectory() as f:
        path=Path(f)/'readback.db';path.write_bytes(payload)
        with sqlite3.connect(path) as db:
            check('independent_actions_drive_readback',db.execute("select value from b04s_counters where account='synthetic-A'").fetchone()==(16,))
            check('six_unique_drive_receipts',db.execute('select count(*) from b04s_receipts').fetchone()==(6,))
            check('original_source_table_preserved',db.execute("select count(*) from sqlite_master where type='table' and name not like 'b04s_%'").fetchone()[0]>0)
    return {'schema':'Family-B04-shared-writer-v1','status':'PASS','scope':'TEMP_ONLY_HOSTED_QUEUE_TO_DRIVE','run':run,'checks':checks,'count':len(checks),'drive_sha256_before_cleanup':hashlib.sha256(payload).hexdigest()}

if __name__=='__main__':
    os.umask(0o077)
    if sys.argv[1]=='build':build()
    else:
        try:report=verify()
        except Exception as e:
            report={'status':'FAIL','error_type':type(e).__name__}
            if isinstance(e,AssertionError):report['check']=str(e)
        (ROOT/'proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        if report['status']!='PASS':raise SystemExit(1)
