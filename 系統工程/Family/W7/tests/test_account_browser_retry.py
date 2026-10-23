"""Execute the actual browser script; lost replies retain one request identity."""
import json
from pathlib import Path
import re
import subprocess
import pytest

@pytest.mark.parametrize('mode,expected',[('500',2),('network',2),('401',1),('exhausted',3),('pending',2)])
def test_browser_retry_retains_request_identity(mode,expected):
    page=(Path(__file__).resolve().parents[1]/'account_login.html').read_text()
    script=re.search(r'<script nonce="__NONCE__">(.*?)</script>',page,re.S).group(1)
    harness='''
const assert=require('node:assert/strict');
const nodes={'#status':{textContent:''},'meta[name="family-csrf"]':{content:'csrf'},'#session':{},'#logout':{}};
global.document={querySelector:s=>nodes[s],querySelectorAll:()=>[]};
global.location={pathname:'/family/index.php'};
global.crypto=require('node:crypto').webcrypto;
global.setTimeout=callback=>callback();
const sent=[];
global.fetch=async(url,options)=>{
 sent.push({url,body:options.body});
 if(mode==='pending'&&sent.length===1)return {status:202,json:async()=>({pending:'a'.repeat(48)})};
 if(mode==='network'&&sent.length===1)throw new Error('connection lost');
 const status=mode==='401'?401:(mode==='exhausted'||(mode==='500'&&sent.length===1)?500:200);
 return {status,ok:status===200,json:async()=>{assert.notEqual(status,500);return status===401?{error:'AUTH_REQUIRED'}:{result:{expires_at:1234567890}};}};
};
'''
    tail='''
(async()=>{await request('login',{user_id:'synthetic',password:'synthetic-only'});
 assert.equal(sent.length,expected);assert.ok(JSON.parse(sent[0].body).request_id.length>=16);
 if(mode==='pending'){assert.equal(sent[1].body,undefined);assert.equal(sent[1].url,'/family/index.php/_result/'+'a'.repeat(48));}
 else{assert.ok(sent.every(x=>x.body===sent[0].body));assert.ok(sent.every(x=>x.url==='/family/index.php/login'));}
 assert.ok(!nodes['#status'].textContent.includes('synthetic-only'));
})().catch(error=>{console.error(error);process.exit(1);});
'''
    run=subprocess.run(['node','-e','const mode='+json.dumps(mode)+';const expected='+str(expected)+';'+harness+script+tail],capture_output=True,timeout=10)
    assert run.returncode==0,run.stderr.decode()
