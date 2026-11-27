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
            "update_file_args": {"fileId": self.key["file_id"], "file_uri": "/fixture/upload.db"},
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

    def test_shared_workspace_authorizes_only_one_confirmation_until_receipt(self):
        landed = {}
        prepares = Mock(return_value={"status": "DOCS03_DRIVE_UPDATE_REQUIRED",
                                      "update_file_args": {"fileId": self.key["file_id"], "file_uri": "/fixture/upload.db"}})

        def send(chat, message, payload=None):
            key = {**self.key, "request_id": chat}
            return self.turn(message, payload=payload, conversation_id=chat,
                build_menu=lambda auth: SimpleNamespace(
                    auth=SimpleNamespace(family_login=auth),
                    select=lambda *_, **__: {**self.staged, "result": {"receipt_key": key}}),
                recover_receipt=lambda key: landed.get(key["request_id"]), prepare_writeback=prepares,
                write_slot=docs03._DriveWriteSlot(self.workspace, self.key["file_id"], "fixture-project", chat))

        chats = ("first-chat", "second-chat")
        with ThreadPoolExecutor(2) as workers:
            states = list(workers.map(lambda chat: send(chat, "confirm", self.payload)["status"], chats))
        self.assertCountEqual(states, ["DOCS03_DRIVE_UPDATE_REQUIRED", "DOCS03_DRIVE_WRITE_PENDING"])
        winner = chats[states.index("DOCS03_DRIVE_UPDATE_REQUIRED")]
        other = chats[states.index("DOCS03_DRIVE_WRITE_PENDING")]
        self.assertEqual(send(other, "still-pending")["status"], "DOCS03_DRIVE_WRITE_PENDING")
        self.assertEqual(send(winner, "waiting-for-drive")["status"], "AWAIT_DRIVE_CONFIRMATION")
        prepares.assert_called_once()
        landed[winner] = {"status": "PERSISTED_REMOTE_VERIFIED", **self.key, "request_id": winner}
        self.assertEqual(send(winner, "check-original")["status"], "PERSISTED_REMOTE_VERIFIED")
        self.assertEqual(send(other, "after-readback")["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        self.assertEqual(prepares.call_count, 2)

    def test_slot_releases_preflight_failures_but_not_unrelated_receipts(self):
        file_id = self.key["file_id"]
        first = docs03._DriveWriteSlot(self.workspace, file_id, "fixture-project", "original-chat")
        other = docs03._DriveWriteSlot(self.workspace, file_id, "fixture-project", "another-chat")
        different_file = docs03._DriveWriteSlot(self.workspace, "another-file", "fixture-project", "another-chat")
        self.prepare.side_effect = ValueError("backup mismatch")
        with self.assertRaisesRegex(ValueError, "backup mismatch"):
            self.turn("confirm", self.payload, write_slot=first)
        self.assertTrue(other.acquire(self.key))
        self.assertTrue(different_file.acquire({**self.key, "file_id": "another-file"}))
        first.finish(self.key, {"status": "PERSISTED_REMOTE_VERIFIED", **self.key})
        self.assertFalse(first.acquire(self.key))
        other.finish(self.key, {"status": "PERSISTED_REMOTE_VERIFIED", **self.key, "fingerprint": "different"})
        self.assertFalse(first.acquire(self.key))
        other.finish(self.key, {"status": "PERSISTED_REMOTE_VERIFIED", **self.key})
        self.assertTrue(first.acquire(self.key))

    def test_unrecognized_preflight_response_does_not_consume_original_writeback(self):
        self.turn("first", self.payload)
        for response in ({}, {"status": "TEMPORARY_TOOL_RESULT"}, None,
                         {"status": "DOCS03_DRIVE_UPDATE_REQUIRED"},
                         {"status": "DOCS03_DRIVE_UPDATE_REQUIRED",
                          "update_file_args": {"fileId": self.key["file_id"]}},
                         {"status": "DOCS03_DRIVE_UPDATE_REQUIRED",
                          "update_file_args": {"fileId": "other", "file_uri": "/fixture/upload.db"}}):
            with self.subTest(response=response):
                self.prepare.return_value = response
                with self.assertRaisesRegex(ValueError, "DOCS03_INVALID_WRITEBACK_RESPONSE"):
                    self.turn("bad-preflight")
        self.allow_update()
        self.assertEqual(self.turn("retry")["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        self.assertEqual(self.turn("wait")["status"], "AWAIT_DRIVE_CONFIRMATION")
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

    def test_exact_historical_replay_does_not_displace_new_confirmation(self):
        self.allow_update()
        self.turn("first", self.payload)
        self.land_receipt()
        saved = self.turn("landed")
        self.recover.return_value = None
        self.prepare.return_value = {"status": "DOCS03_BACKUP_REQUIRED"}
        latest = {**self.payload, "revision": "latest"}
        self.assertEqual(self.turn("later-confirmation", latest)["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(self.turn("fresh-replay", self.payload), saved)
        self.assertEqual(self.turn("fresh-replay"), saved)
        changed = {**self.payload, "revision": "neither"}
        self.assertEqual(self.turn("different-confirmation", changed)["status"], "ANOTHER_REQUEST_PENDING")
        self.assertEqual(self.turn("continue-latest")["status"], "DOCS03_BACKUP_REQUIRED")
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

    def test_pinned_candidate_reuses_exact_bytes_and_rejects_replacement(self):
        project, conversation = "fixture-project", "original-chat"
        journal, _ = docs03._journal_directory(self.workspace, project, conversation, create=True)
        source = self.workspace / "candidate.xlsx"
        source.write_bytes(b"approved candidate")
        revision = sha256(source.read_bytes()).hexdigest()

        def pin(digest):
            return Path(docs03._pin_candidate(
                self.workspace, project, conversation, source, digest, "xlsx"))

        with self.assertRaisesRegex(ValueError, "DOCS03_CANDIDATE_DIGEST_MISMATCH"):
            pin("0" * 64)
        self.assertEqual(list(journal.iterdir()), [])
        saved = pin(revision)
        self.assertEqual(saved.parent, journal)
        self.assertEqual(saved.stat().st_mode & 0o077, 0)
        self.assertEqual(revision, sha256(saved.read_bytes()).hexdigest())
        self.assertEqual(pin(revision), saved)
        self.assertEqual(list(journal.iterdir()), [saved])
        saved.write_bytes(b"changed candidate")
        with self.assertRaisesRegex(ValueError, "DOCS03_CANDIDATE_DIGEST_MISMATCH"):
            pin(revision)
        self.assertEqual(saved.read_bytes(), b"changed candidate")

    def test_direct_account_entry_uses_the_registered_workbook_download(self):
        source = self.workspace / "ledger.db"
        source.write_bytes(b"fixture")
        workbook_folder = self.workspace / "separate-download"
        workbook_folder.mkdir()
        workbook = workbook_folder / "mou_03_股票配置選擇進度.xlsx"
        download = Mock(return_value=("wrong-id", workbook))
        select = Mock(return_value={"status": "FAMILY03_ACCOUNT_PREVIEW"})
        build = Mock(return_value=SimpleNamespace(
            auth=SimpleNamespace(family_login=self.auth), select=select))
        args = dict(auth=self.auth, document_id="fixture-doc",
                    document={"documentId": "fixture-doc", "revisionId": "fixture-revision"},
                    project_id="fixture-project", conversation_id="original-chat",
                    workspace_dir=self.workspace, message_id="confirm",
                    project_name="MOU", login_account="MOU", family_alias="mou",
                    client_id=self.auth.client_id, downloaded_db_path=source,
                    official_drive_file_id="ledger-id", verified_drive_sha256=sha256(source.read_bytes()).hexdigest(),
                    mutation_staging_dir=self.workspace, download_original=Mock(),
                    native_writeback=True, payload=self.payload, progress_file_id="workbook-id",
                    download_progress=download)
        original_load = docs03._load_module
        with patch.object(docs03, "_load_module", side_effect=lambda name:
                          SimpleNamespace(build_project_menu=build)
                          if name == "on_demand_project" else original_load(name)):
            with self.assertRaisesRegex(PermissionError, "DOCS03_PROGRESS_BINDING_MISMATCH"):
                docs03.run_project_docs03(**args)
            build.assert_not_called()
            download.return_value = ("workbook-id", workbook)
            self.assertEqual(docs03.run_project_docs03(**args)["status"], "FAMILY03_ACCOUNT_PREVIEW")
        build.assert_called_once()
        self.assertEqual(build.call_args.kwargs["family03_progress_path"], workbook)

    def test_account_preflight_uses_fresh_drive_bytes_and_prefers_original_receipt(self):
        import sqlite3

        cases = {
            "download moved": "DOCS03_DRIVE_UPDATE_REQUIRED",
            "receipt became visible": "PERSISTED_REMOTE_VERIFIED",
            "ledger changed": "DOCS03_PREVIEW_STALE",
            "workbook changed": "DOCS03_PREVIEW_STALE",
            "journal copy gone": "DOCS03_PREVIEW_STALE",
        }
        for case, expected in cases.items():
            with self.subTest(case=case), TemporaryDirectory(dir=self.workspace) as folder:
                root = Path(folder)
                source, backup, latest = (root / name for name in ("turn1.db", "backup.db", "turn2.db"))
                workbook = root / "progress.xlsx"
                mutation_fixture.seed(source)
                copyfile(source, backup)
                copyfile(source, latest)
                workbook.write_bytes(b"preview workbook")
                self.auth.user_id = "JO"
                self.auth.client_id = mutation_fixture.CLIENT
                binding = dict(auth=self.auth, login_account="JO", client_id=mutation_fixture.CLIENT,
                    family_alias="Joseph", official_drive_file_id="ledger-id", staging_dir=root)
                stager = mutation_fixture.MUT.OnDemandMutationStager(
                    **binding, downloaded_db_path=source, verified_drive_sha256=sha256(source.read_bytes()).hexdigest())
                stage = stager.stage("adjust_target", {
                    "request_id": "fixture-confirm", "owner_confirmed": True,
                    "record": {"confirmed": True, "source_reference": "fixture",
                               "allocations": [{"instrument_key": "VT", "weight": "1"}]},
                })
                select = Mock(return_value={"status": "DB_WRITEBACK_REQUIRED", "result": stage})
                menu = SimpleNamespace(auth=SimpleNamespace(family_login=self.auth), select=select)
                download = Mock(return_value=("ledger-id", source))
                payload = {**self.payload, "revision": sha256(workbook.read_bytes()).hexdigest()}
                context = dict(auth=self.auth, document_id="fixture-doc",
                    document={"documentId": "fixture-doc", "revisionId": "fixture-revision"},
                    project_id="fixture-project", conversation_id="original-chat", workspace_dir=root,
                    project_name="fixture", login_account="JO", client_id=self.auth.client_id,
                    family_alias="Joseph", official_drive_file_id="ledger-id", mutation_staging_dir=root,
                    download_original=download, native_writeback=True, progress_file_id="workbook-id",
                    download_progress=lambda _: ("workbook-id", workbook), build_original_menu=lambda _: menu)

                first = docs03.run_project_docs03(**context, message_id="first", payload=payload,
                    downloaded_db_path=source, verified_drive_sha256=sha256(source.read_bytes()).hexdigest())
                self.assertEqual(first["status"], "DOCS03_BACKUP_REQUIRED")
                if case in ("receipt became visible", "workbook changed"):
                    workbook.write_bytes(b"updated workbook")
                if case == "receipt became visible":
                    copyfile(stage["writeback_plan"]["candidate"]["path"], latest)
                if case == "ledger changed":
                    with sqlite3.connect(latest) as db:
                        db.execute("CREATE TABLE independent_change (flag TEXT)")
                source.unlink()
                Path(stage["writeback_plan"]["candidate"]["path"]).unlink()
                if case == "journal copy gone":
                    journal, _ = docs03._journal_directory(
                        root, context["project_id"], context["conversation_id"], create=False)
                    next(journal.glob("upload-*.db")).unlink()
                download.side_effect = [("ledger-id", backup), ("ledger-id", latest)]
                result = docs03.run_project_docs03(**context, message_id="continue",
                    downloaded_db_path=latest, verified_drive_sha256=sha256(latest.read_bytes()).hexdigest(),
                    verified_backup=("backup-id", backup))
                self.assertEqual(result["status"], expected)
                self.assertEqual("update_file_args" in result, case == "download moved")
                if case == "receipt became visible":
                    self.assertEqual(result["result"]["request_id"], "fixture-confirm")
                    self.assertEqual(result["result"]["sha256"], sha256(latest.read_bytes()).hexdigest())
                select.assert_called_once()

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
            other = docs03._DriveWriteSlot(self.workspace, "original-db", "fixture-project", "other-chat")
            other_key = {**self.key, "request_id": "other-confirmation"}
            self.assertTrue(other.acquire(other_key))
            blocked = turn("while-other-is-writing", verified_backup=("backup-id", backup))
            self.assertEqual(blocked["status"], "DOCS03_DRIVE_WRITE_PENDING")
            self.assertNotIn("update_file_args", blocked)
            other.release(other_key)
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


class Docs03NativeHostTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.auth = TestLogin()
        self.ledger = self.root / "ledger.db"
        self.ledger.write_bytes(b"fixture ledger")
        self.workbook = self.root / "mou_03_股票配置選擇進度.xlsx"
        self.download_ledger = Mock(return_value=("ledger-id", self.ledger))
        self.download_workbook = Mock(return_value=("progress-id", self.workbook))
        self.build_menu = Mock()

    def turn(self, payload=None, **overrides):
        opts = dict(auth=self.auth, document_id="fixture-doc",
                    document={"documentId": "fixture-doc", "revisionId": "fixture-revision"},
                    project_id="fixture-project", conversation_id="original-chat",
                    workspace_dir=self.root, message_id="fixture-message",
                    project_name="MOU", login_account="MOU", client_id=self.auth.client_id,
                    family_alias="mou", official_drive_file_id="ledger-id",
                    progress_file_id="progress-id", download_original=self.download_ledger,
                    download_progress=self.download_workbook, build_original_menu=self.build_menu,
                    mutation_staging_dir=self.root, payload=payload,
                    verified_account_backup=("ledger-backup", self.ledger),
                    verified_progress_backup=("progress-backup", self.workbook))
        return docs03.run_project_docs03_native_turn(**(opts | overrides))

    def test_missing_host_inputs_and_wrong_login_stop_before_downloading(self):
        for edits, error, message in (
                ({"conversation_id": None}, ValueError, "TRUSTED_CONVERSATION_BINDING_REQUIRED"),
                ({"message_id": None}, ValueError, "STABLE_MESSAGE_ID_REQUIRED"),
                ({"workspace_dir": None}, ValueError, "DOCS03_WORKSPACE_DIRECTORY_REQUIRED"),
                ({"progress_file_id": "ledger-id"}, ValueError, "DOCS03_DISTINCT_SOURCE_IDS_REQUIRED"),
                ({"login_account": "AR"}, PermissionError, "DOCS03_PROJECT_ACCOUNT_MISMATCH"),
                ({"document": {"documentId": "wrong"}}, PermissionError, "WRONG_LOGIN_DOCUMENT")):
            with self.subTest(edits=edits), self.assertRaisesRegex(error, message):
                self.turn(**edits)
        self.download_ledger.assert_not_called()
        self.download_workbook.assert_not_called()
        self.build_menu.assert_not_called()

    def test_native_first_dispatch_rejects_changed_sources_before_downloading(self):
        self.download_ledger.side_effect = TimeoutError("ledger could not be loaded")
        result = self.turn({"action": "confirm_account", "revision": "original"})
        self.assertEqual(result["status"], "DOCS03_READ_RETRY_REQUIRED")
        self.download_ledger.reset_mock(side_effect=True)
        for candidate in ({"official_drive_file_id": "other-ledger"}, {"progress_file_id": "other-excel"}):
            with self.subTest(changed=candidate), \
                    self.assertRaisesRegex(PermissionError, "DOCS03_ORIGINAL_SOURCE_BINDING_CHANGED"):
                self.turn(message_id="continue", **candidate)
        self.download_ledger.assert_not_called()
        self.download_workbook.assert_not_called()
        with patch.object(docs03, "run_project_docs03", return_value={"status": "DOCS03_BACKUP_REQUIRED"}) as account:
            self.assertEqual(self.turn(message_id="continue")["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(account.call_args.kwargs["payload"],
                         {"action": "confirm_account", "revision": "original"})

    def test_excel_uses_same_host_menu_with_only_the_excel_backup(self):
        answer = dict(revision="original", question_id="choice", key="goal", reply="成長")

        def stage(**args):
            self.assertEqual(args["verified_backup"], ("progress-backup", self.workbook))
            self.assertEqual(args["payload"], answer)
            downloaded, path = args["download_progress"]("progress-id")
            self.assertEqual(downloaded, "progress-id")
            args["build_menu"](self.auth, path)
            return {"status": "DOCS03_BACKUP_REQUIRED"}

        with patch.object(docs03, "run_project_docs03_progress", side_effect=stage) as progress, \
                patch.object(docs03, "run_project_docs03") as account:
            self.assertEqual(self.turn(answer)["status"], "DOCS03_BACKUP_REQUIRED")
        progress.assert_called_once()
        account.assert_not_called()
        self.build_menu.assert_called_once_with(self.auth, self.workbook, self.ledger)

    def test_excel_receipt_can_be_recovered_after_relogin_without_ledger(self):
        from openpyxl import Workbook

        event = "a" * 64
        book = Workbook()
        book.active.title = "選擇進度"
        book.active.append(["股票配置・選擇進度", "mou"])
        history = book.create_sheet("選擇歷程")
        history.append(["事件識別", "家人"])
        book.save(self.workbook)
        revision = sha256(self.workbook.read_bytes()).hexdigest()
        candidate = self.root / "candidate.xlsx"
        history.append([event, "mou"])
        book.save(candidate)
        backup = self.root / "backup.xlsx"
        copyfile(self.workbook, backup)

        def select(number, *, payload):
            self.assertEqual(number, 3)
            self.assertEqual(set(payload), {"revision", "question_id", "key", "reply"})
            return {"status": "FAMILY03_PROGRESS_WRITEBACK_REQUIRED", "result": {
                "status": "FAMILY03_PROGRESS_WRITEBACK_REQUIRED", "本人": "mou",
                "檔名": self.workbook.name, "原檔摘要": revision, "新檔摘要": sha256(candidate.read_bytes()).hexdigest(),
                "候選檔": str(candidate), "事件識別": event,
                "讀回入口": {"event_id": event, "source_revision": revision}}}

        self.build_menu.return_value = SimpleNamespace(
            auth=SimpleNamespace(family_login=self.auth), select=select)
        answer = dict(revision=revision, question_id="choice", key="goal", reply="成長")
        self.assertEqual(self.turn(answer, verified_progress_backup=None)["status"], "DOCS03_BACKUP_REQUIRED")
        candidate.unlink()
        other = docs03._DriveWriteSlot(self.root, "progress-id", "fixture-project", "other-chat")
        other_key = {"file_id": "progress-id", "request_id": "other-excel-event"}
        self.assertTrue(other.acquire(other_key))
        direct = docs03.run_project_docs03_progress(
            auth=self.auth, document_id="fixture-doc",
            document={"documentId": "fixture-doc", "revisionId": "fixture-revision"},
            project_id="fixture-project", conversation_id="original-chat",
            workspace_dir=self.root, message_id="direct-while-other-is-writing",
            login_account="MOU", client_id=self.auth.client_id, family_alias="mou",
            progress_file_id="progress-id", download_progress=self.download_workbook,
            build_menu=lambda *_: self.fail("a staged answer must not re-open the menu"),
            verified_backup=("backup-id", backup))
        self.assertEqual(direct["status"], "DOCS03_DRIVE_WRITE_PENDING")
        self.assertNotIn("update_file_args", direct)
        other.release(other_key)
        update = self.turn(message_id="backup", verified_progress_backup=("backup-id", backup))
        self.assertEqual(update["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        uploaded_artifact = Path(update["update_file_args"]["file_uri"])
        self.assertEqual(uploaded_artifact.stat().st_mode & 0o077, 0)
        self.assertNotEqual(uploaded_artifact, candidate)
        copyfile(uploaded_artifact, self.workbook)
        self.download_ledger.reset_mock(side_effect=True)
        self.download_ledger.side_effect = FileNotFoundError("ledger unavailable")
        self.download_workbook.reset_mock()
        with self.assertRaisesRegex(PermissionError, "stale fixture login"):
            self.turn(message_id="expired", document={"documentId": "fixture-doc", "revisionId": "expired"})
        self.download_workbook.assert_not_called()
        self.auth = TestLogin()
        self.download_workbook.return_value = ("another-id", self.workbook)
        with self.assertRaisesRegex(PermissionError, "DOCS03_PROGRESS_BINDING_MISMATCH"):
            self.turn(message_id="wrong-workbook-id")
        self.download_workbook.return_value = ("progress-id", self.workbook)
        book.active["B1"] = "someone-else"
        book.save(self.workbook)
        with self.assertRaisesRegex(PermissionError, "FAMILY03_PROGRESS_OWNER_MISMATCH"):
            self.turn(message_id="wrong-workbook-owner")
        book.active["B1"] = "mou"
        history.append([event, "mou"])
        book.save(self.workbook)
        with self.assertRaisesRegex(ValueError, "FAMILY03_DUPLICATE_PROGRESS_EVENT"):
            self.turn(message_id="duplicate-event")
        copyfile(uploaded_artifact, self.workbook)
        reply = self.turn(message_id="after-relogin")
        self.assertEqual(reply["status"], "PERSISTED_REMOTE_VERIFIED")
        self.assertEqual(reply["result"]["progress_receipt"]["事件序號"], 1)
        self.assertEqual(self.turn(message_id="answer-redelivered", payload=answer), reply)
        self.download_workbook.reset_mock()
        for changed in ({"progress_file_id": "other-workbook"},
                        {"official_drive_file_id": "other-ledger"}):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                    PermissionError, "DOCS03_ORIGINAL_SOURCE_BINDING_CHANGED"):
                self.turn(message_id="after-relogin", **changed)
        self.download_workbook.assert_not_called()
        self.assertEqual(self.turn(message_id="after-relogin"), reply)
        self.download_ledger.assert_not_called()
        self.build_menu.assert_called_once()

    def test_native_account_resume_reads_one_fresh_ledger_without_reopening_menu(self):
        source = self.ledger
        source.unlink()
        mutation_fixture.seed(source)
        self.auth.user_id = "JO"
        self.auth.client_id = mutation_fixture.CLIENT
        member = dict(login_account="JO", family_alias="Joseph")
        self.workbook = self.root / "Joseph_03_股票配置選擇進度.xlsx"
        self.workbook.write_bytes(b"fixture preview")
        self.download_workbook.return_value = ("progress-id", self.workbook)
        stager = mutation_fixture.MUT.OnDemandMutationStager(
            auth=self.auth, **member, client_id=self.auth.client_id,
            official_drive_file_id="ledger-id", downloaded_db_path=source,
            verified_drive_sha256=sha256(source.read_bytes()).hexdigest(), staging_dir=self.root)
        staged = stager.stage("adjust_target", {
            "request_id": "fixture-confirm", "owner_confirmed": True,
            "record": {"confirmed": True, "source_reference": "fixture",
                       "allocations": [{"instrument_key": "VT", "weight": "1"}]},
        })
        self.build_menu.return_value = SimpleNamespace(
            auth=SimpleNamespace(family_login=self.auth),
            select=Mock(return_value={"status": "DB_WRITEBACK_REQUIRED", "result": staged}))
        payload = dict(action="confirm_account", revision=sha256(self.workbook.read_bytes()).hexdigest())
        self.assertEqual(self.turn(payload, verified_account_backup=None, **member)["status"],
                         "DOCS03_BACKUP_REQUIRED")
        backup = self.root / "original-backup.db"
        copyfile(source, backup)
        update = self.turn(message_id="backup", verified_account_backup=("backup-id", backup), **member)
        self.assertEqual(update["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
        copyfile(update["update_file_args"]["file_uri"], source)
        self.download_ledger.reset_mock()
        self.download_workbook.reset_mock()
        self.download_ledger.side_effect = [("ledger-id", source), TimeoutError("unexpected second download")]
        reply = self.turn(message_id="continue", **member)
        self.assertEqual(reply["status"], "PERSISTED_REMOTE_VERIFIED")
        self.assertEqual(reply["result"]["request_id"], "fixture-confirm")
        self.download_ledger.assert_called_once_with("ledger-id")
        self.download_workbook.assert_not_called()
        self.assertEqual(self.turn(payload, message_id="replay", **member), reply)
        self.download_ledger.assert_called_once_with("ledger-id")
        self.build_menu.assert_called_once()

    def test_account_uses_same_host_menu_and_rejects_mismatched_downloads(self):
        payload = dict(action="confirm_account", revision="original")

        def stage(**args):
            self.assertEqual(args["verified_backup"], ("ledger-backup", self.ledger))
            self.assertNotIn("verified_drive_sha256", args)
            args["build_original_menu"](self.auth)
            return {"status": "DOCS03_BACKUP_REQUIRED"}

        with patch.object(docs03, "run_project_docs03", side_effect=stage) as account, \
                patch.object(docs03, "run_project_docs03_progress") as progress:
            self.download_ledger.return_value = ("other-id", self.ledger)
            with self.assertRaisesRegex(PermissionError, "DOCS03_WRITEBACK_BINDING_MISMATCH"):
                self.turn(payload)
            self.build_menu.assert_not_called()
            self.download_workbook.assert_not_called()
            self.download_ledger.return_value = ("ledger-id", self.ledger)
            self.download_workbook.return_value = ("other-id", self.workbook)
            with self.assertRaisesRegex(PermissionError, "DOCS03_PROGRESS_BINDING_MISMATCH"):
                self.turn()
            self.build_menu.assert_not_called()
            self.download_workbook.return_value = ("progress-id", self.workbook)
            self.assertEqual(self.turn()["status"], "DOCS03_BACKUP_REQUIRED")
        progress.assert_not_called()
        self.build_menu.assert_called_once_with(self.auth, self.workbook, self.ledger)


if __name__ == "__main__":
    unittest.main()
