"""Carry verified data/funding progress through an original C7 refusal.

This is a scoped continuation diagnostic, not a replacement Work9 or Mentor.
It copies actual source results; no target, amount or approval is invented.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from family_input import digest


def build(root, request, analysis, work6, c7, source_sections):
    identity = {'client_id': request['client_id'], 'run_id': request['run_id'],
        'owner': request['owner'], 'source_db_sha256': request['client_snapshot']['payload']['source_sha256']}
    for key, value in identity.items():
        if analysis.get(key) != value:
            raise PermissionError('DEPLOYMENT_PROGRESS_ANALYSIS_IDENTITY:' + key)
    unsigned = {k: v for k, v in analysis.items() if k not in ('report_digest', 'source_sha256')}
    if analysis['report_digest'] != digest(unsigned):
        raise PermissionError('DEPLOYMENT_PROGRESS_ANALYSIS_DIGEST')
    funding = analysis.get('account_funding_check')
    if funding is not None:
        if any(funding.get(k) != v for k, v in identity.items()):
            raise PermissionError('DEPLOYMENT_PROGRESS_FUNDING_IDENTITY')
        if funding.get('output_digest') != digest({k: v for k, v in funding.items() if k != 'output_digest'}):
            raise PermissionError('DEPLOYMENT_PROGRESS_FUNDING_DIGEST')
    pool = analysis.get('v75_macro_inputs') or {}
    ready = pool.get('ready_data_handoff') or {}
    delta = pool.get('additional_delta_handoff') or {}
    sparse = (delta or ready).get('sparse_yield_evidence') or {}
    quality = (analysis.get('native_bond_source') or {}).get('etf_quality_assessments') or pool.get('etf_quality_assessments', {})
    evidence = {}
    for symbol, assessment in quality.items():
        distribution = assessment.get('calculations', {}).get('distribution_source') or {}
        evidence[symbol] = {'quality_components': deepcopy(assessment['metrics']),
            'missing_quality_inputs': deepcopy(assessment.get('unprovided_inputs', [])),
            'distribution_source': {k: deepcopy(distribution.get(k)) for k in (
                'periods', 'as_reported_total_distribution', 'as_reported_income_sum', 'as_reported_roc_pct',
                'complete_source_breakdown', 'complete_final_breakdown', 'provisional_issuer_components', 'missing_roc_dates')},
            'source_available_at': assessment.get('source_available_at')}
        if distribution.get('partial_components'):
            evidence[symbol]['partial_distribution_components'] = {
                k: deepcopy(v) for k, v in distribution['partial_components'].items() if k != 'rows'}
    if sparse:
        evidence.setdefault('SPSB', {})['sparse_yields'] = {k: deepcopy(sparse.get(k)) for k in (
            'distinct_observations', 'counts_by_metric', 'delta_summary', 'weekly_history_available', 'engine_input_eligible')}
    coverage = ready.get('bounded_event_coverage')
    if coverage:
        evidence.setdefault('SGOV', {})['bounded_event_coverage'] = {k: deepcopy(coverage[k]) for k in (
            'review_period_start', 'review_period_end', 'forms_screened', 'filings_retrieved',
            'locally_retained_matched_primary_documents', 'all_forms_reviewed',
            'unnamed_trust_effects_fully_covered', 'new_trade_gate_created')}
    path = Path('系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/work7/asset_framework.py')
    out = {'schema_version': 'Family.W8.DeploymentProgressReview.v1', **deepcopy(identity),
        'evaluation_at': request['evaluation_at'], 'analysis_report_digest': analysis['report_digest'],
        'scope': 'SOURCE_BOUND_CONTINUATION_DIAGNOSTIC__NOT_UNIFIED_WORK9_MENTOR',
        'source_sections_produced': sorted(source_sections),
        'configuration': {'work6_status': work6['loop_status'], 'c7_status': c7['status'],
            'bucket_comparison': deepcopy(c7.get('residual_allocation', {}).get('buckets', [])),
            'native_issues': deepcopy(c7.get('issues', [])),
            'rule_reference': {'path': str(path), 'sha256': sha256((Path(root)/path).read_bytes()).hexdigest(),
                'function': '_build_residual_allocation',
                'rule': 'Confirmed Final Target asset-class totals must match same-run V70; mismatch routes upstream for reconfirmation.'},
            'approved_target_digest': digest(request['confirmed_target']), 'approval_changed': False,
            'new_tactical_approval_created': False},
        'account_funding_check': deepcopy(funding), 'data_evidence': evidence,
        'remaining_predicate_inputs': deepcopy(pool.get('asset_unprovided_inputs', {})),
        'engineering_dependencies': [
            {'stage': 'UNIFIED_WORK9', 'state': 'WAITING_FOR_VALID_NATIVE_CANONICAL_DECISIONS_AND_FUNDING'},
            {'stage': 'UNIFIED_MENTOR', 'state': 'WAITING_FOR_UNIFIED_WORK9'}],
        'formal_contract_state': 'RETURN_TO_V70_RECONFIRMATION_REQUIRED' if c7['status'] == 'RETURN_TO_V70' else c7['status'],
        'missing_data_and_contract_routing_kept_separate': True,
        'full_native_pipeline_complete': False, 'full_native_mentor_reached': False,
        'trade_action': 'NO_TRADE'}
    out['digest'] = digest(out)
    return out
