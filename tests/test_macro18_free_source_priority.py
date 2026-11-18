"""Verify original entrypoint routing, failure fallback and unchanged calculations."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'系統工程/總經V70/總經爬蟲18項.py'
spec=importlib.util.spec_from_file_location('macro18_free_priority',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Response:
    def __init__(self,text,status=200):self.text=text;self.content=text.encode();self.status_code=status;self.headers={}
    def json(self):return json.loads(self.text)
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError('fixture HTTP '+str(self.status_code))

class Session:
    def __init__(self,handler):self.headers={};self.calls=[];self.handler=handler
    def mount(self,*args,**kwargs):pass
    def get(self,url,**kwargs):self.calls.append(url);return self.handler(url)
    def post(self,*args,**kwargs):raise AssertionError('Unexpected POST before verified free primary')

class FreePriority(TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'FRED_API_KEY':'test-unused-key'});self.env.start()
        self.sleep=patch.object(m.time,'sleep',return_value=None);self.sleep.start()
        self.vix=patch.object(m,'last_completed_vix_session',return_value=dt.date(2026,11,17));self.vix.start()
    def tearDown(self):self.env.stop();self.sleep.stop();self.vix.stop()
    def fetcher(self,handler):
        s=Session(handler)
        with patch.object(m.requests,'Session',return_value=s):f=m.Fetcher()
        return f,s
    def test_five_tested_series_prefer_csv_even_with_api_key(self):
        for series in ['VIXCLS','T10Y2Y','BAMLH0A0HYM2','T5YIE','SAHMREALTIME']:
            with self.subTest(series=series):
                f,s=self.fetcher(lambda u:Response('observation_date,'+series+'\n2026-11-17,1.5\n'))
                self.assertEqual(float(f.fred(series).iloc[-1]),1.5)
                self.assertEqual(len(s.calls),1);self.assertIn('fredgraph.csv?id='+series,s.calls[0])
    def test_lagged_csv_still_falls_back_to_original_cboe(self):
        def respond(u):
            if 'fredgraph.csv' in u:return Response('observation_date,VIXCLS\n2026-11-16,22.91\n')
            if 'cboe.com' in u:return Response('DATE,OPEN,HIGH,LOW,CLOSE\n11/17/2026,20,21,19,20.5\n')
            raise AssertionError('Unexpected source')
        f,s=self.fetcher(respond);self.assertEqual(float(f.fred('VIXCLS').iloc[-1]),20.5)
        self.assertIn('fredgraph.csv',s.calls[0]);self.assertIn('cboe.com',s.calls[1]);self.assertIn('VIX_LAGGED_SESSION',f.fredattempts['VIXCLS'][0]['error'])
    def test_http_failure_continues_to_original_cboe(self):
        f,s=self.fetcher(lambda u:Response('',403) if 'fredgraph.csv' in u else Response('DATE,CLOSE\n11/17/2026,20.5\n'))
        self.assertEqual(float(f.fred('VIXCLS').iloc[-1]),20.5);self.assertEqual(len(s.calls),2)
    def test_unrate_uses_exact_bls_total_sa_table_first(self):
        cols=pd.MultiIndex.from_tuples([('Label','Label'),('Seasonally adjusted','Oct 2026'),('Not seasonally adjusted','Oct 2026')])
        frame=pd.DataFrame([['Unemployment rate',4.1,9.9],['Unemployment rate women',3.9,8.8]],columns=cols)
        f,s=self.fetcher(lambda u:Response('<table>fixture</table>'))
        with patch.object(m.pd,'read_html',return_value=[frame]):value=f.fred('UNRATE')
        self.assertEqual(float(value.iloc[-1]),4.1);self.assertIn('empsit.t01.htm',s.calls[0]);self.assertEqual(len(s.calls),1)
    def test_sahm_bypasses_short_current_u3_cache_for_original_history(self):
        months=pd.date_range('2025-08-01',periods=15,freq='MS')
        body=json.dumps({'observations':[{'date':str(day.date()),'value':str(4+i*.01)} for i,day in enumerate(months)]})
        f,s=self.fetcher(lambda u:Response(body))
        f.fredcache['UNRATE']=pd.Series([4.14],index=pd.to_datetime(['2026-10-01']))
        f.fredsources['UNRATE']=('BLS_EMPLOYMENT_TABLE','https://www.bls.gov/news.release/empsit.t01.htm')
        result=m.sahm_from_unrate(f)
        self.assertAlmostEqual(result['value'],.12)
        self.assertEqual(result['observation_date'],'2026-10-01')
        self.assertIn('api.stlouisfed.org',s.calls[0])
        self.assertTrue(all('empsit.t01.htm' not in u for u in s.calls))
        self.assertEqual(len(f.fredcache['UNRATE']),15)
    def test_unrate_history_without_key_keeps_original_bls_first(self):
        f,s=self.fetcher(lambda u:Response(''))
        months=pd.date_range('2025-08-01',periods=15,freq='MS')
        body={'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':'LNS14000000','data':[{'year':str(d.year),'period':'M'+str(d.month).zfill(2),'value':'4.1'} for d in months]}]}}
        with patch.dict(os.environ,{'FRED_API_KEY':''}),patch.object(s,'post',return_value=Response(json.dumps(body))) as history:
            result=f.fred('UNRATE',require_history=True)
        self.assertEqual(len(result),15);self.assertEqual(s.calls,[])
        self.assertIn('/v2/timeseries/data/',history.call_args.args[0])
    def test_breakeven_prefers_treasury_and_does_not_read_fred(self):
        with patch.object(m,'treasury_breakeven',return_value={'value':2.26}) as primary,patch.object(m,'latest') as backup:
            self.assertEqual(m.breakeven_5y(object())['value'],2.26);primary.assert_called_once();backup.assert_not_called()
    def test_breakeven_treasury_failure_keeps_original_fred(self):
        with patch.object(m,'treasury_breakeven',side_effect=ValueError('offline')),patch.object(m,'latest',return_value={'value':2.2}) as backup:
            self.assertEqual(m.breakeven_5y(object())['value'],2.2);backup.assert_called_once()
    def test_month_delta_preserves_calendar_month_fred_backup(self):
        class F:
            def fred(self,s):return pd.Series([2.37,2.26],index=pd.to_datetime(['2026-10-16','2026-11-17']))
        with patch.object(m,'treasury_breakeven',side_effect=ValueError('offline')):
            r=m.month_delta(F());self.assertAlmostEqual(r['value'],-.11)
    def test_month_delta_rejects_old_baseline_in_both_sources(self):
        class F:
            def fred(self,s):return pd.Series([2.37,2.26],index=pd.to_datetime(['2026-09-01','2026-11-17']))
        with patch.object(m,'treasury_breakeven',side_effect=ValueError('offline')),self.assertRaises(RuntimeError):
            m.month_delta(F())
    def test_config_keeps_18_original_scope(self):
        c=m.load_source_config();self.assertEqual(len(c['indicators']),18)
        self.assertEqual(c['indicators']['m04']['primary_source'],'ISM_OFFICIAL_PDF')
        self.assertIn('ISM_OFFICIAL',c['indicators']['m04']['backup_sources'])
        self.assertEqual(c['indicators']['m19']['primary_source'],'BLS_EMPLOYMENT_TABLE')
    def test_ism_preferred_official_pdf_reuses_existing_parser(self):
        real_datetime=dt.datetime
        class Clock(real_datetime):
            @classmethod
            def now(cls,tz=None):return real_datetime(2026,11,18,12,tzinfo=dt.timezone.utc).astimezone(tz)
        f,s=self.fetcher(lambda u:Response('%PDF-fixture'));f.job_series=set()
        with patch.object(m.dt,'datetime',Clock),patch('scripts.refresh_v703_predeploy.manufacturing_headline_from_official_pdf',return_value=55.5) as parser:
            r=m.ism_official(f,'m04');self.assertEqual(r['value'],55.5);self.assertEqual(r['observation_date'],'2026-10-01');self.assertTrue(s.calls[0].endswith('.pdf'));parser.assert_called_once()
    def test_ism_pdf_failure_uses_original_official_html(self):
        real_datetime=dt.datetime
        class Clock(real_datetime):
            @classmethod
            def now(cls,tz=None):return real_datetime(2026,11,18,12,tzinfo=dt.timezone.utc).astimezone(tz)
        body='<html>October 2026 Manufacturing PMI at 55.5 percent '+('official report '*40)+'</html>'
        f,s=self.fetcher(lambda u:Response('',403) if u.endswith('.pdf') else Response(body));f.job_series=set()
        with patch.object(m.dt,'datetime',Clock):
            r=m.ism_official(f,'m04');self.assertEqual(r['value'],55.5);self.assertTrue(s.calls[0].endswith('.pdf'));self.assertIn('/ism-pmi-reports/pmi/october/',s.calls[1])

if __name__=='__main__':main()
