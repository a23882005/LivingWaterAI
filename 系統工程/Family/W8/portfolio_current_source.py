"""Join dated account asset references for a disclosed cash-zero comparison.

This produces a C Current Allocation comparison, not a current broker NAV.
Every security is valued, account cash assumptions stay visible, and funding
domains remain separate. No allocation base, buying power or SGOV role is cash.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from family_input import digest
from family_boundary import timestamp
from current_allocation_source import number


def _read(descriptor):
    raw = Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest() != descriptor['sha256']:
        raise PermissionError('PORTFOLIO_MARKET_SOURCE_CHANGED')
    return json.loads(raw)


def quote(instrument, source, evaluation_at):
    item = source['items'][instrument['instrument_key']]
    raw = _read(item['raw']); receipt = _read(item['receipt'])
    if (receipt.get('sha256') != item['raw']['sha256'] or receipt.get('http_status') != 200
            or not receipt.get('retrieved_at') or not receipt.get('url')):
        raise PermissionError('PORTFOLIO_MARKET_RECEIPT_MISMATCH')
    result = raw['chart']['result'][0]; meta = result['meta']
    symbol = meta['symbol']
    if (item.get('provider_symbol') != symbol or symbol.split('.')[0] != instrument['ticker']
            or meta['currency'] != instrument.get('quote_currency')
            or symbol.rsplit('.', 1)[-1] not in ('TW', 'TWO')):
        raise PermissionError('PORTFOLIO_MARKET_IDENTITY_MISMATCH')
    regular = meta['currentTradingPeriod']['regular']
    close_at = datetime.fromtimestamp(regular['end'], timezone.utc)
    if close_at > timestamp(evaluation_at, 'evaluation_at'):
        raise PermissionError('PORTFOLIO_MARKET_INCOMPLETE_SESSION')
    # Use only the provider's matching completed daily bar, not a live quote.
    zone_offset = int(meta['gmtoffset'])
    local_date = datetime.fromtimestamp(regular['end'] + zone_offset, timezone.utc).date()
    pairs = [(t, c) for t, c in zip(result['timestamp'], result['indicators']['quote'][0]['close'])
             if c is not None and datetime.fromtimestamp(t + zone_offset, timezone.utc).date() == local_date]
    if len(pairs) != 1:
        raise ValueError('PORTFOLIO_COMPLETED_DAILY_BAR_REQUIRED')
    return {'value': str(number(pairs[0][1])), 'currency': meta['currency'],
        'observation_at': close_at.isoformat(), 'retrieved_at': receipt['retrieved_at'],
        'provider_symbol': symbol, 'source_sha256': item['raw']['sha256'],
        'source_reference': receipt['url'], 'registry_exchange_changed': False,
        'scope': 'DATED_ANALYSIS_REFERENCE__NOT_CANONICAL_EXECUTION_MARKET_ATTESTATION'}


def build(request, analysis, selected, sources, market_descriptor):
    market = _read(market_descriptor)
    snapshot = request['client_snapshot']['payload']; tables = snapshot['tables']
    if (market.get('schema_version') != 'Family.W8.PortfolioMarketSource.v1'
            or market.get('client_id') != request['client_id']
            or market.get('source_db_sha256') != snapshot['source_sha256']):
        raise PermissionError('PORTFOLIO_MARKET_OWNER_MISMATCH')
    out = {'schema_version': 'Family.W8.PortfolioCurrentComparison.v1',
        'client_id': request['client_id'], 'run_id': request['run_id'],
        'source_db_sha256': snapshot['source_sha256'], 'evaluation_at': request['evaluation_at'],
        'mode': 'CASH_ZERO_SIMULATION', 'positions': [], 'cash_assumptions': [], 'issues': [],
        'source_basis': 'DATED_REFERENCE_COMPOSITE__RESTATED_CURRENT_VINTAGE_NOT_PIT',
        'scope': 'GLOBAL_DATED_ASSET_AND_REPORTED_CASH_COMPARISON__NOT_VERIFIED_NET_NAV',
        'bank_cash_scope': 'OUT_OF_SCOPE', 'cross_account_funding_authorized': False,
        'trade_action': 'NO_TRADE', 'new_approval_created': False}
    currency = request['owner']['currency']; out['currency'] = currency
    fx = analysis['native_target_source'].get('fx_observation')
    def convert(amount, original_currency):
        if original_currency == currency:
            return number(amount)
        if (not fx or fx.get('base_currency') != currency or fx.get('quote_currency') != original_currency
                or not fx.get('source_url') or fx['as_of'] > request['evaluation_at'][:10]):
            raise ValueError('PORTFOLIO_CURRENT_EXPLICIT_FX_REQUIRED')
        with localcontext() as ctx:
            ctx.prec = 50
            return number(amount) / number(fx['quote_per_base'])
    out['fx_observation'] = deepcopy(fx)
    if selected['issues']:
        out['issues'] += deepcopy(selected['issues'])
    for row in selected['positions']:
        if row['valuation']['state'] != 'KNOWN':
            continue
        out['positions'].append({'instrument_id': row['instrument_id'], 'symbol': row['symbol'],
            'account_key': request['owner']['account'], 'value': row['valuation']['value'],
            'source': deepcopy(row), 'currency': currency})
    account_contexts = sources['native_bundle']['stock_request']['c7_funding_context']['contexts']
    account_keys = {r['account_key'] for r in tables['portfolio_account']}
    covered = {r['account'] for r in account_contexts if r.get('account') is not None}
    if covered != account_keys:
        raise PermissionError('PORTFOLIO_ACCOUNT_SCOPE_COVERAGE_MISMATCH')
    instruments = {r['instrument_key']: r for r in tables['portfolio_instrument']}
    latest = {}
    for position in tables['portfolio_position']:
        if position['account_key'] == request['owner']['account']:
            continue  # The accepted broker/intake layer already superseded these old rows.
        if timestamp(position['as_of_utc'], 'position.as_of') > timestamp(request['evaluation_at'], 'evaluation_at'):
            continue
        key = (position['account_key'], position['instrument_key'])
        old = latest.get(key)
        if old and old['as_of_utc'] == position['as_of_utc'] and old['quantity_decimal'] != position['quantity_decimal']:
            raise PermissionError('PORTFOLIO_CURRENT_POSITION_CONFLICT')
        if old is None or position['as_of_utc'] > old['as_of_utc']:
            latest[key] = position
    for (account, key), position in sorted(latest.items()):
        try:
            observation = quote(instruments[key], market, request['evaluation_at'])
        except KeyError:
            out['issues'].append({'code': 'PORTFOLIO_CURRENT_QUOTE_REQUIRED', 'instrument_id': key})
            continue
        with localcontext() as ctx:
            ctx.prec = 50
            value = convert(number(position['quantity_decimal']) * number(observation['value']), observation['currency'])
        out['positions'].append({'instrument_id': key, 'symbol': instruments[key]['ticker'],
            'account_key': account, 'value': str(value), 'currency': currency,
            'source': {'position': deepcopy(position), 'price': observation}})
    cash_sources = analysis['cash_trial']
    for account_context in account_contexts:
        account = account_context.get('account')
        if account is None:
            continue  # Explicitly confirmed absent funding domain, not a zero-valued real account.
        if account == request['owner']['account']:
            cash = selected['reported_cash']
            if cash['state'] != 'KNOWN':
                out['issues'].append({'code': 'PORTFOLIO_SELECTED_CASH_UNKNOWN', 'account_key': account})
                continue
            amount = number(cash['value']); cash_source = deepcopy(cash)
        else:
            # Existing funding contexts already passed the original account
            # isolation validator. Preserve this exact authorized zero trial.
            amount = number(account_context['brokerage_cash_state']['total'])
            if amount != 0:
                raise ValueError('PORTFOLIO_OTHER_ACCOUNT_NONZERO_CASH_SOURCE_REQUIRED')
            policy = cash_sources['scenario']['authorization']
            if (policy.get('missing_cash_value') != '0' or not policy.get('source_reference')):
                raise PermissionError('PORTFOLIO_ZERO_CASH_AUTHORIZATION_REQUIRED')
            cash_source = {'value': '0', 'evidence_state': 'AUTHORIZED_ASSUMPTION',
                'source_reference': policy['source_reference'], 'account_key': account,
                'scope': 'SIMULATION_ONLY__NOT_PROOF_OF_ZERO_CASH'}
            out['cash_assumptions'].append(deepcopy(cash_source))
        out['positions'].append({'instrument_id': 'ACCOUNT_CASH:' + account, 'symbol': None,
            'account_key': account, 'value': str(amount), 'currency': currency, 'source': cash_source})
    with localcontext() as ctx:
        ctx.prec = 50
        total = sum((number(p['value']) for p in out['positions']), Decimal(0))
        out['denominator'] = {'state': 'KNOWN' if not out['issues'] and total > 0 else 'UNKNOWN',
            'value': str(total) if not out['issues'] and total > 0 else None, 'currency': currency,
            'as_of': request['evaluation_at'], 'data_quality': 'FALLBACK_USED', 'scope': out['scope']}
        for position in out['positions']:
            position['weight'] = str(number(position['value']) / total) if total > 0 and not out['issues'] else None
    out['portfolio_nav'] = deepcopy(selected['portfolio_nav'])
    out['portfolio_nav']['reason'] = 'COMPARISON_USES_AUTHORIZED_CASH_ASSUMPTIONS_AND_DATED_PRICES__NET_NAV_NOT_ATTESTED'
    out['output_digest'] = digest(out)
    return out
