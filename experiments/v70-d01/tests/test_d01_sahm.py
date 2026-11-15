"""Actual saved FRED400 replay plus clearly separate security/identity fixtures."""
import json,sys,tempfile,unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'candidate_code'))
from run_d01_sahm import ROOT,run

class D01Tests(unittest.TestCase):
    def test_actual_missing_key_response_is_blocked_without_fabricated_sample(self):
        body=(ROOT/'evidence/d01_live_client/SAHMREALTIME_metadata_response.json').read_bytes();calls=[]
        def actual_error_replay(url):
            calls.append(url);query=parse_qs(urlsplit(url).query)
            self.assertEqual(query['series_id'],['SAHMREALTIME']);self.assertNotIn('api_key',query)
            return 400,{'Content-Type':'application/json'},body
        with tempfile.TemporaryDirectory() as td:
            report=run(date(2026,11,15),td,environ={},sender=actual_error_replay)
            self.assertEqual(len(calls),1)
            self.assertEqual(report['status'],'BLOCKED_MISSING_CONTROLLED_FRED_API_KEY_INJECTION')
            self.assertEqual(report['minimum_missing_setting']['name'],'FRED_API_KEY')
            self.assertIsNone(report['technical_sample']);self.assertFalse(report['runtime_sample_admitted'])
            self.assertEqual(report['metadata']['error_code'],400)
            self.assertIn('api_key is not set',report['metadata']['error_message'])

    def test_controlled_credential_sentinel_never_reaches_any_output_file(self):
        # Synthetic noncredential sentinel exercises a server-error echo; no network call.
        sentinel='SYNTHETIC_D01_SENTINEL_NOT_A_REAL_KEY'
        calls=[]
        def fake_echo(url):
            calls.append(url);self.assertEqual(parse_qs(urlsplit(url).query)['api_key'],[sentinel])
            body=json.dumps({'error_code':400,'error_message':'Rejected URL '+url+' key='+sentinel}).encode()
            return 400,{'Content-Type':'application/json','ETag':sentinel},body
        with tempfile.TemporaryDirectory() as td:
            report=run(date(2026,11,15),td,environ={'FRED_API_KEY':sentinel},sender=fake_echo)
            self.assertEqual(len(calls),1);self.assertTrue(report['credential_present'])
            self.assertEqual(report['status'],'BLOCKED_CREDENTIAL_OR_API_ACCESS')
            self.assertTrue(report['requests'][0]['body_redacted'])
            self.assertNotEqual(report['requests'][0]['HTTP_body_sha256'],report['requests'][0]['archived_body_sha256'])
            for p in Path(td).rglob('*'):
                if p.is_file():self.assertNotIn(sentinel.encode(),p.read_bytes(),p.name)
            self.assertFalse(report['formal_state_modified']);self.assertFalse(report['public_app_use_approved'])

    def test_controlled_wrong_series_is_rejected_even_when_http_is200(self):
        # Identity-only synthetic metadata; contains no invented Sahm numerical value.
        def wrong_series(url):
            if urlsplit(url).path=='/fred/series':
                body={'seriess':[{'id':'SAHMCURRENT','title':'Sahm Rule Current','frequency':'Monthly','units':'Percentage Points'}]}
            else:body={'count':0,'observations':[]}
            return 200,{'Content-Type':'application/json'},json.dumps(body).encode()
        with tempfile.TemporaryDirectory() as td:
            report=run(date(2026,11,15),td,environ={'FRED_API_KEY':'SYNTHETIC_SENTINEL'},sender=wrong_series)
            self.assertEqual(report['status'],'BLOCKED_SERIES_DATA_OR_VINTAGE_QUALITY')
            self.assertIn('SAHMREALTIME identity',report['quality_error'])
            self.assertIsNone(report['technical_sample']);self.assertFalse(report['runtime_sample_admitted'])

if __name__=='__main__':unittest.main()
