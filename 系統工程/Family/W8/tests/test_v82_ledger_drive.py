"""Isolated planning-resource transport; never real orders or client budgets."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json,sqlite3,shutil,sys,unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from on_demand_drive_io import Binding,digest,seal_working_copy
from v82_ledger_drive import create_resource,inspect_ledger,stage_sync,LedgerWriteback,register_reference,read_reference,resolve_resource,cycle_snapshot
from formal_mode_analysis import native
native(ROOT)
from livingwater_v82_runtime.daily_slice import CycleLedgerStore,open_cycle,update_intent,speed,maturity


class LedgerDriveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.client='fam_'+'a'*32;self.member=Binding('AR',self.client,'SYNTHETIC_MEMBER_FILE','Arthur')
        self.binding=Binding('AR',self.client,'SYNTHETIC_LEDGER_FILE','Arthur')
        self.member_db=self.root/'member.db'
        with sqlite3.connect(self.member_db) as db:
            db.execute('CREATE TABLE family_member_identity(client_id TEXT PRIMARY KEY,family_alias TEXT)')
            db.execute('INSERT INTO family_member_identity VALUES (?,?)',(self.client,'Arthur'))
            db.execute('CREATE TABLE portfolio_account(client_id TEXT,account_key TEXT)')
            db.execute('INSERT INTO portfolio_account VALUES (?,?)',(self.client,'SYNTHETIC_US'))
        self.original=self.root/'original.db'
        create_resource(self.member_db,self.original,self.member,lambda:'AR',authority='SYNTHETIC_OWNER_AUTHORITY',created_at='2026-10-30T00:00:00Z')
        self.working=self.root/'working.db';seal_working_copy(self.original,self.working)
        self.owner={'client_id':self.client,'funding_domain':'US_BROKER','broker':'SYNTHETIC_BROKER',
                    'account':'SYNTHETIC_US','currency':'USD'}
        self.rates=speed(mode='Left Overweight',maturity_result=maturity([
            {'id':'M'+str(i),'truth':'TRUE' if i<=3 else 'FALSE'} for i in range(1,9)]),
            credit_level=0,core_etf='TRUE',high_beta='FALSE',macro_pressure='FALSE',extreme_valuation='OFF')
        self.io=LedgerWriteback(self.binding,lambda:'AR')

    def cycle(self,owner=None):
        return open_cycle(owner=owner or self.owner,session_id='2026-10-30',exchange='SYNTHETIC_EXCHANGE',
            asset_id='SYNTHETIC_ASSET',opened_at='2026-10-30T00:01:00Z',gap='100',speed_result=self.rates,
            permission=True,exposure_reconciled=True,session_open=True)

    def event(self,cycle,state='OPEN',filled='0',remaining='25',event='OPEN',release=False):
        return update_intent(cycle,event_id=event,intent_id='SYNTHETIC_INTENT',state=state,
            filled_amount=filled,remaining_amount=remaining,receipt={'owner':cycle['owner'],'asset_id':cycle['asset_id'],
            'source_reference':'SYNTHETIC_EVENT','source_hash':'a'*64,'as_of':'2026-10-30T00:02:00Z',
            'available_at':'2026-10-30T00:02:00Z','release_confirmed':release},evaluation_at='2026-10-30T00:03:00Z',
            speed_result=self.rates,permission=True,session_id='2026-10-30',session_open=True)

    def candidate(self):
        target=self.root/'candidate.db'
        stage_sync(self.original,self.working,target,self.binding,updated_at='2026-10-30T00:04:00Z')
        return target

    def copies(self,candidate):
        fresh=self.root/'fresh.db';backup=self.root/'backup.db';remote=self.root/'new_environment.db'
        shutil.copyfile(self.original,fresh);shutil.copyfile(self.original,backup);shutil.copyfile(candidate,remote)
        return fresh,backup,remote

    def test_initial_resource_asserts_neither_cycle_nor_empty_broker_orders(self):
        info=inspect_ledger(self.original,self.binding)
        self.assertEqual(info['cycle_count'],0);self.assertFalse(info['financial_cycle_initialized'])
        self.assertFalse(info['broker_orders_complete_asserted'])
        self.assertFalse(info['cycles']);self.assertEqual(info['header']['sync_revision'],0)

    def descriptor(self):
        return {'file_id':self.binding.file_id,'source_reference':'drive:'+self.binding.file_id,
            'downloaded_from_drive':True,'retrieved_at':'2026-10-30T00:01:00Z',
            'local_path':str(self.original),'sha256':digest(self.original)}

    def register(self):
        return register_reference(self.member_db,self.member,self.original,self.binding.file_id,
            authority='SYNTHETIC_OWNER',verified_at='2026-10-30T00:01:00Z')

    def test_registered_source_requires_new_download_not_creation_hash(self):
        self.assertEqual(resolve_resource(self.member_db,self.member,None,evaluation_at='2026-10-30T00:03:00Z')['status'],
            'MEMBER_LEDGER_NOT_REGISTERED')
        with self.assertRaisesRegex(PermissionError,'UNREGISTERED'):
            resolve_resource(self.member_db,self.member,self.descriptor(),evaluation_at='2026-10-30T00:03:00Z')
        self.register()
        self.assertEqual(resolve_resource(self.member_db,self.member,None,evaluation_at='2026-10-30T00:03:00Z')['status'],
            'REGISTERED_LEDGER_FRESH_DOWNLOAD_REQUIRED')
        resource=resolve_resource(self.member_db,self.member,self.descriptor(),evaluation_at='2026-10-30T00:03:00Z')
        self.assertEqual(resource['cycle_count'],0)
        out=cycle_snapshot(resource,owner=self.owner,asset_id='SYNTHETIC_ASSET',exchange='SYNTHETIC_EXCHANGE',session_id='2026-10-30')
        self.assertIsNone(out['cycle']);self.assertEqual(out['status'],'QUALIFIED_GAP_REQUIRED_FOR_CYCLE_INITIALIZATION')

    def test_registered_download_scope_hash_and_future_cutoff_are_enforced(self):
        self.register()
        for change in ({'file_id':'SYNTHETIC_OTHER'}, {'source_reference':'drive:OTHER'},
                       {'sha256':'0'*64},{'downloaded_from_drive':False},{'retrieved_at':'2026-10-31T00:01:00Z'}):
            with self.subTest(change=change),self.assertRaises(PermissionError):
                resolve_resource(self.member_db,self.member,self.descriptor()|change,evaluation_at='2026-10-30T00:03:00Z')

    def test_exact_registered_cycle_lookup_and_foreign_owner_rejection(self):
        cycle=self.event(self.cycle());CycleLedgerStore(self.original).save(cycle,expected_revision=None)
        self.register()
        resource=resolve_resource(self.member_db,self.member,self.descriptor(),evaluation_at='2026-10-30T00:03:00Z')
        args={'asset_id':'SYNTHETIC_ASSET','exchange':'SYNTHETIC_EXCHANGE','session_id':'2026-10-30'}
        self.assertEqual(cycle_snapshot(resource,owner=self.owner,**args)['cycle'],cycle)
        self.assertIsNone(cycle_snapshot(resource,owner=self.owner,**(args|{'session_id':'2026-11-02'}))['cycle'])
        with self.assertRaises(PermissionError):cycle_snapshot(resource,owner=self.owner|{'client_id':'fam_'+'b'*32},**args)

    def test_creation_never_overwrites_a_file(self):
        before=self.original.read_bytes()
        with self.assertRaises(FileExistsError):
            create_resource(self.member_db,self.original,self.member,lambda:'AR',authority='SYNTHETIC',created_at='2026-10-30T00:00:00Z')
        self.assertEqual(self.original.read_bytes(),before)

    def test_wrong_login_and_missing_creation_authority_are_rejected(self):
        with self.assertRaises(PermissionError):
            create_resource(self.member_db,self.root/'bad.db',self.member,lambda:'JO',authority='SYNTHETIC',created_at='2026-10-30T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'AUTHORITY_REQUIRED'):
            create_resource(self.member_db,self.root/'bad.db',self.member,lambda:'AR',authority='',created_at='2026-10-30T00:00:00Z')

    def test_sequential_original_id_backup_and_fresh_environment_readback(self):
        cycle=self.event(self.cycle());CycleLedgerStore(self.working).save(cycle,expected_revision=None)
        candidate=self.candidate();plan=self.io.prepare(self.original,candidate);fresh,backup,remote=self.copies(candidate)
        ready=self.io.authorize_update(plan,fresh,backup,'SYNTHETIC_BACKUP',serialized_writer=True,
                                      candidate_file_uri=str(candidate),local_upload_supported=True)
        self.assertEqual(ready['update_file_args']['fileId'],self.binding.file_id)
        self.assertFalse(ready['distributed_remote_cas_provided'])
        receipt=self.io.verify_readback(plan,remote,self.binding.file_id)
        self.assertEqual(receipt['status'],'PERSISTED_REMOTE_VERIFIED');self.assertEqual(receipt['cycle_count'],1)
        restored=CycleLedgerStore(remote).get(cycle['slice_cycle_id'])
        self.assertEqual(restored,cycle);self.assertEqual(restored['G0'],'100')
        self.assertEqual(restored['B0'],'25.00');self.assertEqual(restored['intents']['SYNTHETIC_INTENT']['remaining_amount'],'25')

    def test_serialization_is_required_and_preflight_is_not_persistence(self):
        candidate=self.candidate();plan=self.io.prepare(self.original,candidate);fresh,backup,_=self.copies(candidate)
        with self.assertRaisesRegex(PermissionError,'SERIALIZED_WRITER_REQUIRED'):
            self.io.authorize_update(plan,fresh,backup,'SYNTHETIC_BACKUP')
        ready=self.io.authorize_update(plan,fresh,backup,'SYNTHETIC_BACKUP',serialized_writer=True)
        self.assertEqual(ready['status'],'CONNECTOR_FILE_REFERENCE_REQUIRED')

    def test_member_database_cannot_be_used_as_the_ledger(self):
        with self.assertRaisesRegex(ValueError,'TABLE_SET_MISMATCH'):inspect_ledger(self.member_db,self.member)

    def test_ledger_binding_cannot_target_original_member_database_id(self):
        candidate=self.candidate()
        with self.assertRaisesRegex(PermissionError,'MUST_NOT_OVERWRITE_MEMBER_DB'):
            LedgerWriteback(self.member,lambda:'AR').prepare(self.original,candidate)

    def test_foreign_client_cycle_is_rejected(self):
        owner={**self.owner,'client_id':'fam_'+'b'*32};cycle=self.cycle(owner)
        CycleLedgerStore(self.working).save(cycle,expected_revision=None)
        with self.assertRaisesRegex(PermissionError,'OWNER_ACCOUNT_MISMATCH'):inspect_ledger(self.working,self.binding)

    def test_unknown_account_cycle_is_rejected(self):
        cycle=self.cycle({**self.owner,'account':'SYNTHETIC_OTHER_ACCOUNT'})
        CycleLedgerStore(self.working).save(cycle,expected_revision=None)
        with self.assertRaisesRegex(PermissionError,'OWNER_ACCOUNT_MISMATCH'):inspect_ledger(self.working,self.binding)

    def test_direct_sqlite_pending_shrink_cannot_bypass_native_save_guard(self):
        old=self.event(self.cycle());CycleLedgerStore(self.original).save(old,expected_revision=None)
        shutil.copyfile(self.original,self.working);changed=deepcopy(old);changed['revision']+=1
        changed['intents']['SYNTHETIC_INTENT'].update(state='CANCEL_PENDING',remaining_amount='0')
        with sqlite3.connect(self.working) as db:
            db.execute('UPDATE cycles SET revision=?,payload=?',(changed['revision'],json.dumps(changed)))
        candidate=self.candidate()
        with self.assertRaisesRegex(ValueError,'UNCONFIRMED_COMMITMENT_REDUCTION'):self.io.prepare(self.original,candidate)

    def test_initial_gap_and_budget_cannot_be_reset_by_a_candidate(self):
        old=self.cycle();CycleLedgerStore(self.original).save(old,expected_revision=None)
        shutil.copyfile(self.original,self.working);changed=deepcopy(old);changed.update(G0='200',B0='50.00',revision=1)
        with sqlite3.connect(self.working) as db:db.execute('UPDATE cycles SET revision=1,payload=?',(json.dumps(changed),))
        with self.assertRaisesRegex(ValueError,'INITIAL_FACTS_IMMUTABLE'):self.io.prepare(self.original,self.candidate())

    def test_history_cannot_be_deleted(self):
        old=self.cycle();CycleLedgerStore(self.original).save(old,expected_revision=None)
        shutil.copyfile(self.original,self.working)
        with sqlite3.connect(self.working) as db:db.execute('DELETE FROM cycles')
        with self.assertRaisesRegex(ValueError,'HISTORY_CANNOT_BE_DELETED'):self.io.prepare(self.original,self.candidate())

    def test_index_corruption_is_rejected(self):
        old=self.event(self.cycle());CycleLedgerStore(self.working).save(old,expected_revision=None)
        with sqlite3.connect(self.working) as db:db.execute('DELETE FROM intent_owner')
        with self.assertRaisesRegex(ValueError,'INTENT_INDEX_MISMATCH'):inspect_ledger(self.working,self.binding)

    def test_source_lineage_mismatch_is_rejected(self):
        candidate=self.candidate()
        with sqlite3.connect(candidate) as db:db.execute('UPDATE v82_ledger_resource SET parent_sha256=?',('f'*64,))
        with self.assertRaisesRegex(ValueError,'SOURCE_REVISION_CONFLICT'):self.io.prepare(self.original,candidate)

    def test_stale_backup_and_wrong_remote_id_cannot_be_accepted(self):
        candidate=self.candidate();plan=self.io.prepare(self.original,candidate);fresh,backup,remote=self.copies(candidate)
        shutil.copyfile(candidate,fresh)
        with self.assertRaisesRegex(RuntimeError,'STALE_SOURCE_OR_BACKUP'):
            self.io.authorize_update(plan,fresh,backup,'SYNTHETIC_BACKUP',serialized_writer=True,
                candidate_file_uri=str(candidate),local_upload_supported=True)
        with self.assertRaisesRegex(PermissionError,'REMOTE_ID_CHANGED'):self.io.verify_readback(plan,remote,'WRONG')

    def test_member_pointer_is_staged_idempotently_without_changing_original(self):
        before=digest(self.member_db);copy=self.root/'member_candidate.db';shutil.copyfile(self.member_db,copy)
        ref=register_reference(copy,self.member,self.original,self.binding.file_id,authority='SYNTHETIC',verified_at='2026-10-30T00:04:00Z')
        self.assertEqual(ref['file_id'],self.binding.file_id);self.assertTrue(ref['requires_fresh_drive_read'])
        self.assertFalse(ref['ledger_current_sha256_asserted']);self.assertIsNone(read_reference(self.member_db,self.member))
        self.assertEqual(before,digest(self.member_db))
        again=register_reference(copy,self.member,self.original,self.binding.file_id,authority='SYNTHETIC',verified_at='2026-10-30T00:05:00Z')
        self.assertEqual(again,ref)
        with self.assertRaisesRegex(PermissionError,'ALREADY_BOUND'):
            register_reference(copy,self.member,self.original,'SYNTHETIC_DIFFERENT_LEDGER',authority='SYNTHETIC',verified_at='2026-10-30T00:05:00Z')


if __name__=='__main__':unittest.main()
