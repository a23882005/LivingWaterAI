"""Regression for 2026-10-25 Arthur 01: 13 questions finished, no allocation saved."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from family_menu import FamilyMenu


class Auth:
    def __init__(self):
        self.active = True

    def require_login(self):
        if not self.active:
            raise PermissionError("LOGIN")

    def login(self, user, password):
        if user != "AR" or password != "synthetic":
            raise PermissionError("LOGIN")
        self.active = True

    def logout(self):
        self.active = False


def menu(handlers=None, completion_checks=None):
    return FamilyMenu(Auth(), project_name="Arthur", login_account="AR",
                      handlers=handlers, completion_checks=completion_checks)


def test_01_no_handler_keeps_pending_and_never_returns_completed_menu():
    ui = menu()
    got = ui.select(1)
    assert got["status"] == "FIRST_ALLOCATION_ENGINE_NOT_CONNECTED"
    assert got["pending_operation"] == "first_allocation"
    assert "menu" not in got
    assert ui.pending == (1, {})


def test_01_interview_complete_is_not_first_allocation_complete():
    ui = menu({"first_allocation": lambda payload: {
        "status": "INTERVIEW_COMPLETE", "answers_count": 13,
    }})
    got = ui.select("01")
    assert got["status"] == "FIRST_ALLOCATION_IN_PROGRESS"
    assert got["result"]["answers_count"] == 13
    assert "menu" not in got
    assert ui.pending == (1, {})


def test_01_claimed_saved_without_trusted_verifier_remains_pending():
    ui = menu({"first_allocation": lambda payload: {"status": "COMPLETED"}})
    got = ui.select(1)
    assert got["status"] == "FIRST_ALLOCATION_IN_PROGRESS"


def test_01_verifier_must_explicitly_confirm_full_save_readback():
    seen = []
    def verifier(result):
        seen.append(result)
        return result.get("target_receipt") == "T" and result.get("deployment_receipt") == "D" and result.get("save_readback") == "OK"
    handler = lambda p: {"target_receipt": "T", "deployment_receipt": "D", "save_readback": "OK"}
    ui = menu({"first_allocation": handler}, {"first_allocation": verifier})
    got = ui.select(1)
    assert got["status"] == "COMPLETED"
    assert got["menu"].count("｜") == 14
    assert len(seen) == 1 and ui.pending is None


def test_01_verifier_rejection_preserves_pending():
    ui = menu({"first_allocation": lambda p: {"status": "INTERVIEW_COMPLETE"}},
              {"first_allocation": lambda r: False})
    assert ui.select(1)["status"] == "FIRST_ALLOCATION_IN_PROGRESS"
    assert ui.pending == (1, {})


def test_01_handler_failure_keeps_pending():
    def broken(_payload):
        raise RuntimeError("engine unavailable")
    ui = menu({"first_allocation": broken})
    with pytest.raises(RuntimeError):
        ui.select(1)
    assert ui.pending == (1, {})


def test_other_menu_operation_unchanged():
    ui = menu({"read_portfolio": lambda p: {"status": "READ_OK"}})
    got = ui.select(2)
    assert got["status"] == "COMPLETED"
    assert got["result"]["status"] == "READ_OK"
    assert got["menu"].count("｜") == 14
