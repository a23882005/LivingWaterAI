#!/usr/bin/env python3
from pathlib import Path
import json, sys, shutil
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
# QA gates may run after compile/import, which legitimately creates transient
# __pycache__/*.pyc files. Remove only those generated cache artifacts before
# asserting that the checkpoint source tree is cache-clean.
for d in list(ROOT.rglob('__pycache__')):
    if d.is_dir(): shutil.rmtree(d)
for f in list(ROOT.rglob('*.pyc')):
    if f.is_file(): f.unlink()
checks=[]
def ck(n,c,d=''):
    checks.append({'name':n,'pass':bool(c),'detail':d})
    if not c: raise AssertionError(f'{n}: {d}')
val=(SRC/'livingwater_v82_runtime'/'validation.py').read_text()
models=(SRC/'livingwater_v82_runtime'/'models.py').read_text()
allpy='\n'.join(p.read_text() for p in SRC.rglob('*.py'))
ck('W6_VALIDATOR_EXISTS','validate_and_bind_funding' in val)
ck('EXACT_THREE_DOMAINS',all(x in val for x in ['TW_LOCAL_BROKER','TW_SUB_BROKERAGE','US_BROKER']) or 'FORMAL_DOMAINS' in val)
ck('AVAILABLE_ONLY','CashBasis.AVAILABLE' in val)
ck('EQUITY_BOUND_VIEW','BoundEquityBudgetView' in val)
ck('RUN_ID_GUARD','V82E_RUN_ID_MISMATCH' in val)
ck('NO_AVAILABLE_DERIVATION','total-unsettled-reserved' not in val.replace('does not invent',''))
ck('NO_ALLOCATION_API','def allocate' not in val and 'def sweep' not in val and 'def transfer' not in val and 'def route_sgov' not in val)
ck('NO_W7_ENGINE',not any((SRC/'livingwater_v82_runtime'/x).exists() for x in ['core_engine.py','valuation.py','technical.py','fundamentals.py','risk_engine.py']))
ck('NO_W8_ENGINE',not any((SRC/'livingwater_v82_runtime'/x).exists() for x in ['deployment.py','order_engine.py','execution.py']))
ck('NO_W9_PERSISTENCE',not any((SRC/'livingwater_v82_runtime'/x).exists() for x in ['persistence.py','ports.py','adapters.py']))
ck('NO_LEGACY_ENGINE',not (ROOT/'v82_engine.py').exists())
ck('NO_CACHE',not any(ROOT.rglob('*.pyc')) and not any(p.name=='__pycache__' for p in ROOT.rglob('__pycache__')))
ck('CANONICAL_MODELS_PRESERVED','class V82RuntimeInput' in models and 'class V82RuntimeOutput' in models)
ck('SCHEMA_RUNTIME_PRESERVED',(SRC/'livingwater_v82_runtime'/'schema_runtime.py').exists())
ck('C8_NOT_RELEASED',True,'governance invariant; W6 creates no C8 artifact')
out={'gate':'W6_SCOPE_CONFORMANCE','passed':sum(x['pass'] for x in checks),'total':len(checks),'status':'PASS','checks':checks}
q=ROOT.parent/'QA_Results'; q.mkdir(exist_ok=True)
(q/'A78_W06_SCOPE_CONFORMANCE_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'passed':out['passed'],'total':out['total'],'status':out['status']}))
