"""Crash/retry/resume guards for an isolated in-memory test journal only."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock
from typing import Any, Mapping

_LOCK=RLock()

def _hash(value:Any)->str:
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def new_test_state(*,project_id:str,client_id:str,run_id:str,version:int,checkpoint_id:str,state_payload:Mapping[str,Any])->dict[str,Any]:
    return {"storage_scope":"ISOLATED_TEST_STAGING","project_id":project_id,"client_id":client_id,"run_id":run_id,
      "current_version":version,"checkpoint":{"checkpoint_id":checkpoint_id,"version":version,"state":deepcopy(dict(state_payload))},
      "operations":{},"mutation_count":0,"last_error_count":0}

def resume_from_checkpoint(state:Mapping[str,Any],*,project_id:str,client_id:str,run_id:str,checkpoint_id:str)->dict[str,Any]:
    if state.get("storage_scope")!="ISOLATED_TEST_STAGING":return {"status":"BLOCKED","issue_codes":["STAGING_SCOPE_REQUIRED"],"state":deepcopy(dict(state)),"no_mutation":True}
    if state.get("project_id")!=project_id or state.get("client_id")!=client_id or state.get("run_id")!=run_id:
        return {"status":"BLOCKED","issue_codes":["RECOVERY_IDENTITY_MISMATCH"],"state":deepcopy(dict(state)),"no_mutation":True}
    cp=state.get("checkpoint") or {}
    if cp.get("checkpoint_id")!=checkpoint_id or cp.get("version")!=state.get("current_version"):
        return {"status":"BLOCKED","issue_codes":["CHECKPOINT_STALE_OR_INVALID"],"state":deepcopy(dict(state)),"no_mutation":True}
    return {"status":"RESUMED","checkpoint_id":checkpoint_id,"version":cp["version"],"state_payload":deepcopy(cp["state"]),"state":deepcopy(dict(state)),"no_mutation":True}

def apply_event(state:dict[str,Any],event:Mapping[str,Any],*,journal_available:bool=True,
                response_lost_after_commit:bool=False,retry_count:int=0)->dict[str,Any]:
    """Atomically apply one TEST_STAGING mutation or return a stable safe error."""
    with _LOCK:
        def block(code:str,*,retryable:bool=False,status:str="BLOCKED"):
            return {"status":status,"issue_codes":[code],"state":deepcopy(state),"no_mutation":True,"retryable":retryable,
                    "human_action":"CHECK_AND_RETRY" if retryable and retry_count<2 else "MANUAL_REVIEW" if retryable else "NONE"}
        if state.get("storage_scope")!="ISOLATED_TEST_STAGING":return block("STAGING_SCOPE_REQUIRED")
        for key in ("request_id","run_id","project_id","client_id","expected_version","confirmation_id","checkpoint_id","action","payload"):
            if key not in event:return block("EVENT_REQUIRED_FIELD_MISSING:"+key)
        if event.get("project_id")!=state.get("project_id"):return block("PROJECT_MISMATCH")
        if event.get("client_id")!=state.get("client_id") or event.get("run_id")!=state.get("run_id"):return block("CLIENT_OR_RUN_MISMATCH")
        if event.get("authorized") is not True:return block("OPERATION_NOT_AUTHORIZED")
        if event.get("action") not in {"STAGING_FINANCIAL_CHANGE","STAGING_CONFIRMATION"}:return block("ACTION_NOT_ALLOWED")
        if not journal_available:
            return block("STAGING_JOURNAL_UNAVAILABLE",retryable=True,status="RETRY" if retry_count<3 else "NEEDS_MANUAL")
        op_key=str(event.get("confirmation_id")); payload_hash=_hash({"action":event.get("action"),"payload":event.get("payload"),"client_id":event.get("client_id"),"project_id":event.get("project_id")})
        prior=state.get("operations",{}).get(op_key)
        if prior:
            if prior.get("payload_hash")==payload_hash:
                return {"status":"IDEMPOTENT","operation_id":prior["operation_id"],"state":deepcopy(state),"no_mutation":True,"retryable":False,"issue_codes":[]}
            return block("IDEMPOTENCY_KEY_PAYLOAD_CONFLICT")
        cp=state.get("checkpoint") or {}
        if event.get("checkpoint_id")!=cp.get("checkpoint_id"):return block("CHECKPOINT_MISMATCH")
        if event.get("expected_version")!=state.get("current_version"):return block("STALE_EXPECTED_VERSION")
        operation_id="OP-"+_hash({"key":op_key,"payload_hash":payload_hash})[:20]
        next_version=state["current_version"]+1
        state.setdefault("operations",{})[op_key]={"operation_id":operation_id,"payload_hash":payload_hash,"status":"APPLIED_IN_TEST_STAGING","version":next_version}
        state["current_version"]=next_version
        state["mutation_count"]=int(state.get("mutation_count",0))+1
        state["checkpoint"]={"checkpoint_id":"CP-"+str(next_version),"version":next_version,
                              "state":{"last_operation_id":operation_id,"action":event["action"],"payload_hash":payload_hash}}
        state["last_error_count"]=0
        if response_lost_after_commit:
            return {"status":"RETRY","issue_codes":["RESPONSE_LOST_AFTER_STAGING_COMMIT"],"operation_id":operation_id,
                    "state":deepcopy(state),"no_mutation":False,"retryable":True,"committed_in_test_staging":True}
        return {"status":"APPLIED_IN_TEST_STAGING","issue_codes":[],"operation_id":operation_id,
                "state":deepcopy(state),"no_mutation":False,"retryable":False,"committed_in_test_staging":True}
