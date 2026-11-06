"""W8 deterministic deployment/target/gap/execution planning.

This module consumes W7 state/permission and the W6 bound equity budget. It
implements canonical nine-stage deployment math and order-intent boundaries
without inventing Price-Map→Stage mappings or a second funding engine.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
from functools import wraps
from typing import Any, Mapping, Sequence
from .enums import (ACTIVE_ORDER_STATES, CANONICAL_DEPLOYMENT_TARGET_RATE_PCT,
    NormalDeploymentMode, OrderLifecycleState, PredicateTruth)
from .models import BoundEquityBudgetView, StructuredOrderPlan
from .core_rules import PermissionResult

UNKNOWN="UNKNOWN"
NOT_APPLICABLE="NOT_APPLICABLE"

STAGE_RATE_PCT={f"STAGE_{i+1}": Decimal(str(v)) for i,v in enumerate(CANONICAL_DEPLOYMENT_TARGET_RATE_PCT)}
LEFT_STAGES=frozenset({f"STAGE_{i}" for i in range(2,8)})
EXECUTION_DECIMAL_VERSION='V82_EXECUTION_DECIMAL_1.0.1'


def _execution_precision(fn):
    """Keep source-cap precision before legal lot flooring (CMR9.1).

    A 40-digit proportional cap must not round up to the next lot under a
    caller's default 28-digit context. This changes no cap or target formula.
    """
    @wraps(fn)
    def exact(*args,**kwargs):
        values=[kwargs.get('order_working_price'),kwargs.get('minimum_lot'),kwargs.get('normalized_order_price'),
            kwargs.get('canonical_valuation_price'),kwargs.get('fee_reserve'),
            *kwargs.get('required_known_caps',()),*kwargs.get('required_valuation_caps',()),
            *kwargs.get('required_cash_use_caps',())]
        gap=kwargs.get('gap');budget=kwargs.get('bound_equity_budget')
        plan=kwargs.get('execution_plan')
        if plan is not None:values.extend((plan.execution_quantity,plan.execution_price,plan.execution_amount))
        if gap is not None:values.extend((gap.positive_deployment_gap,gap.project_target_position_amount,gap.projected_position_amount))
        if budget is not None:values.append(budget.amount)
        numbers=[v for v in (_d(x) for x in values) if v is not None]
        digits=max((len(v.as_tuple().digits) for v in numbers),default=28)
        with localcontext() as ctx:
            span=max((v.adjusted() for v in numbers),default=0)-min((v.as_tuple().exponent for v in numbers),default=0)
            ctx.prec=max(80,2*digits+32,span+32);ctx.rounding=ROUND_FLOOR
            return fn(*args,**kwargs)
    return exact

def _d(v: Any) -> Decimal | None:
    if isinstance(v,bool): return None
    try:
        d=Decimal(str(v)); return d if d.is_finite() else None
    except (InvalidOperation,ValueError,TypeError): return None

@dataclass(frozen=True, slots=True)
class ActiveOrderExposure:
    order_intent_id:str
    side:str
    state:OrderLifecycleState
    order_qty:Decimal
    confirmed_filled_qty:Decimal

@dataclass(frozen=True, slots=True)
class DeploymentDecision:
    mode:NormalDeploymentMode
    stage:str
    target_rate:Decimal|None
    reason_codes:tuple[str,...]=()

@dataclass(frozen=True, slots=True)
class PositionGap:
    project_target_position_amount:Decimal
    target_amount:Decimal
    confirmed_amount:Decimal
    active_buy_exposure_amount:Decimal
    active_sell_exposure_amount:Decimal
    projected_position_amount:Decimal
    final_deployment_gap_amount:Decimal
    positive_deployment_gap:Decimal
    actual_completion_rate:Decimal|None
    projected_completion_rate:Decimal|None

@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    action:str
    maximum_allowed_buy_amount:Decimal
    execution_amount:Decimal|None
    execution_quantity:Decimal|None
    execution_price:Decimal|None
    projected_post_fill_completion_rate:Decimal|None
    order_plan:StructuredOrderPlan
    residual_gap_amount:Decimal
    reason_codes:tuple[str,...]

def select_deployment_mode(*, runaway_up:PredicateTruth, right_add:PredicateTruth,
    left_buy_point:PredicateTruth) -> NormalDeploymentMode:
    """Formal W3 priority. UNKNOWN may not be coerced to FALSE."""
    if runaway_up is PredicateTruth.TRUE: return NormalDeploymentMode.TREND_DEPLOYMENT
    if runaway_up is PredicateTruth.UNKNOWN: return NormalDeploymentMode.UNKNOWN
    if right_add is PredicateTruth.TRUE: return NormalDeploymentMode.RIGHT_CONFIRMATION
    if right_add is PredicateTruth.UNKNOWN: return NormalDeploymentMode.UNKNOWN
    if left_buy_point is PredicateTruth.TRUE: return NormalDeploymentMode.LEFT_OVERWEIGHT
    if left_buy_point is PredicateTruth.UNKNOWN: return NormalDeploymentMode.UNKNOWN
    return NormalDeploymentMode.BASE_DEPLOYMENT

def resolve_deployment_stage(*, mode:NormalDeploymentMode, left_stage:str|None=None,
    trend_stage:str|None=None) -> DeploymentDecision:
    """Resolve only SOT-authorized stage references.

    Price Map is intentionally not accepted as an argument: W8 must not create
    a fixed five-layer Price Map→nine-stage mapping. Left STAGE_2..7 and Trend
    stage are explicit already-adjudicated context from the existing V82 SOT.
    """
    if mode is NormalDeploymentMode.UNKNOWN:
        return DeploymentDecision(mode,UNKNOWN,None,("DEPLOYMENT_MODE_UNKNOWN",))
    if mode is NormalDeploymentMode.BASE_DEPLOYMENT:
        stage="STAGE_1"
    elif mode is NormalDeploymentMode.RIGHT_CONFIRMATION:
        stage="STAGE_8"
    elif mode is NormalDeploymentMode.LEFT_OVERWEIGHT:
        if left_stage not in LEFT_STAGES:
            return DeploymentDecision(mode,UNKNOWN,None,("LEFT_STAGE_REQUIRED_OR_INVALID",))
        stage=left_stage
    else:
        # Trend has a maximum of STAGE_9; SOT explicitly says Runaway Up does
        # not mechanically force STAGE_9. Therefore an already-adjudicated
        # canonical trend stage is required.
        if trend_stage not in STAGE_RATE_PCT:
            return DeploymentDecision(mode,UNKNOWN,None,("TREND_STAGE_REQUIRED_OR_INVALID",))
        stage=trend_stage
    return DeploymentDecision(mode,stage,STAGE_RATE_PCT[stage]/Decimal("100"),())

def _active_exposure(orders:Sequence[ActiveOrderExposure], valuation_price:Decimal) -> tuple[Decimal,Decimal]:
    buy=sell=Decimal("0")
    seen=set()
    for o in orders:
        if o.order_intent_id in seen: raise ValueError("DUPLICATE_ORDER_INTENT_ID")
        seen.add(o.order_intent_id)
        if o.state not in ACTIVE_ORDER_STATES: continue
        oq=_d(o.order_qty); fq=_d(o.confirmed_filled_qty)
        if oq is None or fq is None or oq<0 or fq<0 or fq>oq: raise ValueError("ORDER_STATE_CONFLICT")
        remaining=max(oq-fq,Decimal("0"))
        side=o.side.upper()
        if side=="BUY": buy += remaining*valuation_price
        elif side=="SELL": sell += remaining*valuation_price
        else: raise ValueError("INVALID_ORDER_SIDE")
    return buy,sell

def calculate_position_gap(*, project_target_position_amount:Any, target_rate:Any,
    confirmed_position_qty:Any, canonical_valuation_price:Any,
    active_orders:Sequence[ActiveOrderExposure]=()) -> PositionGap:
    target=_d(project_target_position_amount); rate=_d(target_rate)
    qty=_d(confirmed_position_qty); px=_d(canonical_valuation_price)
    if None in (target,rate,qty,px) or target<0 or rate<0 or rate>1 or qty<0 or px<=0:
        raise ValueError("INVALID_REQUIRED_DEPLOYMENT_INPUT")
    confirmed=qty*px
    active_buy,active_sell=_active_exposure(active_orders,px)
    projected=confirmed+active_buy-active_sell
    if projected<0: raise ValueError("INVALID_EXECUTION_STATE_RECONCILIATION_REQUIRED")
    target_amount=target*rate
    gap=target_amount-projected
    actual=(confirmed/target if target>0 else None)
    projected_rate=(projected/target if target>0 else None)
    return PositionGap(target,target_amount,confirmed,active_buy,active_sell,projected,gap,max(gap,Decimal("0")),actual,projected_rate)

@_execution_precision
def build_buy_execution_plan(*, gap:PositionGap, permission:PermissionResult,
    bound_equity_budget:BoundEquityBudgetView, order_working_price:Any,
    minimum_lot:Any, required_known_caps:Sequence[Any]=(),
    canonical_valuation_price:Any=None, fee_reserve:Any=None,
    required_valuation_caps:Sequence[Any]=(), required_cash_use_caps:Sequence[Any]=(),
    order_type:str="LIMIT", time_in_force:str="GTC", scheduling_mode:str="MANUAL",
    broker_or_adapter_constraints:Any=None, order_intent_id:str|None=None,
    normalized_order_price:Any=None, execution_currency:str|None=None, reconciliation_required:bool=False,
    t_plus_1_recheck_required:bool=False, t_plus_1_recheck_passed:bool=False) -> ExecutionPlan:
    """Create a recommendation/order intent boundary, never a broker order.

    Tick normalization belongs to the Execution Adapter. For LIMIT intents W8
    requires normalized_order_price; it never fabricates a legal tick.
    The formal pre-round MIN remains unchanged. Producer-classified valuation
    caps additionally bind quantity*valuation_price; cash-use caps include the
    reliable adapter's fee reserve. A reserve is not a fabricated fee schedule.
    """
    reasons=[]
    if not execution_currency or execution_currency != bound_equity_budget.currency:
        return _blocked_unknown("EXECUTION_CURRENCY_MISSING_OR_MISMATCH")
    budget=_d(bound_equity_budget.amount)
    wp=_d(order_working_price); lot=_d(minimum_lot)
    if budget is None or budget<0: raise ValueError("INVALID_BOUND_EQUITY_BUDGET")
    caps=[]
    for x in required_known_caps:
        d=_d(x)
        if d is None or d<0:
            return _blocked_unknown("REQUIRED_CAP_UNKNOWN_OR_INVALID")
        caps.append(d)
    exposure_caps=[];cash_caps=[budget]
    for values,destination in ((required_valuation_caps,exposure_caps),(required_cash_use_caps,cash_caps)):
        for x in values:
            d=_d(x)
            if d is None or d<0:return _blocked_unknown("REQUIRED_CAP_UNKNOWN_OR_INVALID")
            destination.append(d)
    max_buy=min([gap.positive_deployment_gap,budget,*caps] if caps else [gap.positive_deployment_gap,budget])
    if reconciliation_required: return _known_no_action(max_buy,gap.positive_deployment_gap,("RECONCILIATION_REQUIRED",))
    if t_plus_1_recheck_required and not t_plus_1_recheck_passed:
        return _known_no_action(max_buy,gap.positive_deployment_gap,("T_PLUS_1_RECHECK_REQUIRED",))
    if not permission.new_buy_order_permission:
        return _known_no_action(max_buy,gap.positive_deployment_gap,permission.reason_codes or ("BUY_PERMISSION_FALSE",))
    if gap.final_deployment_gap_amount<=0:
        return _known_no_action(max_buy,Decimal("0"),("NO_POSITIVE_DEPLOYMENT_GAP",))
    if max_buy<=0:
        return _known_no_action(max_buy,gap.positive_deployment_gap,("MAXIMUM_ALLOWED_BUY_AMOUNT_ZERO",))
    if wp is None or wp<=0 or lot is None or lot<=0:
        return _blocked_unknown("ORDER_PRICE_OR_LOT_UNKNOWN_OR_INVALID",max_buy,gap.positive_deployment_gap)
    price=_d(normalized_order_price)
    if order_type.upper()=="LIMIT":
        if price is None or price<=0:
            return _blocked_unknown("NORMALIZED_LIMIT_PRICE_REQUIRED",max_buy,gap.positive_deployment_gap)
    else:
        # Market order has no fabricated fixed execution price.
        return _blocked_unknown("MARKET_PRICE_PLAN_REQUIRES_EXECUTION_ADAPTER",max_buy,gap.positive_deployment_gap)
    valuation=_d(canonical_valuation_price);fee=_d(fee_reserve)
    if valuation is None or valuation<=0:
        return _blocked_unknown("CANONICAL_VALUATION_PRICE_REQUIRED",max_buy,gap.positive_deployment_gap)
    if fee is None or fee<0:
        return _blocked_unknown("EXECUTION_FEE_RESERVE_REQUIRED",max_buy,gap.positive_deployment_gap)
    exposure_limit=min([gap.positive_deployment_gap,*exposure_caps])
    cash_limit=min(cash_caps)
    notional_limit=min(max_buy,max(cash_limit-fee,Decimal(0)))
    raw=min(notional_limit/price,exposure_limit/valuation)
    # Only the adapter-normalized price and legal lot determine final quantity.
    # An earlier working-price floor must not discard a legal normalized lot.
    qty=(raw/lot).to_integral_value(rounding=ROUND_FLOOR)*lot
    if qty<=0:
        return _known_no_action(max_buy,gap.positive_deployment_gap,("POSITIVE_NON_EXECUTABLE_RESIDUAL_GAP",))
    notional=qty*price
    if notional>max_buy: raise AssertionError("BUY_NOTIONAL_EXCEEDS_MAXIMUM")
    exposure=qty*valuation
    if exposure>exposure_limit:raise AssertionError("BUY_VALUATION_EXPOSURE_EXCEEDS_MAXIMUM")
    if notional+fee>cash_limit:raise AssertionError("BUY_CASH_USE_WITH_FEES_EXCEEDS_MAXIMUM")
    if not order_intent_id:
        return _blocked_unknown("ORDER_INTENT_ID_REQUIRED",max_buy,gap.positive_deployment_gap)
    post=gap.projected_position_amount+exposure
    projected_post=(post/gap.project_target_position_amount if gap.project_target_position_amount>0 else None)
    plan=StructuredOrderPlan(True,order_type.upper(),price,qty,time_in_force,scheduling_mode,
        broker_or_adapter_constraints,order_intent_id)
    remaining=gap.positive_deployment_gap-exposure
    residual=remaining if remaining>0 else Decimal("0")
    return ExecutionPlan("BUY",max_buy,notional,qty,price,projected_post,plan,residual,tuple(reasons))

@_execution_precision
def execution_price_basis(*, execution_plan:ExecutionPlan, canonical_valuation_price:Any, fee_reserve:Any) -> Mapping[str,Any]:
    """Exact accounting projections for the existing cash and evidence consumers."""
    qty=execution_plan.execution_quantity;valuation=_d(canonical_valuation_price);fee=_d(fee_reserve)
    return {'canonical_valuation_price':valuation,
        'valuation_increment':qty*valuation if qty is not None and valuation is not None else None,
        'configured_fee_reserve':fee,
        'required_cash_amount':(execution_plan.execution_amount+fee if qty is not None and qty>0 and fee is not None
            else Decimal(0) if qty==0 else None)}

def _known_no_action(max_buy:Decimal,residual:Decimal,reasons:tuple[str,...]) -> ExecutionPlan:
    return ExecutionPlan("NO_NEW_BUY",max_buy,Decimal("0"),Decimal("0"),None,None,
        StructuredOrderPlan(False,None,None,Decimal("0"),None,None,None,None),residual,reasons)

def _blocked_unknown(reason:str,max_buy:Decimal=Decimal("0"),residual:Decimal=Decimal("0")) -> ExecutionPlan:
    return ExecutionPlan("BLOCKED_UNKNOWN",max_buy,None,None,None,None,
        StructuredOrderPlan(UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN),residual,(reason,))

def validate_order_transition(previous:OrderLifecycleState|None, new:OrderLifecycleState) -> bool:
    """W8 lifecycle legality. Recommendation/Intent precede this broker state."""
    if previous is None: return new is OrderLifecycleState.SUBMITTED
    allowed={
        # Broker-confirmed facts may skip locally unobserved intermediate states.
        # This exact minimum relation is frozen by the W3 lifecycle contract.
        OrderLifecycleState.SUBMITTED:{OrderLifecycleState.OPEN,OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.FILLED,OrderLifecycleState.CANCEL_PENDING,OrderLifecycleState.REPLACE_PENDING,OrderLifecycleState.CANCELLED,OrderLifecycleState.REJECTED,OrderLifecycleState.EXPIRED},
        OrderLifecycleState.OPEN:{OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.FILLED,OrderLifecycleState.CANCEL_PENDING,OrderLifecycleState.REPLACE_PENDING,OrderLifecycleState.CANCELLED,OrderLifecycleState.REJECTED,OrderLifecycleState.EXPIRED},
        OrderLifecycleState.PARTIAL_FILL:{OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.FILLED,OrderLifecycleState.CANCEL_PENDING,OrderLifecycleState.REPLACE_PENDING,OrderLifecycleState.CANCELLED,OrderLifecycleState.REJECTED,OrderLifecycleState.EXPIRED},
        OrderLifecycleState.CANCEL_PENDING:{OrderLifecycleState.CANCELLED,OrderLifecycleState.FILLED,OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.REJECTED,OrderLifecycleState.EXPIRED},
        OrderLifecycleState.REPLACE_PENDING:{OrderLifecycleState.REPLACED,OrderLifecycleState.CANCELLED,OrderLifecycleState.FILLED,OrderLifecycleState.PARTIAL_FILL,OrderLifecycleState.REJECTED,OrderLifecycleState.EXPIRED},
    }
    return new in allowed.get(previous,set())
