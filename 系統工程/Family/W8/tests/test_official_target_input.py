"""Current official allocations supersede old document target views."""
from copy import deepcopy
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
from family_input import digest
from family_boundary import validate_target
from datetime import datetime, timezone
import official_target_input as M
import approved_target_input as A


class OfficialTargetTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'approved.md'
        line = '- 正式投資池：NT$1,000；生活費NT$500仍在投資池外。'
        self.path.write_text(line)
        self.base = {'local_source_path': str(self.path),
            'source_sha256': hashlib.sha256(self.path.read_bytes()).hexdigest(),
            'source_line': line, 'amount': '1000', 'currency': 'TWD',
            'source_reference': 'SYNTHETIC_APPROVED_POOL',
            'source_available_at': '2026-10-01T00:00:00Z'}
        self.client = 'fam_' + 'a' * 32
        self.at = '2026-10-28T00:00:00Z'
        self.snapshot = {'schema_version': 'Family.W5.W1Snapshot.v1',
            'data_provenance': 'SOURCE_BACKED', 'client_id': self.client,
            'source_sha256': 'a'*64, 'tables': {
                'final_target_version': [{'client_id': self.client, 'target_key': 'MAIN',
                    'version_no': 2, 'lifecycle_state': 'CONFIRMED', 'completeness_state': 'COMPLETE',
                    'confirmed_by': 'AUTHORIZED_REPRESENTATIVE',
                    'confirmation_source_ref': 'SYNTHETIC_EXISTING_CONFIRMATION',
                    'created_at_utc': '2026-10-20T00:00:00Z',
                    'confirmed_at_utc': '2026-10-20T01:00:00Z'}],
                'final_target_allocation': [], 'portfolio_instrument': []}}
        for symbol, weight in [('AAA', 800000), ('BBB', 200000), ('CCC', 0)]:
            self.snapshot['tables']['final_target_allocation'].append({
                'client_id': self.client, 'target_key': 'MAIN', 'version_no': 2,
                'instrument_key': 'OPAQUE-' + symbol, 'weight_units': weight,
                'allocation_state': 'ACCEPTED', 'allocation_source_ref': 'SYNTHETIC_OWNER',
                'created_at_utc': '2026-10-20T00:00:00Z'})
            self.snapshot['tables']['portfolio_instrument'].append({
                'client_id': self.client, 'instrument_key': 'OPAQUE-' + symbol,
                'ticker': symbol, 'instrument_type': 'ETF', 'identity_state': 'KNOWN'})
        self.rehash()

    def rehash(self):
        self.snapshot['payload_digest'] = digest(self.snapshot['tables'])

    def build(self):
        return M.build(self.snapshot, evaluation_at=self.at, base_source=self.base)

    def test_original_confirmation_and_explicit_zero_preserved(self):
        before = deepcopy(self.snapshot)
        view, proof = self.build()
        draft = view['payload']['draft']
        self.assertEqual([r['target_amount']['amount'] for r in draft['target_lines']],
                         ['800.0', '200.0', '0'])
        self.assertEqual(view['payload']['confirmation_evidence']['confirmed_by'],
                         'AUTHORIZED_REPRESENTATIVE')
        self.assertFalse(proof['approval_created'])
        self.assertEqual(self.snapshot, before)
        self.assertEqual(M.validate(view, proof, self.snapshot, self.at), view)
        self.assertEqual(validate_target(view, self.client,
            datetime(2026,10,28,tzinfo=timezone.utc),official_target_source=proof,
            snapshot=self.snapshot),view)

    def test_rehashed_forged_amount_or_other_snapshot_rejected(self):
        view, proof = self.build()
        changed = deepcopy(view)
        changed['payload']['draft']['target_lines'][0]['target_amount']['amount'] = '999'
        proof['target_view_digest'] = digest(changed)
        with self.assertRaisesRegex(PermissionError, 'REPLAY_MISMATCH'):
            M.validate(changed, proof, self.snapshot, self.at)
        self.snapshot['source_sha256'] = 'b' * 64
        with self.assertRaisesRegex(PermissionError, 'REPLAY_MISMATCH'):
            M.validate(view, proof, self.snapshot, self.at)

    def test_latest_incomplete_does_not_restore_old_confirmed_target(self):
        latest=deepcopy(self.snapshot['tables']['final_target_version'][0])
        latest.update(version_no=3,lifecycle_state='DRAFT')
        self.snapshot['tables']['final_target_version'].append(latest);self.rehash()
        with self.assertRaisesRegex(ValueError,'NOT_CURRENT_COMPLETE'):
            self.build()

    def test_bad_sum_duplicate_identity_future_or_foreign_row_rejected(self):
        for kind in ('sum','duplicate','future','foreign'):
            with self.subTest(kind=kind):
                saved=deepcopy(self.snapshot)
                rows=self.snapshot['tables']['final_target_allocation']
                if kind=='sum':rows[0]['weight_units']-=1
                elif kind=='duplicate':rows.append(deepcopy(rows[-1]))
                elif kind=='future':rows[0]['created_at_utc']='2026-10-29T00:00:00Z'
                else:rows[0]['client_id']='another-member'
                self.rehash()
                with self.assertRaisesRegex(ValueError,'ALLOCATION_INVALID'):self.build()
                self.snapshot=saved

    def test_wrong_pool_amount_and_changed_source_rejected(self):
        self.base['amount']='500'
        with self.assertRaisesRegex(ValueError,'AMOUNT_MISMATCH'):self.build()
        self.base['amount']='1000';self.path.write_text('changed')
        with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):self.build()


