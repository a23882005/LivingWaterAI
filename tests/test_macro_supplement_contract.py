import importlib.util,sys,unittest,copy
from pathlib import Path
from test_v703_policy_evidence import policy,NOW
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_macro_supplement import validate

def payload():
 r=policy();items={'m06_rate':r}
 for k,date in [('m06_inf','2026-09-30'),('m06_rstar','2026-06-30'),('m06_output_gap','2026-06-30'),('s05','2026-10-21'),('m03_qqq','2026-10-21'),('m03_spy','2026-10-21'),('m03_vt','2026-10-21')]:
  items[k]=dict(value=2.0,observation_date=date,status='OK',method='synthetic fixture',source_url='https://example.com',candidate_checks=copy.deepcopy(r['candidate_checks']))
 for k in ('m03_qqq','m03_spy','m03_vt'):
  for c in items[k]['candidate_checks']:c.update(url='https://example.com',value=2.0,metric_or_horizon='Forward P/E')
 return dict(schema='V70.3/10h-eight-supplement-v3',generated_at=NOW.isoformat(),as_of_taipei=NOW.astimezone(__import__('datetime').timezone(__import__('datetime').timedelta(hours=8))).isoformat(),items=items)
class SupplementTests(unittest.TestCase):
 def test_complete_fixture(self):self.assertEqual(validate(payload(),NOW),[])
 def test_missing_extra_policy_and_stale(self):
  for kind in ('missing','extra','policy','stale','malformed_checks'):
   p=payload()
   if kind=='missing':del p['items']['s05']
   elif kind=='extra':p['items']['m06']=dict(value=1)
   elif kind=='policy':del p['items']['m06_rate']['source_evidence']
   elif kind=='malformed_checks':p['items']['m03_qqq']['candidate_checks']=None
   else:p['generated_at']='2026-10-20T00:00:00Z'
   self.assertTrue(validate(p,NOW),kind)
 def test_prompt_preserves_original(self):
  import json
  root=Path(__file__).resolve().parents[1]/'系統工程/Family/W7'
  original=json.loads((root/'evidence/A04/task_before.json').read_text())
  prompt=(root/'A04_Task提示詞_待A13切換.txt').read_text()
  self.assertTrue(prompt.startswith(original['prompt']))
  for field in ('source_evidence','last_verified_at','26小時','提交後','3／6／12'):self.assertIn(field,prompt)
if __name__=='__main__':unittest.main()
