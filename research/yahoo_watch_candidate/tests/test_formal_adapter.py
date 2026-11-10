import unittest
from formal_adapter import digest,project
class Tests(unittest.TestCase):
    def setUp(self):
        self.a={'left_inputs':{'price_condition_at_least_one':'TRUE'},'identity':{'client_id':'SYNTHETIC_PRIVATE'}}
        self.t={'native_technical_aggregation':{'runaway_down':'FALSE'}}
        self.r=dict(source_qualification='VERIFIED_FORMAL_DAILY',analysis_sha256=digest(self.a),technical_sha256=digest(self.t),rule_sha256='r',snapshot_id='s',producer_id='p',as_of=1,valid_until=2)
    def test_only_expected_private_free_projection(self):
        p=project(self.a,self.t,receipt=self.r)
        self.assertTrue(p['L_price']);self.assertFalse(p['RunawayDown']);self.assertNotIn('identity',p)
    def test_bad_hash(self):
        with self.assertRaises(ValueError):project(self.a,{},receipt=self.r)
    def test_unqualified(self):
        with self.assertRaises(ValueError):project(self.a,self.t,receipt={**self.r,'source_qualification':'YAHOO_5M'})
    def test_unknown_not_false(self):
        self.a['left_inputs']['price_condition_at_least_one']='UNKNOWN';self.r['analysis_sha256']=digest(self.a)
        self.assertIsNone(project(self.a,self.t,receipt=self.r)['L_price'])
