"""W7-A01: malformed successful responses must not poison FRED fallback."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import requests

spec=importlib.util.spec_from_file_location('macro18_source',Path(__file__).resolve().parents[1]/'系統工程/總經V70/總經爬蟲18項.py')
macro=importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)

def response(text,status=200,kind='text/csv'):
    r=requests.Response();r.status_code=status;r._content=text.encode()
    r.headers['Content-Type']=kind;r.url='https://fred.stlouisfed.org/'
    return r

GOOD='observation_date,BAMLH0A0HYM2\n2026-10-20,3.33\n'

class SourceResponseTests(unittest.TestCase):
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
