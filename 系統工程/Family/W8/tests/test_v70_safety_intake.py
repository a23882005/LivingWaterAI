"""Approved v2 evidence intake; all data in this module is synthetic.

The real private four-member replay and approved source bytes are delivered
separately. Upstream scores and observations never assert V82 safety facts.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json,sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
import member_v82_analysis as M
import test_member_v82_analysis as member_fixture
import test_v10_source_observations as macro_fixture


def fixture():
    signals={name:{'signal_name':name,'value':None,'unit':None,
        'level':None,'direction':None,'speed':None,'as_of':None,'published_at':None,
        'source':None,'data_quality':'UNKNOWN','issue_codes':['MISSING'],
        'issue_detail':'SYNTHETIC missing original source',
        'judgment_issue_codes':['METHODOLOGY_UNAVAILABLE']}
        for name in sorted(M.V70_SAFETY_SIGNAL_NAMES)}
    for name in ('fed_policy','real_yield','core_cpi','employment_unemployment_rate',
                 'employment_nonfarm_payrolls_3m_avg','hy_oas','vix','move'):
        signals[name].update(value=0,unit='SYNTHETIC_UNIT',as_of='2026-10-28',
            published_at='2026-10-28',source='https://synthetic.invalid/official',
            data_quality='FALLBACK_USED' if name=='core_cpi' else 'OK',issue_codes=[])
        signals[name].pop('issue_detail')
    return {'schema_version':'V70.3/family-macro-safety-v2',
        'snapshot_timestamp':'2026-10-29T22:00:00Z','data_cutoff':'2026-10-29T20:00:00Z',
        'v70_version':'SYNTHETIC_RULE_VERSION','health_score':100,'score_status':'FORMAL_VALID',
        'source_commit':'SYNTHETIC_SOURCE_COMMIT','feed_sha256':'a'*64,
        'upstream_snapshot_reference':{'daily_record_id':'SYNTHETIC_RECORD','feed_sha256':'a'*64},
        'upstream_publication':{'mode':'FORMAL','notice':'SYNTHETIC_CAVEAT'},
        'approval':{'status':'APPROVED','approved_at':'2026-10-29T22:30:00Z',
            'record_url':'https://synthetic.invalid/approval'},
        'consumer':{'safety_assessment_status':'PARTIAL','unknown_policy':'V82 §62 UNKNOWN'},
        'signals':signals,'v70_indicators':{'synthetic_id':{'value':0,'dataDate':'2026-10-28'}},
        'v70_judgments':{'mSafe_final':100,'groupRisk':{'synthetic_group':0},'isEmerg':False}}


class V70SafetyIntakeTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.at='2026-10-29T23:00:00Z'
        self.data=fixture()

    def descriptor(self):
        p=self.folder/'SYNTHETIC_V70_V2.json';p.write_text(json.dumps(self.data))
        return {'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_APPROVED_V70_DESCRIPTOR'}

    def read(self):return M.read_v70_safety_snapshot(self.descriptor(),self.at)

    def test_original_signals_indicators_judgments_dates_and_caveats_retained(self):
        before=deepcopy(self.data);out=self.read()
        for key,value in before.items():self.assertEqual(out[key],value)
        self.assertEqual(self.data,before)
        self.assertEqual(len(out['signals']),28);self.assertEqual(len(out['unknown_signals']),20)
        self.assertEqual(out['signals']['core_cpi']['data_quality'],'FALLBACK_USED')
        self.assertIsNone(out['signals']['vix']['direction'])
        out['v70_judgments']['isEmerg']=True
        self.assertEqual(self.read()['v70_judgments'],before['v70_judgments'])

    def test_zero_is_a_real_observation_and_null_remains_unknown(self):
        out=self.read()
        self.assertEqual(out['signals']['vix']['value'],0)
        self.assertNotIn('vix',out['unknown_signals'])
        self.assertIsNone(out['signals']['material_macro_events']['value'])
        self.assertIn('material_macro_events',out['unknown_signals'])

    def test_changed_source_bytes_rejected(self):
        source=self.descriptor();Path(source['local_path']).write_text('{}')
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):
            M.read_v70_safety_snapshot(source,self.at)

    def test_wrong_schema_and_v3_are_not_accepted_as_v2(self):
        for schema in ('V70.3/family-macro-feed-v3','V70.3/family-macro-safety-v1'):
            self.data['schema_version']=schema
            with self.subTest(schema=schema),self.assertRaisesRegex(ValueError,'SCHEMA_MISMATCH'):self.read()

    def test_unapproved_or_missing_approval_record_rejected(self):
        for approval in ({},{'status':'PENDING'},{'status':'APPROVED'},[]):
            self.data['approval']=approval
            with self.subTest(approval=approval),self.assertRaisesRegex(PermissionError,'APPROVAL_REQUIRED'):self.read()

    def test_evaluation_before_approval_rejected_even_after_data_cutoff(self):
        with self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):
            M.read_v70_safety_snapshot(self.descriptor(),'2026-10-29T22:29:59Z')
        out=M.read_v70_safety_snapshot(self.descriptor(),'2026-10-30T06:30:00+08:00')
        self.assertEqual(out['approval'],self.data['approval'])

    def test_invalid_cutoff_capture_or_approval_order_rejected(self):
        for key,value in [('data_cutoff','2026-10-29T22:01:00Z'),
                          ('snapshot_timestamp','2026-10-29T22:31:00Z')]:
            before=deepcopy(self.data);self.data[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):self.read()
            self.data=before
        self.data['approval']['approved_at']='2026-10-30T00:00:00Z'
        with self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):self.read()

    def test_unzoned_time_is_rejected(self):
        self.data['snapshot_timestamp']='2026-10-29T22:00:00'
        with self.assertRaisesRegex(ValueError,'TIMEZONE_REQUIRED'):self.read()

    def test_lineage_is_required(self):
        self.data['upstream_snapshot_reference']={}
        with self.assertRaisesRegex(ValueError,'LINEAGE_REQUIRED'):self.read()
        self.data=fixture();source=self.descriptor();source.pop('source_reference')
        with self.assertRaisesRegex(ValueError,'LINEAGE_REQUIRED'):
            M.read_v70_safety_snapshot(source,self.at)

    def test_absent_extra_or_empty_signal_set_is_rejected(self):
        for change in ('missing','extra','empty'):
            self.data=fixture()
            if change=='missing':self.data['signals'].pop('material_macro_events')
            elif change=='extra':self.data['signals']['unapproved_new_signal']={}
            else:self.data['signals']={}
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'SIGNAL_SET_MISMATCH'):self.read()

    def test_null_requires_unknown_quality_and_missing_reason(self):
        for key,value in [('data_quality','OK'),('issue_detail','')]:
            self.data=fixture();self.data['signals']['repo'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'UNKNOWN_REASON_REQUIRED'):self.read()

    def test_observation_requires_matching_identity_quality_source_and_date(self):
        for key,value in [('signal_name','other'),('data_quality',None),('data_quality','UNKNOWN'),
                          ('source',None),('as_of',None)]:
            self.data=fixture();self.data['signals']['vix'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.read()

    def test_observation_and_publication_after_data_cutoff_rejected(self):
        for key,value in [('as_of','2026-10-30'),('published_at','2026-10-30'),
                          ('as_of','2026-10-29T20:00:01Z')]:
            self.data=fixture();self.data['signals']['vix'][key]=value
            with self.subTest(key=key,value=value),self.assertRaisesRegex(PermissionError,'FUTURE_SIGNAL'):self.read()

    def test_missing_original_indicator_or_judgment_objects_rejected(self):
        for key in ('v70_indicators','v70_judgments'):
            self.data=fixture();self.data.pop(key)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'ORIGINAL_EVIDENCE_REQUIRED'):self.read()

    def test_original_provider_and_runner_keep_v3_and_all_safety_permissions_unchanged(self):
        f=member_fixture.MemberV82Tests();f.setUp();self.addCleanup(f.doCleanups)
        f.config['market_sources']={s:f.market(s) for s in ('VT','QQQ')}
        f.config['run_binding']={'client_id':f.client,'evaluation_at':f.at,
            'run_id':'SYNTHETIC_V70_INTAKE_REPLAY'}
        macro=macro_fixture.FormalSourceTest().snapshot();p=self.folder/'SYNTHETIC_V3.json'
        p.write_text(json.dumps(macro['payload']));macro.update(source_path=str(p),
            source_sha256=sha256(p.read_bytes()).hexdigest(),capture_receipt={
                'schema_version':'Family.W5.SourceCaptureBound.v1','captured_at':'2026-10-28T00:00:00Z',
                'source_sha256':sha256(p.read_bytes()).hexdigest(),'payload_digest':macro['digest'],
                'basis':'EXACT_SOURCE_BYTES_READ_AND_HASH_CHECKED'})
        f.config['macro_snapshot']=macro
        def run():
            provider=member_fixture.OnDemandAnalysisProvider(
                member_fixture.MemberV82SourceProducer(**f.config),repo_root=ROOT)
            request,runner=provider(f.snapshot,{'question':'SYNTHETIC_V2_V3_COEXISTENCE'})
            return request,runner,runner.analyze(request)
        before_snapshot=deepcopy(f.snapshot);base_request,_,base=run()
        f.config['v70_safety_snapshot_source']=self.descriptor()
        request,runner,result=run()
        for current,previous in zip(result['positions'],base['positions']):
            for key in ('holding','target_lines','market','native_product_identity','valuation_observations'):
                self.assertEqual(current[key],previous[key])
            self.assertEqual(current['core_observation']['result'],previous['core_observation']['result'])
            self.assertEqual(current['v3_macro_observations'],previous['macro_observations'])
            self.assertEqual(current['macro_observations']['source_sha256'],
                f.config['v70_safety_snapshot_source']['sha256'])
            self.assertEqual(current['core_observation']['macro_safety_source_audit'],current['macro_observations'])
        self.assertEqual(request['macro_snapshot'],base_request['macro_snapshot'])
        self.assertEqual(request['confirmed_target'],base_request['confirmed_target'])
        self.assertEqual(f.snapshot,before_snapshot)
        self.assertEqual(result['v70_safety_snapshot']['health_score'],100)
        self.assertEqual(len(result['v70_safety_snapshot']['unknown_signals']),20)
        self.assertEqual(result['v70_safety_snapshot']['v70_indicators'],self.data['v70_indicators'])
        self.assertFalse(result['database_written'])
        for row in result['positions']:
            self.assertFalse(row['core_observation']['result']['permission']['new_buy_order_permission'])
            self.assertIn('safety.macro',{g['field_path'] for g in row['core_observation']['input_gaps']})
        source=f.config['v70_safety_snapshot_source'];Path(source['local_path']).write_text('{}')
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):runner.analyze(request)
