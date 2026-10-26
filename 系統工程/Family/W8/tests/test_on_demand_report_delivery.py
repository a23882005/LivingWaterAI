"""No-host Family W8 Drive report delivery: synthetic artifact tests."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import importlib.util
import unittest

P = Path(__file__).resolve().parents[1] / "on_demand_report_delivery.py"
spec = importlib.util.spec_from_file_location("w8_report_delivery_test", P)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

CLIENT = "fam_" + "a"*32
FOLDER = "test_report_folder_id"

def fake_rendered():
    return {
        "qa_passed": True, "renderer_contract": "Family.W6.v16.parameterized",
        "client_id": CLIENT, "run_id": "unit-run",
        "source_db_sha256": "b"*64, "source_digest": "c"*64,
        "w6_current_digest": "d"*64,
        "data_as_of": "2026-10-26T11:00:00Z", "analysis_version": "W6-v16",
        "artifacts": {
            "report.pdf": b"%PDF-1.4 synthetic\n",
            "index.html": b"<!doctype html><title>synthetic</title>",
            "report.html": b"<html>synthetic</html>",
        },
    }


class ReportDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.dir = TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def plan(self, **changes):
        raw = fake_rendered()
        raw.update(changes)
        return M.prepare_report_delivery(
            raw, account="JO", client_id=CLIENT, folder_id=FOLDER,
            output_dir=self.dir.name, created_at=datetime(2026,10,26,3,0,tzinfo=timezone.utc))

    def complete_artifacts(self, plan):
        receipts = []
        remote = {}
        for i, item in enumerate(plan["uploads"]):
            file_id = "valid_remote_" + str(i)
            receipts.append({"success": True, "id": file_id,
                             "name": item["name"], "parent_id": FOLDER})
            remote[file_id] = Path(item["path"]).read_bytes()
        return receipts, remote

    def test_complete_upload_readback_and_manifest(self):
        plan = self.plan()
        self.assertEqual(plan["status"],"STAGED_NOT_PERSISTED")
        self.assertTrue(all("Joseph_配置報告_20261026_110000_TW" in x["name"]
                            for x in plan["uploads"]))
        receipts,remote = self.complete_artifacts(plan)
        manifest = M.prepare_verified_manifest(plan,receipts,remote)
        self.assertEqual(manifest["status"],"ARTIFACTS_REMOTE_VERIFIED__MANIFEST_PENDING")
        result = M.verify_published_manifest(
            manifest,{"success":True,"name":manifest["manifest_filename"],
                      "id":"manifest_id","parent_id":FOLDER}, manifest["manifest_bytes"])
        self.assertEqual(result["status"],"PERSISTED_REMOTE_VERIFIED")

    def test_cross_family_report_rejected(self):
        with self.assertRaisesRegex(ValueError,"W6_QA_AND_MEMBER_REQUIRED"):
            self.plan(client_id="fam_"+"b"*32)

    def test_artifact_changed_on_drive_rejected(self):
        plan = self.plan()
        receipts,remote = self.complete_artifacts(plan)
        remote[receipts[0]["id"]] = b"tampered"
        with self.assertRaisesRegex(RuntimeError,"REPORT_REMOTE_ARTIFACT_READBACK_FAILED"):
            M.prepare_verified_manifest(plan,receipts,remote)

    def test_wrong_remote_parent_rejected(self):
        plan = self.plan()
        receipts,remote = self.complete_artifacts(plan)
        receipts[0]["parent_id"] = "another_member_folder"
        with self.assertRaisesRegex(PermissionError,"REPORT_REMOTE_FOLDER_OR_RECEIPT_MISMATCH"):
            M.prepare_verified_manifest(plan,receipts,remote)

    def test_manifest_not_uploaded_not_complete(self):
        plan = self.plan()
        receipts,remote = self.complete_artifacts(plan)
        manifest = M.prepare_verified_manifest(plan,receipts,remote)
        with self.assertRaisesRegex(PermissionError,"REPORT_MANIFEST_REMOTE_RECEIPT_MISMATCH"):
            M.verify_published_manifest(manifest,{"success":False},manifest["manifest_bytes"])

    def test_collision_does_not_overwrite_report(self):
        self.plan()
        with self.assertRaisesRegex(FileExistsError,"REPORT_STAGE_COLLISION"):
            self.plan()

    def test_bad_pdf_blocks_stage(self):
        bad = fake_rendered()
        bad["artifacts"]["report.pdf"] = b"not pdf"
        with self.assertRaisesRegex(ValueError,"W6_PDF_INVALID"):
            M.prepare_report_delivery(bad,account="JO",client_id=CLIENT,
                 folder_id=FOLDER,output_dir=self.dir.name)

if __name__ == "__main__":
    unittest.main()
