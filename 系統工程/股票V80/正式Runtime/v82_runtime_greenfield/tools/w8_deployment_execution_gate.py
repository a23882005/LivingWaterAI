#!/usr/bin/env python3
import json,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from livingwater_v82_runtime.deployment import *
from livingwater_v82_runtime.enums import *
from livingwater_v82_runtime.models import BoundEquityBudgetView
from livingwater_v82_runtime.core_rules import PermissionResult

checks=[]
def ck(i,cond,detail=""):
    checks.append({"id":i,"pass":bool(cond),"detail":detail})
def raises(i,fn,msg):
    try: fn(); ck(i,False,"did not raise")
    except Exception as e: ck(i,msg in str(e),str(e))

# Mode priority / UNKNOWN
ck("MODE_TREND_PRIORITY",select_deployment_mode(runaway_up=PredicateTruth.TRUE,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.TRUE) is NormalDeploymentMode.TREND_DEPLOYMENT)
ck("MODE_RUNAWAY_UNKNOWN_FAIL_CLOSED",select_deployment_mode(runaway_up=PredicateTruth.UNKNOWN,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.TRUE) is NormalDeploymentMode.UNKNOWN)
ck("MODE_RIGHT",select_deployment_mode(runaway_up=PredicateTruth.FALSE,right_add=PredicateTruth.TRUE,left_buy_point=PredicateTruth.TRUE) is NormalDeploymentMode.RIGHT_CONFIRMATION)
ck("MODE_RIGHT_UNKNOWN",select_deployment_mode(runaway_up=PredicateTruth.FALSE,right_add=PredicateTruth.UNKNOWN,left_buy_point=PredicateTruth.TRUE) is NormalDeploymentMode.UNKNOWN)
ck("MODE_LEFT",select_deployment_mode(runaway_up=PredicateTruth.FALSE,right_add=PredicateTruth.FALSE,left_buy_point=PredicateTruth.TRUE) is NormalDeploymentMode.LEFT_OVERWEIGHT)
ck("MODE_BASE",select_deployment_mode(runaway_up=PredicateTruth.FALSE,right_add=PredicateTruth.FALSE,left_buy_point=PredicateTruth.FALSE) is NormalDeploymentMode.BASE_DEPLOYMENT)

# Stage orthogonality
ck("BASE_STAGE1",resolve_deployment_stage(mode=NormalDeploymentMode.BASE_DEPLOYMENT).stage=="STAGE_1")
ck("RIGHT_STAGE8",resolve_deployment_stage(mode=NormalDeploymentMode.RIGHT_CONFIRMATION).stage=="STAGE_8")
ck("LEFT_STAGE2",resolve_deployment_stage(mode=NormalDeploymentMode.LEFT_OVERWEIGHT,left_stage="STAGE_2").target_rate==Decimal(".20"))
ck("LEFT_STAGE7",resolve_deployment_stage(mode=NormalDeploymentMode.LEFT_OVERWEIGHT,left_stage="STAGE_7").target_rate==Decimal(".85"))
ck("LEFT_STAGE_REQUIRED",resolve_deployment_stage(mode=NormalDeploymentMode.LEFT_OVERWEIGHT).stage==UNKNOWN)
ck("LEFT_NO_STAGE8",resolve_deployment_stage(mode=NormalDeploymentMode.LEFT_OVERWEIGHT,left_stage="STAGE_8").stage==UNKNOWN)
ck("TREND_EXPLICIT_STAGE",resolve_deployment_stage(mode=NormalDeploymentMode.TREND_DEPLOYMENT,trend_stage="STAGE_9").target_rate==Decimal("1"))
ck("TREND_NOT_FORCED_STAGE9",resolve_deployment_stage(mode=NormalDeploymentMode.TREND_DEPLOYMENT).stage==UNKNOWN)
ck("UNKNOWN_STAGE",resolve_deployment_stage(mode=NormalDeploymentMode.UNKNOWN).stage==UNKNOWN)

