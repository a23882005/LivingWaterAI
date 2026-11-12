from pf_gate_a_readiness import assess_gate_a_cases, REQUIRED_CASES

def batch(value):
    return {key:{"status":value} for key in REQUIRED_CASES}

def test_positive_claims_still_hold():
    out=assess_gate_a_cases(batch("PASS"))
    assert out["state"]=="AWAITING_INDEPENDENT_VERIFICATION"
    assert out["gate_a"]=="HOLD" and out["safe_to_release"] is False

def test_one_failed_case_has_priority():
    items=batch("PASS")
    items["EA-07"]["status"]="FAIL"
    out=assess_gate_a_cases(items)
    assert out["state"]=="FAIL"
    assert out["missing_or_invalid"]==["EA-07"]

def test_missing_and_extra_case_rejected():
    items=batch("PASS")
    items.pop("EA-02")
    assert assess_gate_a_cases(items)["reason"]=="invalid_case_inventory"
    items=batch("PASS")
    items["EA-10"]={"status":"PASS"}
    assert assess_gate_a_cases(items)["reason"]=="invalid_case_inventory"

def test_malformed_status_rejected():
    for bad in ("passed", True, None, 1):
        items=batch("PASS")
        items["EA-03"]["status"]=bad
        assert assess_gate_a_cases(items)["reason"]=="invalid_case_status"

def test_invalid_item_rejected():
    items=batch("PASS")
    items["EA-06"]=None
    assert assess_gate_a_cases(items)["reason"]=="invalid_case_entry"

def test_blocked_case_stays_blocked():
    items=batch("PASS")
    items["EA-09"]["status"]="BLOCKED"
    out=assess_gate_a_cases(items)
    assert out["state"]=="BLOCKED" and out["work13_allowed"] is False

def test_untrusted_details_not_reflected():
    items=batch("PASS")
    items["EA-01"]["private_notes"]="never-echo-this-marker"
    assert "never-echo-this-marker" not in str(assess_gate_a_cases(items))
