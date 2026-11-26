"""Use the original Docs login for the 03 write and receipt journal."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path


def _conversation_class():
    path = Path(__file__).with_name("conversation_entry.py")
    spec = spec_from_file_location("family_docs03_conversation_entry", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConversationEntry


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
               workspace_dir=None, private_dir=None):
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
    entry = _conversation_class()(
        project_id=project_id, conversation_id=conversation_id, private_dir=private_dir,
        session=session, mobile=None, read_page=lambda: document, patch_page=None,
        prepare_account=None, build_menu=build_menu, recover_receipt=recover_receipt,
    )
    if payload is None:
        return entry.handle_message(message_id, "繼續")
    return entry.handle_message(message_id, number=3, payload=payload)
