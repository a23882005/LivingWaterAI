#!/usr/bin/env python3
from __future__ import annotations
import copy, json, sys, tempfile
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from livingwater_v82_runtime.validation import *
from livingwater_v82_runtime.enums import *
from livingwater_v82_runtime.core_rules import *
from livingwater_v82_runtime.deployment import *
from livingwater_v82_runtime.canonical_output import *
from livingwater_v82_runtime.persistence import *
from livingwater_v82_runtime.ports import *
from livingwater_v82_runtime.models import ExecutionAccountRef
from livingwater_v82_runtime.schema_runtime import compile_schema

T=[]
def check(i,cat,fn):
    try: fn(); T.append((i,cat,True,''))
    except Exception as e: T.append((i,cat,False,f'{type(e).__name__}: {e}'))
def eq(a,b,msg=''): assert a==b, msg or f'{a!r}!={b!r}'
def raises(fn, contains=None):
    try: fn()
    except Exception as e:
        if contains: assert contains in str(e),str(e)
        return e
    raise AssertionError('expected exception')
def truth(x): assert x

def base():
    ids=[('TW_LOCAL_BROKER','tw','A'),('TW_SUB_BROKERAGE','sub','B'),('US_BROKER','ib','C')]; ctx=[]
    for d,b,a in ids:
        ctx.append({'domain':d,'broker':b,'account':a,'bucket_new_investment_amount':100,'brokerage_cash_state':{'total':150,'available':100,'unsettled':20,'reserved':10},'executable_budget':{'equity':{'amount':60,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a},'bond':{'amount':40,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a}},'source_reference_ids':[d+'-ref']})
    return {'contract_name':INPUT_CONTRACT_NAME,'contract_version':INPUT_CONTRACT_VERSION,'run_id':'R1','client_project_version':'P1','asset':{'asset_id':'QQQ','asset_type':'BROAD_ETF','asset_grade':'A','portfolio_role':'CORE'},'execution_account':{'domain':'US_BROKER','broker':'ib','account':'C'},'client_target':{'project_target_position':100,'authorization_reference':'AUTH1'},'upstream_v70_snapshot':{'run_id':'R1','upstream_v70_snapshot_id':'V70-1','v70_stock_tactical_budget_amount':100,'v70_stock_tactical_budget_currency':'USD','v70_stock_tactical_budget_status':'KNOWN','v70_stock_tactical_budget_data_as_of':'2026-09-25','v70_original_dry_powder_amount':100,'v70_original_dry_powder_currency':'USD','v70_budget_source_reference':'v70','v70_budget_data_quality':'OK','v70_budget_issue_codes':[]},'confirmed_position_snapshot':{},'source_lineage':['source'],'c7_funding_context':{'contract_name':C7_CONTRACT_NAME,'contract_version':C7_CONTRACT_VERSION,'run_id':'R1','base_currency':'USD','bank_cash_scope':'OUT_OF_SCOPE','total_new_investment_amount':300,'contexts':ctx,'source_reference_ids':['c7']}}
def analysis49():
    vals={k:'KNOWN' for k in CANONICAL_FIELD_NAMES}; vals.update({'execution_amount':Decimal('10'),'execution_quantity':Decimal('1'),'execution_price':Decimal('10'),'project_target_position':Decimal('100'),'confirmed_position':Decimal('20'),'actual_completion_rate':Decimal('.2'),'canonical_deployment_target_rate':Decimal('.3'),'projected_post_fill_completion_rate':Decimal('.3'),'order_submission_plan':{'should_place_order':True,'order_type':'LIMIT','limit_price':Decimal('10'),'quantity':Decimal('1'),'time_in_force':'GTC','scheduling_mode':'MANUAL','broker_or_adapter_constraints':None,'order_intent_id':'x'}})
    return assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82')

def mutate(path, value):
    z=base(); cur=z
    for p in path[:-1]: cur=cur[p]
    if value is _DEL: del cur[path[-1]]
    else: cur[path[-1]]=value
    return z
