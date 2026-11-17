"""m14 strict Wednesday/91-day alignment; actual FRED originals and marked mutations."""
import contextlib
import copy
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from test_macro18_source_response import macro, response

ROOT=Path(__file__).resolve().parents[1]


class NetLiquidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipts=json.loads((ROOT/'tests/fixtures/m14_fred_20261117.json').read_text())['sources']
        cls.raw={}
        for name,receipt in cls.receipts.items():
            archive=(ROOT/receipt['archive_path']).read_bytes()
            assert hashlib.sha256(archive).hexdigest()==receipt['archive_sha256']
            raw=gzip.decompress(archive)
            assert len(raw)==receipt['response_bytes'] and hashlib.sha256(raw).hexdigest()==receipt['response_sha256']
            cls.raw[name]=raw

    def real_series(self):
        def get(url,**kwargs):
            name=url.split('id=')[-1]
            return response(self.raw[name].decode())
        with patch.dict(macro.os.environ,{'FRED_API_KEY':''}),patch.object(macro.requests.Session,'get',side_effect=get),patch.object(macro.time,'sleep'):
            f=macro.Fetcher();row=macro.netliq(f)
        return f.fredcache,row

    def fake(self,series,fail=None):
        class F:
            def __init__(self):self.fredattempts={};self.job_series=set()
            def fred(self,name):
                self.job_series.add(name)
                stamp='2026-11-16T04:00:00Z'  # marked test clock, never live evidence
                if name==fail:
                    self.fredattempts[name]=[{'provider':'TEST_ONLY','result':'FAILED','error':'synthetic timeout','attempted_at':stamp}]
                    raise RuntimeError('synthetic timeout '+name)
                self.fredattempts[name]=[{'provider':'FROZEN_TEST_REPLAY','result':'OK','verified_at':stamp,
                                          'observation_date':str(series[name].index[-1].date())}]
                return series[name]
        return F()

    def small(self):
        index=pd.to_datetime(['2026-07-15','2026-10-14','2026-10-21'])
        return {'WALCL':pd.Series([10000,12000,15000],index=index),
                'WDTGAL':pd.Series([1000,1500,2000],index=index),
                'RRPONTSYD':pd.Series([1,1.25,3],index=index)}

    def run_producer(self,series,today,fail=None,cache=False):
        f=self.fake(series,fail);now=dt.datetime.combine(today,dt.time(4),tzinfo=dt.timezone.utc)
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return now.astimezone(tz) if tz else now.replace(tzinfo=None)
        clock=SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')});clock.datetime=Fixed
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(macro,'dt',clock));stack.enter_context(patch.object(macro,'Fetcher',return_value=f))
            for name in ('latest','breakeven_5y','month_delta','ism_official','sahm_from_published','nfp',
                         'core_cpi','yahoo_price','cnn','lei_verified_history'):
                stack.enter_context(patch.object(macro,name,side_effect=RuntimeError('other indicator outside m14 test')))
            prior=None;cache_path=None
            if cache:
                prior=macro.row('m14',-5.92,'2026-11-04','https://fred.stlouisfed.org/series/WALCL','test prior')
                prior.update(last_verified_at='2026-11-16T03:00:00Z',source_evidence={'fixture':'original source fingerprint'})
                cache_path=Path(folder)/'prior.json';cache_path.write_text(json.dumps({'items':{'m14':prior}}))
            result=macro.run(Path(folder)/'out',cache_path=cache_path)
            from scripts.validate_macro18_outputs import validate_outputs
            self.assertEqual(validate_outputs(Path(folder)/'out'),19)
            return result['items']['m14'],prior

    def test_actual_originals_identify_missing_RRP_and_preserve_value(self):
        series,row=self.real_series()
        self.assertNotIn(pd.Timestamp('2026-11-11'),series['RRPONTSYD'].index)
        self.assertRegex(self.raw['RRPONTSYD'].decode(),r'2026-11-11,(?:\.|\s*)(?:\r?\n)')
        self.assertEqual((row['value'],row['observation_date']),(-5.92,'2026-11-04'))
        d=row['alignment_diagnostics']
        self.assertEqual(d['latest_weekly_wednesday'],'2026-11-11')
        self.assertEqual(d['missing_at_latest_weekly'],['RRPONTSYD'])
        self.assertEqual(d['selected_begin'],'2026-08-05')
        self.assertEqual(d['values_at_required_dates']['2026-11-11'],
                         {'WALCL':6758867.0,'WDTGAL':912134.0,'RRPONTSYD':None})
        self.assertEqual(d['values_at_required_dates']['2026-08-12']['RRPONTSYD'],0.725)

    def test_complete_same_wednesday_and_units_remain_unchanged(self):
        series=self.small();series={k:s.iloc[:2] for k,s in series.items()}
        before=copy.deepcopy(series);row=macro.netliq(self.fake(series))
        self.assertEqual((row['value'],row['observation_date'],row['unit']),(1.25,'2026-10-14','USD bn'))
        self.assertEqual(row['alignment_diagnostics']['missing_at_latest_weekly'],[])
        for name in series:pd.testing.assert_series_equal(series[name],before[name])

    def test_missing_single_source_never_fills_or_relabels_older_value(self):
        for missing in ('WALCL','WDTGAL','RRPONTSYD'):
            with self.subTest(missing=missing):
                series=self.small();series[missing]=series[missing].iloc[:2]
                row=macro.netliq(self.fake(series))
                self.assertEqual((row['value'],row['observation_date']),(1.25,'2026-10-14'))
                self.assertEqual(row['alignment_diagnostics']['missing_at_latest_weekly'],[missing])
                self.assertIsNone(row['alignment_diagnostics']['values_at_required_dates']['2026-10-21'][missing])

    def test_explicit_nan_is_missing_and_not_zero(self):
        series=self.small();series['RRPONTSYD'].iloc[-1]=float('nan')
        row=macro.netliq(self.fake(series))
        self.assertEqual(row['observation_date'],'2026-10-14')
        self.assertIsNone(row['alignment_diagnostics']['values_at_required_dates']['2026-10-21']['RRPONTSYD'])
        json.dumps(row,allow_nan=False)

    def test_absent_exact_91_day_base_does_not_use_nearby_day(self):
        series=self.small();f=self.fake(series)
        with self.assertRaisesRegex(ValueError,'13 週前同日值: 2026-07-22'):macro.netliq(f)
        self.assertEqual(f.netliq_diagnostics['status'],'MISSING_EXACT_91_DAY_BASE')
        self.assertIsNone(f.netliq_diagnostics['values_at_required_dates']['2026-07-22']['WALCL'])

    def test_non_wednesday_values_are_ignored(self):
        series={k:s.iloc[:2] for k,s in self.small().items()}
        for s in series.values():s.loc[pd.Timestamp('2026-10-15')]=999999
        row=macro.netliq(self.fake(series))
        self.assertEqual((row['value'],row['observation_date']),(1.25,'2026-10-14'))

    def test_actual_zero_RRP_is_a_valid_observation(self):
        series={k:s.iloc[:2] for k,s in self.small().items()}
        series['RRPONTSYD'].iloc[-1]=0
        row=macro.netliq(self.fake(series))
        self.assertEqual(row['value'],2.5)
        self.assertEqual(row['alignment_diagnostics']['values_at_required_dates']['2026-10-14']['RRPONTSYD'],0)

    def test_repeated_replay_is_identical(self):
        series,_=self.real_series()
        self.assertEqual(macro.netliq(self.fake(series)),macro.netliq(self.fake(series)))

    def test_producer_keeps_exact_12_day_expiry_and_three_output_contracts(self):
        series,_=self.real_series()
        for day,expected in ((dt.date(2026,11,16),'OK'),(dt.date(2026,11,17),'STALE')):
            row,_=self.run_producer(series,day)
            self.assertEqual(row['status'],expected)
            self.assertEqual((row['value'],row['observation_date']),(-5.92,'2026-11-04'))
            self.assertEqual(row['alignment_diagnostics']['missing_at_latest_weekly'],['RRPONTSYD'])
        self.assertEqual(macro.load_source_config()['indicators']['m14']['max_age_days'],12)

    def test_failed_source_retains_full_prior_evidence_and_failure_diagnostics(self):
        series,_=self.real_series();row,prior=self.run_producer(series,dt.date(2026,11,17),'WDTGAL',cache=True)
        for field in ('value','observation_date','unit','last_verified_at','source_evidence'):
            self.assertEqual(row[field],prior[field])
        self.assertTrue(row['cache_used']);self.assertEqual(row['status'],'STALE')
        self.assertIn('synthetic timeout WDTGAL',row['retrieval_error'])
        self.assertEqual(row['alignment_diagnostics']['status'],'FETCH_INCOMPLETE')
        self.assertEqual(set(row['alignment_diagnostics']['source_latest_dates']),{'WALCL'})


if __name__=='__main__':unittest.main()
