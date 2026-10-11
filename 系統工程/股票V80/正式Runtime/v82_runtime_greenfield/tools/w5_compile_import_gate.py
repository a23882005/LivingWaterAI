from __future__ import annotations
import ast, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
sys.path.insert(0,str(SRC))
checks=[]
for p in sorted(SRC.rglob('*.py')):
    ast.parse(p.read_text(encoding='utf-8')); checks.append((f'AST:{p.relative_to(ROOT)}','PASS'))
import livingwater_v82_runtime as rt
checks.append(('IMPORT:livingwater_v82_runtime','PASS'))
validators=rt.compile_all_schemas(); checks.append((f'SCHEMA_COMPILE:{len(validators)}','PASS'))
from livingwater_v82_runtime.enums import FundingDomain, CashBasis, CANONICAL_DEPLOYMENT_TARGET_RATE_PCT, OrderLifecycleState
assert [x.value for x in FundingDomain]==['TW_LOCAL_BROKER','TW_SUB_BROKERAGE','US_BROKER']
assert [x.value for x in CashBasis]==['AVAILABLE']
assert CANONICAL_DEPLOYMENT_TARGET_RATE_PCT==(10,20,30,45,60,75,85,95,100)
assert len(OrderLifecycleState)==10
checks.append(('CANONICAL_ENUM_SMOKE','PASS'))
print(json.dumps({'gate':'W5_COMPILE_IMPORT','result':'PASS','checks':checks},ensure_ascii=False,indent=2))
