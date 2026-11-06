"""Approved ETF structural leaves: source validity, owner limits and intervals."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from etf_structure_source import evaluate_etf_structure as evaluate,lookthrough_intervals,mandate_subset

class ETFStructureTest(unittest.TestCase):
    def fixture(self):
        req={'client_id':'SYNTHETIC_MEMBER','evaluation_at':'2026-10-28T01:00:00Z',
            'confirmed_target':{'payload':{'draft':{'etf_constraints':{'VT':{
                'client_id':'SYNTHETIC_MEMBER','symbol':'VT','allowed_mandate_components':['GLOBAL_EQUITY'],
                'exposure_limits':[{'risk_domain':'DISALLOWED','allowed_exposure':'0.10','authority_reference':'SYNTHETIC_OWNER_RULE'}]}}}}}}
        common={'as_of':'2026-10-27T20:00:00Z','available_at':'2026-10-27T20:15:00Z',
            'valid_until':'2026-10-28T20:00:00Z','data_quality':'OK'}
        facts={'symbol':'VT','source_sha256':'a'*64,'source_url':'https://fund-docs.vanguard.com/synthetic.json',
            'fund_status':{**common,'operating_status':'OPERATING'},
            'mandate':{**common,'components':['GLOBAL_EQUITY'],'method_version':'SYNTHETIC-v1'},
            'nav_redemption_status':{**common,'nav_reporting_valid':True,'creation_redemption_function_valid':True},
            'termination_event':{**common,'confirmed_termination':False,'permanent_disqualification':False,
                'required_domains':['FUND_TERMINATION','PERMANENT_OPERATIONAL_DISQUALIFICATION'],
                'checked_domains':['FUND_TERMINATION','PERMANENT_OPERATIONAL_DISQUALIFICATION'],
                'checkpoint_id':'SYNTHETIC_CHECKPOINT','coverage_complete':True},
            'lookthrough':{**common,'universe_complete':True,'weight_unit':'fraction','total_weight':'1',
                'components':[{'component_id':'A','weight':'0.05','risk_status':{'DISALLOWED':True}},
                              {'component_id':'B','weight':'0.95','risk_status':{'DISALLOWED':False}}]}}
        return facts,req
    def test_complete_bound_facts_compute_viable_and_leave_inputs_unchanged(self):
        facts,req=self.fixture();before=deepcopy((facts,req));out=evaluate(facts,req,'VT')
        self.assertEqual(out['result'],'TRUE');self.assertEqual(out['source_ready_count'],5)
        self.assertEqual((facts,req),before)
    def test_absent_sources_and_owner_limits_remain_exact_gaps(self):
        _,req=self.fixture();req['confirmed_target']['payload']['draft']['etf_constraints']={}
        out=evaluate(None,req,'VT');self.assertEqual(out['result'],'UNKNOWN')
        self.assertIn('approved_target.etf_constraints.VT.allowed_mandate_components',
            out['leaves']['current_mandate_within_client_approved_mandate']['missing_fields'])
        self.assertEqual(out['source_ready_count'],0)
    def test_registration_is_not_an_operating_status(self):
        facts,req=self.fixture();facts['fund_status']['operating_status']='REGISTERED'
        self.assertEqual(evaluate(facts,req,'VT')['leaves']['fund_legally_operating']['truth'],'UNKNOWN')
    def test_missing_current_status_does_not_erase_independent_nav_result(self):
        facts,req=self.fixture();del facts['fund_status'];out=evaluate(facts,req,'VT')
        self.assertEqual(out['result'],'UNKNOWN');self.assertEqual(out['source_ready_count'],4)
        self.assertEqual(out['leaves']['nav_reporting_and_creation_redemption_function_valid']['truth'],'TRUE')
    def test_actual_structural_failure_short_circuits_other_unknowns(self):
        facts,req=self.fixture();facts['fund_status']['operating_status']='CEASED';del facts['lookthrough']
        self.assertEqual(evaluate(facts,req,'VT')['result'],'FALSE')
    def test_unverified_event_absence_and_irrelevant_coverage_are_not_clearance(self):
        facts,req=self.fixture();e=facts['termination_event'];e['coverage_complete']=False
        self.assertEqual(evaluate(facts,req,'VT')['leaves']['termination_or_disqualification_absent']['truth'],'UNKNOWN')
        e.update(coverage_complete=True,required_domains=['IRRELEVANT'],checked_domains=['IRRELEVANT'])
        self.assertEqual(evaluate(facts,req,'VT')['leaves']['termination_or_disqualification_absent']['truth'],'UNKNOWN')
        e['confirmed_termination']=True
        self.assertEqual(evaluate(facts,req,'VT')['result'],'FALSE')
    def test_freshness_and_pit_are_independent_of_retrieval(self):
        for key,value in [('available_at','2026-10-28T02:00:00Z'),('valid_until','2026-10-28T00:00:00Z')]:
            facts,req=self.fixture();facts['fund_status'][key]=value
            self.assertEqual(evaluate(facts,req,'VT')['leaves']['fund_legally_operating']['truth'],'UNKNOWN')
    def test_event_lifecycle_validity_does_not_require_an_invented_expiry(self):
        facts,req=self.fixture();event=facts['termination_event'];del event['valid_until']
        event['source_validity']={'state':'VALID','basis':'ORIGINAL_EVENT_LIFECYCLE',
            'method_version':'SYNTHETIC_CMREVENT-v1','checked_at':'2026-10-28T00:59:00Z'}
        self.assertEqual(evaluate(facts,req,'VT')['leaves']['termination_or_disqualification_absent']['truth'],'TRUE')
        event['source_validity']['checked_at']='2026-10-28T02:00:00Z'
        self.assertEqual(evaluate(facts,req,'VT')['leaves']['termination_or_disqualification_absent']['truth'],'UNKNOWN')
    def test_bound_source_and_official_authority_are_required(self):
        facts,req=self.fixture();facts['source_url']='https://untrusted.example/value'
        self.assertEqual(evaluate(facts,req,'VT')['source_ready_count'],0)
        facts,req=self.fixture();del facts['source_sha256'];self.assertEqual(evaluate(facts,req,'VT')['source_ready_count'],0)
    def test_owner_and_symbol_are_never_borrowed(self):
        facts,req=self.fixture();req['confirmed_target']['payload']['draft']['etf_constraints']['VT']['client_id']='OTHER'
        with self.assertRaisesRegex(PermissionError,'OWNER_POLICY'):evaluate(facts,req,'VT')
        facts,req=self.fixture();facts['symbol']='OTHER'
        with self.assertRaisesRegex(ValueError,'SYMBOL'):evaluate(facts,req,'VT')
    def test_mandate_subset_is_computed_not_assumed_from_product_class(self):
        self.assertTrue(mandate_subset(['EQUITY'],['EQUITY','CASH']))
        self.assertFalse(mandate_subset(['LEVERAGED'],['EQUITY']))
        self.assertIsNone(mandate_subset(['EQUITY'],None))
    def test_unknown_weights_produce_an_interval_with_exact_cap_boundaries(self):
        facts,req=self.fixture();composition=facts['lookthrough'];limits=req['confirmed_target']['payload']['draft']['etf_constraints']['VT']['exposure_limits']
        composition['components'][1]['risk_status']={}
        out=lookthrough_intervals(composition,limits);self.assertEqual(out['truth'],'UNKNOWN')
        self.assertEqual((out['limits'][0]['lower'],out['limits'][0]['upper']),('0.05','1.00'))
        limits[0]['allowed_exposure']='1';self.assertEqual(lookthrough_intervals(composition,limits)['truth'],'TRUE')
        limits[0]['allowed_exposure']='0.049';self.assertEqual(lookthrough_intervals(composition,limits)['truth'],'FALSE')
    def test_incomplete_universe_is_not_renormalized(self):
        facts,req=self.fixture();limits=req['confirmed_target']['payload']['draft']['etf_constraints']['VT']['exposure_limits']
        facts['lookthrough']['components'].pop();out=lookthrough_intervals(facts['lookthrough'],limits)
        self.assertEqual(out['truth'],'UNKNOWN');self.assertIn('lookthrough.incomplete_weight_denominator',out['issues'])
    def test_empty_limits_are_not_explicitly_approved_none(self):
        facts,req=self.fixture();p=req['confirmed_target']['payload']['draft']['etf_constraints']['VT'];p['exposure_limits']=[]
        self.assertEqual(evaluate(facts,req,'VT')['result'],'UNKNOWN')
        p.update(lookthrough_restrictions='EXPLICIT_APPROVED_NONE',authority_reference='SYNTHETIC_APPROVED_NONE')
        del facts['lookthrough'];out=evaluate(facts,req,'VT')
        self.assertEqual(out['result'],'TRUE');self.assertEqual(out['leaves']['lookthrough_disposition_allows_long_term_holding']['applicability'],'NOT_APPLICABLE_EXPLICIT_APPROVED_NONE')

if __name__=='__main__':unittest.main()
