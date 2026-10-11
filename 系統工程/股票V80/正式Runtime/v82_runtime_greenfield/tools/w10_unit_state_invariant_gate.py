#!/usr/bin/env python3
from __future__ import annotations
import copy, json, sys, tempfile
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from livingwater_v82_runtime.validation import validate_and_bind_funding, V82InputValidationError
from livingwater_v82_runtime.enums import *
from livingwater_v82_runtime.core_rules import *
from livingwater_v82_runtime.deployment import *
from livingwater_v82_runtime.canonical_output import *
from livingwater_v82_runtime.persistence import *
from livingwater_v82_runtime.ports import require_same_account
from livingwater_v82_runtime.models import ExecutionAccountRef

def base():
    ids=[('TW_LOCAL_BROKER','tw','A'),('TW_SUB_BROKERAGE','sub','B'),('US_BROKER','ib','C')]; ctx=[]
    for d,b,a in ids:
        ctx.append({'domain':d,'broker':b,'account':a,'bucket_new_investment_amount':100,'brokerage_cash_state':{'total':150,'available':100,'unsettled':20,'reserved':10},'executable_budget':{'equity':{'amount':60,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a},'bond':{'amount':40,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a}},'source_reference_ids':[d+'-ref']})
    return {'contract_name':'LivingWaterAI.V82.RuntimeInput','contract_version':'V82-INPUT-v1.0.1-W2-RECHECK2','run_id':'R1','client_project_version':'P1','asset':{'asset_id':'QQQ','asset_type':'BROAD_ETF','asset_grade':'A','portfolio_role':'CORE'},'execution_account':{'domain':'US_BROKER','broker':'ib','account':'C'},'client_target':{'project_target_position':100,'authorization_reference':'AUTH1'},'upstream_v70_snapshot':{'run_id':'R1','upstream_v70_snapshot_id':'V70-1','v70_stock_tactical_budget_amount':100,'v70_stock_tactical_budget_currency':'USD','v70_stock_tactical_budget_status':'KNOWN','v70_stock_tactical_budget_data_as_of':'2026-09-25','v70_original_dry_powder_amount':100,'v70_original_dry_powder_currency':'USD','v70_budget_source_reference':'v70','v70_budget_data_quality':'OK','v70_budget_issue_codes':[]},'confirmed_position_snapshot':{},'source_lineage':['source'],'c7_funding_context':{'contract_name':'LivingWaterAI.C.Work7.FundingContext','contract_version':'C-W7-FUND-v1.0.0','run_id':'R1','base_currency':'USD','bank_cash_scope':'OUT_OF_SCOPE','total_new_investment_amount':300,'contexts':ctx,'source_reference_ids':['c7']}}

def analysis49():
    vals={k:'KNOWN' for k in CANONICAL_FIELD_NAMES}; vals.update({'execution_amount':Decimal('10'),'execution_quantity':Decimal('1'),'execution_price':Decimal('10'),'project_target_position':Decimal('100'),'confirmed_position':Decimal('20'),'actual_completion_rate':Decimal('.2'),'canonical_deployment_target_rate':Decimal('.3'),'projected_post_fill_completion_rate':Decimal('.3'),'order_submission_plan':{'should_place_order':True,'order_type':'LIMIT','limit_price':Decimal('10'),'quantity':Decimal('1'),'time_in_force':'GTC','scheduling_mode':'MANUAL','broker_or_adapter_constraints':None,'order_intent_id':'x'}})
    return assemble_canonical_analysis(values=vals,run_id='R1',rule_version='V82')

def suff(ok=True):
    return SufficiencyResult(ok,DataQuality.OK if ok else DataQuality.INSUFFICIENT,(),())
def structural(active=False):
    return StructuralRiskResult(StructuralBreakState.ACTIVE if active else StructuralBreakState.RESOLVED,CompanyRiskGrade.R1 if active else CompanyRiskGrade.NONE,Decimal('50') if active else Decimal('100'),1 if active else 0,())

T=[]
def check(i,fn):
    try: fn(); T.append((i,True,''))
    except Exception as e: T.append((i,False,f'{type(e).__name__}: {e}'))
