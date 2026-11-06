"""Approved legacy target input reaches original boundary without re-signing."""
from copy import deepcopy
from datetime import datetime, timezone
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE.parent/'W5'))
sys.path.insert(0,str(HERE.parent/'W5/tests'))
from family_boundary import validate_target,BoundaryError,prepare_input
from test_family_boundary import fixture
spec=spec_from_file_location('approved_target_input_test',HERE/'approved_target_input.py')
M=module_from_spec(spec);spec.loader.exec_module(M)


class ApprovedTargetTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'approved.md'
        line='| VT | 100% | existing approved target |'
        self.path.write_text('# Existing approved target\n'+line+'\n')
        self.client='fam_'+'a'*32
        self.args=dict(client_id=self.client,source_path=self.path,
            source_reference='drive:verified_source',source_available_at='2026-09-15T00:00:00Z',
            target_version=1,allocation_version='EXISTING-v1',
            rows=[{'source_line':line,'weight':'1'}],
            mappings=[{'instrument_id':'VT','ticker':'VT','asset_type':'股票ETF'}])

    def build(self):return M.build_approved_target_view(**self.args)

    def validate(self,pack):
        return validate_target(pack['target'],self.client,
            datetime(2026,10,27,tzinfo=timezone.utc),
            approved_document_source=pack['trusted_approved_target_source'])

    def test_existing_approval_and_unknown_capital_preserved(self):
        pack=self.build();target=self.validate(pack)
        self.assertEqual(target['payload']['confirmation_evidence']['action'],'READ_EXISTING_APPROVAL')
        self.assertIsNone(target['payload']['confirmation_evidence']['original_confirmed_at'])
        self.assertIsNone(target['payload']['draft']['target_lines'][0]['target_amount']['amount'])
        self.assertFalse(pack['database_written'])

    def test_original_prepare_input_binds_document_target(self):
        req,ctx=fixture(self.client);pack=self.build();target=pack['target']
        req['confirmed_target']=target;ctx['approved_document_target_source']=pack['trusted_approved_target_source']
        ctx['target_hash']=target['target_hash']
        out=prepare_input(req,trusted_context=ctx)
        self.assertEqual(out.payload['target_binding']['allocation_id'],target['payload']['draft']['allocation_id'])

    def test_source_or_request_replacement_rejected(self):
        pack=self.build();pack['target']['payload']['draft']['target_lines'][0]['weight']['value']=.5
        with self.assertRaisesRegex(BoundaryError,'VIEW_MISMATCH'):self.validate(pack)
        pack=self.build();self.path.write_text('changed source')
        with self.assertRaisesRegex(BoundaryError,'SOURCE_CHANGED'):self.validate(pack)

    def test_target_rows_must_be_original_source_and_client_bound(self):
        self.args['rows'][0]['weight']='0.9'
        with self.assertRaisesRegex(ValueError,'WEIGHT_SOURCE'):self.build()
        self.args['rows'][0]['weight']='1';pack=self.build()
        pack['trusted_approved_target_source']['client_id']='another'
        with self.assertRaisesRegex(BoundaryError,'TRUSTED_SOURCE_REQUIRED'):self.validate(pack)

    def test_document_account_scope_keeps_cash_and_completeness_unknown(self):
        req,ctx=fixture(self.client);snap=req['client_snapshot']['payload']
        # Existing known synthetic category; no external broker ID is required.
        pack=self.build();scope=M.bind_document_account_scope(snap,pack,account_key='ACCOUNT_1',
            broker='BROKER_1',broker_source_label='Existing approved target',currency='USD',
            funding_domain='INVESTMENT_1')
        from family_boundary import bind_owner
        result=bind_owner(snap,req['owner'],datetime(2026,10,27,tzinfo=timezone.utc),approved_account_scope=scope)
        self.assertFalse(result['cash_verified'])
        self.assertFalse(result['holdings_completeness_verified'])
        self.assertIsNone(scope['external_broker_account_id'])
        scope['owner']['account']='another'
        with self.assertRaisesRegex(BoundaryError,'SCOPE_MISMATCH'):
            bind_owner(snap,req['owner'],datetime(2026,10,27,tzinfo=timezone.utc),approved_account_scope=scope)

    def test_owner_accepts_existing_official_holdings_without_new_portfolio(self):
        req,ctx=fixture(self.client);snap=req['client_snapshot']['payload']
        snap['schema_version']='Family.W5.W1Snapshot.v1'
        snap['data_provenance']='SOURCE_BACKED';snap['source_sha256']='a'*64
        snap['payload_digest']=M._digest(snap['tables'])
        before=deepcopy(snap)
        decision={'schema_version':'Family.W8.OwnerOfficialHoldingsDecision.v1',
            'action':'ACCEPT_EXISTING_OFFICIAL_HOLDINGS','client_id':self.client,
            'official_file_id':'official-db','source_db_sha256':'a'*64,
            'source_reference':'OWNER_DECISION_CURRENT_CONVERSATION',
            'statement':'現在有的就是正式持倉',
            'recorded_at':'2026-10-27T00:00:00Z'}
        proof=M.bind_official_holdings(snap,official_file_id='official-db',
            account_key='ACCOUNT_1',owner_decision=decision,
            evaluation_at='2026-10-27T01:00:00Z')
        from family_boundary import position_view
        positions=position_view(snap,'ACCOUNT_1',datetime(2026,10,27,1,tzinfo=timezone.utc),proof)
        self.assertEqual(len(positions),1)
        self.assertEqual(snap,before)
        self.assertFalse(proof['cash_settlement_asserted'])
        self.assertFalse(proof['database_written'])
        for key,value in [('client_id','another'),('official_file_id','another'),
                          ('source_db_sha256','b'*64)]:
            changed=deepcopy(decision);changed[key]=value
            with self.assertRaisesRegex(PermissionError,'OWNER_DECISION_MISMATCH'):
                M.bind_official_holdings(snap,official_file_id='official-db',
                    account_key='ACCOUNT_1',owner_decision=changed,
                    evaluation_at='2026-10-27T01:00:00Z')


if __name__=='__main__':unittest.main()
