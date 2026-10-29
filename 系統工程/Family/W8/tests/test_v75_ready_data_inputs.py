"""Append-only evidence, exact source reconciliation and independent limits."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import gzip
import json
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'W5')]
import v75_ready_data_inputs as R
import v75_etf_quality_inputs as Q
from mentor_bridge import distribution_source_text, ready_data_evidence_notes


AT = '2026-10-29T17:00:00Z'


def source(tmp_path, files):
    items = []
    for name, raw in files.items():
        p = tmp_path / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
        items.append({'path': name, 'size': len(raw), 'sha256': sha256(raw).hexdigest()})
    raw = json.dumps(items).encode(); (tmp_path / 'PACKAGE_MANIFEST.json').write_bytes(raw)
    return {'schema_version': 'Family.W8.V75ReadyDataSource.v1', 'root': str(tmp_path),
        'manifest_sha256': sha256(raw).hexdigest(), 'ingested_at': '2026-10-29T16:00:00Z'}


def test_manifest_bound_bytes_paths_and_availability_are_enforced(tmp_path):
    s = source(tmp_path, {'a.txt': b'original'})
    assert R.manifest_files(s, AT) == {'a.txt': b'original'}
    with pytest.raises(PermissionError, match='AVAILABILITY'):
        R.manifest_files(s, '2026-10-29T15:59:59Z')
    (tmp_path / 'a.txt').write_bytes(b'changed!')
    with pytest.raises(PermissionError, match='SOURCE_HASH'): R.manifest_files(s, AT)
    raw = json.dumps([{'path': '../a.txt', 'size': 0, 'sha256': '0' * 64}]).encode()
    (tmp_path / 'PACKAGE_MANIFEST.json').write_bytes(raw); s['manifest_sha256'] = sha256(raw).hexdigest()
    with pytest.raises(PermissionError, match='MANIFEST_PATH'): R.manifest_files(s, AT)


def distribution_files():
    header = ['Record Date', 'Ex-Date', 'Payable Date', 'Total Distribution', 'Income',
        'ST Cap Gains', 'LT Cap Gains', 'Return of Capital']
    dates = ['Oct 01, 2026', 'Sep 01, 2026', 'Aug 03, 2026', 'Jul 01, 2026',
        'Jun 01, 2026', 'May 01, 2026', 'Apr 01, 2026', 'Mar 02, 2026',
        'Feb 02, 2026', 'Dec 19, 2025', 'Dec 01, 2025', 'Nov 03, 2025']
    rows = [dict(zip(header, [d, d, d, '0.300000', '0.300000', '0', '0', '0'])) for d in dates]
    xml = ('<Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Distributions"><Table>'
        + ''.join('<Row>' + ''.join('<Cell><Data>' + c + '</Data></Cell>' for c in r) + '</Row>'
            for r in [header] + [list(r.values()) for r in rows]) + '</Table></Worksheet></Workbook>')
    delivered = {'ticker': 'SGOV', 'currency': 'USD', 'rows': rows,
        'per_share_totals': {'Total Distribution': '3.6', 'Income': '3.6',
            'ST Cap Gains': '0', 'LT Cap Gains': '0', 'Return of Capital': '0'},
        'roc_amount_weighted_pct': '0', 'source': 'https://issuer.example/sgov',
        'tax_finality': 'provisional_issuer_display_not_final_2026_tax'}
    import csv, io
    buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=header); writer.writeheader(); writer.writerows(rows)
    return {'quality/sgov_fresh_20261029.xls': xml.encode(),
        'quality/sgov_provisional_12payment_decomposition.json': json.dumps(delivered).encode(),
        'quality/sgov_12_distributions_fresh.csv': buf.getvalue().encode()}


def test_complete_provisional_breakdown_is_usable_without_claiming_final_tax():
    files = distribution_files(); out = R.sgov_distributions(files, '2026-10-29')
    assert out['periods'] == 12 and out['as_reported_total_distribution'] == '3.600000'
    assert out['as_reported_income_sum'] == '3.600000' and out['as_reported_roc_pct'] == '0'
    assert out['complete_source_breakdown'] and not out['complete_final_breakdown']
    assert out['provisional_issuer_components']
    assert Q.components({'trailing_12m_roc_pct': out['as_reported_roc_pct']}, 'US')[0]['distribution_quality_state'] == 'DISTRIBUTION_OK'
    text = distribution_source_text('SGOV', out)
    assert '每股總額 USD 3.600000' in text and '暫定' in text and '年度最終稅表' in text
    files['quality/sgov_fresh_20261029.xls'] = files['quality/sgov_fresh_20261029.xls'].replace(b'0.300000', b'0.300001', 1)
    with pytest.raises(PermissionError, match='XML_ROW_MISMATCH'): R.sgov_distributions(files, '2026-10-29')


def event_files():
    acc = '0001193125-25-000001'; doc = 'test.htm'
    url = 'https://www.sec.gov/Archives/edgar/data/1100663/000119312525000001/' + doc
    raw = b'<p>SGOV October 31, 2025 ICE US 1-Month Treasury Bill Index; prior cash did not earn any reinvestment income.</p>'
    event = {'ticker': 'SGOV', 'type': 'adopted_underlying_index_cash_flow_reinvestment_change',
        'source_url': url, 'document_date': '2025-10-31', 'materiality': 'not adjudicated',
        'approval_status': 'unknown', 'effective': 'after October 31, 2025 rebalancing'}
    coverage = {'review_period_start': '2025-10-29', 'review_period_end': '2026-10-29',
        'forms_screened': ['497'], 'filings_retrieved': 1, 'events': [event]}
    scan = [{'accession': acc, 'date': '2025-10-31', 'url': url, 'access': 'retrieved',
        'bytes': len(raw), 'SGOV_confirmed_match': True}]
    recent = {'accessionNumber': [acc], 'form': ['497'], 'filingDate': ['2025-10-31'],
        'acceptanceDateTime': ['2025-10-30T21:36:50.000Z'], 'primaryDocument': [doc]}
    return {'quality/sgov_bounded_event_coverage.json': json.dumps(coverage).encode(),
        'quality/sgov_497_scan.json': json.dumps(scan).encode(),
        'quality/sgov_submissions.json': json.dumps({'cik': '1100663', 'filings': {'recent': recent}}).encode(),
        'quality/' + acc + '.html.gz': gzip.compress(raw)}


def test_adopted_event_is_scoped_fact_without_materiality_approval_or_new_buy_gate():
    files = event_files(); out = R.sec_events(files); event = out['events'][0]
    assert event['materiality'] is None and event['internal_approval_status'] is None
    assert not event['automatic_buy_prohibition'] and not out['new_trade_gate_created']
    assert not out['all_forms_reviewed'] and not out['unqualified_no_event_assertion']
    assert event['sec_accepted_at'] != event['filing_date']
    facts = {'authorized_universe': True, 'abs_latest_premium_discount_pct': '0',
        'median_20d_abs_premium_discount_pct': '0'}
    assert Q.components(facts, 'US')[0]['structure_state'] == 'UNKNOWN'
    scan = json.loads(files['quality/sgov_497_scan.json']); scan.append(scan[0])
    files['quality/sgov_497_scan.json'] = json.dumps(scan).encode()
    with pytest.raises(PermissionError, match='SCAN_COVERAGE'): R.sec_events(files)


def sparse_files():
    html = ('<h2>Fund Characteristics <span>as of Oct 03 2023</span></h2>'
        '<table><tr><td>Yield to Maturity<div>tooltip 99%</div></td><td>6.19%</td></tr></table>'
        '<h2>Index Characteristics as of Oct 03 2023</h2>'
        '<table><tr><td>Yield to Maturity</td><td>99%</td></tr></table>'
        '<h2>Yields as of Oct 02 2023</h2>'
        '<table><tr><th>30 Day SEC Yield<span>tooltip</span></th><td>5.77%</td></tr></table>').encode()
    manifest = []; rows = []; files = {}
    for i, capture in enumerate(('20231004120000', '20231005120000')):
        path = f'raw{i}.html'; raw = gzip.compress(html) if i else html
        original = 'https://www.ssga.com/us/en/individual/etfs/funds/test-spsb'
        replay = 'https://web.archive.org/web/' + capture + 'id_/' + original
        manifest.append({'path': path, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw),
            'status': 200, 'capture_timestamp': capture, 'original_url': original, 'replay_url': replay})
        files['spsb_sparse_history/' + path] = raw
        for metric, day, value in [('portfolio_ytm', '2023-10-03', '6.19'), ('sec_yield_30day', '2023-10-02', '5.77')]:
            rows.append({'ticker': 'SPSB', 'metric': metric, 'as_of': day, 'value_percent': value,
                'raw_file': path, 'original_url': original, 'archive_replay_url': replay, 'capture_timestamp': capture})
    files['spsb_sparse_history/replay_manifest.json'] = json.dumps(manifest).encode()
    files['spsb_sparse_history/sparse_archived_issuer_yields.json'] = json.dumps(rows).encode()
    return files


def test_sparse_fund_yields_replay_exact_asof_and_keep_missing_weeks_missing():
    files = sparse_files(); out = R.sparse_yields(files, AT)
    assert out['raw_source_rows'] == 4 and out['distinct_observations'] == 2
    assert out['counts_by_metric'] == {'portfolio_ytm': 1, 'sec_yield_30day': 1}
    assert {r['as_of'] for r in out['observations']} == {'2023-10-03', '2023-10-02'}
    assert all(len(r['sources']) == 2 for r in out['observations'])
    assert not out['engine_input_eligible'] and not out['weekly_history_available']
    assert not out['missing_weeks_filled'] and not out['percentile_calculated']
    rows = json.loads(files['spsb_sparse_history/sparse_archived_issuer_yields.json']); rows[0]['value_percent'] = '99'
    files['spsb_sparse_history/sparse_archived_issuer_yields.json'] = json.dumps(rows).encode()
    with pytest.raises(PermissionError, match='EXTRACTION_MISMATCH'): R.sparse_yields(files, AT)


def test_archive_future_capture_and_changed_raw_bytes_fail():
    files = sparse_files()
    with pytest.raises(PermissionError, match='FUTURE_CAPTURE'): R.sparse_yields(files, '2023-10-03T12:00:00Z')
    files['spsb_sparse_history/raw0.html'] += b'changed'
    with pytest.raises(PermissionError, match='RAW_HASH'): R.sparse_yields(files, AT)


def auxiliary_files():
    previous = [{'ex_date': f'2026-{i:02d}-01', 'dividend': '.1', 'roc': None} for i in range(1, 13)]
    supplied = {'ticker': 'SPSB', 'roc_pct': None, 'roc_amount_USD_per_share': None,
        'issuer_reported_dividend_total_USD_per_share': '1.2',
        'rows': [{'EX-DATE': f'{i:02d}/01/2026', 'TICKER': 'SPSB', 'CUSIP': '78464A474', 'DIVIDEND ($)': '.1'} for i in range(1, 13)]}
    return {'quality/spsb_12payment_dividends_with_explicit_roc_null.json': json.dumps(supplied).encode(),
        'quality/spsb_qii_2026.csv': b'ticker,pay_date,qualified_interest_income_percent,ROC_percent\nSPSB,2026-10-06,81.28,\n',
        'quality/spsb_qii2026.txt': b'10/6/2026\n SPSB 81.28%',
        'quality/spsb_qii2026.pdf': b'SYNTHETIC PDF BYTES'}, previous


def test_qii_is_separate_from_roc_and_prior_tax_rows_are_not_replaced():
    files, previous = auxiliary_files(); before = deepcopy(previous)
    out = R.spsb_auxiliary(files, previous)
    assert previous == before and out['dividends']['roc_pct'] is None
    assert not out['qii']['roc_inferred'] and out['prior_year_final_tax_rows_preserved']
    assert not out['fiscal_year_fund_aggregate_mixed_with_per_share']
    files['quality/spsb_qii_2026.csv'] = files['quality/spsb_qii_2026.csv'].replace(b'81.28,', b'81.28,18.72')
    with pytest.raises(PermissionError, match='QII_IS_NOT_ROC'): R.spsb_auxiliary(files, previous)


def test_addendum_changes_distribution_only_and_does_not_create_spsb_pred008(tmp_path):
    from test_v75_etf_quality_inputs import formal_manifest
    import formal_v75_parameters as P
    import v75_macro_inputs as M
    # The ordinary issuer-quality path remains a prerequisite to this addendum.
    assert R.extend({}, None, {}, AT) == {}
    with pytest.raises(PermissionError, match='PRIOR_FORMAL_HANDOFF_REQUIRED'):
        R.extend({}, {'schema_version': 'unused'}, {}, AT)
    base = tmp_path / 'base'; base.mkdir()
    descriptor, manifest, expected = formal_manifest(base)
    with patch.object(P, 'PARAMETER_SHA256', expected):
        pool = M.read(descriptor, AT)
    files, previous = auxiliary_files()
    files.update(distribution_files()); files.update(event_files()); files.update(sparse_files())
    ready = tmp_path / 'ready'; ready.mkdir(); bound = source(ready, files)
    pool['source_handoff'] = {'source_reference': 'SYNTHETIC_PRIOR_HANDOFF'}
    pool['issuer_observations']['SPSB'] = {'facts': {'distribution_source_observation': {'rows': previous}}}
    before = deepcopy(pool['asset_metrics']['SPSB'].get('PRED-008'))
    data = {key: Path(item['local_path']).read_bytes() for key, item in manifest['sources'].items()}
    result = R.extend(pool, bound, data, AT)
    quality = result['etf_quality_assessments']['SGOV']
    assert quality['metrics']['distribution_quality_state'] == 'DISTRIBUTION_OK'
    assert quality['metrics']['structure_state'] == 'UNKNOWN'
    assert 'trailing_12m_roc_pct_with_complete_issuer_breakdown' not in quality['unprovided_inputs']
    assert quality['source_available_at'] == bound['ingested_at']
    assert result['asset_metrics']['SPSB'].get('PRED-008') == before
    assert result['source_handoff']['source_reference'] == 'SYNTHETIC_PRIOR_HANDOFF'
    assert result['ready_data_handoff']['spsb_distribution_and_qii']['dividends']['roc_pct'] is None
    assert not result['canonical_yield_observations']['SPSB']['sparse_audit_evidence']['engine_input_eligible']


def test_report_names_sparse_evidence_and_does_not_call_qii_roc():
    ready = {'sparse_yield_evidence': {'counts_by_metric': {'portfolio_ytm': 12, 'sec_yield_30day': 12}}}
    text = ''.join(ready_data_evidence_notes(ready, 'SPSB'))
    assert '12筆組合YTM' in text and '12筆30-Day SEC Yield' in text
    assert '未冒充五年完整週序列' in text and 'QII不是ROC' in text
