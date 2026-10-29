"""Produce a real same-run C Work6/Work7 result, including original refusals.

Long-term approval is retained as its own source. It never confirms a new
tactical proposal. A source section being present does not mean C7 is ready.
"""
from copy import deepcopy
from decimal import Decimal

from family_input import digest
from configuration_source import benchmark_source, run_work6_engine
from c7_engine import run_c7_engine
from current_allocation_source import build as current_allocation
from deployment_readiness import c7_bucket_preflight


def current_sgov_roles(roles, physical_value, reference_value):
    bond = Decimal(roles['sgov_bond_bucket_amount']['amount'])
    dry = Decimal(roles['sgov_dry_powder_bucket_amount']['amount'])
    if bond < 0 or dry < 0 or bond + dry != Decimal(physical_value):
        raise PermissionError('C7_CURRENT_SGOV_ROLE_VALUE_MISMATCH')
    if bond == 0:
        return [('SGOV_BOND', 'bond ETF', Decimal(0)), ('SGOV_DRY', 'cash', reference_value)]
    if dry == 0:
        return [('SGOV_BOND', 'bond ETF', reference_value), ('SGOV_DRY', 'cash', Decimal(0))]
    raise ValueError('C7_CURRENT_MIXED_SGOV_ROLE_QUANTITIES_REQUIRED')


def metric(value, unit, at, refs, *, quality='OK', freshness='UNKNOWN'):
    return {'value_state': 'KNOWN' if value is not None else 'UNKNOWN',
        'value': float(value) if value is not None else None, 'unit': unit, 'as_of': at,
        'data_quality': quality if value is not None else 'UNKNOWN', 'freshness': freshness,
        'issue_codes': [], 'source_reference_ids': list(refs), 'source_native_status': None}


def money(value, currency, at, refs, *, quality='OK'):
    return {'value_state': 'KNOWN' if value is not None else 'UNKNOWN',
        'amount': float(value) if value is not None else None, 'currency': currency, 'as_of': at,
        'data_quality': quality if value is not None else 'UNKNOWN', 'freshness': 'UNKNOWN',
        'issue_codes': [], 'source_reference_ids': list(refs)}


def reference(sid, kind, owner, value, at, *, quality='OK', freshness='UNKNOWN'):
    return {'source_id': sid, 'source_kind': kind, 'owner': owner,
        'source_reference': sid + ':' + digest(value), 'source_fingerprint': digest(value),
        'source_fingerprint_algorithm': 'SHA256', 'source_version': '1.0',
        'as_of': at, 'retrieved_at': None, 'data_quality': quality, 'freshness': freshness,
        'issue_codes': [], 'source_native_status': None, 'notes': None}


