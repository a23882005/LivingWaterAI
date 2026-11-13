import json,re,subprocess,unittest
from pathlib import Path
HTML=Path(__file__).resolve().parents[1]/'系統工程/總經V70/V70-3-27.html'
class AuxiliaryContractTests(unittest.TestCase):
 def test_missing_inputs_and_historical_isolation(self):
  html=HTML.read_text()
  def fn(name):
   start=html.index('function '+name+'('); end=html.index('\n}',start) if name in ('recalcNetLiquidity','updateCapBps') else html.index('\n        }',start)
   return html[start:end+len('\n        }') if name not in ('recalcNetLiquidity','updateCapBps') else end+2]
  js='''const assert=require('node:assert/strict');global.window={};const els={};global.document={getElementById:(id)=>els[id]||(els[id]={value:'',textContent:''})};function calcTotal(){};function _toNum(v){return v===''?NaN:Number(v)};'''
  js+='\n'.join(fn(n) for n in ('updateBond','v703SyncBondCard','recalcNetLiquidity','updateCapBps'))
  js+='''
  v703SyncBondCard({m05:{status:'OFFICIAL_UNAVAILABLE',value:null}});
  assert.equal(els['bond-score-display'].textContent,'NA');updateBond('2.64');assert.equal(els['bond-score-display'].textContent,'NA');
  v703SyncBondCard({m05:{status:'OK',value:2.6,dataDate:'2026-10-01'},m08:{value:2.86}});
  assert.equal(els['bond-cpi-yoy'].textContent,': 2.6%（2026-10-01）');assert.equal(els['bond-score-display'].textContent,'NA');assert.equal(els['bond-nominal-yield'].textContent,': NA');
  document.getElementById('in_m02').value='3.3';document.getElementById('cap_bps_m02');updateCapBps();assert.equal(els.cap_bps_m02.textContent,'330 bps');
  document.getElementById('in_m14').value='-5.92';recalcNetLiquidity();assert.equal(els.in_m14.value,'-5.92');
  // Existing mapping remains unchanged when future qualified inputs are explicitly wired.
  window.v703BondInputsQualified=true;
  for(const [x,y] of [[-1,'0.0'],[0.5,'5.0'],[2,'10.0']]){updateBond(x);assert.equal(els['bond-score-display'].textContent,y)}
  '''
  subprocess.run(['node','-e',js],check=True,capture_output=True,text=True)
 def test_no_static_current_bond_values(self):
  h=HTML.read_text();card=h[h.index('id="bond-nominal-yield"'):h.index('id="bond-score-display"')]
  for old in ('5.242%','2.6%','2.64%'):self.assertNotIn(old,card)
  self.assertIn('歷史教學範例：2026 年 1–2 月',h)

  self.assertNotIn("自動回寫到上方「淨流動性 Δ13W」欄位，用於所有計算",h)
  self.assertIn("歷史範例結果，不回寫當期指標、不參與當期計分",h)
