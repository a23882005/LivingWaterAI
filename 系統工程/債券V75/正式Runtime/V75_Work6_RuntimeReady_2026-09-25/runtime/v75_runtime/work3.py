from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from .constants import PREDICATE_VERSION, RULE_SOT_VERSION
from .enums import BrokerDomainType, EvaluationState, ValueStatus
from .models import Money, MoneyValue, PerAssetDeploymentInput, PercentValue, V75RunInput
from .work3_models import (
    AssetEligibilityAssessment,
    BucketReconciliation,
    GapCalculation,
    LongTermBucketLine,
    SgovRoleReconciliation,
    Work3BucketClass,
    Work3EligibilityState,
    Work3Issue,
    Work3IssueClass,
    Work3State,
)

WORK3_ENGINE_VERSION = "V75_WORK3_ELIGIBILITY_BUCKET_SGOV_v1.0.1"

# Rule SOT v2.7.0 generic long-term core templates.
US_GENERIC_CORE_WEIGHTS = {"SGOV": Decimal("70"), "SPSB": Decimal("30")}
TW_GENERIC_CORE_WEIGHTS = {"00859B": Decimal("80"), "00860B": Decimal("20")}

# Known legacy/special instruments retained by the Rule SOT for existing-position
# management and/or explicitly authorized special cases. They receive no generic
# long-term template weight in Work3.
SUPPORTED_NON_CORE = frozenset({
    "SHY", "IEF", "SPIB", "TLT", "SPLB",
    "00719B", "00679B", "00725B", "00761B", "00937B",
})

# BNDW is explicitly removed from generic new allocation/new-buy targets by v2.7.0.
EXISTING_MANAGEMENT_ONLY = frozenset({"BNDW"})

# The SOT discusses 00985B conditionally based on client credit-quality preference,
# but the frozen V75RunInput does not carry that preference. Work3 therefore cannot
# deterministically resolve it and must preserve UNKNOWN rather than guess.
CONDITIONAL_UNKNOWN = frozenset({"00985B"})

# Listing / execution-domain compatibility. The frozen broker domains distinguish
# Taiwan-local trading from Taiwan sub-brokerage and direct US brokerage.
# US-listed instruments may be held in US_BROKER or TW_SUB_BROKERAGE; Taiwan-listed
# instruments belong to TW_LOCAL_BROKER. Unknown assets are not guessed here.
US_LISTED_ASSETS = frozenset({
    "SGOV", "SPSB", "BNDW", "SHY", "IEF", "SPIB", "TLT", "SPLB",
})
TW_LISTED_ASSETS = frozenset({
    "00859B", "00860B", "00719B", "00679B", "00725B", "00761B", "00937B", "00985B",
})


def _domain_compatible(asset_id: str, broker_domain_type: BrokerDomainType) -> bool | None:
    aid = _aid(asset_id)
    if aid in US_LISTED_ASSETS:
        return broker_domain_type in {BrokerDomainType.US_BROKER, BrokerDomainType.TW_SUB_BROKERAGE}
    if aid in TW_LISTED_ASSETS:
        return broker_domain_type == BrokerDomainType.TW_LOCAL_BROKER
    return None


def _aid(value: str) -> str:
    return value.strip().upper()


def _money(amount: Decimal | str | int, currency: str) -> Money:
    return Money(amount=Decimal(str(amount)), currency=currency)


def _known_money(amount: Decimal | str | int, currency: str) -> MoneyValue:
    return MoneyValue(status=ValueStatus.KNOWN, value=_money(amount, currency))


def _unknown_money() -> MoneyValue:
    return MoneyValue(status=ValueStatus.UNKNOWN, value=None)


def _sum_amounts(values: Iterable[Money], currency: str) -> Money:
    total = Decimal("0")
    for value in values:
        if value.currency != currency:
            raise ValueError("Work3 cannot sum cross-currency Money values")
        total += value.amount
    return _money(total, currency)


