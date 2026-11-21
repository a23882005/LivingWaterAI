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

    def test_member_report_13_names_missing_operator_inputs(self):
        config={"client_id":CLIENT,"source_db_sha256":self.sha,"repo_root":str(FAMILY.parent.parent)}
        import sys
        with patch.object(sys,"path",[str(W8),str(FAMILY/"W5"),*sys.path]):
            menu=self.menu(member_v82_source_config=config,report_staging_dir=self.temp.name)
        self.assertEqual(menu.select(13)["status"],"LOGIN_REQUIRED")
        out=menu.login("testpass")
        self.assertEqual(out["status"],"REPORT_INPUTS_REQUIRED")
        self.assertEqual(out["result"]["missing"],["trusted_w6_current_input_producer","approved_w6_archive_or_renderer"])

    def test_member_report_receiver_requires_a_verified_run_in_this_login(self):
        config={"client_id":CLIENT,"source_db_sha256":self.sha,"repo_root":str(FAMILY.parent.parent)}
        def receiver(*args, **kwargs):
            self.fail("Menu13 invoked its receiver without a verified Menu04")
        menu=self.menu(member_v82_source_config=config,report_staging_dir=self.temp.name,
                       trusted_member_w6_receiver=receiver,approved_w6_renderer=lambda _:None)
        self.assertEqual(menu.select(13)["status"],"LOGIN_REQUIRED")
        out=menu.login("testpass")
        self.assertEqual(out["status"],"REPORT_INPUTS_REQUIRED")
        self.assertEqual(out["result"]["missing"],["same_session_verified_menu04_run"])

    def test_member_report_12_reads_and_verifies_only_own_archive(self):
        import json
        folder="unit_approved_folder";mid="approved_manifest";data=b"one verified artifact"
        stem="Joseph_配置報告_20261103_081347_TW"
        files=[{"id":ext,"name":stem+"."+ext,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()} for ext in ("pdf","html")]
        manifest={"schema":"Family.W8.ReportArchive.v1","state":"COMPLETE","account":"JO","client_id":CLIENT,
                  "folder_id":folder,"created_at":"2026-11-03T08:13:47+08:00","run_id":"prior","files":files}
        metadata={f["id"]:{"id":f["id"],"name":f["name"],"parents":[folder],"shared":False}
                  for f in [*files,{"id":mid,"name":stem+".manifest.json"}]}
        calls=[]
        def read(lookup):
            calls.append(lookup)
            return {"manifest_file_id":mid,"manifest_bytes":json.dumps(manifest).encode(),
                    "readbacks":{f["id"]:data for f in files},"file_metadata":metadata}
        menu=self.menu(trusted_report_archive_reader=read)
        self.assertEqual(menu.select(12)["status"],"LOGIN_REQUIRED")
        self.assertEqual(calls,[])
        result=menu.login("testpass")
        self.assertEqual(result["result"]["status"],"REPORT_LOOKUP_REMOTE_VERIFIED")
        self.assertEqual(calls[0]["folder_id"],folder)
        metadata["pdf"]["parents"]=["wrong_folder"]
        with self.assertRaisesRegex(PermissionError,"PRIVATE_PARENT"):
            menu.select(12)
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
        html_plan=result["result"]["html_imports"]["index.html"]
        self.assertEqual(html_plan["status"],"HTML_IMPORT_READY_NOT_PERSISTED")
        self.assertEqual(html_plan["tool"],"mcp__Google_Drive__import_document")
        self.assertEqual(html_plan["import_args"]["upload_mode"],"keep_source_file_type")
        self.assertEqual(html_plan["import_args"]["parent_folder_id"],
                         "unit_approved_folder")
        self.assertTrue(Path(html_plan["import_args"]["source_file"]).is_file())
        self.assertNotIn("report.pdf",result["result"]["html_imports"])
        self.assertNotEqual(result["result"]["status"],"PERSISTED_REMOTE_VERIFIED")


if __name__=="__main__":
    unittest.main()
