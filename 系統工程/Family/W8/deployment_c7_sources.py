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


def metric(value, unit, at, refs, *, quality='OK', freshness='UNKNOWN'):
    return {'value_state': 'KNOWN' if value is not None else 'UNKNOWN',
        'value': float(value) if value is not None else None, 'unit': unit, 'as_of': at,
        'data_quality': quality if value is not None else 'UNKNOWN', 'freshness': freshness,
        'issue_codes': [], 'source_reference_ids': list(refs), 'source_native_status': None}


def money(value, currency, at, refs):
    return {'value_state': 'KNOWN' if value is not None else 'UNKNOWN',
        'amount': float(value) if value is not None else None, 'currency': currency, 'as_of': at,
        'data_quality': 'OK' if value is not None else 'UNKNOWN', 'freshness': 'UNKNOWN',
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
        v70[field] = money(raw['payload'][field], currency, raw['snapshot_as_of'], [v70_ref])
    mappings = {r['instrument_id']: r for r in preflight['mapping']}
    lines = []
    for row in target['payload']['draft']['target_lines']:
        weight = Decimal(str(row['weight']['value'])); mapping = mappings[row['instrument_id']]
        kind = {'STOCK': 'equity exposure', 'BOND': 'bond exposure',
                'V70_ORIGINAL_DRY_POWDER': 'cash'}.get(mapping['bucket'], 'UNKNOWN')
        native_id = projection['source_to_native'][row['instrument_id']]
        lines.append({'instrument_id': native_id, 'ticker': row['ticker'],
            'display_name': row.get('display_name'), 'asset_type': kind, 'market': None,
            'base_currency': currency, 'value_state': 'KNOWN',
            'weight': metric(weight, 'portfolio_weight', at, [target_ref]),
            'portfolio_amount': money(base * weight, currency, at, [target_ref]),
            'source_reference_ids': [target_ref]})
    proposal = {'allocation_id': 'APPROVED-BASE-PROJECTION:' + digest(target),
        'stage': 'PROPOSED', 'as_of': at, 'denominator': money(base, currency, at, [target_ref]),
        'positions': lines, 'declared_total_weight': metric(sum(Decimal(str(r['weight']['value']))
            for r in lines), 'portfolio_weight', at, [target_ref]),
        'confirmation_status': 'PENDING', 'confirmed_at': None, 'confirmed_by': None,
        'source_reference_ids': [target_ref]}
    # Historical approved capital and a selected-account asset reference have
    # different scope. No manufactured 100% Current snapshot or signing event.
    canonical = {'contract_name': 'LivingWaterAI.C.CanonicalInput', 'contract_version': 'C-W1-v1.0.1',
        'identity': {k: request[k] for k in ('client_id', 'run_id', 'request_id')},
        'decision_phase': 'PROPOSAL_REVIEW', 'capital_context': {
            'total_investment_amount': money(base, currency, at, [target_ref]), 'base_currency': currency,
            'fx_metadata': {'value_state': 'UNKNOWN', 'as_of': None, 'rates': [], 'source_reference_ids': []}},
        'allocations': {'current_allocation': {'value_state': 'UNKNOWN', 'snapshot': None,
            'reason': current['portfolio_nav']['reason']},
            'proposed_allocation': {'value_state': 'KNOWN', 'snapshot': proposal, 'reason':
                'Existing long-term weights/base projected for review; no tactical approval implied'},
            'final_target': {'value_state': 'NONE', 'snapshot': None,
                'reason': 'No new same-run Work6 confirmation has been created'}},
        'v70_asset_framework': v70, 'benchmark_reference': benchmark['reference'],
        'source_references': benchmark['source_references'] + [
            reference(target_ref, 'CLIENT_PROJECT', 'CLIENT_PROJECT', target, at),
            reference(current_ref, 'SYSTEM_DERIVED', 'C_INTEGRATION', current, at, quality='INSUFFICIENT'),
            reference(v70_ref, 'V70_SNAPSHOT', 'V70', raw, raw['snapshot_as_of'],
                      quality=raw['payload']['data_quality'], freshness=freshness)],
        'issues': [], 'traceability': []}
    canonical['identity']['portfolio_id'] = 'GLOBAL-PORTFOLIO:' + request['client_id']
    adjustment = {'contract_name': 'LivingWaterAI.C.Work6.AdjustmentRequest',
        'contract_version': 'C-W6-v1.0.0', 'adjustment_id': 'SOURCE-REVIEW:' + request['run_id'],
        'requested_change_types': ['REVIEW_ONLY'], 'weight_overrides': [], 'preference_decisions': [],
        'confirmation': {'action': 'KEEP_PENDING', 'client_explicit_decision': 'UNKNOWN',
            'confirmed_at': None, 'confirmed_by': None, 'source_reference_ids': []},
        'radar_scores': [], 'source_references': [], 'source_reference_ids': [target_ref, current_ref, v70_ref]}
    work6_source = {'schema_version': 'Family.W5.Work6Source.v1', 'canonical_input': canonical,
        'adjustment_request': adjustment, 'benchmark_source': deepcopy(descriptor), 'evaluated_at': at}
    work6 = run_work6_engine(root, work6_source)
    source = {'schema_version': 'Family.W5.C7Source.v1', 'producer': 'Family.W8.OriginalConfigurationSources',
        'version': '1.0', 'source_reference': 'VERIFIED-ANALYSIS:' + analysis['report_digest'],
        'family_owner': deepcopy(request['owner']), 'canonical_input': canonical,
        'work6_result': work6['result'], 'work6_source': work6_source,
        'funding_context': deepcopy(out['native_bundle']['stock_request']['c7_funding_context']),
        'evaluated_at': at}
    computed = run_c7_engine(root, source)
    out['native_bundle']['asset_framework'] = computed['result']
    out['trusted_context']['c7_source'] = source
    out['component_results']['configuration'] = {'work6': work6, 'c7': computed,
        'approval_identity': {'source_digest': digest(target), 'scope': 'EXISTING_LONG_TERM_APPROVAL',
            'source_confirmation_evidence': deepcopy(target['payload']['confirmation_evidence']),
            'new_confirmation_created': False, 'tactical_target_approved': False},
        'scope_gaps': deepcopy(current['portfolio_nav']), 'bucket_preflight': preflight}
    out['context_bindings']['c7_source'] = {'status': 'ORIGINAL_WORK6_AND_C7_EXECUTED',
        'source_digest': digest(source), 'work6_source_digest': digest(work6_source),
        'framework_status': computed['result']['status'],
        'qualified_for_native_dispatch': computed['result']['status'] == 'READY_FOR_PM_GATE'}
    out['context_call_trace'] += work6['call_trace'] + computed['call_trace']
    return out
