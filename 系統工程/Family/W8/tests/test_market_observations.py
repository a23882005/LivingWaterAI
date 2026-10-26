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

    def test_stock_does_not_receive_bond_predicates(self):
        result=M.evaluate_observed_history(self.rows,repo_root=ROOT,
            evaluation_at='2026-10-02T00:00:00Z',macro=self.macro,asset_id='VT')
        self.assertEqual(result['v75_original_predicates'],{})
        self.assertEqual(result['v75_scope'],'NOT_A_V75_SUPPORTED_BOND')

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