def _ordered_union(*sequences: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for seq in sequences:
        for raw in seq:
            item = _aid(raw)
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _has_positive(amount: Money | None) -> bool:
    return amount is not None and amount.amount > 0


def _classify_asset(
    asset_id: str,
    *,
    authorized: bool,
    existing_amount: Decimal,
    broker_domain_type: BrokerDomainType,
) -> AssetEligibilityAssessment:
    aid = _aid(asset_id)
    has_existing = existing_amount > 0

    domain_compatible = _domain_compatible(aid, broker_domain_type)
    if domain_compatible is False:
        if aid in US_GENERIC_CORE_WEIGHTS:
            bucket_class = Work3BucketClass.US_GENERIC_CORE
        elif aid in TW_GENERIC_CORE_WEIGHTS:
            bucket_class = Work3BucketClass.TW_GENERIC_CORE
        elif aid in EXISTING_MANAGEMENT_ONLY:
            bucket_class = Work3BucketClass.EXISTING_ONLY
        elif aid in SUPPORTED_NON_CORE:
            bucket_class = Work3BucketClass.AUTHORIZED_NON_CORE
        else:
            bucket_class = Work3BucketClass.UNKNOWN
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.INELIGIBLE,
            bucket_class=bucket_class,
            new_long_term_target_allowed=False,
            existing_position_management_allowed=False,
            authorized=authorized,
            reason_codes=["BROKER_DOMAIN_INCOMPATIBLE_FOR_ASSET"],
        )

    if aid in US_GENERIC_CORE_WEIGHTS:
        if authorized:
            return AssetEligibilityAssessment(
                asset_id=aid,
                eligibility_state=Work3EligibilityState.ELIGIBLE,
                bucket_class=Work3BucketClass.US_GENERIC_CORE,
                new_long_term_target_allowed=True,
                existing_position_management_allowed=True,
                authorized=True,
                reason_codes=["AUTHORIZED_US_GENERIC_CORE"],
            )
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION,
            bucket_class=Work3BucketClass.US_GENERIC_CORE,
            new_long_term_target_allowed=False,
            existing_position_management_allowed=has_existing,
            authorized=False,
            reason_codes=["NOT_IN_AUTHORIZED_UNIVERSE"] + (["EXISTING_POSITION_STILL_REQUIRES_REVIEW"] if has_existing else []),
        )

    if aid in TW_GENERIC_CORE_WEIGHTS:
        if authorized:
            return AssetEligibilityAssessment(
                asset_id=aid,
                eligibility_state=Work3EligibilityState.ELIGIBLE,
                bucket_class=Work3BucketClass.TW_GENERIC_CORE,
                new_long_term_target_allowed=True,
                existing_position_management_allowed=True,
                authorized=True,
                reason_codes=["AUTHORIZED_TW_GENERIC_CORE"],
            )
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION,
            bucket_class=Work3BucketClass.TW_GENERIC_CORE,
            new_long_term_target_allowed=False,
            existing_position_management_allowed=has_existing,
            authorized=False,
            reason_codes=["NOT_IN_AUTHORIZED_UNIVERSE"] + (["EXISTING_POSITION_STILL_REQUIRES_REVIEW"] if has_existing else []),
        )

    if aid in EXISTING_MANAGEMENT_ONLY:
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION,
            bucket_class=Work3BucketClass.EXISTING_ONLY,
            new_long_term_target_allowed=False,
            existing_position_management_allowed=has_existing,
            authorized=authorized,
            reason_codes=["REMOVED_FROM_GENERIC_NEW_ALLOCATION"] + (["EXISTING_POSITION_MANAGEMENT_ALLOWED"] if has_existing else []),
        )

    if aid in SUPPORTED_NON_CORE:
        if authorized:
            return AssetEligibilityAssessment(
                asset_id=aid,
                eligibility_state=Work3EligibilityState.ELIGIBLE,
                bucket_class=Work3BucketClass.AUTHORIZED_NON_CORE,
                new_long_term_target_allowed=True,
                existing_position_management_allowed=True,
                authorized=True,
                reason_codes=["AUTHORIZED_NON_CORE_NO_GENERIC_TEMPLATE_WEIGHT"],
            )
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION,
            bucket_class=Work3BucketClass.AUTHORIZED_NON_CORE,
            new_long_term_target_allowed=False,
            existing_position_management_allowed=has_existing,
            authorized=False,
            reason_codes=["NON_CORE_NOT_AUTHORIZED"] + (["EXISTING_POSITION_STILL_REQUIRES_REVIEW"] if has_existing else []),
        )

    if aid in CONDITIONAL_UNKNOWN:
        return AssetEligibilityAssessment(
            asset_id=aid,
            eligibility_state=Work3EligibilityState.UNKNOWN,
            bucket_class=Work3BucketClass.UNKNOWN,
            new_long_term_target_allowed=None,
            existing_position_management_allowed=has_existing,
            authorized=authorized,
            reason_codes=["CONDITIONAL_ELIGIBILITY_CONTEXT_NOT_IN_FROZEN_INPUT"],
        )

    return AssetEligibilityAssessment(
        asset_id=aid,
        eligibility_state=Work3EligibilityState.UNKNOWN,
        bucket_class=Work3BucketClass.UNKNOWN,
        new_long_term_target_allowed=None,
        existing_position_management_allowed=has_existing,
        authorized=authorized,
        reason_codes=["ASSET_NOT_DETERMINISTICALLY_CLASSIFIED_BY_WORK3_SOT"],
    )


