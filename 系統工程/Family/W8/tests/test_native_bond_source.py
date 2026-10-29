"""Actual original V75 checks, with unknown roles and source quality intact."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import test_holdings_analysis as holding_tests
from native_funding_advice import build_shared_inputs
import native_bond_source as B


class NativeBondSourceTest(unittest.TestCase):
    def case(self):
        p,req,report,trial,investment,tactical=holding_tests.NativeFundingAdviceTest().case()
        req['owner']['funding_domain']='INVESTMENT'  # Family purpose is not the native broker domain.
        req['client_snapshot']['payload']['tables']={'sgov_role_proposal':[],'sgov_role_confirmation':[]}
        row=report['analysis_result']['positions'][0]
        row.update(symbol='SGOV',instrument_id='SYNTHETIC_SGOV',
            native_product_identity={'engine_route':'V75_PREDICATES','asset_type':None,'asset_grade':'UNKNOWN'})
        row['market'].update(symbol='SGOV',provider_verified_at='2026-10-27T22:00:00Z',source_sha256='b'*64,
            observed_date='2026-10-26',v75_original_predicates={})
        row['current_analysis']['recommendation']['position_currency']=req['owner']['currency']
        lines=req['confirmed_target']['payload']['draft']['target_lines']
        lines[:]=[{'instrument_id':'SGOV_BOND','ticker':'SGOV','target_amount':
            {'value_state':'KNOWN','amount':'700','currency':'USD'}},
            {'instrument_id':'SGOV_DRY','ticker':'SGOV','target_amount':
            {'value_state':'KNOWN','amount':'300','currency':'USD'}}]
        shared=build_shared_inputs(p,req,report,trial=trial,investment=investment,tactical=tactical)
        strategy={'client_id':req['client_id'],'bond_percent':20,'life_stage_code':'L7',
            'source_reference':'SYNTHETIC_EXISTING_STRATEGIC_SOURCE'}
        return p,req,report,shared,strategy

    def build(self,p,req,report,shared,strategy):
        return B.build(p.root,req,report,shared_inputs=shared,fx_observation=None,strategic_policy=strategy)

    def test_real_work5_keeps_unknown_freshness_and_separate_sgov_roles(self):
        p,req,report,shared,strategy=self.case();before=deepcopy((req,report,shared))
        out=self.build(p,req,report,shared,strategy)
        self.assertEqual(out['status'],'ORIGINAL_V75_SOURCE_CHECKED_WITH_GAPS',out['issues'])
        self.assertIn('C8C9.Work5.build_v75_runtime_input',out['call_trace'])
        self.assertEqual(out['targets']['SGOV']['money']['amount'],'700')
        native=out['adapter_result']['v75_runtime_input']
        self.assertEqual(native['existing_bond_holdings'][0]['amount']['amount'],'500')
        self.assertEqual(native['sgov_bond_bucket_amount'],{'status':'UNKNOWN','value':None})
        self.assertEqual(native['sgov_dry_powder_bucket_amount'],{'status':'UNKNOWN','value':None})
        self.assertEqual(native['funding_settlement_status'],'UNKNOWN')
        self.assertEqual(native['market_snapshot']['freshness_state'],'UNKNOWN')
        self.assertFalse(out['native_validation']['accepted'])
        self.assertIsNone(out['canonical_result'])
        self.assertTrue(any(i['code']=='SGOV_BOND_ROLE_UNKNOWN_WITH_EXISTING_HOLDING' for i in out['issues']))
        self.assertEqual(out['trade_action'],'NO_TRADE')
        self.assertEqual((req,report,shared),before)

    def test_target_ambiguity_does_not_drop_one_role_or_insert_zero(self):
        p,req,report,shared,strategy=self.case()
        req['confirmed_target']['payload']['draft']['target_lines'][0]['instrument_id']='UNIDENTIFIED_ROLE'
        out=self.build(p,req,report,shared,strategy)
        self.assertEqual(out['status'],'SOURCE_INCOMPLETE')
        self.assertNotIn('adapter_request',out)
        self.assertTrue(any(i['field_path']=='target_bond_holdings.SGOV' for i in out['issues']))
        self.assertEqual(out['targets'],{})

    def test_approved_unheld_spsb_target_is_not_omitted_from_native_bucket(self):
        p,req,report,shared,strategy=self.case()
        req['confirmed_target']['payload']['draft']['target_lines'].append({
            'instrument_id':'SPSB','ticker':'SPSB','target_amount':
                {'value_state':'KNOWN','amount':'300','currency':'USD'}})
        out=self.build(p,req,report,shared,strategy)
        native=out['adapter_result']['v75_runtime_input']
        self.assertEqual({r['asset_id'] for r in native['target_bond_holdings']},{'SGOV','SPSB'})
        self.assertEqual({r['asset_id'] for r in native['existing_bond_holdings']},{'SGOV'})
        self.assertEqual(set(native['authorized_universe']),{'SGOV','SPSB'})
        self.assertFalse(any(i['code']=='US_GENERIC_CORE_TARGET_RATIO_MISMATCH' for i in out['issues']))
        self.assertTrue(any(i['field_path']=='bond_evidence.SPSB.market' for i in out['issues']))

    def test_replay_rejects_resigned_native_result_and_delivery(self):
        p,req,report,shared,strategy=self.case()
        out=self.build(p,req,report,shared,strategy)
        report['native_bond_source']=out
        row=report['analysis_result']['positions'][0]
        row['current_analysis']['native_bond_source']=B.delivery(out)
        B.validate(p.root,req,report)
        out['native_validation']['accepted']=True
        row['current_analysis']['native_bond_source']=B.delivery(out)
        with self.assertRaisesRegex(PermissionError,'REPLAY_MISMATCH'):B.validate(p.root,req,report)

    def test_other_member_or_mutated_market_cannot_reuse_shared_envelope(self):
        p,req,report,shared,strategy=self.case()
        shared['work3_input']['client_state_context']['payload']['client_id']='another-member'
        with self.assertRaisesRegex(PermissionError,'SHARED_BINDING'):self.build(p,req,report,shared,strategy)
        p,req,report,shared,strategy=self.case()
        report['analysis_result']['positions'][0]['market']['observed_close']='999'
        with self.assertRaisesRegex(PermissionError,'MARKET_BINDING'):self.build(p,req,report,shared,strategy)


if __name__=='__main__':unittest.main()