def eq(a,b,msg=''): assert a==b, msg or f'{a!r}!={b!r}'
def raises(fn, contains=None):
    try: fn()
    except Exception as e:
        if contains: assert contains in str(e),str(e)
        return
    raise AssertionError('expected exception')

# U01-U10
check('U01',lambda: eq(validate_and_bind_funding(base()).run_id,'R1'))
check('U02',lambda: eq({x['domain'] for x in base()['c7_funding_context']['contexts']},{d.value for d in FundingDomain}))
check('U03',lambda: eq((validate_and_bind_funding(base()).bound_equity_budget.broker,validate_and_bind_funding(base()).bound_equity_budget.account),('ib','C')))
check('U04',lambda: eq(arbitrate_primary_special_classification({'TRUE_RISK_REDUCTION':PredicateTruth.UNKNOWN,'RUNAWAY_DOWN':PredicateTruth.TRUE}),'UNKNOWN'))
check('U05',lambda: eq(len(analysis49().fields),49))
check('U06',lambda: eq(len(project_formal_execution_view(analysis49()).fields),13))
def u07():
    g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=4,canonical_valuation_price=100,active_orders=[ActiveOrderExposure('o','BUY',OrderLifecycleState.OPEN,Decimal('1'),Decimal('0'))]); eq((g.target_amount,g.confirmed_amount,g.projected_position_amount,g.final_deployment_gap_amount),(Decimal('600.0'),Decimal('400'),Decimal('500'),Decimal('100.0')))
check('U07',u07)
def u08():
    b=validate_and_bind_funding(base()).bound_equity_budget; p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=0,canonical_valuation_price=100); x=build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=4,normalized_order_price=9,execution_currency='USD',order_intent_id='x'); eq(x.execution_quantity,Decimal('4')); eq(x.execution_price,Decimal('9')); assert x.execution_quantity % Decimal('4') == 0 and x.execution_amount <= x.maximum_allowed_buy_amount
check('U08',u08)
def u09():
    b=validate_and_bind_funding(base()).bound_equity_budget; p=PermissionResult(HardGateState.NOT_TRIGGERED,True,()); g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=0,canonical_valuation_price=100); x=build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot='UNKNOWN',normalized_order_price=10,execution_currency='USD',order_intent_id='x'); eq(x.action,'BLOCKED_UNKNOWN')
check('U09',u09)
def u10():
    eq(content_digest({'b':2,'a':1}),content_digest({'a':1,'b':2}))
    r=InMemorySnapshotRepository(); rec=r.append(snapshot_id='u10',kind='K',run_id='R1',payload={'a':1,'b':2},rule_version='v',contract_version='c',source_lineage=('src-A','src-B'),created_at='t',idempotency_key='u10',domain='US_BROKER',broker='ib',account='C'); eq(rec.source_lineage,('src-A','src-B')); eq(rec.digest,content_digest(rec.payload))
check('U10',u10)
# S01-S08
def s01():
    assert validate_order_transition(None,OrderLifecycleState.SUBMITTED); assert validate_order_transition(OrderLifecycleState.SUBMITTED,OrderLifecycleState.OPEN); assert validate_order_transition(OrderLifecycleState.OPEN,OrderLifecycleState.PARTIAL_FILL); assert validate_order_transition(OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.FILLED)
check('S01',s01)
def assert_true(x): assert x
check('S02',lambda: assert_true(validate_order_transition(OrderLifecycleState.SUBMITTED,OrderLifecycleState.FILLED)))
check('S03',lambda: eq(validate_order_transition(OrderLifecycleState.FILLED,OrderLifecycleState.OPEN),False))
def s04(): raises(lambda: calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure('o','BUY',OrderLifecycleState.PARTIAL_FILL,Decimal('1'),Decimal('2'))]),'ORDER_STATE_CONFLICT')
check('S04',s04)
def s05():
    assert validate_order_transition(OrderLifecycleState.OPEN,OrderLifecycleState.CANCEL_PENDING) and OrderLifecycleState.CANCEL_PENDING in ACTIVE_ORDER_STATES
    g=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure('o','BUY',OrderLifecycleState.CANCEL_PENDING,Decimal('2'),Decimal('0'))]); eq(g.active_buy_exposure_amount,Decimal('20'))
