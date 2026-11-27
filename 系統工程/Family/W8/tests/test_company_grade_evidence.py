"""A deployment classification must not manufacture permission or targets."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
from company_grade_evidence import RULE, classify


class CompanyGradeEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((HERE / 'company_grade_evidence.json').read_text())

    def test_reviewable_annual_evidence_keeps_current_safety_and_targets_separate(self):
        for symbol in self.catalog['items']:
            result = classify(symbol, self.catalog, RULE)
            self.assertIn(result['asset_grade'], ('B', 'D'))
            evidence = result['grade_evidence']
            self.assertFalse(evidence['assessment_is_owner_approval'])
            self.assertFalse(evidence['assessment_is_current_safety_clearance'])
            self.assertTrue(evidence['no_fixed_position_limit_or_target_inferred'])
            self.assertNotIn('hard_gate', result)
            self.assertNotIn('target_amount', result)
        # Financial-service revenue must include net interest, not just
        # the narrower contracts-with-customers/commission component.
        self.assertEqual(self.catalog['items']['IBKR']['financial_evidence']['revenue']['tag'],
                         'RevenuesNetOfInterestExpense')

    def test_uncovered_symbol_or_missing_formal_grade_dictionary_stays_unclassified(self):
        self.assertIsNone(classify('NOT_COVERED', self.catalog, RULE))
        self.assertIsNone(classify('MSFT', self.catalog, 'identity only'))

    def test_wrong_filing_and_incomparable_period_cannot_support_a_grade(self):
        wrong = deepcopy(self.catalog)
        wrong['items']['MSFT']['filing']['cik'] = 1045810
        with self.assertRaisesRegex(ValueError, 'SEC_FILING_IDENTITY'):
            classify('MSFT', wrong, RULE)
        wrong = deepcopy(self.catalog)
        wrong['items']['MSFT']['financial_evidence']['net_income']['periods'][0]['start'] = '2024-01-01'
        with self.assertRaisesRegex(ValueError, 'COMPARABLE_FINANCIAL'):
            classify('MSFT', wrong, RULE)

    def test_grade_cannot_be_resigned_into_owner_approval_or_safety_clearance(self):
        for field in ('assessment_is_owner_approval', 'assessment_is_current_safety_clearance'):
            wrong = deepcopy(self.catalog)
            wrong['items']['NVDA'][field] = True
            with self.assertRaisesRegex(ValueError, 'STRUCTURAL_EVIDENCE'):
                classify('NVDA', wrong, RULE)

    def test_assessed_risk_class_requires_its_own_evidence_basis(self):
        wrong = deepcopy(self.catalog)
        wrong['items']['AVGO']['asset_grade'] = 'B'
        with self.assertRaisesRegex(ValueError, 'ASSESSMENT_BASIS'):
            classify('AVGO', wrong, RULE)


if __name__ == '__main__':
    unittest.main()
