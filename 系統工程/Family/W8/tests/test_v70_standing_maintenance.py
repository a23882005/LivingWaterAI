"""Synthetic standing-authority, new-capture and original-consumer regressions."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json,sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
import member_v82_analysis as M
import test_v70_safety_decisions as D
import test_member_v82_analysis as F

NUMERIC=('core_cpi','core_pce','employment_nonfarm_payrolls_3m_avg',
    'employment_unemployment_rate','fed_policy','gdp','hy_oas','move','pce',
    'real_yield','rrp','sofr','srf','treasury_10y','treasury_2y','treasury_30y','vix')


def authority():
    # Independently supplied trusted config, not copied from a daily payload.
    return {'status':'PASS_PM_ACTIVATION_ACCEPTED','approved_at':'2026-10-29T22:45:00Z',
        'activation_acceptance_at':'2026-10-29T22:49:00Z',
        'record_url':'https://synthetic.invalid/standing-authorization',
        'approved_numeric_signal_keys':list(NUMERIC),
        'unknown_signal_keys':sorted(M.V70_SAFETY_SIGNAL_NAMES-set(NUMERIC))}


def standing():
    d=D.extended();a=authority()
    d.update(data_cutoff='2026-10-29T22:50:00Z',snapshot_timestamp='2026-10-29T22:51:00Z',
        run_timestamp_utc='2026-10-29T22:52:00Z',publication_identity='e'*64,
        automatic_context_validation={'status':'FORMAL_LIVE_FEED_AND_DAILY_CAPTURE_MATCH',
            'human_per_run_approval_claimed':False},
        upstream_publication={'mode':'FORMAL','scoringAllowed':True})
    d['approval'].update(record_url=a['record_url'],approval_type='STANDING_MAINTENANCE_AUTHORIZATION',
        human_review_of_current_snapshot=False)
    d['extension_approval']={k:deepcopy(v) for k,v in a.items() if k!='activation_acceptance_at'}
    d['extension_approval'].update(status='APPROVED',approved_by='SYNTHETIC_PM',
        scope='SYNTHETIC_APPROVED_MAINTENANCE',approval_type='STANDING_MAINTENANCE_AUTHORIZATION',
        human_review_of_current_snapshot=False,activation_acceptance='PENDING_PM_ACTIVATION_ACCEPTANCE')
    return d


class StandingMaintenanceTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'SYNTHETIC_CAPTURE.json'
        self.data=standing();self.auth=authority();self.at='2026-10-29T23:00:00Z'

    def descriptor(self):
        self.path.write_text(json.dumps(self.data))
        return M.build_v70_safety_snapshot_source(self.path,
            source_reference='SYNTHETIC_APPROVED_DRIVE_SOURCE',standing_authority_binding=self.auth)

    def read(self):return M.read_v70_safety_snapshot(self.descriptor(),self.at)

    def test_standing_originals_zero_unknowns_and_independent_binding_are_preserved(self):
        d=self.descriptor();out=M.read_v70_safety_snapshot(d,self.at)
        for k,v in self.data.items():self.assertEqual(out[k],v)
        self.assertEqual(out['standing_maintenance_authorization'],self.auth)
        self.assertEqual(len(out['unknown_signals']),11)
        self.assertEqual(out['signals']['vix']['value'],0)
        self.assertEqual(d['source_reference'],'SYNTHETIC_APPROVED_DRIVE_SOURCE')
        d['standing_maintenance_authorization']['status']='CHANGED'
        self.assertEqual(self.auth['status'],'PASS_PM_ACTIVATION_ACCEPTED')

    def test_daily_json_cannot_grant_itself_standing_authority(self):
        d=self.descriptor();d.pop('standing_maintenance_authorization')
        with self.assertRaisesRegex(PermissionError,'STANDING_AUTHORIZATION_REQUIRED'):
            M.read_v70_safety_snapshot(d,self.at)

    def test_revoked_mismatched_or_malformed_trusted_authority_rejects(self):
        for key,value in [('status','PENDING'),('record_url','other'),('approved_at','2026-10-29T22:44:00Z')]:
            a=authority();a[key]=value;self.auth=a
            with self.subTest(key=key),self.assertRaisesRegex(PermissionError,'STANDING_AUTHORIZATION_REQUIRED'):self.read()
        self.auth=['MALFORMED']
        with self.assertRaisesRegex(PermissionError,'STANDING_AUTHORIZATION_REQUIRED'):self.read()

    def test_scope_order_is_irrelevant_but_expansion_duplicates_and_adoption_reject(self):
        self.data['extension_approval']['approved_numeric_signal_keys'].reverse()
        self.data['extension_approval']['unknown_signal_keys'].reverse()
        self.assertEqual(len(self.read()['unknown_signals']),11)
        for mutate in [lambda d:d['extension_approval']['approved_numeric_signal_keys'].append('cpi'),
                       lambda d:d['extension_approval']['approved_numeric_signal_keys'].__setitem__(0,'vix'),
                       lambda d:d['signals']['cpi'].update(value=3,data_quality='OK')]:
            self.data=standing();mutate(self.data)
            with self.assertRaisesRegex(PermissionError,'SCOPE_MISMATCH'):self.read()

    def test_authorized_source_failure_remains_missing_and_never_zero(self):
        self.data['signals']['vix'].update(value=None,data_quality='UNKNOWN',issue_detail='SYNTHETIC_HTTP_FAILURE')
        out=self.read();self.assertIsNone(out['signals']['vix']['value'])
        self.assertEqual(len(out['unknown_signals']),12)

    def test_daily_batch_after_activation_refreshes_hash_without_rewriting_approval(self):
        first=self.descriptor();old=deepcopy(self.data)
        self.data.update(data_cutoff='2026-10-30T22:50:00Z',snapshot_timestamp='2026-10-30T22:51:00Z',
            run_timestamp_utc='2026-10-30T22:52:00Z',publication_identity='f'*64)
        self.at='2026-10-30T23:00:00Z';second=self.descriptor()
        self.assertNotEqual(first['sha256'],second['sha256'])
        self.assertEqual(first['standing_maintenance_authorization'],second['standing_maintenance_authorization'])
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):
            M.read_v70_safety_snapshot(first,self.at)
        out=M.read_v70_safety_snapshot(second,self.at)
        self.assertEqual(out['approval'],old['approval'])
        self.assertEqual(out['extension_approval'],old['extension_approval'])

    def test_future_capture_run_cutoff_or_activation_never_becomes_available(self):
        for key,value in [('data_cutoff','2026-10-29T22:51:01Z'),
                          ('snapshot_timestamp','2026-10-29T22:52:01Z'),
                          ('run_timestamp_utc','2026-10-29T23:00:01Z')]:
            self.data=standing();self.data[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):self.read()
        self.data=standing();self.auth['activation_acceptance_at']='2026-10-29T23:00:01Z'
        with self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):self.read()

    def test_candidate_and_false_human_approval_or_publication_claims_reject(self):
        for field in ['candidate','human_context','human_approval','human_extension','publication','identity']:
            self.data=standing()
            if field=='candidate':self.data['automatic_context_validation']['status']='CANDIDATE'
            elif field=='human_context':self.data['automatic_context_validation']['human_per_run_approval_claimed']=True
            elif field=='human_approval':self.data['approval']['human_review_of_current_snapshot']=True
            elif field=='human_extension':self.data['extension_approval']['human_review_of_current_snapshot']=True
            elif field=='publication':self.data['upstream_publication']['mode']='CANDIDATE'
            else:self.data['publication_identity']='not-an-identity'
            with self.subTest(field=field),self.assertRaisesRegex(PermissionError,'FORMAL_PUBLICATION_REQUIRED'):self.read()

    def test_original_provider_runner_and_decision_consumers_receive_bound_source(self):
        f=F.MemberV82Tests();f.setUp();self.addCleanup(f.doCleanups)
        f.config['market_sources']={s:f.market(s) for s in ('VT','QQQ')}
        f.config['run_binding']={'client_id':f.client,'evaluation_at':f.at,'run_id':'SYNTHETIC_STANDING'}
        f.config['v70_safety_snapshot_source']=self.descriptor();before=deepcopy(f.snapshot)
        provider=F.OnDemandAnalysisProvider(M.MemberV82SourceProducer(**f.config),repo_root=ROOT)
        request,runner=provider(f.snapshot,{'question':'SYNTHETIC_STANDING_SOURCE'})
        result=runner.analyze(request);shared=result['v70_safety_snapshot']
        self.assertEqual(shared['standing_maintenance_authorization'],self.auth)
        self.assertEqual(shared['approval']['approved_at'],self.data['approval']['approved_at'])
        for row in result['positions']:
            self.assertEqual(row['macro_observations']['source_sha256'],shared['sha256'])
            self.assertEqual(row['core_observation']['macro_safety_source_audit']['source_sha256'],shared['sha256'])
            self.assertEqual(row['formal_conclusion']['macro_safety_source_audit']['source_sha256'],shared['sha256'])
            self.assertFalse(row['core_observation']['result']['permission']['new_buy_order_permission'])
        self.assertFalse(result['database_written']);self.assertEqual(result['trade_authorization'],'NONE')
        self.assertEqual(f.snapshot,before)
        self.path.write_text('{}')
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):runner.analyze(request)
