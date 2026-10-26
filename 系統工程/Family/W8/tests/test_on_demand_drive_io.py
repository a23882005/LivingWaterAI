import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from on_demand_drive_io import Binding, OnDemandWriteback, inspect, seal_working_copy

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.binding=Binding('AR','fam_'+'a'*32,'synthetic-original','Arthur')
        self.io=OnDemandWriteback(self.binding,lambda:'AR')
        self.original=self.root/'original.db'
        with sqlite3.connect(self.original) as c:
            c.executescript('CREATE TABLE family_member_identity(client_id TEXT,family_alias TEXT); CREATE TABLE values_test(n INTEGER);')
            c.execute('INSERT INTO family_member_identity VALUES(?,?)',(self.binding.client_id,'Arthur'))
            c.execute('INSERT INTO values_test VALUES(1)')
        self.candidate=self.root/'candidate.db';shutil.copyfile(self.original,self.candidate)
        with sqlite3.connect(self.candidate) as c:c.execute('UPDATE values_test SET n=2')
        self.plan=self.io.prepare(self.original,self.candidate)
        self.fresh=self.root/'fresh.db';self.backup=self.root/'backup.db';self.remote=self.root/'remote.db'
        shutil.copyfile(self.original,self.fresh);shutil.copyfile(self.original,self.backup);shutil.copyfile(self.candidate,self.remote)
        self.checks=[('SELECT n FROM values_test',(),[(2,)])]
    def tearDown(self):self.tmp.cleanup()
    def test_happy(self):
        uri='sediment://file_unit_generated_artifact'
        args=self.io.authorize_update(self.plan,self.fresh,self.backup,
                                      'synthetic-backup',candidate_file_uri=uri)
        self.assertEqual(args['update_file_args']['file_uri'],uri)
        self.assertEqual(args['status'],'READY_NOT_PERSISTED')
        self.assertEqual(self.io.verify_readback(self.plan,self.remote,'synthetic-original',self.checks)['status'],'PERSISTED_REMOTE_VERIFIED')
    def test_local_path_cannot_be_used_as_connector_uri(self):
        with self.assertRaisesRegex(ValueError,'VALID_CONNECTOR_FILE_URI_REQUIRED'):
            self.io.authorize_update(self.plan,self.fresh,self.backup,
                                     'synthetic-backup',candidate_file_uri=str(self.candidate))
    def test_missing_artifact_reference_is_not_ready_to_write(self):
        waiting=self.io.authorize_update(self.plan,self.fresh,self.backup,'synthetic-backup')
        self.assertEqual(waiting['status'],'CONNECTOR_FILE_REFERENCE_REQUIRED')
        self.assertNotIn('update_file_args',waiting)
        self.assertEqual(waiting['candidate_sha256'],self.plan['candidate']['sha256'])
    def test_four_accounts(self):
        for name in ('MOU','JO','AR','LI'):Binding(name,'fam_'+'a'*32,'synthetic-'+name,name)
    def test_wrong_login(self):
        with self.assertRaises(PermissionError):OnDemandWriteback(self.binding,lambda:'JO').prepare(self.original,self.candidate)
    def test_wrong_identity(self):
        with self.assertRaises(PermissionError):inspect(self.original,Binding('JO','fam_'+'b'*32,'synthetic-other','Joseph'))
    def test_stale_source(self):
        shutil.copyfile(self.candidate,self.fresh)
        with self.assertRaises(RuntimeError):self.io.authorize_update(self.plan,self.fresh,self.backup,'backup')
    def test_wrong_backup(self):
        shutil.copyfile(self.candidate,self.backup)
        with self.assertRaises(RuntimeError):self.io.authorize_update(self.plan,self.fresh,self.backup,'backup')
    def test_no_backup(self):
        with self.assertRaises(ValueError):self.io.authorize_update(self.plan,self.fresh,self.backup,self.binding.file_id)
    def test_changed_candidate(self):
        with sqlite3.connect(self.candidate) as c:c.execute('UPDATE values_test SET n=3')
        with self.assertRaises(ValueError):self.io.authorize_update(self.plan,self.fresh,self.backup,'backup')
    def test_remote_wrong_id(self):
        with self.assertRaises(PermissionError):self.io.verify_readback(self.plan,self.remote,'wrong',self.checks)
    def test_remote_wrong_hash(self):
        shutil.copyfile(self.original,self.remote)
        with self.assertRaises(RuntimeError):self.io.verify_readback(self.plan,self.remote,self.binding.file_id,self.checks)
    def test_remote_wrong_fields(self):
        with self.assertRaises(ValueError):self.io.verify_readback(self.plan,self.remote,self.binding.file_id,[('SELECT n FROM values_test',(),[(3,)])])
    def test_no_fields(self):
        with self.assertRaises(ValueError):self.io.verify_readback(self.plan,self.remote,self.binding.file_id,[])
    def test_local_is_not_remote(self):
        with self.assertRaises(ValueError):self.io.verify_readback(self.plan,self.candidate,self.binding.file_id,self.checks)
    def test_wal_rejected(self):
        Path(str(self.candidate)+'-wal').write_bytes(b'pending')
        with self.assertRaises(ValueError):inspect(self.candidate,self.binding)
    def test_seal_includes_wal(self):
        c=sqlite3.connect(self.candidate);c.execute('PRAGMA journal_mode=WAL');c.execute('UPDATE values_test SET n=4');c.commit()
        out=self.root/'sealed.db';seal_working_copy(self.candidate,out)
        with sqlite3.connect(out) as d:self.assertEqual(d.execute('SELECT n FROM values_test').fetchone(),(4,))
        inspect(out,self.binding);c.close()
    def test_bad_sqlite(self):
        self.remote.write_bytes(b'not sqlite')
        with self.assertRaises(ValueError):inspect(self.remote,self.binding)

if __name__=='__main__':unittest.main()
