#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
BASELINE={
  "pyproject.toml": "d02e5373fe45179bfa2e5f61dafe29e6e9aa26181876c800d7714a6182bb8379",
  "src/livingwater_v82_runtime/__init__.py": "290fea5db450ecdaf93b39f87fff44ea082573e90253a53d30b2e83131b206ea",
  "src/livingwater_v82_runtime/canonical_output.py": "9e85fa2c42c046ec0835ecf536d324245ff5dd24d1f9cd77c4f29e6be4d1f433",
  "src/livingwater_v82_runtime/core_rules.py": "4c494b08aa820828596732828b1b4b40d4d16a36a72eb3366ddaa59231e0a546",
  "src/livingwater_v82_runtime/deployment.py": "81e2b13ab208152c47a36338b265c819d79a63810a8378202e50783354d647dd",
  "src/livingwater_v82_runtime/enums.py": "7328cc2fc15112666df0be93d66bb639bae5b880e838a477ec205500bc3de4f9",
  "src/livingwater_v82_runtime/models.py": "f240c0fc296ab635e856779ad43d6cc884bceb619f2f70fa379c8c165adf82fc",
  "src/livingwater_v82_runtime/persistence.py": "69352d5f11af125afbe458901f7ffcf66f4c4579ecb7e89697eda031ab56680b",
  "src/livingwater_v82_runtime/ports.py": "61d3eac516e45fdb992bf7d16a8139102760af2c3ca54fea51ec7ec6e41d362e",
  "src/livingwater_v82_runtime/schema/__init__.py": "e0de44b03a68a67884047802bfbed6616901acb1cbbebbda709ce8fc68ea7439",
  "src/livingwater_v82_runtime/schema/runtime_input.schema.json": "32c112a8a282cb34110e69234daed7dbdbb9292e1ec52aca95015e38126b8c10",
  "src/livingwater_v82_runtime/schema/runtime_output.schema.json": "2a148edc8fc8c3ba647e2cc9095259ec8135a87704a5defbd15b8eaed5c690f9",
  "src/livingwater_v82_runtime/schema_runtime.py": "09ad8c881bf3e57a0982eaa7256c7bd74fc2c55031fc61e10fbaba0daa876875",
  "src/livingwater_v82_runtime/validation.py": "aeaf8d5e8a33919ef43ebda7d25355325ed0d2c26d3c32f5047cad1b61abc370",
  "src/livingwater_v82_runtime/version.py": "1fd3564596fb35b79144f2cffd5d5f01198b357ada9e8ad533e38e63ef3fdae8"
}
checks=[]
def ck(i,cond,detail): checks.append({'id':i,'pass':bool(cond),'detail':detail})

actual={}
for rel in BASELINE:
    p=ROOT/rel
    actual[rel]=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'MISSING'
ck('W0_W11_RUNTIME_HASH_FREEZE',actual==BASELINE,'all W11 runtime/package source hashes unchanged')
noncache=[]
for p in [ROOT/'pyproject.toml',*sorted(SRC.rglob('*'))]:
    if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc': noncache.append(str(p.relative_to(ROOT)))
ck('NO_UNEXPECTED_RUNTIME_SOURCE',set(noncache)==set(BASELINE),'no W12 business runtime file added/removed')
ck('W12_E2E_TOOL_PRESENT',(ROOT/'tools/w12_full_e2e_cutover_readiness_gate.py').is_file(),'W12 readiness harness only')
ck('NO_LEGACY_ENGINE_COPIED',not any(ROOT.rglob('v82_engine.py')),'legacy engine not copied into Greenfield Runtime')
ck('PACKAGE_VERSION_CANDIDATE',(SRC/'livingwater_v82_runtime/version.py').read_text(encoding='utf-8').strip()=='__version__ = "0.9.0"','candidate stays 0.9.0 pending ABC gate')
qa=ROOT.parent/'QA_Results'
e2e=qa/'A78_W12_FULL_E2E_CUTOVER_RUNTIME_READINESS_GATE.json'
obj=json.loads(e2e.read_text(encoding='utf-8')) if e2e.is_file() else {}
tests={x.get('id'):x for x in obj.get('tests',[])}
ck('W12_E2E_PASS_8_8',obj.get('status')=='PASS' and obj.get('passed')==8 and obj.get('total')==8 and tests.get('E07',{}).get('pass') is True,'E01-E08 all pass with authorized E07 shadow evidence')
ev=obj.get('cutover_evidence',{})
ck('ZERO_UNRESOLVED_P0',ev.get('unresolved_p0')==[],'0 unresolved P0')
p1=ev.get('unresolved_p1',[])
ck('ZERO_UNRESOLVED_P1',p1==[],'0 unresolved P1')
ck('NO_SELF_CUTOVER_ACTIVATION',ev.get('activation_performed') is False,'A line must not self-activate/release')
ck('READINESS_FOR_ABC_GATE',ev.get('candidate_state')=='READY_FOR_ABC_V82_RUNTIME_READY_GATE','A line may hand back only as candidate for ABC Runtime Ready Gate; no self-activation')
shadow=ev.get('shadow_cases',[])
ck('AUTHORIZED_E07_SHADOW_PASS',ev.get('shadow_method')=='AUTHORIZED_LEGACY_EXECUTABLE_DUAL_RUN' and ev.get('same_frozen_semantic_input') is True and ev.get('adapter_business_rules_added') is False and ev.get('shadow_coverage')=='10/10' and isinstance(shadow,list),'authorized true Legacy/New dual-run covered all W4 invariants without adapter business rules')
rollback=ev.get('rollback',{})
ck('ROLLBACK_FROZEN_W9_COMPAT_READER',rollback.get('frozen_w9_reader_passed') is True and rollback.get('compatibility_reader')=='FROZEN_W9_JSONL_CONTRACT_READER','rollback compatibility read is independent of current repository class')
release_names=[p.name for p in ROOT.parent.rglob('*') if p.is_file() and ('C_Work8_RELEASE' in p.name or 'C8_RELEASED' in p.name)]
ck('C_WORK8_NOT_RELEASED',not release_names,'no C Work8 release artifact created')

out={'gate':'W12 Scope Conformance E07 RECHECK4','status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','passed':sum(x['pass'] for x in checks),'total':len(checks),'checks':checks}
qa.mkdir(exist_ok=True)
(qa/'A78_W12_SCOPE_CONFORMANCE_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(qa/'A78_W12_SCOPE_CONFORMANCE_GATE.txt').write_text(f"{out['status']} {out['passed']}/{out['total']}\n"+'\n'.join(f"{x['id']}: {'PASS' if x['pass'] else 'FAIL'} {x['detail']}" for x in checks)+'\n',encoding='utf-8')
print(json.dumps({'gate':out['gate'],'passed':out['passed'],'total':out['total'],'status':out['status']},ensure_ascii=False))
if out['status']!='PASS':
    for x in checks:
        if not x['pass']: print('FAIL',x['id'],x['detail'])
    raise SystemExit(1)
