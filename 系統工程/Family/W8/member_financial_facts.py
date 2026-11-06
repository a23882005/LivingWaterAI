"""Source-backed reported money and broker observations for the original C7 chain.

These facts retain their actual meaning: an Owner investment intention, a cash
report and a provider settled-cash observation are distinct. None of them is a
substitute for the existing complete reconciliation and funding contracts.
"""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from family_input import digest, read_snapshot
from member_market_source import time
from w1_portfolio_observations import major_amount

FIELDS = {
    ('CASH', 'reported_amount'): 'REPORTED_CASH',
    ('CASH', 'reported_cash'): 'REPORTED_CASH',
    ('CASH', 'owner_reported_amount'): 'REPORTED_CASH',
    ('CASH', 'reported_amount_minor'): 'REPORTED_CASH',
    ('CASH', 'owner_confirmed_investable_minor'): 'OWNER_INVESTMENT_INTENT',
    ('OWNER_SCREENSHOT_SOURCE', 'cash_balance'): 'REPORTED_CASH',
    ('OWNER_SCREENSHOT_SOURCE', 'total_cash_same_balance_not_additive'): 'REPORTED_CASH',
    ('W6_ACCEPTED_SOURCE', 'cash_usd_display'): 'REPORTED_CASH',
}


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('MEMBER_MONEY_NUMBER_REQUIRED')
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('MEMBER_MONEY_FINITE_NUMBER_REQUIRED')
    return str(n)


def reported_money(request):
    snapshot = request['client_snapshot']['payload']
    tables = snapshot['tables']; client = request['client_id']; cutoff = time(request['evaluation_at'])
    if (snapshot['client_id'] != client or snapshot['payload_digest'] != digest(tables)
            or request.get('trade_authorization') != 'NONE'
            or any(r.get('client_id', client) != client for rows in tables.values() for r in rows)):
        raise PermissionError('MEMBER_MONEY_MEMBER_SNAPSHOT_OR_TRADE_SCOPE')
    runs = {}
    for run in tables.get('portfolio_snapshot_run', []):
        if run.get('run_state') != 'SEALED' or run.get('source_kind') == 'USER_HYPOTHETICAL':
            continue
        stamps = [run.get(k) for k in ('as_of_utc', 'created_at_utc', 'sealed_at_utc', 'recorded_at_utc')]
        if not run.get('as_of_utc') or any(time(t) > cutoff for t in stamps if t):
            continue
        if run['run_id'] in runs and runs[run['run_id']] != run:
            raise ValueError('MEMBER_MONEY_RUN_CONFLICT')
        runs[run['run_id']] = run
    candidates = {}; excluded = []
    for row in tables.get('portfolio_snapshot_item', []):
        kind = FIELDS.get((row.get('domain_code'), row.get('field_key')))
        if kind is None or row.get('value_state') != 'KNOWN':
            continue
        run = runs.get(row.get('run_id'))
        if run is None or row.get('source_kind') == 'USER_HYPOTHETICAL':
            continue
        stamps = [row.get(k) for k in ('recorded_at_utc', 'created_at_utc', 'source_observed_at_utc')]
        if any(time(t) > cutoff for t in stamps if t):
            excluded.append(dict(reason='ORIGINAL_ROW_AFTER_CUTOFF', original_row=deepcopy(row)))
            continue
        currency = row.get('currency_code')
        if not currency or not row.get('source_reference'):
            excluded.append(dict(reason='ORIGINAL_CURRENCY_OR_REFERENCE_REQUIRED', original_row=deepcopy(row)))
            continue
        minor = row['field_key'].endswith('_minor')
        if minor and (row.get('value_type') != 'INTEGER_MINOR' or row.get('unit') != 'MINOR'):
            raise ValueError('MEMBER_MONEY_EXPLICIT_MINOR_UNIT_REQUIRED')
        amount = major_amount(row.get('value_integer_minor')) if minor else number(row.get('value_text'))
        if amount is None:
            raise ValueError('MEMBER_MONEY_KNOWN_AMOUNT_MISSING')
        confirmed = (kind == 'OWNER_INVESTMENT_INTENT' and row.get('source_kind') == 'OWNER_VERIFIED'
                     and run.get('source_kind') == 'OWNER_VERIFIED')
        state = 'OWNER_CONFIRMED_INTENT' if confirmed else 'REPORTED_UNQUALIFIED'
        item = dict(fact_kind=kind, value_state='KNOWN', amount=amount, currency=currency,
                    entity_key=row.get('entity_key'), qualification=state,
                    as_of=row.get('source_observed_at_utc'),
                    available_at=max((t for t in [run['as_of_utc'], run.get('sealed_at_utc'),
                                     row.get('recorded_at_utc')] if t), key=time),
                    source_run=deepcopy(run), source_rows=[deepcopy(row)],
                    available_cash=None, authorized_incremental_amount=None,
                    settlement_qualified=False)
        key = (kind, row.get('entity_key'), currency)
        rank = (time(run['as_of_utc']), run.get('version_no', 0))
        old = candidates.get(key)
        if old and rank == old[0]:
            previous = old[1]
            if (previous['source_run']['run_id'] != run['run_id']
                    or Decimal(previous['amount']) != Decimal(amount)
                    or previous['qualification'] != state or previous['as_of'] != item['as_of']):
                raise ValueError('MEMBER_MONEY_SAME_VINTAGE_CONFLICT')
            if row not in previous['source_rows']:
                previous['source_rows'].append(deepcopy(row))
                previous['available_at'] = max(previous['available_at'], item['available_at'], key=time)
        elif old is None or rank > old[0]:
            candidates[key] = (rank, item)
    facts = [candidates[k][1] for k in sorted(candidates, key=str)]
    for fact in facts:
        fact['source_rows'].sort(key=digest)
        fact['fact_digest'] = digest(fact)
    return dict(facts=facts, excluded=excluded, cash_sources_proven_nonoverlapping=False,
                aggregate_reported_cash=None, qualified_available_cash=None,
                interpretation='REPORTED_CASH_AND_OWNER_INTENTION_ARE_NOT_SETTLED_DEPLOYABLE_CASH')