def _target_ratio_valid(targets: dict[str, Money], weights: dict[str, Decimal]) -> bool | None:
    positive = {aid: targets.get(aid, _money(0, next(iter(targets.values())).currency if targets else "USD")).amount for aid in weights}
    total = sum(positive.values(), Decimal("0"))
    if total == 0:
        return None
    if any(positive[aid] <= 0 for aid in weights):
        return False
    # Exact Decimal cross-multiplication, avoiding floating-point ratios.
    items = list(weights.items())
    base_asset, base_weight = items[0]
    for aid, weight in items[1:]:
        if positive[base_asset] * weight != positive[aid] * base_weight:
            return False
    return True


def _sgov_reconciliation(run: V75RunInput) -> SgovRoleReconciliation:
    bond = run.sgov_bond_bucket_amount
    dry = run.sgov_dry_powder_bucket_amount
    reasons = ["SGOV_BOND_AND_DRY_POWDER_ROLES_SEPARATE", "DRY_POWDER_INPUT_READ_ONLY"]
    if bond.status == ValueStatus.KNOWN and dry.status == ValueStatus.KNOWN:
        assert bond.value is not None and dry.value is not None
        observed = _known_money(bond.value.amount + dry.value.amount, run.currency)
        reasons.append("OBSERVED_ROLE_TOTAL_RECONCILED")
    elif bond.status == ValueStatus.NOT_APPLICABLE and dry.status == ValueStatus.NOT_APPLICABLE:
        observed = MoneyValue(status=ValueStatus.NOT_APPLICABLE, value=None)
        reasons.append("BOTH_SGOV_ROLES_NOT_APPLICABLE")
    else:
        observed = _unknown_money()
        reasons.append("OBSERVED_ROLE_TOTAL_UNKNOWN_WITHOUT_BOTH_KNOWN_VALUES")
    return SgovRoleReconciliation(
        sgov_bond_bucket_amount=bond,
        sgov_dry_powder_bucket_amount=dry,
        observed_role_total_amount=observed,
        reason_codes=reasons,
    )


