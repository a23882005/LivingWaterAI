"""Canonical V82 enums materialized from W2/W3 blueprints.

No business calculation or funding validation is implemented here. W6+ owns
validation/rule execution. Values intentionally preserve the canonical strings.
"""
from enum import Enum

class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

class FundingDomain(StrEnum):
    TW_LOCAL_BROKER = "TW_LOCAL_BROKER"
    TW_SUB_BROKERAGE = "TW_SUB_BROKERAGE"
    US_BROKER = "US_BROKER"

class CashBasis(StrEnum):
    AVAILABLE = "AVAILABLE"

class BankCashScope(StrEnum):
    OUT_OF_SCOPE = "OUT_OF_SCOPE"

class AssetType(StrEnum):
    INDIVIDUAL_STOCK = "INDIVIDUAL_STOCK"
    BROAD_ETF = "BROAD_ETF"
    SECTOR_ETF = "SECTOR_ETF"
    INDUSTRY_ETF = "INDUSTRY_ETF"
    THEME_ETF = "THEME_ETF"
    HIGH_VOLATILITY_ETF = "HIGH_VOLATILITY_ETF"
    OTHER_APPROVED_EQUITY_VEHICLE = "OTHER_APPROVED_EQUITY_VEHICLE"

class AssetGrade(StrEnum):
    A = "A"; B = "B"; C = "C"; D = "D"

class PortfolioRole(StrEnum):
    CORE = "CORE"; SATELLITE = "SATELLITE"; UNKNOWN = "UNKNOWN"

class AssetClassificationStatus(StrEnum):
    COMPLETE = "COMPLETE"; UNKNOWN = "UNKNOWN"; INVALID_COMBINATION = "INVALID_COMBINATION"

class DataQuality(StrEnum):
    OK = "OK"; FALLBACK_USED = "FALLBACK_USED"; INSUFFICIENT = "INSUFFICIENT"; UNKNOWN = "UNKNOWN"

class DataIssueCode(StrEnum):
    MISSING = "MISSING"; STALE = "STALE"; CONFLICT = "CONFLICT"; UNVERIFIABLE = "UNVERIFIABLE"
    LOW_CREDIBILITY = "LOW_CREDIBILITY"; DATE_UNKNOWN = "DATE_UNKNOWN"; FREQUENCY_MISMATCH = "FREQUENCY_MISMATCH"
    FIELD_INCOMPLETE = "FIELD_INCOMPLETE"; INVALID_VALUE = "INVALID_VALUE"; METHODOLOGY_UNAVAILABLE = "METHODOLOGY_UNAVAILABLE"
    METHODOLOGY_MISMATCH = "METHODOLOGY_MISMATCH"; PARTIAL_COVERAGE = "PARTIAL_COVERAGE"; SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

class NormalDeploymentMode(StrEnum):
    BASE_DEPLOYMENT = "Base Deployment"
    LEFT_OVERWEIGHT = "Left Overweight"
    RIGHT_CONFIRMATION = "Right Confirmation"
    TREND_DEPLOYMENT = "Trend Deployment"
    UNKNOWN = "UNKNOWN"

CANONICAL_DEPLOYMENT_TARGET_RATE_PCT = (10, 20, 30, 45, 60, 75, 85, 95, 100)

class PrimarySpecialClassification(StrEnum):
    LEFT_BUY_POINT = "左側買點"
    RIGHT_ADD = "右側加碼"
    RUNAWAY_UP = "Runaway Up"
    RUNAWAY_DOWN = "Runaway Down"
    TECHNICAL_REDUCTION = "技術減碼"
    TRUE_RISK_REDUCTION = "真正降低風險"

PRIMARY_SPECIAL_KNOWN_NONE_DISPLAY = "無特殊分類"
PRIMARY_SPECIAL_UNKNOWN = "UNKNOWN"

class FieldSentinelSemantics(StrEnum):
    UNKNOWN = "UNKNOWN"; NOT_APPLICABLE = "NOT_APPLICABLE"; NONE = "NONE"

