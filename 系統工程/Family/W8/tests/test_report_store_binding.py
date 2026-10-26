"""Regression: menu 12/13 report storage must match the signed-in member."""
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("official_family_entry", ROOT / "official_family_entry.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class FakeAuth:
    def require_login(self):
        return "JO"


class ReportStoreBindingTests(unittest.TestCase):
    def make_menu(self, store, renderer=None):
        return ENTRY.build_official_family_menu(
            auth=FakeAuth(), project_name="Joseph", login_account="JO",
            client_id="fam_" + "a"*32,
            coordinator=SimpleNamespace(headers={"family.joseph": {}}),
            principal_provider=lambda: SimpleNamespace(subject="account:JO"),
            report_store=store, report_renderer=renderer)

    def test_reject_other_family_report_store(self):
        with self.assertRaisesRegex(PermissionError, "OFFICIAL_REPORT_OWNER_MISMATCH"):
            self.make_menu(SimpleNamespace(login_account="AR", client_id="fam_"+"a"*32))

    def test_reject_other_client_report_store(self):
        with self.assertRaisesRegex(PermissionError, "OFFICIAL_REPORT_OWNER_MISMATCH"):
            self.make_menu(SimpleNamespace(login_account="JO", client_id="fam_"+"b"*32))

    def test_authorized_store_wires_report_view(self):
        store = SimpleNamespace(login_account="JO", client_id="fam_"+"a"*32)
        menu = self.make_menu(store)
        self.assertIn("previous_report", menu.handlers)
        self.assertIn("read_portfolio", menu.handlers)
        self.assertNotIn("generate_report", menu.handlers)

    def test_renderer_wires_generation_and_rejects_source_override(self):
        store = SimpleNamespace(login_account="JO", client_id="fam_"+"a"*32)
        menu = self.make_menu(store, renderer=lambda source, payload: {})
        self.assertIn("generate_report", menu.handlers)
        with self.assertRaisesRegex(PermissionError, "REPORT_SOURCE_OVERRIDE_REJECTED"):
            menu.select(13, payload={"client_id": "another_family"})

    def test_report_rejects_renderer_using_wrong_source(self):
        store = SimpleNamespace(login_account="JO", client_id="fam_"+"a"*32)
        cid = "fam_"+"a"*32
        snap = {"schema_version": "Family.W5.W1Snapshot.v1",
                "client_id": cid,
                "identity": {"client_id": cid, "family_alias": "Joseph"},
                "source_sha256": "test_sha", "payload_digest": "test_payload",
                "tables": {}}
        menu = self.make_menu(store, renderer=lambda source, payload: {
            "client_id": cid, "source_db_sha256": "test_sha",
            "source_digest": "WRONG"})
        with patch.object(ENTRY.OfficialFamilyEntry, "current_snapshot", return_value=snap):
            with self.assertRaisesRegex(PermissionError, "REPORT_OUTPUT_SOURCE_MISMATCH"):
                menu.select(13, payload={})

    def test_renderer_requires_store(self):
        with self.assertRaisesRegex(ValueError, "OFFICIAL_REPORT_STORE_REQUIRED"):
            ENTRY.build_official_family_menu(
                auth=FakeAuth(), project_name="Joseph", login_account="JO",
                client_id="fam_"+"a"*32,
                coordinator=SimpleNamespace(headers={"family.joseph": {}}),
                principal_provider=lambda: SimpleNamespace(subject="account:JO"),
                report_renderer=lambda payload: payload)


if __name__ == "__main__":
    unittest.main()
