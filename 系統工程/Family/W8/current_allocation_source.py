"""Value accepted account holdings without turning them into a global NAV.

The denominator is a dated composite of security values and reported cash.
It is neither broker net liquidation nor an executable cash balance. Other
accounts and unknown cash remain explicit; an approved investment base never
substitutes for a current valuation.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext

from family_input import digest
from family_boundary import timestamp
from position_source_bridge import quantity_time
from valuation import value_position


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('CURRENT_ALLOCATION_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('CURRENT_ALLOCATION_NUMBER_INVALID') from None
    if not result.is_finite() or result < 0:
        raise ValueError('CURRENT_ALLOCATION_NUMBER_INVALID')
    return result


def build(request, analysis, prepared, context):
    identity = {'client_id': request['client_id'], 'run_id': request['run_id'],
                'owner': request['owner'],
                'source_db_sha256': request['client_snapshot']['payload']['source_sha256']}
    if any(analysis.get(k) != v for k, v in identity.items()):
        raise PermissionError('CURRENT_ALLOCATION_ANALYSIS_IDENTITY_MISMATCH')
    positions = prepared.payload['positions']
    rows = analysis['analysis_result']['positions']
    index = {r['instrument_id']: r for r in rows}
    if len(index) != len(rows) or set(index) != {p['instrument_key'] for p in positions}:
        raise PermissionError('CURRENT_ALLOCATION_POSITION_COVERAGE_MISMATCH')
    out = {'schema_version': 'Family.W8.CurrentAllocationSource.v1', **deepcopy(identity),
           'evaluation_at': request['evaluation_at'], 'positions': [], 'issues': [],
           'currency': request['owner']['currency'],
           'scope': 'SELECTED_ACCOUNT_GROSS_ASSET_REFERENCE__NOT_BROKER_NET_LIQUIDATION',
           'valuation_basis': 'ACCEPTED_QUANTITIES_AT_DATED_REFERENCE_PRICES',
           'latest_market_freshness_asserted': False,
           'cash_available_inferred_from_total': False, 'trade_action': 'NO_TRADE'}
    for position in positions:
        key = position['instrument_key']; row = index[key]; market = row.get('market') or {}
        instrument = position['source_instrument']; symbol = instrument.get('ticker')
        currency = instrument.get('quote_currency')
        if (row.get('symbol') != symbol or market.get('instrument_key') != key
                or row.get('owner') != request['owner']):
            raise PermissionError('CURRENT_ALLOCATION_POSITION_IDENTITY_MISMATCH')
        if (position.get('quantity_state') != 'KNOWN' or not currency
                or market.get('observed_close') is None or not market.get('observed_date')
                or not market.get('source_sha256')):
            out['issues'].append({'code': 'POSITION_VALUATION_SOURCE_REQUIRED', 'instrument_id': key})
            continue
        observed = market['observed_date'] + 'T00:00:00Z'
        if timestamp(observed, 'price.observed_at') > timestamp(request['evaluation_at'], 'evaluation_at'):
            raise PermissionError('CURRENT_ALLOCATION_FUTURE_PRICE')
        if market.get('provider_verified_at'):
            if timestamp(market['provider_verified_at'], 'price.available_at') > timestamp(request['evaluation_at'], 'evaluation_at'):
                raise PermissionError('CURRENT_ALLOCATION_FUTURE_SOURCE')
        quantity_at, quantity_basis = quantity_time(request, position['source_position'], context)
        quantity = {'state': 'KNOWN', 'value': str(number(position['quantity'])),
                    'instrument_key': key, 'as_of': quantity_at, 'as_of_basis': quantity_basis,
                    'source_reference': 'ACCEPTED-POSITION:' + digest(position)}
        price = {'state': 'KNOWN', 'value': str(number(market['observed_close'])),
                 'currency': currency, 'instrument_key': key, 'as_of': request['evaluation_at'],
                 'price_observation_date': market['observed_date'],
                 'price_observation_as_of': None, 'observation_time_state': 'DATE_ONLY',
                 'price_source_digest': market['source_sha256'],
                 'valuation_basis': out['valuation_basis'],
                 'source_reference': 'ANALYSIS-MARKET:' + market['source_sha256']}
        # FX is an independently supplied, asset-specific source, never the
        # account currency or an unlabelled inverse of an old allocation base.
        fx = context.get('current_allocation_fx', {}).get(key)
        valued = value_position(quantity=quantity, price=price, fx=fx,
                                target_currency=out['currency'], evaluation_at=request['evaluation_at'])
        reference = row.get('current_analysis', {}).get('recommendation', {})
        if (currency == out['currency'] and reference.get('confirmed_position_amount') is not None
                and number(reference['confirmed_position_amount']) != number(valued['value'])):
            raise PermissionError('CURRENT_ALLOCATION_EXISTING_VALUE_MISMATCH')
        if valued['state'] != 'KNOWN':
            out['issues'].append({'code': 'POSITION_VALUATION_UNAVAILABLE',
                                  'instrument_id': key, 'issue_codes': valued['issue_codes']})
        out['positions'].append({'instrument_id': key, 'symbol': symbol,
                                 'quantity': quantity, 'price': price, 'valuation': valued,
                                 'formal_position_valuation_allowed': row.get('position_valuation_allowed')})
    trial = analysis['cash_trial']
    if trial.get('owner') != request['owner']:
        raise PermissionError('CURRENT_ALLOCATION_CASH_OWNER_MISMATCH')
    total_source = trial.get('formal_sources', {}).get('total')
    total_assumed = any(a.get('field_path') == 'cash_state.total' for a in trial.get('assumptions', []))
    cash = None
    if total_source and not total_assumed:
        cash = number(trial['decimal_values']['total'])
    else:
        out['issues'].append({'code': 'REPORTED_TOTAL_CASH_REQUIRED', 'field_path': 'cash_trial.total'})
    out['reported_cash'] = {'state': 'KNOWN' if cash is not None else 'UNKNOWN',
                            'value': str(cash) if cash is not None else None,
                            'source': deepcopy(total_source), 'executable_budget': False}
    with localcontext() as ctx:
        ctx.prec = 50
        subtotal = sum((number(p['valuation']['value']) for p in out['positions']
                        if p['valuation']['state'] == 'KNOWN'), Decimal(0))
        out['known_security_subtotal'] = str(subtotal)
        total = subtotal + cash if cash is not None and not out['issues'] else None
        out['account_asset_reference'] = {'state': 'KNOWN' if total is not None else 'UNKNOWN',
            'value': str(total) if total is not None else None, 'currency': out['currency'],
            'as_of': request['evaluation_at'], 'scope': out['scope']}
        for position in out['positions']:
            position['account_weight'] = (str(number(position['valuation']['value']) / total)
                if total is not None and total > 0 and position['valuation']['state'] == 'KNOWN' else None)
    accounts = request['client_snapshot']['payload']['tables']['portfolio_account']
    out['other_accounts'] = [r['account_key'] for r in accounts
                             if r['account_key'] != request['owner']['account']]
    out['portfolio_nav'] = {'state': 'UNKNOWN', 'value': None, 'currency': out['currency'],
        'reason': 'GLOBAL_SCOPE_AND_NET_ASSET_RECONCILIATION_REQUIRED',
        'missing_account_keys': deepcopy(out['other_accounts']),
        'account_asset_reference_is_not_global_nav': True}
    out['source_reference'] = 'CURRENT-ALLOCATION:' + digest(out)
    out['output_digest'] = digest(out)
    return out
