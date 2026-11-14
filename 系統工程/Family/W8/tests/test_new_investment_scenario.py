"""No external contribution is distinct from cash and absent accounts."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'系統工程/Family/W5'),str(ROOT/'系統工程/Family/W8'),
    str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src')]
from family_input import digest
from new_investment_scenario import build_plan,apply_plan
from livingwater_v82_runtime import funding_absence as A,validate_and_bind_funding
from runtime_loader import load_c_module


class NewInvestmentTest(unittest.TestCase):
    def setUp(self):
        self.owner={'client_id':'SYNTHETIC','account':'SYNTHETIC_ACCOUNT','currency':'USD'}
        self.snapshot={'client_id':'SYNTHETIC','source_sha256':'a'*64,'tables':{'funding_source':[],
            'currency_registry':[{'currency_code':'USD','minor_digits':2}]}}
        self.policy={'schema_version':'Family.W8.NewInvestmentTrialPolicy.v1','client_id':'SYNTHETIC',
            'new_external_money':'0','source_reference':'SYNTHETIC_OWNER_NO_EXTERNAL_MONEY'}
        self.contexts=[{'domain':'US_BROKER','account':'SYNTHETIC_ACCOUNT','broker':'SYNTHETIC_IB',
            'bucket_new_investment_amount':None,'brokerage_cash_state':{'total':145.67,'available':95,'unsettled':0,'reserved':0},
            'executable_budget':{'equity':{'amount':None},'bond':{'amount':None}}}]
    def test_zero_contribution_does_not_zero_existing_positive_cash(self):
        before=deepcopy((self.snapshot,self.contexts));plan=build_plan(self.snapshot,self.owner,self.policy)
        result=apply_plan(self.contexts,plan)
        self.assertEqual(plan['total_new_investment_amount'],'0');self.assertTrue(plan['assumed_zero'])
        self.assertEqual(result[0]['bucket_new_investment_amount'],0)
        self.assertIsInstance(result[0]['bucket_new_investment_amount'],int)
        self.assertEqual(result[0]['brokerage_cash_state'],self.contexts[0]['brokerage_cash_state'])
        self.assertEqual((self.snapshot,self.contexts),before)
    def test_existing_confirmed_contribution_takes_priority_over_zero_trial(self):
        self.snapshot['tables']['funding_source']=[{'client_id':'SYNTHETIC','source_id':'SYNTHETIC_DEPOSIT',
            'source_kind':'CASH_DEPOSIT','source_state':'CONFIRMED_IN_ACCOUNT','evidence_state':'VERIFIED','currency_code':'USD',
            'amount_minor':12345,'account_key':'SYNTHETIC_ACCOUNT'}]
        plan=build_plan(self.snapshot,self.owner,self.policy);result=apply_plan(self.contexts,plan)
        self.assertEqual(plan['total_new_investment_amount'],'123.45');self.assertFalse(plan['assumed_zero'])
        self.assertEqual(result[0]['bucket_new_investment_amount'],123.45)
        self.assertIsNone(result[0]['executable_budget']['equity']['amount'])
    def test_existing_context_amount_is_not_overwritten(self):
        self.contexts[0]['bucket_new_investment_amount']=20
        self.assertEqual(apply_plan(self.contexts,build_plan(self.snapshot,self.owner,self.policy))[0]['bucket_new_investment_amount'],20)
    def test_missing_policy_is_unknown_and_cross_owner_policy_is_rejected(self):
        self.assertIsNone(build_plan(self.snapshot,self.owner)['total_new_investment_amount'])
        self.policy['client_id']='OTHER'
        with self.assertRaisesRegex(ValueError,'EXPLICIT_NO_EXTERNAL_MONEY_POLICY_REQUIRED'):
            build_plan(self.snapshot,self.owner,self.policy)
    def test_confirmed_foreign_amount_is_retained_without_fx_or_zero_override(self):
        self.snapshot['tables']['funding_source']=[{'client_id':'SYNTHETIC','source_id':'FX',
            'source_kind':'CASH_DEPOSIT','source_state':'CONFIRMED_IN_ACCOUNT','evidence_state':'VERIFIED','currency_code':'TWD',
            'amount_minor':5000,'account_key':'OTHER_ACCOUNT'}]
        result=build_plan(self.snapshot,self.owner,self.policy)
        self.assertIsNone(result['total_new_investment_amount']);self.assertFalse(result['assumed_zero'])
        self.assertEqual(result['confirmed_source_rows'][0]['amount_minor'],5000)


class AbsentContextTest(unittest.TestCase):
    def request(self):
        req=json.loads((ROOT/'系統工程/Family/W5/tests/fixtures/work4_adapter_request.json').read_text())
        ctx=next(c for c in req['c7_funding_context']['contexts'] if c['domain']=='TW_SUB_BROKERAGE')
        ctx.update(account_presence=A.PRESENCE,account_presence_source='SYNTHETIC_OWNER_ABSENCE',
            broker=None,account=None,bucket_new_investment_amount=0,
            brokerage_cash_state={k:0 for k in ('total','available','unsettled','reserved')})
        ctx['source_reference_ids'].append('SYNTHETIC_OWNER_ABSENCE')
        for leg in ctx['executable_budget'].values():leg.update(amount=0,source_broker=None,source_account=None)
        req['c7_funding_context']['contract_version']=A.VERSION
        req['c7_funding_context']['total_new_investment_amount']=1100
        return req,ctx
    def test_original_work4_and_v82_bind_present_account_without_fictitious_account(self):
        req,ctx=self.request();before=deepcopy(req)
        built=load_c_module(ROOT,4).build_v82_runtime_input(req)
        bound=validate_and_bind_funding(built['v82_runtime_input'])
        self.assertEqual(str(bound.bound_equity_budget.amount),'450.0')
        self.assertEqual(bound.c7_contract_version,A.VERSION);self.assertIsNone(ctx['account'])
        self.assertEqual(req,before)
    def test_absence_cannot_fund_or_hide_identity_or_missing_proof(self):
        for mutation in ('budget','cash','account','source','old_version'):
            req,ctx=self.request()
            if mutation=='budget':ctx['executable_budget']['equity']['amount']=1
            if mutation=='cash':ctx['brokerage_cash_state']['total']=1
            if mutation=='account':ctx['account']='FAKE_ACCOUNT'
            if mutation=='source':ctx['account_presence_source']=''
            if mutation=='old_version':req['c7_funding_context']['contract_version']='C-W7-FUND-v1.0.0'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                load_c_module(ROOT,4).build_v82_runtime_input(req)
    def test_missing_identity_without_owner_absence_remains_invalid(self):
        req,ctx=self.request();ctx.pop('account_presence');ctx.pop('account_presence_source')
        with self.assertRaises(ValueError):load_c_module(ROOT,4).build_v82_runtime_input(req)
    def test_present_account_original_funding_is_unchanged(self):
        req=json.loads((ROOT/'系統工程/Family/W5/tests/fixtures/work4_adapter_request.json').read_text())
        built=load_c_module(ROOT,4).build_v82_runtime_input(req)
        self.assertEqual(str(validate_and_bind_funding(built['v82_runtime_input']).bound_equity_budget.amount),'450.0')

if __name__=='__main__':unittest.main()
