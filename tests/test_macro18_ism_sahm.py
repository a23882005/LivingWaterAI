"""Regression tests for direct official ISM and Sahm sources."""
import datetime as dt
import importlib.util
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
            with self.assertRaisesRegex(RuntimeError,'month/year/type heading mismatch'):
                macro.ism_official(fake,'m04')
        self.assertEqual(fake.fredattempts['ISM_m04'][0]['result'],'FAILED')

    def test_sahm_published_series_preferred(self):
        fake=SimpleNamespace(fred=lambda name:pd.Series([0.21],index=pd.to_datetime(['2026-09-01'])),
                             fredsources={})
        with patch.object(macro,'sahm_from_unrate',side_effect=AssertionError('should not use U3')):
            r=macro.sahm_from_published(fake)
        self.assertEqual(r['value'],0.21)
        self.assertEqual(r['observation_date'],'2026-09-01')

if __name__=='__main__':unittest.main()
