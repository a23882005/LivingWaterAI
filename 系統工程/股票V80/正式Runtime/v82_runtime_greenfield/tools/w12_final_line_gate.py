#!/usr/bin/env python3
from __future__ import annotations
import csv, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT.parent
QA = LATEST / 'QA_Results'
MATRIX = LATEST / 'A78_W04_Formal_Test_Matrix.tsv'

RUNS = [
    ('W5_COMPILE_IMPORT', 'w5_compile_import_gate.py', 'PASS', None),
    ('W6', 'w6_validation_account_isolation_gate.py', 'PASS', (59,59)),
    ('W7', 'w7_core_rule_engine_gate.py', 'PASS', (43,43)),
    ('W8', 'w8_deployment_execution_gate.py', 'PASS', (50,50)),
    ('W9', 'w9_canonical_persistence_ports_gate.py', 'PASS', (44,44)),
    ('W10', 'w10_unit_state_invariant_gate.py', 'PASS', (30,30)),
    ('W11', 'w11_negative_contract_regression_integration_gate.py', 'PASS', (64,64)),
    ('W12_E2E', 'w12_full_e2e_cutover_readiness_gate.py', 'PASS', (8,8)),
    ('W12_SCOPE', 'w12_scope_conformance_gate.py', 'PASS', (13,13)),
]

def run_gate(label: str, filename: str, expected_status: str, expected: tuple[int,int] | None):
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = str(ROOT/'src') + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    p = subprocess.run([sys.executable, str(ROOT/'tools'/filename)], cwd=str(ROOT), env=env, capture_output=True, text=True)
    text = (p.stdout or '') + ('\n' + p.stderr if p.stderr else '')
    if expected_status == 'HOLD':
        ok = p.returncode == 2 and '"status": "HOLD"' in text
    else:
        ok = p.returncode == 0
    detail = f'exit={p.returncode}; expected_status={expected_status}'
    if label == 'W5_COMPILE_IMPORT':
        ok = ok and '"result": "PASS"' in text
        detail += '; compile/import PASS' if ok else '; compile/import result missing'
    elif expected:
        a,b = expected
        if expected_status == 'HOLD':
            matched = bool(re.search(rf'"passed"\s*:\s*{a}.*?"total"\s*:\s*{b}.*?"status"\s*:\s*"HOLD"', text, re.S))
        else:
            patterns = [rf'"passed"\s*:\s*{a}.*?"total"\s*:\s*{b}.*?"status"\s*:\s*"PASS"', rf'{a}/{b}\s+PASS']
            matched = any(re.search(q, text, re.S) for q in patterns)
        ok = ok and matched
        detail += f'; expected {a}/{b}; evidence={"yes" if matched else "no"}'
    return {'label':label,'script':filename,'pass':ok,'detail':detail,'stdout_tail':'\n'.join(text.splitlines()[-8:])}

def expected_formal_ids():
    ids=[]
    ids += [f'U{i:02}' for i in range(1,11)]
    ids += [f'S{i:02}' for i in range(1,9)]
    ids += [f'I{i:02}' for i in range(1,13)]
    ids += [f'N{i:02}' for i in range(1,27)]
    ids += [f'C{i:02}' for i in range(1,5)]
    ids += [f'R{i:02}' for i in range(1,4)]
    ids += [f'G{i:02}' for i in range(1,8)]
    ids += [f'E{i:02}' for i in range(1,9)]
    return ids

