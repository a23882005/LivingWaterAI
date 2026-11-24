"""W8 trusted local mutation staging for the four Family ChatGPT Projects.

Call only for an authenticated Owner-confirmed 01/03/06/10/11 command.
This applies the EXISTING W8/official_mutations.py writer to a new SQLite
working copy. It never directly alters Google Drive or claims a local file was
saved. The separate on_demand_drive_io + authenticated Drive tool must back up,
persist to the SAME Drive ID, then verify remote bytes and edited fields.
"""
from pathlib import Path
import importlib.util
import os
import json
import re
import secrets
import sqlite3

OPERATIONS=("first_allocation","adjust_target","new_funding",
            "update_profile","record_event")

def _load(name, filename):
    path=Path(__file__).parent / filename
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise RuntimeError("W8_MUTATION_DEPENDENCY_MISSING")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class OnDemandMutationStager:
    def __init__(self, *, auth, login_account, client_id, family_alias,
                 official_drive_file_id, downloaded_db_path, verified_drive_sha256,
                 staging_dir):
        if (not hasattr(auth,"require_login") or not callable(auth.require_login)
                or not isinstance(staging_dir,(str,Path))
                or not re.fullmatch(r"[0-9a-f]{64}",str(verified_drive_sha256))):
            raise ValueError("W8_VERIFIED_MUTATION_BINDING_REQUIRED")
        self.auth=auth
        self.login_account=login_account
        self.client_id=client_id
        self.family_alias=family_alias
        self.file_id=official_drive_file_id
        self.original=Path(downloaded_db_path).resolve(strict=True)
        self.source_sha=verified_drive_sha256
        self.staging_dir=Path(staging_dir).resolve(strict=True)
        if not self.staging_dir.is_dir() or self.staging_dir.is_symlink():
            raise ValueError("W8_SECURE_STAGING_DIRECTORY_REQUIRED")
        self.drive=_load("family_w8_mutation_writeback","on_demand_drive_io.py")
        self.receipts = _load("family_request_receipts",
                              Path(__file__).resolve().parents[1] / "W7" / "資料存取管理.py")
        self.binding=self.drive.Binding(
            login_account,client_id,official_drive_file_id,family_alias)
        self.writer=self.drive.OnDemandWriteback(self.binding,auth.require_login)

    def stage(self,operation,payload):
        if operation not in OPERATIONS:
            raise ValueError("W8_UNSUPPORTED_MUTATION")
        if self.auth.require_login()!=self.login_account:
            raise PermissionError("FAMILY_PROJECT_ACCOUNT_MISMATCH")
        if (not isinstance(payload,dict)
                or set(payload)!={"request_id","record","owner_confirmed"}
                or payload["owner_confirmed"] is not True
                or not isinstance(payload["record"],dict)
                or not isinstance(payload["request_id"],str)
                or not 1 <= len(payload["request_id"]) <= 128):
            raise ValueError("OWNER_CONFIRMED_MUTATION_REQUIRED")
        original=self.drive.inspect(self.original,self.binding)
        if original["sha256"]!=self.source_sha:
            raise RuntimeError("OFFICIAL_DB_SOURCE_CHANGED")
        record = dict(payload["record"])
        if operation == "first_allocation":
            record["request_id"] = payload["request_id"]
        request = {"client_id": self.client_id, "record": record}
        fingerprint = self.receipts.digest(self.receipts.canonical([operation, request]).encode())
        key = {"request_id": payload["request_id"], "fingerprint": fingerprint,
               "operation": operation, "file_id": self.file_id, "client_id": self.client_id}

        def write(db, data):
            row = data["record"]
            if operation == "adjust_target" and any(
                    isinstance(item, dict) and ("candidate_ticker" in item or "approved_role" in item)
                    for item in row.get("allocations", []) or []):
                target = _load("family03_target", "family03_target.py")
                data["record"] = target.resolve_target_rows(
                    db, self.client_id, row, self.original.parent,
                    _load("family03_equity", "equity_sleeve.py"),
                    _load("family03_plans", "family03_plans.py"),
                    _load("family03_prices", "family03_prices.py"), mutation.now())
            result = mutation.make_writer(operation, self.client_id)(db, data)
            if not isinstance(result, dict) or result.get("status") != "STORED":
                raise RuntimeError("OFFICIAL_MUTATION_NOT_STORED_IN_CANDIDATE")
            return result

        mutation = _load("family_w8_mutation_writer", "official_mutations.py")
        source = self.original.read_bytes()
        if self.receipts.digest(source) != self.source_sha:
            raise RuntimeError("OFFICIAL_DB_SOURCE_CHANGED")
        data, result, duplicate = self.receipts.transaction(
            source, "account:" + self.login_account, key["request_id"], operation, request, write)
        if duplicate:
            return self._saved(key, result, self.source_sha)
        sealed = self.staging_dir / ("w8-candidate-" + secrets.token_hex(16) + ".db")
        try:
            with os.fdopen(os.open(sealed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(data)
            plan = self.writer.prepare(self.original, sealed)
            if plan["source"]["sha256"] != self.source_sha:
                raise RuntimeError("OFFICIAL_DB_SOURCE_CHANGED")
            return {"status": "STAGED_NOT_PERSISTED", "operation": operation,
                    "request_id": key["request_id"], "client_id": self.client_id,
                    "source_sha256": self.source_sha, "receipt_key": key,
                    "business_result": result, "writeback_plan": plan, "trade_authorization": "NONE"}
        except BaseException:
            sealed.unlink(missing_ok=True)
            raise

    def _saved(self, key, result, sha):
        return {"status": "PERSISTED_REMOTE_VERIFIED", **key, "sha256": sha,
                "business_result": result, "trade_authorization": "NONE"}

    def receipt_reader(self, download_original):
        """Bind the runner's native Drive download to the household's fixed ID."""
        def read(key):
            self.writer._admit()
            if key["file_id"] != self.file_id:
                raise PermissionError("RECEIPT_BINDING_MISMATCH")
            remote_id, fresh_path = download_original(self.file_id)
            return self.recover_receipt(key, fresh_path, remote_id)
        return read

    def recover_receipt(self, key, fresh_remote, remote_file_id):
        """Use only a fresh host download from the bound Drive ID. No write or new stage."""
        self.writer._admit()
        if (remote_file_id != self.file_id or key["file_id"] != self.file_id
                or key["client_id"] != self.client_id or key["operation"] not in OPERATIONS):
            raise PermissionError("RECEIPT_BINDING_MISMATCH")
        info = self.drive.inspect(fresh_remote, self.binding)
        with sqlite3.connect(Path(info["path"]).as_uri() + "?mode=ro", uri=True) as db:
            table = self.receipts.RECEIPTS
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                return None
            row = db.execute(f"SELECT fingerprint,result FROM {table} WHERE subject=? AND request_id=?",
                             ("account:" + self.login_account, key["request_id"])).fetchone()
        if row is None:
            return None
        if row[0] != key["fingerprint"]:
            raise ValueError("REQUEST_COLLISION")
        result = json.loads(row[1])
        if result.get("status") != "STORED" or result.get("operation") != key["operation"]:
            raise ValueError("INVALID_MUTATION_RECEIPT")
        return self._saved(key, result, info["sha256"])

def mutation_handlers(stager):
    if not isinstance(stager,OnDemandMutationStager):
        raise ValueError("W8_MUTATION_STAGER_REQUIRED")
    return {op:lambda payload,operation=op:stager.stage(operation,payload)
            for op in OPERATIONS}

