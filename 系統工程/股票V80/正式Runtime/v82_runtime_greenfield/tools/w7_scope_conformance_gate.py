from pathlib import Path
import ast,json
ROOT=Path(__file__).resolve().parents[1]
core=(ROOT/'src/livingwater_v82_runtime/core_rules.py').read_text()
tree=ast.parse(core)
checks=[]
def ck(n,c): checks.append((n,bool(c)))
for token in ['Data Sufficiency','valuation','fundamentals','technical','hard-gate','structural-risk']:
    ck('HAS_'+token.upper().replace(' ','_').replace('-','_'), token.lower() in core.lower())
# Forbidden W8/W9 implementation responsibilities must not appear as functions/classes.
names={n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
for bad in ['place_order','build_order','calculate_quantity','deployment_stage','persist','save_snapshot','broker_adapter','order_intent']:
    ck('NO_'+bad.upper(), all(bad not in n.lower() for n in names))
ck('NO_IO_IMPORT',not any(isinstance(n,(ast.Import,ast.ImportFrom)) and any(a.name in {'sqlite3','requests','httpx','pandas'} for a in n.names) for n in ast.walk(tree)))
ck('NO_W8_TARGET_RATE', 'CANONICAL_DEPLOYMENT_TARGET_RATE_PCT' not in core)
ck('NO_FUNDING_ENGINE', 'FundingDomain' not in core and 'BoundEquityBudgetView' not in core)
failed=[n for n,c in checks if not c]
out={'gate':'A78_W07_SCOPE_CONFORMANCE_GATE','total':len(checks),'passed':len(checks)-len(failed),'failed':failed,'status':'PASS' if not failed else 'FAIL','checks':[{'id':n,'pass':c} for n,c in checks]}
q=ROOT.parent/'QA_Results'; q.mkdir(exist_ok=True); (q/'A78_W07_SCOPE_CONFORMANCE_GATE.json').write_text(json.dumps(out,indent=2))
print(f"{out['passed']}/{out['total']} PASS")
raise SystemExit(1 if failed else 0)
