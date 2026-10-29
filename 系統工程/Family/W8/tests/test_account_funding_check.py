"""Actual original Work6 plus incomplete/overspent multi-claim coverage."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
import test_holdings_analysis as holding_tests
import test_native_bond_source as bond_tests
from native_funding_advice import build_shared_inputs, build as build_stock
from native_bond_source import build as build_bond
import account_funding_check as A


class AccountFundingCheckTest(unittest.TestCase):
    def case(self):
        p, req, report, _, strategy = bond_tests.NativeBondSourceTest().case()
        _, _, stock_report, trial, investment, tactical = holding_tests.NativeFundingAdviceTest().case()
        report['analysis_result']['positions'].append(deepcopy(stock_report['analysis_result']['positions'][0]))
        req['confirmed_target']['payload']['draft']['target_lines'].append({
            'instrument_id': 'QQQ', 'ticker': 'QQQ',
            'target_amount': {'value_state': 'KNOWN', 'amount': '1000', 'currency': 'USD'}})
        report.update(client_id=req['client_id'], run_id=req['run_id'], owner=deepcopy(req['owner']),
            source_db_sha256=req['client_snapshot']['payload']['source_sha256'],
            cash_trial=trial, order_source={'status': 'UNKNOWN'})
        shared = build_shared_inputs(p, req, report, trial=trial, investment=investment, tactical=tactical)
        report['native_funding_advice'] = build_stock(p, req, report,
            trial=trial, investment=investment, tactical=tactical, shared_inputs=shared)
        report['native_bond_source'] = build_bond(p.root, req, report,
            shared_inputs=shared, fx_observation=None, strategic_policy=strategy)
        return p, req, report

    def test_original_work6_runs_without_treating_unknown_bond_amount_as_zero(self):
        p, req, report = self.case()
        out = A.build(p.root, req, report)
        self.assertEqual(out['status'], 'NATIVE_ACCOUNT_FUNDING_CHECKED_WITH_GAPS', out['issues'])
        check = out['adapter_checks']['SYNTHETIC_QQQ']
        self.assertEqual(check['status'], 'PASSED')
        self.assertEqual(check['native_work6']['cash_eligibility']['total'], '500')
        self.assertEqual(check['native_work6']['cash_eligibility']['available'], '0')
        self.assertEqual(out['known_claims_budget_check']['status'], 'PASSED')
        self.assertEqual(out['coverage']['native_amounts_counted'], 1)
        self.assertEqual(out['coverage']['unresolved_native_decisions'], 1)
        self.assertIsNone(out['unresolved_decisions'][0]['amount'])
        self.assertFalse(out['unresolved_decisions'][0]['missing_amount_replaced_by_zero'])
        self.assertFalse(out['full_native_canonical_complete'])
        self.assertNotEqual(out['conservation_status'], 'CONSERVATION_CHECK_PASSED')

    def test_orders_and_physical_sgov_do_not_become_available_cash(self):
        p, req, report = self.case()
        report['native_bond_source']['physical_holdings']['SGOV']['valuation']['amount'] = '90000'
        out = A.build(p.root, req, report)
        self.assertFalse(out['physical_sgov_included_in_available_cash'])
        self.assertEqual(out['order_source']['status'], 'UNKNOWN')
        self.assertEqual(out['known_claims_budget_check']['result']['available_remaining'], '0')
        self.assertFalse(out['joint_execution_authorized'])

    def test_overspending_claim_is_rejected_instead_of_scaled_or_zeroed(self):
        p, req, report = self.case()
        report['native_funding_advice']['items']['SYNTHETIC_QQQ']['native_plan']['execution_amount'] = '1'
        out = A.build(p.root, req, report)
        self.assertEqual(out['status'], 'BUDGET_REJECTED')
        self.assertEqual(out['known_claims_budget_check']['reason'], 'AGGREGATE_BUDGET_EXCEEDED')
        self.assertEqual(out['claims'][0]['amount'], '1')

    def test_wrong_member_and_incomplete_coverage_are_not_aggregated(self):
        p, req, report = self.case()
        wrong = deepcopy(report)
        wrong['native_funding_advice']['items']['SYNTHETIC_QQQ']['owner']['account'] = 'OTHER'
        with self.assertRaisesRegex(PermissionError, 'COMPONENT_IDENTITY'):
            A.build(p.root, req, wrong)
        wrong = deepcopy(report)
        wrong['native_funding_advice']['items'].pop('SYNTHETIC_QQQ')
        with self.assertRaisesRegex(PermissionError, 'COVERAGE'):
            A.build(p.root, req, wrong)

    def test_serialized_adapter_tampering_fails_original_replay(self):
        p, req, report = self.case()
        item = report['native_funding_advice']['items']['SYNTHETIC_QQQ']
        item['work4_result']['v82_runtime_input']['execution_account']['account'] = 'OTHER'
        with self.assertRaisesRegex(PermissionError, 'WORK4_REPLAY'):
            A.build(p.root, req, report)

    def test_distinct_registry_keys_do_not_duplicate_the_same_native_asset(self):
        p, req, report = self.case()
        row = deepcopy(report['analysis_result']['positions'][1])
        row['instrument_id'] = 'DUPLICATE_QQQ'
        report['analysis_result']['positions'].append(row)
        report['native_funding_advice']['items']['DUPLICATE_QQQ'] = deepcopy(
            report['native_funding_advice']['items']['SYNTHETIC_QQQ'])
        with self.assertRaisesRegex(PermissionError, 'DUPLICATE_NATIVE_ASSET'):
            A.build(p.root, req, report)

    def test_missing_stock_stage_stays_unresolved_after_account_check(self):
        p, req, report = self.case()
        item = report['native_funding_advice']['items']['SYNTHETIC_QQQ']
        item['status'] = 'FUNDING_BOUND'
        item.pop('native_plan')
        out = A.build(p.root, req, report)
        self.assertEqual(out['coverage']['stock_adapters_checked'], 1)
        self.assertEqual(out['coverage']['native_amounts_counted'], 0)
        self.assertEqual(out['coverage']['unresolved_native_decisions'], 2)

    def test_report_resigning_does_not_replace_native_aggregate_replay(self):
        p, req, report = self.case()
        report['account_funding_check'] = A.build(p.root, req, report)
        A.validate(p.root, req, report)
        report['account_funding_check']['known_claims_budget_check']['result']['equity_used'] = '2'
        with self.assertRaisesRegex(PermissionError, 'CHECK_REPLAY'):
            A.validate(p.root, req, report)


if __name__ == '__main__':
    unittest.main()
