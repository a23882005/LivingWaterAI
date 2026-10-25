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
from official_mutations import make_writer
import copy

API = "https://www.googleapis.com/drive/v3/files/"

# All five write operations share the same verified B07 principal and B06
# same-file-id backup/transaction/readback mechanism.
MUTATION_TOOLS = {
    "family_first_allocation": "first_allocation",
    "family_adjust_target": "adjust_target",
    "family_new_funding": "new_funding",
    "family_update_profile": "update_profile",
    "family_record_event": "record_event",
}
MUTATION_LABELS = {
    "family_first_allocation": "保存本人已確認的第一次建倉資料與持倉快照。",
    "family_adjust_target": "正式保存本人確認的投資標的與目標權重。",
    "family_new_funding": "正式保存本人確認的新增資金來源與金額。",
    "family_update_profile": "正式更新本人確認的生活需求與投資資料。",
    "family_record_event": "記錄本人確認的交易或資金異動事件，保留事件歷史。",
}


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
        ] + [
            {"name": name, "description": MUTATION_LABELS[name],
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "request_id": {"type": "string", "minLength": 1, "maxLength": 128},
                     "record": {"type": "object"},
                 },
                 "required": ["request_id", "record"], "additionalProperties": False},
             "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}}
            for name in MUTATION_TOOLS
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
        if name in MUTATION_TOOLS:
            # Explicit user-confirmed records only; server derives the family
            # resource and client ID from the authenticated session and DB.
            if (set(arguments) != {"request_id", "record"}
                or not isinstance(arguments["request_id"], str)
                or not 1 <= len(arguments["request_id"]) <= 128
                or not isinstance(arguments["record"], dict)):
                raise ValueError("INVALID_MUTATION_ARGUMENTS")
            operation = MUTATION_TOOLS[name]
            request_id = arguments["request_id"]
            record = copy.deepcopy(arguments["record"])
            if operation == "first_allocation":
                # Prevent conflicting idempotency between receipt and snapshot.
                record["request_id"] = request_id
            before = self.coordinator.snapshot(key, principal)
            saved = self.coordinator.update(
                key, principal, request_id, before["epoch"], operation,
                {"client_id": client_id, "record": record})
            data = saved["result"]
            if data.get("status") != "STORED":
                raise RuntimeError("OFFICIAL_MUTATION_NOT_STORED")
            after = self.coordinator.snapshot(key, principal)
            if _client_id_from_official_bytes(after["data"]) != client_id:
                raise PermissionError("OFFICIAL_MUTATION_CLIENT_MISMATCH")
            if (not saved["duplicate"] and
                after["sha256"] == before["sha256"]):
                raise RuntimeError("OFFICIAL_MUTATION_NOT_PERSISTED")
            return {
                "status": "SAVED", "operation": operation,
                "source": "OFFICIAL_GOOGLE_DRIVE",
                "client_id": client_id, "result": data,
                "duplicate_request": saved["duplicate"],
                "source_sha256": after["sha256"],
                "readback_verified": True, "trade_authorization": "NONE"}
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
    # Generic handler keys are fixed server-side and are never caller-controlled.
    # The client ID embedded in the trusted payload is checked against the
    # member's real SQLite identity inside the B06 transaction.
    write_handlers = {
        op: (lambda db, payload, op=op:
             make_writer(op, payload["client_id"])(db, payload))
        for op in MUTATION_TOOLS.values()
    }
    coordinator = Coordinator(headers, policies, backend, root / "resource-locks",
                              handlers=write_handlers,
                              session_guard=router.oauth.session_guard)
    router.mcp = AccountMCP(router.oauth, business_tools=OfficialBusinessTools(router.oauth, coordinator))
    return router
