"""Use the original Docs login for the 03 write and receipt journal."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path


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
               workspace_dir=None, private_dir=None, prepare_writeback=None):
    """Use fresh native Docs metadata and the same host workspace on every turn.

    Supply workspace_dir for new runs. The host must reuse it and pass trusted
    project, conversation and message IDs. private_dir supports already-started
    requests whose original journal location is known.
    """
    if (workspace_dir is None) == (private_dir is None):
        raise ValueError("DOCS03_EXACTLY_ONE_JOURNAL_LOCATION_REQUIRED")
    if payload is not None and (
            not isinstance(payload, dict) or payload.get("action") != "confirm_account"):
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
        prepare_writeback=prepare_writeback,
    )
    if payload is None:
        return entry.handle_message(message_id, "繼續")
    return entry.handle_message(message_id, number=3, payload=payload)


def run_project_docs03(*, auth, document_id, document, project_id,
                       conversation_id, workspace_dir, message_id,
                       project_name, login_account, client_id, family_alias,
                       downloaded_db_path, official_drive_file_id,
                       verified_drive_sha256, mutation_staging_dir,
                       download_original, payload=None,
                       backup_original=None, replace_original=None,
                       native_writeback=False, verified_backup=None):
    """Connect 03 to same-account Drive callbacks supplied by the trusted host.

    backup_original(file_id) returns a newly saved backup's ID and download path.
    replace_original accepts the authorized native Drive update arguments.
    Supply both to let the journal own submission, or omit both for staged-only use.
    With native_writeback=True the host obtains a backup on a separate tool
    call, passes its ID and downloaded path as verified_backup, and submits the
    returned update arguments once. Continue with a fresh original download.
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
    sources = {
        "login_account": login_account,
        "client_id": client_id,
        "family_alias": family_alias,
        "downloaded_db_path": downloaded_db_path,
        "official_drive_file_id": official_drive_file_id,
        "verified_drive_sha256": verified_drive_sha256,
    }

    def build_menu(login):
        return _load_module("on_demand_project").build_project_menu(
            family_login=login, project_name=project_name,
            mutation_staging_dir=mutation_staging_dir, **sources)

    def recover_receipt(key):
        stager = _load_module("on_demand_mutations").OnDemandMutationStager(
            auth=auth, staging_dir=mutation_staging_dir, **sources)
        return stager.receipt_reader(download_original)(key)

    def prepare_writeback(staged):
        plan = staged["writeback_plan"]
        binding_values = (login_account, client_id, official_drive_file_id)
        if (plan["account"], plan["client_id"], plan["file_id"]) != binding_values:
            raise PermissionError("DOCS03_WRITEBACK_BINDING_MISMATCH")
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
