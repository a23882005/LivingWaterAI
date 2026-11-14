"""Reconcile append-only SPSB evidence; no synthetic weeks or whole-TTM ROC."""
from collections import Counter
from copy import deepcopy
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json

from v75_handoff_inputs import csv_rows, excel_day, iso, xlsx_rows, distribution_window
from v75_ready_data_inputs import manifest_files, sparse_yields
from v75_remaining_inputs import number, time


def observation_key(row):
    return row['metric'], row.get('as_of'), number(row['value_percent'])


def merge_yields(files, previous, evaluation_at, source):
    delta = sparse_yields(files, evaluation_at, prefix='yield')
    old = {observation_key(r): deepcopy(r) for r in previous['observations']}
    new = {observation_key(r): r for r in delta['observations']}
    delivered = json.loads(files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json'], parse_float=Decimal)
    expected = set(new) - set(old)
    if len(delivered) != len(expected) or {observation_key(r) for r in delivered} != expected:
        raise PermissionError('ADDITIONAL_YIELD_DELTA_SET_MISMATCH')
    for row in delivered:
        actual = new[observation_key(row)]
        def proof(r):
            return (r['capture_timestamp'], r['original_url'],
                r.get('archive_replay_url', r.get('replay_url')), r.get('path', r.get('raw_file')))
        if row['ticker'] != 'SPSB' or Counter(map(proof, row['sources'])) != Counter(map(proof, actual['sources'])):
            raise PermissionError('ADDITIONAL_YIELD_DELTA_SOURCE_MISMATCH')
    for key, row in new.items():
        if any(s.get('retrieval_utc') and time(s['retrieval_utc']) > time(source['ingested_at']) for s in row['sources']):
            raise PermissionError('ADDITIONAL_RETRIEVAL_AFTER_INGESTION')
        target = old.setdefault(key, {k: deepcopy(v) for k, v in row.items() if k != 'sources'})
        target.setdefault('sources', []).extend({**deepcopy(s),
            'origin_handoff_manifest_sha256': source['manifest_sha256'],
            'origin_source_root': source['root']} for s in row['sources'])
    by_date = {}
    for metric, day, value in old:
        by_date.setdefault((metric, day), set()).add(value)
    if any(len(values) != 1 for values in by_date.values()):
        raise PermissionError('ADDITIONAL_YIELD_SAME_DATE_VALUE_CONFLICT')
    summary = {'baseline_unique_metric_observations': previous['distinct_observations'],
        'replayed_source_rows': delta['raw_source_rows'],
        'new_unique_metric_observations': len(expected), 'cumulative_unique_metric_observations': len(old),
        'per_metric': {}, 'same_date_value_conflicts': [], 'not_a_qualified_weekly_series': True}
    for metric in ('portfolio_ytm', 'sec_yield_30day'):
        days = sorted(date.fromisoformat(day) for m, day, value in old if m == metric)
        summary['per_metric'][metric] = {
            'new_unique_observations': sum(key[0] == metric for key in expected),
            'cumulative_unique_observations': len(days), 'first_as_of': str(days[0]), 'last_as_of': str(days[-1]),
            'unique_ISO_weeks': len({d.isocalendar()[:2] for d in days}),
            'largest_gap_days': max((b-a).days for a, b in zip(days, days[1:]))}
    if summary != json.loads(files['yield/DELTA_SUMMARY.json']):
        raise PermissionError('ADDITIONAL_YIELD_SUMMARY_MISMATCH')
    return {**deepcopy(previous), 'observations': sorted(old.values(), key=lambda r: (r['metric'], r['as_of'])),
        'distinct_observations': len(old), 'raw_source_rows': previous['raw_source_rows'] + delta['raw_source_rows'],
        'counts_by_metric': dict(Counter(key[0] for key in old)), 'delta_summary': summary,
        'weekly_history_available': False, 'engine_input_eligible': False,
        'missing_weeks_filled': False, 'percentile_calculated': False}


def partial_components(files, previous_dividends, prior_tax_sha256, evaluation_at):
    raw = files['roc/SPDR_ICI_Tax_Summary_Primary_20261029.xlsx']
    if sha256(raw).hexdigest() != prior_tax_sha256:
        raise PermissionError('ADDITIONAL_TAX_PREVIOUS_SOURCE_MISMATCH')
    tax = xlsx_rows(raw)
    if tax[1]['A'] != 'SPDR ETF 2025 Tax Summary - Primary Layout':
        raise PermissionError('ADDITIONAL_TAX_YEAR_IDENTITY')
    delivered = json.loads(files['roc/spsb_TTM_partial_components.json'])
    if delivered['currency'] != 'USD' or delivered['asof'] > time(evaluation_at).date().isoformat():
        raise PermissionError('ADDITIONAL_COMPONENT_CURRENCY_OR_ASOF')
    if excel_day(tax[4]['B']) != delivered['tax_report_date']:
        raise PermissionError('ADDITIONAL_TAX_REPORT_DATE')
    original = csv_rows(files['roc/spsb_original_12_distributions.csv'])
    if original != previous_dividends['rows']:
        raise PermissionError('ADDITIONAL_PREVIOUS_DISTRIBUTIONS_MISMATCH')
    by_date = {iso(r['EX-DATE'], '%m/%d/%Y'): r for r in original}
    extracted = csv_rows(files['roc/spsb_TTM_partial_components.csv'])
    rows = delivered['rows']
    if len(rows) != 12 or len({r['ex_date'] for r in rows}) != 12 or {r['ex_date'] for r in rows} != set(by_date):
        raise PermissionError('ADDITIONAL_PAYMENT_COVERAGE')
    normalized = [{k: '' if v is None else str(v) for k, v in r.items()} for r in rows]
    if normalized != extracted:
        raise PermissionError('ADDITIONAL_COMPONENT_JSON_CSV_MISMATCH')
    fields = {'income_dividends_USD_per_share': 'N', 'ordinary_dividends_USD_per_share': 'Q',
        'short_term_capital_gain_USD_per_share': 'O', 'total_capital_gain_distribution_USD_per_share': 'V',
        'nondividend_distribution_ROC_USD_per_share': 'Z'}
    known = []; output = []
    for row in rows:
        original = by_date[row['ex_date']]
        if (row['ticker'] != 'SPSB' or row['cusip'] != '78464A474'
                or row['record_date'] != iso(original['RECORD DATE'], '%m/%d/%Y')
                or row['pay_date'] != iso(original['PAYABLE DATE'], '%m/%d/%Y')
                or row['distribution_source_row'] != int(original['source_row'])
                or number(row['distribution_USD_per_share']) != number(original['DIVIDEND ($)'])):
            raise PermissionError('ADDITIONAL_PAYMENT_JOIN_MISMATCH')
        if row['tax_source_row'] is not None:
            source = tax[row['tax_source_row']]
            if (source['B'] != row['cusip'] or source['C'] != row['ticker']
                    or any(source.get(k) not in ('', None) for k in ('D', 'E', 'F'))
                    or excel_day(source['G']) != row['record_date'] or excel_day(source['H']) != row['ex_date']
                    or excel_day(source['I']) != row['pay_date']
                    or number(source['J']) != number(row['distribution_USD_per_share'])
                    or any(number(row[k]) != number(source[column]) for k, column in fields.items())):
                raise PermissionError('ADDITIONAL_TAX_ROW_MISMATCH')
            known.append(row)
        elif any(row[k] is not None for k in fields):
            raise PermissionError('ADDITIONAL_UNKNOWN_COMPONENT_NOT_NULL')
        output.append({'ex_date': row['ex_date'], 'dividend': row['distribution_USD_per_share'],
            'total': row['distribution_USD_per_share'] if row['tax_source_row'] is not None else None,
            'income': row['income_dividends_USD_per_share'],
            'roc': row['nondividend_distribution_ROC_USD_per_share'],
            'final_tax_characterization': row['tax_source_row'] is not None,
            'characterization': 'OFFICIAL_2025_TAX_BREAKDOWN' if row['tax_source_row'] is not None else 'ROC_NOT_PRESENT_IN_DISTRIBUTION_FILE',
            'source_row': row['distribution_source_row'], 'tax_source_row': row['tax_source_row']})
    total = sum((number(r['distribution_USD_per_share']) for r in rows), Decimal(0))
    verified = sum((number(r['distribution_USD_per_share']) for r in known), Decimal(0))
    income = sum((number(r['income_dividends_USD_per_share']) for r in known), Decimal(0))
    roc = sum((number(r['nondividend_distribution_ROC_USD_per_share']) for r in known), Decimal(0))
    summary = {'total_distribution_per_share': total, 'component_verified_payment_count': len(known),
        'total_payment_count': len(rows), 'component_verified_distribution_per_share': verified,
        'component_verified_amount_coverage_fraction': verified/total,
        'component_verified_amount_coverage_percent': verified/total*100,
        'known_income_dividends_per_share': income, 'known_ROC_per_share': roc,
        'unknown_component_distribution_per_share': total-verified, 'known_subset_only_ROC_percent': roc/verified*100}
    if any(number(delivered[k]) != value for k, value in summary.items()) or any(
            delivered[k] is not None for k in ('full_TTM_income_per_share', 'full_TTM_ROC_per_share', 'full_TTM_ROC_weighted_percent')):
        raise PermissionError('ADDITIONAL_PARTIAL_TTM_SUMMARY_MISMATCH')
    window = distribution_window(output, delivered['asof'])
    if window['complete_source_breakdown'] or window['as_reported_roc_pct'] is not None:
        raise PermissionError('ADDITIONAL_PARTIAL_TTM_NOT_COMPLETE')
    window.update(partial_components={**deepcopy(delivered),
        'income_and_ordinary_dividends_are_overlapping': True, 'overlapping_income_added_twice': False,
        'source_raw_sha256': sha256(raw).hexdigest(), 'next_year_attribution_is_new_payment_data': False},
        currency='USD', amount_basis='PER_SHARE')
    return window


def extend(pool, source, data, evaluation_at, prior_handoff):
    if source is None: return pool
    if not pool.get('ready_data_handoff') or not prior_handoff:
        raise PermissionError('ADDITIONAL_PRIOR_READY_HANDOFF_REQUIRED')
    files = manifest_files(source, evaluation_at, schema='Family.W8.V75AdditionalDeltaSource.v1',
        manifest_name='TOP_MANIFEST.json', size_field='bytes')
    previous = pool['ready_data_handoff']
    prior_manifest = (Path(prior_handoff['root']) / 'PACKAGE_MANIFEST.json').read_bytes()
    if sha256(prior_manifest).hexdigest() != prior_handoff['manifest_sha256']:
        raise PermissionError('ADDITIONAL_PRIOR_MANIFEST_HASH')
    prior_tax_sha = next(r['sha256'] for r in json.loads(prior_manifest) if r['path'] == 'etf_quality/spsb_tax.xlsx')
    yields = merge_yields(files, previous['sparse_yield_evidence'], evaluation_at, source)
    distribution = partial_components(files, previous['spsb_distribution_and_qii']['dividends'], prior_tax_sha, evaluation_at)
    distribution.update(source_manifest_sha256=source['manifest_sha256'], source_available_at=source['ingested_at'])
    receipt = {'schema_version': 'Family.W8.VerifiedV75AdditionalDelta.v1',
        'manifest_sha256': source['manifest_sha256'], 'source_available_at': source['ingested_at'],
        'source_reference': source['source_reference'], 'raw_files_verified': len(files),
        'sparse_yield_evidence': yields, 'partial_distribution_components': distribution,
        'prior_sources_preserved': True, 'trade_action': 'NO_TRADE'}
    pool['additional_delta_handoff'] = receipt
    pool['available_at'] = max(pool['available_at'], source['ingested_at'], key=time)
    pool['source_proofs']['ADDITIONAL_DELTA_HANDOFF'] = {
        'source_reference': source['source_reference'], 'source_sha256': source['manifest_sha256'], 'available_at': source['ingested_at']}
    pool['canonical_yield_observations']['SPSB']['sparse_audit_evidence'] = deepcopy(yields)
    issuer = pool['issuer_observations']['SPSB']
    issuer['facts']['distribution_source_observation'] = distribution
    pool.setdefault('distribution_source_observations', {})['SPSB'] = deepcopy(distribution)
    from v75_etf_quality_inputs import assess
    assessment = assess(issuer, pool.get('qualified_bond_markets', {}).get('SPSB'), data.get('YAHOO_SPSB'),
        pool['formal_parameters'], evaluation_at,
        authorized_universe=pool['etf_quality_assessments']['SPSB']['normalized_facts']['authorized_universe'])
    pool['etf_quality_assessments']['SPSB'] = assessment
    pool['asset_metrics']['SPSB']['PRED-010'] = assessment['metrics']
    pool['calculations']['SPSB.PRED-010'] = assessment
    pool['asset_unprovided_inputs']['SPSB']['PRED-010'] = assessment['unprovided_inputs']
    return pool
