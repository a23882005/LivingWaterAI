"""Mode selection is independent of funding, Gap and technical enthusiasm."""
from copy import deepcopy
from pathlib import Path
import sys,unittest,tempfile,hashlib
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from formal_mode_analysis import resolve_mode_context,target_for_symbol,order_source,order_result_status,native_orders,native,tri
from approved_target_input import build_approved_target_view,enrich_document_target_view,_digest

class ModeAnalysisTest(unittest.TestCase):
    def context(self,**kw):
        args=dict(up=False,right=False,left_price_conditions={'price':False},
            fundamentals_viable=True,left_safety=True,
            stage_facts={k:True for k in ('asset_identity','primary_framework','fundamentals_viable','valuation_legal')})
        args.update(kw);return resolve_mode_context(ROOT,**args)
    def test_false_right_up_does_not_prevent_base(self):
        out=self.context()
        self.assertEqual(out['selected_mode'],'Base Deployment');self.assertEqual(out['formal_stage'],'STAGE_1')
        self.assertEqual(out['canonical_target_rate'],'0.1')
        self.assertFalse(out['four_modes']['Base']['technical_confirmation_required'])
    def test_left_uses_price_or_without_an_oversold_ticket(self):
        out=self.context(left_price_conditions={'price':False,'valuation':True,'near_support':None})
        self.assertEqual(out['selected_mode'],'Left Overweight')
        self.assertEqual(out['formal_stage'],'UNKNOWN')
        self.assertFalse(out['four_modes']['Left']['oversold_required_for_entry'])
        self.assertEqual(self.context(left_price_conditions={'price':True},left_stage='STAGE_4')['canonical_target_rate'],'0.45')
    def test_unknown_higher_mode_is_not_coerced_to_base(self):
        self.assertEqual(self.context(left_price_conditions={'price':None})['selected_mode'],'UNKNOWN')
        self.assertEqual(self.context(up=None)['selected_mode'],'UNKNOWN')
    def test_reference_stage_does_not_fill_missing_required_fact(self):
        out=self.context(stage_facts={'asset_identity':True,'primary_framework':True,'fundamentals_viable':None,'valuation_legal':True})
        self.assertEqual(out['native_stage_result']['stage'],'STAGE_1')
        self.assertEqual(out['formal_stage'],'UNKNOWN');self.assertIsNone(out['canonical_target_rate'])
        self.assertEqual(out['stage_required_unknown_fields'],['fundamentals_viable'])
    def test_stage_does_not_read_cash_gap_or_permission(self):
        self.assertEqual(self.context(up=True,trend_stage='STAGE_8')['canonical_target_rate'],'0.95')
        self.assertIsNone(self.context(up=True)['canonical_target_rate'])
        self.assertEqual(self.context(right=True)['selected_mode'],'Right Confirmation')
    def test_unknown_orders_and_absent_target_are_not_zero(self):
        req={'client_snapshot':{'payload':{'tables':{'portfolio_snapshot_item':[{'entity_key':'IB_SCREEN',
            'field_key':'order_tab_count','value_text':'2'}]}}}}
        self.assertIsNone(order_source(req)['active_orders'])
        self.assertTrue(target_for_symbol(req,'VT')['absence_is_not_zero'])
    def test_no_orders_confirmation_is_scoped_and_does_not_replace_old_screenshots(self):
        request={'client_id':'SYNTHETIC','owner':{'client_id':'SYNTHETIC','account':'A'},
            'run_id':'RUN','client_snapshot':{'payload':{'source_sha256':'a'*64,'tables':{
            'portfolio_snapshot_item':[{'entity_key':'IB_SCREEN','field_key':'order_tab_count','value_text':'5'}]}}}}
        proof={'schema_version':'Family.W8.OwnerNoOpenOrders.v1','client_id':'SYNTHETIC',
            'owner':deepcopy(request['owner']),'no_open_orders':True,'source_reference':'SYNTHETIC_OWNER_STATEMENT'}
        before=deepcopy(request)
        self.assertEqual(order_source(request,proof)['active_orders'],[])
        self.assertEqual(request,before)
        self.assertIsNone(order_source(request)['active_orders'])
        proof['owner']['account']='B'
        with self.assertRaisesRegex(PermissionError,'SCOPE_MISMATCH'):order_source(request,proof)

    def test_numeric_truth_is_not_a_boolean_assertion(self):
        self.assertIsNone(tri(0));self.assertIsNone(tri(1))

    def test_broker_replacement_remaining_quantity_reaches_original_gap_calculator(self):
        request={'client_id':'SYNTHETIC','owner':{'account':'A'},'run_id':'R',
            'broker_snapshot_source_digest':'a'*64}
        source={'schema_version':'Family.W5.BrokerOrderExposure.v1',
            'client_id':'SYNTHETIC','owner':{'account':'A'},'run_id':'R',
            'source_descriptor_digest':'a'*64,'status':'BROKER_WORKING_EXPOSURE_VERIFIED',
            'complete_for_open_order_exposure':True,'lifecycle_fully_resolved':False,
            'active_orders':[{'asset_id':'VT','order_intent_id':'SYNTHETIC:1','side':'BUY',
                'state':'REPLACE_PENDING','order_qty':'2','confirmed_filled_qty':'1'}]}
        orders=order_source(request,broker_orders=source)
        dep,_,_=native(ROOT)
        gap=dep.calculate_position_gap(project_target_position_amount='1000',target_rate='1',
            confirmed_position_qty='10',canonical_valuation_price='90',active_orders=native_orders(ROOT,orders,'VT'))
        self.assertEqual(str(gap.active_buy_exposure_amount),'90')
        self.assertEqual(str(gap.final_deployment_gap_amount),'10')
        self.assertIn('REPLACEMENT_LIFECYCLE_PENDING',order_result_status(orders))
        self.assertEqual(native_orders(ROOT,orders,'OTHER'),())
        source['owner']['account']='OTHER'
        with self.assertRaisesRegex(PermissionError,'BINDING_MISMATCH'):
            order_source(request,broker_orders=source)

