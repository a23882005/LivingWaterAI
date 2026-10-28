"""Formal v1.0 observations keep existing facts distinct from validity."""
from pathlib import Path
import sys,unittest
from decimal import Decimal as D
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from v10_source_observations import forward_observations,macro_observations,credit_logic

class FormalSourceTest(unittest.TestCase):
    def snapshot(self):
        raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-27T01:00:00Z',
            'verification':{'ready':True},'indicators':{}}
        for key,value,unit in [('m02','3.38','%'),('m07','19.45',''),('m12','102.19',''),('m03_vt','15.9','倍 Forward')]:
            raw['indicators'][key]={'value':value,'unit':unit,'status':'OK','dataDate':'2026-10-23',
                'source':'SYNTHETIC_PROVIDER','lastVerifiedAt':'2026-10-27T00:59:00Z'}
        raw['indicators']['m03_vt']['sourceEvidence']={'label':'Forward PE','value':'15.9','source_url':'SYNTHETIC_PROVIDER'}
        return {'payload':raw,'digest':digest(raw),'source_sha256':'a'*64}
    def test_existing_forward_value_is_mapped_without_invented_validity(self):
        row=forward_observations(self.snapshot(),'VT','2026-10-27T21:00:00Z')[0]
        self.assertEqual(row['current'],'15.9');self.assertEqual(row['valuation_level'],'NORMAL')
        self.assertEqual(row['freshness'],'UNKNOWN');self.assertEqual(row['pit_status'],'UNVERIFIABLE')
        self.assertEqual(row['as_of'],'2026-10-23')
        self.assertEqual(forward_observations(self.snapshot(),'VWRA','2026-10-27T21:00:00Z'),[])
    def test_published_v70_is_accepted_for_current_analysis_without_fake_publication_time(self):
        from copy import deepcopy
        s=self.snapshot();before=deepcopy(s)
        metrics=forward_observations(s,'VT','2026-10-28T01:00:00Z',purpose='CURRENT_HOLDINGS_ANALYSIS')
        self.assertTrue(metrics[0]['current_source_accepted']);self.assertFalse(metrics[0]['historical_publication_time_verified'])
        self.assertFalse(metrics[0]['execution_input_eligible'])
        self.assertIsNone(metrics[0]['available_at']);self.assertIsNone(metrics[0]['valid_until'])
        self.assertEqual(metrics[0]['strict_contract_validity']['pit_status'],'UNVERIFIABLE')
        root=HERE.parents[2];sys.path.insert(0,str(root/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
        from livingwater_v82_runtime.core_rules import resolve_valuation
        result=resolve_valuation(metrics,['FORWARD_PE','TRAILING_PE','CAPE','PB','FCF_YIELD'])
        self.assertEqual(result.level.value,'NORMAL');self.assertTrue(result.formal_output_eligible)
        self.assertEqual(s,before)
        strict=forward_observations(s,'VT','2026-10-28T01:00:00Z')[0]
        self.assertEqual(strict['freshness'],'UNKNOWN');self.assertEqual(strict['pit_status'],'UNVERIFIABLE')
    def test_current_acceptance_still_requires_published_verified_v70_and_exact_field(self):
        s=self.snapshot();s['payload']['verification']['ready']=False;s['digest']=digest(s['payload'])
        self.assertEqual(forward_observations(s,'VT','2026-10-28T01:00:00Z',purpose='CURRENT_HOLDINGS_ANALYSIS'),[])
        s=self.snapshot();s['payload']['indicators']['m03_vt']['sourceEvidence']['label']='Trailing PE';s['digest']=digest(s['payload'])
        with self.assertRaisesRegex(ValueError,'DEFINITION_OR_SOURCE'):
            forward_observations(s,'VT','2026-10-28T01:00:00Z',purpose='CURRENT_HOLDINGS_ANALYSIS')
    def test_checked_capture_is_a_known_by_bound_not_formal_pit(self):
        s=self.snapshot();s['capture_receipt']={'schema_version':'Family.W5.SourceCaptureBound.v1',
            'captured_at':'2026-10-27T20:00:00Z','source_sha256':s['source_sha256'],
            'payload_digest':s['digest'],'basis':'EXACT_SOURCE_BYTES_READ_AND_HASH_CHECKED'}
        result=forward_observations(s,'VT','2026-10-27T21:00:00Z')[0]
        self.assertTrue(result['known_by_capture_verified'])
        self.assertEqual(result['pit_status'],'UNVERIFIABLE');self.assertIsNone(result['available_at'])
        self.assertIn('field_available_at/PIT',result['missing_contracts'])
        s['capture_receipt']['captured_at']='2026-10-27T22:00:00Z'
        self.assertFalse(forward_observations(s,'VT','2026-10-27T21:00:00Z')[0]['known_by_capture_verified'])
        s['capture_receipt']['captured_at']='2026-10-27T20:00:00Z';s['capture_receipt']['payload_digest']='tampered'
        self.assertFalse(forward_observations(s,'VT','2026-10-27T21:00:00Z')[0]['known_by_capture_verified'])
    def test_wrong_metric_label_is_not_forward_pe(self):
        s=self.snapshot();s['payload']['indicators']['m03_vt']['sourceEvidence']['label']='Trailing PE';s['digest']=digest(s['payload'])
        with self.assertRaisesRegex(ValueError,'DEFINITION_OR_SOURCE'):forward_observations(s,'VT','2026-10-27T21:00:00Z')
    def test_valid_explicit_contract_reaches_original_native_valuation(self):
        s=self.snapshot();row=s['payload']['indicators']['m03_vt']
        row.update(frequency='DAILY',available_at='2026-10-27T00:59:00Z',valid_until='2026-10-27T22:00:00Z')
        s['digest']=digest(s['payload']);metrics=forward_observations(s,'VT','2026-10-27T21:00:00Z')
        self.assertEqual(metrics[0]['freshness'],'FRESH');self.assertEqual(metrics[0]['pit_status'],'VERIFIED')
        root=HERE.parents[2];sys.path.insert(0,str(root/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
        from livingwater_v82_runtime.core_rules import resolve_valuation
        result=resolve_valuation(metrics,['FORWARD_PE','TRAILING_PE','CAPE','PB','FCF_YIELD'])
        self.assertEqual(result.level.value,'NORMAL');self.assertTrue(result.formal_output_eligible)
    def test_expired_contract_is_stale_and_future_availability_is_not_verified(self):
        s=self.snapshot();row=s['payload']['indicators']['m03_vt']
        row.update(frequency='DAILY',available_at='2026-10-27T00:59:00Z',valid_until='2026-10-27T20:00:00Z')
        s['digest']=digest(s['payload']);self.assertEqual(forward_observations(s,'VT','2026-10-27T21:00:00Z')[0]['freshness'],'STALE')
        row['available_at']='2026-10-27T22:00:00Z';s['digest']=digest(s['payload'])
        self.assertEqual(forward_observations(s,'VT','2026-10-27T21:00:00Z')[0]['pit_status'],'UNVERIFIABLE')
    def test_known_bands_survive_missing_credit_event_coverage(self):
        result=macro_observations(self.snapshot(),'2026-10-27T21:00:00Z')
        self.assertEqual(result['observed']['hy_oas']['value'],'338.00')
        self.assertEqual(result['observed']['move']['band'],'ELEVATED')
        self.assertEqual(result['credit']['C1'],'TRUE');self.assertEqual(result['credit']['C2'],'FALSE')
        self.assertEqual(result['credit']['C3'],'UNKNOWN');self.assertEqual(result['credit']['risk_level'],'UNKNOWN')
        self.assertEqual(result['credit']['proven_lower_bound'],1);self.assertEqual(result['credit']['possible_upper_bound'],3)
    def test_known_higher_risk_short_circuits_unrelated_missing_values(self):
        result=credit_logic(None,None,None,official=True)
        self.assertEqual(result['risk_level'],3)
        result=credit_logic(D(200),D(10),D(80),rapid=False,official=False)
        self.assertEqual(result['risk_level'],0)
    def test_source_tampering_and_future_observation_are_rejected(self):
        s=self.snapshot();s['payload']['indicators']['m02']['value']='0'
        with self.assertRaisesRegex(ValueError,'BINDING'):macro_observations(s,'2026-10-27T21:00:00Z')
        s=self.snapshot();s['payload']['indicators']['m02']['dataDate']='2026-10-28';s['digest']=digest(s['payload'])
        with self.assertRaisesRegex(ValueError,'FUTURE'):macro_observations(s,'2026-10-27T21:00:00Z')

if __name__=='__main__':unittest.main()
