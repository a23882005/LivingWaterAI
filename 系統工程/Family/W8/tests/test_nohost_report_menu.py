"""No-host W7/W8 report menu integration. All member data synthetic."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util
import unittest
import hashlib
import sqlite3

HERE=Path(__file__).resolve().parent
W8=HERE.parent
FAMILY=W8.parent

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

MENU=load(FAMILY/"W7"/"family_menu.py","w7_no_host_menu")
PROJECT=load(W8/"on_demand_project.py","w8_no_host_project")
READER=load(FAMILY/"W5"/"family_input.py","w5_reader_no_host")

CLIENT="fam_"+"a"*32


class Auth:
    user_id="JO"
    client_id=CLIENT
    active=False
    def login(self,password):
        if password!="testpass":raise PermissionError()
        self.active=True
    def require_login(self):
        if not self.active:raise PermissionError()
        return self.user_id
    def logout(self):
        self.active=False


class NoHostReportMenus(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.auth=Auth()
        self.db=Path(self.temp.name)/"source.db"
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE family_member_identity (client_id TEXT,family_alias TEXT)")
            db.execute("INSERT INTO family_member_identity VALUES(?,?)",(CLIENT,"Joseph"))
            for table in READER.TABLES:
                db.execute('CREATE TABLE "'+table+'" (client_id TEXT)')
        self.sha=hashlib.sha256(self.db.read_bytes()).hexdigest()

    def menu(self,**options):
        return PROJECT.build_project_menu(
            family_login=self.auth,project_name="Joseph",
            login_account="JO",client_id=CLIENT,family_alias="Joseph",
            downloaded_db_path=self.db,
            official_drive_file_id="unit_approved_id",
            verified_drive_sha256=self.sha,
            official_report_folder_id="unit_approved_folder",
            **options
        )

    def test_previous_report_triggers_tool_lookup(self):
        menu=self.menu()
        menu.login("testpass")
        out=menu.select(12)
        self.assertEqual(out["status"],"REPORT_LOOKUP_REQUIRED")
        self.assertEqual(out["result"]["folder_id"],"unit_approved_folder")
        self.assertEqual(out["result"]["trade_authorization"],"NONE")

    def test_report_not_connected_is_not_false_success(self):
        menu=self.menu()
        menu.login("testpass")
        self.assertEqual(menu.select(13)["status"],"HANDLER_PENDING")

    def test_generator_prepares_not_publishes(self):
        # Patch only the W6 renderer for a routing test. Real W6 rendering is
        # independently tested against the approved pinned ZIP.
        actual_load=PROJECT._load
        def fake_load(path,name):
            if path.name=="on_demand_w6.py":
                class MockW6:
                    def __init__(self,*a,**kw):pass
                    def __call__(self,src,payload):
                        return {"qa_passed":True,
                            "renderer_contract":"Family.W6.v16.parameterized",
                            "client_id":CLIENT,"run_id":"r001",
                            "source_db_sha256":src["source_db_sha256"],
                            "source_digest":src["digest"],"w6_current_digest":"a"*64,
                            "data_as_of":"2026-10-26T11:00:00Z",
                            "analysis_version":"W6-v16",
                            "artifacts":{"report.pdf":b"%PDF-1.4 test",
                                         "index.html":b"<!doctype html>test"}}
                return SimpleNamespace(OnDemandW6Renderer=MockW6)
            return actual_load(path,name)
        with patch.object(PROJECT,"_load",side_effect=fake_load):
            menu=self.menu(
                trusted_w6_current_input_producer=lambda *a: None,
                approved_w6_renderer=lambda *a: None,
                report_staging_dir=self.temp.name)
            menu.login("testpass")
            result=menu.select(13)
        self.assertEqual(result["status"],"REPORT_UPLOAD_REQUIRED")
        self.assertEqual(result["result"]["status"],"STAGED_NOT_PERSISTED")
        self.assertTrue(all(Path(item["path"]).exists()
                            for item in result["result"]["uploads"]))


if __name__=="__main__":
    unittest.main()
