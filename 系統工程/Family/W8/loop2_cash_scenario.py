"""A cash-only simulation overlay, kept separate from official source facts.

This adapter never changes native enums, account identities, investment pools,
SGOV roles, targets or budgets. Its values are Decimal strings until the native
JSON boundary. A failed overlay is diagnostic data, never an effective input.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from family_input import digest

CASH_FIELDS = ('total', 'available', 'unsettled', 'reserved')


def _money(value):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('INVALID_CASH_VALUE')
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError('INVALID_CASH_VALUE') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError('INVALID_CASH_VALUE')
    return str(amount)


def build_cash_overlay(raw_cash, *, snapshot, owner, authorization, run_id):
    if (set(raw_cash) != set(CASH_FIELDS) or not run_id
            or owner.get('client_id') != snapshot['client_id']
            or authorization.get('schema_version') != 'Family.W8.CashTrialPolicy.v1'
            or authorization.get('missing_cash_value') != '0'
            or not authorization.get('source_reference')):
        raise ValueError('INVALID_CASH_OVERLAY_SCOPE_OR_AUTHORIZATION')
    assumptions = []
    values = {}
    issues = []
    for name in CASH_FIELDS:
        value = raw_cash[name]
        if value is None:
            values[name] = '0'
            assumptions.append({'field_path': 'cash_state.' + name,
                'original_state': 'NULL_OR_ABSENT', 'assumed_value': '0',
                'authorization_reference': authorization['source_reference'],
                'run_id': run_id, 'scope': 'SIMULATION_ONLY',
                'evidence_status': 'AUTHORIZED_ASSUMPTION'})
        else:
            try:
                values[name] = _money(value)
            except ValueError:
                issues.append({'code': 'INVALID_CASH_VALUE', 'field_path': 'cash_state.' + name})
    if not issues:
        for name in CASH_FIELDS[1:]:
            if Decimal(values[name]) > Decimal(values['total']):
                issues.append({'code': 'CASH_ASSUMPTION_CONFLICT' if raw_cash['total'] is None else 'CASH_SOURCE_CONFLICT',
                    'field_path': 'cash_state.' + name,
                    'missing_reason': 'Subvalue exceeds total; known values were retained'})
    context = {'schema_version': 'Family.W8.CashSimulationContext.v1',
        'enabled': True, 'mode': 'CASH_ZERO_SIMULATION', 'run_id': run_id,
        'owner': deepcopy(owner), 'source_db_sha256': snapshot['source_sha256'],
        'snapshot_digest': digest(snapshot), 'raw_cash': deepcopy(raw_cash),
        'raw_cash_digest': digest(raw_cash), 'effective_cash': values,
        'authorization': deepcopy(authorization),
        'authorization_reference': authorization['source_reference'],
        'assumptions': assumptions, 'issues': issues, 'no_trade': True,
        'status': 'BLOCKED' if issues else 'VALIDATED',
        'label': '本次模擬含現金缺值補零', 'official_cash_records_changed': False}
    context['overlay_digest'] = digest(context)
    return context


def validate_cash_overlay(raw_cash, scenario, *, snapshot, owner, authorization, run_id):
    """Recompute the whitelist overlay; a claimed digest alone is insufficient."""
    expected = build_cash_overlay(raw_cash, snapshot=snapshot, owner=owner,
        authorization=authorization, run_id=run_id)
    if scenario != expected:
        raise PermissionError('CASH_OVERLAY_BINDING_MISMATCH')
    return {'effective_cash': deepcopy(expected['effective_cash']) if not expected['issues'] else None,
        'issues': deepcopy(expected['issues']), 'overlay_digest': expected['overlay_digest']}