class _D: pass
_DEL=_D()

# N01-N26 formal negative matrix
check('N01','NEGATIVE',lambda: raises(lambda:validate_and_bind_funding(mutate(['execution_account','broker'],_DEL)),'REQUIRED_FIELD_MISSING'))
def n02(): z=base(); z['execution_account']['account']='NOPE'; raises(lambda:validate_and_bind_funding(z),'EXECUTION_ACCOUNT_NOT_FOUND')
check('N02','NEGATIVE',n02)
def n03(): z=base(); z['c7_funding_context']['contexts'][1]=copy.deepcopy(z['c7_funding_context']['contexts'][2]); raises(lambda:validate_and_bind_funding(z),'DUPLICATE')
check('N03','NEGATIVE',n03)
check('N04','NEGATIVE',lambda: raises(lambda:validate_and_bind_funding(mutate(['c7_funding_context','contexts',2,'domain'],'ILLEGAL')),'ILLEGAL_FUNDING_DOMAIN'))
check('N05','NEGATIVE',lambda: raises(lambda:validate_and_bind_funding(mutate(['c7_funding_context','total_new_investment_amount'],301)),'BUCKET_TOTAL_MISMATCH'))
check('N06','NEGATIVE',lambda: raises(lambda:validate_and_bind_funding(mutate(['c7_funding_context','contexts',2,'executable_budget','equity','amount'],'NaN')),'AMOUNT_INVALID'))
def n07(): z=base(); z['c7_funding_context']['contexts'][2]['executable_budget']['equity']['cash_basis']='UNSETTLED'; raises(lambda:validate_and_bind_funding(z),'CASH_BASIS_NOT_AVAILABLE')
check('N07','NEGATIVE',n07)
def owner_bad(field,val,code): z=base(); z['c7_funding_context']['contexts'][2]['executable_budget']['equity'][field]=val; raises(lambda:validate_and_bind_funding(z),code)
check('N08','NEGATIVE',lambda: owner_bad('source_broker','other','CROSS_BROKER'))
check('N09','NEGATIVE',lambda: owner_bad('source_account','other','CROSS_ACCOUNT'))
check('N10','NEGATIVE',lambda: owner_bad('source_domain','TW_LOCAL_BROKER','CROSS_DOMAIN'))
def n11(): z=base(); leg=z['c7_funding_context']['contexts'][2]['executable_budget']['equity']; leg['source_account']='OTHER'; raises(lambda:validate_and_bind_funding(z),'CROSS_ACCOUNT')
check('N11','NEGATIVE',n11)
check('N12','NEGATIVE',lambda: raises(lambda:reject_v75_equity_funding({'bond_executable_budget':1}),'FORBIDDEN_V75'))
check('N13','NEGATIVE',lambda: raises(lambda:reject_v75_equity_funding({'SGOV_BOND_BUCKET':1}),'FORBIDDEN_V75'))
check('N14','NEGATIVE',lambda: raises(lambda:reject_v75_equity_funding({'SGOV_DRY_POWDER_BUCKET':1}),'FORBIDDEN_V75'))
def n15(): z=base(); z['c7_funding_context']['contexts'][2]['executable_budget']['equity']['amount']=70; z['c7_funding_context']['contexts'][2]['executable_budget']['bond']['amount']=40; raises(lambda:validate_and_bind_funding(z),'EXCEEDS_AVAILABLE')
check('N15','NEGATIVE',n15)
def n16(): z=base(); c=z['c7_funding_context']['contexts'][2]; c['brokerage_cash_state']['available']=120;c['bucket_new_investment_amount']=100;c['executable_budget']['equity']['amount']=70;c['executable_budget']['bond']['amount']=40; raises(lambda:validate_and_bind_funding(z),'EXCEEDS_ACCOUNT_BUCKET')
check('N16','NEGATIVE',n16)
check('N17','NEGATIVE',lambda: raises(lambda:validate_and_bind_funding(mutate(['c7_funding_context','run_id'],'R2')),'RUN_ID_MISMATCH'))
check('N18','NEGATIVE',lambda: raises(lambda:reject_v75_equity_funding({'bank_cash':1}),'FORBIDDEN_V75'))
check('N19','NEGATIVE',n07)
def n20(): z=base(); z['c7_funding_context']['contexts'].pop(); z['c7_funding_context']['total_new_investment_amount']=200; raises(lambda:validate_and_bind_funding(z),'FUNDING_DOMAIN_SET_INVALID')
check('N20','NEGATIVE',n20)
def n21():
    z=base(); z['c7_funding_context']['contexts'][1]['broker']='tw'; z['c7_funding_context']['contexts'][1]['account']='A'
    # owner fields follow changed context so broker+account uniqueness is the failure.
    for leg in z['c7_funding_context']['contexts'][1]['executable_budget'].values(): leg['source_broker']='tw';leg['source_account']='A'
    raises(lambda:validate_and_bind_funding(z),'DUPLICATE_BROKER_ACCOUNT_CONTEXT')
