"""Normalize existing W1 observations without asserting financial completeness.

One dated/versioned cash row supplies every cash field. Reported amounts,
payables, settlement and investment authorization remain separate facts.
The original W5 account reader alone qualifies an explicit owner binding.
"""
from copy import deepcopy
from decimal import Decimal, localcontext

from family_input import digest
from family_boundary import bind_owner, BoundaryError
from member_market_source import time


MINOR_COLUMNS = {
    'reported_cash': 'reported_cash_minor',
    'settled_cash': 'normalized_settled_minor',
    'pending_receivable': 'pending_receivable_minor',
    'pending_payable': 'pending_payable_minor',
    'reserved_cash': 'reserved_minor',
}


def major_amount(value):
    if value is None:
        return None
    # W1 official_mutations.minor_units stores hundredths in INTEGER columns,
    # including TWD. No currency-dependent rounding or binary float conversion.
    if type(value) is not int:
        raise ValueError('C7_W1_INTEGER_MINOR_UNITS_REQUIRED')
    with localcontext() as numeric:
        numeric.prec = max(50, len(str(abs(value))) + 3)
        return format(Decimal(value) / 100, 'f')


def latest_rows(rows, keys, cutoff):
    """Select one complete original row per key; never coalesce its columns."""
    chosen = {}
    excluded = []
    for original in rows:
        row = deepcopy(original)
        at = row.get('as_of_utc')
        available = [row[k] for k in ('recorded_at_utc', 'created_at_utc', 'reconciled_at_utc') if row.get(k)]
        if at is None:
            excluded.append({'reason': 'ORIGINAL_OBSERVATION_TIME_REQUIRED', 'row': row})
            continue
        if time(at) > cutoff or any(time(t) > cutoff for t in available):
            excluded.append({'reason': 'ORIGINAL_ROW_AFTER_CUTOFF', 'row': row})
            continue
        version = row.get('version', 0)
        if type(version) is not int or version < 0:
            raise ValueError('C7_W1_ORIGINAL_VERSION_REQUIRED')
        key = tuple(row.get(k) for k in keys)
        rank = (time(at), version)
        old = chosen.get(key)
        if old and old[0] == rank and old[1] != row:
            raise ValueError('C7_W1_SAME_SNAPSHOT_CONFLICT')
        if old is None or rank > old[0]:
            chosen[key] = (rank, row)
    # Stable order makes this review reproducible regardless of SQL row order.
    return [chosen[k][1] for k in sorted(chosen, key=lambda k: tuple(str(v) for v in k))], excluded


def normalize(request):
    snapshot = request['client_snapshot']['payload']
    client = request['client_id']
    if snapshot.get('client_id', client) != client:
        raise PermissionError('C7_W1_OBSERVATION_CLIENT_MISMATCH')
    tables = snapshot['tables']
    cutoff = time(request['evaluation_at'])
    accounts = tables.get('portfolio_account', [])
    keys = [r['account_key'] for r in accounts]
    if len(keys) != len(set(keys)):
        raise ValueError('C7_W1_ACCOUNT_IDENTITY_CONFLICT')
    names = ('portfolio_account', 'account_ownership', 'account_broker_link',
             'funding_account_domain_link', 'cash_balance_snapshot', 'portfolio_position')
    for name in names:
        for row in tables.get(name, []):
            if row.get('client_id', client) != client or row.get('account_key') not in keys:
                raise PermissionError('C7_W1_OBSERVATION_ACCOUNT_MISMATCH:' + name)
    cash, excluded_cash = latest_rows(tables.get('cash_balance_snapshot', []),
                                     ('account_key', 'currency_code'), cutoff)
    positions, excluded_positions = latest_rows(tables.get('portfolio_position', []),
                                               ('account_key', 'instrument_key'), cutoff)
    normalized = []
    for account in sorted(accounts, key=lambda r: r['account_key']):
        aid = account['account_key']
        links = [r for r in tables.get('account_broker_link', [])
                 if r['account_key'] == aid and r.get('link_state') == 'ACTIVE']
        domains = [r for r in tables.get('funding_account_domain_link', [])
                   if r['account_key'] == aid and r.get('link_state') == 'VERIFIED'
                   and r.get('currency_code') == account.get('account_currency')]
        owner = {'client_id': client, 'account': aid, 'currency': account.get('account_currency'),
                 'broker': links[0].get('broker_key') if len(links) == 1 else None,
                 'funding_domain': domains[0].get('funding_domain_key') if len(domains) == 1 else None}
        missing = [k for k in ('broker', 'currency', 'funding_domain') if not owner[k]]
        qualification = None
        if not missing:
            try:
                # Document category analysis scope is deliberately not passed:
                # that scope does not prove an actual financial account.
                evidence_snapshot={**snapshot,'tables':{**tables,
                    **{k:tables.get(k,[]) for k in ('account_ownership','funding_domain')}}}
                bind_owner(evidence_snapshot, owner, cutoff)
                qualification = 'ORIGINAL_W5_OWNER_BINDING_PASSED'
            except BoundaryError as error:
                missing.append(error.issue['field_path'] + ':' + error.issue['code'])
        cash_observations = []
        for row in (r for r in cash if r['account_key'] == aid):
            cash_observations.append({
                'currency': row.get('currency_code'), 'as_of': row['as_of_utc'],
                'available_at': row.get('reconciled_at_utc'),
                'version': row.get('version'), 'original_row': deepcopy(row),
                'original_row_digest': digest(row), 'unit': 'currency_major', 'minor_unit_scale': 100,
                'amounts': {k: major_amount(row.get(column)) for k, column in MINOR_COLUMNS.items()},
                'reported_cash_basis': row.get('reported_cash_basis'),
                'data_state': row.get('data_state'), 'source_reference': row.get('source_reference'),
                'available_cash': None, 'authorized_incremental_amount': None,
                'qualified_funding': False,
            })
        normalized.append({'account_key': aid, 'original_account': deepcopy(account),
            'owner_candidate': owner, 'binding_qualification': qualification,
            'missing_binding_fields': missing,
            'positions': [deepcopy(r) for r in positions if r['account_key'] == aid],
            'cash_observations': cash_observations,
            'positions_complete': None, 'orders_complete': None, 'net_asset_value': None})
    return {'schema_version': 'Family.W8.W1PortfolioObservationReview.v1',
        'client_id': client, 'source_db_sha256': snapshot['source_sha256'],
        'target_version': request['confirmed_target']['target_version'],
        'evaluation_at': request['evaluation_at'], 'accounts': normalized,
        'excluded_cash_rows': excluded_cash, 'excluded_position_rows': excluded_positions,
        'qualified_account_count': sum(r['binding_qualification'] is not None for r in normalized),
        'complete_reconciliation_facts': False, 'qualified_funding': False,
        'missing_original_groups': ['complete_positions_prices_cash_debt_payables_at_one_cutoff',
            'complete_orders_fills_commitments_releases', 'protection_and_cap_confirmation',
            'cash_eligibility_and_incremental_authorization'],
        'trade_action': 'NO_TRADE'}