class ExplicitTargetTest(unittest.TestCase):
    def pack(self,path,line):
        return build_approved_target_view(client_id='fam_'+'a'*32,source_path=path,
            source_reference='SYNTHETIC_APPROVED_DOC',source_available_at='2026-10-27T00:00:00Z',
            target_version=1,allocation_version='SYNTHETIC-v1',rows=[{'source_line':line,'weight':'1'}],
            mappings=[{'instrument_id':'SYNTHETIC_VT','ticker':'VT','asset_type':'股票ETF'}])
    def test_explicit_twd_is_not_approximate_usd_or_current_nav(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.md';line='| VT | 100% | 123,000 | 約3,900 |'
            p.write_text('| 標的 | 目標比例 | 目標台幣 | 約當美元 |\n|---|---|---|---|\n'+line+'\n')
            pack=self.pack(p,line);view,proof=enrich_document_target_view(pack['target'],pack['trusted_approved_target_source'])
            money=target_for_symbol({'confirmed_target':view},'VT')
            self.assertEqual((money['amount'],money['currency']),('123000','TWD'))
            self.assertEqual(view['payload']['draft']['denominator']['amount'],'123000')
            self.assertEqual(proof['target_view_digest'],_digest(view))
            again,again_proof=enrich_document_target_view(view,proof)
            self.assertEqual((again,again_proof),(view,proof))
    def test_old_unknown_view_is_enriched_without_approval_or_weight_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.md';line='| VT | 100% | 120 |'
            p.write_text('| 標的 | 目標比例 | 目標金額（US$） |\n|---|---|---|\n'+line+'\n')
            pack=self.pack(p,line);old=pack['target'];old['payload']['draft']['target_lines'][0]['target_amount']={'value_state':'UNKNOWN','amount':None,'currency':None}
            proof=pack['trusted_approved_target_source'];proof['target_view_digest']=_digest(old)
            before=deepcopy(old);raw=p.read_bytes();view,newproof=enrich_document_target_view(old,proof)
            self.assertEqual(old,before);self.assertEqual(p.read_bytes(),raw)
            self.assertEqual(view['payload']['draft']['target_lines'][0]['target_amount']['amount'],'120')
            self.assertEqual(view['payload']['confirmation_evidence'],old['payload']['confirmation_evidence'])
            self.assertEqual(view['payload']['draft']['target_lines'][0]['weight'],old['payload']['draft']['target_lines'][0]['weight'])
            view['payload']['draft']['target_lines'][0]['target_amount']['amount']='999';newproof['target_view_digest']=_digest(view)
            with self.assertRaisesRegex(ValueError,'SOURCE_CONFLICT'):enrich_document_target_view(view,newproof)
    def test_ambiguous_or_missing_currency_does_not_create_money(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.md';line='| VT | 100% | 120 |'
            p.write_text('| 標的 | 目標比例 | 目標金額 |\n|---|---|---|\n'+line+'\n')
            money=target_for_symbol({'confirmed_target':self.pack(p,line)['target']},'VT')
            self.assertEqual(money['value_state'],'UNKNOWN')

if __name__=='__main__':unittest.main()
