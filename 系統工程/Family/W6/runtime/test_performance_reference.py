import unittest
from performance_reference import weighted_reference
class ReferenceTests(unittest.TestCase):
 def metric(self,r):return dict(annualized_return=r,currency='USD',period_start='2020-01-01',period_end='2025-01-01',as_of='2025-01-01',return_basis='TOTAL_RETURN_PRETAX')
 def test_complete(self):
  x=weighted_reference([dict(instrument_id='A',weight=.4),dict(instrument_id='B',weight=.6)],{'A':self.metric(.1),'B':self.metric(.05)});self.assertAlmostEqual(x['a_ref'],.07);self.assertIsNone(x['score_0_100'])
 def test_missing_never_renormalized(self):
  x=weighted_reference([dict(instrument_id='A',weight=.4),dict(instrument_id='B',weight=.6)],{'A':self.metric(.1)});self.assertEqual(x['coverage'],.4);self.assertAlmostEqual(x['known_contribution'],.04);self.assertIsNone(x['a_ref'])
 def test_different_period(self):
  a=self.metric(.1);b=self.metric(.05);b['period_end']='2024-01-01';x=weighted_reference([dict(instrument_id='A',weight=.4),dict(instrument_id='B',weight=.6)],{'A':a,'B':b});self.assertIsNone(x['a_ref'])
 def test_unknown_basis(self):
  a=self.metric(.1);a['return_basis']='UNKNOWN';self.assertIsNone(weighted_reference([dict(instrument_id='A',weight=1)],{'A':a})['a_ref'])
 def test_duplicates(self):
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):weighted_reference([dict(instrument_id='A',weight=.5)]*2,{})
 def test_weights(self):
  with self.assertRaisesRegex(ValueError,'WEIGHT_SUM'):weighted_reference([dict(instrument_id='A',weight=.7)],{})
if __name__=='__main__':unittest.main()
