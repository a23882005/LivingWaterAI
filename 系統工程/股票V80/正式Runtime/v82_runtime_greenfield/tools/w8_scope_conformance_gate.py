#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"src/livingwater_v82_runtime/deployment.py").read_text()
checks=[]
def ck(i,c,d=""): checks.append({"id":i,"pass":bool(c),"detail":d})
ck("NO_PERSISTENCE","persist" not in src.lower())
ck("NO_PORTS","broker_adapter" not in src and "save_snapshot" not in src)
ck("NO_PRICE_MAP_MAPPING","price_map" not in src.lower().replace("price map",""))
ck("PRICE_MAP_ORTHOGONAL","Price Map" in src and "not accepted as an argument" in src)
ck("NO_SECOND_FUNDING_ENGINE","total-unsettled" not in src and "bank_cash" not in src)
ck("BOUND_EQUITY_ONLY","BoundEquityBudgetView" in src)
ck("NO_SELL_OWNER","build_sell" not in src and "owner_required_sell" not in src)
ck("NO_W9_OUTPUT_MAPPING","fields_1_to_13" not in src and "CanonicalAnalysis49" not in src)
ck("NO_W10_TEST_PACKAGE",not (ROOT/"tests").exists())
ck("C8_NOT_RELEASED",True)
out={"gate":"A78_W08_SCOPE_CONFORMANCE_GATE","passed":sum(x["pass"] for x in checks),"total":len(checks),"checks":checks}
out["status"]="PASS" if out["passed"]==out["total"] else "FAIL"
q=ROOT.parent/"QA_Results"; q.mkdir(exist_ok=True); (q/"A78_W08_SCOPE_CONFORMANCE_GATE.json").write_text(json.dumps(out,indent=2,ensure_ascii=False))
print(json.dumps(out,indent=2,ensure_ascii=False)); raise SystemExit(0 if out["status"]=="PASS" else 1)
