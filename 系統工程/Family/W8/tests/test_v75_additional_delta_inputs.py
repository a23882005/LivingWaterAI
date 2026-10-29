"""Cumulative sparse evidence and a partial tax join never become full coverage."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv
import io
import json
import sys
import zipfile

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
import v75_additional_delta_inputs as D
from v75_ready_data_inputs import manifest_files
from mentor_bridge import distribution_source_text, ready_data_evidence_notes
from test_v75_ready_data_inputs import sparse_files

AT = '2026-10-29T18:00:00Z'


def yield_case():
    files = {k.replace('spsb_sparse_history/', 'yield/'): v for k, v in sparse_files().items()}
    rows = json.loads(files['yield/sparse_archived_issuer_yields.json'])
    delivered = []
    for metric in ('portfolio_ytm', 'sec_yield_30day'):
        group = [r for r in rows if r['metric'] == metric]
        delivered.append({k: v for k, v in group[0].items() if k not in
            ('raw_file', 'original_url', 'archive_replay_url', 'capture_timestamp')})
        delivered[-1]['sources'] = [{k: r[k] for k in
            ('raw_file', 'original_url', 'archive_replay_url', 'capture_timestamp')} for r in group]
    old = {'ticker': 'SPSB', 'observations': [
        {'metric': 'portfolio_ytm', 'as_of': '2019-10-02', 'value_percent': '1', 'sources': []},
        {'metric': 'sec_yield_30day', 'as_of': '2019-10-01', 'value_percent': '1', 'sources': []}],
        'distinct_observations': 2, 'raw_source_rows': 2, 'counts_by_metric': {'portfolio_ytm': 1, 'sec_yield_30day': 1}}
    summary = {'baseline_unique_metric_observations': 2, 'replayed_source_rows': 4,
        'new_unique_metric_observations': 2, 'cumulative_unique_metric_observations': 4,
        'per_metric': {}, 'same_date_value_conflicts': [], 'not_a_qualified_weekly_series': True}
    for metric, first, last in [('portfolio_ytm', '2019-10-02', '2023-10-03'),
                               ('sec_yield_30day', '2019-10-01', '2023-10-02')]:
        summary['per_metric'][metric] = {'new_unique_observations': 1, 'cumulative_unique_observations': 2,
            'first_as_of': first, 'last_as_of': last, 'unique_ISO_weeks': 2,
            'largest_gap_days': (date.fromisoformat(last)-date.fromisoformat(first)).days}
    files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json'] = json.dumps(delivered).encode()
    files['yield/DELTA_SUMMARY.json'] = json.dumps(summary).encode()
    return files, old, {'root': '/synthetic/delta', 'manifest_sha256': '0'*64, 'ingested_at': AT}


def test_sparse_append_retains_both_metrics_sources_and_unfilled_gaps():
    files, old, source = yield_case(); before = deepcopy(old)
    out = D.merge_yields(files, old, AT, source)
    assert old == before and out['distinct_observations'] == 4
    assert out['counts_by_metric'] == {'portfolio_ytm': 2, 'sec_yield_30day': 2}
    assert out['raw_source_rows'] == 6 and not out['weekly_history_available']
    assert not out['engine_input_eligible'] and not out['missing_weeks_filled'] and not out['percentile_calculated']
    new = next(r for r in out['observations'] if r['as_of'] == '2023-10-03')
    assert len(new['sources']) == 2 and all(r['raw_file'].startswith('yield/') for r in new['sources'])


def test_claimed_delta_count_and_asof_source_are_replayed():
    files, old, source = yield_case()
    claimed = json.loads(files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json']); claimed[0]['as_of'] = '2023-10-04'
    files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json'] = json.dumps(claimed).encode()
    with pytest.raises(PermissionError, match='DELTA_SET_MISMATCH'): D.merge_yields(files, old, AT, source)
    files, old, source = yield_case()
    claimed = json.loads(files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json']); claimed[0]['sources'][0]['capture_timestamp'] = '20231006120000'
    files['yield/NEW_UNIQUE_YIELD_OBSERVATIONS.json'] = json.dumps(claimed).encode()
    with pytest.raises(PermissionError, match='DELTA_SOURCE_MISMATCH'): D.merge_yields(files, old, AT, source)


def test_same_date_conflict_is_not_silently_replaced_and_decimal_identity_is_exact():
    assert D.observation_key({'metric': 'portfolio_ytm', 'as_of': '2023-10-03', 'value_percent': '6.190'}) == \
        D.observation_key({'metric': 'portfolio_ytm', 'as_of': '2023-10-03', 'value_percent': '6.19'})
    files, old, source = yield_case()
    old['observations'][0].update(as_of='2023-10-03', value_percent='99')
    with pytest.raises(PermissionError, match='SAME_DATE_VALUE_CONFLICT'): D.merge_yields(files, old, AT, source)


def encoded_csv(rows):
    buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=list(rows[0])); writer.writeheader()
    writer.writerows(rows); return buf.getvalue().encode()


def component_case():
    days = ['2026-10-01', '2026-09-01', '2026-08-03', '2026-07-01', '2026-06-01', '2026-05-01',
        '2026-04-01', '2026-03-02', '2026-02-02', '2025-12-18', '2025-12-01', '2025-11-03']
    original = []; rows = []; tax = {1: {'A': 'SPDR ETF 2025 Tax Summary - Primary Layout'}, 4: {'B': '46042'}}
    for i, day in enumerate(days):
        d = date.fromisoformat(day); known = i >= 9; tr = 165-i if known else None
        original.append({'source_row': str(8088+i), 'TICKER': 'SPSB', 'CUSIP': '78464A474',
            'EX-DATE': d.strftime('%m/%d/%Y'), 'RECORD DATE': d.strftime('%m/%d/%Y'),
            'PAYABLE DATE': d.strftime('%m/%d/%Y'), 'DIVIDEND ($)': '.1'})
        row = {'ticker': 'SPSB', 'cusip': '78464A474', 'ex_date': day, 'record_date': day, 'pay_date': day,
            'distribution_USD_per_share': '.1', 'distribution_source_row': 8088+i,
            'income_dividends_USD_per_share': '.1' if known else None,
            'ordinary_dividends_USD_per_share': '.1' if known else None,
            'short_term_capital_gain_USD_per_share': '0' if known else None,
            'total_capital_gain_distribution_USD_per_share': '0' if known else None,
            'nondividend_distribution_ROC_USD_per_share': '0' if known else None,
            'component_status': 'SYNTHETIC', 'tax_source_row': tr}
        rows.append(row)
        if known:
            serial = str((d-date(1899, 12, 30)).days)
            tax[tr] = {'B': '78464A474', 'C': 'SPSB', 'G': serial, 'H': serial, 'I': serial,
                'J': '.1', 'N': '.1', 'O': '0', 'Q': '.1', 'V': '0', 'Z': '0', 'L': '0'}
    sheet = '<worksheet><sheetData>'
    from html import escape
    for n, cells in sorted(tax.items()):
        sheet += '<row r="'+str(n)+'">'+''.join('<c r="'+k+str(n)+'" t="inlineStr"><is><t>'+escape(v)+'</t></is></c>' for k,v in cells.items())+'</row>'
    sheet += '</sheetData></worksheet>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Tax" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', sheet)
    delivered = {'asof': '2026-10-29', 'currency': 'USD', 'tax_report_date': '2026-01-20', 'rows': rows,
        'total_distribution_per_share': '1.2', 'component_verified_payment_count': 3, 'total_payment_count': 12,
        'component_verified_distribution_per_share': '.3', 'component_verified_amount_coverage_fraction': '.25',
        'component_verified_amount_coverage_percent': '25', 'known_income_dividends_per_share': '.3',
        'known_ROC_per_share': '0', 'unknown_component_distribution_per_share': '.9',
        'known_subset_only_ROC_percent': '0', 'full_TTM_income_per_share': None,
        'full_TTM_ROC_per_share': None, 'full_TTM_ROC_weighted_percent': None}
    raw = buf.getvalue()
    files = {'roc/SPDR_ICI_Tax_Summary_Primary_20261029.xlsx': raw,
        'roc/spsb_original_12_distributions.csv': encoded_csv(original),
        'roc/spsb_TTM_partial_components.csv': encoded_csv(rows),
        'roc/spsb_TTM_partial_components.json': json.dumps(delivered).encode()}
    return files, {'rows': original}, sha256(raw).hexdigest()


def test_three_known_payments_do_not_make_nine_unknown_payments_zero_roc():
    files, old, pin = component_case(); out = D.partial_components(files, old, pin, AT)
    assert out['periods'] == 12 and out['as_reported_roc_pct'] is None and not out['complete_source_breakdown']
    assert len(out['missing_roc_dates']) == 9 and not out['complete_final_breakdown']
    assert out['partial_components']['component_verified_distribution_per_share'] == '.3'
    assert out['partial_components']['full_TTM_ROC_per_share'] is None
    assert out['partial_components']['income_and_ordinary_dividends_are_overlapping']
    assert not out['partial_components']['overlapping_income_added_twice']
    assert '其餘9次' in distribution_source_text('SPSB', out)


def test_subset_roc_cannot_be_promoted_to_whole_ttm_and_tax_source_is_pinned():
    files, old, pin = component_case()
    with pytest.raises(PermissionError, match='PREVIOUS_SOURCE_MISMATCH'): D.partial_components(files, old, '0'*64, AT)
    d = json.loads(files['roc/spsb_TTM_partial_components.json']); d['full_TTM_ROC_per_share'] = '0'
    files['roc/spsb_TTM_partial_components.json'] = json.dumps(d).encode()
    with pytest.raises(PermissionError, match='PARTIAL_TTM_SUMMARY_MISMATCH'): D.partial_components(files, old, pin, AT)


def test_unknown_components_and_mismatched_tax_payment_dates_are_rejected():
    files, old, pin = component_case()
    d = json.loads(files['roc/spsb_TTM_partial_components.json']); d['rows'][0]['income_dividends_USD_per_share'] = '0'
    files['roc/spsb_TTM_partial_components.json'] = json.dumps(d).encode(); files['roc/spsb_TTM_partial_components.csv'] = encoded_csv(d['rows'])
    with pytest.raises(PermissionError, match='UNKNOWN_COMPONENT_NOT_NULL'): D.partial_components(files, old, pin, AT)
    files, old, pin = component_case()
    d = json.loads(files['roc/spsb_TTM_partial_components.json']); d['rows'][-1]['pay_date'] = '2025-11-04'
    files['roc/spsb_TTM_partial_components.json'] = json.dumps(d).encode(); files['roc/spsb_TTM_partial_components.csv'] = encoded_csv(d['rows'])
    with pytest.raises(PermissionError, match='PAYMENT_JOIN_MISMATCH'): D.partial_components(files, old, pin, AT)


def test_additional_manifest_schema_and_latest_report_counts(tmp_path):
    assert D.extend({}, None, {}, AT, None) == {}
    with pytest.raises(PermissionError, match='PRIOR_READY_HANDOFF_REQUIRED'): D.extend({}, {}, {}, AT, None)
    raw = b'data'; (tmp_path/'a').write_bytes(raw)
    manifest = json.dumps([{'path': 'a', 'bytes': 4, 'sha256': sha256(raw).hexdigest()}]).encode()
    (tmp_path/'TOP_MANIFEST.json').write_bytes(manifest)
    s = {'schema_version': 'Family.W8.V75AdditionalDeltaSource.v1', 'root': str(tmp_path),
        'ingested_at': AT, 'manifest_sha256': sha256(manifest).hexdigest()}
    assert manifest_files(s, AT, schema=s['schema_version'], manifest_name='TOP_MANIFEST.json', size_field='bytes') == {'a': raw}
    ready = {'sparse_yield_evidence': {'counts_by_metric': {'portfolio_ytm': 12, 'sec_yield_30day': 12}}}
    delta = {'sparse_yield_evidence': {'counts_by_metric': {'portfolio_ytm': 39, 'sec_yield_30day': 39}}}
    text = ''.join(ready_data_evidence_notes(ready, 'SPSB', delta))
    assert '39筆組合YTM' in text and '39筆30-Day SEC Yield' in text and 'QII不是ROC' in text
