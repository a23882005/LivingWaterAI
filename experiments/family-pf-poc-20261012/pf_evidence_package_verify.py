"""Offline package consistency check; neither authorizes Gate A nor verifies provenance."""
from pathlib import Path
from pf_external_evidence_inventory import inspect_inventory
from pf_evidence_digest_verify import check_artifact
from pf_gate_a_checklist import REQUIRED_EVIDENCE

def verify_package(entries, local_paths, now=None):
    result={"state":"HOLD","gate_a":"HOLD","verification":"NOT_INDEPENDENTLY_VERIFIED","artifacts":{}}
    inventory=inspect_inventory(entries, now)
    result["inventory"]=inventory
    if inventory["state"]!="REVIEW_PACKAGE_READY":
        return result
    if not isinstance(local_paths,dict) or set(local_paths)!=set(REQUIRED_EVIDENCE):
        return result
    for key in REQUIRED_EVIDENCE:
        path=local_paths.get(key)
        if not isinstance(path,(str,Path)):
            return result
        checked=check_artifact(path,entries[key]["sha256"])
        result["artifacts"][key]=checked["reason"]
        if not checked["match"]:
            return result
    result["state"]="FILES_MATCH_INVENTORY"
    return result
