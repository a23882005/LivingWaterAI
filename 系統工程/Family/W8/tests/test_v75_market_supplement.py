"""Dated source replay, business-day gaps and unchanged canonical freshness."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_market_supplement as S
from family_input import digest
from bond_advisory import candidates
candidates(ROOT)
from v75_runtime.predicates import EVALUATORS


class MarketSupplementTest(unittest.TestCase):
    def fixture(self,folder,*,missing=False,available='2026-10-29T01:00:00Z'):
        dates=['2026-10-21','2026-10-22','2026-10-23','2026-10-26','2026-10-27','2026-10-28']
        stamps=[int(datetime.fromisoformat(d+'T13:30:00+00:00').timestamp()) for d in dates]
        values=[100,102,None if missing else 105,106,108,110]
        data={'chart':{'error':None,'result':[{'meta':{'symbol':'^MOVE',
            'exchangeTimezoneName':'America/New_York','dataGranularity':'1d',
            'currentTradingPeriod':{'regular':{'end':int(datetime(2026,10,28,20,tzinfo=timezone.utc).timestamp())}}},
            'timestamp':stamps,'indicators':{'quote':[{'close':values}]}}]}}
        raw=Path(folder)/'synthetic-move.json';raw.write_text(json.dumps(data));h=sha256(raw.read_bytes()).hexdigest()
        receipt=Path(folder)/'synthetic-receipt.json';receipt.write_text(json.dumps({
            'url':'https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE?interval=1d',
            'http_status':200,'sha256':h,'available_at':available,
            'requested_at':(S._time(available)-timedelta(seconds=1)).isoformat()}))
        source={'local_path':str(raw),'sha256':h,'receipt_path':str(receipt),
            'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}
        return source,raw

    def test_exact_comparison_crosses_weekend_and_preserves_macro_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            source,_=self.fixture(folder);at='2026-10-29T02:00:00Z';s=S.read(source,at)
            self.assertEqual(s['comparison_date'],'2026-10-21')
            self.assertEqual(s['metrics']['move_pct_change_5bd'],'10.0')
            self.assertFalse(s['exchange_close_attested'])
            raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-27T01:00:00Z',
                'verification':{'ready':True},'indicators':{'m12':{'status':'OK','value':103,
                    'unit':'','source':'https://provider.example/MOVE','dataDate':'2026-10-26'}}}
            macro={'payload':raw,'digest':digest(raw),'source_sha256':'c'*64}
            result=EVALUATORS['PRED-005']({'move':'103'},S._time(at),
                ['OBSERVED_CACHE_ONLY','ORIGINAL_NUMERIC_FORMULAS','FULL_SOURCE_COVERAGE_PENDING'])
            old={'metrics':{'move':'103'},'original_result':result.model_dump(mode='json'),
                'input_coverage':'PARTIAL','original_result_as_of_basis':'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE',
                'input_freshness_verified':False,'original_default_freshness_is_not_attestation':True,
                'deployment_input_eligible':False}
            observation={'assets':[{'symbol':'SGOV','call_trace':[],
                'v75_original_predicates':{'PRED-005':old}}]};before=deepcopy(observation)
            out=S.apply(observation,s,evaluation_at=at,repo_root=ROOT);slot=out['assets'][0]['v75_original_predicates']['PRED-005']
            self.assertEqual(slot['original_result']['aggregate_state'],'NORMAL')
            self.assertFalse(slot['deployment_input_eligible'])
            self.assertFalse(slot['input_freshness_verified'])
            self.assertEqual(slot['previous_macro_observation'],old)
            self.assertEqual(observation,before)
            req={'evaluation_at':at,'macro_snapshot':macro}
            report={'bond_market_supplement':s,'analysis_result':{'positions':[{'market':out['assets'][0]}]}}
            context={'bond_market_supplement_source':source}
            S.validate(req,context,report,ROOT)
            slot['metrics']['move']='999'
            with self.assertRaisesRegex(PermissionError,'PREDICATE_REPLAY'):S.validate(req,context,report,ROOT)

    def test_missing_business_day_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            source,_=self.fixture(folder,missing=True)
            with self.assertRaisesRegex(ValueError,'BUSINESS_DAY_COVERAGE'):
                S.read(source,'2026-10-29T02:00:00Z')

    def test_intraday_and_future_capture_are_not_closed_historical_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            source,_=self.fixture(folder,available='2026-10-28T15:00:00Z')
            with self.assertRaisesRegex(ValueError,'NONCLOSED'):S.read(source,'2026-10-29T02:00:00Z')
            source,_=self.fixture(folder,available='2026-10-30T01:00:00Z')
            with self.assertRaisesRegex(PermissionError,'RECEIPT_BINDING'):S.read(source,'2026-10-29T02:00:00Z')

    def test_modified_provider_bytes_rejected_before_use(self):
        with tempfile.TemporaryDirectory() as folder:
            source,path=self.fixture(folder);path.write_text('{}')
            with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):S.read(source,'2026-10-29T02:00:00Z')


if __name__=='__main__':unittest.main()