def broker_observations(request, descriptor):
    if descriptor is None:
        return None
    from broker_snapshot_source import pinned, response
    manifest = pinned(descriptor); snapshot = request['client_snapshot']['payload']
    if (manifest.get('schema_version') != 'Family.W8.MemberBrokerObservations.v1'
            or any(manifest.get(k) != request[k] for k in ('client_id', 'run_id', 'evaluation_at'))
            or manifest.get('source_db_sha256') != snapshot['source_sha256']
            or manifest.get('snapshot_digest') != snapshot['payload_digest']
            or manifest.get('target_version') != request['confirmed_target']['target_version']
            or not manifest.get('source_reference')
            or time(manifest['available_at']) > time(request['evaluation_at'])):
        raise PermissionError('MEMBER_BROKER_OBSERVATIONS_SCOPE_OR_TIME')
    calls = {}; failures = []; references = []
    methods = dict(positions='get_account_positions', balances='get_account_balances',
                   summary='get_account_summary', orders='get_account_orders', trades='get_account_trades')
    pm_quality=None
    if manifest.get('pm_document_source') is not None:
        from pm_source_document import account
        if manifest.get('calls') or manifest.get('member_scope')!='Joseph':
            raise PermissionError('MEMBER_PM_BROKER_SINGLE_ORIGINAL_AND_RECIPIENT_REQUIRED')
        # A re-labelled manifest is not proof of the private document's recipient.
        # Replay the same sealed W1 DB before reading any private account rows.
        # This verifies household routing only, not broker ownership or funding.
        recipient=manifest.get('recipient_snapshot_source')
        if (not isinstance(recipient,dict) or not recipient.get('local_path')
            or recipient.get('sha256')!=snapshot['source_sha256']):
            raise PermissionError('MEMBER_PM_BROKER_RECIPIENT_SNAPSHOT_REQUIRED')
        actual=read_snapshot(Path(recipient['local_path']),expected_client_id=request['client_id'])
        if (actual!=snapshot or actual['source_sha256']!=recipient['sha256']
            or actual['identity'].get('family_alias')!='Joseph'):
            raise PermissionError('MEMBER_PM_BROKER_ORIGINAL_RECIPIENT_MISMATCH')
        calls,original=account(manifest['pm_document_source'],manifest['available_at'])
        references=[deepcopy(manifest['pm_document_source'])]
        positions=calls['positions'].get('positions');balances=calls['balances'].get('balances')
        if not isinstance(positions,list) or not isinstance(balances,list):
            raise ValueError('MEMBER_PM_BROKER_ORIGINAL_POSITIONS_AND_BALANCES_REQUIRED')
        gross=calls['summary'].get('gross_position_value');nav=calls['summary'].get('net_liquidation')
        selected=[b for b in balances if b.get('currency')=='USD']
        if len(selected)!=1:raise ValueError('MEMBER_BROKER_CASH_CURRENCY_AMBIGUOUS')
        contract_ids=[]
        for row in positions:
            contract=row.get('contract_id')
            if (type(contract) is not int or contract<=0 or row.get('currency')!='USD'
                or row.get('asset_class')!='STK' or not row.get('contract_description')):
                raise PermissionError('MEMBER_PM_BROKER_POSITION_IDENTITY_OR_CURRENCY')
            contract_ids.append(contract)
            for key in ('position','market_price','market_value'):number(row.get(key))
        if len(contract_ids)!=len(set(contract_ids)):raise ValueError('MEMBER_PM_BROKER_DUPLICATE_CONTRACT')
        value=sum((Decimal(number(r['market_value'])) for r in positions),Decimal(0))
        balance=selected[0];cash=Decimal(number(balance['settled_cash']))
        pm_quality=dict(original_captured_at=original['retrieved_at_utc'],client_scope=original['client_scope'],
            original_finance_eligibility=original['finance_eligibility'],
            position_market_value_sum=str(value),broker_gross_position_value=number(gross),
            position_sum_minus_broker_gross=str(value-Decimal(number(gross))),
            broker_NAV_observation=number(nav),position_sum_plus_cash_minus_NAV=str(value+Decimal(number(balance['cash_balance']))-Decimal(number(nav))),
            cash_total_observation=number(balance['cash_balance']),settled_cash_observation=str(cash),
            negative_settled_cash=cash<0,BASE_is_not_additional_account=True,
            source_numbers_preserved_as_decimal_spellings=True,qualifies_complete_portfolio_NAV=False,
            quantities_adjusted_again=False,orders_complete=False,owner_and_same_cutoff_qualified=False,
            SGOV_role_confirmation_created=False,old_database_positions_overwritten=False)
        observed_symbols={r['contract_description'].split()[0] for r in positions}
        trades=calls['trades'].get('trades');orders=calls['orders'].get('orders')
        if not isinstance(trades,list) or not isinstance(orders,list):raise ValueError('MEMBER_PM_BROKER_ORIGINAL_TRADES_AND_ORDERS_REQUIRED')
        pm_quality['trade_symbols_without_exact_position_symbol']=sorted({r['symbol'] for r in trades}-observed_symbols)
        pm_quality['trade_listing_aliases_merged']=False
    for name, item in manifest.get('calls', {}).items():
        if name not in methods:
            raise PermissionError('MEMBER_BROKER_OBSERVATION_METHOD_REQUIRED')
        captured = time(item['retrieved_at'])
        if captured > time(manifest['available_at']):
            raise PermissionError('MEMBER_BROKER_OBSERVATION_FUTURE_CAPTURE')
        original = pinned(item)
        if (original.get('method') != methods[name] or original.get('arguments') != item.get('arguments')
                or time(original['retrieved_at'].replace(' UTC', '+00:00')) != captured):
            raise PermissionError('MEMBER_BROKER_OBSERVATION_CALL_LINEAGE')
        references.append(deepcopy(item))
        try:
            calls[name] = response(item, methods[name])
        except ValueError as error:
            failures.append(dict(method=methods[name], reason_code=str(error)))
    balances = calls.get('balances', {}).get('balances')
    cash = []
    if isinstance(balances, list):
        currencies = set()
        for row in balances:
            currency = row.get('currency')
            if currency == 'BASE':
                continue  # The provider's BASE display is not another balance.
            if not currency or currency in currencies:
                raise ValueError('MEMBER_BROKER_CASH_CURRENCY_AMBIGUOUS')
            currencies.add(currency)
            cash.append(dict(currency=currency, reported_total=number(row['cash_balance']),
                             broker_settled_observation=number(row['settled_cash']),
                             qualification='BROKER_OBSERVATION_OWNER_AND_CUTOFF_UNQUALIFIED',
                             available_cash=None))
    positions = calls.get('positions', {}).get('positions')
    orders = calls.get('orders', {}).get('orders')
    trades = calls.get('trades', {}).get('trades')
    unresolved = [deepcopy(r) for r in orders or [] if r.get('order_status') == 'REPLACED']
    result=dict(source_descriptor=deepcopy(descriptor), original_call_references=references,
                owner_binding='UNVERIFIED_CONNECTION_OBSERVATION', provider_snapshot_as_of=None,
                capture_is_not_provider_snapshot_time=True, cash_observations=cash,
                positions=deepcopy(positions), orders=deepcopy(orders), trades=deepcopy(trades),
                trade_query=({'period':'DAYS_30'} if pm_quality is not None else
                    deepcopy(manifest.get('calls', {}).get('trades', {}).get('arguments'))),
                summary_observations=deepcopy(calls.get('summary')), provider_failures=failures,
                replaced_orders_requiring_successor_or_release=unresolved,
                pending_exposure=None, orders_complete=False, complete_NAV=None,
                qualified_available_cash=None, margin_funds_used_as_cash=False,
                replacement_release_inferred=False)
    if pm_quality is not None:result['PM_document_reconciliation_quality']=pm_quality
    return result