def extend(root, request, analysis, prepared, context, sources):
    out = deepcopy(sources)
    current = current_allocation(request, analysis, prepared, context)
    out['component_results']['current_allocation'] = current
    portfolio = None
    if context.get('portfolio_market_source') is not None:
        from portfolio_current_source import build as portfolio_current
        portfolio = portfolio_current(request, analysis, current, out, context['portfolio_market_source'])
        out['component_results']['portfolio_current_comparison'] = portfolio
    descriptor = context.get('configuration_benchmark_source')
    if descriptor is None:
        out['source_validation_issues'].append({'source_section': 'trusted_context.c7_source',
            'code': 'CONFIGURATION_BENCHMARK_SOURCE_REQUIRED',
            'field_path': 'configuration_benchmark_source'})
        return out
    benchmark = benchmark_source(root, descriptor, request['evaluation_at'])
    preflight = c7_bucket_preflight(root, request, analysis, context)
    at = request['evaluation_at']; currency = request['owner']['currency']
    target = request['confirmed_target']; projection = analysis['native_target_source']
    base = Decimal(projection['denominator']['amount'])
    comparison_ready = portfolio is not None and portfolio['denominator']['state'] == 'KNOWN'
    if comparison_ready:
        base = Decimal(portfolio['denominator']['value'])
    comparison_quality = 'FALLBACK_USED' if comparison_ready else 'OK'
    target_ref = 'SRC_APPROVED_LONG_TERM'; current_ref = 'SRC_CURRENT_SCOPE'; v70_ref = 'SRC_V70'
    tactical = next(r['current_analysis']['v70_tactical_budget'] for r in analysis['analysis_result']['positions']
                    if r['current_analysis'].get('v70_tactical_budget'))
    allocation = tactical['allocation']; raw = out['trusted_context']['v70_source']['context']
    freshness = analysis.get('native_source_freshness', {}).get('v70', {}).get('state', 'UNKNOWN')
    v70 = {'value_state': 'KNOWN', 'run_id': request['run_id'],
        'upstream_v70_snapshot_id': raw['upstream_v70_snapshot_id'],
        'snapshot_as_of': raw['snapshot_as_of'], 'data_quality': raw['payload']['data_quality'],
        'freshness': freshness, 'issue_codes': list(raw['payload']['issue_codes']),
        'source_reference_ids': [v70_ref], 'life_stage_code': allocation['lifeStageCode'],
        'life_stage_label': allocation['lifeStageLabel']}
    for field, key in [('strategic_stock_weight', 'S0'), ('strategic_bond_weight', 'B0'),
                       ('tactical_tilt_t', 'T'), ('stock_tactical_weight', 'sTot'),
                       ('bond_tactical_weight', 'bTot'), ('v70_original_dry_powder_weight', 'cTot')]:
        v70[field] = metric(Decimal(str(allocation[key])) / 100, 'portfolio_weight',
                             raw['snapshot_as_of'], [v70_ref], freshness=freshness)
    for field in ('stock_tactical_amount', 'bond_tactical_amount', 'v70_original_dry_powder_amount'):
        v70[field] = money(raw['payload'][field], currency, raw['snapshot_as_of'], [v70_ref],
                           quality=raw['payload']['data_quality'])
    mappings = {r['instrument_id']: r for r in preflight['mapping']}
    native_products = {r['symbol']: r['native_product_identity'] for r in analysis['analysis_result']['positions']}
    currency_by_symbol = {}
    for instrument in request['client_snapshot']['payload']['tables']['portfolio_instrument']:
        if instrument.get('quote_currency'):
            currency_by_symbol[instrument.get('ticker')] = instrument['quote_currency']
    lines = []
    for row in target['payload']['draft']['target_lines']:
        weight = Decimal(str(row['weight']['value'])); mapping = mappings[row['instrument_id']]
        kind = {'STOCK': 'equity exposure', 'BOND': 'bond exposure',
                'V70_ORIGINAL_DRY_POWDER': 'cash'}.get(mapping['bucket'], 'UNKNOWN')
        if mapping['bucket'] == 'STOCK':
            product_type = native_products.get(row['ticker'], {}).get('asset_type') or row.get('asset_type', '')
            if product_type == 'INDIVIDUAL_STOCK': kind = 'equity individual stock'
            elif 'ETF' in product_type: kind = 'equity ETF'
        native_id = projection['source_to_native'][row['instrument_id']]
        lines.append({'instrument_id': native_id, 'ticker': row['ticker'],
            'display_name': row.get('display_name'), 'asset_type': kind, 'market': None,
            'base_currency': currency_by_symbol.get(row['ticker']), 'value_state': 'KNOWN',
            'weight': metric(weight, 'portfolio_weight', at, [target_ref]),
            'portfolio_amount': money(base * weight, currency, at, [target_ref], quality=comparison_quality),
            'source_reference_ids': [target_ref]})
    proposal = {'allocation_id': 'APPROVED-BASE-PROJECTION:' + digest(target),
        'stage': 'PROPOSED', 'as_of': at, 'denominator': money(base, currency, at, [target_ref], quality=comparison_quality),
        'positions': lines, 'declared_total_weight': metric(sum(Decimal(str(r['weight']['value']))
            for r in lines), 'portfolio_weight', at, [target_ref]),
        'confirmation_status': 'PENDING', 'confirmed_at': None, 'confirmed_by': None,
        'source_reference_ids': [target_ref]}
    current_slot = {'value_state': 'UNKNOWN', 'snapshot': None, 'reason': current['portfolio_nav']['reason']}
    if comparison_ready:
        current_lines = []
        approved_by_symbol = {r['ticker']: r for r in lines}
        for position in portfolio['positions']:
            symbol = position['symbol']; value = Decimal(position['value'])
            approved = approved_by_symbol.get(symbol)
            kind = approved['asset_type'] if approved else 'UNKNOWN'
            product = native_products.get(symbol, {})
            if symbol is None:
                kind = 'cash'
            elif product.get('asset_type') == 'INDIVIDUAL_STOCK':
                kind = 'equity individual stock'
            elif product.get('engine_route', '').startswith('V82_'):
                kind = 'equity ETF'
            native_id = symbol or position['instrument_id']
            role_values = [(native_id, kind, value)]
            if symbol == 'SGOV' and {'SGOV_BOND', 'SGOV_DRY'}.issubset(set(projection['source_to_native'].values())):
                roles = analysis['sgov_role_source']['roles']
                role_values = current_sgov_roles(roles,
                    analysis['sgov_role_source']['physical']['valuation']['amount'], value)
            for iid, asset_type, role_value in role_values:
                current_lines.append({'instrument_id': iid, 'ticker': symbol, 'display_name': None,
                    'asset_type': asset_type, 'market': None,
                    'base_currency': currency_by_symbol.get(symbol) if symbol else currency,
                    'value_state': 'KNOWN',
                    'weight': metric(role_value / base, 'portfolio_weight', at, [current_ref], quality='FALLBACK_USED'),
                    'portfolio_amount': money(role_value, currency, at, [current_ref], quality=comparison_quality),
                    'source_reference_ids': [current_ref]})
        if len({r['instrument_id'] for r in current_lines}) != len(current_lines):
            raise PermissionError('C7_CURRENT_CROSS_ACCOUNT_INSTRUMENT_COLLISION')
        current_slot = {'value_state': 'KNOWN', 'reason': portfolio['scope'], 'snapshot': {
            'allocation_id': 'CURRENT-COMPARISON:' + portfolio['output_digest'], 'stage': 'CURRENT', 'as_of': at,
            'denominator': money(base, currency, at, [current_ref], quality=comparison_quality), 'positions': current_lines,
            'declared_total_weight': metric(1, 'portfolio_weight', at, [current_ref], quality='FALLBACK_USED'),
            'confirmation_status': 'NOT_APPLICABLE', 'confirmed_at': None, 'confirmed_by': None,
            'source_reference_ids': [current_ref]}}
    # Historical approved capital and a selected-account asset reference have
    # different scope. No manufactured 100% Current snapshot or signing event.
    canonical = {'contract_name': 'LivingWaterAI.C.CanonicalInput', 'contract_version': 'C-W1-v1.0.1',
        'identity': {k: request[k] for k in ('client_id', 'run_id', 'request_id')},
        'decision_phase': 'PROPOSAL_REVIEW', 'capital_context': {
            'total_investment_amount': money(base, currency, at, [target_ref], quality=comparison_quality), 'base_currency': currency,
            'fx_metadata': {'value_state': 'UNKNOWN', 'as_of': None, 'rates': [], 'source_reference_ids': []}},
        'allocations': {'current_allocation': current_slot,
            'proposed_allocation': {'value_state': 'KNOWN', 'snapshot': proposal, 'reason':
                'Existing long-term weights/base projected for review; no tactical approval implied'},
            'final_target': {'value_state': 'NONE', 'snapshot': None,
                'reason': 'No new same-run Work6 confirmation has been created'}},
        'v70_asset_framework': v70, 'benchmark_reference': benchmark['reference'],
        'source_references': benchmark['source_references'] + [
            reference(target_ref, 'CLIENT_PROJECT', 'CLIENT_PROJECT', target, at),
            reference(current_ref, 'SYSTEM_DERIVED', 'C_INTEGRATION', portfolio or current, at,
                      quality='FALLBACK_USED' if comparison_ready else 'INSUFFICIENT'),
            reference(v70_ref, 'V70_SNAPSHOT', 'V70', raw, raw['snapshot_as_of'],
                      quality=raw['payload']['data_quality'], freshness=freshness)],
        'issues': [], 'traceability': []}
    canonical['identity']['portfolio_id'] = 'GLOBAL-PORTFOLIO:' + request['client_id']
    if comparison_ready and portfolio.get('fx_observation'):
        fx = portfolio['fx_observation']
        canonical['capital_context']['fx_metadata'] = {'value_state': 'KNOWN', 'as_of': fx['as_of'],
            'source_reference_ids': [current_ref], 'rates': [{
                'pair': fx['base_currency'] + '/' + fx['quote_currency'],
                'rate': metric(fx['quote_per_base'], 'quote_per_base', fx['as_of'], [current_ref])}]}
    adjustment = {'contract_name': 'LivingWaterAI.C.Work6.AdjustmentRequest',
        'contract_version': 'C-W6-v1.0.0', 'adjustment_id': 'SOURCE-REVIEW:' + request['run_id'],
        'requested_change_types': ['REVIEW_ONLY'], 'weight_overrides': [], 'preference_decisions': [],
        'confirmation': {'action': 'KEEP_PENDING', 'client_explicit_decision': 'UNKNOWN',
            'confirmed_at': None, 'confirmed_by': None, 'source_reference_ids': []},
        'radar_scores': [], 'source_references': [], 'source_reference_ids': [target_ref, current_ref, v70_ref]}
    evidence = target['payload']['confirmation_evidence']
    if (comparison_ready and evidence.get('action') == 'READ_EXISTING_APPROVAL'
            and evidence.get('confirmed_at') and evidence.get('confirmed_by')):
        # Transport the already-bound approval of these exact long-term
        # weights. No new tactical weights, timestamp or signing event exists.
        adjustment['confirmation'] = {'action': 'CONFIRM', 'client_explicit_decision': 'TRUE',
            'confirmed_at': evidence['confirmed_at'], 'confirmed_by': evidence['confirmed_by'],
            'source_reference_ids': [target_ref]}
    work6_source = {'schema_version': 'Family.W5.Work6Source.v1', 'canonical_input': canonical,
        'adjustment_request': adjustment, 'benchmark_source': deepcopy(descriptor), 'evaluated_at': at}
    work6 = run_work6_engine(root, work6_source)
    final = work6['result']['final_target']
    if final['value_state'] == 'KNOWN':
        approved_weights = {r['instrument_id']: Decimal(str(r['weight']['value'])) for r in lines}
        transported = {r['instrument_id']: Decimal(str(r['weight']['value'])) for r in final['snapshot']['positions']}
        if (set(approved_weights) != set(transported)
                or any(abs(approved_weights[k] - transported[k]) > Decimal('1e-12') for k in approved_weights)):
            raise PermissionError('C7_EXISTING_APPROVAL_WEIGHTS_CHANGED')
    source = {'schema_version': 'Family.W5.C7Source.v1', 'producer': 'Family.W8.OriginalConfigurationSources',
        'version': '1.0', 'source_reference': 'VERIFIED-ANALYSIS:' + analysis['report_digest'],
        'family_owner': deepcopy(request['owner']), 'canonical_input': canonical,
        'work6_result': work6['result'], 'work6_source': work6_source,
        'funding_context': deepcopy(out['native_bundle']['stock_request']['c7_funding_context']),
        'evaluated_at': at,
        'comparison_context': {'scope': portfolio['scope'] if portfolio else current['scope'],
            'mode': 'CASH_ZERO_SIMULATION',
            'source_basis': 'DATED_REFERENCE_COMPOSITE__RESTATED_CURRENT_VINTAGE_NOT_PIT',
            'cash_assumptions': deepcopy(portfolio['cash_assumptions']) if portfolio else [],
            'portfolio_nav': deepcopy(portfolio['portfolio_nav'] if portfolio else current['portfolio_nav']),
            'approval_source': deepcopy(target), 'new_confirmation_created': False,
            'tactical_target_approved': False, 'not_authorization_for_tactical_execution': True,
            'holding_policy_state': 'NO_NEW_PREFERENCE_DECISIONS_INFERRED__W1_POLICY_BINDING_STILL_REQUIRED',
            'original_approved_money_projection': deepcopy(projection['denominator'])}}
    computed = run_c7_engine(root, source)
    from deployment_progress_review import build as build_progress_review
    source['continuation_review'] = build_progress_review(root, request, analysis,
        work6['result'], computed['result'], [*out['native_bundle'], 'asset_framework'])
    computed = run_c7_engine(root, source)
    out['native_bundle']['asset_framework'] = computed['result']
    out['trusted_context']['c7_source'] = source
    out['component_results']['configuration'] = {'work6': work6, 'c7': computed,
        'approval_identity': {'source_digest': digest(target), 'scope': 'EXISTING_LONG_TERM_APPROVAL',
            'source_confirmation_evidence': deepcopy(target['payload']['confirmation_evidence']),
            'new_confirmation_created': False, 'tactical_target_approved': False,
            'original_approved_money_projection': deepcopy(projection['denominator']),
            'comparison_amounts_are_not_new_approved_budgets': True},
        'scope_gaps': deepcopy(current['portfolio_nav']), 'bucket_preflight': preflight}
    out['context_bindings']['c7_source'] = {'status': 'ORIGINAL_WORK6_AND_C7_EXECUTED',
        'source_digest': digest(source), 'work6_source_digest': digest(work6_source),
        'framework_status': computed['result']['status'],
        'qualified_for_native_dispatch': computed['result']['status'] == 'READY_FOR_PM_GATE'}
    out['context_call_trace'] += work6['call_trace'] + computed['call_trace']
    return out
