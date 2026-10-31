"""Synthetic proof qualification and unchanged native Core arbitration."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from copy import deepcopy
from hashlib import sha256
import json,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from v82_core_source import read,SAFETY
from native_asset_source import native_core_observation


class CoreSourceTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.request={'client_id':'fam_'+'a'*32,'owner':{'client_id':'fam_'+'a'*32,'account':'SYNTHETIC_ACCOUNT'},
            'evaluation_at':'2026-10-30T00:03:00Z','client_snapshot':{'payload':{'source_sha256':'a'*64}}}
        self.proof_file=self.root/'proof.txt';self.proof_file.write_text('SYNTHETIC_OPERATOR_EVIDENCE')
        self.proof={'local_path':str(self.proof_file),'sha256':sha256(self.proof_file.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_PRODUCER','methodology_reference':'SYNTHETIC_APPROVED_SOURCE_CONTRACT',
            'as_of':'2026-10-30T00:00:00Z','available_at':'2026-10-30T00:01:00Z',
            'valid_until':'2026-10-30T01:00:00Z','pit_status':'VERIFIED','pit_receipt_reference':'SYNTHETIC_PIT_RECEIPT'}
        self.data={'schema_version':'Family.W8.V82CoreSource.v1','client_id':self.request['client_id'],
            'owner':self.request['owner'],'asset_id':'SYNTHETIC_ASSET','source_db_sha256':'a'*64,
            'available_at':'2026-10-30T00:02:00Z','source_reference':'SYNTHETIC_BINDING','leaves':{}}
        self.observed={'source_path':'SYNTHETIC_MARKET','source_sha256':'b'*64,
            'observed_named_signals':{k:[{'truth':'FALSE'}]*n for k,n in
                [('right_signals',7),('up_price',6),('up_confirm',6),('down_break',6),('down_accel',6)]}}

    def source(self):
        path=self.root/'source.json';path.write_text(json.dumps(self.data))
        return read({'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()},self.request,'SYNTHETIC_ASSET')

    def leaf(self,name,value,**extra):
        self.data['leaves'][name]={'value':value,'proof':deepcopy(self.proof),**extra}

    def all_safety(self):
        for name in SAFETY:
            extra={'coverage':{'required_domains':['SYNTHETIC_DOMAIN'],'checked_domains':['SYNTHETIC_DOMAIN'],
                'event_registry_checkpoint':'SYNTHETIC_CHECKPOINT','coverage_cutoff':self.proof['as_of']}} if name=='safety.material_events' else {}
            self.leaf(name,'TRUE',**extra)
        self.leaf('hard_gate_predicates',['FALSE'],complete_predicate_scope_verified=True)

    def evaluate(self,source=None):
        return native_core_observation(ROOT,self.observed,broad_etf=True,qualified_core_source=source)

    def test_missing_source_keeps_native_unknown_and_all_safety_slots(self):
        out=self.evaluate()
        self.assertEqual(out['result']['permission']['hard_gate'],'UNKNOWN')
        self.assertEqual({r['name'] for r in out['actual_inputs']['safety_facts']},set(SAFETY))
        self.assertFalse(out['result']['permission']['new_buy_order_permission'])

    def test_one_valid_leaf_never_erases_missing_other_domains(self):
        self.leaf('safety.macro','TRUE');out=self.evaluate(self.source())
        self.assertFalse(out['result']['permission']['new_buy_order_permission'])
        gaps={r['field_path'] for r in out['input_gaps']}
        self.assertNotIn('safety.macro',gaps);self.assertIn('safety.material_events',gaps)

    def test_qualified_inputs_reach_original_native_arbiter_and_hard_gate_wins(self):
        self.all_safety();out=self.evaluate(self.source())
        self.assertEqual(out['result']['permission']['hard_gate'],'NOT_TRIGGERED')
        self.assertTrue(out['result']['permission']['new_buy_order_permission'])
        self.leaf('hard_gate_predicates',['TRUE'],complete_predicate_scope_verified=True)
        out=self.evaluate(self.source())
        self.assertFalse(out['result']['permission']['new_buy_order_permission'])
        self.assertEqual(out['result']['permission']['hard_gate'],'TRIGGERED')

    def test_wrong_asset_owner_or_database_scope_rejected(self):
        for key,value in [('asset_id','OTHER'),('owner',{}),('source_db_sha256','f'*64)]:
            old=self.data[key];self.data[key]=value
            with self.subTest(key=key),self.assertRaises(PermissionError):self.source()
            self.data[key]=old

    def test_changed_proof_stale_future_and_unverifiable_pit_rejected(self):
        for change in [{'sha256':'f'*64},{'valid_until':'2026-10-30T00:02:00Z'},
            {'available_at':'2026-10-31T00:00:00Z'},{'pit_status':'NOT_APPLICABLE'},
            {'methodology_reference':None}]:
            self.leaf('safety.macro','TRUE');self.data['leaves']['safety.macro']['proof'].update(change)
            with self.subTest(change=change),self.assertRaises(PermissionError):self.source()

    def test_news_without_full_negative_search_coverage_cannot_clear_events(self):
        self.leaf('safety.material_events','TRUE')
        with self.assertRaisesRegex(PermissionError,'EVENT_COVERAGE'):self.source()

    def test_incomplete_hard_gate_scope_cannot_clear_gate(self):
        self.leaf('hard_gate_predicates',['FALSE'])
        with self.assertRaisesRegex(PermissionError,'HARD_GATE_SCOPE'):self.source()

    def test_qualified_own_metric_replaces_only_matching_unknown_metric(self):
        metric={'metric_name':'FORWARD_PE','current':'15','historical_median':'20','unit':'multiple',
            'source_reference':self.proof['source_reference'],'source_sha256':self.proof['sha256'],
            'as_of':self.proof['as_of'],'freshness':'FRESH','pit_status':'VERIFIED','data_quality':'OK'}
        self.leaf('valuation_metrics',[metric]);out=self.evaluate(self.source())
        self.assertEqual(out['result']['valuation']['level'],'CHEAP')
        self.assertEqual(out['result']['valuation']['primary_metric'],'FORWARD_PE')
        with self.assertRaisesRegex(PermissionError,'OWN_WATERFALL'):
            native_core_observation(ROOT,self.observed,valuation_waterfall=['PB'],qualified_core_source=self.source())

    def test_etf_thesis_and_stock_structure_cannot_cross_applicability(self):
        self.leaf('structural_confirmation','TRUE')
        with self.assertRaises(PermissionError):self.evaluate(self.source())
        self.data['leaves']={};self.leaf('safety.etf_structure','TRUE')
        with self.assertRaises(PermissionError):native_core_observation(ROOT,self.observed,broad_etf=False,qualified_core_source=self.source())
