"""Cash-only trial assumptions and propagation of genuine native rejections."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import native_asset_source as M
from family_input import digest
from family_runner import FamilyRunner
from family_boundary import BoundaryError


class NativeSourceTest(unittest.TestCase):
    def setUp(self):
        self.client='fam_'+'a'*32
        self.owner={'client_id':self.client,'account':'SYNTHETIC_IB','broker':'IBKR','currency':'USD'}
        self.policy={'schema_version':'Family.W8.CashTrialPolicy.v1','missing_cash_value':'0',
            'source_reference':'SYNTHETIC_EXPLICIT_CASH_ONLY_POLICY'}
        self.tables={'portfolio_instrument':[],'portfolio_position':[],
            'portfolio_snapshot_run':[{'client_id':self.client,'run_id':'SCREEN','run_state':'SEALED',
                'source_kind':'USER_PROVIDED','as_of_utc':'2026-10-20T00:00:00Z','version_no':1}],
            'portfolio_snapshot_item':[
                {'client_id':self.client,'run_id':'SCREEN','domain_code':'OWNER_SCREENSHOT_SOURCE',
                 'entity_key':'VT','field_key':'quantity','value_state':'KNOWN','value_text':'1.2500'},
                {'client_id':self.client,'run_id':'SCREEN','domain_code':'OWNER_SCREENSHOT_SOURCE',
                 'entity_key':'IB_SCREEN','field_key':'cash_balance','value_state':'KNOWN',
                 'value_text':'123.45','currency_code':'USD'}],
            'currency_registry':[{'currency_code':'USD','minor_digits':2}],
            'cash_balance_snapshot':[]}

    def snapshot(self,sha='a'*64):
        return {'client_id':self.client,'source_sha256':sha,'tables':self.tables,'payload_digest':digest(self.tables)}

    def test_existing_total_retained_and_only_missing_cash_fields_zeroed(self):
        before=deepcopy(self.tables);out=M.cash_trial(self.snapshot(),self.owner,self.policy)
        self.assertEqual(out['decimal_values']['total'],'123.45')
        self.assertEqual(out['cash_state']['available'],0)
        self.assertEqual({r['field_path'] for r in out['assumptions']},
            {'cash_state.available','cash_state.unsettled','cash_state.reserved'})
        self.assertEqual(self.tables,before)
        self.assertEqual(self.tables['portfolio_snapshot_item'][0]['value_text'],'1.2500')
        self.assertEqual(out['label'],'缺漏現金按 0 試算')

    def test_policy_and_member_source_are_required(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_CASH_TRIAL_POLICY_REQUIRED'):
            M.cash_trial(self.snapshot(),self.owner,{})
        self.tables['portfolio_snapshot_item'][0]['client_id']='OTHER'
        with self.assertRaisesRegex(PermissionError,'CLIENT_MISMATCH'):
            M.cash_trial(self.snapshot(),self.owner,self.policy)

    def test_formal_available_and_reserved_from_same_db_view_not_zeroed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic.db'
            with sqlite3.connect(p) as db:
                db.execute('CREATE TABLE cash_available_view(client_id TEXT,account_key TEXT,currency_code TEXT,'
                    'as_of_utc TEXT,version INTEGER,available_state TEXT,available_minor INTEGER,reserved_minor INTEGER)')
                db.execute('INSERT INTO cash_available_view VALUES(?,?,?,?,?,?,?,?)',
                    (self.client,'SYNTHETIC_IB','USD','2026-10-21T00:00:00Z',1,'VERIFIED',950,225))
            raw=p.read_bytes();snapshot=self.snapshot(hashlib.sha256(raw).hexdigest())
            out=M.cash_trial(snapshot,self.owner,self.policy,db_path=p)
            self.assertEqual(out['decimal_values']['available'],'9.5')
            self.assertEqual(out['decimal_values']['reserved'],'2.25')
            self.assertEqual([r['field_path'] for r in out['assumptions']],['cash_state.unsettled'])
            self.assertEqual(p.read_bytes(),raw)
            snapshot['source_sha256']='b'*64
            with self.assertRaisesRegex(PermissionError,'DB_MISMATCH'):
                M.cash_trial(snapshot,self.owner,self.policy,db_path=p)

    def test_formal_classes_are_distinct_and_unlisted_company_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic-rule-catalog.md'
            p.write_text('\n'.join(M.FORMAL_CLASSES)+'\n# 第四十九章｜VT／VWRA型\n')
            source={'local_path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'source_reference':'SYNTHETIC_RULE_CATALOG'}
            self.assertEqual(M.classification('VT',source)['primary_class'],'全球股票ETF')
            self.assertEqual(M.classification('SOXX',source)['primary_class'],'半導體ETF')
            self.assertEqual(M.classification('UNLISTED_COMPANY',source)['primary_class'],'UNKNOWN')
            self.assertEqual(M.classification('VT',source)['asset_grade'],'UNKNOWN')
            p.write_text('replaced')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):M.classification('VT',source)

    def test_grade_requires_product_evidence_and_formal_mapping_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic-rules.md'
            p.write_text('\n'.join(M.FORMAL_CLASSES)+'\n# 第四十九章｜VT／VWRA型\n廣泛分散核心市場結構 → `A`\n')
            source={'local_path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                'source_reference':'SYNTHETIC_RULE_CATALOG'}
            product=Path(tmp)/'synthetic-issuer.json'
            product.write_text(json.dumps({'symbol':'VT',
                'source_url':'https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf',
                'excerpts':['FTSE Global All Cap Index','Passively managed','developed and emerging',
                            'large-, mid-, and small-capitalization']}))
            proof={'local_path':str(product),'sha256':hashlib.sha256(product.read_bytes()).hexdigest()}
            self.assertEqual(M.classification('VT',source,proof)['asset_grade'],'A')
            product.write_text('{}');proof['sha256']=hashlib.sha256(product.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'STRUCTURE_EVIDENCE_REQUIRED'):
                M.classification('VT',source,proof)

    def test_three_domain_slots_preserve_unknown_account_without_fabrication(self):
        self.tables['portfolio_account']=[{'account_key':'SYNTHETIC_IB','account_label':'IB US category'},
            {'account_key':'SYNTHETIC_TW','account_label':'Taiwan broker source category'}]
        snapshot=self.snapshot();selected=M.cash_trial(snapshot,self.owner,self.policy)
        producer=M.AssetSourceProducer.__new__(M.AssetSourceProducer)
        producer.policy=self.policy;producer.db_path=None
        owner={'funding_domain':'US_BROKER','broker':'IBKR','account':'SYNTHETIC_IB'}
        contexts,trials=producer.funding_contexts(snapshot,owner,selected,'SYNTHETIC_RUN','SYNTHETIC_REF')
        self.assertEqual(len(contexts),3)
        self.assertEqual(contexts[0]['broker'],'Taiwan broker source category')
        self.assertEqual(contexts[0]['account'],'SYNTHETIC_TW')
        self.assertIsNone(contexts[1]['broker']);self.assertIsNone(contexts[1]['account'])
        self.assertEqual(contexts[1]['brokerage_cash_state'],{'total':0.0,'available':0.0,'unsettled':0.0,'reserved':0.0})
        self.assertEqual(len(trials['TW_SUB_BROKERAGE']['assumptions']),4)
        self.assertTrue(all(row['bucket_new_investment_amount'] is None for row in contexts))

    def test_qqq_has_independent_identity_grade_and_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            rule=Path(tmp)/'synthetic-rules.md'
            rule.write_text('\n'.join(M.FORMAL_CLASSES)+'\n# 第四十六章｜QQQ型\n'+
                '中度集中／成長或大型權值集中，但仍屬Broad核心曝險 → `B`')
            source={'local_path':str(rule),'sha256':hashlib.sha256(rule.read_bytes()).hexdigest(),
                'source_reference':'SYNTHETIC_RULE_CATALOG'}
            product=HERE/'QQQ_product_identity.json'
            proof={'local_path':str(product),'sha256':hashlib.sha256(product.read_bytes()).hexdigest()}
            result=M.classification('QQQ',source,proof)
            self.assertEqual(result['asset_grade'],'B');self.assertEqual(result['asset_type'],'BROAD_ETF')
            self.assertEqual(result['analysis_capabilities'],['V82_QQQ_CORE'])
            with self.assertRaisesRegex(ValueError,'STRUCTURE_EVIDENCE_REQUIRED'):
                M.classification('SOXX',source,proof)

    def test_native_money_error_has_exact_path_and_cash_cannot_make_an_investment_pool(self):
        error=ValueError('C8C9.W4.MONEY: c7.contexts[0].bucket_new_investment_amount must be JSON number or decimal string')
        self.assertEqual(M.native_error_path(error),'/c7_funding_context/contexts/0/bucket_new_investment_amount')

    def failure_case(self):
        req={'client_id':self.client,'run_id':'SYNTHETIC_RUN','request_id':'SYNTHETIC_REQ',
            'evaluation_at':'2026-10-28T00:00:00Z',  # Historical base-rule rejection fixture.
            'owner':self.owner,'client_snapshot':{'payload':self.snapshot()}}
        report={'schema_version':'Family.W8.NativeSourceProduction.v1','status':'BLOCKED_BY_ORIGINAL_ADAPTER',
            'complete_native_bundle':False,'mentor':None,'client_id':self.client,'owner':self.owner,
            'run_id':req['run_id'],'source_db_sha256':'a'*64,'request_digest':digest(req),
            'first_failure':{'function':'C8C9.Work4.build_v82_runtime_input','code':'C8C9.W4.C7_DOMAIN_SET',
                'field_path':'c7_funding_context.contexts','raw_error':'C7 FundingContext must retain exactly three contexts'},
            'call_trace':['SYNTHETIC_TEST_NATIVE_REJECTION_REPORT']}
        report['report_digest']=digest(report)
        runner=FamilyRunner.__new__(FamilyRunner);runner.context_provider=lambda:{'client_id':self.client}
        runner.native_source_report=report
        return req,report,runner

    def test_original_failure_propagates_without_claiming_pipeline_or_mentor(self):
        req,report,runner=self.failure_case()
        with patch('family_runner.prepare_input') as guard:
            result=runner.analyze(req)
        guard.assert_called_once()
        self.assertEqual(result['status'],'DATA_UNAVAILABLE')
        self.assertEqual(result['issue_codes'][0]['code'],'C8C9.W4.C7_DOMAIN_SET')
        self.assertIsNone(result['mentor'])
        self.assertFalse(result['source_production']['complete_native_bundle'])

    def test_source_failure_cannot_replace_member_or_claim_success(self):
        for key,value in [('client_id','OTHER'),('status','OK'),('mentor',{'fake':'mentor'})]:
            req,report,runner=self.failure_case();report[key]=value
            report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
            with patch('family_runner.prepare_input'):result=runner.analyze(req)
            self.assertEqual(result['status'],'BLOCKED')
            self.assertNotIn('source_production',result)
            self.assertIsNone(result['mentor'])

    def test_authentication_failure_stops_before_source_result_publication(self):
        req,report,runner=self.failure_case()
        with patch('family_runner.prepare_input',side_effect=BoundaryError('ANALYSIS_PERMISSION_REQUIRED','analysis_permission')):
            result=runner.analyze(req)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertNotIn('source_production',result)


if __name__=='__main__':unittest.main()
