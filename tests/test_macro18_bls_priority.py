"""BLS current U3/nonfarm priority, original calculations and fallback contracts."""
import json
from unittest import TestCase
from unittest.mock import patch
from test_macro18_free_source_priority import m, Session, Response


def payload(series, values):
    return {'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':series,'data':[
        {'year':'2026','period':f'M{month:02d}','value':str(v)} for month,v in values]}]}}


class BlsPriorityTests(TestCase):
    def fetcher(self,handler):
        session=Session(handler)
        with patch.object(m.requests,'Session',return_value=session):f=m.Fetcher()
        return f,session

    def test_current_u3_prefers_api_even_with_fred_key(self):
        body=payload('LNS14000000',[(10,4.1),(9,4.2)])
        with patch.dict(m.os.environ,{'FRED_API_KEY':'test-unused-key'}):
            f,s=self.fetcher(lambda u:Response(json.dumps(body)))
            r=m.latest(f,'m19','UNRATE')
        self.assertEqual(r['value'],4.1);self.assertEqual(r['unit'],'%')
        self.assertEqual(len(s.calls),1);self.assertIn('/LNS14000000',s.calls[0])
        self.assertEqual(f.fredsources['UNRATE'][0],'BLS_OFFICIAL_API')
        ev=f.fredattempts['UNRATE'][0];self.assertEqual(ev['series_id'],'LNS14000000')
        self.assertEqual(len(ev['response_sha256']),64)

    def test_nonfarm_original_three_changes_and_thousand_unit(self):
        body=payload('CES0000000001',[(7,159000),(8,159130),(9,159270),(10,159411)])
        with patch.dict(m.os.environ,{'FRED_API_KEY':'test-unused-key'}):
            f,s=self.fetcher(lambda u:Response(json.dumps(body)));r=m.nfp(f)
        self.assertEqual(r['value'],137);self.assertEqual(r['unit'],'千人')
        self.assertEqual(r['observation_date'],'2026-10-01')
        self.assertEqual(len(s.calls),1);self.assertIn('/CES0000000001',s.calls[0])

    def test_nonfarm_truncated_api_uses_original_bls_history_before_fred(self):
        short=payload('CES0000000001',[(9,159270),(10,159411)])
        full=payload('CES0000000001',[(7,159000),(8,159130),(9,159270),(10,159411)])
        f,s=self.fetcher(lambda u:Response(json.dumps(short)))
        with patch.object(s,'post',return_value=Response(json.dumps(full))) as history:r=m.nfp(f)
        self.assertEqual(r['value'],137);self.assertEqual(len(s.calls),1)
        self.assertIn('/v2/timeseries/data/',history.call_args.args[0])
        self.assertEqual([a['result'] for a in f.fredattempts['PAYEMS']],['FAILED','OK'])

    def test_all_bls_http_failures_continue_to_existing_fred_csv(self):
        body='observation_date,PAYEMS\n2026-07-01,159000\n2026-08-01,159130\n2026-09-01,159270\n2026-10-01,159411\n'
        f,s=self.fetcher(lambda u:Response(body) if 'fredgraph.csv' in u else Response('',503))
        with patch.dict(m.os.environ,{'FRED_API_KEY':''}),patch.object(s,'post',return_value=Response('',503)),patch.object(m.time,'sleep'):
            r=m.nfp(f)
        self.assertEqual(r['value'],137);self.assertEqual(f.fredsources['PAYEMS'][0],'FRED_CSV')

    def test_wrong_bls_series_is_rejected_before_history_backup(self):
        wrong=payload('WRONG',[(10,4.1)])
        correct=payload('CES0000000001',[(7,159000),(8,159130),(9,159270),(10,159411)])
        f,s=self.fetcher(lambda u:Response(json.dumps(wrong)))
        with patch.object(s,'post',return_value=Response(json.dumps(correct))):r=m.nfp(f)
        self.assertEqual(r['value'],137);self.assertIn('SERIES mismatch',f.fredattempts['PAYEMS'][0]['error'])

    def test_annual_average_not_used_as_latest_month(self):
        body=payload('LNS14000000',[(10,4.1),(13,99)])
        f,s=self.fetcher(lambda u:Response(json.dumps(body)));r=m.latest(f,'m19','UNRATE')
        self.assertEqual(r['value'],4.1);self.assertEqual(r['observation_date'],'2026-10-01')

    def test_nonconsecutive_months_fail_both_bls_and_fred(self):
        body=payload('CES0000000001',[(6,158900),(7,159000),(9,159270),(10,159411)])
        f,s=self.fetcher(lambda u:Response(json.dumps(body)))
        with patch.object(s,'post',return_value=Response(json.dumps(body))),self.assertRaises(RuntimeError):m.nfp(f)

    def test_sahm_history_keeps_original_fred_priority_with_key(self):
        body={'observations':[{'date':'2026-10-01','value':'4.1'}]}
        with patch.dict(m.os.environ,{'FRED_API_KEY':'test-unused-key'}):
            f,s=self.fetcher(lambda u:Response(json.dumps(body)));f.fred('UNRATE',require_history=True)
        self.assertIn('api.stlouisfed.org',s.calls[0])
