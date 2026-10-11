from pathlib import Path
root=Path(__file__).resolve().parents[1]
checks={
'W9_CANONICAL_MODULE':(root/'src/livingwater_v82_runtime/canonical_output.py').exists(),
'W9_PERSISTENCE_MODULE':(root/'src/livingwater_v82_runtime/persistence.py').exists(),
'W9_PORTS_MODULE':(root/'src/livingwater_v82_runtime/ports.py').exists(),
'W9_GATE_PRESENT':(root/'tools/w9_canonical_persistence_ports_gate.py').exists(),
'NO_W10_TOOL':not any((root/'tools').glob('w10*')),
'NO_W11_TOOL':not any((root/'tools').glob('w11*')),
'NO_W12_TOOL':not any((root/'tools').glob('w12*')),
'CANONICAL_NO_FUNDING_RECALC':'validate_and_bind_funding' not in (root/'src/livingwater_v82_runtime/canonical_output.py').read_text(),
'CANONICAL_NO_CORE_RECALC':'evaluate_core_rule_state' not in (root/'src/livingwater_v82_runtime/canonical_output.py').read_text(),
'CANONICAL_NO_DEPLOY_RECALC':'calculate_position_gap' not in (root/'src/livingwater_v82_runtime/canonical_output.py').read_text(),
}
passed=sum(checks.values()); print(f'{passed}/{len(checks)} PASS');
for k,v in checks.items(): print(k,'PASS' if v else 'FAIL')
raise SystemExit(0 if passed==len(checks) else 1)
