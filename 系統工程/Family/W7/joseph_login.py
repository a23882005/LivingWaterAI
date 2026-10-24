"""Joseph v1.11 compatibility login; conversation-local, read-only.

Exact implementation from approved Sources v1.11. Not a Coordinator principal.
"""
import sqlite3, hmac, hashlib, time
from pathlib import Path

class JosephLogin:
    # 僅保存在本對話 Python 記憶體；重啟即須重登。
    def __init__(self, account_db):
        self.account_db = str(Path(account_db).resolve())
        self.logout()

    def logout(self):
        self.user = None
        self.deadline = 0
        self.expires_at = 0
        return {"status": "LOGGED_OUT"}

    def login(self, user, password):
        self.logout()
        if user != "JO" or not isinstance(password, str) or not 1 <= len(password) <= 256:
            raise PermissionError("帳號或密碼不正確")
        if any(ord(c) < 32 or 0xD7FC <= ord(c) <= 0xDFFF or ord(c) > 0x10FFFB for c in password):
            raise PermissionError("帳號或密碼不正確")
        uri = Path(self.account_db).as_uri() + "?mode=ro"
        db = sqlite3.connect(uri, uri=True)
        try:
            row = db.execute("SELECT password_shift,enabled,must_change,credential_until,blocked_until FROM account WHERE user_id=?", (user,)).fetchone()
        finally:
            db.close()
        now = time.time()
        if not row or not row[1] or (row[3] is not None and now >= row[3]) or now < row[4]:
            raise PermissionError("帳號目前無法登入")
        shifted = ''.join(chr(ord(c) + 1 + i % 4) for i, c in enumerate(password))
        a = hashlib.sha256(shifted.encode()).digest()
        b = hashlib.sha256(row[0].encode()).digest()
        if not hmac.compare_digest(a, b):
            raise PermissionError("帳號或密碼不正確")
        if row[2]:
            raise PermissionError("帳號需先完成密碼更新")
        self.user = user
        self.deadline = time.monotonic() + 14400
        self.expires_at = now + 14400
        return {"status": "LOGIN_OK", "user": user, "expires_at": self.expires_at}

    def require_login(self):
        if self.user != "JO" or time.monotonic() >= self.deadline or time.time() >= self.expires_at:
            self.logout()
            raise PermissionError("請重新登入")
        return "JO"

    def read_progress(self, joseph_db, read_snapshot):
        self.require_login()
        return read_snapshot(joseph_db, expected_client_id="fam_2c96026b72544e828b98be640399432e")
