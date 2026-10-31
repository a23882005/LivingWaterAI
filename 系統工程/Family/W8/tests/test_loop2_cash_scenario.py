"""Loop2 spec T02/T03 and cash portions of T04/T05/T15; not full P3 UAT."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from loop2_cash_scenario import build_cash_overlay, validate_cash_overlay


class CashOverlayTest(unittest.TestCase):
    def setUp(self):
        self.snapshot={'client_id':'SYNTHETIC_MEMBER','source_sha256':'a'*64,
            'holdings':[{'quantity':'1.2345'}],'physical_sgov':None}
        self.owner={'client_id':'SYNTHETIC_MEMBER','account':'SYNTHETIC_ACCOUNT','currency':'USD'}
        self.authorization={'schema_version':'Family.W8.CashTrialPolicy.v1',
            'missing_cash_value':'0','source_reference':'SYNTHETIC_AUTHORIZATION'}
        self.kw={'snapshot':self.snapshot,'owner':self.owner,
            'authorization':self.authorization,'run_id':'SYNTHETIC_RUN'}
        self.raw={'total':'100.0000','available':None,'unsettled':None,'reserved':'0.0000'}

    def test_T02_preserves_known_precision_raw_source_and_cash_whitelist(self):
        before=deepcopy(self.snapshot);raw=deepcopy(self.raw)
        scenario=build_cash_overlay(self.raw,**self.kw)
        effective=validate_cash_overlay(self.raw,scenario,**self.kw)['effective_cash']
        self.assertEqual(effective,{'total':'100.0000','available':'0','unsettled':'0','reserved':'0.0000'})
        self.assertEqual({a['field_path'] for a in scenario['assumptions']},
            {'cash_state.available','cash_state.unsettled'})
        self.assertTrue(all(a['scope']=='SIMULATION_ONLY' and a['run_id']=='SYNTHETIC_RUN'
            for a in scenario['assumptions']))
        self.assertEqual(self.snapshot,before);self.assertEqual(self.raw,raw)
        with self.assertRaisesRegex(ValueError,'SCOPE'):
            build_cash_overlay({**self.raw,'physical_sgov':None},**self.kw)

    def test_T03_missing_total_retains_known_positive_available_and_blocks(self):
        self.raw.update(total=None,available='5.1234')
        scenario=build_cash_overlay(self.raw,**self.kw)
        self.assertEqual(scenario['effective_cash']['available'],'5.1234')
        self.assertEqual(scenario['issues'][0]['code'],'CASH_ASSUMPTION_CONFLICT')
        self.assertIsNone(validate_cash_overlay(self.raw,scenario,**self.kw)['effective_cash'])

    def test_T03_invalid_cash_is_not_replaced_with_zero(self):
        for invalid in ('oops','-1','NaN','Infinity',True,0.1):
            with self.subTest(value=invalid):
                self.raw['available']=invalid
                scenario=build_cash_overlay(self.raw,**self.kw)
                self.assertEqual(scenario['issues'][0]['code'],'INVALID_CASH_VALUE')
                self.assertNotIn('available',scenario['effective_cash'])

    def test_T05_cross_member_run_currency_snapshot_and_overlay_tampering_rejected(self):
        scenario=build_cash_overlay(self.raw,**self.kw)
        for key,replacement in [('run_id','OTHER'),('owner',{**self.owner,'currency':'TWD'}),
                ('snapshot',{**self.snapshot,'holdings':[]} )]:
            with self.subTest(key=key),self.assertRaises(PermissionError):
                validate_cash_overlay(self.raw,scenario,**{**self.kw,key:replacement})
        scenario['effective_cash']['available']='1'
        with self.assertRaises(PermissionError):validate_cash_overlay(self.raw,scenario,**self.kw)
        with self.assertRaises(ValueError):
            build_cash_overlay(self.raw,**{**self.kw,'owner':{**self.owner,'client_id':'OTHER'}})

    def test_T15_fixed_input_replay_has_same_digest_and_no_trade(self):
        a=build_cash_overlay(self.raw,**self.kw);b=build_cash_overlay(self.raw,**self.kw)
        self.assertEqual(a,b);self.assertTrue(a['no_trade'])
        self.assertEqual(a['mode'],'CASH_ZERO_SIMULATION')
        self.assertNotIn('data_provenance',a)


if __name__=='__main__':unittest.main()
