import json,pathlib,subprocess,unittest,re
from test_v703_policy_evidence import policy,b,NOW
HTML=pathlib.Path(__file__).resolve().parents[1]/'系統工程/總經V70/V70-3-27.html'
def node(code,p):
 s=HTML.read_text();a=s.index('        // W7-A03:');p['source']=s[a:s.index('        function v703BuildDateControls()',a)]
 pre="const vm=require('vm'),assert=require('assert');const p=JSON.parse(require('fs').readFileSync(0,'utf8'));const c={window:{},URL,Date,macroConfig:[],document:{getElementById:()=>null}};vm.createContext(c);vm.runInContext(p.source,c);"
 r=subprocess.run(['node','-e',pre+code],input=json.dumps(p),text=True,capture_output=True)
 if r.returncode:raise AssertionError(r.stderr)
class FrontendTests(unittest.TestCase):
 def test_shared_backend_frontend_cases(self):
  from policy_case_matrix import cases
  shared=[dict(name=n,row=b._normalize(r,'m06_rate'),valid=expected,now=t.timestamp()*1000) for n,r,t,expected in cases()]
  node('for(const x of p.cases)assert.strictEqual(c.v703PolicyIssues(x.row,x.now).length===0,x.valid,x.name);',dict(cases=shared))
 def test_action_rechecks_time_and_edits(self):
  node('''
let now=p.now; class Clock extends Date {constructor(...a){super(...(a.length?a:[now]));} static now(){return now;}} c.Date=Clock;
const elements={};c.document.getElementById=id=>elements[id]||null;c.macroConfig=[{id:'m06_rate'}];
function reset(){now=p.now;Object.assign(c.window,{v703FeedVerified:true,v703DemoMode:false,v703DataComplete:true,v703CreditGateBlocked:false,v703LEIHistoryVerified:true,v703VerifiedInputSnapshot:{m06_rate:structuredClone(p.row)},v703SourceBatch:{asOf:new Date(now).toISOString()}});elements.in_m06_rate={value:String(p.row.value)};elements['v703-date-m06_rate']={value:p.row.dataDate};elements['v703-source-m06_rate']={value:p.row.source};}
reset();assert.strictEqual(c.window.v703CanPublishFormalAllocation(),true);
for(const [field,value] of [['in_m06_rate','4.2'],['v703-date-m06_rate','2026-07-29'],['v703-source-m06_rate','https://example.com']]){reset();elements[field].value=value;assert.strictEqual(c.window.v703CanPublishFormalAllocation(),false);}
reset();c.window.v703SourceBatch.asOf=new Date(now-26*3600000+1).toISOString();assert.strictEqual(c.window.v703CanPublishFormalAllocation(),true);now++;assert.strictEqual(c.window.v703CanPublishFormalAllocation(),false);
reset();now=Date.parse(p.row.retrievalTime)+26*3600000;c.window.v703SourceBatch.asOf=new Date(now).toISOString();assert.strictEqual(c.window.v703CanPublishFormalAllocation(),false);
reset();c.window.v703DemoMode=true;assert.strictEqual(c.window.v703CanPublishFormalAllocation(),false);
reset();c.window.v703FeedVerified=false;assert.strictEqual(c.window.v703CanPublishFormalAllocation(),false);
''',dict(row=b._normalize(policy(),'m06_rate'),now=NOW.timestamp()*1000))
 def test_all_inline_script_syntax(self):
  scripts=[c for a,c in re.findall(r'<script\b([^>]*)>(.*?)</script>',HTML.read_text(),re.S) if 'application/json' not in a and c.strip()]
  node('for(const source of p.scripts)new vm.Script(source);',dict(scripts=scripts))
if __name__=='__main__':unittest.main()
