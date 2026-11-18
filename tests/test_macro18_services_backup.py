"""Verify the original collector switches sources without relaxing ISM identity."""
import datetime as dt
import importlib.util
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import requests
from scripts.ism_services_backup import SERVICES_BACKUP_URL, parse_services_pmi

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('macro_services_backup',ROOT/'系統工程/總經V70/總經爬蟲18項.py')
macro=importlib.util.module_from_spec(spec);spec.loader.exec_module(macro)
REAL_DATETIME=dt.datetime
class Clock(REAL_DATETIME):
    @classmethod
    def now(cls,tz=None):return REAL_DATETIME(2026,11,18,14,tzinfo=dt.timezone.utc).astimezone(tz)

def fixture(value='54.5',month='October',publication='2026-11-04'):
    headline=f'The ISM Services PMI decreased to {value} in {month} 2026, compared to forecasts.'
    return ("<html><script>TEAlertsName='United States ISM Services PMI'; TESymbol='UNITEDSTANONMANPMI';</script>"
            '<p>Institute for Supply Management</p><h2 id="description">'+headline+'</h2>'
            '<div class="comment more">'+headline+'</div><small class="te-stream-date">'+publication+'</small>'
            '<p>Business Activity 99.9; New Orders 88.8</p></html>').encode()

class Response:
    def __init__(self,body,status=200,url=SERVICES_BACKUP_URL):self.content=body;self.text=body.decode();self.status_code=status;self.url=url
    def raise_for_status(self):
        if self.status_code!=200:raise requests.HTTPError('HTTP '+str(self.status_code))

class Tests(unittest.TestCase):
    def test_preserves_value_and_original_month_start(self):
        value,day,pub,evidence=parse_services_pmi(fixture(),'2026-10',dt.date(2026,11,18))
        self.assertEqual((value,day,pub),(54.5,'2026-10-01','2026-11-04'))
        self.assertEqual(evidence['series_symbol'],'UNITEDSTANONMANPMI')
    def test_rejects_manufacturing_series(self):
        with self.assertRaisesRegex(ValueError,'SERIES_MISMATCH'):
            parse_services_pmi(fixture().replace(b'UNITEDSTANONMANPMI',b'NAPMPMI'),'2026-10',dt.date(2026,11,18))
    def test_rejects_wrong_current_target_month(self):
        with self.assertRaisesRegex(ValueError,'WRONG_TARGET_MONTH'):
            parse_services_pmi(fixture(),'2026-09',dt.date(2026,11,18))
    def test_rejects_future_release(self):
        with self.assertRaisesRegex(ValueError,'FUTURE_PUBLICATION'):
            parse_services_pmi(fixture(),'2026-10',dt.date(2026,11,3))
    def test_requires_release_bound_to_identical_headline(self):
        body=fixture().replace(b'<div class="comment more">The ISM Services PMI decreased to 54.5',b'<div class="comment more">The ISM Services PMI decreased to 53.8')
        with self.assertRaisesRegex(ValueError,'NOT_BOUND'):
            parse_services_pmi(body,'2026-10',dt.date(2026,11,18))
    def test_rejects_subindex_as_headline(self):
        body=fixture().replace(b'<h2 id="description">The ISM Services PMI',b'<h2 id="description">The ISM Services Business Activity')
        with self.assertRaisesRegex(ValueError,'HEADLINE_VALUE_OR_PERIOD'):
            parse_services_pmi(body,'2026-10',dt.date(2026,11,18))
    def test_rejects_missing_ism_origin(self):
        with self.assertRaisesRegex(ValueError,'ORIGIN_NOT_IDENTIFIED'):
            parse_services_pmi(fixture().replace(b'Institute for Supply Management',b'Other survey'),'2026-10',dt.date(2026,11,18))
    def fake(self,handler):
        calls=[]
        def get(url,**kwargs):calls.append(url);return handler(url)
        return SimpleNamespace(timeout=1,s=SimpleNamespace(get=get),job_series=set(),fredattempts=defaultdict(list)),calls
    def test_original_official_route_still_wins(self):
        body=('<html>October 2026 Services PMI at 54.5 percent '+('official report '*45)+'</html>').encode()
        f,calls=self.fake(lambda u:Response(body,url=u))
        with patch.object(macro.dt,'datetime',Clock):r=macro.ism_official(f,'m15')
        self.assertEqual(r['value'],54.5);self.assertEqual(len(calls),1)
        self.assertEqual(f.fredattempts['ISM_m15'][0]['provider'],'ISM_OFFICIAL')
    def test_failed_official_route_uses_backup_with_receipt(self):
        f,calls=self.fake(lambda u:Response(fixture()) if u==SERVICES_BACKUP_URL else Response(b'gone',404,u))
        with patch.object(macro.dt,'datetime',Clock):r=macro.ism_official(f,'m15')
        self.assertEqual((r['value'],r['observation_date'],r['publication_date']),(54.5,'2026-10-01','2026-11-04'))
        self.assertEqual(calls[-1],SERVICES_BACKUP_URL)
        self.assertEqual([x['result'] for x in f.fredattempts['ISM_m15']],['FAILED','OK'])
        self.assertEqual(len(r['source_evidence']['response_sha256']),64)
    def test_rejects_login_redirect(self):
        f,calls=self.fake(lambda u:Response(fixture(),url='https://tradingeconomics.com/login') if u==SERVICES_BACKUP_URL else Response(b'gone',404,u))
        with patch.object(macro.dt,'datetime',Clock),self.assertRaisesRegex(RuntimeError,'redirected away'):
            macro.ism_official(f,'m15')
    def test_both_sources_failed_remain_failed(self):
        f,calls=self.fake(lambda u:Response(b'unavailable',503,u))
        with patch.object(macro.dt,'datetime',Clock),self.assertRaisesRegex(RuntimeError,'official monthly headline source failed'):
            macro.ism_official(f,'m15')
        self.assertEqual([x['result'] for x in f.fredattempts['ISM_m15']],['FAILED','FAILED'])

if __name__=='__main__':unittest.main()
