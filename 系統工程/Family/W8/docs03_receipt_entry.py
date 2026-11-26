"""Use the original Docs login for the 03 write and receipt journal."""
from contextlib import closing
import fcntl
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import sqlite3


def _load_module(name):
    path = Path(__file__).with_name(f"{name}.py")
    spec = spec_from_file_location(f"family_docs03_{name}", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _journal_directory(workspace_dir, project_id, conversation_id, *, create):
    """Resolve one directory in the conversation's persistent host workspace."""
    if not all(isinstance(value, str) and value.strip()
               for value in (project_id, conversation_id)):
        raise ValueError("TRUSTED_CONVERSATION_BINDING_REQUIRED")
    root = Path(workspace_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("DOCS03_WORKSPACE_DIRECTORY_REQUIRED")
    identity = json.dumps([project_id, conversation_id], ensure_ascii=False,
                          separators=(",", ":"))
    scope = sha256(identity.encode()).hexdigest()
    directory = root / f".family03-{scope}"
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or (directory.exists() and
            (not directory.is_dir() or directory.stat().st_mode & 0o077)):
        raise PermissionError("DOCS03_PRIVATE_JOURNAL_DIRECTORY_REQUIRED")
    return directory, directory / f"{scope}.sqlite3"


class _Docs03Session:
    stage = "IDLE"

    def __init__(self, auth, document_id):
        self.auth = auth
        self.document_id = document_id

    def check(self, document):
        self.auth.begin_request()
        if not isinstance(document, dict) or document.get("documentId") != self.document_id:
            raise PermissionError("WRONG_LOGIN_DOCUMENT")
        self.auth.check_revision(document.get("revisionId"))
        return self.auth.require_login()

    def begin(self, action, document):
        self.check(document)
        return "RUN_PENDING_ACTION"

    def select(self, document, number, *, build_menu, payload):
        self.check(document)
        menu = build_menu(self.auth)
        if number != 3 or menu.auth.family_login is not self.auth:
            raise PermissionError("DOCS03_MENU_BINDING_MISMATCH")
        return menu.select(3, payload=payload)


def run_docs03(*, auth, document_id, document, project_id, conversation_id,
               build_menu, recover_receipt, message_id, payload=None,
               workspace_dir=None, private_dir=None, prepare_writeback=None,
               progress_answers=False):
    """Use fresh native Docs metadata and the same host workspace on every turn.

    Supply workspace_dir for new runs. The host must reuse it and pass trusted
    project, conversation and message IDs. private_dir supports already-started
    requests whose original journal location is known.
    """
    if (workspace_dir is None) == (private_dir is None):
        raise ValueError("DOCS03_EXACTLY_ONE_JOURNAL_LOCATION_REQUIRED")
    if payload is not None and not (
            isinstance(payload, dict) and (
                _is_progress_write(payload) if progress_answers
                else payload.get("action") == "confirm_account")):
        raise ValueError("DOCS03_CONFIRMATION_PAYLOAD_REQUIRED")
    session = _Docs03Session(auth, document_id)
    session.check(document)
    if workspace_dir is not None:
        private_dir, journal = _journal_directory(
            workspace_dir, project_id, conversation_id, create=payload is not None)
        if payload is None and not journal.is_file():
            return {"status": "DOCS03_JOURNAL_MISSING"}
    entry = _load_module("conversation_entry").ConversationEntry(
        project_id=project_id, conversation_id=conversation_id, private_dir=private_dir,
        session=session, mobile=None, read_page=lambda: document, patch_page=None,
        prepare_account=None, build_menu=build_menu, recover_receipt=recover_receipt,
        prepare_writeback=prepare_writeback, progress_answers=progress_answers,
    )
    if payload is None:
        return entry.handle_message(message_id, "繼續")
    return entry.handle_message(message_id, number=3, payload=payload)


def _is_progress_write(payload):
    return (set(payload) == {"revision", "question_id", "key", "reply"}
            or (payload.get("action") == "restore"
                and set(payload) == {"action", "version", "slot", "revision"}))


def run_project_docs03_turn(*, auth, document_id, document, project_id,
                            conversation_id, workspace_dir, message_id,
                            account_turn, progress_turn, payload=None):
    """Route 03 confirmation, answers and plain continue to their original journal.

    Each trusted callback accepts (message_id, payload) and uses the same
    household, project, conversation and workspace passed to this router.
    """
    if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 256:
        raise ValueError("STABLE_MESSAGE_ID_REQUIRED")
    if payload is None:
        requested = None
    elif isinstance(payload, dict) and payload.get("action") == "confirm_account":
        requested = "account"
    elif isinstance(payload, dict) and _is_progress_write(payload):
        requested = "progress"
    else:
        raise ValueError("DOCS03_CONFIRMATION_PAYLOAD_REQUIRED")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("TRUSTED_CONVERSATION_BINDING_REQUIRED")
    _Docs03Session(auth, document_id).check(document)
    hosts = {"account": (project_id, account_turn),
             "progress": (project_id + "|03-progress", progress_turn)}
    directory, routes = _journal_directory(
        workspace_dir, project_id + "|03-router", conversation_id, create=True)
    if routes.is_symlink():
        raise PermissionError("DOCS03_PRIVATE_JOURNAL_DIRECTORY_REQUIRED")
    lock_path = directory / "turn.lock"
    with (os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a") as lock,
          closing(sqlite3.connect(routes)) as route):
        fcntl.flock(lock, fcntl.LOCK_EX)
        route.executescript("""
            CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, kind TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS interrupted_dispatch (
                slot INTEGER PRIMARY KEY CHECK(slot=1),
                id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recovered_replies (
                id TEXT PRIMARY KEY, original_id TEXT NOT NULL);
        """)
        reply_id = message_id
        alias = route.execute(
            "SELECT original_id FROM recovered_replies WHERE id=?", (reply_id,)
        ).fetchone()
        if alias:
            message_id = alias[0]
        active, finished, known = [], [], {}
        for kind, (scope, _) in hosts.items():
            _, journal = _journal_directory(workspace_dir, scope, conversation_id, create=False)
            if not journal.exists():
                continue
            if journal.is_symlink():
                raise PermissionError("DOCS03_PRIVATE_JOURNAL_DIRECTORY_REQUIRED")
            if journal.stat().st_size == 0:
                # The host may have stopped after creating the file, before creating its schema.
                continue
            with closing(sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True)) as work:
                row = work.execute("SELECT phase FROM work ORDER BY rowid DESC LIMIT 1").fetchone()
                original = work.execute(
                    "SELECT phase FROM work WHERE id=? UNION ALL "
                    "SELECT w.phase FROM replies r JOIN work w ON w.id=r.work_id "
                    "WHERE r.id=? LIMIT 1", (message_id, message_id)
                ).fetchone()
                if original:
                    known[kind] = original[0]
            if row and row[0] in ("open", "running", "writeback"):
                active.append(kind)
            elif row and row[0] == "done":
                finished.append(kind)
        if len(active) > 1:
            return {"status": "DOCS03_MULTIPLE_PENDING_REQUESTS"}
        dispatch_id = None
        with route:
            prior = route.execute("SELECT kind FROM turns WHERE id=?", (message_id,)).fetchone()
            if len(known) > 1:
                return {"status": "DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION"}
            previous = prior[0] if prior else next(iter(known), None)
            if previous is not None and requested is not None and previous != requested:
                raise ValueError("REQUEST_COLLISION")
            kind = previous or requested
            interrupted = route.execute(
                "SELECT id, kind, payload FROM interrupted_dispatch WHERE slot=1"
            ).fetchone()
            completed_replay = previous is not None and known.get(previous) == "done"
            if interrupted and (message_id == interrupted[0] or not completed_replay):
                original_id, original_kind, saved_payload = interrupted
                original_payload = json.loads(saved_payload)
                if payload is not None and (requested != original_kind or payload != original_payload):
                    if message_id == original_id:
                        raise ValueError("REQUEST_COLLISION")
                    return {"status": "ANOTHER_REQUEST_PENDING"}
                if active and active[0] != original_kind:
                    return {"status": "DOCS03_MULTIPLE_PENDING_REQUESTS"}
                if reply_id != original_id:
                    route.execute("INSERT OR IGNORE INTO recovered_replies VALUES(?,?)",
                                  (reply_id, original_id))
                message_id, kind, payload = original_id, original_kind, original_payload
                dispatch_id = original_id
            elif active:
                # A known, completed message can only read its stored result.
                if kind is not None and kind != active[0] and known.get(kind) != "done":
                    return {"status": "ANOTHER_REQUEST_PENDING"}
                kind = kind or active[0]
            elif kind is None:
                if len(finished) == 1:
                    kind = finished[0]
                elif len(finished) > 1:
                    last = route.execute("SELECT kind FROM turns ORDER BY rowid DESC LIMIT 1").fetchone()
                    if last is None:
                        return {"status": "DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION"}
                    kind = last[0]
                else:
                    return {"status": "NO_PENDING_REQUEST"}
            if not interrupted and payload is not None and not active and kind not in known:
                # Record the original input before the business journal can receive it.
                route.execute("INSERT INTO interrupted_dispatch VALUES(1,?,?,?)", (
                    message_id, kind, json.dumps(payload, ensure_ascii=False, allow_nan=False)))
                dispatch_id = message_id
            route.execute("INSERT OR IGNORE INTO turns VALUES(?,?)", (message_id, kind))
        try:
            result = hosts[kind][1](message_id, payload)
        except ValueError:
            # A rejected request must not prevent the next valid action.
            with route:
                route.execute("DELETE FROM interrupted_dispatch WHERE id=?", (dispatch_id,))
            raise
        if dispatch_id is not None:
            with route:
                route.execute("DELETE FROM interrupted_dispatch WHERE id=?", (dispatch_id,))
        return result


def run_project_docs03_progress(*, auth, document_id, document, project_id,
                                conversation_id, workspace_dir, message_id,
                                login_account, client_id, family_alias,
                                progress_file_id, download_progress, build_menu,
                                payload=None, verified_backup=None):
    """Stage or resume one XLSX answer using the original 03 menu.

    The trusted host supplies the fixed Excel ID and a fresh download callback.
    build_menu(login, path) binds that local Excel to the original project menu.
    After a backup, pass its actual ID and path; issue the returned update once.
    """
    if (getattr(auth, "user_id", None), getattr(auth, "client_id", None)) != (login_account, client_id):
        raise PermissionError("DOCS03_PROJECT_ACCOUNT_MISMATCH")
    if not isinstance(project_id, str) or not project_id.strip() or not progress_file_id:
        raise ValueError("DOCS03_PROGRESS_BINDING_REQUIRED")
    if verified_backup is not None and (
            not isinstance(verified_backup, tuple) or len(verified_backup) != 2):
        raise ValueError("DOCS03_BACKUP_ID_AND_PATH_REQUIRED")
    expected_name = family_alias + "_03_股票配置選擇進度.xlsx"
    planner = _load_module("family03_plans")

    def current_menu():
        file_id, path = download_progress(progress_file_id)
        path = Path(path)
        if file_id != progress_file_id or path.name != expected_name:
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        menu = build_menu(auth, path)
        if menu.auth.family_login is not auth:
            raise PermissionError("DOCS03_MENU_BINDING_MISMATCH")
        return menu, path

    class ProgressMenu:
        def __init__(self, menu):
            self.menu, self.auth = menu, menu.auth

        def select(self, number, *, payload):
            response = self.menu.select(number, payload=payload)
            if response["status"] != "FAMILY03_PROGRESS_WRITEBACK_REQUIRED":
                return response
            staged = response["result"]
            if (staged["本人"], staged["檔名"]) != (family_alias, expected_name):
                raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
            lookup = staged["讀回入口"]
            key = {"file_id":progress_file_id, "client_id":client_id,
                   "request_id":lookup["event_id"], "source_revision":lookup["source_revision"],
                   "operation":"save_progress"}
            return {"status":"DB_WRITEBACK_REQUIRED", "result":{**staged, "receipt_key":key}}

    def observe(key):
        if (key["file_id"], key["client_id"], key["operation"]) != (
                progress_file_id, client_id, "save_progress"):
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        menu, downloaded = current_menu()
        result = menu.select(3, payload={"action":"progress_receipt",
            "event_id":key["request_id"], "source_revision":key["source_revision"]})["result"]
        if (result.get("本人"), result.get("檔名"), result.get("事件識別"), result.get("revision")) != (
                family_alias, expected_name, key["request_id"], sha256(downloaded.read_bytes()).hexdigest()):
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        return result, downloaded

    def recover(key):
        observed, _ = observe(key)
        if observed["status"] == "FAMILY03_PROGRESS_EVENT_FOUND":
            return {**key, "status":"PERSISTED_REMOTE_VERIFIED", "progress_receipt":observed}
        return None

    def prepare(staged):
        key = staged["receipt_key"]
        observed, downloaded = observe(key)
        backup_id, backup_path = verified_backup or (None, None)
        update = planner.prepare_progress_update(staged, observed, file_id=progress_file_id,
            downloaded_id=progress_file_id, downloaded_path=downloaded,
            backup_id=backup_id, backup_path=backup_path)
        if update["status"] == "FAMILY03_PROGRESS_BACKUP_REQUIRED":
            return {**update, "status":"DOCS03_BACKUP_REQUIRED", "request_id":key["request_id"]}
        if update["status"] == "FAMILY03_PROGRESS_SOURCE_CHANGED":
            return {"status":"DOCS03_PREVIEW_STALE", "request_id":key["request_id"],
                    "text":"作答進度已有更新，請重新開啟 03 接續最新題目。"}
        # The first observation missed a save that landed before preflight.
        if update["status"] == "FAMILY03_PROGRESS_EVENT_FOUND":
            return {**key, "status":"PERSISTED_REMOTE_VERIFIED", "progress_receipt":update}
        return {**update, "status":"DOCS03_DRIVE_UPDATE_REQUIRED", "request_id":key["request_id"]}

    result = run_docs03(auth=auth, document_id=document_id, document=document,
        project_id=project_id + "|03-progress", conversation_id=conversation_id,
        workspace_dir=workspace_dir, message_id=message_id, payload=payload,
        build_menu=lambda _: ProgressMenu(current_menu()[0]), recover_receipt=recover,
        prepare_writeback=prepare, progress_answers=True)
    if result["status"] == "PERSISTED_REMOTE_VERIFIED":
        receipt = result["result"]
        if (receipt["file_id"], receipt["client_id"]) != (progress_file_id, client_id):
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
    return result


def run_project_docs03(*, auth, document_id, document, project_id,
                       conversation_id, workspace_dir, message_id,
                       project_name, login_account, client_id, family_alias,
                       downloaded_db_path, official_drive_file_id,
                       verified_drive_sha256, mutation_staging_dir,
                       download_original, payload=None,
                       backup_original=None, replace_original=None,
                       native_writeback=False, verified_backup=None,
                       progress_file_id=None, download_progress=None):
    """Connect 03 to same-account Drive callbacks supplied by the trusted host.

    backup_original(file_id) returns a newly saved backup's ID and download path.
    replace_original accepts the authorized native Drive update arguments.
    Supply both to let the journal own submission, or omit both for staged-only use.
    With native_writeback=True the host obtains a backup on a separate tool
    call, passes its ID and downloaded path as verified_backup, and submits the
    returned update arguments once. Continue with a fresh original download.
    Pass the registered progress_file_id and its download callback to recheck
    the confirmed workbook revision before an original-ledger update.
    """
    if not callable(download_original):
        raise TypeError("DOCS03_DRIVE_DOWNLOAD_REQUIRED")
    managed = backup_original is not None or replace_original is not None
    if managed and not (callable(backup_original) and callable(replace_original)):
        raise TypeError("DOCS03_DRIVE_BACKUP_AND_UPDATE_REQUIRED")
    if (type(native_writeback) is not bool or (native_writeback and managed)
            or (verified_backup is not None and not native_writeback)):
        raise ValueError("DOCS03_INVALID_WRITEBACK_MODE")
    if verified_backup is not None and (
            not isinstance(verified_backup, tuple) or len(verified_backup) != 2
            or not isinstance(verified_backup[0], str) or not verified_backup[0]
            or not isinstance(verified_backup[1], (str, Path))):
        raise ValueError("DOCS03_BACKUP_ID_AND_PATH_REQUIRED")
    if (getattr(auth, "user_id", None), getattr(auth, "client_id", None)) != (login_account, client_id):
        raise PermissionError("DOCS03_PROJECT_ACCOUNT_MISMATCH")
    check_progress = progress_file_id is not None or download_progress is not None
    if check_progress and not (isinstance(progress_file_id, str) and progress_file_id.strip()
                               and callable(download_progress) and (managed or native_writeback)):
        raise ValueError("DOCS03_PROGRESS_RECHECK_CONFIGURATION")
    sources = {
        "login_account": login_account,
        "client_id": client_id,
        "family_alias": family_alias,
        "downloaded_db_path": downloaded_db_path,
        "official_drive_file_id": official_drive_file_id,
        "verified_drive_sha256": verified_drive_sha256,
    }

    class ConfirmedProgressMenu:
        def __init__(self, menu):
            self.menu, self.auth = menu, menu.auth

        def select(self, number, *, payload):
            response = self.menu.select(number, payload=payload)
            if response["status"] == "DB_WRITEBACK_REQUIRED":
                response = {**response, "result":{**response["result"],
                    "progress_binding":{"file_id":progress_file_id, "revision":payload["revision"]}}}
            return response

    def build_menu(login):
        menu = _load_module("on_demand_project").build_project_menu(
            family_login=login, project_name=project_name,
            mutation_staging_dir=mutation_staging_dir, **sources)
        return ConfirmedProgressMenu(menu) if check_progress else menu

    def recover_receipt(key):
        stager = _load_module("on_demand_mutations").OnDemandMutationStager(
            auth=auth, staging_dir=mutation_staging_dir, **sources)
        return stager.receipt_reader(download_original)(key)

    def prepare_writeback(staged):
        plan = staged["writeback_plan"]
        binding_values = (login_account, client_id, official_drive_file_id)
        if (plan["account"], plan["client_id"], plan["file_id"]) != binding_values:
            raise PermissionError("DOCS03_WRITEBACK_BINDING_MISMATCH")
        progress_binding = staged.get("progress_binding")
        if progress_binding is not None:
            if not check_progress or progress_binding["file_id"] != progress_file_id:
                raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        elif check_progress:
            raise ValueError("DOCS03_CONFIRMED_PROGRESS_BINDING_REQUIRED")
        if native_writeback and verified_backup is None:
            return {"status":"DOCS03_BACKUP_REQUIRED", "file_id":official_drive_file_id,
                    "request_id":staged["request_id"]}
        backup_id, backup_path = (verified_backup if native_writeback
                                  else backup_original(official_drive_file_id))
        fresh_id, fresh_path = download_original(official_drive_file_id)
        if fresh_id != official_drive_file_id:
            raise PermissionError("DOCS03_WRITEBACK_BINDING_MISMATCH")
        if progress_binding is not None:
            received_id, progress_path = download_progress(progress_file_id)
            if received_id != progress_file_id:
                raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
            if sha256(Path(progress_path).read_bytes()).hexdigest() != progress_binding["revision"]:
                return {"status":"DOCS03_PREVIEW_STALE", "request_id":staged["request_id"],
                        "text":"股票方案已有更新，請回 03 重新查看全帳戶目標，再確認一次。"}
        drive = _load_module("on_demand_drive_io")
        binding = drive.Binding(*binding_values, family_alias)
        writer = drive.OnDemandWriteback(binding, auth.require_login)
        if drive.inspect(fresh_path, binding)["sha256"] != plan["source"]["sha256"]:
            return {
                "status": "DOCS03_PREVIEW_STALE",
                "request_id": staged["request_id"],
                "text": "帳本已有更新，請回 03 重新查看全帳戶目標，再確認一次。",
            }
        authorized = writer.authorize_update(
            plan, fresh_path, backup_path, backup_id,
            candidate_file_uri=plan["candidate"]["path"], local_upload_supported=True)
        if native_writeback:
            return {"status":"DOCS03_DRIVE_UPDATE_REQUIRED", "request_id":staged["request_id"],
                    "update_file_args":authorized["update_file_args"]}
        return lambda: replace_original(**authorized["update_file_args"])

    result = run_docs03(
        auth=auth, document_id=document_id, document=document,
        project_id=project_id, conversation_id=conversation_id,
        workspace_dir=workspace_dir, message_id=message_id, payload=payload,
        build_menu=build_menu, recover_receipt=recover_receipt,
        prepare_writeback=prepare_writeback if managed or native_writeback else None)
    if result.get("status") == "PERSISTED_REMOTE_VERIFIED":
        receipt = result["result"]
        if (receipt.get("file_id"), receipt.get("client_id")) != (official_drive_file_id, client_id):
            raise PermissionError("DOCS03_RECEIPT_BINDING_MISMATCH")
    return result
