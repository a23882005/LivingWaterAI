"""Real original routines on synthetic caches; identity/data failures stop intake."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'系統工程/Family/W5'))
from family_input import digest
spec=importlib.util.spec_from_file_location('market_observations_test',HERE/'on_demand_market_observations.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class ObservationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.folder=self.root/'data/market_history/global';self.folder.mkdir(parents=True)
        self.path=self.folder/'SGOV.csv'
        self.rows=[{'Date':f'2026-09-{n:02d}','Open':100+n,'High':102+n,
                    'Low':99+n,'Close':101+n,'Volume':1000} for n in range(1,29)]
        self.write()
        self.manifest={'items':{'SGOV':{'status':'OK','rows':len(self.rows),
            'latest_observation':self.rows[-1]['Date'],'last_verified_utc':'2026-10-01T00:00:00Z'}}}
        self.write_manifest()
        self.snapshot={'client_id':'MEMBER','source_sha256':'a'*64,'tables':{
            'portfolio_position':[{'instrument_key':'I1'}],
            'portfolio_instrument':[{'instrument_key':'I1','ticker':'SGOV','identity_state':'KNOWN'}]}}
        raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-01T00:00:00Z',
            'verification':{'ready':True},'indicators':{
                'm02':{'status':'OK','value':3.4,'unit':'%','source':'https://official.example/hy','dataDate':'2026-09-30'},
                'm12':{'status':'OK','value':103.31,'unit':'','source':'https://finance.yahoo.com/quote/%5EMOVE/','dataDate':'2026-09-30'}}}
        self.macro={'payload':raw,'digest':digest(raw),'source_sha256':'b'*64}

    def write(self):
        with self.path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(self.rows[0]));w.writeheader();w.writerows(self.rows)

    def write_manifest(self):
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))

    def build(self):
        return M.build_member_market_observations(self.snapshot,[],self.macro,
            repo_root=self.root,evaluation_at='2026-10-02T00:00:00Z')

    def test_original_v75_credit_and_unknown_missing_metrics(self):
        result=M.evaluate_observed_history(self.rows,repo_root=ROOT,
            evaluation_at='2026-10-02T00:00:00Z',macro=self.macro,asset_id='SGOV')
        p=result['v75_original_predicates']
        self.assertEqual(p['PRED-004']['metrics']['hy_oas_bps'],'340.0')
        self.assertEqual(p['PRED-004']['original_result']['aggregate_state'],'HY_NORMAL')
        self.assertIsNone(p['PRED-005']['original_result']['aggregate_state'])
        self.assertEqual(p['PRED-005']['metrics'],{'move':'103.31'})
        self.assertEqual(p['PRED-001']['input_coverage'],'MISSING')
        self.assertTrue(all(not r['deployment_input_eligible'] for r in p.values()))
        self.assertFalse(result['formal_deployment_eligible'])
        self.assertIn('emv_14',result['numeric'])
        self.assertNotIn('emv_3_3',result['numeric'])
        named={r['name']:r for group in result['observed_named_signals'].values() for r in group}
        self.assertNotEqual(named['dif_up']['truth'],'UNKNOWN')
        self.assertNotEqual(named['ma5_gt_ma10_gt_ma20']['truth'],'UNKNOWN')
        self.assertEqual(named['atr_expanding_fast']['truth'],'UNKNOWN')
        self.assertEqual(named['kd_golden_cross']['truth'],'UNKNOWN')

    def test_stock_does_not_receive_bond_predicates(self):
        result=M.evaluate_observed_history(self.rows,repo_root=ROOT,
            evaluation_at='2026-10-02T00:00:00Z',macro=self.macro,asset_id='VT')
        self.assertEqual(result['v75_original_predicates'],{})
        self.assertEqual(result['v75_scope'],'NOT_A_V75_SUPPORTED_BOND')

    def configure_vwra_alias(self):
        folder=self.root/'系統工程/Family/W8';folder.mkdir(parents=True)
        row={'provider_symbol':'VWRA.L','reference_exchange':'XLON','reference_timezone':'Europe/London',
            'quote_currency':'USD','isin':'SYNTHETIC_ISIN','source_url':'https://issuer.example/synthetic',
            'verified_on':'2026-10-01','history_policy':'CONTIGUOUS_VALID_SUFFIX_FOR_ANALYSIS_ONLY',
            'scope':'ANALYSIS_REFERENCE_ONLY'}
        (folder/'market_identity_aliases.json').write_text(json.dumps({
            'schema_version':'Family.W8.AnalysisMarketAliases.v1','aliases':{'VWRA':row}}))
        self.snapshot['tables']['portfolio_instrument'][0].update(ticker='VWRA',quote_currency='USD')
        self.manifest['items']['VWRA.L']=self.manifest['items'].pop('SGOV');self.write_manifest()
        self.path=self.folder/'VWRA.L.csv';self.write()

    def test_reviewed_alias_preserves_holding_symbol_and_currency_checks(self):
        self.configure_vwra_alias();before=deepcopy(self.snapshot)
        with patch.object(M,'evaluate_observed_history',return_value={'formal_deployment_eligible':False}):
            asset=self.build()['assets'][0]
        self.assertEqual(asset['symbol'],'VWRA');self.assertEqual(asset['provider_symbol'],'VWRA.L')
        self.assertFalse(asset['analysis_identity_mapping']['held_exchange_inferred'])
        self.assertEqual(self.snapshot,before)
        self.snapshot['tables']['portfolio_instrument'][0]['quote_currency']='CHF'
        self.assertEqual(self.build()['missing'][0]['code'],'ANALYSIS_MARKET_ALIAS_IDENTITY_MISMATCH')

    def test_bad_prefix_uses_contiguous_suffix_without_repair_or_middle_row_deletion(self):
        self.configure_vwra_alias();self.rows[0]['High']=1;self.write();before=self.path.read_bytes()
        with patch.object(M,'evaluate_observed_history',return_value={'formal_deployment_eligible':False}) as engine:
            asset=self.build()['assets'][0]
        self.assertEqual(len(engine.call_args.args[0]),27)
        self.assertEqual(asset['history_quality']['excluded_prefix_rows'],1)
        self.assertEqual(asset['history_quality']['analysis_start'],'2026-09-02')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(asset['history_quality']['source_values_modified'])

    def test_bad_latest_bar_cannot_be_hidden_by_suffix_policy(self):
        self.configure_vwra_alias();self.rows[-1]['High']=1;self.write()
        with patch.object(M,'evaluate_observed_history') as engine:out=self.build()
        engine.assert_not_called()
        self.assertEqual(out['missing'][0]['code'],'CACHE_SAMPLE_INSUFFICIENT_AFTER_SOURCE_ERRORS')

    def test_close_only_components_do_not_invent_high_low_or_atr(self):
        first=M.evaluate_close_history(self.rows,repo_root=ROOT)
        changed=deepcopy(self.rows)
        for row in changed:row.update(High=-999,Low=999,Volume=-1)
        second=M.evaluate_close_history(changed,repo_root=ROOT)
        self.assertEqual(first['numeric'],second['numeric'])
        self.assertIsNotNone(first['numeric']['ma20'])
        self.assertIsNone(first['numeric']['atr14']);self.assertIsNone(first['numeric']['kd_k_9_3'])
        self.assertEqual(first['observed_named_signals']['right_signals'][0]['truth'],'UNKNOWN')

    def test_exact_member_symbol_cache_and_source_hash(self):
        with patch.object(M,'evaluate_observed_history',return_value={'formal_deployment_eligible':False}):
            out=self.build()
        self.assertEqual(out['client_id'],'MEMBER')
        self.assertEqual(out['assets'][0]['source_sha256'],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(out['assets'][0]['observed_date'],'2026-09-28')
        self.assertFalse(out['assets'][0]['formal_identity_verified'])

    def test_nato_is_not_canadian_nato(self):
        self.snapshot['tables']['portfolio_instrument'][0]['ticker']='NATO'
        self.manifest['items']['NATO.CN']=self.manifest['items'].pop('SGOV');self.write_manifest()
        out=self.build();self.assertEqual(out['assets'],[])
        self.assertEqual(out['missing'][0]['code'],'EXACT_SYMBOL_CACHE_UNAVAILABLE')

    def test_sealed_symbol_missing_from_registry_is_still_observed(self):
        self.snapshot['tables']['portfolio_position']=[]
        self.snapshot['tables']['portfolio_instrument']=[]
        self.snapshot['payload_digest']='bound-snapshot'
        holdings={'client_id':'MEMBER','source_db_sha256':'a'*64,
            'snapshot_digest':'bound-snapshot','analysis_security_positions':[
                {'symbol':'SGOV','instrument':None,'source_row':{'source_reference':'SYNTHETIC_SEALED_SOURCE'}}]}
        with patch.object(M,'evaluate_observed_history',return_value={'formal_deployment_eligible':False}):
            out=M.build_member_market_observations(self.snapshot,[],self.macro,
                repo_root=self.root,evaluation_at='2026-10-02T00:00:00Z',official_holdings=holdings)
        self.assertEqual(out['assets'][0]['symbol'],'SGOV')
        self.assertEqual(out['assets'][0]['instrument_registry_state'],'SOURCE_SYMBOL_ONLY')
        self.assertFalse(out['assets'][0]['formal_identity_verified'])
        holdings['source_db_sha256']='b'*64
        with self.assertRaisesRegex(PermissionError,'HOLDINGS_SNAPSHOT_MISMATCH'):
            M.build_member_market_observations(self.snapshot,[],self.macro,
                repo_root=self.root,evaluation_at='2026-10-02T00:00:00Z',official_holdings=holdings)

    def test_bad_ohlc_rejected(self):
        self.rows[-1]['High']=1;self.write()
        out=self.build();self.assertEqual(out['missing'][0]['code'],'CACHE_OHLCV_INVALID')

    def test_manifest_mismatch_rejected(self):
        self.manifest['items']['SGOV']['rows']+=1;self.write_manifest()
        self.assertEqual(self.build()['missing'][0]['code'],'CACHE_MANIFEST_MISMATCH')

    def test_future_verification_rejected(self):
        self.manifest['items']['SGOV']['last_verified_utc']='2030-01-01T00:00:00Z';self.write_manifest()
        self.assertEqual(self.build()['missing'][0]['code'],'CACHE_VERIFICATION_IN_FUTURE')

    def test_changed_source_during_calculation_rejected(self):
        def mutate(*a,**k):
            self.path.write_text('replaced');return {}
        with patch.object(M,'evaluate_observed_history',side_effect=mutate):out=self.build()
        self.assertEqual(out['assets'],[])
        self.assertEqual(out['missing'][0]['code'],'CACHE_CHANGED_DURING_CALCULATION')

    def test_macro_tampering_and_units_rejected(self):
        self.macro['payload']['indicators']['m02']['unit']='bps'
        with self.assertRaisesRegex(ValueError,'DIGEST'):M._macro_metrics(self.macro,'2026-10-02T00:00:00Z')
        self.macro['digest']=digest(self.macro['payload'])
        with self.assertRaisesRegex(ValueError,'UNIT_OR_SOURCE'):M._macro_metrics(self.macro,'2026-10-02T00:00:00Z')


if __name__=='__main__':unittest.main()
