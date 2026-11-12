"""Strict offline reviewer preflight; never grants Gate A or release permission."""
from pf_evidence_package_verify import verify_package

def review_preflight(entries, local_paths, trusted_root, now=None):
    result={"state":"HOLD","gate_a":"HOLD","verification":"NOT_INDEPENDENTLY_VERIFIED"}
    if trusted_root is None:
        result["reason"]="trusted_root_required"
        return result
    checked=verify_package(entries,local_paths,now,trusted_root=trusted_root)
    result["package"]=checked
    if checked["state"]!="FILES_MATCH_INVENTORY":
        result["reason"]="package_not_verified"
        return result
    result["state"]="READY_FOR_INDEPENDENT_REVIEW"
    result["reason"]="offline_bytes_consistent_only"
    return result
