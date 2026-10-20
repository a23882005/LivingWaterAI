"""Bind explicit V70 tactical amounts; a ready macro feed is not a budget."""
from decimal import Decimal, InvalidOperation


class TacticalBudgetError(ValueError):
    pass


def tactical_cap(handoff, leg):
    if leg not in {'equity', 'bond'}:
        raise TacticalBudgetError('INVALID_LEG')
    context = handoff['v70_runtime_context']
    payload = context['payload']
    if context['run_id'] != handoff['run_id'] or payload.get('run_id') != handoff['run_id']:
        raise TacticalBudgetError('TACTICAL_RUN_MISMATCH')
    if not context.get('upstream_v70_snapshot_id') or not context.get('source_reference_ids'):
        raise TacticalBudgetError('TACTICAL_SOURCE_REQUIRED')
    if payload.get('value_state') != 'KNOWN' or payload.get('data_quality') not in {'OK','FALLBACK_USED'}:
        raise TacticalBudgetError('TACTICAL_VALUE_NOT_KNOWN')
    issues = payload.get('issue_codes')
    if not isinstance(issues, list) or any(not isinstance(x,str) for x in issues):
        raise TacticalBudgetError('TACTICAL_ISSUES_REQUIRED')
    field = 'stock_tactical_amount' if leg == 'equity' else 'bond_tactical_amount'
    value = payload.get(field)
    if value is None or isinstance(value, bool):
        raise TacticalBudgetError('TACTICAL_AMOUNT_REQUIRED:' + field)
    try: amount = Decimal(str(value))
    except InvalidOperation as exc: raise TacticalBudgetError('TACTICAL_AMOUNT_INVALID') from exc
    if not amount.is_finite() or amount < 0:
        raise TacticalBudgetError('TACTICAL_AMOUNT_INVALID')
    settlement = handoff['funding_context']['settlement']
    if settlement['source_status'] != 'SETTLED' or settlement['cash_basis'] != 'AVAILABLE':
        raise TacticalBudgetError('SETTLED_AVAILABLE_REQUIRED')
    # These explicit risk states carry a zero new-buy ceiling. Preserve the
    # original payload in the caller rather than changing its declared amount.
    blocked = [code for code in issues if code in {'EXCEEDS_CAP','HARD_GATE','HARD_GATE_TRIGGERED'}]
    return {'amount': Decimal('0') if blocked else amount,
            'source_amount': amount, 'currency': handoff['currency'],
            'source_snapshot_id': context['upstream_v70_snapshot_id'],
            'reason_codes': blocked, 'source_field': field}
