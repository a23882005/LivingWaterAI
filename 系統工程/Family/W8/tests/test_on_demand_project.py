"""W8 no-host ChatGPT runtime smoke: four-account isolation and user-triggered menu."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

FAMILY = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("test_w8_chatgpt_on_demand", ROOT/"on_demand_project.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FakeFamilyLogin:
    def __init__(self, account, client):
        self.user_id = account
        self.client_id = client
        self.active = False
    def login(self, password):
        if password != "synthetic-secret":
            raise PermissionError("bad credential")
        self.active = True
    def require_login(self):
        if not self.active:
            raise PermissionError("Login required")
        return self.user_id
    def logout(self):
        self.active = False


def sample_db(path,client,alias):
    spec=importlib.util.spec_from_file_location("w8_reader_test", FAMILY/"W5"/"family_input.py")
    reader=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE family_member_identity(client_id TEXT,family_alias TEXT)")
        db.execute("INSERT INTO family_member_identity VALUES(?,?)",(client,alias))
        for table in reader.TABLES:
            db.execute('CREATE TABLE "'+table+'" (client_id TEXT)')
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ChatGPTRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client="fam_"+"a"*32
        self.account="JO"
        self.db=Path(self.temp.name)/"verified_copy.db"
        self.hash=sample_db(self.db,self.client,"Joseph")
        self.login=FakeFamilyLogin(self.account,self.client)

    def menu(self,**changes):
        args=dict(family_login=self.login,project_name="Joseph",
                  login_account=self.account,client_id=self.client,
                  family_alias="Joseph",downloaded_db_path=self.db,
                  official_drive_file_id="synthetic-file-id",
                  verified_drive_sha256=self.hash)
        args.update(changes)
        return M.build_project_menu(**args)

    def test_first_message_requests_password_then_loads_menu(self):
        menu=self.menu()
        self.assertEqual(menu.welcome()["status"],"LOGIN_REQUIRED")
        out=menu.login("synthetic-secret")
        self.assertEqual(out["status"],"READY")
        self.assertIn("Joseph",out["menu"])

    def test_authentication_bound_real_w5_snapshot(self):
        menu=self.menu()
        menu.login("synthetic-secret")
        out=menu.select(2)
        self.assertEqual(out["status"],"COMPLETED")
        self.assertEqual(out["result"]["client_id"],self.client)
        self.assertEqual(out["result"]["source_sha256"],self.hash)
        self.assertEqual(out["result"]["trade_authorization"],"NONE")

    def test_wrong_account_no_login(self):
        with self.assertRaisesRegex(PermissionError,"FAMILY_LOGIN_OWNER_MISMATCH"):
            self.menu(login_account="AR")

    def test_wrong_database_owner_rejected(self):
        menu=self.menu(client_id=self.client)
        menu.login("synthetic-secret")
        bad_hash=hashlib.sha256(b"wrong").hexdigest()
        bad_menu=self.menu(verified_drive_sha256=bad_hash)
        bad_menu.login("synthetic-secret")
        with self.assertRaisesRegex(RuntimeError,"FAMILY_DRIVE_SOURCE_CHANGED"):
            bad_menu.select(2)

    def test_unknown_portfolio_not_fake_deployed(self):
        menu=self.menu()
        menu.login("synthetic-secret")
        result=menu.select(4,payload={"question":"SOXX今天能買嗎"})
        self.assertEqual(result["status"],"DATA_UNAVAILABLE")
        self.assertEqual(result["result"]["trade_authorization"],"NONE")

    def test_logout_invalidates_local_session(self):
        menu=self.menu()
        menu.login("synthetic-secret")
        out=menu.select(14,payload={"action":"logout"})
        self.assertEqual(out["status"],"COMPLETED")
        self.assertEqual(menu.select(2)["status"],"LOGIN_REQUIRED")


if __name__=="__main__":
    unittest.main()
