"""Regression tests for direct official ISM and Sahm sources."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from collections import defaultdict
import requests
import pandas as pd

spec=importlib.util.spec_from_file_location('macro18_sources',Path(__file__).resolve().parents[1]/'系統工程/總經V70/總經爬蟲18項.py')
macro=importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)

MONTHLY_CALENDAR_FIXTURE = Path(__file__).parent / 'fixtures/monthly_official_release_calendar_20261106.json'

class FakeResponse:
    def __init__(self,text): self.text=text
    def raise_for_status(self): pass

RealDatetime=dt.datetime
class FixedDatetime(RealDatetime):
    @classmethod
    def now(cls,tz=None): return RealDatetime(2026,10,24,tzinfo=tz)

class SourceTests(unittest.TestCase):
    def test_ism_both_sectors_official_headlines(self):
        for key,sector,value in [('m04','Manufacturing',54.5),('m15','Services',54.9)]:
            fake=SimpleNamespace(timeout=10,s=SimpleNamespace(get=lambda *a,**k:FakeResponse(
                '<html><h1>September 2026 ISM® '+sector+' PMI® Report</h1>'
                '<h2>'+sector+' PMI® at '+str(value)+'%</h2><p>'+'A'*500+'</p></html>')),
                job_series=set(),fredattempts=defaultdict(list))
            with patch.object(macro.dt,'datetime',FixedDatetime):
                r=macro.ism_official(fake,key)
            self.assertEqual(float(r['value']),value)
            self.assertEqual(r['observation_date'],'2026-09-01')
            self.assertEqual(fake.fredattempts['ISM_'+key][-1]['result'],'OK')

    def test_ism_rejects_wrong_month_after_release(self):
        fake=SimpleNamespace(timeout=10,s=SimpleNamespace(get=lambda *a,**k:FakeResponse(
            '<html><h1>August 2026 ISM® Manufacturing PMI® Report</h1>'
            '<h2>Manufacturing PMI® at 54.6%</h2><p>'+'A'*500+'</p></html>')),
            job_series=set(),fredattempts=defaultdict(list))
        with patch.object(macro.dt,'datetime',FixedDatetime):
            with self.assertRaisesRegex(RuntimeError,'date or sector headline mismatch'):
                macro.ism_official(fake,'m04')
        self.assertEqual(fake.fredattempts['ISM_m04'][0]['result'],'FAILED')

    def test_october_manufacturing_uses_same_month_official_roundup(self):
        class NovemberDatetime(RealDatetime):
            @classmethod
            def now(cls,tz=None):
                return RealDatetime(2026,11,6,4,0,tzinfo=tz)

        calls=[]
        def get(url,**kwargs):
            calls.append(url)
            if '/pmi/october/' in url:
                return FakeResponse('<html>The content you are looking for is no longer available.'+'A'*500+'</html>')
            if 'roundup-october-2026-manufacturing/' in url:
                return FakeResponse(
                    '<html><h1>ISM PMI Reports Roundup: October Manufacturing</h1>'
                    '<time>November 02, 2026</time><p>The Manufacturing PMI® '
                    'reflected U.S. factory activity remaining steady; it even '
                    'increased 1 percentage point to at 55.5 percent.</p>'
                    + 'A'*600+'</html>')
            raise AssertionError('Previous month must not be fetched as October: '+url)
        fake=SimpleNamespace(timeout=10,s=SimpleNamespace(get=get),
                             job_series=set(),fredattempts=defaultdict(list))
        with patch.object(macro.dt,'datetime',NovemberDatetime):
            r=macro.ism_official(fake,'m04')
        self.assertEqual((r['observation_date'],r['value']),('2026-10-01',55.5))
        self.assertIn('roundup-october-2026-manufacturing',r['source_url'])
        self.assertEqual([x['result'] for x in fake.fredattempts['ISM_m04']],['FAILED','FAILED','OK'])
        self.assertEqual(len(calls),3)
        self.assertTrue(calls[0].endswith('r4in202610pmi.pdf'))

    def test_unavailable_current_report_cannot_promote_previous_month(self):
        class NovemberDatetime(RealDatetime):
            @classmethod
            def now(cls,tz=None):
                return RealDatetime(2026,11,6,4,0,tzinfo=tz)
        calls=[]
        def get(url,**kwargs):
            calls.append(url)
            return FakeResponse('<html>The content you are looking for is no longer available.'+'A'*500+'</html>')
        fake=SimpleNamespace(timeout=10,s=SimpleNamespace(get=get),
                             job_series=set(),fredattempts=defaultdict(list))
        with patch.object(macro.dt,'datetime',NovemberDatetime):
            with self.assertRaisesRegex(RuntimeError,'ISM official monthly headline source failed'):
                macro.ism_official(fake,'m04')
        self.assertEqual(len(calls),3)
        self.assertTrue(calls[0].endswith('r4in202610pmi.pdf'))
        self.assertTrue(all('/september/' not in url for url in calls))

    def test_live_month_release_gate_and_cached_source_fail_closed(self):
        now=RealDatetime(2026,11,6,4,0,tzinfo=dt.timezone.utc)
        today=now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        # Keep this frozen pre-release case independent of daily production refreshes.
        fixture=MONTHLY_CALENDAR_FIXTURE.read_text(encoding='utf-8')
        with patch.object(macro.Path,'read_text',return_value=fixture):
            calendar=macro.verified_monthly_calendar(today,now)
        self.assertEqual(set(calendar),{'m04','m05','m15','m18','m19','m20'})
        row=macro.row('m19',4.2,'2026-09-01',
                      'https://fred.stlouisfed.org/series/UNRATE','live official')
        row.update(attempt_result='SUCCESS',cache_used=False,
                   last_verified_at='2026-11-06T03:50:00Z')
        self.assertTrue(macro.release_certified_live_month(row,calendar,now))
        self.assertEqual(macro.freshen(dict(row),today,calendar,now)['status'],'OK')
        released=RealDatetime(2026,11,6,13,30,tzinfo=dt.timezone.utc)
        self.assertFalse(macro.release_certified_live_month(row,calendar,released))
        self.assertEqual(macro.freshen(dict(row),released.date(),calendar,released)['status'],'STALE')
        for changed in (
            dict(row,cache_used=True),
            dict(row,attempt_result='FAILED'),
            dict(row,last_verified_at=None),
            dict(row,observation_date='2026-08-01'),
        ):
            self.assertFalse(macro.release_certified_live_month(changed,calendar,now))
        self.assertFalse(macro.release_certified_live_month(row,{},now))

    def test_monthly_calendar_rejects_future_verification(self):
        now=RealDatetime(2026,11,6,4,0,tzinfo=dt.timezone.utc)
        today=now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        fixture=json.loads(MONTHLY_CALENDAR_FIXTURE.read_text(encoding='utf-8'))
        fixture['checked_at_utc']='2026-11-06T04:00:01Z'
        with patch.object(macro.Path,'read_text',return_value=json.dumps(fixture)):
            self.assertEqual(macro.verified_monthly_calendar(today,now),{})

    def test_sahm_published_series_preferred(self):
        fake=SimpleNamespace(fred=lambda name:pd.Series([0.21],index=pd.to_datetime(['2026-09-01'])),
                             fredsources={})
        gap={'status':'MISSING_MONTHS','missing_months':['2025-10']}
        with (patch.object(macro,'sahm_from_unrate',side_effect=AssertionError('must retain published value')),
              patch.object(macro,'sahm_bls_crosscheck',return_value=gap)):
            r=macro.sahm_from_published(fake)
        self.assertEqual(r['value'],0.21)
        self.assertEqual(r['observation_date'],'2026-09-01')
        self.assertEqual(r['sahm_bls_check'],gap)

    def sahm_bls_fixture(self, months, values, series_id='LNS14000000'):
        points=[{'year':str(month.year),'period':f'M{month.month:02d}','value':str(value)}
                for month,value in zip(months,values)]
        body={'status':'REQUEST_SUCCEEDED',
              'Results':{'series':[{'seriesID':series_id,'data':points[::-1]}]}}
        reply=FakeResponse(json.dumps(body))
        reply.content=reply.text.encode()
        reply.json=lambda:body
        return SimpleNamespace(timeout=40,s=SimpleNamespace(get=lambda *args,**kwargs:reply))

    def test_sahm_bls_complete_window_matches_negative_reading(self):
        months=pd.period_range('2024-07','2025-09',freq='M')
        fake=self.sahm_bls_fixture(months,[4.2]*14+[4.0])
        check=macro.sahm_bls_crosscheck(fake,{'observation_date':'2025-09-01','value':-0.07})
        self.assertEqual(check['status'],'MATCH')
        self.assertEqual(check['calculated_value_pp'],-0.07)
        self.assertEqual(len(check['response_sha256']),64)
        check=macro.sahm_bls_crosscheck(fake,{'observation_date':'2025-09-01','value':0.0})
        self.assertEqual(check['status'],'VALUE_MISMATCH')

    def test_sahm_bls_gap_and_month_mismatch_have_no_candidate_value(self):
        months=pd.period_range('2025-07','2026-09',freq='M')
        fake=self.sahm_bls_fixture(months,[4.2]*3+['-']+[4.2]*11)
        published={'observation_date':'2026-09-01','value':0.0}
        check=macro.sahm_bls_crosscheck(fake,published)
        self.assertEqual(check['missing_months'],['2025-10'])
        self.assertNotIn('calculated_value_pp',check)
        check=macro.sahm_bls_crosscheck(fake,dict(published,observation_date='2026-08-01'))
        self.assertEqual(check['status'],'MONTH_MISMATCH')
        self.assertNotIn('calculated_value_pp',check)

    def test_sahm_bls_january_window_no_longer_includes_october_gap(self):
        months=pd.period_range('2025-10','2027-01',freq='M')
        fake=self.sahm_bls_fixture(months,['-']+[4.2]*12+[4.5]*3)
        with patch.object(macro.dt,'datetime',wraps=RealDatetime) as clock:
            clock.now.side_effect=lambda tz:RealDatetime(2027,2,6,tzinfo=tz)
            check=macro.sahm_bls_crosscheck(fake,{'observation_date':'2027-01-01','value':0.3})
        self.assertEqual(check['status'],'MATCH')

    def test_sahm_bls_rejects_wrong_series(self):
        fake=self.sahm_bls_fixture([],[],'NOT_U3')
        check=macro.sahm_bls_crosscheck(fake,{'observation_date':'2025-09-01','value':0.0})
        self.assertEqual(check['status'],'SOURCE_ERROR')

if __name__=='__main__':unittest.main()

