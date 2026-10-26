"""W8 no-host report publication plan for ChatGPT + Google Drive tools.

A report is never called SAVED merely because a local PDF exists. The
interactive executor must upload to the authenticated member's fixed Drive
folder, fetch each uploaded file, then upload/fetch the manifest last.
All operations are one-shot in response to the member; no server or daemon.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import json
import re

TAIPEI = timezone(timedelta(hours=8))
ALIASES = {"JO": "Joseph", "MOU": "mou", "AR": "Arthur", "LI": "Lilian"}
REQUIRED = ("report.pdf", "index.html")
ARTIFACT_SUFFIX = {
    "report.pdf": ".pdf", "index.html": ".html",
    "report.html": "_內文.html", "report.zip": ".zip",
}
MIMES = {
    ".pdf": "application/pdf", ".html": "text/html",
    ".zip": "application/zip",
}


def _digest(raw):
    return sha256(raw).hexdigest()


def _canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def prepare_report_delivery(rendered, *, account, client_id, folder_id,
                            output_dir, created_at=None):
    """Locally prepare artifact bytes and a deterministic Drive upload checklist."""
    if account not in ALIASES or not re.fullmatch(r"fam_[0-9a-f]{32}", str(client_id)):
        raise PermissionError("REPORT_FAMILY_BINDING_REQUIRED")
    if not _string(folder_id) or not re.fullmatch("[A-Za-z0-9_-]+", folder_id):
        raise ValueError("OFFICIAL_REPORT_FOLDER_REQUIRED")
    if (not isinstance(rendered, dict)
            or rendered.get("qa_passed") is not True
            or rendered.get("renderer_contract") != "Family.W6.v16.parameterized"
            or rendered.get("client_id") != client_id
            or not _string(rendered.get("run_id"))
            or not _string(rendered.get("data_as_of"))
            or not _string(rendered.get("analysis_version"))):
        raise ValueError("W6_QA_AND_MEMBER_REQUIRED")
    for field in ("source_db_sha256", "source_digest", "w6_current_digest"):
        if not re.fullmatch("[0-9a-f]{64}", str(rendered.get(field, ""))):
            raise ValueError("REPORT_LINEAGE_REQUIRED")
    artifacts = rendered.get("artifacts")
    if not isinstance(artifacts, dict) or not set(REQUIRED).issubset(artifacts):
        raise ValueError("W6_REQUIRED_ARTIFACTS_MISSING")
    if set(artifacts) - set(ARTIFACT_SUFFIX):
        raise ValueError("W6_UNEXPECTED_ARTIFACT")
    for name, value in artifacts.items():
        if not isinstance(value, bytes) or not value or len(value) > 64*1024*1024:
            raise ValueError("W6_INVALID_ARTIFACT")
        if name == "report.pdf" and not value.startswith(b"%PDF-"):
            raise ValueError("W6_PDF_INVALID")
    when = created_at or datetime.now(timezone.utc)
    if not isinstance(when, datetime) or when.utcoffset() is None:
        raise ValueError("REPORT_CREATED_TIME_REQUIRED")
    stem = ALIASES[account] + "_配置報告_" + when.astimezone(TAIPEI).strftime("%Y%m%d_%H%M%S_TW")
    folder = Path(output_dir).resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError("REPORT_LOCAL_STAGE_DIRECTORY_REQUIRED")
    planned = [(kind, stem + ARTIFACT_SUFFIX[kind], data)
               for kind, data in sorted(artifacts.items())]
    for _, name, _ in planned:
        if (folder/name).exists():
            raise FileExistsError("REPORT_STAGE_COLLISION")
    upload = []
    for kind, name, data in planned:
        path = folder/name
        path.write_bytes(data)
        if path.read_bytes() != data:
            raise RuntimeError("REPORT_LOCAL_READBACK_FAILED")
        upload.append({
            "artifact": kind, "name": name, "path": str(path),
            "mime": MIMES[path.suffix], "sha256": _digest(data), "bytes": len(data),
        })
    receipt = {
        "schema": "Family.W8.ReportDelivery.v1", "account": account,
        "client_id": client_id, "folder_id": folder_id,
        "source_db_sha256": rendered["source_db_sha256"],
        "source_digest": rendered["source_digest"],
        "w6_current_digest": rendered["w6_current_digest"],
        "run_id": rendered["run_id"], "data_as_of": rendered["data_as_of"],
        "analysis_version": rendered["analysis_version"],
        "created_at": when.astimezone(TAIPEI).isoformat(),
        "uploads": [{key:value for key,value in row.items() if key!="path"} for row in upload],
    }
    return {
        "status": "STAGED_NOT_PERSISTED",
        "receipt": receipt, "uploads": upload,
        "manifest_filename": stem + ".manifest.json",
        "trade_authorization": "NONE",
    }



def bind_connector_uploads(plan, file_uri_by_artifact):
    """Create actual Google Drive upload_file tool args, never local-path args.

    The executor obtains these refs from generated current-turn artifacts.
    Uploaded bytes are still verified through fresh Drive readback before
    manifest completion; URI presence alone never proves persistence.
    """
    if plan.get("status") != "STAGED_NOT_PERSISTED":
        raise ValueError("REPORT_STAGE_REQUIRED")
    if (not isinstance(file_uri_by_artifact, dict)
            or set(file_uri_by_artifact) != {r["artifact"] for r in plan["uploads"]}):
        raise ValueError("REPORT_ARTIFACT_REFERENCES_INCOMPLETE")
    output=[]
    used=set()
    for item in plan["uploads"]:
        uri=file_uri_by_artifact[item["artifact"]]
        if (not isinstance(uri,str)
                or not re.fullmatch(r"sediment://file_[A-Za-z0-9_-]+", uri)
                or uri in used):
            raise ValueError("VALID_REPORT_CONNECTOR_FILE_URI_REQUIRED")
        used.add(uri)
        output.append({"artifact":item["artifact"],
                       "expected_sha256":item["sha256"],
                       "upload_file_args":{"file_uri":uri,
                                          "parent_folder_id":plan["receipt"]["folder_id"],
                                          "file_name":item["name"],
                                          "mime_type":item["mime"]}})
    return {"status":"UPLOAD_READY_NOT_PERSISTED",
            "requests":output, "trade_authorization":"NONE"}


def prepare_verified_manifest(plan, receipts, readbacks):
    """Return the manifest bytes only after real Drive artifact readbacks.

    Receipts originate from Drive uploads, with id/name/parent and size.
    Readbacks must be fresh bytes retrieved from each specific uploaded ID,
    not the local artifact file reused as a shortcut.
    """
    if plan.get("status") != "STAGED_NOT_PERSISTED":
        raise ValueError("REPORT_STAGE_REQUIRED")
    rows = plan["uploads"]
    if not isinstance(receipts, list) or len(receipts) != len(rows):
        raise ValueError("REPORT_UPLOAD_RECEIPTS_INCOMPLETE")
    if not isinstance(readbacks, dict):
        raise ValueError("REPORT_REMOTE_READBACKS_REQUIRED")
    official = plan["receipt"]["folder_id"]
    verified = []
    used = set()
    for row, proof in zip(rows, receipts):
        # Current Google Drive upload_file returns file_name (or title)
        # rather than the legacy, hand-normalized proof["name"].
        name = (proof.get("file_name") or proof.get("name") or proof.get("title")
                if isinstance(proof,dict) else None)
        if (not isinstance(proof, dict) or name != row["name"]
                or proof.get("parent_id") != official
                or not proof.get("success")):
            raise PermissionError("REPORT_REMOTE_FOLDER_OR_RECEIPT_MISMATCH")
        ident = proof.get("id")
        if (not _string(ident) or not re.fullmatch("[A-Za-z0-9_-]+", ident)
                or ident in used):
            raise ValueError("REPORT_UPLOAD_ID_INVALID")
        used.add(ident)
        remote = readbacks.get(ident)
        if (not isinstance(remote, bytes)
                or len(remote) != row["bytes"]
                or _digest(remote) != row["sha256"]):
            raise RuntimeError("REPORT_REMOTE_ARTIFACT_READBACK_FAILED")
        verified.append({
            "id": ident, "name": row["name"], "sha256": row["sha256"],
            "bytes": row["bytes"], "mime": row["mime"],
        })
    content = {
        "schema": "Family.W8.ReportArchive.v1",
        "state": "COMPLETE",
        **{key:value for key,value in plan["receipt"].items()
           if key not in ("schema", "uploads")},
        "files": verified,
    }
    result = _canonical(content)
    return {
        "status": "ARTIFACTS_REMOTE_VERIFIED__MANIFEST_PENDING",
        "manifest_filename": plan["manifest_filename"],
        "manifest_bytes": result,
        "manifest_sha256": _digest(result),
        "folder_id": official,
        "trade_authorization": "NONE",
    }


def verify_published_manifest(manifest_plan, receipt, freshly_fetched_bytes):
    """Final success requires separately uploaded and fetched Drive manifest."""
    if manifest_plan.get("status") != "ARTIFACTS_REMOTE_VERIFIED__MANIFEST_PENDING":
        raise ValueError("REPORT_MANIFEST_PLAN_REQUIRED")
    actual_name = (receipt.get("file_name") or receipt.get("name") or receipt.get("title")
                   if isinstance(receipt,dict) else None)
    if (not isinstance(receipt, dict) or receipt.get("success") is not True
            or actual_name != manifest_plan["manifest_filename"]
            or receipt.get("parent_id") != manifest_plan["folder_id"]
            or not _string(receipt.get("id"))):
        raise PermissionError("REPORT_MANIFEST_REMOTE_RECEIPT_MISMATCH")
    if (not isinstance(freshly_fetched_bytes, bytes)
            or _digest(freshly_fetched_bytes) != manifest_plan["manifest_sha256"]
            or freshly_fetched_bytes != manifest_plan["manifest_bytes"]):
        raise RuntimeError("REPORT_MANIFEST_REMOTE_READBACK_FAILED")
    return {
        "status": "PERSISTED_REMOTE_VERIFIED",
        "manifest_file_id": receipt["id"],
        "manifest_sha256": manifest_plan["manifest_sha256"],
        "folder_id": manifest_plan["folder_id"],
        "trade_authorization": "NONE",
    }
