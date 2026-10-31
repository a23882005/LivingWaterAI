"""Replay original Work6 and conserve only amounts actually produced natively.

Pending stock/bond decisions remain uncounted, never zero-filled. This check
cannot promote independent analyses into a complete or jointly executable run.
"""
from copy import deepcopy
from family_input import digest
from funding_guard import check_aggregate, FundingError
from runtime_loader import load_c_module


def build(root, request, report):
    funding = report.get('native_funding_advice')
    if funding is None:
        return None
    identity = {'client_id': request['client_id'], 'run_id': request['run_id'],
                'owner': request['owner'],
                'source_db_sha256': request['client_snapshot']['payload']['source_sha256']}
    for key, value in identity.items():
        if report.get(key) != value:
            raise PermissionError('ACCOUNT_FUNDING_SOURCE_IDENTITY_MISMATCH:' + key)
    positions = {p['instrument_id']: p for p in report['analysis_result']['positions']}
    if len(positions) != len(report['analysis_result']['positions']) or set(funding['items']) != set(positions):
        raise PermissionError('ACCOUNT_FUNDING_COVERAGE_MISMATCH')
    if len({p['symbol'] for p in positions.values()}) != len(positions):
        # Different registry keys do not make repeated single-asset native
        # scenarios independent claims. An explicit lot merge is upstream work.
        raise PermissionError('ACCOUNT_FUNDING_DUPLICATE_NATIVE_ASSET')
    bond = report.get('native_bond_source') or {}
    out = {'schema_version': 'Family.W8.AccountFundingCheck.v1', **deepcopy(identity),
           'status': 'SOURCE_INCOMPLETE', 'adapter_checks': {}, 'claims': [],
           'unresolved_decisions': [], 'known_claims_budget_check': None,
           'conservation_status': 'BLOCKED_MISSING_NATIVE_DECISIONS',
           'coverage': {'requested': len(positions), 'stock_adapters_checked': 0,
                        'native_amounts_counted': 0, 'unresolved_native_decisions': 0},
           'cash_source': deepcopy(report.get('cash_trial')),
           'new_external_money': funding['new_external_money'],
           'physical_bond_positions': deepcopy(bond.get('physical_holdings', {})),
           'sgov_role_sources': deepcopy(bond.get('sgov_role_source_rows', {})),
           'sgov_role_accounting': deepcopy(report.get('sgov_role_source')),
           'sgov_role_policy': deepcopy(report.get('bond_policy_audit')),
           'physical_sgov_included_in_available_cash': False,
           'target_or_historical_sgov_amounts_used_as_current_cash': False,
           'order_source': deepcopy(report.get('order_source')),
           'full_native_canonical_complete': False, 'joint_execution_authorized': False,
           'call_trace': [], 'issues': [], 'trade_action': 'NO_TRADE'}
    w6 = load_c_module(root, 6)
    cash = None
    for iid, item in funding['items'].items():
        row = positions[iid]
        if (item.get('owner') != request['owner'] or item.get('run_id') != request['run_id']
            or item.get('source_db_sha256') != identity['source_db_sha256']
            or item.get('symbol') != row['symbol']):
            raise PermissionError('ACCOUNT_FUNDING_COMPONENT_IDENTITY_MISMATCH')
        if 'work4_result' in item and bond.get('adapter_result') is not None:
            stock = item['stock_request']
            if stock['work3_handoff'] != load_c_module(root, 3).build_context_handoff(item['work3_input']):
                raise PermissionError('ACCOUNT_FUNDING_WORK3_REPLAY_MISMATCH')
            if item['work4_result'] != load_c_module(root, 4).build_v82_runtime_input(stock):
                raise PermissionError('ACCOUNT_FUNDING_WORK4_REPLAY_MISMATCH')
            native_request = {'contract_name': w6.INPUT_CONTRACT_NAME,
                'contract_version': w6.INPUT_CONTRACT_VERSION, 'baseline_id': w6.BASELINE_ID,
                'run_id': request['run_id'], 'work3_handoff': stock['work3_handoff'],
                'c7_funding_context': stock['c7_funding_context'],
                'work4_adapter_result': item['work4_result'],
                'work5_adapter_result': bond['adapter_result']}
            try:
                native = w6.validate_funding_account_isolation(native_request)
                candidate = native['cash_eligibility']
                if cash is not None and candidate != cash:
                    raise PermissionError('ACCOUNT_FUNDING_SHARED_CASH_CONFLICT')
                cash = deepcopy(candidate)
                out['adapter_checks'][iid] = {'status': 'PASSED', 'native_work6': native,
                                             'input_digest': digest(native_request)}
                out['call_trace'].append({'instrument_id': iid,
                    'function': 'C8C9.Work6.validate_funding_account_isolation'})
            except ValueError as error:
                out['adapter_checks'][iid] = {'status': 'REJECTED',
                    'code': getattr(error, 'code', type(error).__name__), 'reason': str(error)}
                out['issues'].append({'instrument_id': iid, 'code': 'NATIVE_WORK6_REJECTED',
                                      'field_path': 'adapter_checks.' + iid})
        adapter_passed=out['adapter_checks'].get(iid,{}).get('status')=='PASSED'
        if item['status'] == 'CASH_TRIAL_ADVICE_COMPUTED' and adapter_passed:
            amount = item['native_plan'].get('execution_amount')
            if amount is not None:
                out['claims'].append({'claim_id': 'V82:' + iid, 'owner': deepcopy(request['owner']),
                    'run_id': request['run_id'], 'asset_class': 'EQUITY', 'amount': amount,
                    'asset_id': row['symbol'], 'source_engine': 'V82',
                    'source_reference': 'native_funding_advice.items.' + iid + '.native_plan'})
                continue
        out['unresolved_decisions'].append({'instrument_id': iid, 'symbol': row['symbol'],
            'native_status': item['status'], 'amount': None,
            'funding_adapter_status':out['adapter_checks'].get(iid,{}).get('status'),
            'component_issues':deepcopy(item.get('issues',[])),
            'mode_reason_codes':deepcopy(row.get('current_analysis',{}).get('current_judgment',{}).get('reason_codes',[])),
            'formal_stage_unknown_fields':deepcopy(row.get('formal_conclusion',{}).get('stage_required_unknown_fields',[])),
            'field_path': ('native_bond_source.canonical_result' if item['status'] == 'BOND_DELEGATED_TO_V75'
                           else 'native_funding_advice.items.' + iid + '.native_plan'),
            'missing_amount_replaced_by_zero': False})
    out['coverage'].update(stock_adapters_checked=len(out['adapter_checks']),
        native_amounts_counted=len(out['claims']),
        unresolved_native_decisions=len(out['unresolved_decisions']))
    if cash is not None:
        try:
            aggregate = check_aggregate(owner=request['owner'], run_id=request['run_id'],
                available=cash['available'], equity_budget=cash['equity_executable_budget'],
                bond_budget=cash['bond_executable_budget'], claims=out['claims'])
            out['known_claims_budget_check'] = {'status': 'PASSED', 'result': aggregate,
                'scope': 'ONLY_ENUMERATED_NATIVE_AMOUNTS__UNRESOLVED_DECISIONS_EXCLUDED'}
            out['status'] = ('ADAPTER_CHECKS_REJECTED' if out['issues']
                             else 'NATIVE_ACCOUNT_FUNDING_CHECKED_WITH_GAPS')
        except FundingError as error:
            out['status'] = 'BUDGET_REJECTED'
            out['known_claims_budget_check'] = {'status': 'REJECTED', 'reason': str(error)}
            out['issues'].append({'code': str(error), 'field_path': 'claims'})
        out['call_trace'].append({'function': 'W5.check_aggregate:enumerated_actual_native_amounts_only'})
    else:
        out['issues'].append({'code': 'WORK4_WORK5_ACCOUNT_FUNDING_SOURCE_REQUIRED',
                              'field_path': 'native_stock_and_bond_adapters'})
    # Repeated adapter observations attest one shared pool, not N balances.
    out['shared_cash_ledger'] = {'schema_version':'Family.W8.SharedCashLedger.v1',
        'owner':deepcopy(request['owner']),'run_id':request['run_id'],
        'cash_basis':'AVAILABLE','shared_cash_source_count':1 if cash is not None else 0,
        'adapter_observation_count':sum(r['status']=='PASSED' for r in out['adapter_checks'].values()),
        'shared_cash_fingerprint':digest(cash) if cash is not None else None,
        'available_once':cash['available'] if cash is not None else None,
        'equity_budget_once':cash['equity_executable_budget'] if cash is not None else None,
        'bond_budget_once':cash['bond_executable_budget'] if cash is not None else None,
        'known_claims':deepcopy(out['claims']),
        'known_claims_budget_check':deepcopy(out['known_claims_budget_check']),
        'unresolved_decisions':deepcopy(out['unresolved_decisions']),
        'physical_sgov_is_cash':False,'sgov_roles_added_to_physical_value':False,
        'new_external_money_added_again':False,'unknown_amounts_counted_as_zero':False,
        'scope':'ONE_SHARED_ACCOUNT_POOL__ENUMERATED_KNOWN_NATIVE_AMOUNTS_ONLY',
        'joint_execution_authorized':False,'trade_action':'NO_TRADE'}
    out['output_digest'] = digest(out)
    return out


def validate(root, request, report):
    if report.get('account_funding_check') != build(root, request, report):
        raise PermissionError('ACCOUNT_FUNDING_CHECK_REPLAY_MISMATCH')
