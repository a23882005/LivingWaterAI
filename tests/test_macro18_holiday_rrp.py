"""Hash-bound live originals replay plus explicitly synthetic negative mutations."""
import copy
import datetime as dt
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import pandas as pd
import test_macro18_netliq as legacy
from test_macro18_source_response import macro
from scripts import m14_holiday_rrp as h
from scripts.build_daily_v703_site import _validate, _normalize

FIXTURE=Path(__file__).parent/'fixtures/m14_holiday_20261117.json.gz'
NOW=dt.datetime(2026,11,17,12,tzinfo=dt.timezone.utc) # REPLAY ONLY

class HolidayTests(unittest.TestCase):
    def setUp(self):
        self.row=json.loads(gzip.decompress(FIXTURE.read_bytes()))
        self.ev=self.row['source_evidence']['holiday_outstanding']['endpoints']['2026-11-11']['evidence']
        self.day=dt.date(2026,11,11)

    def rewrite(self,edit):
        # Mutate both range and matching daily response, recomputing their hashes.
        for r in [self.ev['range'],*self.ev['daily'].values()]:
            data=json.loads(h.unpack(r));edit(data['repo']['operations'])
            r.update(h.receipt(json.dumps(data).encode(),r['url'],r['retrieved_at']))

    def outstanding(self):return h.derive(self.day,self.ev,NOW)

    def test_actual_official_originals_recompute_46_756(self):
        self.assertEqual(self.outstanding()['value_usd_bn'],.152)
        self.assertEqual(self.row['value'],46.756);h.validate_item(self.row,NOW)
        self.assertEqual(self.row['alignment_diagnostics']['values_at_required_dates']['2026-11-11']['RRPONTSYD'],None)

    def test_actual_calendar_and_holiday_year_required(self):
        raw=h.unpack(self.ev['holiday_calendar'])
        self.assertIn(self.day,h.holiday_dates(raw,2026))
        with self.assertRaises(ValueError):h.holiday_dates(raw,2025)

    def test_normal_business_day_missing_is_not_filled(self):
        with self.assertRaisesRegex(ValueError,'holiday not confirmed'):h.derive(dt.date(2026,11,10),self.ev,NOW)

    def test_duplicate_identical_operations_count_once(self):
        self.rewrite(lambda ops:ops.extend(copy.deepcopy(ops)))
        self.assertEqual(self.outstanding()['value_usd_bn'],.152)

    def test_contradictory_duplicate_rejected(self):
        def edit(ops):
            if ops:
                op=copy.deepcopy(ops[0]);op['totalAmtAccepted']=999;ops.append(op)
        self.rewrite(edit)
        with self.assertRaisesRegex(ValueError,'contradictory'):self.outstanding()

    def test_treasury_total_disagreement_rejected(self):
        def edit(ops):
            for op in ops:
                if op['operationId']=='RP 111026 26':op['totalAmtAccepted']+=1
        self.rewrite(edit)
        with self.assertRaisesRegex(ValueError,'amount mismatch'):self.outstanding()

    def test_empty_queries_are_not_zero(self):
        self.rewrite(lambda ops:ops.clear())
        with self.assertRaisesRegex(ValueError,'missing business-day'):self.outstanding()

    def test_daily_page_missing_rejected(self):
        self.ev['daily'].pop('2026-11-10')
        with self.assertRaisesRegex(ValueError,'incomplete daily'):self.outstanding()

    def test_range_truncation_detected_by_daily_queries(self):
        r=self.ev['range'];obj=json.loads(h.unpack(r));obj['repo']['operations'].pop()
        r.update(h.receipt(json.dumps(obj).encode(),r['url'],r['retrieved_at']))
        with self.assertRaisesRegex(ValueError,'completeness mismatch'):self.outstanding()

    def test_pagination_metadata_is_fail_closed(self):
        r=self.ev['range'];obj=json.loads(h.unpack(r));obj['repo']['nextPage']='2'
        r.update(h.receipt(json.dumps(obj).encode(),r['url'],r['retrieved_at']))
        with self.assertRaisesRegex(ValueError,'paginated'):self.outstanding()

    def test_wrong_security_identity_rejected(self):
        def edit(ops):
            for op in ops:
                if op['operationId']=='RP 111026 26':op['details'][0]['securityType']='Agency'
        self.rewrite(edit)
        with self.assertRaisesRegex(ValueError,'Treasury-only'):self.outstanding()

    def test_repo_term_and_non_results_not_counted(self):
        for field,value in [('operationType','Repo'),('term','Term'),('auctionStatus','Announcement')]:
            with self.subTest(field=field):
                self.setUp()
                def edit(ops):
                    for op in ops:
                        if op['operationId']=='RP 111026 26':op[field]=value
                self.rewrite(edit)
                with self.assertRaises(ValueError):self.outstanding()

    def test_maturity_date_is_excluded(self):
        # A hypothetical NYFed holiday on the contract's maturity date must not
        # count a matured principal. Real Nov 11 contract crosses two calendar days.
        self.rewrite(lambda ops:None)
        contract=self.outstanding()['contracts'][0]
        self.assertEqual(contract['maturityDate'],'2026-11-12')
        self.assertFalse(dt.date.fromisoformat(contract['settlementDate'])<=dt.date(2026,11,12)<dt.date.fromisoformat(contract['maturityDate']))
        def edit(ops):
            for op in ops:
                if op['operationId']=='RP 111026 26':
                    op.update(operationDate='2026-11-09',settlementDate='2026-11-09',maturityDate='2026-11-10')
        # Direct unique parser inspection plus a range mutation is rejected by date binding.
        self.rewrite(edit)
        with self.assertRaises(ValueError):self.outstanding()

    def test_future_or_unsettled_contract_rejected(self):
        for field in ('settlementDate','operationDate'):
            with self.subTest(field=field):
                self.setUp()
                def edit(ops):
                    for op in ops:
                        if op['operationId']=='RP 111026 26':op[field]='2026-11-12'
                self.rewrite(edit)
                with self.assertRaises(ValueError):self.outstanding()

    def test_future_receipt_clock_rejected(self):
        self.ev['holiday_calendar']['retrieved_at']='2026-11-18T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'clock invalid'):self.outstanding()

    def test_hash_corruption_rejected(self):
        self.ev['range']['response_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.outstanding()

    def test_publication_recomputes_value_and_evidence(self):
        self.row['status']='OK'
        self.assertEqual(_validate('m14',self.row,NOW.date(),now_utc=NOW),[])
        for field,value in [('value',47),('unit','USD million'),('observation_date','2026-11-12')]:
            r=copy.deepcopy(self.row);r[field]=value
            self.assertTrue(_validate('m14',r,NOW.date(),now_utc=NOW))
        r=copy.deepcopy(self.row);r.pop('source_evidence')
        self.assertTrue(_validate('m14',r,NOW.date(),now_utc=NOW))
        normalized=_normalize(self.row,'m14')
        self.assertEqual(normalized['sourceEvidence'],self.row['source_evidence'])

    def test_exact_12_day_limit_applies_in_builder(self):
        self.row['status']='OK'
        self.assertEqual(_validate('m14',self.row,dt.date(2026,11,23),now_utc=NOW),[])
        self.assertTrue(_validate('m14',self.row,dt.date(2026,11,24),now_utc=NOW))

    def test_fred_priority_including_real_zero(self):
        for value in (0,.35):
            series={n:pd.Series(v) for n,v in self.original_series().items()}
            series['RRPONTSYD'].loc[pd.Timestamp('2026-11-11')]=value
            f=legacy.NetLiquidityTests().fake(series)
            with patch.object(h,'fetch_holiday',side_effect=AssertionError('must not derive')):
                r=macro.netliq(f)
            self.assertNotIn('source_evidence',r)
            self.assertAlmostEqual(r['value'],46.908-value)

    def original_series(self):
        return {name:{pd.Timestamp(k):v for k,v in h.fred_values(r,name).items() if v is not None}
                for name,r in self.row['source_evidence']['holiday_outstanding']['fred_originals'].items()}

    def test_producer_wiring_and_repeat_preserves_derived_receipts(self):
        series={n:pd.Series(v) for n,v in self.original_series().items()}
        f=legacy.NetLiquidityTests().fake(series)
        f.m14_originals=self.row['source_evidence']['holiday_outstanding']['fred_originals']
        with patch.object(h,'fetch_holiday',return_value=self.outstanding()):
            first=macro.netliq(f);second=macro.netliq(f)
        self.assertEqual(first,second);self.assertEqual(first['value'],46.756)
        h.validate_item(first,NOW)

    def test_base_holiday_uses_same_rule_and_exact_91_days(self):
        # Explicit synthetic future replay: base is the actual Nov 11 holiday.
        end=dt.date(2027,2,10);begin=self.day
        series={
            'WALCL':pd.Series([10000.,12000.],index=pd.to_datetime([begin,end])),
            'WDTGAL':pd.Series([1000.,1500.],index=pd.to_datetime([begin,end])),
            'RRPONTSYD':pd.Series([.3],index=pd.to_datetime([end]))}
        f=legacy.NetLiquidityTests().fake(series);f.m14_originals={}
        for name,ser in series.items():
            rows=['observation_date,'+name]
            for day in (begin,end):
                value=ser.get(pd.Timestamp(day),'.')
                rows.append(day.isoformat()+','+str(value))
            f.m14_originals[name]=h.receipt(('\n'.join(rows)+'\n').encode(),macro.FRED+name,'2027-02-11T00:00:00Z')
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return dt.datetime(2027,2,11,tzinfo=dt.timezone.utc)
        with patch.object(macro.dt,'datetime',Fixed),patch.object(h,'fetch_holiday',return_value=self.outstanding()):
            result=macro.netliq(f)
        self.assertEqual(result['value'],1.352)
        self.assertEqual(result['source_evidence']['holiday_outstanding']['begin'],'2026-11-11')
        self.assertEqual(set(result['source_evidence']['holiday_outstanding']['endpoints']),{'2026-11-11'})

    def test_expired_contracts_do_not_contribute(self):
        def edit(ops):
            for op in ops:
                if op['operationId']=='RP 110926 26':
                    op['details'][0]['amtAccepted']=900000000000
                    op['totalAmtAccepted']=900000000000
        self.rewrite(edit)
        self.assertEqual(self.outstanding()['value_usd_bn'],.152)

    def test_failures_preserve_prior_derived_evidence_and_clock(self):
        import contextlib,tempfile
        from types import SimpleNamespace
        series={n:pd.Series(v) for n,v in self.original_series().items()}
        f=legacy.NetLiquidityTests().fake(series,fail='WDTGAL')
        prior=copy.deepcopy(self.row)
        prior.update(status='OK',last_verified_at='2026-11-17T05:50:00Z')
        fixed_now=dt.datetime(2026,11,18,4,tzinfo=dt.timezone.utc)
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)
        clock=SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')});clock.datetime=Fixed
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(macro,'dt',clock));stack.enter_context(patch.object(macro,'Fetcher',return_value=f))
            for name in ('latest','breakeven_5y','month_delta','ism_official','sahm_from_published','nfp','core_cpi','yahoo_price','cnn','lei_verified_history'):
                stack.enter_context(patch.object(macro,name,side_effect=RuntimeError('outside scoped test')))
            cache=Path(folder)/'cache.json';cache.write_text(json.dumps({'items':{'m14':prior}}))
            result=macro.run(Path(folder)/'out',cache_path=cache)['items']['m14']
        for key in ('source_evidence','last_verified_at','value','observation_date'):
            self.assertEqual(result[key],prior[key])
        self.assertTrue(result['cache_used']);self.assertEqual(result['status'],'STALE')

    def test_holiday_http_failure_retains_newer_cache_and_original_clock(self):
        import contextlib,tempfile
        from types import SimpleNamespace
        series={n:pd.Series(v) for n,v in self.original_series().items()}
        f=legacy.NetLiquidityTests().fake(series)
        f.m14_originals=self.row['source_evidence']['holiday_outstanding']['fred_originals']
        prior=copy.deepcopy(self.row)
        prior.update(status='OK',last_verified_at='2026-11-17T05:50:00Z')
        fixed_now=dt.datetime(2026,11,18,4,tzinfo=dt.timezone.utc)
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)
        clock=SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')});clock.datetime=Fixed
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(h,'fetch_holiday',side_effect=RuntimeError('synthetic NYFed timeout')))
            stack.enter_context(patch.object(macro,'dt',clock));stack.enter_context(patch.object(macro,'Fetcher',return_value=f))
            for name in ('latest','breakeven_5y','month_delta','ism_official','sahm_from_published','nfp','core_cpi','yahoo_price','cnn','lei_verified_history'):
                stack.enter_context(patch.object(macro,name,side_effect=RuntimeError('outside scoped test')))
            cache=Path(folder)/'cache.json';cache.write_text(json.dumps({'items':{'m14':prior}}))
            result=macro.run(Path(folder)/'out',cache_path=cache)['items']['m14']
        for key in ('source_evidence','last_verified_at','value','observation_date'):
            self.assertEqual(result[key],prior[key])
        self.assertTrue(result['cache_used']);self.assertEqual(result['status'],'STALE')

    def test_missing_91_day_and_normal_base_not_filled(self):
        series={n:pd.Series(v) for n,v in self.original_series().items()}
        series['WALCL']=series['WALCL'].drop(pd.Timestamp('2026-08-12'))
        f=legacy.NetLiquidityTests().fake(series);f.m14_originals=self.row['source_evidence']['holiday_outstanding']['fred_originals']
        with patch.object(h,'fetch_holiday',return_value=self.outstanding()):
            with self.assertRaisesRegex(ValueError,'13 週前同日值'):macro.netliq(f)

if __name__=='__main__':unittest.main()
