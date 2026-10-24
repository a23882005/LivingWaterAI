"""W7-A01: malformed successful responses must not poison FRED fallback."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import requests
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('macro18_source',Path(__file__).resolve().parents[1]/'系統工程/總經V70/總經爬蟲18項.py')
macro=importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)

def response(text,status=200,kind='text/csv'):
    r=requests.Response();r.status_code=status;r._content=text.encode()
    r.headers['Content-Type']=kind;r.url='https://fred.stlouisfed.org/'
    return r

GOOD='observation_date,BAMLH0A0HYM2\n2026-10-20,3.33\n'

class SourceResponseTests(unittest.TestCase):
    def test_real_october_lei_report_and_three_month_merge(self):
        text=(Path(__file__).parent/'fixtures/pnc_lei_20261022.txt').read_text()
        url=macro.LEI_PNC_ROOT+'PNC_Economics_Research_LEI_22_October_2026.pdf'
        parsed=macro.parse_lei_pnc(text,url)
        self.assertEqual((parsed['publication_date'],parsed['observation_date'],parsed['value']),
                         ('2026-10-22','2026-09-01',-0.5))
        # Exercise the existing discovery/PDF parser/history producer, without
        # changing its merge/rotation logic or using live network in CI.
        listing=response('<a href="'+url+'">LEI</a>')
        pdf=response('%PDF fixture');pdf._content=b'%PDF fixture'
        f=SimpleNamespace(s=SimpleNamespace(get=lambda u,**kw:listing if u.endswith('.html') else pdf),timeout=5)
        with patch('pypdf.PdfReader',return_value=SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)])):
            result=macro.lei_verified_history(f)
        self.assertEqual((result['observation_date'],result['value']),('2026-09-01',-0.5))
        self.assertEqual([(r['observation_date'],r['value']) for r in f.lei_history],
                         [('2026-07-01',-1.1),('2026-08-01',-0.7),('2026-09-01',-0.5)])

    def test_lei_rejects_other_metrics_and_identifies_missing_fields(self):
        for metric in ['Six-month growth rate improved to 0.6%.','Monthly growth rate improved to 0.1%.','Index level rose to 99.6%.']:
            with self.subTest(metric=metric),self.assertRaisesRegex(ValueError,'annual growth'):
                macro.parse_lei_pnc('22 October 2026 (LEI) was unchanged in September. '+metric,macro.LEI_PNC_ROOT)
        with self.assertRaisesRegex(ValueError,'observation month'):
            macro.parse_lei_pnc('22 October 2026 year earlier growth rate improved to -0.5%.',macro.LEI_PNC_ROOT)

    def test_malformed_response_retried_without_cached_body(self):
        with patch.dict(macro.os.environ,{'FRED_API_KEY':''}), patch.object(requests.Session,'get',side_effect=[response('<html>temporary error</html>',kind='text/html'),response(GOOD)]) as get, patch.object(macro.time,'sleep'):
            f=macro.Fetcher();s=f.fred('BAMLH0A0HYM2')
            self.assertEqual(s.iloc[-1],3.33);self.assertEqual(get.call_count,2)
            self.assertEqual([x['result'] for x in f.fredattempts['BAMLH0A0HYM2']],['FAILED','OK'])
            self.assertEqual(f.fredattempts['BAMLH0A0HYM2'][0]['content_type'],'text/html')
            f.fred('BAMLH0A0HYM2');self.assertEqual(get.call_count,2)

    def test_repeated_malformed_response_stops_after_two(self):
        with patch.dict(macro.os.environ,{'FRED_API_KEY':''}), patch.object(requests.Session,'get',return_value=response('<html>bad</html>')) as get, patch.object(macro.time,'sleep'):
            f=macro.Fetcher()
            with self.assertRaises(RuntimeError):f.fred('BAMLH0A0HYM2')
            self.assertEqual(get.call_count,2)
            with self.assertRaises(RuntimeError):f.fred('BAMLH0A0HYM2')
            self.assertEqual(get.call_count,2)

    def test_rate_limit_is_not_retried_as_parse_error(self):
        with patch.dict(macro.os.environ,{'FRED_API_KEY':''}), patch.object(requests.Session,'get',return_value=response('limited',429)) as get:
            with self.assertRaises(RuntimeError):macro.Fetcher().fred('BAMLH0A0HYM2')
            self.assertEqual(get.call_count,1)

    def test_api_failure_then_csv_success_keeps_attempts_and_redacts_key(self):
        with patch.dict(macro.os.environ,{'FRED_API_KEY':'synthetic-test-secret'}), patch.object(requests.Session,'get',side_effect=[response('bad',kind='text/html'),response('bad',kind='text/html'),response(GOOD)]) as get, patch.object(macro.time,'sleep'):
            f=macro.Fetcher();f.fred('BAMLH0A0HYM2')
            self.assertEqual(get.call_count,3)
            self.assertNotIn('synthetic-test-secret',str(f.fredattempts))
            self.assertEqual(len(f.fredattempts['BAMLH0A0HYM2']),3)

    def test_valid_source_is_not_retried(self):
        with patch.dict(macro.os.environ,{'FRED_API_KEY':''}), patch.object(requests.Session,'get',return_value=response(GOOD)) as get:
            f=macro.Fetcher();f.fred('BAMLH0A0HYM2')
            self.assertEqual(get.call_count,1)
            self.assertEqual(f.fredattempts['BAMLH0A0HYM2'][0]['observation_date'],'2026-10-20')

if __name__=='__main__':unittest.main()
