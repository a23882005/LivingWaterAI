import contextlib,csv,datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from validate_macro18_outputs import validate_outputs
from test_macro18_source_response import macro

class DiagnosticsTests(unittest.TestCase):
 def test_failed_fetch_cache_preserves_error_and_three_outputs(self):
  class Fake:
   def __init__(self):self.fredattempts={}
  def failed(f,*a):
   f.job_series.add('BAMLH0A0HYM2');f.fredattempts['BAMLH0A0HYM2']=[{'provider':'FRED_CSV','result':'FAILED','error':'synthetic timeout','attempted_at':'2026-10-22T01:00:00Z'}]
   raise RuntimeError('synthetic timeout')
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   for name in ('latest','breakeven_5y','month_delta','netliq','sahm_from_unrate','nfp','core_cpi','yahoo_price','cnn','lei_verified_history'):
    stack.enter_context(patch.object(macro,name,side_effect=failed))
   stack.enter_context(patch.object(macro,'Fetcher',Fake))
   prior=macro.row('m02',3.3,dt.date.today().isoformat(),'https://fred.stlouisfed.org/series/BAMLH0A0HYM2','fixture')
   prior.update(last_verified_at='2026-10-20T01:00:00Z',source_evidence={'fixture':'original evidence'})
   cache=Path(tmp)/'prior.json';cache.write_text(json.dumps({'generated_at':'2026-10-20T02:00:00Z','items':{'m02':prior}}))
   result=macro.run(Path(tmp)/'out',cache_path=cache);r=result['items']['m02']
   self.assertEqual(r['status'],'STALE');self.assertEqual(r['error'],'synthetic timeout')
   self.assertEqual(r['last_verified_at'],prior['last_verified_at']);self.assertTrue(r['cache_used'])
   self.assertEqual(r['cache_source']['observation_date'],prior['observation_date'])
   with (Path(tmp)/'out/18_macro_verification.csv').open(encoding='utf-8-sig') as stream:
    rows={r['id']:r for r in csv.DictReader(stream)}
   self.assertEqual(json.loads(rows['m02']['source_attempts']),r['source_attempts'])
   self.assertEqual(json.loads(rows['m02']['cache_source']),r['cache_source'])
   report=(Path(tmp)/'out/18_macro_report.md').read_text();self.assertIn('synthetic timeout',report);self.assertIn('2026-10-20T01:00:00Z',report)
   self.assertEqual(json.loads((Path(tmp)/'out/18_macro_verification.json').read_text())['items']['m02'],r)
   self.assertEqual(validate_outputs(Path(tmp)/'out'),19)
   csvpath=Path(tmp)/'out/18_macro_verification.csv'
   csvpath.write_text(csvpath.read_text(encoding='utf-8-sig').replace('synthetic timeout','erased'),encoding='utf-8-sig')
   with self.assertRaises(ValueError):validate_outputs(Path(tmp)/'out')
 def test_netliq_common_wednesday_and_exact_13_weeks(self):
  dates=pd.to_datetime(['2026-07-15','2026-10-14','2026-10-15'])
  series={'WALCL':pd.Series([10000,12000,15000],index=dates),'WDTGAL':pd.Series([1000,1500,2000],index=dates),'RRPONTSYD':pd.Series([1,1.25,3],index=dates)}
  class F:
   def fred(self,s):return series[s]
  r=macro.netliq(F());self.assertEqual(r['observation_date'],'2026-10-14');self.assertEqual(r['value'],1.25)
  series['WDTGAL']=series['WDTGAL'].drop(pd.Timestamp('2026-07-15'))
  with self.assertRaisesRegex(ValueError,'13'):macro.netliq(F())
if __name__=='__main__':unittest.main()
