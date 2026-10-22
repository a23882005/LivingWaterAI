"""W7-A09 shared explicit expected policy outcomes, not inferred from implementation."""
import unittest
from policy_case_matrix import cases
from test_v703_policy_evidence import b
class PolicyRateBoundaryTests(unittest.TestCase):
    def test_shared_contract_matrix(self):
        for name,row,now,expected in cases():
            with self.subTest(case=name):
                self.assertEqual(not b._validate('m06_rate',row,now.date(),{},now),expected)
                print('POLICY_CASE',name,'PASS',flush=True)
if __name__=='__main__':unittest.main()
