from copy import deepcopy
from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from recommendation_report import build

class ReportTest(unittest.TestCase):
    def case(self):
        c={'recommendation':{'confirmed_holdings_component':{'positive_gap_amount':'123.45'},'position_currency':'USD',
             'new_external_funding_buy_amount':'0','buy_gap_amount':None,'missing_fields':['active_orders_and_fill_reconciliation']},
           'current_judgment':{'mode':'Right Confirmation','target_rate_reference':'0.95','target_amount_reference':'950','currency':'USD'},
           'technical':{'native_result':{'right_confirmation':'TRUE','runaway_up':'FALSE','runaway_down':'FALSE'}},
           'valuation':{'native_result':{'level':'NORMAL'}},'market':{'observed_date':'2026-10-27'}}
        p={'instrument_id':'SYNTHETIC','symbol':'SYN','holding':{'quantity':'5'},'owner':{'currency':'USD'},'current_analysis':c}
        r={'status':'ANALYSIS_PARTIAL','analysis_result':{'positions':[p]},'mentor':{'items':[{'item_id':'SYNTHETIC',
            'recommendation':{'recommended_sell_amount':{'status':'UNKNOWN','amount':None}},'explanation':'SYNTHETIC_NATIVE_EXPLANATION'}]}}
        req={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN','confirmed_target':{'payload':{'draft':{'target_lines':[
            {'ticker':'SYN','weight':{'value_state':'KNOWN','value':'0.2'}}]}}}}
        return r,req
    def test_gap_and_new_money_are_separate_and_orders_do_not_block_report(self):
        r,q=self.case();before=deepcopy(r);out=build(r,q);row=out['rows'][0]
        self.assertEqual(row['holding_gap_amount'],'123.45');self.assertEqual(row['proposed_new_external_buy_amount'],'0')
        self.assertIsNone(row['proposed_existing_asset_redeployment_amount'])
        self.assertEqual(out['report_delivery_status'],'COMPLETE');self.assertEqual(out['analysis_status'],'ANALYSIS_PARTIAL')
        self.assertEqual(row['approved_allocation_weight'],q['confirmed_target']['payload']['draft']['target_lines'][0]['weight']['value']);self.assertEqual(row['stage_cumulative_rate'],'0.95')
        self.assertIn('尚未扣除本人既有未成交委託',out['markdown']);self.assertEqual(r,before)
    def test_unknown_money_is_not_rendered_as_zero(self):
        r,q=self.case();r['analysis_result']['positions'][0]['current_analysis']['recommendation'].update(confirmed_holdings_component=None,new_external_funding_buy_amount=None)
        out=build(r,q);self.assertIsNone(out['rows'][0]['holding_gap_amount']);self.assertIn('未定',out['html'])
    def test_missing_mentor_coverage_is_not_a_completed_report(self):
        r,q=self.case();r['mentor']['items']=[]
        with self.assertRaisesRegex(ValueError,'COVERAGE_MISMATCH'):build(r,q)

if __name__=='__main__':unittest.main()
