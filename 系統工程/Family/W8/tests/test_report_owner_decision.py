"""Owner-row provenance and pending weights, with an entirely synthetic SQLite DB."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=importlib.util.spec_from_file_location('owner_decision_fixture',Path(__file__).parent/'fixtures/report_html/synthetic.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class OwnerDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'synthetic.db'
        self.c=F.owner_decision_case(self.path)

    def build(self,c=None):
        return F.D.build_w6_current_data((c or self.c)['source'],(c or self.c)['market'],(c or self.c)['engine'])

    def source(self,evidence,**extra):
        options={'owner_decision':evidence,'expected_owner_decision_digest':F.A.digest(evidence),
                 'profile_db_path':self.path,'evaluation_at':F.AT};options.update(extra)
        return F.S.build_report_source(self.c['snapshot'],account='AR',expected_client_id=F.CLIENT,**options)

    def test_exact_db_row_and_pinned_projection_keep_originals_and_pending_weights(self):
        before=deepcopy(self.c);raw=self.path.read_bytes();out=self.build()
        self.assertEqual(self.c,before);self.assertEqual(self.path.read_bytes(),raw)
        self.assertEqual(out['target_version'],None)
        rows={r['代碼']:r for r in out['target']}
        self.assertNotIn('NEW',rows)
        self.assertEqual(rows['KEEP']['權重'],'0.4');self.assertEqual(rows['BOTH']['權重'],'0.4')
        self.assertIsNone(rows['SYN_A']['權重']);self.assertIsNone(rows['SYN_B']['權重'])
        self.assertTrue(all(r['市值TWD'] is None for r in rows.values()))
        self.assertEqual(out['report_source_lineage']['owner_target_decision']['original_row'],self.c['owner_evidence']['original_row'])
        self.assertEqual(self.c['source']['historical_confirmed_target_details'],self.c['legacy_source']['current_confirmed_target_details'])

    def test_profile_context_is_required_and_prose_is_not_an_approval_parser(self):
        with self.assertRaisesRegex(ValueError,'TRUSTED_CONTEXT_REQUIRED'):
            F.S.build_report_source(self.c['snapshot'],account='AR',expected_client_id=F.CLIENT,owner_decision=self.c['owner_evidence'])
        changed=deepcopy(self.c['owner_evidence']);changed['original_row']['value_text']='SYNTHETIC unverified instruction'
        with self.assertRaisesRegex(ValueError,'BINDING'):
            self.source(changed,expected_owner_decision_digest=F.A.digest(self.c['owner_evidence']))
        with self.assertRaisesRegex(ValueError,'ORIGINAL_ROW'):
            self.source(changed)

    def test_foreign_db_client_original_row_and_unauthorized_projection_rejected(self):
        for attack in ('client','DB','db_file','row_client','row_source','projection_weight','new_percentage','duplicate','overlap'):
            with self.subTest(attack=attack):
                e=deepcopy(self.c['owner_evidence'])
                if attack=='client':e['client_id']='OTHER'
                elif attack=='DB':e['source_db_sha256']='b'*64
                elif attack=='db_file':
                    other=self.path.with_name('wrong.db');other.write_bytes(b'SYNTHETIC_WRONG_FILE')
                    with self.assertRaisesRegex(ValueError,'DB_SHA'):self.source(e,profile_db_path=other)
                    continue
                elif attack=='row_client':e['original_row']['client_id']='OTHER'
                elif attack=='row_source':e['original_row']['source_reference']='ALTERED'
                elif attack=='projection_weight':e['PM_projection']['included_weight_units']=[70000,70000]
                elif attack=='new_percentage':e['PM_projection']['included_weight_pending']=[{'ticker':'SYN_A','weight':.07}]
                elif attack=='duplicate':e['PM_projection']['included_weight_pending']=['SYN_A','SYN_A']
                else:e['PM_projection']['included_weight_pending']=['NEW']
                with self.assertRaises(ValueError):self.source(e)

    def test_future_profile_and_future_report_receipt_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'FUTURE'):
            F.owner_decision_case(Path(self.tmp.name)/'future.db',row_changes={'updated_at_utc':'2099-01-01T00:00:00Z'})
        c=deepcopy(self.c);d=c['source']['owner_target_decision'];d['verified_cutoff']='2099-01-01T00:00:00Z'
        d['digest']=F.A.digest({k:v for k,v in d.items() if k!='digest'});F.owner_decision_refresh(c)
        with self.assertRaisesRegex(ValueError,'FUTURE'):self.build(c)

    def test_rehashed_display_weights_cannot_create_approval(self):
        for attack in ('zero','percentage','old_instrument','raw_row'):
            with self.subTest(attack=attack):
                c=deepcopy(self.c);d=c['source']['owner_target_decision']
                if attack=='raw_row':d['original_row']['value_text']='ALTERED'
                elif attack=='old_instrument':d['selection_lines'].append(deepcopy(d['historical_targets'][0]['allocations'][-1]))
                else:d['selection_lines'][-1]['weight_units']=0 if attack=='zero' else 70000
                d['digest']=F.A.digest({k:v for k,v in d.items() if k!='digest'});F.owner_decision_refresh(c)
                with self.assertRaisesRegex(ValueError,'OWNER_DECISION'):self.build(c)

    def test_new_db_cannot_take_the_old_member_result(self):
        old=F.member_case()
        with self.assertRaises(ValueError):
            F.A.make_member_review_inputs(self.c['source'],old['request'],old['result'],source_id='SYNTHETIC_OLD_RESULT',rules_sha='e'*64)

    def test_reported_cash_stays_unknown_without_addition_or_nav(self):
        c=deepcopy(self.c);c['source']['current_cash_by_account_currency']=[
            {'account_key':key,'currency':'TWD','reported_cash_minor':123400,'data_state':'NEEDS_REVIEW'}
            for key in ('SYN_CASH_A','SYN_CASH_ALIAS')]
        F.owner_decision_refresh(c);out=self.build(c)
        self.assertIsNone(out['current_total_twd']);self.assertEqual(out['actual'],[]);self.assertEqual(out['drift'],[])
        self.assertIsNone(out['approved_radar']);self.assertEqual(len(c['source']['current_cash_by_account_currency']),2)

    def test_legacy_complete_target_and_only_permitted_renderer_blocks(self):
        c=deepcopy(self.c);c['source']=c['legacy_source'];F.owner_decision_refresh(c)
        old=self.build(c);self.assertNotIn('target_decision',old);self.assertEqual(old['target_version'],7)
        new=self.build();self.assertIn('piegrid',str(F.R._build_blocks(old)[4]))
        self.assertNotIn('piegrid',str(F.R._build_blocks(new)[4]))
        # With the identical data and no decision, all unaffected chapters stay exact.
        adapted=deepcopy(old);adapted['target_decision']=new['target_decision'];adapted['target']=new['target'];adapted['target_version']=None
        a=F.R._build_blocks(old);b=F.R._build_blocks(adapted)
        self.assertEqual([i+1 for i in range(14) if a[i]!=b[i]],[2,5,6])


if __name__=='__main__':unittest.main()
