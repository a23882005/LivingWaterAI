"""Regression tests for the original Menu 03 confirmation journal."""
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from hashlib import sha256
from shutil import copyfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_on_demand_mutations as mutation_fixture


spec = spec_from_file_location(
    "family_docs03_writeback_test",
    Path(__file__).resolve().parents[1] / "docs03_receipt_entry.py",
)
docs03 = module_from_spec(spec)
spec.loader.exec_module(docs03)


class TestLogin:
    user_id = "MOU"
    client_id = "fixture-client"

    def begin_request(self):
        pass

    def check_revision(self, revision):
        if revision != "fixture-revision":
            raise PermissionError("stale fixture login")

    def require_login(self):
        return self.user_id


class Docs03WritebackTests(unittest.TestCase):
    def setUp(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.workspace = Path(root.name)
        self.auth = TestLogin()
        self.payload = {"action": "confirm_account", "revision": "before"}
        self.key = {"file_id": "original-db", "client_id": self.auth.client_id,
                    "operation": "adjust_target", "request_id": "confirmation",
                    "fingerprint": "a" * 64}
        self.staged = {"status": "DB_WRITEBACK_REQUIRED",
                       "pending_operation": "adjust_target",
                       "result": {"receipt_key": self.key}}
        self.select = Mock(return_value=self.staged)
        self.prepare = Mock(return_value={"status": "DOCS03_BACKUP_REQUIRED"})
        self.recover = Mock(return_value=None)

    def turn(self, message, payload=None, **overrides):
        arguments = {
            "auth": self.auth, "document_id": "fixture-doc",
            "document": {"documentId": "fixture-doc", "revisionId": "fixture-revision"},
            "project_id": "fixture-project", "conversation_id": "original-chat",
            "workspace_dir": self.workspace, "message_id": message,
            "build_menu": lambda login: SimpleNamespace(
                auth=SimpleNamespace(family_login=login), select=self.select),
            "recover_receipt": self.recover, "prepare_writeback": self.prepare,
            "payload": payload,
        }
        return docs03.run_docs03(**(arguments | overrides))

    def allow_update(self):
        self.prepare.return_value = {
            "status": "DOCS03_DRIVE_UPDATE_REQUIRED",
            "update_file_args": {"fileId": self.key["file_id"]},
        }

    def land_receipt(self):
        self.recover.return_value = {"status": "PERSISTED_REMOTE_VERIFIED", **self.key}

    def test_concurrent_resumes_issue_only_one_update(self):
        self.assertEqual(self.turn("first", self.payload)["status"], "DOCS03_BACKUP_REQUIRED")
        self.allow_update()
        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(self.turn, ("resume-a", "resume-b")))
        self.assertCountEqual([r["status"] for r in results],
                              ["DOCS03_DRIVE_UPDATE_REQUIRED", "AWAIT_DRIVE_CONFIRMATION"])
        self.assertEqual(self.turn("resume-again")["status"], "AWAIT_DRIVE_CONFIRMATION")
        self.assertEqual(self.prepare.call_count, 2)
        self.select.assert_called_once()

    def test_lost_update_response_and_new_message_replay(self):
        def submit():
            self.land_receipt()
            raise TimeoutError("fixture lost its response")

        self.prepare.return_value = Mock(side_effect=submit)
        result = self.turn("first", self.payload)
        self.assertEqual(result["status"], "PERSISTED_REMOTE_VERIFIED")
        self.assertEqual(self.turn("continue-after-restart"), result)
        self.assertEqual(self.turn("resent-as-new-message", self.payload), result)
        self.prepare.return_value.assert_called_once()
        self.select.assert_called_once()

    def test_unknown_update_remains_read_only_across_turns(self):
        submit = Mock(side_effect=TimeoutError("fixture has unknown outcome"))
        self.prepare.return_value = submit
        self.assertEqual(self.turn("first", self.payload)["status"], "AWAIT_DRIVE_CONFIRMATION")
        self.assertEqual(self.turn("resume")["status"], "AWAIT_DRIVE_CONFIRMATION")
        submit.assert_called_once()
        self.prepare.assert_called_once()
        self.select.assert_called_once()

    def test_backup_error_can_resume_without_restarting_confirmation(self):
        self.prepare.side_effect = ValueError("fixture backup mismatch")
        with self.assertRaisesRegex(ValueError, "backup mismatch"):
            self.turn("first", self.payload)
        self.prepare.side_effect = None
        self.allow_update()
        self.assertEqual(self.turn("retry-after-backup")["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        self.select.assert_called_once()

    def test_stale_preview_releases_pending_for_new_confirmation(self):
        self.turn("first", self.payload)
        self.prepare.return_value = {"status": "DOCS03_PREVIEW_STALE", "request_id": "confirmation"}
        result = self.turn("discover-stale")
        self.assertEqual(result["status"], "DOCS03_PREVIEW_STALE")
        self.assertNotIn("update_file_args", result)
        self.assertEqual(self.turn("discover-stale"), result)
        self.prepare.return_value = {"status": "DOCS03_BACKUP_REQUIRED"}
        updated = {**self.payload, "revision": "latest"}
        self.assertEqual(self.turn("fresh-confirm", updated)["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(self.select.call_count, 2)

    def test_different_confirmation_does_not_replace_pending(self):
        self.turn("first", self.payload)
        unrelated = {**self.payload, "revision": "different"}
        self.assertEqual(self.turn("different", unrelated)["status"], "ANOTHER_REQUEST_PENDING")
        self.select.assert_called_once()

    def test_session_binding_checked_before_returning_a_receipt(self):
        self.allow_update()
        self.turn("first", self.payload)
        self.land_receipt()
        self.assertEqual(self.turn("different-chat", conversation_id="other-chat")["status"],
                         "DOCS03_JOURNAL_MISSING")
        with self.assertRaisesRegex(PermissionError, "WRONG_LOGIN_DOCUMENT"):
            self.turn("wrong-doc", document={"documentId": "different", "revisionId": "fixture-revision"})
        with self.assertRaisesRegex(PermissionError, "stale fixture login"):
            self.turn("wrong-revision", document={"documentId": "fixture-doc", "revisionId": "different"})
        self.assertEqual(self.turn("correct-chat")["result"]["request_id"], "confirmation")

    def test_native_writeback_checks_backup_and_receipt_account(self):
        source = self.workspace / "downloaded.db"
        remote = self.workspace / "remote.db"
        backup = self.workspace / "backup.db"
        mutation_fixture.seed(source)
        copyfile(source, remote)
        copyfile(source, backup)
        self.auth.user_id = "JO"
        self.auth.client_id = mutation_fixture.CLIENT
        sources = {
            "login_account": "JO", "client_id": mutation_fixture.CLIENT,
            "family_alias": "Joseph", "official_drive_file_id": "original-db",
            "downloaded_db_path": source, "verified_drive_sha256": sha256(source.read_bytes()).hexdigest(),
        }
        stager = mutation_fixture.MUT.OnDemandMutationStager(
            auth=self.auth, staging_dir=self.workspace, **sources)

        def select(number, *, payload):
            self.assertEqual(number, 3)
            self.assertEqual(payload, self.payload)
            result = stager.stage("adjust_target", {
                "request_id": "confirmation", "owner_confirmed": True,
                "record": {"confirmed": True, "source_reference": "fixture",
                           "allocations": [{"instrument_key": "VT", "weight": "1"}]},
            })
            return {"status": "DB_WRITEBACK_REQUIRED", "result": result}

        def download(file_id):
            self.assertEqual(file_id, "original-db")
            return file_id, remote

        def turn(message_id, **overrides):
            args = {
                "auth": self.auth, "document_id": "fixture-doc",
                "document": {"documentId": "fixture-doc", "revisionId": "fixture-revision"},
                "project_id": "fixture-project", "conversation_id": "original-chat",
                "workspace_dir": self.workspace, "message_id": message_id,
                "project_name": "fixture", "mutation_staging_dir": self.workspace,
                "download_original": download, "native_writeback": True,
                **sources,
            }
            return docs03.run_project_docs03(**(args | overrides))

        original_load = docs03._load_module
        build = Mock(return_value=SimpleNamespace(
            auth=SimpleNamespace(family_login=self.auth), select=select))
        with patch.object(docs03, "_load_module", side_effect=lambda name:
                          SimpleNamespace(build_project_menu=build)
                          if name == "on_demand_project" else original_load(name)):
            self.assertEqual(turn("first", payload=self.payload)["status"], "DOCS03_BACKUP_REQUIRED")
            with self.assertRaisesRegex(ValueError, "DISTINCT_REMOTE_BACKUP_REQUIRED"):
                turn("wrong-backup", verified_backup=("original-db", backup))
            staged = turn("verified-backup", verified_backup=("backup-id", backup))
            self.assertEqual(staged["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
            self.assertEqual(staged["update_file_args"]["fileId"], "original-db")
            copyfile(staged["update_file_args"]["file_uri"], remote)
            saved = turn("after-write")
            self.assertEqual(saved["status"], "PERSISTED_REMOTE_VERIFIED")
            with self.assertRaisesRegex(PermissionError, "DOCS03_RECEIPT_BINDING_MISMATCH"):
                turn("after-write", official_drive_file_id="different-db")
            with self.assertRaisesRegex(PermissionError, "DOCS03_PROJECT_ACCOUNT_MISMATCH"):
                turn("after-write", login_account="AR")
            self.assertEqual(turn("new-message", payload=self.payload), saved)
            build.assert_called_once()


if __name__ == "__main__":
    unittest.main()