check('N21','NEGATIVE',n21)
def n22():
    vals={k:'KNOWN' for k in CANONICAL_FIELD_NAMES}; vals['latest_price']=0; vals['order_submission_plan']={'should_place_order':False,'order_type':None,'limit_price':None,'quantity':Decimal('0'),'time_in_force':None,'scheduling_mode':None,'broker_or_adapter_constraints':None,'order_intent_id':None}
    raises(lambda:assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82',field_metadata={'latest_price':{'data_quality':'UNKNOWN'}}),'UNKNOWN_COERCION')
check('N22','NEGATIVE',n22)
def n23():
    vals={k:'KNOWN' for k in CANONICAL_FIELD_NAMES}; vals.pop('latest_price'); raises(lambda:assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82'),'49_FIELD_COUNT_MISMATCH')
check('N23','NEGATIVE',n23)
def n24():
    a=analysis49(); v=dict(project_formal_execution_view(a).fields); v['執行金額']=Decimal('999'); raises(lambda:validate_formal_view_against_analysis(a,v),'13_VIEW_MAPPING_CONFLICT')
check('N24','NEGATIVE',n24)
def n25():
    vals={k:v.value for k,v in analysis49().fields.items()}; vals['order_submission_plan']=dict(vals['order_submission_plan']); vals['order_submission_plan']['quantity']=Decimal('2'); a=assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82'); raises(lambda:project_formal_execution_view(a),'ORDER_PLAN_DUPLICATE_VALUE_CONFLICT')
check('N25','NEGATIVE',n25)
def n26():
    vals={k:v.value for k,v in analysis49().fields.items()}; vals['order_submission_plan']={'should_place_order':True}; a=assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82'); raises(lambda:project_formal_execution_view(a),'ORDER_PLAN_SHAPE_INVALID')
check('N26','NEGATIVE',n26)

# C01-C04 contract tests
def c01():
    z=base(); errs=list(compile_schema('runtime_input').iter_errors(z)); eq(errs,[])
    z['contract_version']='BAD'; raises(lambda:validate_and_bind_funding(z),'CONTRACT_CONFLICT')
check('C01','CONTRACT',c01)
def c02():
    z=base(); z['c7_funding_context']['contract_version']='BAD'; raises(lambda:validate_and_bind_funding(z),'FUNDING_CONTEXT_CONTRACT_MISMATCH')
check('C02','CONTRACT',c02)
def c03():
    a=analysis49(); v=project_formal_execution_view(a); eq(tuple(v.fields),FORMAL_OUTPUT_NAMES); eq(v.fields['執行金額'],Decimal('10')); eq(v.fields['執行股數'],Decimal('1')); eq(v.fields['執行價格'],Decimal('10'))
check('C03','CONTRACT',c03)
def c04():
    reg=json.loads((ROOT.parent/'A78_W02_Reason_Error_Code_Registry.json').read_text()); codes={x['code'] for x in reg['contract_error_codes']}; required={'V82E_REQUIRED_FIELD_MISSING','V82E_CROSS_BROKER_FUNDING','V82E_CROSS_ACCOUNT_FUNDING','V82E_CROSS_DOMAIN_FUNDING','V82E_UNKNOWN_COERCION','V82E_49_FIELD_COUNT_MISMATCH','V82E_13_VIEW_MAPPING_CONFLICT','V82E_ORDER_PLAN_DUPLICATE_VALUE_CONFLICT','V82E_ORDER_PLAN_SHAPE_INVALID'}; truth(required<=codes)
check('C04','CONTRACT',c04)

# R01-R03 regression semantics
def r01():
    b=validate_and_bind_funding(base()).bound_equity_budget; eq((b.domain.value,b.broker,b.account,b.amount,b.currency),('US_BROKER','ib','C',Decimal('60'),'USD'))
check('R01','REGRESSION',r01)
def r02():
    # legacy-style cross-account fallback is now an expected rejection, never preserved
    z=base(); z['execution_account']['account']='NOPE'; raises(lambda:validate_and_bind_funding(z),'EXECUTION_ACCOUNT_NOT_FOUND')
check('R02','REGRESSION',r02)
def r03():
    a1=analysis49(); a2=analysis49(); eq(project_formal_execution_view(a1).fields,project_formal_execution_view(a2).fields); eq(content_digest({k:v.value for k,v in a1.fields.items()}),content_digest({k:v.value for k,v in a2.fields.items()}))
check('R03','REGRESSION',r03)

# G01-G07 integration boundaries
def g01():
    z=base(); before=copy.deepcopy(z['upstream_v70_snapshot']); validate_and_bind_funding(z); eq(z['upstream_v70_snapshot'],before)
check('G01','INTEGRATION',g01)
def g02():
    b=validate_and_bind_funding(base()).bound_equity_budget; eq((b.domain.value,b.broker,b.account,b.amount),('US_BROKER','ib','C',Decimal('60')))
check('G02','INTEGRATION',g02)
def g03():
    # broker-confirmed fill may skip local states and is authoritative
    truth(validate_order_transition(OrderLifecycleState.SUBMITTED,OrderLifecycleState.FILLED))
check('G03','INTEGRATION',g03)
def g04():
    b=validate_and_bind_funding(base()).bound_equity_budget; g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=0,canonical_valuation_price=100); p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); x=build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=4,normalized_order_price=9,execution_currency='USD',order_intent_id='G04'); truth(x.execution_quantity%Decimal('4')==0); truth(x.execution_amount<=x.maximum_allowed_buy_amount)