check('S05',s05)
def s06():
    assert validate_order_transition(OrderLifecycleState.OPEN,OrderLifecycleState.REPLACE_PENDING); assert validate_order_transition(OrderLifecycleState.REPLACE_PENDING,OrderLifecycleState.REPLACED); assert not validate_order_transition(OrderLifecycleState.REPLACED,OrderLifecycleState.OPEN)
    pending=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure('old','BUY',OrderLifecycleState.REPLACE_PENDING,Decimal('2'),Decimal('0'))]); eq(pending.active_buy_exposure_amount,Decimal('20'))
    replaced=calculate_position_gap(project_target_position_amount=100,target_rate=.5,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure('old','BUY',OrderLifecycleState.REPLACED,Decimal('2'),Decimal('0'))]); eq(replaced.active_buy_exposure_amount,Decimal('0'))
check('S06',s06)
def s07():
    g=calculate_position_gap(project_target_position_amount=100,target_rate=.1,confirmed_position_qty=2,canonical_valuation_price=10); eq(g.positive_deployment_gap,Decimal('0'))
check('S07',s07)
def s08():
    r=arbitrate_permission(safety_sufficiency=suff(),hard_gate_predicates=[PredicateTruth.TRUE],runaway_down=PredicateTruth.FALSE,structural=structural()); assert not r.new_buy_order_permission
check('S08',s08)
# I01-I12
check('I01',lambda: eq(validate_and_bind_funding(base()).bound_equity_budget.amount,Decimal('60')))
def i02():
    z=base(); z['c7_funding_context']['contexts'][0]['executable_budget']['equity']['amount']=61; raises(lambda:validate_and_bind_funding(z),'EXCEEDS_AVAILABLE')
check('I02',i02)
def i03():
    z=base(); z['c7_funding_context']['contexts'][0]['brokerage_cash_state']['available']=150; z['c7_funding_context']['contexts'][0]['executable_budget']['equity']['amount']=61; raises(lambda:validate_and_bind_funding(z),'EXCEEDS_ACCOUNT_BUCKET')
check('I03',i03)
def i04():
    z=base(); z['c7_funding_context']['total_new_investment_amount']=301; raises(lambda:validate_and_bind_funding(z),'BUCKET_TOTAL_MISMATCH')
check('I04',i04)
def i05():
    g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=4,canonical_valuation_price=100,active_orders=[ActiveOrderExposure('o','BUY',OrderLifecycleState.OPEN,Decimal('1'),Decimal('0'))]); eq(g.final_deployment_gap_amount,g.target_amount-g.projected_position_amount)
check('I05',i05)
def i06():
    b=validate_and_bind_funding(base()).bound_equity_budget;p=PermissionResult(HardGateState.NOT_TRIGGERED,True,());g=calculate_position_gap(project_target_position_amount=1000,target_rate=.6,confirmed_position_qty=0,canonical_valuation_price=100);x=build_buy_execution_plan(gap=g,permission=p,bound_equity_budget=b,order_working_price=10,minimum_lot=1,normalized_order_price=10,execution_currency='USD',order_intent_id='x'); eq(x.execution_amount,x.execution_quantity*x.execution_price); assert x.execution_amount<=x.maximum_allowed_buy_amount
check('I06',i06)
check('I07',lambda: eq(select_deployment_mode(runaway_up=PredicateTruth.UNKNOWN,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.TRUE),NormalDeploymentMode.UNKNOWN))
def i08():
    p={k:PredicateTruth.FALSE for k,_ in PRIMARY_SPECIAL_PRIORITY}; p['RIGHT_ADD']=PredicateTruth.TRUE;p['LEFT_BUY_POINT']=PredicateTruth.TRUE;eq(arbitrate_primary_special_classification(p),'右側加碼');p['TRUE_RISK_REDUCTION']=PredicateTruth.TRUE;eq(arbitrate_primary_special_classification(p),'真正降低風險')
check('I08',i08)
def i09():
    r=arbitrate_permission(safety_sufficiency=suff(),hard_gate_predicates=[PredicateTruth.TRUE],runaway_down=PredicateTruth.TRUE,structural=structural(True),emergency_status='PENDING_VERIFICATION'); eq(r.reason_codes,('STRUCTURAL_RISK_PREEMPTION','EMERGENCY_PREEMPTION_PENDING_VERIFICATION','HARD_GATE_TRIGGERED','RUNAWAY_DOWN'))
