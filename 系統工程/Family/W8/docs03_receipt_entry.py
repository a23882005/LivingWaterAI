"""Use the original Docs login for the 03 write and receipt journal."""
from contextlib import closing, contextmanager
import fcntl
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
from shutil import copyfileobj
import sqlite3
from tempfile import NamedTemporaryFile


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


def _digest_stream(stream):
    digest = sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _pin_candidate(workspace_dir, project_id, conversation_id, source, revision, suffix):
    """Keep verified upload bytes beside the journal, outside turn-local downloads."""
    directory, _ = _journal_directory(workspace_dir, project_id, conversation_id, create=False)
    path = Path(source)
    if not isinstance(revision, str) or len(revision) != 64 or any(
            ch not in "0123456789abcdef" for ch in revision):
        raise ValueError("DOCS03_INVALID_CANDIDATE_DIGEST")
    target = directory / f"upload-{revision}.{suffix}"
    with path.open("rb") as original, NamedTemporaryFile(dir=directory) as temp:
        copyfileobj(original, temp)
        temp.flush()
        with open(temp.name, "rb") as copy:
            if _digest_stream(copy) != revision:
                raise ValueError("DOCS03_CANDIDATE_DIGEST_MISMATCH")
        os.fsync(temp.fileno())
        try:
            os.link(temp.name, target)
        except FileExistsError:
            with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), "rb") as existing:
                if (os.fstat(existing.fileno()).st_mode & 0o077
                        or _digest_stream(existing) != revision):
                    raise ValueError("DOCS03_CANDIDATE_DIGEST_MISMATCH")
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return str(target)


