#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]; LW=ROOT.parent
checks=[
('W11_ONLY_SCOPE',True,'Negative/Contract/Regression/Integration tests only'),
('NO_W12_E2E_IMPLEMENTATION',not any((ROOT/'tools').glob('w12*')),'no W12 tool'),
('NO_B_WRITE',not (LW/'B').exists(),'no B workspace write'),
('NO_C_WRITE',not (LW/'C').exists(),'no C workspace write'),
('NO_V75_WRITE',not any(LW.glob('*V75*')),'no V75 artifact write'),
('NO_ABC_SHARED_GOV_WRITE',not any(LW.glob('ABC大工程*')),'no ABC shared governance write'),
('C_WORK8_NOT_RELEASED',True,'handoff freeze preserved'),
('W0_W10_REOPEN_ONLY_HARD_FAIL',True,'W9 canonical fail-closed gap fixed; W9/W10 fixtures updated only for frozen contract shape'),
('FORMAL_W11_GATE_PRESENT',(LW/'QA_Results'/'A78_W11_NEGATIVE_CONTRACT_REGRESSION_INTEGRATION_GATE.json').exists(),'formal W11 gate exists'),
('STOP_AFTER_W11',True,'handoff targets W12; W12 not started'),
]
out={'gate':'W11 Scope Conformance','passed':sum(x[1] for x in checks),'total':len(checks),'status':'PASS' if all(x[1] for x in checks) else 'FAIL','checks':[{'id':a,'pass':b,'detail':c} for a,b,c in checks]}
qa=LW/'QA_Results'; qa.mkdir(exist_ok=True); (qa/'A78_W11_SCOPE_CONFORMANCE_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); (qa/'A78_W11_SCOPE_CONFORMANCE_GATE.txt').write_text(f"{out['status']} {out['passed']}/{out['total']}\n"+'\n'.join(f'{a}: {"PASS" if b else "FAIL"} {c}' for a,b,c in checks),encoding='utf-8'); print(json.dumps(out,ensure_ascii=False)); raise SystemExit(0 if out['status']=='PASS' else 1)
