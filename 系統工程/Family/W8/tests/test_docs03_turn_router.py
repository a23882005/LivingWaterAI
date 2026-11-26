"""Exercise Menu 03 continuation across both original journals."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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
        for kind, operation in (("account", "adjust_target"), ("progress", "save_progress")):
            key = {"file_id": kind, "client_id": "fixture-client", "operation": operation,
                   "request_id": kind, "fingerprint": "a" * 64}
            self.stage[kind] = Mock(return_value={
                "status": "DB_WRITEBACK_REQUIRED", "result": {"receipt_key": key}})
            self.observe[kind] = Mock(return_value=None)

    def original(self, kind, message, payload, **overrides):
        context = self.context | overrides
        if kind == "progress":
            context["project_id"] += "|03-progress"
        return docs03.run_docs03(
            **context, message_id=message, payload=payload,
            build_menu=lambda auth: SimpleNamespace(
                auth=SimpleNamespace(family_login=auth), select=self.stage[kind]),
            recover_receipt=self.observe[kind],
            prepare_writeback=lambda _: {"status": "DOCS03_BACKUP_REQUIRED"},
            progress_answers=kind == "progress")

    def turn(self, message, payload=None, **overrides):
        return docs03.run_project_docs03_turn(
            **(self.context | overrides), message_id=message, payload=payload,
            account_turn=lambda mid, data: self.original("account", mid, data, **overrides),
            progress_turn=lambda mid, data: self.original("progress", mid, data, **overrides))

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