class AcceptanceSuccessorTest(unittest.TestCase):
    def setUp(self):
        self.client='fam_'+'b'*32
        self.old={'schema_version':'Family.W5.W1Snapshot.v1','data_provenance':'SOURCE_BACKED',
            'client_id':self.client,'source_sha256':'a'*64,'tables':{
                'portfolio_account':[{'client_id':self.client,'account_key':'IB','account_currency':None}],
                'portfolio_instrument':[{'client_id':self.client,'instrument_key':'X','ticker':'AAA',
                    'instrument_type':'ETF','quote_currency':'USD'}],
                'portfolio_position':[{'client_id':self.client,'instrument_key':'X','account_key':'IB',
                    'as_of_utc':'2026-10-01T00:00:00Z','quantity_decimal':'2'}],
                'portfolio_snapshot_run':[{'client_id':self.client,'run_id':'INTAKE','run_state':'SEALED',
                    'source_kind':'AUTHORIZED_IMPORT','as_of_utc':'2026-10-02T00:00:00Z'}],
                'portfolio_snapshot_item':[{'client_id':self.client,'run_id':'INTAKE','field_key':'accepted_W6_broker_holdings_json',
                    'value_state':'KNOWN','value_text':'[{"symbol":"AAA","quantity":"2","broker_label":"IB","currency":"USD"}]'}],
                'portfolio_snapshot_lineage':[]}}
        self.old['payload_digest']=digest(self.old['tables'])
        self.decision={'schema_version':'Family.W8.OwnerOfficialHoldingsDecision.v1',
            'action':'ACCEPT_EXISTING_OFFICIAL_HOLDINGS','client_id':self.client,
            'official_file_id':'synthetic-official-db','source_db_sha256':'a'*64,
            'source_reference':'SYNTHETIC_EXISTING_DECISION','statement':'Accept existing holdings',
            'recorded_at':'2026-10-03T00:00:00Z'}
        self.new=deepcopy(self.old);self.new['source_sha256']='b'*64
        self.new['tables']['final_target_version']=[{'version_no':1}]
        self.new['tables']['portfolio_account'][0]['account_label']='translated label'
        self.new['payload_digest']=digest(self.new['tables'])

    def bind(self):
        return A.bind_official_holdings(self.new,previous_snapshot=self.old,
            official_file_id='synthetic-official-db',account_key='IB',owner_decision=self.decision,
            evaluation_at='2026-10-28T00:00:00Z')

    def test_original_decision_is_not_resigned_for_new_db(self):
        proof=self.bind()
        self.assertEqual(proof['source_db_sha256'],'b'*64)
        self.assertEqual(proof['owner_decision'],self.decision)
        self.assertEqual(proof['owner_decision']['source_db_sha256'],'a'*64)
        self.assertFalse(proof['snapshot_rebinding']['new_owner_approval_asserted'])

    def test_changed_sealed_source_or_new_quantity_or_identity_rejected(self):
        for kind in ('sealed','quantity','identity','added'):
            with self.subTest(kind=kind):
                saved=deepcopy(self.new)
                if kind=='sealed':self.new['tables']['portfolio_snapshot_item'][0]['value_text']='[]'
                elif kind=='identity':self.new['tables']['portfolio_instrument'][0]['quote_currency']='TWD'
                else:
                    row=deepcopy(self.new['tables']['portfolio_position'][0])
                    row.update(as_of_utc='2026-10-10T00:00:00Z',quantity_decimal='3',position_source_kind='OWNER_VERIFIED')
                    if kind=='added':
                        row['instrument_key']='Y'
                        self.new['tables']['portfolio_instrument'].append({'instrument_key':'Y','ticker':'BBB'})
                    self.new['tables']['portfolio_position'].append(row)
                self.new['payload_digest']=digest(self.new['tables'])
                with self.assertRaises(PermissionError):self.bind()
                self.new=saved


if __name__=='__main__':unittest.main()
