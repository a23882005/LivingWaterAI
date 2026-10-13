"""Offline package consistency check; neither authorizes Gate A nor verifies provenance."""
from pathlib import Path
from pf_external_evidence_inventory import inspect_inventory
from pf_evidence_digest_verify import check_artifact
from pf_gate_a_checklist import REQUIRED_EVIDENCE

def verify_package(entries, local_paths, now=None, trusted_root=None):
    result={"state":"HOLD","gate_a":"HOLD","verification":"NOT_INDEPENDENTLY_VERIFIED","artifacts":{}}
    inventory=inspect_inventory(entries, now)
    result["inventory"]=inventory
    if inventory["state"]!="REVIEW_PACKAGE_READY":
        return result
    if not isinstance(local_paths,dict) or set(local_paths)!=set(REQUIRED_EVIDENCE):
        return result
    root=None
    if trusted_root is not None:
        try:
            root=Path(trusted_root).resolve(strict=True)
            if not root.is_dir():
                result["path_policy"]="invalid_trusted_root"
                return result
        except (OSError, RuntimeError, ValueError, TypeError):
            result["path_policy"]="invalid_trusted_root"
            return result
    seen_paths=set()
    seen_digests=set()
    for key in REQUIRED_EVIDENCE:
        path=local_paths.get(key)
        if not isinstance(path,(str,Path)):
            return result
        try:
            canonical=Path(path).resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            result["artifacts"][key]="invalid_artifact_path"
            return result
        if root is not None and not canonical.is_relative_to(root):
            result["artifacts"][key]="outside_trusted_root"
            return result
        if canonical in seen_paths:
            result["artifacts"][key]="duplicate_artifact_path"
            return result
        seen_paths.add(canonical)
        digest=entries[key]["sha256"]
        if digest in seen_digests:
            result["artifacts"][key]="duplicate_artifact_digest"
            return result
        seen_digests.add(digest)
        checked=check_artifact(path,entries[key]["sha256"])
        result["artifacts"][key]=checked["reason"]
        if not checked["match"]:
            return result
    result["state"]="FILES_MATCH_INVENTORY"
    return result
