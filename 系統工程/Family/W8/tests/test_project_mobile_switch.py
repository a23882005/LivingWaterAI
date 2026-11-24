from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_mobile_switch import route_mobile_switch


class NativeSwitchTests(unittest.TestCase):
    def test_no_live_prompt_means_start_with_original_request(self):
        session = Mock(stage="IDLE")
        session.begin.return_value = "AWAIT_SWITCH"
        for reply in [None, True]:
            self.assertEqual(route_mobile_switch(session, "07", {}, choice=reply), "AWAIT_SWITCH")
        session.begin.assert_called_with("07", {})
        session.choose_switch.assert_not_called()

    def test_same_revision_continues_to_password(self):
        session = Mock(stage="AWAIT_SWITCH")
        session._base.revision = session._snapshot.return_value.revision = "v1"
        session.choose_switch.return_value = "PREPARE_ACCOUNT_DB"
        self.assertEqual(route_mobile_switch(session, "07", {}, choice=True), "PREPARE_ACCOUNT_DB")
        session.choose_switch.assert_called_once_with(True)

    def test_changed_revision_reopens_original_action(self):
        session = Mock(stage="AWAIT_SWITCH", pending_action=("03", {"original": 2}))
        session._base.revision = "v1"
        session._snapshot.return_value = SimpleNamespace(revision="v2")
        route_mobile_switch(session, "07", {}, choice=True)
        session.choose_switch.assert_not_called()
        session.begin.assert_called_once_with(("03", {"original": 2}), {})

    def test_cancel_and_pending_mobile(self):
        session = Mock(stage="AWAIT_SWITCH")
        route_mobile_switch(session, "07", {}, choice=False)
        session.choose_switch.assert_called_once_with(False)
        session.stage = "AWAIT_PASSWORD"
        self.assertEqual(route_mobile_switch(session, "07", {}, choice=True), "AWAIT_PASSWORD")
        session._snapshot.assert_not_called()

    def test_late_cancel_creates_no_login_and_staged_write_waits_for_readback(self):
        session = Mock(stage="IDLE")
        self.assertEqual(route_mobile_switch(session, "07", {}, choice=False), "CANCELLED")
        session.stage = "READBACK_LOGIN"
        self.assertEqual(route_mobile_switch(session, "07", {}, choice=False), "READBACK_LOGIN")
        session.begin.assert_not_called()
        session.cancel.assert_not_called()
