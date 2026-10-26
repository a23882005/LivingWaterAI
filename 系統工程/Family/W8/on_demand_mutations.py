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
import re
import secrets
import sqlite3

OPERATIONS=("first_allocation","adjust_target","new_funding",
            "update_profile","record_event")

def _load(name, filename):
    path=Path(__file__).with_name(filename)
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
        nonce=secrets.token_hex(16)
        working=self.staging_dir/("w8-working-"+nonce+".db")
        sealed=self.staging_dir/("w8-candidate-"+nonce+".db")
        if self.original in (working,sealed):
            raise PermissionError("OFFICIAL_ORIGINAL_IMMUTABLE")
        result=None
        try:
            # SQLite backup is read-only on source, so no WAL data are lost.
            with sqlite3.connect(self.original.as_uri()+"?mode=ro",uri=True) as src:
                with sqlite3.connect(working) as dst:
                    src.backup(dst)
            os.chmod(working,0o600)
            mutation=_load("family_w8_mutation_writer","official_mutations.py")
            record=dict(payload["record"])
            if operation=="first_allocation":
                record["request_id"]=payload["request_id"]
            with sqlite3.connect(working) as db:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("BEGIN IMMEDIATE")
                handler=mutation.make_writer(operation,self.client_id)
                result=handler(db,{"client_id":self.client_id,"record":record})
                if not isinstance(result,dict) or result.get("status")!="STORED":
                    raise RuntimeError("OFFICIAL_MUTATION_NOT_STORED_IN_CANDIDATE")
                db.commit()
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise RuntimeError("CANDIDATE_FOREIGN_KEY_INVALID")
            self.drive.seal_working_copy(working,sealed)
            os.chmod(sealed,0o600)
            plan=self.writer.prepare(self.original,sealed)
            return {"status":"STAGED_NOT_PERSISTED",
                    "operation":operation,"request_id":payload["request_id"],
                    "client_id":self.client_id,"source_sha256":self.source_sha,
                    "business_result":result,"writeback_plan":plan,
                    "trade_authorization":"NONE"}
        except Exception:
            if sealed.exists():
                sealed.unlink()
            raise
        finally:
            if working.exists():
                working.unlink()

def mutation_handlers(stager):
    if not isinstance(stager,OnDemandMutationStager):
        raise ValueError("W8_MUTATION_STAGER_REQUIRED")
    return {op:lambda payload,operation=op:stager.stage(operation,payload)
            for op in OPERATIONS}
