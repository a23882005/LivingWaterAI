// Run on demand in the ChatGPT workspace. The caller owns Drive backup and readback.
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const runtime = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
const requireHere = createRequire(runtime ? path.join(runtime, '../package.json') : import.meta.url);
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(requireHere.resolve('@oai/artifact-tool')).href);
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
  log.getRangeByIndexes(e.previous+1,0,1,12).values=[[e.id,e.time,member,e.key,e.title,
    JSON.stringify(e.options),JSON.stringify(e.advice),e.choice,e.url,e.stage,JSON.stringify(e.answers),e.token || '']];
  main.getRange('B2:B3').values=[[e.stage],[e.next]];
  rows.forEach(([k],i)=>{main.getRange('C'+(i+7)).values=[[e.answers[k]??null]]});
  alloc.getRange('B2').values=[[e.stage]];
  for(const [i,k] of ['core','sat','star'].entries()){
    const pct=e.mix?.[i], picked=e.answers[k];
    alloc.getRange('B'+(i+5)+':E'+(i+5)).values=[[picked||null,picked && pct!=null ? pct/100 : null,
      pct!=null ? pct/100 : null,picked ? e.stage : null]];
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