def build_work3_state(run: V75RunInput) -> Work3State:
    """Execute only Work3 structural eligibility, long-term target accounting and SGOV role reconciliation.

    This function deliberately does not calculate PRED-001..010, execute Global Evaluation
    Precedence, assign deployment states/percentages, compute deploy_amount, scale multi-asset
    demand, classify final actions, or calculate the later-work undeployed contribution.
    """
    currency = run.currency
    issues: list[Work3Issue] = []
    missing_fields: list[str] = []
    reason_codes: list[str] = [WORK3_ENGINE_VERSION, "LIFE_STAGE_CODE_PASSTHROUGH_NO_UNFROZEN_MACHINE_MAPPING"]

    # Authorized Universe is structural eligibility input. Canonical ticker comparison is case-insensitive,
    # but case-colliding duplicates remain invalid because they would create ambiguous live identity.
    raw_authorized = [item.strip() for item in run.authorized_universe]
    if any(not item for item in raw_authorized):
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INVALID_INPUT,
            code="BLANK_AUTHORIZED_UNIVERSE_ASSET_ID",
            message="authorized_universe cannot contain blank asset ids",
            field="authorized_universe",
        ))
    canonical_authorized = [_aid(item) for item in raw_authorized if item]
    if len(canonical_authorized) != len(set(canonical_authorized)):
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INVALID_INPUT,
            code="DUPLICATE_AUTHORIZED_UNIVERSE_ASSET_ID",
            message="authorized_universe cannot contain duplicate/case-colliding asset ids",
            field="authorized_universe",
        ))
    authorized_set = set(canonical_authorized)

    # Targets must be unique per asset in a single account; holdings may contain multiple lots and are summed.
    target_map: dict[str, Money] = {}
    for item in run.target_bond_holdings:
        aid = _aid(item.asset_id)
        if aid in target_map:
            issues.append(Work3Issue(
                issue_class=Work3IssueClass.INVALID_INPUT,
                code="DUPLICATE_TARGET_ASSET_ID",
                message="target_bond_holdings must contain at most one target per asset/account",
                asset_id=aid,
                field="target_bond_holdings",
            ))
        else:
            target_map[aid] = item.target_amount

    existing_by_asset: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in run.existing_bond_holdings:
        existing_by_asset[_aid(item.asset_id)] += item.amount.amount

    raw_sgov_existing = existing_by_asset.get("SGOV", Decimal("0"))
    sgov_bond_known_amount = Decimal("0")
    if run.sgov_bond_bucket_amount.status == ValueStatus.KNOWN:
        assert run.sgov_bond_bucket_amount.value is not None
        sgov_bond_known_amount = run.sgov_bond_bucket_amount.value.amount
    elif run.sgov_bond_bucket_amount.status == ValueStatus.UNKNOWN and raw_sgov_existing > 0:
        # A physical SGOV holding can contain bond-role and dry-powder units. If the bond-role
        # amount is UNKNOWN, Work3 cannot safely decide how much belongs to V75 existing-position
        # management, even when today's long-term target is zero.
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INSUFFICIENT_DATA,
            code="SGOV_BOND_ROLE_UNKNOWN_WITH_EXISTING_HOLDING",
            message="existing SGOV is present but sgov_bond_bucket_amount is UNKNOWN; role separation is required",
            asset_id="SGOV",
            field="sgov_bond_bucket_amount",
        ))
        missing_fields.append("sgov_bond_bucket_amount")

    sgov_role_assets = ["SGOV"] if sgov_bond_known_amount > 0 else []
    all_assets = _ordered_union(canonical_authorized, target_map.keys(), existing_by_asset.keys(), sgov_role_assets)
    assessments: list[AssetEligibilityAssessment] = []
    assessment_by_asset: dict[str, AssetEligibilityAssessment] = {}
    for aid in all_assets:
        effective_existing_amount = (
            sgov_bond_known_amount if aid == "SGOV" else existing_by_asset.get(aid, Decimal("0"))
        )
        assessment = _classify_asset(
            aid,
            authorized=aid in authorized_set,
            existing_amount=effective_existing_amount,
            broker_domain_type=run.broker_domain_type,
        )
        assessments.append(assessment)
        assessment_by_asset[aid] = assessment

        if assessment.eligibility_state == Work3EligibilityState.UNKNOWN and (
            aid in authorized_set
            or (sgov_bond_known_amount if aid == "SGOV" else existing_by_asset.get(aid, Decimal("0"))) > 0
            or _has_positive(target_map.get(aid))
        ):
            issues.append(Work3Issue(
                issue_class=Work3IssueClass.INSUFFICIENT_DATA,
                code="ELIGIBILITY_UNKNOWN",
                message="asset eligibility cannot be deterministically resolved by the frozen Work3/SOT inputs",
                asset_id=aid,
                field="authorized_universe",
            ))
            missing_fields.append(f"eligibility:{aid}")

        effective_existing_for_review = (
            sgov_bond_known_amount if aid == "SGOV" else existing_by_asset.get(aid, Decimal("0"))
        )
        if effective_existing_for_review > 0 and aid not in authorized_set:
            issues.append(Work3Issue(
                issue_class=Work3IssueClass.REVIEW_REQUIRED,
                code="EXISTING_HOLDING_OUTSIDE_AUTHORIZED_UNIVERSE",
                message="existing holding is not present in authorized_universe; existing-risk management must not silently ignore it",
                asset_id=aid,
                field="authorized_universe",
            ))

    # Broker-domain compatibility is a frozen input boundary. Authorized Universe may be global,
    # so a mismatched authorized-only candidate does not block this account run. A positive target
    # or an actual existing position in an incompatible domain is invalid and fails closed.
    for aid in all_assets:
        compatible = _domain_compatible(aid, run.broker_domain_type)
        if compatible is False:
            active_existing = (
                sgov_bond_known_amount if aid == "SGOV" else existing_by_asset.get(aid, Decimal("0"))
            )
            active_target = target_map.get(aid)
            if active_existing > 0 or _has_positive(active_target):
                issues.append(Work3Issue(
                    issue_class=Work3IssueClass.INVALID_INPUT,
                    code="BROKER_DOMAIN_ASSET_MISMATCH",
                    message="asset listing/execution venue is incompatible with broker_domain_type for this account run",
                    asset_id=aid,
                    field="broker_domain_type",
                ))

    # Positive targets require structural new-allocation eligibility and explicit authorization.
    for aid, target in target_map.items():
        if target.amount <= 0:
            continue
        assessment = assessment_by_asset.get(aid)
        if assessment is None:
            continue
        if aid not in authorized_set:
            issues.append(Work3Issue(
                issue_class=Work3IssueClass.INVALID_INPUT,
                code="POSITIVE_TARGET_NOT_AUTHORIZED",
                message="positive long-term target is not permitted outside authorized_universe",
                asset_id=aid,
                field="target_bond_holdings",
            ))
        elif assessment.eligibility_state in {
            Work3EligibilityState.INELIGIBLE_NEW_ALLOCATION,
            Work3EligibilityState.INELIGIBLE,
        }:
            issues.append(Work3Issue(
                issue_class=Work3IssueClass.INVALID_INPUT,
                code="POSITIVE_TARGET_PROHIBITED_BY_SOT",
                message="positive new-allocation target conflicts with the current Rule SOT eligibility boundary",
                asset_id=aid,
                field="target_bond_holdings",
            ))
        elif assessment.eligibility_state == Work3EligibilityState.UNKNOWN:
            # UNKNOWN was already recorded as insufficient; never coerce it to false/safe.
            pass

    us_total = _sum_amounts(
        [target_map[aid] for aid in US_GENERIC_CORE_WEIGHTS if aid in target_map], currency
    )
    tw_total = _sum_amounts(
        [target_map[aid] for aid in TW_GENERIC_CORE_WEIGHTS if aid in target_map], currency
    )
    all_target_total = _sum_amounts(target_map.values(), currency)
    generic_ids = set(US_GENERIC_CORE_WEIGHTS) | set(TW_GENERIC_CORE_WEIGHTS)
    non_core_total = _sum_amounts(
        [amount for aid, amount in target_map.items() if aid not in generic_ids], currency
    )

    us_ratio = _target_ratio_valid(target_map, US_GENERIC_CORE_WEIGHTS)
    tw_ratio = _target_ratio_valid(target_map, TW_GENERIC_CORE_WEIGHTS)
    if us_ratio is False:
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INVALID_INPUT,
            code="US_GENERIC_CORE_TARGET_RATIO_MISMATCH",
            message="positive US generic bond bucket must retain SGOV/SPSB at 70%/30%",
            field="target_bond_holdings",
        ))
    if tw_ratio is False:
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INVALID_INPUT,
            code="TW_GENERIC_CORE_TARGET_RATIO_MISMATCH",
            message="positive Taiwan generic bond bucket must retain 00859B/00860B at 80%/20%",
            field="target_bond_holdings",
        ))

    long_term_lines: list[LongTermBucketLine] = []
    for aid, target in target_map.items():
        assessment = assessment_by_asset.get(aid)
        bucket_class = assessment.bucket_class if assessment else Work3BucketClass.UNKNOWN
        template_weight = None
        if aid in US_GENERIC_CORE_WEIGHTS:
            template_weight = PercentValue(value=US_GENERIC_CORE_WEIGHTS[aid])
        elif aid in TW_GENERIC_CORE_WEIGHTS:
            template_weight = PercentValue(value=TW_GENERIC_CORE_WEIGHTS[aid])
        long_term_lines.append(LongTermBucketLine(
            asset_id=aid,
            bucket_class=bucket_class,
            target_amount=target,
            template_weight_pct=template_weight,
        ))

    # Gap formula: max(target_amount - eligible_existing_amount, 0), same account only.
    # SGOV uses the explicit SGOV_BOND_BUCKET role amount, never dry powder, as eligible existing amount.
    gap_calculations: list[GapCalculation] = []
    per_asset_inputs: list[PerAssetDeploymentInput] = []
    # Raw SGOV holdings may include Dry Powder. SGOV enters the V75 per-asset bond path when
    # it has an explicit target or a confirmed positive SGOV_BOND_BUCKET role.
    non_sgov_existing_assets = [aid for aid in existing_by_asset.keys() if aid != "SGOV"]
    work_assets = _ordered_union(target_map.keys(), non_sgov_existing_assets, sgov_role_assets)
    for aid in work_assets:
        target = target_map.get(aid, _money(0, currency))
        assessment = assessment_by_asset.get(aid) or _classify_asset(
            aid,
            authorized=aid in authorized_set,
            existing_amount=(sgov_bond_known_amount if aid == "SGOV" else existing_by_asset.get(aid, Decimal("0"))),
            broker_domain_type=run.broker_domain_type,
        )
        gap_reasons: list[str] = []

        if aid == "SGOV":
            if target.amount == 0:
                eligible_existing = run.sgov_bond_bucket_amount
                remaining = _known_money(0, currency)
                gap_reasons.append("ZERO_TARGET_GAP_IS_ZERO")
            elif run.sgov_bond_bucket_amount.status == ValueStatus.KNOWN:
                assert run.sgov_bond_bucket_amount.value is not None
                eligible_existing = run.sgov_bond_bucket_amount
                gap_amount = max(target.amount - run.sgov_bond_bucket_amount.value.amount, Decimal("0"))
                remaining = _known_money(gap_amount, currency)
                gap_reasons.append("SGOV_GAP_USES_BOND_BUCKET_ONLY")
            else:
                eligible_existing = run.sgov_bond_bucket_amount
                remaining = _unknown_money()
                gap_reasons.append("SGOV_BOND_BUCKET_UNKNOWN_FOR_POSITIVE_TARGET")
                issues.append(Work3Issue(
                    issue_class=Work3IssueClass.INSUFFICIENT_DATA,
                    code="SGOV_BOND_BUCKET_REQUIRED_FOR_GAP",
                    message="positive SGOV target requires known sgov_bond_bucket_amount; dry-powder SGOV must not be substituted",
                    asset_id="SGOV",
                    field="sgov_bond_bucket_amount",
                ))
                missing_fields.append("sgov_bond_bucket_amount")
        else:
            existing_amount = existing_by_asset.get(aid, Decimal("0"))
            eligible_existing = _known_money(existing_amount, currency)
            gap_amount = max(target.amount - existing_amount, Decimal("0"))
            remaining = _known_money(gap_amount, currency)
            gap_reasons.append("SAME_ACCOUNT_EXISTING_HOLDINGS_ONLY")

        gap = GapCalculation(
            asset_id=aid,
            target_amount=target,
            eligible_existing_amount=eligible_existing,
            remaining_target_gap_amount=remaining,
            eligibility_state=assessment.eligibility_state,
            reason_codes=gap_reasons,
        )
        gap_calculations.append(gap)

        if remaining.status == ValueStatus.KNOWN and remaining.value is not None:
            per_asset_inputs.append(PerAssetDeploymentInput(
                asset_id=aid,
                remaining_target_gap_amount=remaining.value,
                eligibility_state=assessment.eligibility_state.value,
                existing_position_amount=_money(existing_by_asset.get(aid, Decimal("0")), currency)
                if aid != "SGOV"
                else (
                    run.sgov_bond_bucket_amount.value
                    if run.sgov_bond_bucket_amount.status == ValueStatus.KNOWN and run.sgov_bond_bucket_amount.value is not None
                    else _money(0, currency)
                ),
                currency=currency,
                broker_account_id=run.broker_account_id,
            ))

    bucket_reconciliation = BucketReconciliation(
        bond_long_term_target=all_target_total,
        us_generic_long_term_target=us_total,
        tw_generic_long_term_target=tw_total,
        non_core_long_term_target=non_core_total,
        us_core_ratio_valid=us_ratio,
        tw_core_ratio_valid=tw_ratio,
        target_sum_reconciled=(us_total.amount + tw_total.amount + non_core_total.amount == all_target_total.amount),
        reason_codes=[
            "TARGET_SUM_RECONCILED",
            "CROSS_ACCOUNT_US_TW_LIFE_STAGE_SPLIT_NOT_RECOMPUTED_IN_SINGLE_ACCOUNT_RUN",
        ],
    )
    if not bucket_reconciliation.target_sum_reconciled:
        issues.append(Work3Issue(
            issue_class=Work3IssueClass.INVALID_INPUT,
            code="BUCKET_TARGET_SUM_MISMATCH",
            message="US/TW/non-core bucket totals must reconcile to bond_long_term_target",
        ))

    sgov_reconciliation = _sgov_reconciliation(run)

    # Determine Work3 data-quality state only. This is NOT Global Evaluation Precedence execution.
    classes = {issue.issue_class for issue in issues}
    if Work3IssueClass.INVALID_INPUT in classes:
        evaluation_state = EvaluationState.INVALID_INPUT
    elif Work3IssueClass.REVIEW_REQUIRED in classes:
        evaluation_state = EvaluationState.REVIEW_REQUIRED
    elif Work3IssueClass.INSUFFICIENT_DATA in classes:
        evaluation_state = EvaluationState.INSUFFICIENT_DATA
    else:
        evaluation_state = EvaluationState.COMPLETE

    missing_fields = list(dict.fromkeys(missing_fields))
    blocking_reason_codes = [issue.code for issue in issues if issue.issue_class != Work3IssueClass.INFO]
    reason_codes.extend(blocking_reason_codes)
    work3_complete = evaluation_state == EvaluationState.COMPLETE

    if not work3_complete:
        # Fail closed: Work4 must not consume a partially valid per-asset deployment list.
        per_asset_inputs = []

    return Work3State(
        run_id=run.run_id,
        broker_account_id=run.broker_account_id,
        broker_domain_type=run.broker_domain_type,
        currency=currency,
        rule_version=RULE_SOT_VERSION,
        predicate_version=PREDICATE_VERSION,
        life_stage_code_passthrough=run.life_stage_code,
        evaluation_state=evaluation_state,
        work3_complete=work3_complete,
        bond_long_term_target=all_target_total,
        eligibility_assessments=assessments,
        long_term_bucket_lines=long_term_lines,
        gap_calculations=gap_calculations,
        per_asset_inputs=per_asset_inputs,
        bucket_reconciliation=bucket_reconciliation,
        sgov_reconciliation=sgov_reconciliation,
        missing_required_fields=missing_fields,
        reason_codes=reason_codes,
        issues=issues,
        source_lineage=list(dict.fromkeys([*run.source_lineage, WORK3_ENGINE_VERSION])),
    )
