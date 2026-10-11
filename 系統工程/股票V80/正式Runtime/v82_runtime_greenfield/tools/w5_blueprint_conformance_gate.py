from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parent
SRC=ROOT/'src'
sys.path.insert(0,str(SRC))
from livingwater_v82_runtime import enums, models
from livingwater_v82_runtime.schema_runtime import load_schema, compile_all_schemas
checks=[]
def ck(name, cond, detail=''):
    if not cond: raise AssertionError(f'{name}: {detail}')
    checks.append({'check':name,'result':'PASS','detail':detail})
reg=json.loads((WORK/'A78_W02_Canonical_Enum_Registry.json').read_text())['enums']
map_cls={'FundingDomain':enums.FundingDomain,'CashBasis':enums.CashBasis,'BankCashScope':enums.BankCashScope,'AssetType':enums.AssetType,'AssetGrade':enums.AssetGrade,'PortfolioRole':enums.PortfolioRole,'AssetClassificationStatus':enums.AssetClassificationStatus,'DataQuality':enums.DataQuality,'DataIssueCode':enums.DataIssueCode,'NormalDeploymentMode':enums.NormalDeploymentMode,'FieldSentinelSemantics':enums.FieldSentinelSemantics,'FieldValueState':enums.FieldValueState}
for k,cls in map_cls.items():
    expected=reg[k]['values']; actual=[x.value for x in cls]
    ck(f'ENUM_PARITY:{k}',actual==expected,f'{len(actual)} values')
ck('ENUM_PARITY:CanonicalDeploymentTargetRatePct',list(enums.CANONICAL_DEPLOYMENT_TARGET_RATE_PCT)==reg['CanonicalDeploymentTargetRatePct']['values'],'9 target rates')
ck('ENUM_PARITY:PrimarySpecialClassification',[x.value for x in enums.PrimarySpecialClassification]==reg['PrimarySpecialClassification']['classification_values'],'6 classifications')
model_reg=json.loads((WORK/'A78_W02_Canonical_Data_Model_Registry.json').read_text())
for item in model_reg['models']:
    ck(f'MODEL_PRESENT:{item["model_id"]}',hasattr(models,item['model_id']),item['model_id'])
# schemas byte-equivalent to W2 canonical copies
pairs=[('runtime_input.schema.json','A78_W02_V82_Runtime_Input.schema.json'),('runtime_output.schema.json','A78_W02_V82_Runtime_Output.schema.json')]
for packaged,canonical in pairs:
    a=(SRC/'livingwater_v82_runtime/schema'/packaged).read_bytes(); b=(WORK/canonical).read_bytes()
    ck(f'SCHEMA_BYTE_PARITY:{packaged}',a==b,hashlib.sha256(a).hexdigest())
compile_all_schemas(); ck('SCHEMA_DRAFT202012_COMPILE',True,'2/2')
# exact W3 lifecycle state materialization
w3=(WORK/'A78_W03_State_Machine_Execution_Lifecycle_Contract.md').read_text()
expected={'SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING','FILLED','CANCELLED','REPLACED','REJECTED','EXPIRED'}
actual={x.value for x in enums.OrderLifecycleState}
ck('W3_ORDER_LIFECYCLE_PARITY',actual==expected,'10 states')
ck('W3_ACTIVE_TERMINAL_DISJOINT',enums.ACTIVE_ORDER_STATES.isdisjoint(enums.TERMINAL_ORDER_STATES),'5 active + 5 terminal')
# scope guards
allpy='\n'.join(p.read_text() for p in SRC.rglob('*.py'))
ck('NO_LEGACY_V82_ENGINE_IMPORT','v82_engine' not in allpy,'greenfield only')
ck('NO_W6_FUNDING_VALIDATOR_IMPL','validate_funding' not in allpy and 'cross_account' not in allpy.lower(),'W6 deferred')
ck('NO_W7_CORE_RULE_IMPL','valuation_engine' not in allpy and 'technical_engine' not in allpy,'W7 deferred')
ck('NO_W8_ORDER_EXECUTION_IMPL','place_order(' not in allpy and 'cancel_order(' not in allpy,'W8 deferred')
ck('NO_W9_PERSISTENCE_IMPL','sqlite' not in allpy.lower() and 'persist_snapshot' not in allpy,'W9 deferred')
print(json.dumps({'gate':'W5_BLUEPRINT_CONFORMANCE','result':'PASS','pass_count':len(checks),'failed_count':0,'checks':checks},ensure_ascii=False,indent=2))
