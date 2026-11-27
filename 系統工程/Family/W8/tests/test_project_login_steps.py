import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_login_steps import (docs_login_route, finish_docs_login_and_open_03,
                                 finish_login_and_open_07, prepare_mobile_request)


def document(text):
    return {"documentId": "home", "revisionId": "r1", "tabs": [{
        "tabId": "first", "body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": text + "\n"}}]}}]}}]}


class ProjectLoginStepsTest(unittest.TestCase):
    marker = "a" * 64
    meta = {"id": "home", "modified_time": "2026-11-24T05:09:29.940Z"}

    def route(self, text, **kw):
        return docs_login_route(document(text), document_id="home", **kw)

    def test_legacy_reads_native_file_time(self):
        self.assertEqual(self.route(self.marker), {"status": "READ_MODIFIED_TIME", "file_id": "home"})

    def test_legacy_exact_four_hour_boundary_and_write_guard(self):
        from datetime import datetime
        end = datetime.fromisoformat("2026-11-24T17:09:29.940+08:00").timestamp()
        self.assertEqual(self.route(self.marker, metadata=self.meta, now=end - 1)["status"], "AWAIT_SWITCH")
        self.assertEqual(self.route(self.marker, metadata=self.meta, now=end),
                         {"status": "PREPARE_ACCOUNT_DB", "revision": "r1", "tab_id": "first", "expires_at": end})

    def test_json_uses_recorded_time(self):
        record = json.dumps({"session_marker": self.marker, "expires_at": 15000})
        self.assertEqual(self.route(record, now=15000)["status"], "PREPARE_ACCOUNT_DB")
        self.assertEqual(self.route(record, now=14999)["status"], "AWAIT_SWITCH")

    def test_blank_register(self):
        self.assertEqual(self.route("")["status"], "PREPARE_ACCOUNT_DB")

    def test_other_household_and_invalid_data(self):
        with self.assertRaises(ValueError):
            docs_login_route(document(""), document_id="other")
        for text, meta in [(self.marker, {"id": "other"}), (self.marker, {"id": "home"}),
                           (self.marker, {"id": "home", "modified_time": "2026-11-24T05:09:29"}),
                           ("broken", None), ('{"session_marker":"short","expires_at":123}', None)]:
            with self.subTest(text=text, meta=meta), self.assertRaises(ValueError):
                self.route(text, metadata=meta)

    def test_preparation_uses_the_same_mobile_controller(self):
        session = Mock(stage="PREPARE_ACCOUNT_DB")
        self.assertIs(prepare_mobile_request(session, "private", raw_path="original.db"), session.mobile_begin.return_value)
        session.prepare_password.assert_called_once_with("private", raw_path="original.db")
        session.stage = "AWAIT_PASSWORD"
        prepare_mobile_request(session, "private")
        session.prepare_password.assert_called_once()

    def test_readback_and_original_menu_in_same_call(self):
        session, page, builder = Mock(pending_action=("07", None)), object(), object()
        session.finish_write.return_value = "RUN_PENDING_ACTION"
        result = finish_login_and_open_07(session, page, build_menu=builder)
        self.assertIs(result, session.select.return_value)
        self.assertEqual([c[0] for c in session.method_calls], ["finish_write", "select"])
        session.select.assert_called_once_with(page, 7, build_menu=builder)

    def test_incomplete_readback_never_runs_menu(self):
        session = Mock(pending_action="07")
        session.finish_write.side_effect = RuntimeError("SPACE_WRITE_NOT_OBSERVED_READBACK_REQUIRED")
        with self.assertRaises(RuntimeError):
            finish_login_and_open_07(session, {}, build_menu=Mock())
        session.select.assert_not_called()

    def test_other_actions_stay_with_their_original_handler(self):
        for pending in ["03", (7, {"record": "answer"}), None]:
            session = Mock(pending_action=pending)
            with self.subTest(pending=pending), self.assertRaises(ValueError):
                finish_login_and_open_07(session, {}, build_menu=Mock())
            session.finish_write.assert_not_called()

    def test_native_03_registration_readback_and_home_open_matrix(self):
        cases = {
            "valid": None,
            "wrong document": (ValueError, "WRONG_LOGIN_DOCUMENT"),
            "no revision": (ValueError, "LOGIN_DOCUMENT_REVISION_REQUIRED"),
            "empty registration": (ValueError, "LOGIN_REGISTRATION_INCOMPLETE"),
            "wrong marker": (ValueError, "LOGIN_REGISTRATION_INCOMPLETE"),
            "wrong expiry": (ValueError, "LOGIN_REGISTRATION_INCOMPLETE"),
            "expired": (ValueError, "LOGIN_REGISTRATION_INCOMPLETE"),
            "wrong auth": (PermissionError, "FAMILY_PROJECT_ACCOUNT_MISMATCH"),
            "stale revision": (PermissionError, "stale revision"),
            "wrong menu login": (PermissionError, "DOCS03_MENU_BINDING_MISMATCH"),
        }
        for pending in (3, "03", (3, None), ("03", None)):
            for case, error in cases.items():
                with self.subTest(pending=pending, case=case):
                    page = document(json.dumps({"session_marker": self.marker, "expires_at": 15000}))
                    auth = Mock(user_id="MOU")
                    auth.require_login.return_value = "MOU"
                    menu = Mock()
                    menu.auth.family_login = auth
                    builder = Mock(return_value=menu)
                    params = dict(document_id="home", login_account="MOU", pending_action=pending,
                                  expected_marker=self.marker, expected_expiry=15000,
                                  build_menu=builder, now=14999)
                    if case == "wrong document":
                        page["documentId"] = "other"
                    elif case == "no revision":
                        page.pop("revisionId")
                    elif case == "empty registration":
                        page = document("")
                    elif case == "wrong marker":
                        params["expected_marker"] = "b" * 64
                    elif case == "wrong expiry":
                        params["expected_expiry"] = 15001
                    elif case == "expired":
                        params["now"] = 15000
                    elif case == "wrong auth":
                        auth.user_id = "AR"
                    elif case == "stale revision":
                        auth.check_revision.side_effect = PermissionError("stale revision")
                    elif case == "wrong menu login":
                        menu.auth.family_login = Mock()
                    if error:
                        with self.assertRaisesRegex(*error):
                            finish_docs_login_and_open_03(auth, page, **params)
                        menu.select.assert_not_called()
                        if case != "wrong menu login":
                            builder.assert_not_called()
                        if case not in ("stale revision", "wrong menu login"):
                            auth.confirm_registration.assert_not_called()
                    else:
                        self.assertIs(finish_docs_login_and_open_03(auth, page, **params),
                                      menu.select.return_value)
                        auth.confirm_registration.assert_called_once_with(self.marker, "r1")
                        auth.check_revision.assert_called_once_with("r1")
                        builder.assert_called_once_with(auth)
                        menu.select.assert_called_once_with(3)

    def test_native_03_finish_never_dispatches_other_menus_or_a_write(self):
        for pending in (None, "07", (3, {"action": "confirm_account"})):
            with self.subTest(pending=pending):
                auth, builder = Mock(user_id="MOU"), Mock()
                with self.assertRaisesRegex(ValueError, "ORIGINAL_MENU_03_REQUIRED"):
                    finish_docs_login_and_open_03(auth, {}, document_id="home", login_account="MOU",
                        pending_action=pending, expected_marker=self.marker, expected_expiry=15000,
                        build_menu=builder)
                auth.confirm_registration.assert_not_called()
                builder.assert_not_called()
