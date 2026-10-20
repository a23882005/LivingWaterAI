#!/usr/bin/env python3
"""
活水AI理財教練｜V82 股票／股票ETF規則引擎
Engine Version: v0.5.0
Rule Source: V82.md v1.10.0
Whitepaper Source: V82股票操作白皮書.md v1.3.0

定位：
- 本檔只負責可確定、可測試的 V82 規則核心。
- 外部市場資料抓取、LLM 解釋、客戶專案 I/O、Google Drive I/O 分離處理。
- 規則衝突時以 V82.md 為準；同一 V82.md 內若有殘留衝突，以明確標示
  「V82正式累積部署完成率｜母規則固定值」的九階梯為 canonical。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import floor
from typing import Iterable, Optional, Sequence

from v82_models import (
    CUSTOMER_AUTONOMY_NOTICE,
    NO_SPECIAL_CLASSIFICATION_DISPLAY,
    DeploymentMode,
    ExecutionResult,
    NewOrderPermission,
    SpecialClassification,
)
from v82_deployment import (
    DEPLOYMENT_TARGETS,
    SPECIAL_CLASSIFICATION_PRIORITY,
    canonical_deployment_target_rate,
    classify_special_classification,
    deployment_gap_amount,
    deployment_gap_rate,
    deployment_mode_for_classification,
    execution_result_for,
    new_order_permission,
)


ENGINE_VERSION = "v0.5.0"
RULE_VERSION = "v1.10.0"

class V82Error(RuntimeError):
    pass


class GapRecheckStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class DataQuality(str, Enum):
    OK = "OK"
    FALLBACK_USED = "FALLBACK_USED"
    INSUFFICIENT = "INSUFFICIENT"


class ValuationLevel(str, Enum):
    CHEAP = "CHEAP"
    NORMAL = "NORMAL"
    PRICEY = "PRICEY"
    EXPENSIVE = "EXPENSIVE"
    EXTREME_CANDIDATE = "EXTREME_CANDIDATE"


class ContextStatus(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class AssetGrade(str, Enum):
    A = "A"  # 全球／大型核心 ETF
    B = "B"  # 集中型核心／成長 ETF
    C = "C"  # 產業／衛星 ETF
    D = "D"  # 高 Beta／事件型個股


class TrendStatus(str, Enum):
    BULLISH = "BULLISH"
    MIXED = "MIXED"
    BEARISH = "BEARISH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ValuationWaterfallInput:
    own_history_percentile: Optional[float] = None
    index_or_industry_percentile: Optional[float] = None
    relative_valuation_percentile: Optional[float] = None
    peer_percentile: Optional[float] = None
    reverse_yield_percentile: Optional[float] = None

    def available_values(self) -> list[float]:
        vals = [
            self.own_history_percentile,
            self.index_or_industry_percentile,
            self.relative_valuation_percentile,
            self.peer_percentile,
            self.reverse_yield_percentile,
        ]
        return [float(v) for v in vals if v is not None]


@dataclass
class FundamentalInput:
    thesis_intact: bool = True
    earnings_or_cashflow_intact: bool = True
    guidance_intact: bool = True
    industry_structure_intact: bool = True
    governance_intact: bool = True

    @property
    def healthy(self) -> bool:
        return all([
            self.thesis_intact,
            self.earnings_or_cashflow_intact,
            self.guidance_intact,
            self.industry_structure_intact,
            self.governance_intact,
        ])


@dataclass
class MacroVectorInput:
    position_score: Optional[float] = None
    direction_score: Optional[float] = None
    speed_score: Optional[float] = None

    @property
    def summary(self) -> str:
        if None in (self.position_score, self.direction_score, self.speed_score):
            return "資料不足"
        avg=(self.position_score+self.direction_score+self.speed_score)/3
        return "改善" if avg > 0.15 else ("惡化" if avg < -0.15 else "中性")


@dataclass
class ExposureInput:
    project_weight: Optional[float] = None
    max_project_weight: Optional[float] = None
    overlap_weight: Optional[float] = None
    max_overlap_weight: Optional[float] = None

    @property
    def within_limits(self) -> bool:
        checks=[]
        if self.project_weight is not None and self.max_project_weight is not None:
            checks.append(self.project_weight <= self.max_project_weight)
        if self.overlap_weight is not None and self.max_overlap_weight is not None:
            checks.append(self.overlap_weight <= self.max_overlap_weight)
        return bool(checks) and all(checks)


@dataclass
class SnapshotMeta:
    run_id: Optional[str] = None
    analysis_timestamp: Optional[str] = None
    market_data_as_of: Optional[str] = None
    macro_snapshot_timestamp: Optional[str] = None
    snapshot_type: str = "STOCK_VALUATION_SNAPSHOT"


@dataclass
class MacroSafetyInput:
    credit_level: int = 0
    vix: Optional[float] = None
    move: Optional[float] = None
    treasury_liquidity_normal: bool = True
    repo_usd_liquidity_normal: bool = True
    yen_deleveraging_level: int = 0

    def validate(self) -> None:
        if self.credit_level not in {0, 1, 2, 3}:
            raise V82Error("credit_level 必須為 0～3")
        if self.yen_deleveraging_level not in {0, 1, 2, 3}:
            raise V82Error("yen_deleveraging_level 必須為 0～3")

    @property
    def level3_crisis(self) -> bool:
        self.validate()
        return (
            self.credit_level == 3
            or not self.treasury_liquidity_normal
            or not self.repo_usd_liquidity_normal
            or self.yen_deleveraging_level == 3
        )


@dataclass
class MultiTimeframeInput:
    daily: TrendStatus = TrendStatus.UNKNOWN
    weekly: TrendStatus = TrendStatus.UNKNOWN
    monthly: TrendStatus = TrendStatus.UNKNOWN

    def summary(self) -> str:
        return f"D:{self.daily.value}|W:{self.weekly.value}|M:{self.monthly.value}"


@dataclass
class OrderPlan:
    limit_price: Optional[float] = None
    time_in_force: Optional[str] = None
    can_place_order: bool = False
    cancel_conditions: list[str] = field(default_factory=list)
    recalc_conditions: list[str] = field(default_factory=list)


DEFAULT_CANCEL_CONDITIONS = [
    "財測下修／基本面惡化",
    "HY OAS急升／信用惡化",
    "VIX或MOVE異常急升",
    "重要支撐失守／Runaway Down",
    "政策或地緣政治重大利空",
    "估值假設失效",
]

DEFAULT_RECALC_CONDITIONS = [
    "價格進入下一部署層",
    "Swing High／Low或ATR實質改變",
    "估值或基本面假設改變",
    "Macro／信用／流動性重大變化",
    "重大政策／財報／FOMC／CPI／PCE事件後",
]


@dataclass(frozen=True)
class TD9Result:
    high_count: int
    low_count: int


@dataclass(frozen=True)
class SwingPoint:
    index: int
    value: float


@dataclass
class HardGateInput:
    fundamentals_broken: bool = False
    investment_thesis_broken: bool = False
    credit_level3: bool = False
    treasury_repo_usd_liquidity_crisis: bool = False
    yen_deleveraging_level3: bool = False
    uncontrollable_event_gap: bool = False
    budget_or_limit_unverified: bool = False

    @property
    def on(self) -> bool:
        return any(vars(self).values())


@dataclass
class TechnicalSignals:
    # Right confirmation
    higher_low: bool = False
    kd_golden_cross: bool = False
    macd_bear_hist_shrinking_or_positive: bool = False
    dif_up: bool = False
    emv_positive: bool = False
    rsi_improving_or_near_50: bool = False
    above_ma20: bool = False
    volume_breakout: bool = False
    pressure_breakout: bool = False
    breakout_retest_success: bool = False

    # Runaway Up
    new_20d_close_high: bool = False
    break_confirmed_swing_high: bool = False
    higher_high_higher_low: bool = False
    kd_high_strong_not_breaking: bool = False
    macd_bull_hist_expanding: bool = False
    ma5_gt_ma10_gt_ma20: bool = False
    emv_positive_or_improving: bool = False
    price_volume_healthy: bool = False
    high_td9_then_new_high: bool = False
    rsi_high_no_divergence: bool = False
    eps_guidance_not_worse: bool = False

    # Runaway Down
    keeps_breaking_lows: bool = False
    break_confirmed_swing_low: bool = False
    break_support_no_quick_reclaim: bool = False
    macd_bear_hist_expanding: bool = False
    kd_low_weak: bool = False
    emv_worsening: bool = False
    rsi_falling: bool = False
    price_down_volume_up: bool = False
    atr_expanding_fast: bool = False
    decline_accelerating: bool = False
    rebounds_weaker: bool = False

    # Technical reduction
    high_td9_8_9: bool = False
    kd_death_cross: bool = False
    macd_bull_hist_shrinking: bool = False
    emv_weakening: bool = False
    rsi_divergence: bool = False
    huge_volume_no_gain: bool = False
    break_ma10_ma20: bool = False
    failed_breakout: bool = False
    valuation_extreme_and_technical_weak: bool = False


@dataclass
class PriceLayerInput:
    left_price_condition: bool = False
    price_layer: str = "BASE"  # BASE/LEFT_1/LEFT_2/SWEET/LEFT_MATURE/DEEP_SAFE/VERY_DEEP_SAFE


@dataclass
class PositionInput:
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    available_cash: Optional[float] = None
    max_single_order_amount: Optional[float] = None

    def completion_rate(self) -> Optional[float]:
        if self.target_amount is None or self.current_amount is None:
            return None
        if self.target_amount <= 0:
            raise V82Error("target_amount 必須大於 0")
        return max(0.0, self.current_amount / self.target_amount)


@dataclass
class V82Decision:
    rule_version: str
    engine_version: str
    special_classification: Optional[SpecialClassification]
    special_classification_display: str
    deployment_mode: DeploymentMode
    hard_gate: bool
    new_order_permission: NewOrderPermission
    execution_result: ExecutionResult
    customer_autonomy_preserved: bool
    customer_autonomy_notice: str
    runaway_down: bool
    target_completion_rate: Optional[float]
    canonical_deployment_target_rate: float
    deployment_gap_rate: Optional[float]
    deployment_gap_amount: Optional[float]
    recommended_new_amount: Optional[float]
    approximate_shares: Optional[int]
    reason_codes: list[str] = field(default_factory=list)
    run_id: Optional[str] = None
    analysis_timestamp: Optional[str] = None
    market_data_as_of: Optional[str] = None
    macro_snapshot_timestamp: Optional[str] = None
    snapshot_type: str = "STOCK_VALUATION_SNAPSHOT"
    stock_allocation_final: Optional[float] = None
    v82_undeployed_to_sgov: Optional[float] = None
    asset_symbol: Optional[str] = None
    valuation_label: Optional[str] = None
    macro_status: Optional[str] = None
    fundamentals_status: Optional[str] = None
    price_map_layer: Optional[str] = None
    technical_maturity: Optional[int] = None
    timeframe_summary: Optional[str] = None
    order_plan: Optional[OrderPlan] = None
    data_quality: DataQuality = DataQuality.OK
    gap_recheck_status: GapRecheckStatus = GapRecheckStatus.NOT_APPLICABLE
    macro_vector_summary: str = "資料不足"
    valuation_source_count: int = 0
    exposure_within_limits: Optional[bool] = None

    @property
    def recommended_cumulative_rate(self) -> float:
        """Compatibility read alias for the canonical deployment target rate."""
        return self.canonical_deployment_target_rate


def calculate_td9(closes: Sequence[float]) -> TD9Result:
    """V82 第25章：Setup式 1~9；close 與 4 個交易日前比較，條件中斷歸零。"""
    high = low = 0
    for i in range(len(closes)):
        if i < 4:
            continue
        if closes[i] > closes[i - 4]:
            high = min(9, high + 1)
        else:
            high = 0
        if closes[i] < closes[i - 4]:
            low = min(9, low + 1)
        else:
            low = 0
    return TD9Result(high_count=high, low_count=low)


def confirmed_swing_lows(lows: Sequence[float]) -> list[SwingPoint]:
    """V82 第26章：前2日＋後2日確認 Swing Low。"""
    out: list[SwingPoint] = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            out.append(SwingPoint(i, float(lows[i])))
    return out


def confirmed_swing_highs(highs: Sequence[float]) -> list[SwingPoint]:
    """V82 第27章：前2日＋後2日確認 Swing High。"""
    out: list[SwingPoint] = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            out.append(SwingPoint(i, float(highs[i])))
    return out


def valuation_from_percentile(expensiveness_percentile: float) -> ValuationLevel:
    if not 0 <= expensiveness_percentile <= 100:
        raise V82Error("估值百分位必須介於 0～100")
    if expensiveness_percentile < 20:
        return ValuationLevel.CHEAP
    if expensiveness_percentile < 60:
        return ValuationLevel.NORMAL
    if expensiveness_percentile < 80:
        return ValuationLevel.PRICEY
    if expensiveness_percentile < 95:
        return ValuationLevel.EXPENSIVE
    return ValuationLevel.EXTREME_CANDIDATE


def client_valuation_label(expensiveness_percentile: float) -> str:
    if not 0 <= expensiveness_percentile <= 100:
        raise V82Error("估值百分位必須介於 0～100")
    if expensiveness_percentile < 20:
        return "便宜"
    if expensiveness_percentile < 40:
        return "合理偏低"
    if expensiveness_percentile < 60:
        return "合理"
    if expensiveness_percentile < 80:
        return "合理偏貴"
    if expensiveness_percentile < 95:
        return "偏貴"
    return "很貴"


def yield_to_expensiveness_percentile(raw_yield_percentile: float) -> float:
    """V82 32.4：Yield 型方向反轉。"""
    if not 0 <= raw_yield_percentile <= 100:
        raise V82Error("Yield 百分位必須介於 0～100")
    return 100.0 - raw_yield_percentile


def right_confirmation_count(s: TechnicalSignals) -> int:
    return sum([
        s.higher_low, s.kd_golden_cross, s.macd_bear_hist_shrinking_or_positive,
        s.dif_up, s.emv_positive, s.rsi_improving_or_near_50, s.above_ma20,
        s.volume_breakout, s.pressure_breakout, s.breakout_retest_success,
    ])


def runaway_up(s: TechnicalSignals) -> bool:
    a = any([s.new_20d_close_high, s.break_confirmed_swing_high, s.higher_high_higher_low])
    b = sum([
        s.kd_high_strong_not_breaking, s.macd_bull_hist_expanding,
        s.ma5_gt_ma10_gt_ma20, s.emv_positive_or_improving,
        s.price_volume_healthy, s.high_td9_then_new_high,
        s.rsi_high_no_divergence, s.eps_guidance_not_worse,
    ])
    return a and b >= 3


def runaway_down(s: TechnicalSignals) -> bool:
    a = any([s.keeps_breaking_lows, s.break_confirmed_swing_low, s.break_support_no_quick_reclaim])
    b = sum([
        s.macd_bear_hist_expanding, s.kd_low_weak, s.emv_worsening,
        s.rsi_falling, s.price_down_volume_up, s.atr_expanding_fast,
        s.decline_accelerating, s.rebounds_weaker,
    ])
    return a and b >= 2


def technical_reduction(s: TechnicalSignals) -> bool:
    return sum([
        s.high_td9_8_9, s.kd_death_cross, s.macd_bull_hist_shrinking,
        s.emv_weakening, s.rsi_divergence, s.huge_volume_no_gain,
        s.break_ma10_ma20, s.failed_breakout, s.valuation_extreme_and_technical_weak,
    ]) >= 3



def technical_maturity_score(s: TechnicalSignals) -> int:
    """Soft Signal 成熟度：只做節奏輔助，不覆蓋 Hard Gate。"""
    positives = sum([
        s.higher_low, s.kd_golden_cross, s.macd_bear_hist_shrinking_or_positive,
        s.dif_up, s.emv_positive, s.rsi_improving_or_near_50, s.above_ma20,
        s.volume_breakout, s.breakout_retest_success,
    ])
    negatives = sum([
        s.kd_death_cross, s.macd_bear_hist_expanding, s.emv_worsening,
        s.rsi_falling, s.price_down_volume_up, s.atr_expanding_fast,
    ])
    return max(-6, min(9, positives - negatives))


def build_hard_gate(
    base: HardGateInput,
    *,
    macro: Optional[MacroSafetyInput] = None,
) -> HardGateInput:
    if macro is None:
        return base
    macro.validate()
    return HardGateInput(
        fundamentals_broken=base.fundamentals_broken,
        investment_thesis_broken=base.investment_thesis_broken,
        credit_level3=base.credit_level3 or macro.credit_level == 3,
        treasury_repo_usd_liquidity_crisis=(
            base.treasury_repo_usd_liquidity_crisis
            or not macro.treasury_liquidity_normal
            or not macro.repo_usd_liquidity_normal
        ),
        yen_deleveraging_level3=base.yen_deleveraging_level3 or macro.yen_deleveraging_level == 3,
        uncontrollable_event_gap=base.uncontrollable_event_gap,
        budget_or_limit_unverified=base.budget_or_limit_unverified,
    )


def can_place_new_order(*, permission: NewOrderPermission) -> bool:
    return permission == NewOrderPermission.ALLOWED


def build_order_plan(
    *,
    permission: NewOrderPermission,
    limit_price: Optional[float],
    time_in_force: Optional[str] = "GTC",
) -> OrderPlan:
    can_order = can_place_new_order(permission=permission)
    return OrderPlan(
        limit_price=limit_price,
        time_in_force=time_in_force if can_order and limit_price is not None else None,
        can_place_order=can_order and limit_price is not None,
        cancel_conditions=list(DEFAULT_CANCEL_CONDITIONS),
        recalc_conditions=list(DEFAULT_RECALC_CONDITIONS),
    )


def evaluate_t1_gap_recheck(*, major_event: bool, gap_present: bool, next_session_observed: bool,
                            gap_holds: Optional[bool]=None, volume_healthy: Optional[bool]=None,
                            industry_confirms: Optional[bool]=None, broad_market_supports: Optional[bool]=None,
                            quickly_filled: Optional[bool]=None) -> GapRecheckStatus:
    if not major_event or not gap_present:
        return GapRecheckStatus.NOT_APPLICABLE
    if not next_session_observed:
        return GapRecheckStatus.PENDING
    if quickly_filled is True:
        return GapRecheckStatus.FAILED
    checks=[x for x in (gap_holds,volume_healthy,industry_confirms,broad_market_supports) if x is not None]
    return GapRecheckStatus.PASSED if checks and sum(bool(x) for x in checks) >= max(2,len(checks)-1) else GapRecheckStatus.FAILED


def soft_signal_data_quality(*, available_count:int, expected_count:int, fallback_used:bool=False) -> DataQuality:
    if expected_count <= 0 or available_count < 0 or available_count > expected_count:
        raise V82Error("Soft Signal資料數量不合法")
    if available_count == 0:
        return DataQuality.INSUFFICIENT
    return DataQuality.FALLBACK_USED if fallback_used or available_count < expected_count else DataQuality.OK


def soft_signal_order_speed_multiplier(data_quality: DataQuality) -> float:
    return 1.0 if data_quality == DataQuality.OK else (0.5 if data_quality == DataQuality.FALLBACK_USED else 0.25)


def valuation_waterfall_percentile(data: ValuationWaterfallInput) -> Optional[float]:
    """V82估值Waterfall：只用可得正式來源；不足時不捏造。"""
    vals=data.available_values()
    if not vals:
        return None
    for v in vals:
        if not 0 <= v <= 100:
            raise V82Error("估值百分位必須介於0到100")
    # Own history is preferred when available; otherwise use median of available fallbacks.
    if data.own_history_percentile is not None:
        return float(data.own_history_percentile)
    vals=sorted(vals)
    n=len(vals)
    return vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2


def valuation_completeness_gate(data: ValuationWaterfallInput, minimum_sources: int = 1) -> bool:
    return len(data.available_values()) >= minimum_sources


def exposure_hard_gate(exposure: Optional[ExposureInput]) -> bool:
    if exposure is None:
        return False
    return not exposure.within_limits


def calculate_order_amount(
    position: PositionInput,
    cumulative_rate: float,
) -> Optional[float]:
    if position.target_amount is None or position.current_amount is None:
        return None
    desired = max(0.0, position.target_amount * cumulative_rate - position.current_amount)
    if position.available_cash is not None:
        desired = min(desired, max(0.0, position.available_cash))
    if position.max_single_order_amount is not None:
        desired = min(desired, max(0.0, position.max_single_order_amount))
    return round(desired, 2)


def approximate_shares(amount: Optional[float], limit_price: Optional[float]) -> Optional[int]:
    if amount is None or limit_price is None:
        return None
    if limit_price <= 0:
        raise V82Error("limit_price 必須大於 0")
    return max(0, floor(amount / limit_price))


def decide(
    *,
    hard_gate: HardGateInput,
    technical: TechnicalSignals,
    price: PriceLayerInput,
    position: PositionInput,
    fundamentals_ok: bool,
    credit_liquidity_safe: bool,
    valuation_not_extreme: bool = True,
    limit_price: Optional[float] = None,
    meta: Optional[SnapshotMeta] = None,
    macro: Optional[MacroSafetyInput] = None,
    timeframe: Optional[MultiTimeframeInput] = None,
    asset_symbol: Optional[str] = None,
    valuation_percentile: Optional[float] = None,
    stock_allocation_final: Optional[float] = None,
    time_in_force: Optional[str] = "GTC",
    data_quality: DataQuality = DataQuality.OK,
    gap_recheck_status: GapRecheckStatus = GapRecheckStatus.NOT_APPLICABLE,
    valuation_waterfall: Optional[ValuationWaterfallInput] = None,
    fundamental_detail: Optional[FundamentalInput] = None,
    macro_vector: Optional[MacroVectorInput] = None,
    exposure: Optional[ExposureInput] = None,
) -> V82Decision:
    rd = runaway_down(technical)
    ru = runaway_up(technical)
    tr = technical_reduction(technical)
    effective_gate = build_hard_gate(hard_gate, macro=macro)
    if gap_recheck_status == GapRecheckStatus.PENDING:
        effective_gate.uncontrollable_event_gap = True
    if fundamental_detail is not None and not fundamental_detail.healthy:
        effective_gate.fundamentals_broken = True
    if exposure is not None and exposure_hard_gate(exposure):
        effective_gate.lookthrough_unverified = True

    if valuation_waterfall is not None:
        wf = valuation_waterfall_percentile(valuation_waterfall)
        if wf is not None:
            valuation_percentile = wf

    effective_fundamentals_ok = (
        fundamentals_ok
        and not effective_gate.fundamentals_broken
        and not effective_gate.investment_thesis_broken
    )
    effective_credit_liquidity_safe = (
        credit_liquidity_safe
        and not effective_gate.credit_level3
        and not effective_gate.treasury_repo_usd_liquidity_crisis
        and not effective_gate.yen_deleveraging_level3
    )

    # Stage 1 intentionally leaves the later Structural Break / true-risk-reduction
    # trigger for its assigned stage. A Hard Gate is not a proxy classification.
    classification = classify_special_classification(
        true_risk_reduction_now=False,
        runaway_down_now=rd,
        technical_reduction_now=tr,
        runaway_up_now=ru,
        right_confirmation_count=right_confirmation_count(technical),
        left_price_condition=price.left_price_condition,
        fundamentals_ok=effective_fundamentals_ok,
        credit_liquidity_safe=effective_credit_liquidity_safe,
        valuation_not_extreme=valuation_not_extreme,
    )
    mode = deployment_mode_for_classification(classification)
    canonical_rate = canonical_deployment_target_rate(classification, price.price_layer)
    completion_rate = position.completion_rate()
    gap_rate = deployment_gap_rate(canonical_rate, completion_rate)
    gap_amount = deployment_gap_amount(
        target_amount=position.target_amount,
        current_amount=position.current_amount,
        canonical_target_rate=canonical_rate,
    )
    budget_complete = (
        position.target_amount is not None
        and position.current_amount is not None
        and position.available_cash is not None
    )
    permission = new_order_permission(
        hard_gate_on=effective_gate.on,
        runaway_down_now=rd,
        special_classification=classification,
        fundamentals_ok=effective_fundamentals_ok,
        credit_liquidity_safe=effective_credit_liquidity_safe,
        budget_data_complete=budget_complete,
        gap_rate=gap_rate,
    )
    exec_result = execution_result_for(
        permission=permission,
        hard_gate_on=effective_gate.on,
        runaway_down_now=rd,
        special_classification=classification,
        fundamentals_ok=effective_fundamentals_ok,
        credit_liquidity_safe=effective_credit_liquidity_safe,
        budget_data_complete=budget_complete,
        gap_rate=gap_rate,
    )
    candidate_amount = calculate_order_amount(position, canonical_rate)
    amount = candidate_amount if permission == NewOrderPermission.ALLOWED else (0.0 if candidate_amount is not None else None)
    shares = approximate_shares(amount, limit_price)
    maturity = technical_maturity_score(technical)
    order_plan = build_order_plan(
        permission=permission,
        limit_price=limit_price,
        time_in_force=time_in_force,
    )

    reasons: list[str] = [
        (f"SPECIAL_{classification.name}" if classification is not None else "NO_SPECIAL_CLASSIFICATION"),
        f"MODE_{mode.name}",
        f"NEW_ORDER_{permission.name}",
        f"EXECUTION_{exec_result.name}",
    ]
    if effective_gate.on:
        reasons.append("HARD_GATE_ON")
    if rd:
        reasons.append("RUNAWAY_DOWN")
    if price.left_price_condition:
        reasons.append(f"PRICE_LAYER_{price.price_layer}")
    if maturity >= 3:
        reasons.append("TECHNICAL_MATURITY_POSITIVE")
    elif maturity < 0:
        reasons.append("TECHNICAL_MATURITY_NEGATIVE")

    meta = meta or SnapshotMeta()
    valuation_label = (
        client_valuation_label(valuation_percentile)
        if valuation_percentile is not None else None
    )
    undeployed = None
    if stock_allocation_final is not None:
        if not 0 <= stock_allocation_final <= 1:
            raise V82Error("stock_allocation_final 必須介於 0～1")
        undeployed = round(1.0 - stock_allocation_final, 6)

    return V82Decision(
        rule_version=RULE_VERSION,
        engine_version=ENGINE_VERSION,
        special_classification=classification,
        special_classification_display=(classification.value if classification is not None else NO_SPECIAL_CLASSIFICATION_DISPLAY),
        deployment_mode=mode,
        hard_gate=effective_gate.on,
        new_order_permission=permission,
        execution_result=exec_result,
        customer_autonomy_preserved=True,
        customer_autonomy_notice=CUSTOMER_AUTONOMY_NOTICE,
        runaway_down=rd,
        target_completion_rate=completion_rate,
        canonical_deployment_target_rate=canonical_rate,
        deployment_gap_rate=gap_rate,
        deployment_gap_amount=gap_amount,
        recommended_new_amount=amount,
        approximate_shares=shares,
        reason_codes=reasons,
        run_id=meta.run_id,
        analysis_timestamp=meta.analysis_timestamp,
        market_data_as_of=meta.market_data_as_of,
        macro_snapshot_timestamp=meta.macro_snapshot_timestamp,
        snapshot_type=meta.snapshot_type,
        stock_allocation_final=stock_allocation_final,
        v82_undeployed_to_sgov=undeployed,
        asset_symbol=asset_symbol,
        valuation_label=valuation_label,
        macro_status=("LEVEL3_CRISIS" if macro and macro.level3_crisis else "SAFE_OR_NOT_LEVEL3"),
        fundamentals_status=("OK" if fundamentals_ok else "BROKEN_OR_UNVERIFIED"),
        price_map_layer=price.price_layer,
        technical_maturity=maturity,
        timeframe_summary=(timeframe.summary() if timeframe else None),
        order_plan=order_plan,
    )


def validate_rule_constants() -> None:
    expected = [0.10, 0.20, 0.30, 0.45, 0.60, 0.75, 0.85, 0.95, 1.00]
    actual = list(DEPLOYMENT_TARGETS.values())
    if actual != expected:
        raise V82Error(f"V82 正式累積部署比例遭改動：{actual}")
    if list(SPECIAL_CLASSIFICATION_PRIORITY.values()) != [1, 2, 3, 4, 5, 6]:
        raise V82Error("V82 六類特殊分類優先順序遭改動")


validate_rule_constants()