check('G04','INTEGRATION',g04)
def g05():
    with tempfile.TemporaryDirectory() as td:
        r=JsonlSnapshotRepository(td); r.append(snapshot_id='s',kind='V82',run_id='R1',payload={'x':1},rule_version='V82',contract_version='c',source_lineage=('src',),created_at='t',idempotency_key='g05',domain='US_BROKER',broker='ib',account='C'); r.publish('s'); r.compare_and_swap_latest(stream_key='US_BROKER|ib|C',new_snapshot_id='s',expected_snapshot_id=None); r2=JsonlSnapshotRepository(td); eq(r2.latest('US_BROKER|ib|C').payload,{'x':1})
check('G05','INTEGRATION',g05)
def g06():
    a=analysis49(); out=build_runtime_output(analysis=a,run_id='R1',v82_snapshot_id='s',upstream_v70_snapshot_id='v70',asset_id='QQQ',rule_version='V82',contract_name='LivingWaterAI.V82.RuntimeOutput',contract_version='v1',data_as_of='d',evaluated_at='t',source_lineage=('src',),output_status='OK'); validate_formal_view_against_analysis(a,out.fields_1_to_13)
check('G06','INTEGRATION',g06)
def g07():
    for k in ('bond_executable_budget','SGOV_BOND_BUCKET','SGOV_DRY_POWDER_BUCKET','bank_cash'): raises(lambda k=k:reject_v75_equity_funding({k:1}),'FORBIDDEN_V75')
