"""Small steps callable from the project Python runtime between native tool calls.

Inputs to these functions come from the household's configured connectors.
Routing a new conversation never grants access to an account.
"""
from datetime import datetime
from hmac import compare_digest
import json
import math
import re
import time


def _login_register(document, document_id):
    if not document_id or document.get("documentId") != document_id:
        raise ValueError("WRONG_LOGIN_DOCUMENT")
    revision = document.get("revisionId")
    tabs = document.get("tabs") or []
    if not revision or len(tabs) != 1 or not tabs[0].get("tabId"):
        raise ValueError("LOGIN_DOCUMENT_REVISION_REQUIRED")
    lines = []
    for part in tabs[0]["body"]["content"]:
        if "sectionBreak" in part:
            continue
        if "paragraph" not in part:
            raise ValueError("INVALID_LOGIN_DOCUMENT_CONTENT")
        for element in part["paragraph"].get("elements", []):
            lines.append(element["textRun"]["content"])
    return revision, tabs[0]["tabId"], "".join(lines).strip()


def docs_login_route(document, *, document_id, metadata=None, now=None):
    """Read the official single-tab register. Return a decision and its write guard."""
    revision, tab_id, record = _login_register(document, document_id)
    expires = None
    if re.fullmatch(r"[0-9a-f]{64}", record):
        if metadata is None:
            return {"status": "READ_MODIFIED_TIME", "file_id": document_id}
        if metadata.get("id") != document_id:
            raise ValueError("WRONG_LOGIN_METADATA")
        stamp = metadata.get("modified_time") or metadata.get("modifiedTime")
        if not isinstance(stamp, str):
            raise ValueError("LOGIN_MODIFIED_TIME_REQUIRED")
        modified = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if modified.tzinfo is None:
            raise ValueError("LOGIN_TIMEZONE_REQUIRED")
        expires = modified.timestamp() + 14400
    elif record:
        fields = json.loads(record)
        if not isinstance(fields, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(fields.get("session_marker", ""))):
            raise ValueError("INVALID_LOGIN_RECORD")
        expires = fields.get("expires_at")
        if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= 0:
            raise ValueError("INVALID_LOGIN_EXPIRY")
    current = time.time() if now is None else now
    return {"status": "AWAIT_SWITCH" if expires is not None and current < expires else "PREPARE_ACCOUNT_DB",
            "revision": revision, "tab_id": tab_id, "expires_at": expires}


def prepare_mobile_request(session, temp_dir, **download):
    """Given the actual account download, continue immediately to the mobile request."""
    if session.stage == "PREPARE_ACCOUNT_DB":
        session.prepare_password(temp_dir, **download)
    return session.mobile_begin()


def finish_login_and_open_07(session, page, *, build_menu):
    """Consume native registration readback and dispatch the saved read-only request."""
    action = session.pending_action
    if isinstance(action, tuple) and len(action) == 2 and action[1] is None:
        action = action[0]
    if str(action) not in ("7", "07"):
        raise ValueError("ORIGINAL_MENU_07_REQUIRED")
    if session.finish_write(page) != "RUN_PENDING_ACTION":
        raise RuntimeError("LOGIN_REGISTRATION_INCOMPLETE")
    return session.select(page, 7, build_menu=build_menu)

def finish_docs_login_and_open_03(auth, document, *, document_id, login_account,
                                  pending_action, expected_marker, expected_expiry,
                                  build_menu, now=None):
    """After the original login has written its registration, open only the saved 03 entry."""
    if isinstance(pending_action, tuple) and len(pending_action) == 2 and pending_action[1] is None:
        pending_action = pending_action[0]
    if str(pending_action) not in ("3", "03"):
        raise ValueError("ORIGINAL_MENU_03_REQUIRED")
    if getattr(auth, "user_id", None) != login_account:
        raise PermissionError("FAMILY_PROJECT_ACCOUNT_MISMATCH")
    revision, _, record = _login_register(document, document_id)
    if not record or re.fullmatch(r"[0-9a-f]{64}", record):
        raise ValueError("LOGIN_REGISTRATION_INCOMPLETE")
    route = docs_login_route(document, document_id=document_id, now=now)
    fields = json.loads(record)
    if (route["status"] != "AWAIT_SWITCH" or route["expires_at"] != expected_expiry
            or type(expected_expiry) not in (int, float)
            or not isinstance(expected_marker, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_marker)
            or not compare_digest(fields["session_marker"], expected_marker)):
        raise ValueError("LOGIN_REGISTRATION_INCOMPLETE")
    auth.confirm_registration(expected_marker, revision)
    auth.begin_request()
    auth.check_revision(revision)
    if auth.require_login() != login_account:
        raise PermissionError("FAMILY_PROJECT_ACCOUNT_MISMATCH")
    menu = build_menu(auth)
    if menu.auth.family_login is not auth:
        raise PermissionError("DOCS03_MENU_BINDING_MISMATCH")
    return menu.select(3)
