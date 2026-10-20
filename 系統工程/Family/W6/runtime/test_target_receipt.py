import unittest
from copy import deepcopy
from datetime import datetime,timezone
from target_receipt import receive_target
from report_receiver import ReportError

class TargetReceiptTests(unittest.TestCase):
    def setUp(self):
        self.args=dict(client_id='test',report_run_id='report',evaluation_at=datetime(2026,1,1,tzinfo=timezone.utc),source_id='test-source',rules_sha='test-rules',validator=lambda target,client,at:deepcopy(target))
    def test_preserves_original_target(self):
        target={'confirmation_run_id':'original','target_version':3,'payload':{'value':0}}
        out=receive_target(target,**self.args)
        self.assertEqual(out['payload'],target)
        out['payload']['payload']['value']=99
        self.assertEqual(target['payload']['value'],0)
    def test_unknown(self):
        self.assertIsNone(receive_target(None,**self.args)['payload'])
    def test_validator_mutation_rejected(self):
        with self.assertRaises(ReportError):receive_target({'x':1},**(self.args|{'validator':lambda *args:{'x':2}}))
    def test_missing_lineage(self):
        for key in ['client_id','report_run_id','source_id','rules_sha']:
            with self.subTest(key=key),self.assertRaises(ReportError):receive_target({},**(self.args|{key:''}))

if __name__=='__main__':unittest.main()
