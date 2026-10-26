/* One-shot execution of the existing V70 HTML. No external network or strategy copy. */
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto');
const {JSDOM}=require('jsdom');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
async function main(input){
 const root=path.resolve(input.repo_root);
 const html=fs.readFileSync(path.join(root,'系統工程/總經V70/V70-3-27.html'));
 const raw=fs.readFileSync(path.join(root,'系統工程/總經V70/V70_macro_latest.json'));
 if(hash(html)!==input.html_sha256||hash(raw)!==input.feed_sha256)throw Error('V70_SOURCE_CHANGED');
 const feed=JSON.parse(raw),stock=input.stock_percent,bond=input.bond_percent;
 if(![stock,bond].every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=100)
    ||Math.abs(stock+bond-100)>1e-8)throw Error('APPROVED_STRATEGIC_BASE_REQUIRED');
 const stamp=Date.parse(input.evaluation_at);
 if(!Number.isFinite(stamp)||Date.parse(feed.asOf)>stamp)throw Error('V70_EVALUATION_TIME_INVALID');
 const dom=new JSDOM(html.toString('utf8'),{runScripts:'outside-only',url:'https://family.invalid/V70-3-27.html'});
 const w=dom.window,NativeDate=w.Date;
 w.Date=class extends NativeDate{constructor(...a){super(...(a.length?a:[stamp]));}static now(){return stamp;}};
 // jsdom has no visual layout. These are DOM compatibility properties only.
 Object.defineProperty(w.HTMLElement.prototype,'innerText',{
  get(){return this.textContent;},set(v){this.textContent=v;},configurable:true});
 w.tailwind={};
 const warnings=[],reads=[];
 w.console.warn=(...args)=>warnings.push(args.map(String).join(' '));
 w.fetch=async url=>{
  const request=new URL(String(url),w.location);reads.push(request.pathname);
  if(request.origin==='https://family.invalid'&&request.pathname==='/V70_macro_latest.json')
   return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(feed))};
  // Optional website deployment badge has no calculation input in this runtime.
  return {ok:false,status:404,json:async()=>({})};
 };
 const errors=[];
 try{
  for(const script of w.document.querySelectorAll('script')){
   if(script.src||script.type==='application/json'||script.id==='v703-family-no-manual-inputs')continue;
   try{new vm.Script(script.textContent).runInContext(dom.getInternalVMContext(),{timeout:5000});}
   catch(e){errors.push({script_id:script.id,error:String(e.message)});}
  }
  for(let i=0;i<20;i++)await new Promise(setImmediate);
  if(errors.length)throw Error('V70_ORIGINAL_SCRIPT_ERROR:'+JSON.stringify(errors));
  if(w.setLivingWaterStrategicAllocation(stock,bond)!==true)throw Error('V70_BASE_REJECTED');
  const gates={data_complete:w.v703DataComplete===true,dates_verified:w.v703VerifiedDataDates===true,
   feed_verified:w.v703FeedVerified===true,demo:w.v703DemoMode===true,
   credit_blocked:w.v703CreditGateBlocked===true,can_publish:w.v703CanPublishFormalAllocation()===true};
  const snapshot=w.v703MacroSnapshot,latest=w.v703Latest;
  const ready=gates.can_publish&&!gates.demo&&snapshot?.allocation;
  return {schema_version:'Family.W8.OriginalV70.v1',status:ready?'V70_DATA_READY':'V70_DATA_UNAVAILABLE',
   source_html_sha256:hash(html),source_feed_sha256:hash(raw),feed_as_of:feed.asOf,
   evaluation_at:input.evaluation_at,strategic:{stock,bond},gates,
   tactical_percentages:ready?{stock:snapshot.allocation.sTot,bond:snapshot.allocation.bTot,
     dry_powder:snapshot.allocation.cTot}:null,
   macro_snapshot:snapshot,original_latest:latest,load_issue:w.v703FeedLoadIssue||'',warnings,
   local_reads:reads,ui_profile_defaults_are_not_client_facts:true,
   monetary_amounts:null,trade_authorization:'NONE'};
 }finally{w.close();}
}
let data='';
process.stdin.setEncoding('utf8');
process.stdin.on('data',s=>{data+=s;if(data.length>1048576)throw Error('INPUT_TOO_LARGE');});
process.stdin.on('end',()=>main(JSON.parse(data)).then(out=>process.stdout.write(JSON.stringify(out)))
 .catch(e=>{process.stderr.write(String(e.message));process.exitCode=1;}));
