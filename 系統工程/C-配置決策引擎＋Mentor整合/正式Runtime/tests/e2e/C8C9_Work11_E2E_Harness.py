"""C8C9 Work11 - neutral E2E harness + frozen-scenario evaluator.

Work11 deliberately does NOT import or own Work3-Work9/V82/V75 business logic.
A future Work supplies an executor callable. Expected invariants are authored and
frozen in scenario JSON before execution. Actual runtime output is captured only
as observed evidence and can never be promoted into expected output by this file.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from jsonschema import Draft202012Validator

HARNESS_CONTRACT = "LivingWaterAI.C8C9.Work11.E2EHarness"
HARNESS_VERSION = "C8C9-W11-E2E-HARNESS-v1.0.0"

class HarnessError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code=code; self.detail=detail

def _canon(v: Any) -> Any:
    try:
        return json.loads(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False))
    except Exception as exc:
        raise HarnessError("C8C9.W11.NON_JSON",str(exc))

def digest(v: Any) -> str:
    raw=json.dumps(_canon(v),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()

def file_sha256(path: Path) -> str:
    h=sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def _pointer(root: Any, ptr: str) -> Any:
    if ptr=="": return root
    if not isinstance(ptr,str) or not ptr.startswith("/"):
        raise HarnessError("C8C9.W11.POINTER",f"invalid JSON pointer: {ptr!r}")
    cur=root
    for raw in ptr.split("/")[1:]:
        token=raw.replace("~1","/").replace("~0","~")
        if isinstance(cur,list):
            try: cur=cur[int(token)]
            except Exception: raise HarnessError("C8C9.W11.POINTER",f"missing list path {ptr}")
        elif isinstance(cur,Mapping):
            if token not in cur: raise HarnessError("C8C9.W11.POINTER",f"missing object path {ptr}")
            cur=cur[token]
        else: raise HarnessError("C8C9.W11.POINTER",f"non-container on {ptr}")
    return cur

def _exists(root: Any, ptr: str) -> bool:
    try: _pointer(root,ptr); return True
    except HarnessError: return False

def load_scenario(path: Path, schema_path: Path) -> dict[str,Any]:
    spec=json.loads(path.read_text(encoding="utf-8")); schema=json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errs=sorted(Draft202012Validator(schema).iter_errors(spec),key=lambda e:list(e.absolute_path))
    if errs:
        e=errs[0]; loc="/".join(map(str,e.absolute_path)) or "$"
        raise HarnessError("C8C9.W11.SCENARIO_SCHEMA",f"{loc}: {e.message}")
    if "expected_output" in spec or "golden_output" in spec:
        raise HarnessError("C8C9.W11.SELF_PROOF_FORBIDDEN","expected output payload forbidden")
    return spec

def load_fixtures(spec: Mapping[str,Any], root: Path) -> dict[str,Any]:
    out={}
    for ref in spec["fixtures"]:
        p=(root/ref["path"]).resolve()
        try: p.relative_to(root.resolve())
        except Exception: raise HarnessError("C8C9.W11.FIXTURE_PATH",ref["path"])
        if not p.is_file(): raise HarnessError("C8C9.W11.FIXTURE_MISSING",ref["path"])
        actual=file_sha256(p)
        if actual!=ref["sha256"]: raise HarnessError("C8C9.W11.FIXTURE_HASH",f"{ref['role']} {actual} != {ref['sha256']}")
        if ref.get("media_type")=="application/json":
            out[ref["role"]]=json.loads(p.read_text(encoding="utf-8"))
        else: out[ref["role"]]=p.read_bytes()
    return out

def eval_invariant(inv: Mapping[str,Any], actual: Any, error_code: str|None) -> tuple[bool,str]:
    t=inv["type"]; ptr=inv.get("pointer","")
    try:
        if t=="error_code_equals": return error_code==inv["expected"], str(error_code)
        if error_code is not None: return False,f"unexpected error {error_code}"
        if t=="pointer_exists": return _exists(actual,ptr),ptr
        if t=="pointer_absent": return not _exists(actual,ptr),ptr
        val=_pointer(actual,ptr)
        if t=="pointer_equals": return _canon(val)==_canon(inv["expected"]),repr(val)
        if t=="pointer_true": return val is True,repr(val)
        if t=="pointer_false": return val is False,repr(val)
        if t=="pointer_in": return val in inv["expected"],repr(val)
        if t=="array_contains": return isinstance(val,list) and inv["expected"] in val,repr(val)
        if t=="array_unique": return isinstance(val,list) and len(val)==len({json.dumps(_canon(x),ensure_ascii=False,sort_keys=True) for x in val}),repr(val)
        if t=="same_pointer": return _canon(val)==_canon(_pointer(actual,inv["other_pointer"])),repr(val)
        return False,f"unsupported invariant type {t}"
    except HarnessError as exc: return False,exc.code

def execute(spec: Mapping[str,Any], fixture_root: Path, executor: Callable[[dict[str,Any],Mapping[str,Any]],Any], executor_id: str) -> dict[str,Any]:
    fixtures=load_fixtures(spec,fixture_root)
    actual=None; err_code=None; err_detail=None
    try:
        actual=executor(deepcopy(fixtures),spec)
        actual=_canon(actual)
    except Exception as exc:
        err_code=getattr(exc,"code",type(exc).__name__); err_detail=str(exc)
    results=[]
    for inv in spec["expected_invariants"]:
        ok,detail=eval_invariant(inv,actual,err_code)
        results.append({"id":inv["id"],"pass":bool(ok),"detail":detail,"authority":inv["authority"]})
    expected_error=spec.get("expected_error_code")
    if expected_error is None: expected_error_ok=err_code is None
    else: expected_error_ok=err_code==expected_error
    all_ok=expected_error_ok and all(r["pass"] for r in results)
    fixture_digests={r["role"]:r["sha256"] for r in spec["fixtures"]}
    capture={
      "contract_name":"LivingWaterAI.C8C9.Work11.E2ECapture",
      "contract_version":"C8C9-W11-CAP-v1.0.0",
      "scenario_id":spec["scenario_id"],"target_work":spec["target_work"],"run_id":spec["run_id"],
      "executor_id":executor_id,"status":"PASS" if all_ok else "FAIL",
      "fixture_digests":fixture_digests,"version_freeze":deepcopy(spec["version_freeze"]),
      "actual_output_sha256":None if actual is None else digest(actual),"actual_output":actual,
      "observed_error_code":err_code,"observed_error_detail":err_detail,
      "expected_error_code":expected_error,"invariant_results":results,
      "lineage":deepcopy(spec["lineage"]),
      "expected_source_policy":"STATIC_INVARIANTS_AUTHORED_BEFORE_RUNTIME_EXECUTION_NO_ACTUAL_TO_EXPECTED_PROMOTION"
    }
    return capture

def write_capture(capture: Mapping[str,Any], path: Path) -> str:
    """Persist observed evidence only; never mutates scenario expected invariants."""
    payload=_canon(capture)
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")
    path.write_bytes(raw)
    return sha256(raw).hexdigest()

def reproducibility_equal(a: Mapping[str,Any], b: Mapping[str,Any]) -> bool:
    return a.get("observed_error_code")==b.get("observed_error_code") and a.get("actual_output_sha256")==b.get("actual_output_sha256") and a.get("invariant_results")==b.get("invariant_results")
