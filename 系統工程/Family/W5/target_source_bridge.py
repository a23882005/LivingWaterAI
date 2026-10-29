"""Compare preserved W2 targets to native consumers without rewriting targets.

This is a partial, same-currency binding: original C7 target weights and the
selected V82 money target. C7 integrated weights may legitimately differ after
protection. Bond allocation/FX projections require a separate source contract.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from family_boundary import require
from family_input import digest


def number(value, field):
    try:
        assert not isinstance(value, bool) and value is not None
        result = Decimal(str(value))
        assert result.is_finite() and result >= 0
        return result
    except (AssertionError, InvalidOperation, ValueError):
        require(False, 'TARGET_NUMBER_INVALID', field)


def bind_target_source(request,*,projection=None):
    draft = request['confirmed_target']['payload']['draft']
    rows = draft.get('target_lines')
    require(isinstance(rows, list) and bool(rows), 'TARGET_LINES_REQUIRED',
            'confirmed_target.payload.draft.target_lines', 'W2', 'DATA_UNAVAILABLE')
    lines = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('instrument_id'), str)
                and bool(row['instrument_id'].strip()), 'TARGET_INSTRUMENT_REQUIRED', 'target_lines')
        key = (projection['source_to_native'][row['instrument_id']] if projection is not None
            else row['instrument_id'])
        require(key not in lines, 'TARGET_INSTRUMENT_AMBIGUOUS', 'target_lines.' + key)
        lines[key] = row
    bundle = request['native_bundle']
    targets = bundle['asset_framework']['integrated_asset_framework']['instrument_targets']
    ids = [row['instrument_id'] for row in targets]
    require(len(ids) == len(set(ids)) and set(ids) == set(lines),
            'TARGET_FRAMEWORK_COVERAGE_MISMATCH', 'asset_framework.instrument_targets')
    for row in targets:
        key = row['instrument_id']; weight = lines[key].get('weight', {})
        require(weight.get('value_state') == 'KNOWN', 'TARGET_WEIGHT_UNAVAILABLE',
                'target_lines.' + key + '.weight', 'W2', 'DATA_UNAVAILABLE')
        expected = number(weight.get('value'), 'target.weight')
        require(expected <= 1, 'TARGET_WEIGHT_RANGE', 'target_lines.' + key)
        actual = number(row.get('work6_final_target_weight'), 'C7.work6_final_target_weight')
        require(abs(expected - actual) <= Decimal('1e-12'), 'TARGET_C7_WEIGHT_MISMATCH',
                'asset_framework.instrument_targets.' + key)
    stock = bundle['stock_request']['asset_context']['asset']['asset_id']
    require(bundle['stock_request']['asset_context'].get('project_target_pointer') ==
            '/instrument_targets/' + stock + '/project_target_position',
            'TARGET_STOCK_POINTER_MISMATCH', 'stock_request.asset_context.project_target_pointer')
    require(stock in lines, 'TARGET_STOCK_ID_MAPPING_REQUIRED', 'target_lines',
            'W5', 'DATA_UNAVAILABLE')
    money = lines[stock].get('target_amount', {})
    require(money.get('value_state') == 'KNOWN', 'TARGET_AMOUNT_UNAVAILABLE',
            'target_lines.' + stock + '.target_amount', 'W2', 'DATA_UNAVAILABLE')
    original_money=deepcopy(money)
    if projection is not None:
        money=projection['targets'][stock]['target_amount']
        require(money.get('value_state')=='KNOWN','TARGET_FX_SOURCE_REQUIRED',
                'target_lines.'+stock+'.target_amount','W5','DATA_UNAVAILABLE')
    require(money.get('currency') == request['owner']['currency'],
            'TARGET_FX_SOURCE_REQUIRED', 'target_lines.' + stock + '.target_amount',
            'W5', 'DATA_UNAVAILABLE')
    expected = number(money.get('amount'), 'target_amount.amount')
    for branch in ('stock_request', 'bond_request'):
        native = bundle[branch]['work3_handoff']['final_target']['payload']['instrument_targets']
        require(stock in native, 'TARGET_STOCK_ID_MAPPING_REQUIRED', branch)
        actual = number(native[stock].get('project_target_position'), branch + '.project_target_position')
        require(actual == expected, 'TARGET_V82_AMOUNT_MISMATCH', branch + '.final_target.' + stock)
    result={'scope': 'C7_ORIGINAL_WEIGHTS_AND_V82_SAME_CURRENCY_AMOUNT',
            'target_digest': digest(request['confirmed_target']),
            'source_target_lines': deepcopy(rows), 'stock_target_amount': deepcopy(money),
            'pending': ['V75_TARGET_SPLIT_SOURCE', 'C7_INTEGRATED_WEIGHT_PROJECTION', 'CROSS_CURRENCY_TARGET_FX']}
    if projection is not None:
        result.update(scope='C7_ORIGINAL_WEIGHTS_AND_SOURCE_PROJECTED_V82_MONEY',
            original_stock_target_amount=original_money,native_target_source_digest=digest(projection))
        result['pending'].remove('CROSS_CURRENCY_TARGET_FX')
    return result
