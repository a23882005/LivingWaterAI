"""Regression: menu 12/13 report storage must match the signed-in member."""
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("official_family_entry", ROOT / "official_family_entry.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class FakeAuth:
    def require_login(self):
        return "JO"


class ReportStoreBindingTests(unittest.TestCase):
    def make_menu(self, store):
        return ENTRY.build_official_family_menu(
            auth=FakeAuth(), project_name="Joseph", login_account="JO",
            client_id="fam_" + "a"*32,
            coordinator=SimpleNamespace(headers={"family.joseph": {}}),
            principal_provider=lambda: SimpleNamespace(subject="account:JO"),
            report_store=store)

    def test_reject_other_family_report_store(self):
        with self.assertRaisesRegex(PermissionError, "OFFICIAL_REPORT_OWNER_MISMATCH"):
            self.make_menu(SimpleNamespace(login_account="AR", client_id="fam_"+"a"*32))

    def test_reject_other_client_report_store(self):
        with self.assertRaisesRegex(PermissionError, "OFFICIAL_REPORT_OWNER_MISMATCH"):
            self.make_menu(SimpleNamespace(login_account="JO", client_id="fam_"+"b"*32))

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