class _DriveWriteSlot:
    """Serialize 03 upload authorizations to one Drive file in a shared host workspace."""

    def __init__(self, workspace_dir, file_id, project_id, conversation_id):
        self.workspace = workspace_dir
        self.file_id = file_id
        self.owner = (project_id, conversation_id)

    @contextmanager
    def connect(self, *, create):
        _, path = _journal_directory(self.workspace, "03-drive-write", self.file_id, create=create)
        if not create and not path.exists():
            yield None
            return
        if path.is_symlink():
            raise PermissionError("DOCS03_PRIVATE_JOURNAL_DIRECTORY_REQUIRED")
        if create:
            os.close(os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS current_write "
                       "(slot INTEGER PRIMARY KEY CHECK(slot=1), owner TEXT NOT NULL)")
            yield db

    def _token(self, key):
        if key["file_id"] != self.file_id:
            raise PermissionError("DOCS03_WRITEBACK_BINDING_MISMATCH")
        return json.dumps([self.owner, key], sort_keys=True)

    @contextmanager
    def preflight(self, key):
        """Serialize read-only checks without persisting an upload reservation."""
        owner = self._token(key)
        directory, _ = _journal_directory(self.workspace, "03-drive-write", self.file_id, create=True)
        path = directory / "preflight.lock"
        with os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.connect(create=False) as db:
                existing = None if db is None else db.execute(
                    "SELECT owner FROM current_write WHERE slot=1").fetchone()
            yield existing in (None, (owner,))

    def acquire(self, key):
        owner = self._token(key)
        with self.connect(create=True) as db:
            db.execute("INSERT OR IGNORE INTO current_write VALUES(1,?)", (owner,))
            return db.execute("SELECT owner FROM current_write WHERE slot=1").fetchone() == (owner,)

    def release(self, key):
        owner = self._token(key)
        with self.connect(create=False) as db:
            if db is not None:
                db.execute("DELETE FROM current_write WHERE owner=?", (owner,))

    def finish(self, key, result):
        if (isinstance(result, dict) and result.get("status") == "PERSISTED_REMOTE_VERIFIED"
                and all(result.get(field) == value for field, value in key.items())):
            self.release(key)
        return result


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
               progress_answers=False, write_slot=None):
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
    conversation = _load_module("conversation_entry")

    def observe(key):
        result = recover_receipt(key)
        return write_slot.finish(key, result) if write_slot is not None else result

    def prepare(staged):
        if write_slot is None:
            return prepare_writeback(staged)
        key = staged["receipt_key"]
        pending = {"status":"DOCS03_DRIVE_WRITE_PENDING", "request_id":key["request_id"],
                   "text":"另一筆 03 正在寫回同一檔案。完成原筆讀回後，再輸入「繼續」。"}
        with write_slot.preflight(key) as available:
            if not available:
                return pending
            try:
                result = prepare_writeback(staged)
            except Exception:
                write_slot.release(key)
                raise
            if conversation.is_native_drive_update(result, key):
                if not write_slot.acquire(key):
                    return pending
            else:
                write_slot.release(key)
            return result

    entry = conversation.ConversationEntry(
        project_id=project_id, conversation_id=conversation_id, private_dir=private_dir,
        session=session, mobile=None, read_page=lambda: document, patch_page=None,
        prepare_account=None, build_menu=build_menu, recover_receipt=observe,
        prepare_writeback=prepare if prepare_writeback is not None else None,
        progress_answers=progress_answers,
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
                            account_turn, progress_turn, payload=None, source_binding=None):
    """Route 03 confirmation, answers and plain continue to their original journal.

    Each trusted callback accepts (message_id, payload) and uses the same
    household, project, conversation and workspace passed to this router.
    The combined entry supplies its registered sources for pending work and recovery.
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
    source_digest = None
    if source_binding is not None:
        source_digest = sha256(json.dumps([document_id, source_binding], ensure_ascii=False,
                                         sort_keys=True, allow_nan=False).encode()).hexdigest()
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
                id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                source_digest TEXT);
            CREATE TABLE IF NOT EXISTS original_sources (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recovered_replies (
                id TEXT PRIMARY KEY, original_id TEXT NOT NULL);
        """)
        columns = {row[1] for row in route.execute("PRAGMA table_info(interrupted_dispatch)")}
        if "source_digest" not in columns:
            route.execute("ALTER TABLE interrupted_dispatch ADD COLUMN source_digest TEXT")
        reply_id = message_id
        alias = route.execute(
            "SELECT original_id FROM recovered_replies WHERE id=?", (reply_id,)
        ).fetchone()
        if alias:
            message_id = alias[0]
        active, finished, known, latest = {}, {}, {}, {}
        exact_saved = None
        if requested is not None:
            conversation = _load_module("conversation_entry")
            encoded_payload = conversation.encode(payload)
        for kind, (scope, _) in hosts.items():
            _, journal = _journal_directory(workspace_dir, scope, conversation_id, create=False)
            if not journal.exists():
                continue
            if journal.is_symlink():
                raise PermissionError("DOCS03_PRIVATE_JOURNAL_DIRECTORY_REQUIRED")
            if journal.stat().st_size == 0:
                # The host may have stopped after creating the file, before creating its schema.
                continue
            try:
                with closing(sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True)) as work:
                    tables = {row[0] for row in work.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    if not tables:
                        continue  # SQLite was initialized before its first table was created.
                    row = work.execute("SELECT id, phase FROM work ORDER BY rowid DESC LIMIT 1").fetchone()
                    if "replies" not in tables and row is None:
                        continue  # Initialization stopped before it could accept any request.
                    original = work.execute(
                        "SELECT id, phase FROM work WHERE id=? UNION ALL "
                        "SELECT w.id, w.phase FROM replies r JOIN work w ON w.id=r.work_id "
                        "WHERE r.id=? LIMIT 1", (message_id, message_id)
                    ).fetchone()
                    if kind == requested:
                        exact_saved = conversation.find_saved_confirmation(work, encoded_payload)
            except sqlite3.DatabaseError:
                return {"status": "DOCS03_JOURNAL_RECOVERY_REQUIRED",
                        "text": "目前讀不到原 03 的續接紀錄，請先核對原對話的私人工作區。"}
            if original:
                known[kind] = original
            if row:
                latest[kind] = row[0]
            if row and row[1] in ("open", "running", "writeback"):
                active[kind] = row[0]
            elif row and row[1] == "done":
                finished[kind] = row[0]
        if len(active) > 1:
            return {"status": "DOCS03_MULTIPLE_PENDING_REQUESTS"}
        active_kind = next(iter(active), None)
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
                "SELECT id, kind, payload, source_digest FROM interrupted_dispatch WHERE slot=1"
            ).fetchone()
            known_id, known_phase = known.get(previous, (None, None))
            saved_replay = known_id is None and kind == requested and exact_saved is not None
            terminal_replay = saved_replay or known_phase in ("done", "closed", "cancelled")
            if interrupted and (message_id == interrupted[0] or not terminal_replay):
                original_id, original_kind, saved_payload, original_source_digest = interrupted
                if original_source_digest is not None and original_source_digest != source_digest:
                    raise PermissionError("DOCS03_ORIGINAL_SOURCE_BINDING_CHANGED")
                original_payload = json.loads(saved_payload)
                if message_id != original_id and previous is not None:
                    return {"status": "DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION"}
                if payload is not None and (
                        requested != original_kind
                        or json.dumps(payload, sort_keys=True, allow_nan=False)
                        != json.dumps(original_payload, sort_keys=True, allow_nan=False)):
                    if message_id == original_id:
                        raise ValueError("REQUEST_COLLISION")
                    return {"status": "ANOTHER_REQUEST_PENDING"}
                if active_kind is not None and active_kind != original_kind:
                    return {"status": "DOCS03_MULTIPLE_PENDING_REQUESTS"}
                if reply_id != original_id:
                    route.execute("INSERT OR IGNORE INTO recovered_replies VALUES(?,?)",
                                  (reply_id, original_id))
                message_id, kind, payload = original_id, original_kind, original_payload
                dispatch_id = original_id
            elif active:
                # A terminal message can only read its existing result or cancellation.
                if kind is not None and kind != active_kind and not terminal_replay:
                    return {"status": "ANOTHER_REQUEST_PENDING"}
                kind = kind or active_kind
            elif kind is None:
                if len(finished) == 1:
                    kind = next(iter(finished))
                elif len(finished) > 1:
                    # Completed replies and historical redeliveries aren't new requests.
                    order = route.execute(
                        "SELECT kind FROM turns WHERE (id=? AND kind='account') "
                        "OR (id=? AND kind='progress') ORDER BY rowid DESC",
                        (finished["account"], finished["progress"])
                    ).fetchall()
                    if len(order) != len(finished):
                        return {"status": "DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION"}
                    kind = order[0][0]
                else:
                    return {"status": "NO_PENDING_REQUEST"}
            if not interrupted and payload is not None and not active and kind not in known and not saved_replay:
                # Record the original input before the business journal can receive it.
                route.execute("INSERT INTO interrupted_dispatch VALUES(1,?,?,?,?)", (
                    message_id, kind, json.dumps(payload, ensure_ascii=False, allow_nan=False), source_digest))
                dispatch_id = message_id
            bound_id = known_id
            if dispatch_id is not None:
                bound_id = dispatch_id
            elif saved_replay:
                bound_id = exact_saved
            elif bound_id is None:
                bound_id = latest.get(kind) if payload is None else active.get(kind)
            if bound_id is not None:
                original_source = route.execute(
                    "SELECT digest FROM original_sources WHERE id=?", (bound_id,)
                ).fetchone()
                if original_source is not None and original_source[0] != source_digest:
                    raise PermissionError("DOCS03_ORIGINAL_SOURCE_BINDING_CHANGED")
            if dispatch_id is not None and source_digest is not None:
                route.execute("INSERT OR IGNORE INTO original_sources VALUES(?,?)",
                              (dispatch_id, source_digest))
            route.execute("INSERT OR IGNORE INTO turns VALUES(?,?)", (message_id, kind))
        try:
            result = hosts[kind][1](message_id, payload)
        except (ConnectionError, TimeoutError, FileNotFoundError):
            # Keep the original dispatch and its current writeback phase available.
            return {"status":"DOCS03_READ_RETRY_REQUIRED",
                    "text":"這次暫時讀不到 03 所需的資料。請輸入「繼續」接回原待辦。"}
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
                                payload=None, verified_backup=None, write_slot=None):
    """Stage or resume one XLSX answer using the original 03 menu.

    The trusted host supplies the fixed Excel ID and a fresh download callback.
    build_menu(login, path) binds that local Excel to the original project menu.
    After a backup, pass its actual ID and path; issue the returned update once.
    Direct and combined calls share the same per-file authorization slot.
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

    def current_workbook():
        file_id, path = download_progress(progress_file_id)
        path = Path(path)
        if file_id != progress_file_id or path.name != expected_name:
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        return path

    def progress_menu():
        menu = build_menu(auth, current_workbook())
        if menu.auth.family_login is not auth:
            raise PermissionError("DOCS03_MENU_BINDING_MISMATCH")
        return menu

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
            saved_path = _pin_candidate(
                workspace_dir, project_id + "|03-progress", conversation_id,
                staged["候選檔"], staged["新檔摘要"], "xlsx")
            return {"status":"DB_WRITEBACK_REQUIRED",
                    "result":{**staged, "候選檔":saved_path, "receipt_key":key}}

    def observe(key):
        if (key["file_id"], key["client_id"], key["operation"]) != (
                progress_file_id, client_id, "save_progress"):
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        downloaded = current_workbook()
        reader = _load_module("equity_sleeve").reader_module()
        result = planner.progress_receipt(downloaded, family_alias, {
            "action": "progress_receipt", "event_id": key["request_id"],
            "source_revision": key["source_revision"]}, reader)
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
        if update["status"] == "FAMILY03_PROGRESS_CANDIDATE_MISSING":
            return {"status":"DOCS03_PREVIEW_STALE", "request_id":key["request_id"],
                    "text":"待寫回的作答副本已遺失，請回到 03 重新確認這一題。"}
        # The first observation missed a save that landed before preflight.
        if update["status"] == "FAMILY03_PROGRESS_EVENT_FOUND":
            return {**key, "status":"PERSISTED_REMOTE_VERIFIED", "progress_receipt":update}
        return {**update, "status":"DOCS03_DRIVE_UPDATE_REQUIRED", "request_id":key["request_id"]}

    if write_slot is None:
        write_slot = _DriveWriteSlot(workspace_dir, progress_file_id, project_id, conversation_id)
    result = run_docs03(auth=auth, document_id=document_id, document=document,
        project_id=project_id + "|03-progress", conversation_id=conversation_id,
        workspace_dir=workspace_dir, message_id=message_id, payload=payload,
        build_menu=lambda _: ProgressMenu(progress_menu()), recover_receipt=recover,
        prepare_writeback=prepare, progress_answers=True, write_slot=write_slot)
    if result["status"] == "PERSISTED_REMOTE_VERIFIED":
        receipt = result["result"]
        if (receipt["file_id"], receipt["client_id"]) != (progress_file_id, client_id):
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
    return result


def run_project_docs03(*, auth, document_id, document, project_id,
                       conversation_id, workspace_dir, message_id,
                       project_name, login_account, client_id, family_alias,
                       official_drive_file_id, mutation_staging_dir,
                       downloaded_db_path=None, verified_drive_sha256=None,
                       download_original, payload=None,
                       backup_original=None, replace_original=None,
                       native_writeback=False, verified_backup=None,
                       progress_file_id=None, download_progress=None, build_original_menu=None,
                       write_slot=None):
    """Connect 03 to same-account Drive callbacks supplied by the trusted host.

    backup_original(file_id) returns a newly saved backup's ID and download path.
    replace_original accepts the authorized native Drive update arguments.
    Supply both to let the journal own submission, or omit both for staged-only use.
    With native_writeback=True the host obtains a backup on a separate tool
    call, passes its ID and downloaded path as verified_backup, and submits the
    returned update arguments once. Continue with a fresh original download.
    Pass the registered progress_file_id and its download callback to recheck
    the confirmed workbook revision before an original-ledger update.
    A trusted host may supply build_original_menu(login) to retain its
    household's existing menu version and bind its fresh workbook download.
    The native combined entry lets that builder download the initial ledger
    only when needed. Receipt checks use the ledger downloaded for the lookup.
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
    if (downloaded_db_path is None or verified_drive_sha256 is None) and not (
            downloaded_db_path is None and verified_drive_sha256 is None
            and native_writeback and build_original_menu is not None):
        raise ValueError("DOCS03_INITIAL_LEDGER_REQUIRED")
    sources = {
        "login_account": login_account,
        "client_id": client_id,
        "family_alias": family_alias,
        "downloaded_db_path": downloaded_db_path,
        "official_drive_file_id": official_drive_file_id,
        "verified_drive_sha256": verified_drive_sha256,
    }

    def downloaded_progress():
        received_id, path = download_progress(progress_file_id)
        if received_id != progress_file_id:
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        return Path(path)

    class ConfirmationMenu:
        def __init__(self, menu):
            self.menu, self.auth = menu, menu.auth

        def select(self, number, *, payload):
            response = self.menu.select(number, payload=payload)
            if response["status"] != "DB_WRITEBACK_REQUIRED":
                return response
            staged = response["result"]
            plan = staged["writeback_plan"]
            candidate = plan["candidate"]
            path = _pin_candidate(workspace_dir, project_id, conversation_id,
                                  candidate["path"], candidate["sha256"], "db")
            staged = {**staged, "writeback_plan":{
                **plan, "candidate":{**candidate, "path":path}}}
            if check_progress:
                staged["progress_binding"] = {"file_id":progress_file_id, "revision":payload["revision"]}
            return {**response, "result":staged}

    def build_menu(login):
        if build_original_menu is None:
            progress = {"family03_progress_path": downloaded_progress()} if check_progress else {}
            menu = _load_module("on_demand_project").build_project_menu(
                family_login=login, project_name=project_name,
                mutation_staging_dir=mutation_staging_dir, **sources, **progress)
        else:
            menu = build_original_menu(login)
        return ConfirmationMenu(menu) if managed or native_writeback else menu

    def read_receipt(key, fresh_path, fresh_id):
        if fresh_id != official_drive_file_id:
            raise PermissionError("DOCS03_RECEIPT_BINDING_MISMATCH")
        with Path(fresh_path).open("rb") as downloaded:
            revision = _digest_stream(downloaded)
        receipt_sources = {**sources, "downloaded_db_path": fresh_path,
                           "verified_drive_sha256": revision}
        stager = _load_module("on_demand_mutations").OnDemandMutationStager(
            auth=auth, staging_dir=mutation_staging_dir, **receipt_sources)
        return stager.recover_receipt(key, fresh_path, fresh_id)

    def recover_receipt(key):
        account = auth.require_login()
        if not isinstance(account, str) or account.upper() != login_account.upper():
            raise PermissionError("FAMILY_PROJECT_ACCOUNT_MISMATCH")
        if key["file_id"] != official_drive_file_id:
            raise PermissionError("RECEIPT_BINDING_MISMATCH")
        fresh_id, fresh_path = download_original(official_drive_file_id)
        return read_receipt(key, fresh_path, fresh_id)

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
        drive = _load_module("on_demand_drive_io")
        binding = drive.Binding(*binding_values, family_alias)
        fresh = drive.inspect(fresh_path, binding)
        if fresh["sha256"] != plan["source"]["sha256"]:
            # The original update may have appeared since the earlier receipt lookup.
            saved = read_receipt(staged["receipt_key"], fresh_path, fresh_id)
            if saved is not None:
                return saved
            return {
                "status": "DOCS03_PREVIEW_STALE",
                "request_id": staged["request_id"],
                "text": "帳本已有更新，請回 03 重新查看全帳戶目標，再確認一次。",
            }
        if progress_binding is not None and (
                sha256(downloaded_progress().read_bytes()).hexdigest() != progress_binding["revision"]):
            return {"status":"DOCS03_PREVIEW_STALE", "request_id":staged["request_id"],
                    "text":"股票方案已有更新，請回 03 重新查看全帳戶目標，再確認一次。"}
        if not Path(plan["candidate"]["path"]).is_file():
            return {"status":"DOCS03_PREVIEW_STALE", "request_id":staged["request_id"],
                    "text":"待寫回的帳本副本已遺失，請回到 03 重新預覽並確認。"}
        # This turn can have a different download path for the same Drive bytes.
        confirmed_source = {**plan["source"], "path": fresh["path"]}
        writer = drive.OnDemandWriteback(binding, auth.require_login)
        authorized = writer.authorize_update(
            {**plan, "source": confirmed_source}, fresh_path, backup_path, backup_id,
            candidate_file_uri=plan["candidate"]["path"], local_upload_supported=True)
        if native_writeback:
            return {"status":"DOCS03_DRIVE_UPDATE_REQUIRED", "request_id":staged["request_id"],
                    "update_file_args":authorized["update_file_args"]}
        return lambda: replace_original(**authorized["update_file_args"])

    if native_writeback and write_slot is None:
        write_slot = _DriveWriteSlot(workspace_dir, official_drive_file_id, project_id, conversation_id)
    result = run_docs03(
        auth=auth, document_id=document_id, document=document,
        project_id=project_id, conversation_id=conversation_id,
        workspace_dir=workspace_dir, message_id=message_id, payload=payload,
        build_menu=build_menu, recover_receipt=recover_receipt,
        prepare_writeback=prepare_writeback if managed or native_writeback else None,
        write_slot=write_slot if native_writeback else None)
    if result.get("status") == "PERSISTED_REMOTE_VERIFIED":
        receipt = result["result"]
        if (receipt.get("file_id"), receipt.get("client_id")) != (official_drive_file_id, client_id):
            raise PermissionError("DOCS03_RECEIPT_BINDING_MISMATCH")
    return result