check('G07','INTEGRATION',g07)

# 15 frozen-contract edge cases; no new investment thresholds are introduced.
def edge_zero_equity():
    z=base(); c=z['c7_funding_context']['contexts'][2]; c['executable_budget']['equity']['amount']=0;c['executable_budget']['bond']['amount']=100; eq(validate_and_bind_funding(z).bound_equity_budget.amount,Decimal('0'))
check('ECASE01','EDGE',edge_zero_equity)
def edge_decimal():
    z=base(); c=z['c7_funding_context']['contexts'][2]; c['bucket_new_investment_amount']=100.00;c['brokerage_cash_state']['available']=100.00;c['executable_budget']['equity']['amount']=60.00;c['executable_budget']['bond']['amount']=40.00; eq(validate_and_bind_funding(z).bound_equity_budget.amount,Decimal('60.00'))
check('ECASE02','EDGE',edge_decimal)
check('ECASE03','EDGE',lambda: eq(calculate_position_gap(project_target_position_amount=0,target_rate=0,confirmed_position_qty=0,canonical_valuation_price=10).positive_deployment_gap,Decimal('0')))
check('ECASE04','EDGE',lambda: eq(calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=5,canonical_valuation_price=10).positive_deployment_gap,Decimal('0')))
def e5():
    g=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[]); eq(g.active_buy_exposure_amount,Decimal('0'))
check('ECASE05','EDGE',e5)
def e6():
    raises(lambda:calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure('s','SELL',OrderLifecycleState.OPEN,Decimal('2'),Decimal('0'))]),'RECONCILIATION_REQUIRED')
check('ECASE06','EDGE',e6)
def e7():
    b=validate_and_bind_funding(base()).bound_equity_budget; g=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10); p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); eq(build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=100,normalized_order_price=10,execution_currency='USD',order_intent_id='e7').action,'NO_NEW_BUY')
check('ECASE07','EDGE',e7)
def e8():
    b=validate_and_bind_funding(base()).bound_equity_budget; g=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10); p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); eq(build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=1,normalized_order_price=10,execution_currency='TWD',order_intent_id='e8').action,'BLOCKED_UNKNOWN')
check('ECASE08','EDGE',e8)
check('ECASE09','EDGE',lambda: eq(select_deployment_mode(runaway_up=PredicateTruth.UNKNOWN,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.FALSE),NormalDeploymentMode.UNKNOWN))
check('ECASE10','EDGE',lambda: eq(arbitrate_primary_special_classification({'TRUE_RISK_REDUCTION':PredicateTruth.FALSE,'RUNAWAY_DOWN':PredicateTruth.FALSE,'TECHNICAL_REDUCTION':PredicateTruth.FALSE,'RUNAWAY_UP':PredicateTruth.FALSE,'RIGHT_ADD':PredicateTruth.FALSE,'LEFT_BUY_POINT':PredicateTruth.FALSE}),'無特殊分類'))
def e11():
    r=InMemorySnapshotRepository(); a=r.append(snapshot_id='a',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='same',domain='US_BROKER',broker='ib',account='C'); b=r.append(snapshot_id='a2',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='same',domain='US_BROKER',broker='ib',account='C'); eq(a.snapshot_id,b.snapshot_id)
check('ECASE11','EDGE',e11)
def e12():
    r=InMemorySnapshotRepository(); r.append(snapshot_id='a',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='same',domain='US_BROKER',broker='ib',account='C'); raises(lambda:r.append(snapshot_id='b',kind='K',run_id='R',payload={'x':2},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='same',domain='US_BROKER',broker='ib',account='C'),'IDEMPOTENCY_PAYLOAD_CONFLICT')
check('ECASE12','EDGE',e12)
def e13():
    r=InMemorySnapshotRepository(); r.append(snapshot_id='a',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='a',domain='US_BROKER',broker='ib',account='C'); r.publish('a'); r.compare_and_swap_latest(stream_key='US_BROKER|ib|C',new_snapshot_id='a',expected_snapshot_id=None); raises(lambda:r.compare_and_swap_latest(stream_key='US_BROKER|ib|C',new_snapshot_id='a',expected_snapshot_id=None),'CAS_CONFLICT')