def produce(request, normalized, broker_source=None):
    if (any(normalized.get(k) != request[k] for k in ('client_id', 'run_id', 'evaluation_at'))
            or normalized.get('source_db_sha256') != request['client_snapshot']['payload']['source_sha256']):
        raise PermissionError('MEMBER_FINANCIAL_FACTS_SOURCE_BINDING')
    target = request['confirmed_target']
    out = dict(schema_version='Family.W8.MemberFinancialFacts.v1',
               **{k: request[k] for k in ('client_id', 'run_id', 'evaluation_at')},
               source_db_sha256=normalized['source_db_sha256'],
               reported_money=reported_money(request),
               original_account_cash_observations=deepcopy(normalized.get('account_cash_observations', [])),
               broker_observations=broker_observations(request, broker_source),
               target_selection=dict(source_kind=target.get('source_kind'), target_version=target['target_version'],
                    complete_allocation=target.get('complete_allocation'),
                    owner_selection_decision=deepcopy(target.get('owner_selection_decision'))),
               sgov=deepcopy(normalized.get('sgov')),
               local_planning_ledger=deepcopy(normalized.get('planning_ledger')),
               broker_orders_inferred_empty_from_local_ledger=False,
               qualified_current_NAV=None, qualified_available_cash=None,
               qualified_incremental_authorization=None, financial_cycle_initialized=False,
               trade_authorization='NONE', trade_action='NO_TRADE')
    out['digest'] = digest(out)
    return out
