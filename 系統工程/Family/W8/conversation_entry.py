"""Receive one native ChatGPT turn. Private per-conversation SQLite stores business work only.

Tool callbacks come from the trusted project runner. read_page returns native structuredContent.
The session and the mobile proof stay in this conversation's live execution context.
"""
from contextlib import closing, contextmanager
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def find_saved_confirmation(db, payload_json):
    """Find an already verified Menu 03 receipt for an exact historical input."""
    for request_id, output in db.execute(
            "SELECT id, output FROM work WHERE number=3 AND payload=? AND phase='done' "
            "ORDER BY rowid DESC", (payload_json,)):
        if json.loads(output).get("status") == "PERSISTED_REMOTE_VERIFIED":
            return request_id
    return None


def is_native_drive_update(submission, receipt):
    if not isinstance(submission, dict) or submission.get("status") != "DOCS03_DRIVE_UPDATE_REQUIRED":
        return False
    args = submission.get("update_file_args")
    return (isinstance(args, dict) and args.get("fileId") == receipt["file_id"]
            and isinstance(args.get("file_uri"), str) and bool(args["file_uri"].strip()))


class ConversationEntry:
    def __init__(self, *, private_dir, project_id, conversation_id, session, mobile,
                 read_page, patch_page, prepare_account, build_menu, recover_receipt,
                 prepare_writeback=None, progress_answers=False, prepare_native_writeback=None,
                 complete_native_writeback=None, continue_latest_completed=False):
        if not all(isinstance(v, str) and v.strip() for v in (project_id, conversation_id)):
            raise ValueError("TRUSTED_CONVERSATION_BINDING_REQUIRED")
        folder = Path(private_dir).resolve(strict=True)
        if not folder.is_dir() or folder.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_CONVERSATION_DIRECTORY_REQUIRED")
        scope = sha256(encode([project_id, conversation_id]).encode()).hexdigest()
        self.scope = scope
        self.file = folder / (scope + ".sqlite3")
        os.close(os.open(self.file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600))
        self.session, self.mobile = session, mobile
        self.read_page, self.patch_page = read_page, patch_page
        self.prepare_account, self.build_menu = prepare_account, build_menu
        self.recover_receipt = recover_receipt
        self.prepare_writeback = prepare_writeback
        self.prepare_native_writeback = prepare_native_writeback
        self.complete_native_writeback = complete_native_writeback
        self.progress_answers = progress_answers
        self.continue_latest_completed = continue_latest_completed
        self.lock = RLock()
        self.bound_request = None
        self._rejected_write = None
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS work (
                    id TEXT PRIMARY KEY, number INTEGER NOT NULL, payload TEXT NOT NULL,
                    phase TEXT NOT NULL, output TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending ON work((1))
                    WHERE phase IN ('open','running','writeback');
                CREATE TABLE IF NOT EXISTS replies (id TEXT PRIMARY KEY, work_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS choices (id TEXT PRIMARY KEY, revision TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS logouts (id TEXT PRIMARY KEY, done INTEGER NOT NULL);
            """)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.file, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    @contextmanager
    def _turn(self):
        # Lock only while handling a message. No process waits for a user's next message.
        with self.lock, self.file.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def handle_message(self, message_id, text="", *, number=None, payload=None, notification_id=None):
        """message_id comes from the host and is stable on redelivery, never from message text.
        For a menu answer the host supplies the original number and structured business payload.
        For a mobile callback supply its authentic notification_id; free text never supplies proof.
        """
        if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 256:
            raise ValueError("STABLE_MESSAGE_ID_REQUIRED")
        text = text.strip()
        with self._turn():
            with self.db() as db:
                logout = db.execute("SELECT done FROM logouts WHERE id=?", (message_id,)).fetchone()
                if logout and logout["done"]:
                    return {"status": "LOGGED_OUT", "text": "Goodbye 👋"}
                pending_logout = db.execute("SELECT id FROM logouts WHERE done=0 LIMIT 1").fetchone()
            if pending_logout or logout or text == "14" or number in (14, "14"):
                return self._logout(message_id if not pending_logout else pending_logout["id"])
            # A late notification for an obsolete challenge cannot begin or authorize new work.
            if notification_id is not None and notification_id != self.mobile.request_id:
                return {"status": "UNRELATED_NOTIFICATION"}
            if number is None and text in {str(i) for i in range(1, 14)} | {f"{i:02}" for i in range(1, 14)}:
                number = int(text)
            if number is not None:
                if str(number) not in {str(i) for i in range(1, 14)} | {f"{i:02}" for i in range(1, 14)}:
                    raise ValueError("INVALID_MENU_NUMBER")
                number = int(number)
            if payload is not None and not isinstance(payload, dict):
                raise ValueError("INVALID_MENU_PAYLOAD")
            confirm_account = number == 3 and (
                self.progress_answers or (payload or {}).get("action") == "confirm_account")
            payload_json = encode(payload) if number is not None else None
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                item = db.execute("SELECT * FROM work WHERE id=?", (message_id,)).fetchone()
                if item and number is not None and (item["number"] != number or item["payload"] != payload_json):
                    raise ValueError("REQUEST_COLLISION")
                if not item:
                    item = db.execute("SELECT w.* FROM replies r JOIN work w ON w.id=r.work_id WHERE r.id=?",
                                      (message_id,)).fetchone()
                    if item and confirm_account and (item["number"] != number or item["payload"] != payload_json):
                        raise ValueError("REQUEST_COLLISION")
                if not item and confirm_account:
                    saved_id = find_saved_confirmation(db, payload_json)
                    if saved_id is not None:
                        item = db.execute("SELECT * FROM work WHERE id=?", (saved_id,)).fetchone()
                        db.execute("INSERT INTO replies VALUES(?,?)", (message_id, saved_id))
                if not item:
                    item = db.execute("SELECT * FROM work WHERE phase IN ('open','running','writeback')").fetchone()
                    if confirm_account and item and (item["number"] != number or item["payload"] != payload_json):
                        return {"status": "ANOTHER_REQUEST_PENDING"}
                    if not item and number is not None:
                        db.execute("INSERT INTO work VALUES(?,?,?,'open',NULL)", (message_id, number, payload_json))
                        item = db.execute("SELECT * FROM work WHERE id=?", (message_id,)).fetchone()
                    elif item:
                        db.execute("INSERT INTO replies VALUES(?,?)", (message_id, item["id"]))
                    elif self.bound_request and self.session.stage != "IDLE":
                        item = db.execute("SELECT * FROM work WHERE id=?", (self.bound_request,)).fetchone()
                        if item:
                            db.execute("INSERT INTO replies VALUES(?,?)", (message_id, item["id"]))
                    elif text in ("好了", "繼續"):
                        query = ("SELECT * FROM work WHERE phase='done' ORDER BY rowid DESC LIMIT 1"
                                 if self.continue_latest_completed
                                 else "SELECT * FROM work ORDER BY rowid DESC LIMIT 1")
                        item = db.execute(query).fetchone()
                        if item:
                            db.execute("INSERT INTO replies VALUES(?,?)", (message_id, item["id"]))
            if not item or item["phase"] in ("closed", "cancelled"):
                return {"status": "NO_PENDING_REQUEST"}
            if self.bound_request and self.bound_request != item["id"] and self.session.stage != "IDLE":
                return {"status": "ANOTHER_REQUEST_PENDING"}
            if text in ("取消", "取消切換") and item["phase"] == "open" and self.session.stage in ("IDLE", "AWAIT_SWITCH", "PREPARE_ACCOUNT_DB", "AWAIT_PASSWORD"):
                return self._cancel(item)
            stage = self.session.stage
            was_asked = stage == "AWAIT_SWITCH"
            if stage == "IDLE":
                stage = self.session.begin((item["number"], json.loads(item["payload"])), self.read_page())
                self.bound_request = item["id"]
            if stage == "AWAIT_SWITCH":
                if not was_asked or text not in ("同意", "切換到這裡"):
                    return {"status": stage, "text": "要切換到這個對話繼續嗎？"}
                revision = self.session._base.revision
                with self.db() as db:
                    prior = db.execute("SELECT revision FROM choices WHERE id=?", (message_id,)).fetchone()
                    if prior and prior["revision"] != revision:
                        return {"status": stage, "text": "登入登記已更新，要切換到這裡嗎？"}
                    db.execute("INSERT OR IGNORE INTO choices VALUES(?,?)", (message_id, revision))
                stage = self.session.choose_switch(True)
            if stage == "PREPARE_ACCOUNT_DB":
                self.prepare_account(self.session)
                return self.mobile.start(self.session)
            if stage == "AWAIT_PASSWORD":
                answer = self.mobile.poll(self.session, notification_id)
                if answer["status"] == "CANCELLED":
                    return self._cancel(item)
                if answer["status"] != "READBACK_LOGIN":
                    return answer
                stage = self.session.stage
            if stage == "READBACK_LOGIN":
                result = self._write()
                if result != "RUN_PENDING_ACTION":
                    return {"status": result}
            elif stage != "RUN_PENDING_ACTION":
                return {"status": stage}
            return self._dispatch(item["id"])

    def _cancel(self, item):
        self.session.cancel()
        self.mobile.clear()
        with self.db() as db:
            db.execute("UPDATE work SET phase='cancelled' WHERE id=? AND phase='open'", (item["id"],))
        return {"status": "CANCELLED"}

    def _write(self):
        if not self.session._sent:
            args = self.session.patch_args()
            try:
                receipt = self.patch_page(**args)
            except OSError:
                receipt = None  # The same write may have landed. Read it first.
            if isinstance(receipt, dict) and (receipt.get("error") or {}).get("commit_status") == "not_committed":
                self._rejected_write = receipt
        page = self.read_page()
        try:
            if self._rejected_write is not None:
                result = self.session.reject_write(self._rejected_write, page)
            else:
                result = self.session.finish_write(page)
            self._rejected_write = None
            return result
        except RuntimeError as exc:
            if str(exc) == "SPACE_WRITE_NOT_OBSERVED_READBACK_REQUIRED":
                return "AWAIT_REGISTRATION_READBACK"
            if str(exc) == "SPACE_WRITE_UNCONFIRMED_RECHECK":
                self._rejected_write = None
                return "RECHECK_PENDING_ACTION"
            raise

    def _logout(self, message_id):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO logouts VALUES(?,0)", (message_id,))
            db.execute("UPDATE work SET phase='closed' WHERE phase='done'")
            db.execute("UPDATE work SET phase='cancelled' WHERE phase IN ('open','running','writeback')")
        self.mobile.clear()
        if self.session.stage == "READBACK_LOGIN" and self.session._sent:
            status = self._write()
            if status == "AWAIT_REGISTRATION_READBACK":
                return {"status": status}
        if self.session.stage == "READBACK_LOGOUT":
            status = self._write()
        else:
            auth = self.session.auth
            page = self.read_page() if auth and auth.active and auth.login_revision else None
            status = self.session.logout_request(page)
            if status == "RELEASE_WITH_PATCH":
                status = self._write()
        if status == "Goodbye 👋":
            with self.db() as db:
                db.execute("UPDATE logouts SET done=1 WHERE id=?", (message_id,))
            self.bound_request = None
            return {"status": "LOGGED_OUT", "text": status}
        return {"status": status}

    def _dispatch(self, key):
        page = self.read_page()
        self.session.check(page)  # Required for read-only requests and redelivery too.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM work WHERE id=?", (key,)).fetchone()
            phase = row["phase"]
            if phase == "done":
                return json.loads(row["output"])
            if phase == "open":
                db.execute("UPDATE work SET phase='running' WHERE id=?", (key,))
        if phase == "writeback":
            return self._finish_writeback(key, json.loads(row["output"]))
        elif phase in ("open", "running"):
            original = json.loads(row["payload"])
            tracked_confirmation = (row["number"] == 3 and isinstance(original, dict)
                                    and (self.progress_answers or original.get("action") == "confirm_account"))
            confirmed = (row["number"] in (1, 3, 6, 10, 11) and isinstance(original, dict)
                         and original.get("owner_confirmed") is True and isinstance(original.get("record"), dict))
            if phase == "running" and not (row["number"] == 7 or confirmed or tracked_confirmation):
                return {"status": "AWAIT_ORIGINAL_RESULT", "request_id": key}
            # These confirmed writes can only stage a candidate here. The host cannot
            # receive an upload plan until its receipt key is committed in this journal.
            if confirmed and "request_id" not in original:
                original["request_id"] = sha256(encode([self.scope, key]).encode()).hexdigest()
            try:
                result = self.session.select(page, row["number"], build_menu=self.build_menu, payload=original)
            except ValueError:
                if tracked_confirmation:
                    # A rejected preview has no emitted Drive plan. Release
                    # the pending slot so the member can confirm a new preview.
                    with self.db() as db:
                        db.execute("UPDATE work SET phase='cancelled' WHERE id=? AND phase='running'", (key,))
                raise
        else:
            return {"status": "AWAIT_ORIGINAL_RESULT", "request_id":key}
        if not isinstance(result, dict):
            raise ValueError("INVALID_MENU_RESPONSE")
        phase = "done"
        if result.get("status") == "DB_WRITEBACK_REQUIRED":
            if not (result.get("result") or {}).get("receipt_key"):
                raise RuntimeError("STAGED_WRITE_MISSING_RECEIPT_KEY")
            phase = "writeback"
            if tracked_confirmation and self.prepare_writeback is not None:
                result = {**result, "_managed_writeback": "ready"}
        with self.db() as db:
            db.execute("UPDATE work SET phase=?,output=? WHERE id=?", (phase, encode(result), key))
        if result.get("_managed_writeback") == "ready":
            return self._finish_writeback(key, result)
        return result

    def _finish_writeback(self, key, staged):
        receipt = staged["result"]["receipt_key"]
        saved = self.recover_receipt(receipt)
        if (saved is None and staged.get("_managed_writeback") == "ready"
                and self.prepare_writeback is not None):
            attempted = {**staged, "_managed_writeback": "attempted"}
            if self.prepare_native_writeback is None:
                submission = self.prepare_writeback(staged["result"])
            else:
                submission = self.prepare_native_writeback(staged["result"], self.file, key, encode(attempted))
            status = submission.get("status") if isinstance(submission, dict) else None
            if status in (
                    "DOCS03_BACKUP_REQUIRED", "DOCS03_DRIVE_WRITE_PENDING"):
                return submission
            if status == "DOCS03_PREVIEW_STALE":
                with self.db() as db:
                    db.execute("UPDATE work SET phase='done',output=? WHERE id=? AND phase='writeback'",
                               (encode(submission), key))
                return submission
            if status == "PERSISTED_REMOTE_VERIFIED":
                saved = submission
            else:
                if not callable(submission) and not is_native_drive_update(submission, receipt):
                    raise ValueError("DOCS03_INVALID_WRITEBACK_RESPONSE")
                # A crash or ambiguous connector response after this point must
                # recover by reading the original receipt, never by resubmitting.
                staged = attempted
                if self.prepare_native_writeback is None:
                    with self.db() as db:
                        db.execute("UPDATE work SET output=? WHERE id=? AND phase='writeback'", (encode(staged), key))
                if isinstance(submission, dict):
                    return submission
                try:
                    submission()
                except OSError:
                    pass
                saved = self.recover_receipt(receipt)
        if saved is None:
            return {"status": "AWAIT_DRIVE_CONFIRMATION", "request_id":key}
        if (saved.get("status") != "PERSISTED_REMOTE_VERIFIED"
                or any(saved.get(k) != value for k, value in receipt.items())):
            raise ValueError("REMOTE_RECEIPT_MISMATCH")
        result = {**staged, "status":"PERSISTED_REMOTE_VERIFIED", "result": saved}
        result.pop("pending_operation", None)
        result.pop("_managed_writeback", None)
        output = encode(result)
        if self.complete_native_writeback is None:
            with self.db() as db:
                db.execute("UPDATE work SET phase='done',output=? WHERE id=?", (output, key))
        else:
            self.complete_native_writeback(receipt, self.file, key, output)
        return result
