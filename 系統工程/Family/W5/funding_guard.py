"""Additional Family aggregate invariants; no allocation or funding engine."""
from decimal import Decimal, InvalidOperation, localcontext


class FundingError(ValueError):
    pass


def amount(value):
    if value is None:
        raise FundingError('DATA_UNAVAILABLE')
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise FundingError('INVALID_EXACT_AMOUNT')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise FundingError('INVALID_EXACT_AMOUNT') from exc
    if not result.is_finite() or result < 0:
        raise FundingError('INVALID_EXACT_AMOUNT')
    return result


def owner_key(owner):
    keys = ('client_id', 'funding_domain', 'broker', 'account', 'currency')
    if any(not isinstance(owner.get(k), str) or not owner[k].strip() for k in keys):
        raise FundingError('OWNER_REQUIRED')
    return tuple(owner[k] for k in keys)


def check_aggregate(*, owner, run_id, available, equity_budget, bond_budget, claims):
    key = owner_key(owner)
    if not isinstance(run_id, str) or not run_id:
        raise FundingError('RUN_REQUIRED')
    caps = {'EQUITY': amount(equity_budget), 'BOND': amount(bond_budget)}
    avail = amount(available)
    values = []
    ids = set()
    decisions = set()
    for claim in claims:
        if owner_key(claim['owner']) != key or claim.get('run_id') != run_id:
            raise FundingError('OWNER_OR_RUN_MISMATCH')
        cid = claim.get('claim_id')
        if not isinstance(cid, str) or not cid or cid in ids:
            raise FundingError('DUPLICATE_OR_MISSING_CLAIM')
        ids.add(cid)
        # A new label cannot duplicate the same underlying native decision.
        if 'asset_id' in claim or 'source_engine' in claim:
            decision=(claim.get('source_engine'),claim.get('asset_id'))
            if any(not isinstance(v,str) or not v for v in decision):
                raise FundingError('NATIVE_DECISION_IDENTITY_REQUIRED')
            if decision in decisions:raise FundingError('DUPLICATE_NATIVE_DECISION')
            decisions.add(decision)
        kind = claim.get('asset_class')
        if kind not in caps:
            raise FundingError('ASSET_CLASS_INVALID')
        values.append((kind, amount(claim.get('amount'))))
    all_values = [avail, *caps.values(), *(v for _, v in values)]
    # Enough precision for exact sums across the source decimal exponents.
    precision = max(1, max(v.adjusted() for v in all_values) + 1) + max(0, -min(v.as_tuple().exponent for v in all_values)) + len(str(len(values)+1)) + 2
    with localcontext() as ctx:
        ctx.prec = precision
        totals = {k: sum((v for kind, v in values if kind == k), Decimal(0)) for k in caps}
        total = sum(totals.values(), Decimal(0))
        if any(totals[k] > caps[k] for k in caps) or total > avail:
            raise FundingError('AGGREGATE_BUDGET_EXCEEDED')
        return {'owner': dict(owner), 'run_id': run_id, 'equity_used': str(totals['EQUITY']),
                'bond_used': str(totals['BOND']), 'available_remaining': str(avail-total),
                'trade_action': 'NO_TRADE'}
