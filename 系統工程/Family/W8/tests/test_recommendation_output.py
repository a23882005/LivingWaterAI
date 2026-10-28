"""Recommendation amounts are distinct from broker execution permission."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'系統工程/Family/W5'),str(ROOT/'系統工程/Family/W8')]
from current_analysis_delivery import recommendation_amounts
from mentor_bridge import explain_native,MentorError
from runtime_loader import load_c_module


class RecommendationOutputTest(unittest.TestCase):
    def setUp(self):
        self.owner={'client_id':'SYNTHETIC','currency':'USD','account':'SYNTHETIC_ACCOUNT'}
        self.row={'owner':self.owner,'holding':{'quantity':'5','quantity_state':'KNOWN'},
            'native_product_identity':{'registry_identity':{'quote_currency':'USD'}},
            'market':{'observed_close':'100','observed_date':'2026-10-27'},
            'formal_conclusion':{'approved_project_target':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}}
        self.judgment={'target_rate_reference':'0.95','target_amount_reference':'950'}
    def compute(self,trial=None):
        return recommendation_amounts(self.row,self.judgment,ROOT,cash_trial=trial)
    def test_original_gap_component_computes_without_claiming_missing_orders_are_empty(self):
        out=self.compute()
        self.assertEqual(out['confirmed_holdings_component']['positive_gap_amount'],'450.00')
        self.assertEqual(out['confirmed_position_amount'],'500')
        self.assertIsNone(out['buy_gap_amount'])
        self.assertIn('active_orders_and_fill_reconciliation',out['missing_fields'])
        self.assertIn('V82.calculate_position_gap:confirmed_holdings_component_only',out['call_trace'])
    def test_explicit_approved_usd_column_removes_fx_dependency_without_inventing_rate(self):
        target=self.row['formal_conclusion']['approved_project_target']
        target.update(currency='TWD',amount='31500',source_row='| SYNTHETIC | 10% | NT$31,500 | US$1,000.00 |')
        out=self.compute()
        self.assertEqual(target['amount'],'31500');self.assertEqual(target['currency'],'TWD')
        self.assertEqual(out['calculation_target']['amount'],'1000.00')
        self.assertFalse(out['calculation_target']['fx_inferred'])
        self.assertNotIn('target_to_position_currency_FX',out['missing_fields'])
        self.assertEqual(out['confirmed_holdings_component']['positive_gap_amount'],'450.0000')

    def test_public_fx_enables_original_confirmed_holdings_gap_without_clearing_orders(self):
        from current_analysis_delivery import recommendation_amounts
        target=self.row['formal_conclusion']['approved_project_target']
        target.update(currency='TWD',amount='32000')
        fx={'base_currency':'USD','quote_currency':'TWD','quote_per_base':'32','as_of':'2026-10-27','source_url':'https://example.test/fx'}
        out=recommendation_amounts(self.row,self.judgment,ROOT,fx_observation=fx)
        self.assertEqual(out['confirmed_holdings_component']['positive_gap_amount'],'450.00')
        self.assertNotIn('target_to_position_currency_FX',out['missing_fields'])
        self.assertIn('active_orders_and_fill_reconciliation',out['missing_fields'])
        self.assertIsNone(out['buy_gap_amount'])

    def test_cross_currency_is_not_subtracted_without_fx(self):
        self.row['formal_conclusion']['approved_project_target']['currency']='TWD'
        out=self.compute()
        self.assertIsNone(out['confirmed_holdings_component'])
        self.assertEqual(out['unresolved_gap_formula']['confirmed_amount'],'500')
        self.assertIn('target_to_position_currency_FX',out['missing_fields'])
    def test_owner_cash_zero_trial_limits_only_cash_ceiling(self):
        trial={'owner':deepcopy(self.owner),'currency':'USD','decimal_values':{'available':'0','total':'554.1'},
            'assumptions':[{'field_path':'cash_state.available','assumed_value':'0'}]}
        out=self.compute(trial)
        self.assertEqual(out['cash_only_trial_buy_ceiling'],'0')
        self.assertEqual(out['confirmed_holdings_component']['positive_gap_amount'],'450.00')
        self.assertIsNone(out['buy_gap_amount'])
        trial['owner']['account']='OTHER'
        self.assertIsNone(self.compute(trial)['cash_only_trial_buy_ceiling'])
    def test_quote_currency_is_not_assumed_from_account_currency(self):
        self.row['native_product_identity']['registry_identity']['quote_currency']=None
        out=self.compute()
        self.assertIsNone(out['position_currency']);self.assertIsNone(out['confirmed_position_amount'])
        self.assertIn('verified_quote_currency',out['missing_fields'])
    def test_explicit_holding_price_unit_supplies_missing_registry_currency(self):
        self.row['native_product_identity']['registry_identity']['quote_currency']=None
        self.row['native_product_identity']['holding_price_currency_source']={
            'quote_currency':'USD','registry_conflict':False}
        out=self.compute()
        self.assertEqual(out['confirmed_position_amount'],'500')
        self.assertNotIn('verified_quote_currency',out['missing_fields'])
        self.row['native_product_identity']['registry_identity']['quote_currency']='EUR'
        out=self.compute()
        self.assertIsNone(out['confirmed_position_amount'])
        self.assertIn('verified_quote_currency',out['missing_fields'])
    def test_over_target_is_not_automatically_a_sell_recommendation(self):
        self.row['holding']['quantity']='12'
        out=self.compute()
        self.assertEqual(out['confirmed_holdings_component']['signed_gap_amount'],'-250.00')
        self.assertEqual(out['confirmed_holdings_component']['positive_gap_amount'],'0')
        self.assertTrue(out['excess_over_target_is_not_sell_instruction'])
    def test_native_work9_to_mentor_keeps_advice_amounts_without_trade_permission(self):
        req=json.loads((ROOT/'系統工程/Family/W5/tests/fixtures/work9_mentor_request.json').read_text())
        native=load_c_module(ROOT,9);result=native.build_unified_deployment(req)
        ctx={'client_id':'SYNTHETIC','run_id':result['run_id'],'owner':deepcopy(result['owner']),
            'currency':result['currency'],'runtime_mode':'REAL_DETERMINISTIC','data_provenance':'SYNTHETIC',
            'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','expected_result_digest':native._digest(result)}
        before=deepcopy((req,result,ctx));out=explain_native(ROOT,req,result,trusted_context=ctx)
        for item,original in zip(out['items'],result['canonical_deployment_result']['items']):
            self.assertEqual(item['recommendation']['amount'],original['deployment_amount'])
            self.assertEqual(item['recommendation']['ratio'],original['deployment_ratio'])
            self.assertFalse(item['recommendation']['broker_submission_allowed'])
        self.assertIn('70.00 USD',out['items'][1]['recommendation_explanation'])
        self.assertNotIn("{'value':",out['items'][0]['recommendation_explanation'])
        self.assertTrue(out['execution_advice_allowed']);self.assertTrue(out['recommendations_allowed'])
        self.assertFalse(out['broker_execution_allowed']);self.assertEqual(out['trade_action'],'NO_TRADE')
        self.assertEqual((req,result,ctx),before)
        with self.assertRaisesRegex(MentorError,'MODEL_FINANCIAL_MUTATION_REJECTED'):
            explain_native(ROOT,req,result,trusted_context=ctx,llm_suggested_changes=[{'amount':'999'}])

if __name__=='__main__':unittest.main()
