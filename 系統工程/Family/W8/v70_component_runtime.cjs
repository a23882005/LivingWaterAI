const fs=require('fs'),vm=require('vm'),Module=require('module'),crypto=require('crypto');
const ac=new Module('native-acorn');ac._compile(process.binding('natives')['internal/deps/acorn/acorn/dist/acorn'],'native-acorn');const parse=ac.exports.parse;
const input=JSON.parse(fs.readFileSync(0,'utf8'));const root=input.repo_root,feedPath=input.feed_path||root+'/系統工程/總經V70/V70_macro_latest.json',html=fs.readFileSync(root+'/系統工程/總經V70/V70-3-27.html','utf8'),feed=JSON.parse(fs.readFileSync(feedPath));
const sources=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)].filter(m=>!m[1].includes('src=')&&!m[1].includes('application/json')).map(m=>m[2]);
const hash=s=>crypto.createHash('sha256').update(s).digest('hex');if(hash(html)!==input.html_sha256||hash(fs.readFileSync(feedPath))!==input.feed_sha256)throw Error('V70_SOURCE_CHANGED');
if(!feed.verification?.ready)throw Error('V70_SOURCE_NOT_READY');
const keep=new Set(['macroConfig','C_VALUATION_IDS','C_VALUATION_ALPHA','lifeStageLabels']);const selected=[];
for(const s of sources){let ast;try{ast=parse(s,{ecmaVersion:'latest'})}catch{continue}for(const n of ast.body){if(n.type==='FunctionDeclaration')selected.push(s.slice(n.start,n.end));if(n.type==='VariableDeclaration'&&n.declarations.some(d=>keep.has(d.id.name)))selected.push(s.slice(n.start,n.end));if(n.type==='ExpressionStatement'&&n.expression.type==='AssignmentExpression'&&s.slice(n.expression.left.start,n.expression.left.end)==='window.v703StressModel')selected.push(s.slice(n.start,n.end));}}
const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',style:{},classList:{toggle(){},add(){},remove(){}},get innerText(){return this.textContent},set innerText(v){this.textContent=v}});return nodes.get(id)}
const ctx={console,document:{getElementById:id=>id.startsWith('input-')?null:node(id),querySelector:()=>null},window:null};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(selected.join('\n'),ctx);
vm.runInContext('globalThis.config=macroConfig',ctx);
for(const c of ctx.config){const r=feed.indicators[c.id]||feed.derived?.[c.id];if(!r||!Number.isFinite(Number(r.value)))throw Error('Missing '+c.id);node('in_'+c.id).value=String(r.value);node('sc_'+c.id).textContent=String(ctx.v703RiskForConfig(c,Number(r.value)));}
if(![input.stock_percent,input.bond_percent].every(n=>Number.isFinite(n)&&n>=0&&n<=100)||input.stock_percent+input.bond_percent!==100)throw Error('APPROVED_STRATEGIC_BASE_REQUIRED');
const lifeKnown=typeof input.life_stage_code==='string'&&/^L(?:[1-9]|10)$/.test(input.life_stage_code);
if(input.life_stage_code!=null&&!lifeKnown)throw Error('INVALID_LIFE_STAGE_CODE');
node('strategic-stock').value=String(input.stock_percent);node('strategic-bond').value=String(input.bond_percent);node('life-stage-select').value=lifeKnown?input.life_stage_code:'';node('bond-score-display').textContent='NA';
// Disable only the UI publish branch. No formal-publish readiness is claimed.
ctx.v703ApplyM06Derived();ctx.v703CanPublishFormalAllocation=()=>false;ctx.captureLivingWaterV70State=s=>{ctx.captured=s};ctx.calcTotal();
const s=ctx.captured;const result=ctx.calcAlloc(s.mSafe_final,s.bScore,s.isEmerg,{groupRisk:s.groupRisk,cap_panic:s.cap_panic,cap_crisis:s.cap_crisis,cap_recession:s.cap_recession});
const probes=[0,4.9,5,6.9,7,10].map(b=>ctx.calcAlloc(s.mSafe_final,b,s.isEmerg,{groupRisk:s.groupRisk,cap_panic:s.cap_panic,cap_crisis:s.cap_crisis,cap_recession:s.cap_recession}).meta);
const independent=probes.every(a=>['sTot','bTot','cTot','T'].every(k=>a[k]===result.meta[k]));
if(!independent)throw Error('BOND_SCORE_SOURCE_REQUIRED_FOR_TACTICAL_RESULT');
// Life-stage metadata is not inferred from a missing profile. Explicit S0/B0
// above own this numerical run; never label another member as a student.
if(!lifeKnown){result.meta.lifeStageCode='UNKNOWN';result.meta.lifeStageLabel='UNKNOWN';}
console.log(JSON.stringify({schema_version:'Family.W8.V70ComponentCalculation.v1',snapshot:s,allocation:result.meta,
source_html_sha256:hash(html),source_feed_sha256:input.feed_sha256,feed_as_of:feed.asOf,
scope:'ORIGINAL_NUMERIC_COMPONENTS_NOT_FORMAL_PUBLISH',bond_score_source:'UNKNOWN',bond_score_does_not_affect_this_allocation:independent,
call_trace:['V70.v703ApplyM06Derived','V70.v703RiskForConfig','V70.calcTotal','V70.v703StressModel','V70.calcAlloc'],trade_authorization:'NONE'}));
