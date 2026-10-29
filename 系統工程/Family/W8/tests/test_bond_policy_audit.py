"""Owner records are evidence, never a present SGOV cash or role balance."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import bond_policy_audit as A


class BondPolicyAuditTest(unittest.TestCase):
    def case(self,directory):
        text=('## 歷史本人紀錄\n- IBKR內SGOV定位：**美元股票ETF買點彈藥庫**\n'
            '| `SGOV_BOND_BUCKET` | NT$0 | 2026/09/15 |\n'
            '| `SGOV_DRY_POWDER_BUCKET` | NT$400,000 | 2026/09/15 |\n')
        path=Path(directory)/'synthetic-owner-record.md';path.write_text(text)
        proof={'schema_version':'Family.W5.ApprovedDocumentTargetSource.v1',
            'client_id':'SYNTHETIC_CLIENT','local_source_path':str(path),
            'source_sha256':sha256(path.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_OWNER_RECORD','source_available_at':'2026-09-19T00:00:00Z'}
        request={'client_id':proof['client_id'],'run_id':'SYNTHETIC_RUN',
            'evaluation_at':'2026-10-28T00:00:00Z',
            'client_snapshot':{'payload':{'source_sha256':'a'*64}},
            'confirmed_target':{'source_kind':'OFFICIAL_W1_CONFIRMED_ALLOCATION',
                'payload':{'draft':{'target_lines':[{'ticker':'SGOV','weight':'0.2'}]}}}}
        return request,{'approved_document_target_source':proof},path

    def test_policy_survives_new_target_without_promoting_dated_amounts(self):
        with tempfile.TemporaryDirectory() as directory:
            req,ctx,_=self.case(directory);before=deepcopy((req,ctx));out=A.build(req,ctx)
            self.assertEqual(out['owner_role_policy'],'EXPLICIT_IBKR_STOCK_OPPORTUNITY_RESERVE')
            self.assertEqual(out['current_target_source_kind'],'OFFICIAL_W1_CONFIRMED_ALLOCATION')
            self.assertIn('NT$400,000',out['role_evidence'][2]['text'])
            self.assertFalse(out['historical_amounts_applied_to_current_holdings'])
            self.assertFalse(out['target_amounts_applied_to_current_roles'])
            self.assertEqual(out['current_role_valuation_status'],'NOT_ESTABLISHED_BY_HISTORICAL_DOCUMENT')
            self.assertEqual((req,ctx),before)
            out['historical_amounts_applied_to_current_holdings']=True
            with self.assertRaisesRegex(PermissionError,'REPLAY_MISMATCH'):
                A.validate(req,ctx,{'bond_policy_audit':out})

    def test_other_member_changed_source_and_future_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            req,ctx,path=self.case(directory)
            wrong=deepcopy(ctx);wrong['approved_document_target_source']['client_id']='OTHER_CLIENT'
            with self.assertRaisesRegex(PermissionError,'CLIENT_MISMATCH'):A.build(req,wrong)
            future=deepcopy(ctx);future['approved_document_target_source']['source_available_at']='2026-10-29T00:00:00Z'
            with self.assertRaisesRegex(PermissionError,'TIME_MISMATCH'):A.build(req,future)
            path.write_text('changed owner policy')
            with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):A.build(req,ctx)

    def test_documented_rule_exception_is_not_client_exception_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            req,ctx,_=self.case(directory);rule=Path(directory)/'synthetic-rule.md'
            rule.write_text('若客戶有明確帳戶／市場限制，可依個案調整並記錄原因。\n')
            ctx['bond_rule_source']={'local_source_path':str(rule),'source_reference':'SYNTHETIC_RULE',
                'source_sha256':sha256(rule.read_bytes()).hexdigest(),'source_available_at':'2026-09-19T00:00:00Z'}
            out=A.build(req,ctx)['rule_exception_evidence']
            self.assertEqual(len(out['source_lines']),1)
            self.assertFalse(out['client_exception_approved'])

    def test_legacy_valuation_excerpt_cannot_establish_owner_role_policy(self):
        self.assertIsNone(A.build({}, {'approved_document_target_source':{
            'source_reference':'SYNTHETIC_VALUATION_ONLY'}}))


if __name__=='__main__':unittest.main()
