"""Host-side official read-only Family account/portfolio/04 MCP binding.

Existing B07 OAuth validates the real four-hour session. Existing B06
Coordinator and Google Drive adapter remain the only resource-access path.
This module has no private File IDs and never changes investment algorithms.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY / "W7"))

from account_mcp import AccountMCP
from drive_resource_backend import DriveResourceBackend
from drive_service_transport import GoogleDriveTransport
from private_account_service import load_router
from private_runtime import private_directory, read_private, validate
from resource_headers import validate_policies
from 資料存取管理 import Coordinator
from official_family_entry import OfficialFamilyEntry, RESOURCE_BY_ACCOUNT

API = "https://www.googleapis.com/drive/v3/files/"


class _SessionAuth:
    def __init__(self, oauth, principal):
        self.oauth, self.principal = oauth, principal

    def require_login(self):
        if self.oauth.session_guard(self.principal) is not True:
            raise PermissionError("FAMILY_SESSION_EXPIRED")
        subject = self.principal.subject
        if not isinstance(subject, str) or not subject.startswith("account:"):
            raise PermissionError("INVALID_FAMILY_ACCOUNT")
        return subject.split(":", 1)[1]


def _client_id_from_official_bytes(raw):
    if not isinstance(raw, bytes) or not raw.startswith(b"SQLite format 3" + bytes([0])):
        raise ValueError("OFFICIAL_DB_INVALID")
    with TemporaryDirectory(prefix="family-verified-owner-") as folder:
        path = Path(folder) / "source.db"
        path.write_bytes(raw)
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            ids = db.execute("SELECT client_id FROM family_member_identity").fetchall()
            if len(ids) != 1 or not isinstance(ids[0][0], str):
                raise PermissionError("OFFICIAL_IDENTITY_REQUIRED")
            return ids[0][0]
        finally:
            db.close()


class OfficialBusinessTools:
    def __init__(self, oauth, coordinator):
        self.oauth, self.coordinator = oauth, coordinator

    @staticmethod
    def specs():
        return [
            {"name": "family_portfolio",
             "description": "從本人正式 Google Drive 資料庫查看已有持倉與已記錄的現金和目標。",
             "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
             "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}},
            {"name": "family_deployment_pace",
             "description": "評估本人持倉標的是否適合加碼。已核實資料不足時列明缺項。",
             "inputSchema": {"type": "object", "properties": {
                 "question": {"type": "string", "minLength": 1, "maxLength": 600}},
                 "required": ["question"], "additionalProperties": False},
             "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}
        ]

    def call(self, principal, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("INVALID_BUSINESS_ARGUMENTS")
        auth = _SessionAuth(self.oauth, principal)
        account = auth.require_login()
        if account not in RESOURCE_BY_ACCOUNT:
            raise PermissionError("INVALID_FAMILY_ACCOUNT")
        key = RESOURCE_BY_ACCOUNT[account]
        # The private B06 resource catalog, never a tool argument, chooses ID.
        source = self.coordinator.snapshot(key, principal)
        raw = source["data"]
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise RuntimeError("OFFICIAL_SOURCE_SHA_MISMATCH")
        client_id = _client_id_from_official_bytes(raw)
        entry = OfficialFamilyEntry(
            auth=auth, login_account=account, client_id=client_id,
            coordinator=self.coordinator, principal_provider=lambda: principal)
        if name == "family_portfolio":
            if arguments:
                raise ValueError("INVALID_PORTFOLIO_ARGUMENTS")
            current = entry.read_portfolio({})
            tables = current["snapshot"]["tables"]
            # This is the user's authorized session, but avoid raw 29-table
            # account dumps. Retain timestamp and source status on actual rows.
            return {
                "status": "OK", "source": "OFFICIAL_GOOGLE_DRIVE",
                "portfolio_position": tables["portfolio_position"],
                "portfolio_instrument": tables["portfolio_instrument"],
                "cash_balance_snapshot": tables["cash_balance_snapshot"],
                "final_target_allocation": tables["final_target_allocation"],
                "funding_evaluation": tables["funding_evaluation"],
                "trade_authorization": "NONE"}
        if name == "family_deployment_pace":
            if set(arguments) != {"question"} or not isinstance(arguments["question"], str) or (
                not 1 <= len(arguments["question"].strip()) <= 600):
                raise ValueError("INVALID_INVESTMENT_QUESTION")
            # W5 input must be compiled from verified W2/market/funding,
            # never from generated fake budgets; official data is always read.
            return entry.deployment_pace({"question": arguments["question"].strip()})
        raise ValueError("UNKNOWN_OFFICIAL_TOOL")


def load_official_router(root, *, transport_factory=GoogleDriveTransport):
    """Prepare the real business MCP on the existing private OAuth router.

    Deployment and exposure remain under the existing approved host gates;
    construction never edits any family database.
    """
    root = private_directory(Path(root))
    config = json.loads(read_private(root / "runtime.json"))
    validate(config)
    router = load_router(root, transport_factory=transport_factory)
    resource = config["resource_config"]
    transport = transport_factory(**config["google_oauth"])
    raw = transport.call(API + resource["policy_id"] + "?alt=media", raw=True)
    policies = validate_policies(json.loads(raw))
    headers = resource["headers"]
    assert all(key in headers for key in RESOURCE_BY_ACCOUNT.values())
    backend = DriveResourceBackend(transport, resource["resources"], resource["backup_folder"])
    coordinator = Coordinator(headers, policies, backend, root / "resource-locks",
                              handlers={}, session_guard=router.oauth.session_guard)
    router.mcp = AccountMCP(router.oauth, business_tools=OfficialBusinessTools(router.oauth, coordinator))
    return router
