"""Gate A readiness inventory: process evidence only, never release authorization."""
REQUIRED_CASES=("EA-01","EA-02","EA-03","EA-04","EA-05","EA-06","EA-07","EA-08","EA-09")
STATES=("PASS","FAIL","BLOCKED")

def assess_gate_a_cases(cases):
    result={"gate_a":"HOLD","work13_allowed":False,"safe_to_release":False,
            "state":"BLOCKED","cases":{key:"BLOCKED" for key in REQUIRED_CASES},
            "missing_or_invalid":list(REQUIRED_CASES)}
    if not isinstance(cases,dict) or set(cases)!=set(REQUIRED_CASES):
        result["reason"]="invalid_case_inventory"
        return result
    for key in REQUIRED_CASES:
        entry=cases[key]
        if not isinstance(entry,dict):
            result["reason"]="invalid_case_entry"
            return result
        status=entry.get("status")
        if not isinstance(status,str) or status not in STATES:
            result["reason"]="invalid_case_status"
            return result
        result["cases"][key]=status
    result["missing_or_invalid"]=[key for key in REQUIRED_CASES if result["cases"][key]!="PASS"]
    if "FAIL" in result["cases"].values():
        result["state"]="FAIL"
    elif result["missing_or_invalid"]:
        result["state"]="BLOCKED"
    else:
        result["state"]="AWAITING_INDEPENDENT_VERIFICATION"
    result["reason"]="self_report_only_no_release_authority"
    return result