# Gap/exposure
orders=[
 ActiveOrderExposure("b1","BUY",OrderLifecycleState.OPEN,Decimal("10"),Decimal("2")),
 ActiveOrderExposure("s1","SELL",OrderLifecycleState.CANCEL_PENDING,Decimal("3"),Decimal("1")),
 ActiveOrderExposure("done","BUY",OrderLifecycleState.CANCELLED,Decimal("99"),Decimal("0")),
]
g=calculate_position_gap(project_target_position_amount=10000,target_rate=Decimal(".60"),confirmed_position_qty=40,canonical_valuation_price=100,active_orders=orders)
ck("TARGET_AMOUNT",g.target_amount==Decimal("6000"))
ck("CONFIRMED_AMOUNT",g.confirmed_amount==Decimal("4000"))
ck("ACTIVE_BUY_REMAINING",g.active_buy_exposure_amount==Decimal("800"))
ck("CANCEL_PENDING_STILL_ACTIVE",g.active_sell_exposure_amount==Decimal("200"))
ck("PROJECTED_POSITION",g.projected_position_amount==Decimal("4600"))
ck("FINAL_GAP",g.final_deployment_gap_amount==Decimal("1400"))
ck("ACTUAL_COMPLETION",g.actual_completion_rate==Decimal(".4"))
ck("PROJECTED_COMPLETION",g.projected_completion_rate==Decimal(".46"))
raises("DUP_ORDER_ID",lambda:calculate_position_gap(project_target_position_amount=100,target_rate=.1,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[orders[0],orders[0]]),"DUPLICATE")
raises("FILLED_GT_QTY",lambda:calculate_position_gap(project_target_position_amount=100,target_rate=.1,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure("x","BUY",OrderLifecycleState.OPEN,Decimal("1"),Decimal("2"))]),"ORDER_STATE_CONFLICT")
raises("NEG_PROJECTED",lambda:calculate_position_gap(project_target_position_amount=100,target_rate=.1,confirmed_position_qty=0,canonical_valuation_price=10,active_orders=[ActiveOrderExposure("x","SELL",OrderLifecycleState.OPEN,Decimal("2"),Decimal("0"))]),"RECONCILIATION_REQUIRED")
g0=calculate_position_gap(project_target_position_amount=0,target_rate=.1,confirmed_position_qty=0,canonical_valuation_price=10)
ck("ZERO_DENOM_UNKNOWN_COMPLETION",g0.actual_completion_rate is None and g0.projected_completion_rate is None)
raises("TARGET_RATE_GT_100_FAIL_CLOSED",lambda:calculate_position_gap(project_target_position_amount=100,target_rate=Decimal("1.01"),confirmed_position_qty=0,canonical_valuation_price=10),"INVALID_REQUIRED_DEPLOYMENT_INPUT")