check('I09',i09)
def i10():
    r=InMemorySnapshotRepository(); rec=r.append(snapshot_id='s',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='i',domain='US_BROKER',broker='ib',account='C'); raises(lambda:r.compare_and_swap_latest(stream_key='US_BROKER|ib|C',new_snapshot_id='s',expected_snapshot_id=None),'LATEST_MUST_REFERENCE_PUBLISHED'); r.publish('s'); eq(r.compare_and_swap_latest(stream_key='US_BROKER|ib|C',new_snapshot_id='s',expected_snapshot_id=None).snapshot_id,'s')
check('I10',i10)
def i11():
    r=InMemorySnapshotRepository(); a=r.append(snapshot_id='s1',kind='K',run_id='R',payload={'x':1},rule_version='v',contract_version='c',source_lineage=(),created_at='t',idempotency_key='i1',domain='US_BROKER',broker='ib',account='C'); r.publish('s1'); b=r.append(snapshot_id='s2',kind='K',run_id='R',payload={'x':2},rule_version='v',contract_version='c',source_lineage=(),created_at='t2',idempotency_key='i2',domain='US_BROKER',broker='ib',account='C',supersedes_id='s1'); eq(r.get('s1').payload,{'x':1}); eq(b.supersedes_id,'s1')
check('I11',i11)
def i12():
    bound=validate_and_bind_funding(base()); b=bound.bound_equity_budget
    acct=ExecutionAccountRef(b.domain,b.broker,b.account)
    require_same_account(acct,{'domain':b.domain.value,'broker':b.broker,'account':b.account})
    raises(lambda:require_same_account(acct,{'domain':b.domain.value,'broker':b.broker,'account':'OTHER'}),'ACCOUNT_IDENTITY_MISMATCH')
    r=InMemorySnapshotRepository(); rec=r.append(snapshot_id='s',kind='K',run_id='R1',payload={'account':b.account},rule_version='v',contract_version='c',source_lineage=('R1','QQQ'),created_at='t',idempotency_key='i',domain=b.domain.value,broker=b.broker,account=b.account); eq((rec.domain,rec.broker,rec.account),(b.domain.value,b.broker,b.account)); r.publish('s'); raises(lambda:r.compare_and_swap_latest(stream_key='US_BROKER|ib|OTHER',new_snapshot_id='s',expected_snapshot_id=None),'ACCOUNT_MISMATCH')
    out=build_runtime_output(analysis=analysis49(),run_id='R1',v82_snapshot_id='V82S',upstream_v70_snapshot_id='V70-1',asset_id='QQQ',rule_version='V82',contract_name='LivingWaterAI.V82.RuntimeOutput',contract_version='v1',data_as_of='2026-09-25',evaluated_at='2026-09-25T15:58:00+08:00',source_lineage=('R1','QQQ'),output_status='OK'); eq((out.run_id,out.asset_id,out.source_lineage),('R1','QQQ',('R1','QQQ')))
check('I12',i12)

out={'gate':'W10 Unit + State-transition + Invariant Tests','passed':sum(p for _,p,_ in T),'total':len(T),'status':'PASS' if all(p for _,p,_ in T) else 'FAIL','tests':[{'id':i,'pass':p,'detail':d} for i,p,d in T]}
qa=ROOT.parent/'QA_Results';qa.mkdir(exist_ok=True);(qa/'A78_W10_UNIT_STATE_INVARIANT_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');(qa/'A78_W10_UNIT_STATE_INVARIANT_GATE.txt').write_text(f"{out['status']} {out['passed']}/{out['total']}\n"+'\n'.join(f'{i}: {"PASS" if p else "FAIL"} {d}' for i,p,d in T),encoding='utf-8')
print(json.dumps({'passed':out['passed'],'total':out['total'],'status':out['status']},ensure_ascii=False))
if out['status']!='PASS':
    for i,p,d in T:
        if not p: print('FAIL',i,d)
    raise SystemExit(1)
