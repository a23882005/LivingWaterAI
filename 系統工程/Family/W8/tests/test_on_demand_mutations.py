"""W8 01/03/06/10/11 one-shot stage integration tests; all SQLite synthetic."""
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

FAMILY=Path(__file__).resolve().parents[2]
W8=FAMILY/"W8"
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

MUT=load(W8/"on_demand_mutations.py","w8_stage_mutation_test")
MENU=load(FAMILY/"W7"/"family_menu.py","w8_stage_menu_test")
CLIENT="fam_"+"a"*32

class Auth:
    def require_login(self):return "JO"

def seed(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE family_member_identity(client_id TEXT, family_alias TEXT);
        CREATE TABLE portfolio_instrument(client_id TEXT,instrument_key TEXT);
        CREATE TABLE final_target_version(
          client_id TEXT,target_key TEXT,version_no INTEGER,previous_version_no INTEGER,
          lifecycle_state TEXT,completeness_state TEXT,origin_kind TEXT,
          origin_source_kind TEXT,origin_source_ref TEXT,created_at_utc TEXT,
          confirmed_by TEXT,confirmation_source_kind TEXT,
          confirmation_source_ref TEXT,confirmed_at_utc TEXT);
        CREATE TABLE final_target_allocation(
          client_id TEXT,target_key TEXT,version_no INTEGER,instrument_key TEXT,
          weight_units INTEGER,allocation_state TEXT,
          allocation_source_kind TEXT,allocation_source_ref TEXT,created_at_utc TEXT);
        """)
        db.execute("INSERT INTO family_member_identity VALUES(?,?)",(CLIENT,"Joseph"))
        db.execute("INSERT INTO portfolio_instrument VALUES(?,?)",(CLIENT,"VT"))

class MutationStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.source=root/"official_download.db"
        seed(self.source)
        self.original_sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.stager=MUT.OnDemandMutationStager(
            auth=Auth(),login_account="JO",client_id=CLIENT,
            family_alias="Joseph",official_drive_file_id="synthetic_joseph_file",
            downloaded_db_path=self.source,verified_drive_sha256=self.original_sha,
            staging_dir=root)

    def payload(self, confirmed=True):
        return {
            "request_id":"case_1","owner_confirmed":confirmed,
            "record":{
                "confirmed":True,
                "source_reference":"OWNER_CONFIRM_20261027",
                "allocations":[{"instrument_key":"VT","weight":"1"}]
            }
        }

    def test_staged_target_is_not_officially_saved(self):
        p=self.stager.stage("adjust_target",self.payload())
        self.assertEqual(p["status"],"STAGED_NOT_PERSISTED")
        self.assertEqual(p["business_result"]["version"],1)
        self.assertEqual(p["writeback_plan"]["source"]["sha256"],self.original_sha)
        candidate=p["writeback_plan"]["candidate"]["path"]
        with sqlite3.connect(candidate) as db:
            v=db.execute("SELECT lifecycle_state FROM final_target_version").fetchone()
            self.assertEqual(v,("CONFIRMED",))
        with sqlite3.connect(self.source) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM final_target_version").fetchone(),(0,))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.original_sha)

    def test_no_owner_confirmation_means_no_staged_files(self):
        with self.assertRaisesRegex(ValueError,"OWNER_CONFIRMED_MUTATION_REQUIRED"):
            self.stager.stage("adjust_target",self.payload(confirmed=False))
        with sqlite3.connect(self.source) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM final_target_version").fetchone(),(0,))

    def test_foreign_family_denied(self):
        stager=MUT.OnDemandMutationStager(
            auth=Auth(),login_account="AR",client_id=CLIENT,
            family_alias="Arthur",official_drive_file_id="synthetic_other",
            downloaded_db_path=self.source,verified_drive_sha256=self.original_sha,
            staging_dir=self.temp.name)
        with self.assertRaisesRegex(PermissionError,"FAMILY_PROJECT_ACCOUNT_MISMATCH"):
            stager.stage("adjust_target",self.payload())

    def test_unknown_source_sha_refused(self):
        self.stager.source_sha="0"*64
        with self.assertRaisesRegex(RuntimeError,"OFFICIAL_DB_SOURCE_CHANGED"):
            self.stager.stage("adjust_target",self.payload())

    def test_existing_w7_menu_returns_writeback_required(self):
        handlers=MUT.mutation_handlers(self.stager)
        menu=MENU.FamilyMenu(Auth(),project_name="Joseph",login_account="JO",
                              handlers=handlers)
        result=menu.select(3,payload=self.payload())
        self.assertEqual(result["status"],"DB_WRITEBACK_REQUIRED")
        self.assertEqual(result["pending_operation"],"adjust_target")
        self.assertEqual(result["result"]["status"],"STAGED_NOT_PERSISTED")

    def test_all_five_mutation_routes_are_bound(self):
        self.assertEqual(set(MUT.mutation_handlers(self.stager)),set(MUT.OPERATIONS))

if __name__ == "__main__":
    unittest.main()
