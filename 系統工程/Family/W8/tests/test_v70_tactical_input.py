from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'系統工程/Family/W8')]
from v70_tactical_input import calculate

class V70ComponentTest(unittest.TestCase):
    def setUp(self):
        self.request={'client_id':'SYNTHETIC','owner':{'currency':'USD'},'confirmed_target':{'payload':{'draft':{
            'denominator':{'value_state':'KNOWN','amount':'1000000','currency':'TWD'}}}}}
        self.policy={'client_id':'SYNTHETIC','stock_percent':80,'bond_percent':20,'source_reference':'SYNTHETIC_APPROVED_BASE'}
    def test_original_recomputation_conserves_amounts_and_retains_unknown_bond_source(self):
        before=deepcopy((self.request,self.policy));out=calculate(ROOT,self.request,self.policy)
        self.assertEqual(out['allocation']['S0'],80);self.assertEqual(out['allocation']['B0'],20)
        self.assertEqual(sum(Decimal(v) for v in out['amounts'].values()),Decimal('1000000'))
        self.assertEqual(out['bond_score_source'],'UNKNOWN');self.assertIsNone(out['snapshot']['bScore'])
        self.assertTrue(out['bond_score_does_not_affect_this_allocation'])
        self.assertIsNone(out['native_currency_amounts']);self.assertEqual(out['native_currency_issue'],'V70_TACTICAL_BUDGET_FX_REQUIRED')
        self.assertEqual(out['source_html_sha256'],hashlib.sha256((ROOT/'系統工程/總經V70/V70-3-27.html').read_bytes()).hexdigest())
        self.assertEqual((self.request,self.policy),before)
    def test_new_base_is_sent_to_original_function_instead_of_scaling_old_result(self):
        a=calculate(ROOT,self.request,self.policy)
        other={**self.policy,'stock_percent':60,'bond_percent':40}
        b=calculate(ROOT,self.request,other)
        self.assertEqual(b['allocation']['S0'],60)
        self.assertNotEqual(a['allocation']['sTot'],b['allocation']['sTot'])
        self.assertEqual(a['allocation']['cTot'],b['allocation']['cTot'])
    def test_public_fx_binds_native_currency_without_changing_source_base(self):
        fx={'base_currency':'USD','quote_currency':'TWD','quote_per_base':'32','as_of':'2026-10-27','source_url':'https://example.test/fx'}
        out=calculate(ROOT,self.request,self.policy,fx)
        self.assertIsNone(out['native_currency_issue'])
        for k,value in out['native_currency_amounts'].items():self.assertEqual(Decimal(value)*32,Decimal(out['amounts'][k]))
        self.assertEqual(out['allocation_base']['currency'],'TWD')

    def test_cross_owner_rejected_and_absent_policy_not_inferred(self):
        self.assertIsNone(calculate(ROOT,self.request,None))
        with self.assertRaises(PermissionError):calculate(ROOT,self.request,{**self.policy,'client_id':'OTHER'})

    def test_selected_verified_feed_is_consumed_by_original_v70_components(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=json.loads((ROOT/'系統工程/總經V70/V70_macro_latest.json').read_text())
            path=Path(folder)/'synthetic-capture-of-public-feed.json';path.write_text(json.dumps(raw,sort_keys=True))
            source={'schema_version':'Family.W5.VerifiedMacroFeedSource.v1','local_path':str(path),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            request=deepcopy(self.request);request['macro_snapshot']={'source_sha256':source['sha256']}
            out=calculate(ROOT,request,self.policy,feed_source=source)
            self.assertEqual(out['source_feed_sha256'],source['sha256'])
            self.assertEqual(out['feed_as_of'],raw['asOf'])
            self.assertEqual(out['allocation']['S0'],80)
            request['macro_snapshot']['source_sha256']='f'*64
            with self.assertRaisesRegex(PermissionError,'MACRO_SOURCE_BINDING'):calculate(ROOT,request,self.policy,feed_source=source)

    def test_current_reference_is_preserved_and_does_not_replace_target_base(self):
        policy={**self.policy,'current_stock_percent':40,'current_bond_percent':60,'life_stage_code':'L6'}
        out=calculate(ROOT,self.request,policy)
        self.assertEqual(out['allocation']['S0'],80);self.assertEqual(out['allocation']['B0'],20)
        self.assertEqual(out['current_stock_bond_reference']['stock_percent'],40)
        self.assertEqual(out['allocation']['lifeStageCode'],'L6')
        self.assertIsNone(calculate(ROOT,self.request,self.policy)['current_stock_bond_reference'])
        self.assertEqual(calculate(ROOT,self.request,self.policy)['allocation']['lifeStageCode'],'UNKNOWN')

    def test_saved_cutoff_reexecutes_original_calculation_with_identical_source_bytes(self):
        request={**self.request,'evaluation_at':'2026-10-30T17:14:15Z'}
        first=calculate(ROOT,request,self.policy);second=calculate(ROOT,request,self.policy)
        self.assertEqual(first,second)
        self.assertEqual(first['snapshot']['calculatedAt'],'2026-10-30T17:14:15.000Z')
        self.assertEqual(sum(Decimal(v) for v in first['amounts'].values()),Decimal('1000000'))

    def test_naive_evaluation_clock_cannot_bind_a_formal_source(self):
        with self.assertRaisesRegex(ValueError,'V70_EVALUATION_AT_TIMEZONE_REQUIRED'):
            calculate(ROOT,{**self.request,'evaluation_at':'2026-10-30T17:14:15'},self.policy)

if __name__=='__main__':unittest.main()
