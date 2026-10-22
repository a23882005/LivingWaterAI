import copy,json,tempfile,unittest
from pathlib import Path
from test_d009_state import report
from macro18_state import snapshot,recover,read_diagnostics
from macro18_alert import evaluate

class DiagnosticsStateTests(unittest.TestCase):
 def test_same_observation_new_evidence_saved_without_rotation(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'in.json';raw=report(1)
   raw['items']['m02'].update(last_verified_at='2026-10-22T01:00:00Z',attempt_result='SUCCESS')
   p.write_text(json.dumps(raw));self.assertTrue(snapshot(p,root))
   raw['items']['m02']['last_verified_at']='2026-10-22T02:00:00Z';p.write_text(json.dumps(raw))
   self.assertFalse(snapshot(p,root));self.assertEqual(len(list((root/'backups').glob('*.json'))),1)
   latest=root/'macro18_latest_diagnostics.json'
   self.assertEqual(read_diagnostics(latest,raw)['items']['m02']['last_verified_at'],'2026-10-22T02:00:00Z')
   previous=latest.read_bytes();out=root/'recovery.json';recover(out,root)
   restored=json.loads(out.read_text());self.assertEqual(restored['items']['m02']['last_verified_at'],'2026-10-22T01:00:00Z')
   self.assertEqual(restored['items']['m02']['status'],'STALE');self.assertTrue(restored['items']['m02']['cache_used'])
   self.assertEqual(latest.read_bytes(),previous)
 def test_digest_and_batch_reject_tampering(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'in.json';raw=report(1);p.write_text(json.dumps(raw));snapshot(p,root)
   latest=root/'macro18_latest_diagnostics.json'
   with self.assertRaisesRegex(ValueError,'batch'):read_diagnostics(latest,report(2))
   d=json.loads(latest.read_text());d['report']['items']['m02']['error']='changed';latest.write_text(json.dumps(d))
   with self.assertRaisesRegex(ValueError,'digest'):read_diagnostics(latest)
 def test_usable_cache_source_failure_alerts_without_promoting_status(self):
  r={'items':{'m04':{'status':'USABLE','attempt_result':'FAILED','cache_used':True,'retrieval_error':'timeout','last_verified_at':'old'}}}
  state,alerts=evaluate(r,{},'2026-10-22');self.assertEqual(alerts[0]['error'],'timeout');self.assertEqual(alerts[0]['status'],'USABLE')
  self.assertTrue(alerts[0]['retrieval_failed']);self.assertEqual(state['indicators']['m04']['consecutive_failures'],1)
  r['items']['m04']['attempt_result']='SUCCESS';state,alerts=evaluate(r,state,'2026-10-23');self.assertEqual(alerts,[]);self.assertEqual(state['indicators']['m04']['consecutive_failures'],0)
if __name__=='__main__':unittest.main()
