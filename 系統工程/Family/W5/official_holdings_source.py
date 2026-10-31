"""Produce holdings facts from the existing official snapshot, without DB writes.

The sealed W6 intake and screenshot intake are source layers, not extra lots to
add to the legacy ledger. Keep observation, receipt and valuation time separate.
This view does not certify settlement, instrument identity or account ownership.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('HOLDINGS_SOURCE_TIMEZONE_REQUIRED')
    return result


def _quantity(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('HOLDINGS_QUANTITY_INVALID')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('HOLDINGS_QUANTITY_INVALID') from None
    if not number.is_finite() or number < 0:
        raise ValueError('HOLDINGS_QUANTITY_INVALID')
    return str(value)  # Preserve source precision, including trailing zeroes.


def holding_quote_currency(row):
    """Use an explicit per-share price unit, never a market-value currency."""
    facts=[]
    for key in ('last_price_displayed','average_price_displayed'):
        for fact in row.get('source_fields',{}).get(key,[]):
            currency=fact.get('currency_code')
            if (fact.get('value_state')=='KNOWN' and isinstance(currency,str)
                and len(currency)==3 and currency.isascii() and currency.isalpha() and currency.isupper()
                and fact.get('unit')==currency+'_PER_SHARE'):
                facts.append(deepcopy(fact))
    currencies={f['currency_code'] for f in facts}
    if len(currencies)!=1:return None
    return {'currency':next(iter(currencies)),'source_fields':facts,
        'source_row_digest':_digest(row['source_row']),
        'scope':'ACCEPTED_PER_SHARE_PRICE_UNIT__NO_FX_OR_VENUE_ASSERTION','registry_written':False}


def project_official_holdings(snapshot, *, evaluation_at=None):
    """Resolve source quantities; never sum representations of the same holding.

    W6 import rows keep their broker labels; screenshot rows keep their original
    unknown account/currency. Exact-symbol registry rows may supply identity, but
    a missing registry entry cannot remove an accepted source position.
    """
    client = snapshot['client_id']
    tables = snapshot['tables']
    if snapshot.get('payload_digest') != _digest(tables):
        raise ValueError('HOLDINGS_SNAPSHOT_DIGEST_MISMATCH')
    at = _time(evaluation_at) if evaluation_at else None
    for rows in tables.values():
        for row in rows:
            if row.get('client_id', client) != client:
                raise PermissionError('OFFICIAL_HOLDINGS_CLIENT_MISMATCH')
    registry = {}
    for row in tables.get('portfolio_instrument', []):
        registry.setdefault(row.get('ticker'), []).append(row)
    ledger = []
    by_key = {r['instrument_key']: r for r in tables.get('portfolio_instrument', [])}
    for row in tables.get('portfolio_position', []):
        if at and _time(row['as_of_utc']) > at:
            continue
        instrument = by_key.get(row['instrument_key'], {})
        ledger.append({'symbol': instrument.get('ticker'),
            'instrument_key': row['instrument_key'], 'account_key': row['account_key'],
            'quantity': _quantity(row.get('quantity_decimal')),
            'currency': instrument.get('quote_currency'),
            'observed_at': row.get('as_of_utc'), 'source_kind': 'PORTFOLIO_POSITION',
            'source_row': deepcopy(row)})
    runs = [r for r in tables.get('portfolio_snapshot_run', [])
        if r.get('run_state') == 'SEALED' and r.get('source_kind') != 'USER_HYPOTHETICAL'
        and (not at or _time(r['as_of_utc']) <= at)]
    items = tables.get('portfolio_snapshot_item', [])
    # Select the latest run *with the relevant holding source*. An unrelated
    # newer sealed profile/cash run must not erase the accepted holdings.
    layers = []
    for run in runs:
        current = [r for r in items if r['run_id'] == run['run_id']]
        for kind in ('W6', 'SCREENSHOT'):
            relevant = [r for r in current if
                (kind == 'W6' and r['field_key'] == 'accepted_W6_broker_holdings_json') or
                (kind == 'SCREENSHOT' and r.get('domain_code') == 'OWNER_SCREENSHOT_SOURCE'
                    and r['field_key'] == 'quantity')]
            if relevant:
                layers.append((kind, run, current, relevant))
    chosen = []
    for kind in ('W6', 'SCREENSHOT'):
        candidates = [x for x in layers if x[0] == kind]
        if not candidates:
            continue
        order = max((_time(x[1]['as_of_utc']), x[1].get('version_no', 0)) for x in candidates)
        latest = [x for x in candidates if
            (_time(x[1]['as_of_utc']), x[1].get('version_no', 0)) == order]
        if len(latest) != 1:
            raise ValueError('HOLDINGS_SOURCE_RUN_AMBIGUOUS')
        chosen.extend(latest)
    positions, cash, corrections = [], [], []
    for kind, run, current, relevant in chosen:
        for item in relevant:
            if kind == 'W6':
                if item['value_state'] != 'KNOWN':
                    raise ValueError('W6_HOLDINGS_SOURCE_UNKNOWN')
                rows = json.loads(item['value_text'])
            else:
                rows = [{'symbol': item['entity_key'],
                    'quantity': item.get('value_text') if item['value_state'] == 'KNOWN' else None}]
            for original in rows:
                row = deepcopy(original)
                symbol = row['symbol']
                matches = registry.get(symbol, [])
                if len(matches) > 1:
                    raise ValueError('HOLDINGS_INSTRUMENT_AMBIGUOUS')
                instrument = deepcopy(matches[0]) if matches else None
                source_fields = {}
                if kind == 'SCREENSHOT':
                    for fact in current:
                        if (fact.get('domain_code') == 'OWNER_SCREENSHOT_SOURCE' and
                                fact.get('entity_key') == symbol):
                            source_fields.setdefault(fact['field_key'], []).append(deepcopy(fact))
                currencies = {fact['currency_code'] for facts in source_fields.values()
                    for fact in facts if fact.get('currency_code')}
                if len(currencies) > 1:
                    raise ValueError('HOLDINGS_SOURCE_CURRENCY_CONFLICT')
                source_currency = next(iter(currencies), None)
                if (row.get('currency') and source_currency and
                        row['currency'] != source_currency):
                    raise ValueError('HOLDINGS_SOURCE_CURRENCY_CONFLICT')
                if 'currency' not in row:
                    row['currency'] = source_currency
                row.update(quantity=_quantity(row.get('quantity')),
                    quantity_state='KNOWN' if row.get('quantity') is not None else 'UNKNOWN',
                    source_kind='SEALED_W6' if kind == 'W6' else 'OWNER_SCREENSHOT_SOURCE',
                    source_row=deepcopy(item), source_run_id=run['run_id'],
                    observed_at=item.get('source_observed_at_utc'),
                    received_at=run['as_of_utc'], instrument=instrument,
                    source_fields=source_fields,
                    instrument_key=instrument['instrument_key'] if instrument else None,
                    account_key=None, account_mapping_state='UNKNOWN')
                if at and row['observed_at'] and _time(row['observed_at']) > at:
                    raise ValueError('HOLDINGS_OBSERVATION_IN_FUTURE')
                # Cash is not a security position or physical SGOV.
                if symbol == 'USD_CASH':
                    row.update(asset_kind='CASH', settlement_state='UNKNOWN')
                    cash.append(row)
                else:
                    row['asset_kind'] = 'SECURITY'
                    positions.append(row)
        for item in current:
            if item['field_key'] == 'owner_correction_json' and item['value_state'] == 'KNOWN':
                corrections.append({'payload': json.loads(item['value_text']),
                    'source_row': deepcopy(item), 'received_at': run['as_of_utc']})
            if (item.get('domain_code') == 'OWNER_SCREENSHOT_SOURCE' and
                    item['field_key'] in ('cash_balance', 'reserved_cash', 'settled_cash',
                                         'total_cash_same_balance_not_additive')):
                cash.append({'asset_kind': 'CASH', 'field': item['field_key'],
                    'value': item.get('value_text') if item['value_state'] == 'KNOWN' else None,
                    'value_state': item['value_state'], 'currency': item.get('currency_code'),
                    'observed_at': item.get('source_observed_at_utc'),
                    'received_at': run['as_of_utc'], 'source_row': deepcopy(item),
                    'settlement_state': 'UNKNOWN'})
    # Different sealed source formats have no implicit precedence. Report the
    # overlap instead of adding quantities or choosing by intake timestamp.
    identities = [(r['source_kind'], r['symbol'], r.get('broker_label')) for r in positions]
    if len(identities) != len(set(identities)):
        raise ValueError('HOLDINGS_SOURCE_POSITION_AMBIGUOUS')
    overlap = sorted({r['symbol'] for r in positions
        if len({p['source_kind'] for p in positions if p['symbol'] == r['symbol']}) > 1})
    selected_symbols = {r['symbol'] for r in positions}
    # Ledger-only positions stay visible, e.g. MOU's Taiwan holding not shown in
    # the US screenshots. They remain separate account-scoped original facts.
    ledger_only = [r for r in ledger if r['symbol'] not in selected_symbols]
    registered = set(registry)
    return {'schema_version': 'Family.W8.OfficialHoldingsProjection.v1',
        'client_id': client, 'source_db_sha256': snapshot['source_sha256'],
        'snapshot_digest': snapshot['payload_digest'], 'evaluation_at': evaluation_at,
        'ledger_positions': ledger, 'latest_sealed_source_positions': positions +
            [r for r in cash if r.get('symbol') == 'USD_CASH'],
        'analysis_security_positions': positions, 'ledger_only_positions': ledger_only,
        'cash_sources': cash, 'owner_corrections': corrections,
        'source_symbols_missing_from_instrument_registry': sorted(selected_symbols - registered),
        'source_layer_conflicts': overlap, 'source_layers_preserved': True,
        'cash_settlement_asserted': False, 'database_written': False,
        'trade_authorization': 'NONE'}


def build_official_position_view(snapshot, account, evaluation_at, acceptance, account_scope):
    """Map accepted sealed IB source facts to the already-bound broker category.

    The original account-category proof is validated by bind_owner before this
    function. It does not create an external account number or assert settlement.
    Unmapped brokers remain separate; no Taiwan/US positions are combined.
    """
    owner = account_scope.get('owner', {})
    if (owner.get('client_id') != snapshot['client_id'] or owner.get('account') != account or
            account_scope.get('source_snapshot_digest') != snapshot['payload_digest'] or
            acceptance.get('client_id') != snapshot['client_id'] or
            acceptance.get('source_db_sha256') != snapshot['source_sha256'] or
            acceptance.get('snapshot_digest') != snapshot['payload_digest'] or
            acceptance.get('owner_decision_digest') != _digest(acceptance.get('owner_decision'))):
        raise PermissionError('OFFICIAL_POSITION_SOURCE_BINDING_MISMATCH')
    view = project_official_holdings(snapshot, evaluation_at=evaluation_at.isoformat())
    if view['source_layer_conflicts']:
        raise ValueError('OFFICIAL_POSITION_SOURCE_LAYER_CONFLICT')
    selected = []
    # IB is the broker label in the accepted W6 import. The screenshot intake
    # explicitly records its broker account category as the IB_SCREEN entity.
    # Neither label supplies a guessed brokerage account number.
    for row in view['analysis_security_positions']:
        broker_proof = None
        if owner.get('broker') == 'IBKR':
            if row['source_kind'] == 'SEALED_W6' and row.get('broker_label') == 'IB':
                broker_proof = {'broker_label': 'IB', 'source_row': row['source_row']}
            elif row['source_kind'] == 'OWNER_SCREENSHOT_SOURCE':
                markers = [r for r in snapshot['tables']['portfolio_snapshot_item']
                    if r['run_id'] == row['source_run_id'] and
                    r.get('domain_code') == 'OWNER_SCREENSHOT_SOURCE' and
                    r.get('field_key') == 'broker_account_number']
                if len(markers) == 1 and markers[0]['entity_key'] == 'IB_SCREEN':
                    broker_proof = {'broker_label': 'IB_SCREEN', 'source_row': markers[0]}
        if broker_proof is None:
            continue
        instrument = deepcopy(row.get('instrument'))
        if instrument is None:
            # A stable analysis-view identity, never a new formal registry row.
            instrument = {'client_id': snapshot['client_id'],
                'instrument_key': 'SOURCE:IBKR:' + row['symbol'], 'ticker': row['symbol'],
                'quote_currency': row.get('currency'), 'exchange_code': None,
                'identity_state': 'SOURCE_SYMBOL_ONLY', 'source_reference': row['source_row'].get('source_reference')}
        elif row.get('currency') and instrument.get('quote_currency') not in (None, row['currency']):
            raise ValueError('OFFICIAL_POSITION_CURRENCY_MISMATCH')
        quote_source=holding_quote_currency(row)
        if quote_source is not None:
            if instrument.get('quote_currency') not in (None,quote_source['currency']):
                raise ValueError('OFFICIAL_POSITION_QUOTE_CURRENCY_CONFLICT')
            if instrument.get('quote_currency') is None:
                instrument['quote_currency']=quote_source['currency']
                instrument['quote_currency_source']=quote_source
        source = {'client_id': snapshot['client_id'], 'account_key': account,
            'instrument_key': instrument['instrument_key'], 'quantity_decimal': row['quantity'],
            'as_of_utc': row['observed_at'], 'received_at_utc': row['received_at'],
            'source_kind': row['source_kind'], 'source_row': deepcopy(row['source_row']),
            'source_run_id': row['source_run_id'], 'broker_category_source': broker_proof,
            'source_db_sha256': snapshot['source_sha256'],
            'owner_acceptance_digest': acceptance['owner_decision_digest']}
        selected.append({'instrument_key': instrument['instrument_key'], 'quantity': row['quantity'],
            'quantity_state': row['quantity_state'], 'source_position': source,
            'source_instrument': instrument, 'source_fields': deepcopy(row['source_fields'])})
    # If this broker has a sealed intake, it replaces matching ledger holdings.
    # Other brokers are never silently pulled into the requested account.
    if not selected:
        return None
    ids = [r['instrument_key'] for r in selected]
    if len(ids) != len(set(ids)):
        raise ValueError('OFFICIAL_POSITION_ACCOUNT_SOURCE_AMBIGUOUS')
    return sorted(selected, key=lambda r: r['instrument_key'])
