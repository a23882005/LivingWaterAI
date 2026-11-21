(() => {
  const {fields, tests, rules} = __V70_CAP_RULES__;
  const colors = {red:'#7f1d1d',orange:'#7c2d12',unknown:'#334155'};
  const titles = {red:'系統熔斷',orange:'橘牌｜危機或衰退風險加重',yellow:'黃牌｜股市波動升高',unknown:'資料待確認'};
  const notes = {
    yellow:'市場預期股市短期波動升高。CAP 限制本期總經分數；例如原始分數 53、上限 60，最後仍採 53 分。整戶配置已計入本期風險，已有部位依長期計畫持有。股票買點依 V82，債券買點依 V75 評估。',
    orange:'信用、資金、利率或景氣條件已達警示門檻。危機層兩項達標封頂 55 分，三項以上封頂 45 分；衰退層依本期就業與景氣條件封頂。整戶配置已採最嚴上限。原有部位依長期計畫持有，有可用資金再依 V82、V75 評估買點。',
    red:'VIX 達 28 且 MOVE 達 140，股債波動同時升高。暫停買賣與調倉，新資金暫留，原有股票、債券及等待資金維持原狀。解除後依當時的燈號與買點重新評估。',
    unknown:'部分風險指標缺值，本期牌色待確認。'
  };
  function evaluate(values) {
    const flags = {};
    for (const [key,[field,op,t]] of Object.entries(tests)) {
      const v=values[field];
      flags[key]=Number.isFinite(v)?(op==='ge'?v>=t:v<=t):null;
    }
    flags.B=flags.inflation===false||flags.rise===false?false:
      flags.inflation===null||flags.rise===null?null:true;
    let rows=rules.filter(r=>r.match.every(k=>flags[k.replace(/^!/,'')]===!k.startsWith('!')));
    if(rows.some(r=>r.layer==='衰退'&&r.cap===45)) rows=rows.filter(r=>r.layer!=='衰退'||r.cap!==55);
    const ids=rows.map(r=>r.id), cap=Math.min(100,...rows.map(r=>r.cap));
    const missing=Object.keys(fields).filter(k=>!Number.isFinite(values[k]));
    const level=ids.includes('01')?'red':missing.length?'unknown':cap<=55?'orange':ids.length?'yellow':'normal';
    return {ids,cap,level,missing};
  }
  function render(read) {
    const values=Object.fromEntries(Object.keys(fields).map(k=>[k,read(k)]));
    if(values.m02>=50) values.m02/=100;
    const result=evaluate(values), panel=document.getElementById('engineering-cap');
    const {level,ids,cap,missing}=result;
    panel.hidden=level==='normal';
    const lines=[], reasons={'恐慌':[],'危機':[],'衰退':[]}, layers={'恐慌':100,'危機':100,'衰退':100};
    const crisisPoints=[];
    for(const id of ids) {
      const r=rules.find(row=>row.id===id);
      const keys=r.match.filter(k=>!k.startsWith('!')).flatMap(k=>k==='B'?['inflation','rise']:[k]);
      if(id==='02'||id==='03') keys.push('!move140');
      if(id==='02') keys.push('!v35');
      const details=keys.map(k=>{
        const [field,op,t]=tests[k.replace(/^!/,'')];
        return fields[field]+' '+values[field]+(k.startsWith('!')?' < ':op==='ge'?' ≥ ':' ≤ ')+t;
      });
      layers[r.layer]=Math.min(layers[r.layer],r.cap);
      reasons[r.layer].push(details.join('，'));
      if(r.layer==='危機') crisisPoints.push(...r.match.filter(k=>!k.startsWith('!')));
      lines.push(id+'｜'+r.layer+'層 CAP '+r.cap+'｜'+details.join('，'));
    }
    const summary=level==='normal'?'':titles[level]+(level==='unknown'?'':'｜本期封頂 '+cap+' 分');
    panel.dataset.level=level;
    panel.querySelector('.cap-yellow-limit').textContent=level==='yellow'?'本期總經分數上限 '+cap+' 分':'';
    panel.style.backgroundColor=colors[level]||'';
    panel.querySelector('strong').textContent=summary;
    panel.querySelector('.cap-reasons').textContent=lines.join('\n');
    panel.querySelector('p').textContent=(notes[level]||'')+(missing.length?' 待確認：'+missing.map(k=>fields[k]).join('、'):'');
    panel.querySelector('small').hidden=level!=='red';
    for(const id of ['cap-allocation-note','cap-family-note']) {
      const el=document.getElementById(id);
      if(el) el.textContent=summary+(level==='red'?'｜整戶比例僅供參考，暫停買賣與調倉。':
        ['yellow','orange'].includes(level)?'｜整戶比例已計入封頂，股票依 V82、債券依 V75 評估。':'');
    }
    return {...result,layers,reasons,crisisPoints};
  }
  window.v70Cap={evaluate,render};
})();
