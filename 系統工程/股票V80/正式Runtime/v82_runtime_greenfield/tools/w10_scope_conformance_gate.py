#!/usr/bin/env python3
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def add(i,p,d=''): checks.append({'id':i,'pass':bool(p),'detail':d})
files=[p for p in ROOT.rglob('*') if p.is_file()]
rel=[str(p.relative_to(ROOT)) for p in files]
add('W10_GATE_PRESENT','tools/w10_unit_state_invariant_gate.py' in rel)
add('NO_W11_TOOL',not any('/w11_' in ('/'+x.lower()) or x.lower().startswith('tools/w11_') for x in rel))
add('NO_W12_TOOL',not any('/w12_' in ('/'+x.lower()) or x.lower().startswith('tools/w12_') for x in rel))
add('NO_NEW_B_C_V75_TREE',not any(x.startswith(('B/','C/','V75/')) for x in rel))
add('NO_C_WORK8_RELEASE',not any('C_WORK8_RELEASED' in p.read_text(errors='ignore') for p in files if p.name!='w10_scope_conformance_gate.py' and p.suffix in {'.py','.md','.json','.txt'}))
text=(ROOT/'tools/w10_unit_state_invariant_gate.py').read_text()
add('MATRIX_UNIT_IDS',all(f"'{x}'" in text for x in [f'U{i:02d}' for i in range(1,11)]))
add('MATRIX_STATE_IDS',all(f"'{x}'" in text for x in [f'S{i:02d}' for i in range(1,9)]))
add('MATRIX_INVARIANT_IDS',all(f"'{x}'" in text for x in [f'I{i:02d}' for i in range(1,13)]))
add('EXACT_W10_CASE_COUNT',len(re.findall(r"check\('[USI]\d{2}'",text))==30)
add('NO_E2E_CUTOVER_CODE',not any(k in text for k in ['shadow_run','dual_run','cutover_execute','runtime_readiness_gate']))
out={'gate':'A78_W10_SCOPE_CONFORMANCE_GATE','passed':sum(x['pass'] for x in checks),'total':len(checks),'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks}
qa=ROOT.parent/'QA_Results';qa.mkdir(exist_ok=True);(qa/'A78_W10_SCOPE_CONFORMANCE_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(f"{out['passed']}/{out['total']} {out['status']}")
if out['status']!='PASS':
    for x in checks:
        if not x['pass']: print('FAIL',x['id'],x['detail'])
    raise SystemExit(1)
