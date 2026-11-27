"""Exercise Menu 03 continuation across both original journals."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_docs03_writeback import TestLogin, docs03


class Menu03RouterTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.context = {
            "auth": TestLogin(), "document_id": "fixture-doc",
            "document": {"documentId": "fixture-doc", "revisionId": "fixture-revision"},
            "project_id": "fixture-project", "conversation_id": "original-chat",
            "workspace_dir": Path(folder.name),
        }
        self.account = {"action": "confirm_account", "revision": "account-before"}
        self.progress = {"revision": "excel-before", "question_id": "goal",
                         "key": "goal", "reply": "兼顧成長與收入"}
        self.stage = {}
        self.observe = {}
        self.prepare = {}
        for kind, operation in (("account", "adjust_target"), ("progress", "save_progress")):
            key = {"file_id": kind, "client_id": "fixture-client", "operation": operation,
                   "request_id": kind, "fingerprint": "a" * 64}
            self.stage[kind] = Mock(return_value={
                "status": "DB_WRITEBACK_REQUIRED", "result": {"receipt_key": key}})
            self.observe[kind] = Mock(return_value=None)
            self.prepare[kind] = Mock(return_value={"status": "DOCS03_BACKUP_REQUIRED"})

    def original(self, kind, message, payload, **overrides):
        context = self.context | overrides
        if kind == "progress":
            context["project_id"] += "|03-progress"
        return docs03.run_docs03(
            **context, message_id=message, payload=payload,
            build_menu=lambda auth: SimpleNamespace(
                auth=SimpleNamespace(family_login=auth), select=self.stage[kind]),
            recover_receipt=self.observe[kind],
            prepare_writeback=self.prepare[kind],
            progress_answers=kind == "progress")

    def turn(self, message, payload=None, *, before_dispatch=None, **overrides):
        def dispatch(kind, mid, data):
            if before_dispatch:
                before_dispatch()
            return self.original(kind, mid, data, **overrides)

        return docs03.run_project_docs03_turn(
            **(self.context | overrides), message_id=message, payload=payload,
            account_turn=lambda mid, data: dispatch("account", mid, data),
            progress_turn=lambda mid, data: dispatch("progress", mid, data))

    def test_continue_restores_interrupted_first_dispatch(self):
        for first, other in (("account", "progress"), ("progress", "account")):
            with self.subTest(first=first), TemporaryDirectory() as folder:
                context = {"workspace_dir": Path(folder)}
                self.observe[first].return_value = None
                self.observe[other].return_value = None

                def interrupted():
                    raise KeyboardInterrupt("before opening the business journal")

                with self.assertRaises(KeyboardInterrupt):
                    self.turn("first", getattr(self, first), before_dispatch=interrupted, **context)
                self.assertEqual(self.turn("foreign-reply", conversation_id="other-chat", **context)["status"],
                                 "NO_PENDING_REQUEST")
                with self.assertRaisesRegex(PermissionError, "stale fixture login"):
                    self.turn("expired-reply", document={"documentId": "fixture-doc"}, **context)
                self.assertEqual(self.turn("other", getattr(self, other), **context)["status"],
                                 "ANOTHER_REQUEST_PENDING")
                changed = {**getattr(self, first), "revision": "different"}
                with self.assertRaisesRegex(ValueError, "REQUEST_COLLISION"):
                    self.turn("first", changed, **context)
                self.land(first)
                receipt = self.turn("recovered", **context)
                self.assertEqual(receipt["result"]["file_id"], first)
                self.assertEqual(self.turn("other", getattr(self, other), **context)["status"],
                                 "DOCS03_BACKUP_REQUIRED")
                self.assertEqual(self.turn("recovered", **context), receipt)
                self.assertEqual(self.turn("first", getattr(self, first), **context), receipt)

    def test_transient_failure_before_dispatch_preserves_first_message(self):
        def timed_out():
            raise TimeoutError("test download timeout")

        response = self.turn("confirm", self.account, before_dispatch=timed_out)
        self.assertEqual(response["status"], "DOCS03_READ_RETRY_REQUIRED")
        self.assertNotIn("update_file_args", response)
        self.stage["account"].assert_not_called()
        self.assertEqual(self.turn("unrelated-answer", self.progress)["status"], "ANOTHER_REQUEST_PENDING")
        self.assertEqual(self.turn("next-continue")["status"], "DOCS03_BACKUP_REQUIRED")
        self.stage["account"].assert_called_once()

    def test_read_retry_after_authorization_never_reissues_upload(self):
        for kind in ("account", "progress"):
            with self.subTest(kind=kind), TemporaryDirectory() as folder:
                context = {"workspace_dir": Path(folder)}
                error = FileNotFoundError("test download missing")
                self.prepare[kind].side_effect = [
                    error, {"status": "DOCS03_DRIVE_UPDATE_REQUIRED",
                            "update_file_args": {"fileId": kind, "file_uri": "/fixture/upload.db"}}]
                self.assertEqual(self.turn("original", getattr(self, kind), **context)["status"],
                                 "DOCS03_READ_RETRY_REQUIRED")
                self.assertEqual(self.turn("before-upload", **context)["status"], "DOCS03_DRIVE_UPDATE_REQUIRED")
                self.observe[kind].side_effect = ConnectionError("test readback timeout")
                retry = self.turn("readback-unavailable", **context)
                self.assertEqual(retry["status"], "DOCS03_READ_RETRY_REQUIRED")
                self.assertNotIn("update_file_args", retry)
                self.observe[kind].side_effect = None
                self.assertEqual(self.turn("readback-empty", **context)["status"], "AWAIT_DRIVE_CONFIRMATION")
                self.land(kind)
                saved = self.turn("readback-landed", **context)
                self.assertEqual(saved["status"], "PERSISTED_REMOTE_VERIFIED")
                self.assertEqual(self.turn("readback-landed", **context), saved)
                self.assertEqual(self.prepare[kind].call_count, 2)
                self.stage[kind].assert_called_once()

    def test_interrupted_checkpoint_clears_after_business_journal_rejects_preview(self):
        self.stage["account"].side_effect = ValueError("preview is stale")

        def interrupted():
            raise KeyboardInterrupt("before opening the business journal")

        with self.assertRaises(KeyboardInterrupt):
            self.turn("original-confirm", self.account, before_dispatch=interrupted)
        with self.assertRaisesRegex(ValueError, "preview is stale"):
            self.turn("retry-stale")
        self.assertEqual(self.turn("new-answer", self.progress)["status"],
                         "DOCS03_BACKUP_REQUIRED")

    def test_redelivery_of_cancelled_message_leaves_interrupted_work_untouched(self):
        self.stage["account"].side_effect = ValueError("preview is stale")
        with self.assertRaisesRegex(ValueError, "preview is stale"):
            self.turn("old-confirm", self.account)

        def interrupted():
            raise KeyboardInterrupt("before opening the business journal")

        with self.assertRaises(KeyboardInterrupt):
            self.turn("new-answer", self.progress, before_dispatch=interrupted)
        self.assertEqual(self.turn("old-confirm")["status"], "NO_PENDING_REQUEST")
        self.stage["progress"].assert_not_called()
        self.assertEqual(self.turn("continue-new")["status"], "DOCS03_BACKUP_REQUIRED")
        self.stage["progress"].assert_called_once()

    def test_interrupted_redelivery_distinguishes_boolean_and_number(self):
        original = {**self.account, "owner_confirmed": True}

        def interrupted():
            raise KeyboardInterrupt("before opening the business journal")

        with self.assertRaises(KeyboardInterrupt):
            self.turn("original", original, before_dispatch=interrupted)
        with self.assertRaisesRegex(ValueError, "REQUEST_COLLISION"):
            self.turn("original", {**original, "owner_confirmed": 1})
        self.stage["account"].assert_not_called()
        self.assertEqual(self.turn("continue-original")["status"], "DOCS03_BACKUP_REQUIRED")

    def test_invalid_first_dispatch_releases_router_checkpoint(self):
        self.stage["account"].side_effect = ValueError("preview is stale")
        with self.assertRaisesRegex(ValueError, "preview is stale"):
            self.turn("stale", self.account)
        self.assertEqual(self.turn("new-answer", self.progress)["status"],
                         "DOCS03_BACKUP_REQUIRED")

    def land(self, kind):
        self.observe[kind].return_value = {
            "status": "PERSISTED_REMOTE_VERIFIED",
            **self.stage[kind].return_value["result"]["receipt_key"],
        }

    def test_plain_continue_follows_each_pending_and_replays_each_receipt(self):
        self.assertEqual(self.turn("nothing")["status"], "NO_PENDING_REQUEST")
        self.assertEqual(self.turn("answer", self.progress)["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(self.turn("confirm-too-soon", self.account)["status"],
                         "ANOTHER_REQUEST_PENDING")
        self.assertEqual(self.turn("retry-backup")["status"], "DOCS03_BACKUP_REQUIRED")
        self.land("progress")
        progress_receipt = self.turn("resume-answer")
        self.assertEqual(progress_receipt["result"]["file_id"], "progress")
        self.assertEqual(self.turn("confirm", self.account)["status"], "DOCS03_BACKUP_REQUIRED")
        self.assertEqual(self.turn("another-answer", self.progress)["status"],
                         "ANOTHER_REQUEST_PENDING")
        self.land("account")
        account_receipt = self.turn("resume-account")
        self.assertEqual(account_receipt["result"]["file_id"], "account")
        self.assertEqual(self.turn("most-recent-receipt"), account_receipt)
        self.assertEqual(self.turn("resume-answer"), progress_receipt)
        self.assertEqual(self.turn("resume-account"), account_receipt)
        with self.assertRaisesRegex(ValueError, "REQUEST_COLLISION"):
            self.turn("answer", self.account)
        for stage in self.stage.values():
            stage.assert_called_once()

    def test_original_receipt_stays_readable_with_other_action_pending(self):
        for first, second in (("account", "progress"), ("progress", "account")):
            with self.subTest(first=first), TemporaryDirectory() as folder:
                context = {"workspace_dir": Path(folder)}
                self.observe[first].return_value = None
                self.observe[second].return_value = None
                self.assertEqual(self.turn("first", getattr(self, first), **context)["status"],
                                 "DOCS03_BACKUP_REQUIRED")
                self.land(first)
                receipt = self.turn("first-reply", **context)
                self.assertEqual(receipt["result"]["file_id"], first)
                self.assertEqual(self.turn("second", getattr(self, second), **context)["status"],
                                 "DOCS03_BACKUP_REQUIRED")
                calls = self.stage[first].call_count, self.stage[second].call_count
                self.assertEqual(self.turn("first", getattr(self, first), **context), receipt)
                self.assertEqual(self.turn("first-reply", **context), receipt)
                changed = {**getattr(self, first), "revision": "different"}
                with self.assertRaisesRegex(ValueError, "REQUEST_COLLISION"):
                    self.turn("first", changed, **context)
                self.assertEqual((self.stage[first].call_count, self.stage[second].call_count), calls)
                self.land(second)
                self.assertEqual(self.turn("continue-second", **context)["result"]["file_id"],
                                 second)

    def test_old_explicit_retry_does_not_steal_latest_plain_continue(self):
        for first, second in (("account", "progress"), ("progress", "account")):
            with self.subTest(first=first), TemporaryDirectory() as folder:
                context = {"workspace_dir": Path(folder)}
                self.turn("first", getattr(self, first), **context)
                self.land(first)
                older = self.turn("first-result", **context)
                self.turn("second", getattr(self, second), **context)
                self.land(second)
                latest = self.turn("second-result", **context)
                self.assertEqual(self.turn("older-new-id", getattr(self, first), **context), older)
                self.assertEqual(self.turn("fresh-continue", **context), latest)
                self.assertEqual(self.turn("older-new-id", **context), older)
                self.observe[first].return_value = None
                self.observe[second].return_value = None

    def test_partial_schema_without_requests_resumes_through_original_dispatch(self):
        for first, other in (("account", "progress"), ("progress", "account")):
            with self.subTest(first=first), TemporaryDirectory() as folder:
                scope = self.context["project_id"] + ("|03-progress" if first == "progress" else "")
                context = {"workspace_dir": Path(folder)}

                def interrupted():
                    _, journal = docs03._journal_directory(
                        Path(folder), scope, self.context["conversation_id"], create=True)
                    with closing(sqlite3.connect(journal)) as db, db:
                        db.execute("CREATE TABLE work (id TEXT PRIMARY KEY, number INTEGER NOT NULL, "
                                   "payload TEXT NOT NULL, phase TEXT NOT NULL, output TEXT)")
                    self.assertGreater(journal.stat().st_size, 0)
                    raise KeyboardInterrupt("after a first schema write")

                with self.assertRaises(KeyboardInterrupt):
                    self.turn("first", getattr(self, first), before_dispatch=interrupted, **context)
                self.assertEqual(self.turn("blocked", getattr(self, other), **context)["status"],
                                 "ANOTHER_REQUEST_PENDING")
                self.assertEqual(self.turn("continue-first", **context)["status"], "DOCS03_BACKUP_REQUIRED")
                self.land(first)
                self.assertEqual(self.turn("continue-readback", **context)["result"]["file_id"], first)
                self.observe[first].return_value = None

    def test_partial_schema_with_existing_work_stops_both_routes(self):
        _, journal = docs03._journal_directory(
            self.context["workspace_dir"], self.context["project_id"],
            self.context["conversation_id"], create=True)
        with closing(sqlite3.connect(journal)) as db, db:
            db.execute("CREATE TABLE work (id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO work VALUES ('existing-confirmation')")
        self.assertEqual(self.turn("other-answer", self.progress)["status"],
                         "DOCS03_JOURNAL_RECOVERY_REQUIRED")
        self.stage["progress"].assert_not_called()
        self.stage["account"].assert_not_called()

    def test_empty_journal_from_interrupted_creation_does_not_block_replay(self):
        _, journal = docs03._journal_directory(
            self.context["workspace_dir"], self.context["project_id"] + "|03-progress",
            self.context["conversation_id"], create=True)
        journal.touch(mode=0o600)
        self.assertEqual(self.turn("interrupted-answer", self.progress)["status"],
                         "DOCS03_BACKUP_REQUIRED")
        self.land("progress")
        self.assertEqual(self.turn("continue-answer")["result"]["file_id"], "progress")
        self.stage["progress"].assert_called_once()

    def test_plain_continue_recovers_an_existing_journal(self):
        self.original("account", "old-confirm", self.account)
        self.land("account")
        self.assertEqual(self.turn("new-entry")["result"]["file_id"], "account")

    def test_ambiguous_legacy_pending_stops_without_submitting_either(self):
        self.original("account", "old-confirm", self.account)
        self.original("progress", "old-answer", self.progress)
        self.assertEqual(self.turn("ambiguous")["status"], "DOCS03_MULTIPLE_PENDING_REQUESTS")
        for stage in self.stage.values():
            stage.assert_called_once()

    def test_two_legacy_receipts_are_recovered_by_original_message(self):
        for kind, data in (("account", self.account), ("progress", self.progress)):
            self.original(kind, "old-" + kind, data)
            self.land(kind)
            self.original(kind, "confirmed-" + kind, None)
        self.assertEqual(self.turn("unknown-old-continuation")["status"],
                         "DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION")
        self.assertEqual(self.turn("old-account")["result"]["file_id"], "account")
        self.assertEqual(self.turn("confirmed-progress")["result"]["file_id"], "progress")

    def test_wrong_login_document_and_another_conversation(self):
        self.turn("answer", self.progress)
        with self.assertRaisesRegex(PermissionError, "WRONG_LOGIN_DOCUMENT"):
            self.turn("wrong-doc", document={"documentId": "wrong"})
        with self.assertRaisesRegex(PermissionError, "stale fixture login"):
            self.turn("expired", document={"documentId": "fixture-doc"})
        self.assertEqual(self.turn("other", conversation_id="another-chat")["status"],
                         "NO_PENDING_REQUEST")

    def test_concurrent_new_actions_stage_only_one_pending(self):
        with ThreadPoolExecutor(2) as workers:
            answers = [workers.submit(self.turn, "answer", self.progress),
                       workers.submit(self.turn, "confirm", self.account)]
            self.assertCountEqual([answer.result()["status"] for answer in answers],
                                  ["DOCS03_BACKUP_REQUIRED", "ANOTHER_REQUEST_PENDING"])
        self.assertEqual(sum(stage.call_count for stage in self.stage.values()), 1)
