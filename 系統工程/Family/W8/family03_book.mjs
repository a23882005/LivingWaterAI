// Run on demand in the ChatGPT workspace. The caller owns Drive backup and readback.
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const runtime = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
const requireHere = createRequire(runtime ? path.join(runtime, '../package.json') : import.meta.url);
let artifactPath;
try {
  artifactPath = requireHere.resolve('@oai/artifact-tool');
} catch (error) {
  const request = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
  if (error.code !== 'MODULE_NOT_FOUND' || !request.input || !request.event || request.verify) throw error;
  const { execFileSync } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const writer = fileURLToPath(new URL('./family03_save.py', import.meta.url));
  execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', [writer, process.argv[2]], { stdio: 'inherit' });
  process.exit(0);
}
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(artifactPath).href);
const args = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const { member, input, output } = args;
const questions = JSON.parse(await fs.readFile(new URL('./family03_questions.json', import.meta.url),'utf8'));
const book = input ? await SpreadsheetFile.importXlsx(await FileBlob.load(input)) : Workbook.create();
const rows = Object.entries(questions);
const sheet = name => input ? book.worksheets.getItem(name) : book.worksheets.add(name);
const main=sheet('選擇進度'), alloc=sheet('標的及比例'), log=sheet('選擇歷程');
function header(s,ref) {
  const r=s.getRange(ref);
  r.format.fill='#175950';
  r.format.font.color='#ffffff';
  r.format.font.bold=true;
  r.format.rowHeight=25;
}
function widths(s,values) {
  values.forEach((v,i)=>s.getRangeByIndexes(0,i,1,1).format.columnWidth=v/7);
}
if (!input) {
  main.getRange('A1:B1').values=[['股票配置・選擇進度',member]];
  main.getRange('A2:B2').values=[['目前進度','尚未開始']];
  main.getRange('A3:B3').values=[['續選位置',rows[0][1][0]]];
  main.getRange('A4:B4').values=[['使用方式','登入家人專案選 03 作答。每份建議都能保留、修改，再由本人確認。']];
  main.getRange('A6:F6').values=[['題號','這一題要決定什麼','本次選擇','學習影片','原始影片網址','題目代碼']];
  rows.forEach(([key,[title,,label,id]],i)=>{
    const row=7+i, url='https://www.youtube.com/watch?v='+id;
    main.getRange('A'+row+':F'+row).values=[[i+1,title,null,label,url,key]];
    main.getRange('D'+row).formulas=[['=HYPERLINK(E'+row+',"'+label+'")']];
  });
  alloc.getRange('A1:B1').values=[['股票桶內配置',member]];
  alloc.getRange('A2:B2').values=[['狀態','尚未選擇標的']];
  alloc.getRange('A4:E4').values=[['角色','本人選的標的','占股票桶','系統試算比例','選擇狀態']];
  alloc.getRange('A5:A7').values=[['主軸'],['衛星'],['繁星']];
  alloc.getRange('B9').values=[['股票桶合計']];
  alloc.getRange('C9').formulas=[['=IF(COUNT(C5:C7)=0,"",SUM(C5:C7))']];
  alloc.getRange('C5:D9').setNumberFormat('0%');
  log.getRange('A1:L1').values=[['事件識別','台灣時間','家人','題目代碼','當時問題','當時選項','系統建議與結果','本人選擇','當時提供的影片','選擇狀態','作答後有效答案','方案識別']];
  header(main,'A1:F1'); header(main,'A6:F6'); header(alloc,'A1:E1'); header(alloc,'A4:E4'); header(log,'A1:L1');
  main.getRange('A7:F20').format.rowHeight=23;
  main.getRange('C7:C20').format.font.color='#164DB5';
  widths(main,[95,430,225,220,345,95]); widths(alloc,[100,155,115,125,165]);
  widths(log,[145,158,90,105,320,360,380,240,330,150,330,200]);
  main.freezePanes.freezeRows(6); log.freezePanes.freezeRows(1);
}
if (args.event) {
  const e=args.event;
  if(main.getRange('B1').values[0][0]!==member || log.getUsedRange().rowCount!==e.previous+1)
    throw Error('家人身分或選擇進度已變動');
  const lines=e.advice?.六組比較;
  if(lines){
    const table=book.worksheets.items.find(s=>s.name==='六組比較')||book.worksheets.add('六組比較');
    const titles=['時間','方案','股票配置','資料起日','資料迄日','幣別','狀態','期間報酬','年化報酬','最大回撤','年化波動','Sharpe','Sortino','Calmar','特點與取捨','共同成分或產業（已知百分點）','相對全 VT 的優點','相對全 VT 的代價'];
    table.getRangeByIndexes(0,0,1,titles.length).values=[titles];
    const data=lines.map(r=>{
      const h=r.歷史試算;
      return [e.time,r.名稱,Object.entries(r.股票桶百分比).map(([s,v])=>s+' '+v+'%').join('、'),h.起日,h.迄日,h.幣別,h.狀態,h.期間報酬率,h.年化報酬率,h.最大回撤幅度,h.年化波動率,h.Sharpe,h.Sortino,h.Calmar,[r.取捨,...(r.六組相對特點||[])].join('；'),r.共同曝險.共同曝險.map(x=>x.項目+' '+x.已知合計百分點).join('、')||'已知資料未列出重疊',r.相對優點.join('、'),r.相對代價.join('、')].map(x=>x??null);
    });
    const start=table.getUsedRange().rowCount;
    table.getRangeByIndexes(start,0,data.length,titles.length).values=data;
    table.getRangeByIndexes(start,7,data.length,4).setNumberFormat('0.00%');
    table.getRangeByIndexes(start,11,data.length,3).setNumberFormat('0.00');
    header(table,'A1:R1');widths(table,[180,88,280,120,120,70,180,105,105,105,105,90,90,90,360,400,330,330]);
    table.freezePanes.freezeRows(1);
  }
  if(e.advice?.本人偏好對照?.length){
    const preference=book.worksheets.items.find(s=>s.name==='本人偏好對照')||book.worksheets.add('本人偏好對照');
    preference.getRange('A1:I1').values=[['選擇時間','偏好來自','本人目標','年報區間','跌幅偏好','比較對象','歷史年報對照','歷史跌幅對照','家人版建議']];
    const checks=e.advice.本人偏好對照.flatMap(p=>p.六組對照.map(r=>[e.time,p.偏好來自,p.目標,p.年報區間,p.跌幅偏好,r.名稱,r.報酬對照,r.回撤對照,p.家人版建議]));
    const start=preference.getUsedRange().rowCount;
    preference.getRangeByIndexes(start,0,checks.length,9).values=checks;
    header(preference,'A1:I1');widths(preference,[195,105,220,165,165,110,145,190,540]);
    preference.freezePanes.freezeRows(1);
  }
  const advice=lines ? {六組比較:lines.map(r=>({...r,共同曝險:{共幾項:r.共同曝險.共同曝險.length,明細:'見六組比較頁'}}))} : e.advice;
  log.getRangeByIndexes(e.previous+1,0,1,12).values=[[e.id,e.time,member,e.key,e.title,
    JSON.stringify(e.options),JSON.stringify(advice),e.choice,e.url,e.stage,JSON.stringify(e.answers),e.token || '']];
  const steps={home:'選擇工作方案',goal:'投資目標',returns:'偏好年報酬',loss:'可接受跌幅',band:'選配置範圍',exact:'確認層級比重',theme:'選產業方向',symbol:'選標的',weight_band:'選標的比重範圍',weight:'選標的比例',fund:'資金來源',amount:'金額範圍',replace:'選擇擬換出的持股',review:'檢視完整方案',compare:'六組比較',reduce:'選減碼標的',increase:'選加碼標的',shift:'選移動比重'};
  main.getRange('B2:B3').values=[[e.stage],[steps[e.next]||e.next]];
  if(e.answers.schema===2){
    const st=e.answers;
    const roleNames=['主軸','衛星','繁星'];
    const names=['方案一','方案二','方案三'];
    const plan=st.plans[st.slot];
    main.getRange('A6:F20').clear();
    main.getRange('A6:D6').values=[['工作方案','主軸','衛星','繁星']];
    main.getRange('A7:D9').values=st.plans.map((p,i)=>[names[i],...roleNames.map(r=>
      Object.entries(p.layers[r]).map(([symbol,v])=>symbol+' '+v+'%').join('、')||'尚未選擇')]);
    main.getRange('A11:B12').values=[['目前方案',names[st.slot]],['最後指定',st.final?.方案||'尚未指定']];
    main.getRange('A14:B14').values=[['本案偏好',Object.values(plan.prefs).join('／')]];
    header(main,'A6:D6');
    alloc.getUsedRange().clear();
    alloc.getRange('A1:E1').values=[['方案','角色','標的','占股票部位','版本狀態']];
    const allocations=st.plans.flatMap((p,i)=>roleNames.flatMap(r=>
      Object.entries(p.layers[r]).map(([symbol,v])=>[names[i],r,symbol,v/100,'目前工作稿'])));
    if(allocations.length){
      alloc.getRangeByIndexes(1,0,allocations.length,5).values=allocations;
      alloc.getRangeByIndexes(1,3,allocations.length,1).setNumberFormat('0%');
    }
    header(alloc,'A1:E1');
    if(['save','final'].includes(e.key)){
      const archive=book.worksheets.items.find(s=>s.name==='方案版本')||book.worksheets.add('方案版本');
      archive.getRange('A1:G1').values=[['日期與時間','當時方案','主軸','衛星','繁星','當時決定','版本識別']];
      const cells=roleNames.map(r=>Object.entries(plan.layers[r]).map(([s,v])=>s+' '+v+'%').join('、')||'0%');
      archive.getRangeByIndexes(archive.getUsedRange().rowCount,0,1,7).values=[[e.time,names[st.slot],...cells,e.stage,e.id]];
      header(archive,'A1:G1');widths(archive,[195,100,280,280,280,180,290]);
      archive.freezePanes.freezeRows(1);
    }
  } else {
  rows.forEach(([k],i)=>{main.getRange('C'+(i+7)).values=[[e.answers[k]??null]]});
  alloc.getRange('B2').values=[[e.stage]];
  for(const [i,k] of ['core','sat','star'].entries()){
    const pct=e.mix?.[i], picked=e.answers[k];
    alloc.getRange('B'+(i+5)+':E'+(i+5)).values=[[picked||null,picked && pct!=null ? pct/100 : null,
      pct!=null ? pct/100 : null,picked ? e.stage : null]];
  }
  }
}
book.recalculate();
if(args.verify){
  const r=await book.inspect({kind:'table',range:'選擇進度!A6:E8',include:'values,formulas',tableMaxRows:3,tableMaxCols:5});
  if(!r.ndjson.includes('這一題'))throw Error('進度頁驗證失敗');
  for(const [s,r] of [['選擇進度','A1:D10'],['標的及比例','A1:E9'],['選擇歷程','A1:E2']]){
    const image=await book.render({sheetName:s,range:r,scale:1});
    await fs.writeFile(path.join(path.dirname(output),s+'.png'),new Uint8Array(await image.arrayBuffer()));
  }
}
await (await SpreadsheetFile.exportXlsx(book)).save(output);