check('ECASE13','EDGE',e13)
def e14():
    a=analysis49(); v=project_formal_execution_view(a); eq(len(v.fields),13)
check('ECASE14','EDGE',e14)
def e15():
    raises(lambda:validate_run_lineage(run_id='R1',upstream_v70_run_id='R1',c7_funding_run_id='R2'),'RUN_ID_MISMATCH')
check('ECASE15','EDGE',e15)

# 9 determinism dimensions: funding, gap, permission, classification, deployment mode, execution, 49, 13, digest.
def det(i, fn): check(i,'DETERMINISM',lambda: eq(fn(),fn()))
det('D01',lambda: validate_and_bind_funding(base()).bound_equity_budget)
det('D02',lambda: calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=2,canonical_valuation_price=100))
det('D03',lambda: arbitrate_permission(safety_sufficiency=SufficiencyResult(True,DataQuality.OK,(),()),hard_gate_predicates=[PredicateTruth.FALSE],runaway_down=PredicateTruth.FALSE,structural=StructuralRiskResult(StructuralBreakState.RESOLVED,CompanyRiskGrade.NONE,Decimal('100'),0,())))
det('D04',lambda: arbitrate_primary_special_classification({'TRUE_RISK_REDUCTION':PredicateTruth.FALSE,'RUNAWAY_DOWN':PredicateTruth.FALSE,'TECHNICAL_REDUCTION':PredicateTruth.FALSE,'RUNAWAY_UP':PredicateTruth.FALSE,'RIGHT_ADD':PredicateTruth.TRUE,'LEFT_BUY_POINT':PredicateTruth.TRUE}))
det('D05',lambda: select_deployment_mode(runaway_up=PredicateTruth.FALSE,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.TRUE))
def exec_tuple():
    b=validate_and_bind_funding(base()).bound_equity_budget; g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=0,canonical_valuation_price=100); p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); x=build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=1,normalized_order_price=10,execution_currency='USD',order_intent_id='d'); return (x.action,x.execution_amount,x.execution_quantity,x.execution_price,x.residual_gap_amount)
det('D06',exec_tuple)
det('D07',lambda: tuple((k,v.value) for k,v in analysis49().fields.items()))
det('D08',lambda: tuple(project_formal_execution_view(analysis49()).fields.items()))
det('D09',lambda: content_digest({'a':1,'b':[2,3],'d':Decimal('4.50')}))

out={'gate':'W11 Negative + Contract + Regression + Integration Tests','passed':sum(p for _,_,p,_ in T),'total':len(T),'status':'PASS' if all(p for _,_,p,_ in T) else 'FAIL','category_counts':{},'tests':[{'id':i,'category':c,'pass':p,'detail':d} for i,c,p,d in T]}
for _,c,p,_ in T:
    x=out['category_counts'].setdefault(c,{'passed':0,'total':0}); x['total']+=1; x['passed']+=int(p)
qa=ROOT.parent/'QA_Results'; qa.mkdir(exist_ok=True)
(qa/'A78_W11_NEGATIVE_CONTRACT_REGRESSION_INTEGRATION_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
(qa/'A78_W11_NEGATIVE_CONTRACT_REGRESSION_INTEGRATION_GATE.txt').write_text(f"{out['status']} {out['passed']}/{out['total']}\n"+'\n'.join(f'{k}: {v["passed"]}/{v["total"]}' for k,v in out['category_counts'].items())+'\n'+'\n'.join(f'{i}: {"PASS" if p else "FAIL"} {d}' for i,c,p,d in T),encoding='utf-8')
print(json.dumps({'passed':out['passed'],'total':out['total'],'status':out['status'],'categories':out['category_counts']},ensure_ascii=False))
if out['status']!='PASS':
    for i,c,p,d in T:
        if not p: print('FAIL',i,c,d)
    raise SystemExit(1)