class FieldValueState(StrEnum):
    KNOWN = "KNOWN"; NONE = "NONE"; UNKNOWN = "UNKNOWN"; NOT_APPLICABLE = "NOT_APPLICABLE"

class OrderLifecycleState(StrEnum):
    SUBMITTED = "SUBMITTED"; OPEN = "OPEN"; PARTIAL_FILL = "PARTIAL_FILL"
    CANCEL_PENDING = "CANCEL_PENDING"; REPLACE_PENDING = "REPLACE_PENDING"
    FILLED = "FILLED"; CANCELLED = "CANCELLED"; REPLACED = "REPLACED"
    REJECTED = "REJECTED"; EXPIRED = "EXPIRED"

ACTIVE_ORDER_STATES = frozenset({OrderLifecycleState.SUBMITTED, OrderLifecycleState.OPEN, OrderLifecycleState.PARTIAL_FILL, OrderLifecycleState.CANCEL_PENDING, OrderLifecycleState.REPLACE_PENDING})
TERMINAL_ORDER_STATES = frozenset({OrderLifecycleState.FILLED, OrderLifecycleState.CANCELLED, OrderLifecycleState.REPLACED, OrderLifecycleState.REJECTED, OrderLifecycleState.EXPIRED})


# W7 core-rule enums. Values mirror the formal V82 SOT; no W8 deployment math.
class RequirementLevel(StrEnum):
    SAFETY_REQUIRED = "SAFETY_REQUIRED"; MODULE_REQUIRED = "MODULE_REQUIRED"; OPTIONAL = "OPTIONAL"; INAPPLICABLE = "INAPPLICABLE"
class PredicateTruth(StrEnum):
    TRUE = "TRUE"; FALSE = "FALSE"; UNKNOWN = "UNKNOWN"
class Freshness(StrEnum):
    FRESH = "FRESH"; STALE = "STALE"; UNKNOWN = "UNKNOWN"; NOT_APPLICABLE = "NOT_APPLICABLE"
class PitStatus(StrEnum):
    VERIFIED = "VERIFIED"; UNVERIFIABLE = "UNVERIFIABLE"; NOT_APPLICABLE = "NOT_APPLICABLE"
class CompletionState(StrEnum):
    COMPLETE = "COMPLETE"; INCOMPLETE = "INCOMPLETE"; UNKNOWN = "UNKNOWN"
class ValuationLevel(StrEnum):
    CHEAP = "CHEAP"; NORMAL = "NORMAL"; PRICEY = "PRICEY"; EXPENSIVE = "EXPENSIVE"; EXTREME_CANDIDATE = "EXTREME_CANDIDATE"; UNKNOWN = "UNKNOWN"
class ExtremeValuationFlag(StrEnum):
    ON = "ON"; OFF = "OFF"; UNKNOWN = "UNKNOWN"
class ContextStatus(StrEnum):
    POSITIVE = "POSITIVE"; NEUTRAL = "NEUTRAL"; NEGATIVE = "NEGATIVE"; UNKNOWN = "UNKNOWN"
class HardGateState(StrEnum):
    TRIGGERED = "TRIGGERED"; NOT_TRIGGERED = "NOT_TRIGGERED"; UNKNOWN = "UNKNOWN"
class StructuralBreakState(StrEnum):
    ACTIVE = "ACTIVE"; RESOLVED = "RESOLVED"; PENDING_CONFIRMATION = "PENDING_CONFIRMATION"; UNKNOWN = "UNKNOWN"
class CompanyRiskGrade(StrEnum):
    NONE = "NONE"; R1 = "R1"; R2 = "R2"; R3 = "R3"; UNKNOWN = "UNKNOWN"
class ThesisState(StrEnum):
    NORMAL = "NORMAL"; DETERIORATING = "DETERIORATING"; FAILED = "FAILED"; UNKNOWN = "UNKNOWN"