budget=BoundEquityBudgetView(FundingDomain.US_BROKER,"IB","A1",Decimal("1000"),"USD",CashBasis.AVAILABLE,"C7",("r1",))
perm=PermissionResult(HardGateState.NOT_TRIGGERED,True,())
plan=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=101,minimum_lot=1,required_known_caps=[900],normalized_order_price=100,order_intent_id="oi1",execution_currency="USD")
ck("BUY_ACTION",plan.action=="BUY")
ck("CAP_MIN",plan.maximum_allowed_buy_amount==Decimal("900"))
ck("QTY_FLOOR",plan.execution_quantity==Decimal("9"))
ck("NOTIONAL",plan.execution_amount==Decimal("900"))
ck("NO_OVERRUN",plan.execution_amount<=plan.maximum_allowed_buy_amount)
ck("ORDER_PLAN_CONSISTENCY",plan.order_plan.quantity==plan.execution_quantity and plan.order_plan.limit_price==plan.execution_price)
ck("POST_FILL_COMPLETION",plan.projected_post_fill_completion_rate==Decimal(".55"))
blocked=build_buy_execution_plan(gap=g,permission=PermissionResult(HardGateState.TRIGGERED,False,("HARD_GATE_TRIGGERED",)),bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=100,order_intent_id="x",execution_currency="USD")
ck("PERMISSION_BLOCK",blocked.action=="NO_NEW_BUY" and blocked.execution_amount==0 and blocked.order_plan.should_place_order is False)
t1=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=100,order_intent_id="x",execution_currency="USD",t_plus_1_recheck_required=True,t_plus_1_recheck_passed=False)
ck("T1_BLOCK",t1.action=="NO_NEW_BUY" and "T_PLUS_1_RECHECK_REQUIRED" in t1.reason_codes)
recon=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=100,order_intent_id="x",execution_currency="USD",reconciliation_required=True)
ck("RECON_BLOCK",recon.action=="NO_NEW_BUY")
unknowncap=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,required_known_caps=[None],normalized_order_price=100,order_intent_id="x",execution_currency="USD")
ck("CAP_UNKNOWN_FAIL_CLOSED",unknowncap.action=="BLOCKED_UNKNOWN" and unknowncap.execution_amount is None)
badprice=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=None,order_intent_id="x",execution_currency="USD")
ck("TICK_ADAPTER_REQUIRED",badprice.action=="BLOCKED_UNKNOWN")
noid=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=100,order_intent_id=None,execution_currency="USD")
ck("INTENT_ID_REQUIRED",noid.action=="BLOCKED_UNKNOWN")
small=calculate_position_gap(project_target_position_amount=100,target_rate=.1,confirmed_position_qty=0,canonical_valuation_price=1)
res=build_buy_execution_plan(gap=small,permission=perm,bound_equity_budget=budget,order_working_price=11,minimum_lot=1,normalized_order_price=11,order_intent_id="x",execution_currency="USD")
ck("RESIDUAL_NOT_ZEROED",res.action=="NO_NEW_BUY" and res.residual_gap_amount==Decimal("10"))


curr=build_buy_execution_plan(gap=g,permission=perm,bound_equity_budget=budget,order_working_price=100,minimum_lot=1,normalized_order_price=100,order_intent_id="x",execution_currency="TWD")
ck("CURRENCY_MISMATCH_FAIL_CLOSED",curr.action=="BLOCKED_UNKNOWN")

# lifecycle
ck("LIFE_START",validate_order_transition(None,OrderLifecycleState.SUBMITTED))
ck("LIFE_OPEN",validate_order_transition(OrderLifecycleState.SUBMITTED,OrderLifecycleState.OPEN))
ck("LIFE_PARTIAL",validate_order_transition(OrderLifecycleState.OPEN,OrderLifecycleState.PARTIAL_FILL))
ck("LIFE_CANCEL_PENDING_FILL",validate_order_transition(OrderLifecycleState.CANCEL_PENDING,OrderLifecycleState.FILLED))
ck("LIFE_REPLACE",validate_order_transition(OrderLifecycleState.REPLACE_PENDING,OrderLifecycleState.REPLACED))
ck("LIFE_TERMINAL_NO_BACK",not validate_order_transition(OrderLifecycleState.FILLED,OrderLifecycleState.OPEN))
ck("LIFE_NO_SKIP_START",not validate_order_transition(None,OrderLifecycleState.OPEN))

passed=sum(x["pass"] for x in checks); out={"gate":"A78_W08_DEPLOYMENT_EXECUTION_GATE","passed":passed,"total":len(checks),"status":"PASS" if passed==len(checks) else "FAIL","checks":checks}
q=ROOT.parent/"QA_Results"; q.mkdir(exist_ok=True); (q/"A78_W08_DEPLOYMENT_EXECUTION_GATE.json").write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(out,indent=2,ensure_ascii=False)); raise SystemExit(0 if out["status"]=="PASS" else 1)