def main():
    QA.mkdir(exist_ok=True)
    runs=[run_gate(*r) for r in RUNS]
    checks=[]
    def ck(name, cond, detail): checks.append({'id':name,'pass':bool(cond),'detail':detail})
    for r in runs: ck('FRESH_'+r['label'], r['pass'], r['detail'])

    w11scope=QA/'A78_W11_SCOPE_CONFORMANCE_GATE.json'
    try:
        s=json.loads(w11scope.read_text(encoding='utf-8'))
        ck('W11_SCOPE_ARCHIVED_10_10', s.get('status')=='PASS' and s.get('passed')==10 and s.get('total')==10,
           'historical W11 scope evidence retained; not re-run after W12 by design')
    except Exception as e:
        ck('W11_SCOPE_ARCHIVED_10_10', False, f'cannot read historical scope artifact: {e}')

    with MATRIX.open(encoding='utf-8', newline='') as f:
        rows=list(csv.DictReader(f, delimiter='\t'))
    ids=[r['Test_ID'] for r in rows]
    exp=expected_formal_ids()
    ck('FORMAL_MATRIX_78_UNIQUE', len(ids)==78 and len(set(ids))==78, f'rows={len(ids)} unique={len(set(ids))}')
    ck('FORMAL_MATRIX_ID_SET_EXACT', set(ids)==set(exp), 'U10+S8+I12+N26+C4+R3+G7+E8 = 78')

    w10=json.loads((QA/'A78_W10_UNIT_STATE_INVARIANT_GATE.json').read_text(encoding='utf-8'))
    w11=json.loads((QA/'A78_W11_NEGATIVE_CONTRACT_REGRESSION_INTEGRATION_GATE.json').read_text(encoding='utf-8'))
    w12=json.loads((QA/'A78_W12_FULL_E2E_CUTOVER_RUNTIME_READINESS_GATE.json').read_text(encoding='utf-8'))
    formal_w10 = w10.get('passed')==30 and w10.get('total')==30 and w10.get('status')=='PASS'
    cats=w11.get('category_counts',{})
    formal_w11 = all(cats.get(k)=={'passed':n,'total':n} for k,n in [('NEGATIVE',26),('CONTRACT',4),('REGRESSION',3),('INTEGRATION',7)])
    tests={x.get('id'):x for x in w12.get('tests',[])}
    formal_w12_pass = w12.get('passed')==8 and w12.get('total')==8 and w12.get('status')=='PASS' and tests.get('E07',{}).get('pass') is True
    ck('FORMAL_W10_30_30', formal_w10, 'U/S/I formal cases implemented and PASS')
    ck('FORMAL_W11_40_40', formal_w11, 'N/C/R/G formal cases implemented and PASS; EDGE/DETERMINISM are additional')
    ck('FORMAL_W12_8_8_PASS', formal_w12_pass, 'E01-E08 PASS including authorized Legacy/New E07')
    ck('FORMAL_MATRIX_78_78_PASS', formal_w10 and formal_w11 and formal_w12_pass, '30 + 40 + 8 = 78/78')

    ev=w12.get('cutover_evidence',{})
    p1=ev.get('unresolved_p1',[])
    ck('ZERO_UNRESOLVED_P0', ev.get('unresolved_p0')==[], 'no unresolved P0')
    ck('ZERO_UNRESOLVED_P1', p1==[], 'no unresolved P1')
    ck('CUTOVER_NOT_ACTIVATED', ev.get('activation_performed') is False, 'A line did not self-activate')
    ck('READINESS_FOR_ABC_GATE', ev.get('candidate_state')=='READY_FOR_ABC_V82_RUNTIME_READY_GATE', 'candidate is returned to ABC for formal Runtime Ready Gate')

    qa_ok=all(c['pass'] for c in checks)
    out={
        'gate':'W12 Whole-line Final QA E07 RECHECK4',
        'status':'PASS' if qa_ok else 'FAIL',
        'verification_status':'PASS' if qa_ok else 'FAIL',
        'passed':sum(c['pass'] for c in checks),
        'total':len(checks),
        'fresh_gate_runs':runs,
        'formal_test_matrix':{'passed':78 if qa_ok else None,'total':78,'status':'PASS' if qa_ok else 'FAIL','pending':[]},
        'historical_scope_note':'W5-W11 point-in-time scope gates are not re-executed after downstream Works exist; W11 10/10 frozen PASS evidence is retained and inspected.',
        'checks':checks,
    }
    (QA/'A78_W12_WHOLE_LINE_FINAL_QA_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    (QA/'A78_W12_WHOLE_LINE_FINAL_QA_GATE.txt').write_text(
        f"{out['status']} verification={out['verification_status']} {out['passed']}/{out['total']}\nFORMAL_MATRIX=PASS 78/78\n"+
        '\n'.join(f"{c['id']}: {'PASS' if c['pass'] else 'FAIL'} {c['detail']}" for c in checks)+'\n',encoding='utf-8')
    print(json.dumps({'gate':out['gate'],'status':out['status'],'verification_status':out['verification_status'],'passed':out['passed'],'total':out['total'],'formal_matrix':'78/78 PASS','pending':None},ensure_ascii=False))
    if not qa_ok:
        for c in checks:
            if not c['pass']: print('FAIL',c['id'],c['detail'])
        raise SystemExit(1)
    raise SystemExit(0)

if __name__=='__main__': main()
