"""Contract tests for two independent messages and delivery after a committed write."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import test_on_demand_mutations as mutation_fixture

on_demand_project = mutation_fixture.load(
    Path(__file__).resolve().parents[1] / "on_demand_project.py", "conversation_project_test")


class BoundSession:
    """Small V2.1 interface fixture; the hosted verification service is tested separately."""
    def __init__(self, active=False):
        self.active = active
        self.auth = None
        self.stage = "IDLE"
        self._sent = False
        self.dispatch = Mock(return_value={"status": "COMPLETED", "result": "07"})
        self.key = "a" * 64

    def begin(self, action, page):
        if self.active and page["owner"] == "current":
            return "RUN_PENDING_ACTION"
        self._base = SimpleNamespace(revision=page.get("revision", "r1"))
        self.stage = "AWAIT_SWITCH" if page["owner"] else "PREPARE_ACCOUNT_DB"
        return self.stage

    def choose_switch(self, agreed):
        assert agreed is True and self.stage == "AWAIT_SWITCH"
        self.stage = "PREPARE_ACCOUNT_DB"
        return self.stage

    def mobile_begin(self):
        assert self.stage == "AWAIT_PASSWORD"
        return {"request_id": self.key, "envelope": "fixture-envelope"}

    def mobile_finish(self, receipt):
        assert receipt == {"request_id": self.key, "status": "verified"}
        self.stage = "READBACK_LOGIN"

    def patch_args(self):
        assert not self._sent
        self._sent = True
        return {"intent": self.stage}

    def finish_write(self, page):
        if page["owner"] != "current":
            raise RuntimeError("SPACE_WRITE_NOT_OBSERVED_READBACK_REQUIRED")
        self.stage, self._sent, self.active = "IDLE", False, True
        return "RUN_PENDING_ACTION"

    def cancel(self):
        self.stage = "IDLE"

    def logout_request(self, page):
        self.active = False
        self.cancel()
        return "Goodbye 👋"

    def check(self, page):
        if not self.active or page["owner"] != "current":
            raise PermissionError("fixture auth revoked")

    def select(self, page, number, *, build_menu, payload):
        self.check(page)
        return self.dispatch(number, payload)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.live = {}
        self.page = {"owner": "previous"}
        self.state = "pending"
        self.patch = Mock(side_effect=self.land)
        self.check = Mock(side_effect=lambda request_id: {"request_id": request_id, "status": self.state})
        self.recover = Mock(return_value=None)
        self.session = BoundSession()
        self.key = {"request_id":"record-1", "file_id":"test-file", "client_id":"test-client",
                    "operation":"record_event", "fingerprint":"c"*64}

    def land(self, **args):
        self.page["owner"] = "current"
        return {}

    def entry(self, cid="conversation"):
        return on_demand_project.open_conversation(
            self.live, project_id="fixture", conversation_id=cid, private_dir=self.folder,
            make_session=lambda: self.session, verification_origin="https://verify.example",
            begin_tool=lambda request_id, envelope: {"request_id":request_id,
                        "url":"https://verify.example/verify/" + "b"*64},
            check_tool=self.check, read_page=lambda:dict(self.page), patch_page=self.patch,
            prepare_account=lambda session:setattr(session, "stage", "AWAIT_PASSWORD"),
            build_menu=Mock(), recover_receipt=self.recover)

    def open_verification(self):
        self.assertEqual(self.entry().handle_message("first", "07")["status"], "AWAIT_SWITCH")
        self.assertEqual(self.entry().handle_message("consent", "同意")["status"], "AWAIT_VERIFICATION")

    def test_separate_turns_replay_and_deliberate_new_selection(self):
        self.open_verification()
        self.assertEqual(self.entry().handle_message("waiting", "好了")["status"], "VERIFICATION_PENDING")
        self.session.dispatch.assert_not_called()
        self.state = "verified"
        first = self.entry().handle_message("reply", "好了")
        self.assertEqual(self.entry().handle_message("reply", "好了"), first)
        self.assertEqual(self.entry().handle_message("another reply", "好了"), first)
        self.session.dispatch.assert_called_once_with(7, None)
        self.assertTrue(all(c.kwargs["request_id"] == self.session.key for c in self.check.call_args_list))
        self.entry().handle_message("new selection", "07")
        self.assertEqual(self.session.dispatch.call_count, 2)

    def test_concurrent_copies_deliver_once(self):
        self.open_verification()
        self.state = "verified"
        with ThreadPoolExecutor(2) as workers:
            out = list(workers.map(lambda _: self.entry().handle_message("reply", "好了"), range(2)))
        self.assertEqual(out[0], out[1])
        self.session.dispatch.assert_called_once()

    def test_03_original_answer_survives_cold_runner_without_old_consent(self):
        entry = self.entry()
        entry.handle_message("answer", number=3, payload={"answer":"14 年"})
        entry.handle_message("consent", "同意")
        previous = self.session
        self.live.clear()
        self.session = BoundSession()
        again = self.entry().handle_message("consent", "同意")
        self.assertEqual(again["status"], "AWAIT_SWITCH")
        self.assertEqual(self.entry().handle_message("fresh consent", "同意")["status"], "AWAIT_VERIFICATION")
        self.state = "verified"
        self.entry().handle_message("finish", "好了")
        previous.dispatch.assert_not_called()
        self.session.dispatch.assert_called_once_with(3, {"answer":"14 年"})

    def test_old_consent_cannot_apply_to_new_registration_revision(self):
        self.open_verification()
        self.live.clear()
        self.session = BoundSession()
        self.page["revision"] = "r2"
        self.assertEqual(self.entry().handle_message("new-poll", "好了")["status"], "AWAIT_SWITCH")
        self.assertEqual(self.entry().handle_message("consent", "同意")["status"], "AWAIT_SWITCH")
        self.assertEqual(self.entry().handle_message("new-consent", "同意")["status"], "AWAIT_VERIFICATION")

    def test_readback_pending_does_not_dispatch_or_resend_patch(self):
        self.open_verification()
        self.state = "verified"
        self.patch.side_effect = TimeoutError()
        self.assertEqual(self.entry().handle_message("reply", "好了")["status"], "AWAIT_REGISTRATION_READBACK")
        self.session.dispatch.assert_not_called()
        self.page["owner"] = "current"
        self.entry().handle_message("later", "繼續")
        self.session.dispatch.assert_called_once()
        self.patch.assert_called_once()

    def test_cancel_and_late_callback_keep_previous_owner(self):
        self.open_verification()
        self.assertEqual(self.entry().handle_message("cancel", "取消")["status"], "CANCELLED")
        self.assertEqual(self.entry().handle_message("late", notification_id=self.session.key)["status"],
                         "UNRELATED_NOTIFICATION")
        self.assertEqual(self.page["owner"], "previous")
        self.session.dispatch.assert_not_called()

    def test_logout_cancels_pending_and_late_reply(self):
        self.open_verification()
        self.assertEqual(self.entry().handle_message("out", "14")["status"], "LOGGED_OUT")
        self.assertEqual(self.entry().handle_message("late", "好了")["status"], "NO_PENDING_REQUEST")
        self.assertEqual(self.page["owner"], "previous")
        self.session.dispatch.assert_not_called()

    def test_local_logout_needs_no_space_read(self):
        entry = self.entry()
        entry.read_page = Mock(side_effect=AssertionError("no locally owned login"))
        self.assertEqual(entry.handle_message("out", "14")["status"], "LOGGED_OUT")

    def test_definitively_rejected_logout_retries_release_before_goodbye(self):
        entry = self.entry()
        self.session.stage = "READBACK_LOGOUT"
        self.session._sent = True
        entry._rejected_write = {"error": {"commit_status":"not_committed"}}
        def rejected(receipt, page):
            self.session._sent = False
            return "RELEASE_WITH_PATCH"
        self.session.reject_write = Mock(side_effect=rejected)
        self.assertEqual(entry.handle_message("out", "14")["status"], "RELEASE_WITH_PATCH")
        self.session.finish_write = Mock(return_value="Goodbye 👋")
        self.assertEqual(entry.handle_message("again", "繼續")["status"], "LOGGED_OUT")
        self.patch.assert_called_once()

    def test_replayed_result_requires_current_login(self):
        self.open_verification()
        self.state = "verified"
        self.entry().handle_message("ok", "好了")
        self.page["owner"] = "another"
        self.assertEqual(self.entry().handle_message("first", "07")["status"], "AWAIT_SWITCH")

    def test_stable_id_rejects_a_different_payload(self):
        self.entry().handle_message("first", number=3, payload={"answer":"a"})
        with self.assertRaisesRegex(ValueError, "REQUEST_COLLISION"):
            self.entry().handle_message("first", number=3, payload={"answer":"b"})

    def test_other_conversation_has_separate_pending_work(self):
        self.entry().handle_message("first", "07")
        self.session = BoundSession()
        self.assertEqual(self.entry("new").handle_message("later", "好了")["status"], "NO_PENDING_REQUEST")

    def test_no_proof_in_business_journal(self):
        self.open_verification()
        self.assertNotIn(b"fixture-envelope", self.entry().file.read_bytes())
        self.assertNotIn(self.session.key.encode(), self.entry().file.read_bytes())

    def test_written_but_not_replied_reopens_from_fresh_receipt(self):
        self.page["owner"], self.session.active = "current", True
        self.session.dispatch.return_value = {"status":"DB_WRITEBACK_REQUIRED",
            "result":{"status":"STAGED_NOT_PERSISTED", "receipt_key":self.key}}
        original = {"owner_confirmed":True, "record":{"event_id":"event"}}
        self.assertEqual(self.entry().handle_message("write", number=11, payload=original)["status"],
                         "DB_WRITEBACK_REQUIRED")
        saved = {**self.key, "status":"PERSISTED_REMOTE_VERIFIED","business_result":{"event_id":"event"}}
        self.live.clear()
        self.session = BoundSession(active=True)
        self.assertEqual(self.entry().handle_message("after-restart","好了")["status"],"AWAIT_DRIVE_CONFIRMATION")
        self.recover.return_value = saved
        result = self.entry().handle_message("after-restart","好了")
        self.assertEqual(result["result"], saved)
        self.session.dispatch.assert_not_called()
        self.assertEqual(self.entry().handle_message("write",number=11,payload=original),result)

    def test_writeback_rejects_another_requests_receipt(self):
        self.page["owner"], self.session.active = "current", True
        self.session.dispatch.return_value = {"status":"DB_WRITEBACK_REQUIRED","result":{"receipt_key":self.key}}
        self.entry().handle_message("write", "11")
        self.recover.return_value = {**self.key,"request_id":"another","status":"PERSISTED_REMOTE_VERIFIED"}
        with self.assertRaisesRegex(ValueError, "REMOTE_RECEIPT_MISMATCH"):
            self.entry().handle_message("reply", "好了")


class ReceiptTests(unittest.TestCase):
    def test_actual_writer_recovers_one_version_from_same_db_after_restart(self):
        import hashlib
        fixture = mutation_fixture.MutationStageTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        payload = fixture.payload()
        first = fixture.stager.stage("adjust_target", payload)
        key = first["receipt_key"]
        remote = fixture.source.parent / "fresh-remote.db"
        remote.write_bytes(Path(first["writeback_plan"]["candidate"]["path"]).read_bytes())
        fresh = mutation_fixture.MUT.OnDemandMutationStager(
            auth=mutation_fixture.Auth(), login_account=fixture.stager.login_account,
            client_id=fixture.stager.client_id, family_alias=fixture.stager.family_alias,
            official_drive_file_id=fixture.stager.file_id, downloaded_db_path=remote,
            verified_drive_sha256=hashlib.sha256(remote.read_bytes()).hexdigest(), staging_dir=remote.parent)
        download = Mock(return_value=(fresh.file_id, remote))
        recovered = fresh.receipt_reader(download)(key)
        download.assert_called_once_with(fresh.file_id)
        self.assertEqual(recovered["business_result"], first["business_result"])
        self.assertEqual(fresh.stage("adjust_target", payload), recovered)
        payload["record"]["source_reference"] = "different content"
        with self.assertRaisesRegex(ValueError,"REQUEST_COLLISION"):
            fresh.stage("adjust_target", payload)
        with self.assertRaisesRegex(PermissionError,"RECEIPT_BINDING_MISMATCH"):
            fresh.recover_receipt(key, remote, "another file")
        with sqlite3.connect(remote) as db:
            self.assertEqual(db.execute("SELECT version_no FROM final_target_version").fetchall(), [(1,)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM _family_io_receipts").fetchone(), (1,))