def run_project_docs03_native_turn(*, auth, document_id, document, project_id,
                                   conversation_id, workspace_dir, message_id,
                                   project_name, login_account, client_id, family_alias,
                                   official_drive_file_id, progress_file_id,
                                   download_original, download_progress, build_original_menu,
                                   mutation_staging_dir, payload=None,
                                   verified_account_backup=None, verified_progress_backup=None):
    """Wire both Menu 03 paths to the same trusted host and original menu.

    The host supplies stable IDs and its per-conversation workspace, not values
    parsed from chat. Download callbacks return the actual Drive ID and local
    path. build_original_menu(login, workbook_path, ledger_path) uses the
    already selected household version. Only the routed path consumes a backup.
    """
    if (getattr(auth, "user_id", None), getattr(auth, "client_id", None)) != (login_account, client_id):
        raise PermissionError("DOCS03_PROJECT_ACCOUNT_MISMATCH")
    if not isinstance(workspace_dir, (str, Path)) or not str(workspace_dir).strip():
        raise ValueError("DOCS03_WORKSPACE_DIRECTORY_REQUIRED")
    if (not all(isinstance(value, str) and value.strip()
                for value in (official_drive_file_id, progress_file_id))
            or official_drive_file_id == progress_file_id):
        raise ValueError("DOCS03_DISTINCT_SOURCE_IDS_REQUIRED")
    if not all(callable(callback) for callback in (download_original, download_progress,
                                                    build_original_menu)):
        raise TypeError("DOCS03_HOST_CALLBACKS_REQUIRED")

    context = dict(auth=auth, document_id=document_id, document=document,
                   project_id=project_id, conversation_id=conversation_id,
                   workspace_dir=workspace_dir)
    household = dict(login_account=login_account, client_id=client_id, family_alias=family_alias)
    workbook_name = family_alias + "_03_股票配置選擇進度.xlsx"

    def current_ledger():
        received_id, path = download_original(official_drive_file_id)
        if received_id != official_drive_file_id:
            raise PermissionError("DOCS03_WRITEBACK_BINDING_MISMATCH")
        return Path(path)

    def current_workbook(file_id):
        received_id, path = download_progress(file_id)
        workbook = Path(path)
        if file_id != progress_file_id or received_id != progress_file_id or workbook.name != workbook_name:
            raise PermissionError("DOCS03_PROGRESS_BINDING_MISMATCH")
        return received_id, workbook

    def progress_menu(login, workbook):
        return build_original_menu(login, workbook, current_ledger())

    def account_menu(login):
        ledger = current_ledger()
        return build_original_menu(login, current_workbook(progress_file_id)[1], ledger)

    def progress_turn(mid, data):
        return run_project_docs03_progress(
            **context, **household, message_id=mid, payload=data,
            progress_file_id=progress_file_id, download_progress=current_workbook,
            build_menu=progress_menu, verified_backup=verified_progress_backup)

    def account_turn(mid, data):
        return run_project_docs03(
            **context, **household, message_id=mid, payload=data,
            project_name=project_name, official_drive_file_id=official_drive_file_id,
            mutation_staging_dir=mutation_staging_dir, download_original=download_original,
            native_writeback=True, verified_backup=verified_account_backup,
            progress_file_id=progress_file_id, download_progress=current_workbook,
            build_original_menu=account_menu)

    return run_project_docs03_turn(
        **context, message_id=message_id, payload=payload,
        account_turn=account_turn, progress_turn=progress_turn,
        source_binding=(login_account, client_id, family_alias, official_drive_file_id, progress_file_id))
