"""Append verified issuer evidence without replacing earlier handoff sources.

Distribution completeness and tax finality are separate. Bounded SEC review,
QII and sparse archived yields remain evidence with their own limited scope;
none supplies an approval, a full weekly history or historical NBBO quotes.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import gzip
import json
import re

from v75_handoff_inputs import amount, csv_rows, distribution_window, iso, xml
from v75_remaining_inputs import number, time


def manifest_files(source, evaluation_at):
    if (source.get('schema_version') != 'Family.W8.V75ReadyDataSource.v1'
            or time(source['ingested_at']) > time(evaluation_at)):
        raise PermissionError('READY_DATA_SCHEMA_OR_AVAILABILITY')
    root = Path(source['root']).resolve()
    raw = (root / 'PACKAGE_MANIFEST.json').read_bytes()
    if sha256(raw).hexdigest() != source['manifest_sha256']:
        raise PermissionError('READY_DATA_MANIFEST_HASH')
    files = {}
    for item in json.loads(raw):
        path = PurePosixPath(item['path'])
        local = (root / str(path)).resolve()
        if (path.is_absolute() or '..' in path.parts or not local.is_relative_to(root)
                or str(path) in files):
            raise PermissionError('READY_DATA_MANIFEST_PATH')
        content = local.read_bytes()
        if len(content) != item['size'] or sha256(content).hexdigest() != item['sha256']:
            raise PermissionError('READY_DATA_SOURCE_HASH:' + str(path))
        files[str(path)] = content
    return files


def sgov_distributions(files, observed_date):
    root = xml(files['quality/sgov_fresh_20261029.xls'], True)
    sheet = next(s for s in root.findall('{*}Worksheet')
        if s.attrib.get('{urn:schemas-microsoft-com:office:spreadsheet}Name') == 'Distributions')
    rows = [[c.find('{*}Data').text if c.find('{*}Data') is not None else ''
        for c in row] for row in sheet.findall('{*}Table/{*}Row')]
    header = rows[0]
    original = {r[1]: dict(zip(header, r)) for r in rows[1:] if len(r) == len(header)}
    delivered = json.loads(files['quality/sgov_provisional_12payment_decomposition.json'])
    if delivered['ticker'] != 'SGOV' or delivered['currency'] != 'USD':
        raise PermissionError('READY_DATA_DISTRIBUTION_IDENTITY')
    extracted = csv_rows(files['quality/sgov_12_distributions_fresh.csv'])
    if extracted != delivered['rows']:
        raise PermissionError('READY_DATA_SGOV_JSON_CSV_MISMATCH')
    normalized = []
    for row in extracted:
        raw = original.get(row['Ex-Date'])
        if raw is None or any(row[k] != raw[k] for k in header[:3]) or any(
                amount(row[k]) != amount(raw[k]) for k in header[3:]):
            raise PermissionError('READY_DATA_SGOV_XML_ROW_MISMATCH')
        total = number(raw['Total Distribution'])
        if total != sum((number(raw[k]) for k in header[4:]), Decimal(0)):
            raise PermissionError('READY_DATA_SGOV_COMPONENT_SUM')
        day = iso(row['Ex-Date'], '%b %d, %Y')
        normalized.append({'ex_date': day, 'total': str(total), 'income': amount(raw['Income']),
            'roc': amount(raw['Return of Capital']), 'final_tax_characterization': False,
            'characterization': 'PROVISIONAL_ISSUER_DISPLAY' if day[:4] == '2026' else 'ISSUER_PRIOR_YEAR_DISPLAY'})
    window = distribution_window(normalized, observed_date)
    expected = {iso(d, '%b %d, %Y') for d in original
        if window['period_start_exclusive'] < iso(d, '%b %d, %Y') <= observed_date}
    if {r['ex_date'] for r in normalized} != expected:
        raise PermissionError('READY_DATA_SGOV_TRAILING_COVERAGE')
    for key in header[3:]:
        if sum((number(r[key]) for r in extracted), Decimal(0)) != number(delivered['per_share_totals'][key]):
            raise PermissionError('READY_DATA_SGOV_TOTAL_MISMATCH')
    if number(window['as_reported_roc_pct']) != number(delivered['roc_amount_weighted_pct']):
        raise PermissionError('READY_DATA_SGOV_ROC_MISMATCH')
    window.update(currency='USD', amount_basis='PER_SHARE',
        as_reported_income_sum=str(sum((number(r['income']) for r in normalized), Decimal(0))),
        source_raw_sha256=sha256(files['quality/sgov_fresh_20261029.xls']).hexdigest(),
        source_reference=delivered['source'], tax_finality=delivered['tax_finality'])
    return window


def sec_events(files):
    coverage = json.loads(files['quality/sgov_bounded_event_coverage.json'])
    scan = json.loads(files['quality/sgov_497_scan.json'])
    submissions = json.loads(files['quality/sgov_submissions.json'])
    recent = submissions['filings']['recent']
    records = {recent['accessionNumber'][i]: {k: v[i] for k, v in recent.items()}
        for i in range(len(recent['accessionNumber']))
        if recent['form'][i] == '497' and coverage['review_period_start'] <= recent['filingDate'][i] <= coverage['review_period_end']}
    if (str(submissions['cik']).lstrip('0') != '1100663'
            or coverage['forms_screened'] != ['497']
            or len(scan) != len(records) or len(scan) != coverage['filings_retrieved']
            or len({r['accession'] for r in scan}) != len(scan)
            or set(records) != {r['accession'] for r in scan}):
        raise PermissionError('READY_DATA_SEC_SCAN_COVERAGE')
    for row in scan:
        record = records[row['accession']]
        expected = ('https://www.sec.gov/Archives/edgar/data/1100663/'
            + row['accession'].replace('-', '') + '/' + record['primaryDocument'])
        if row['access'] != 'retrieved' or row['date'] != record['filingDate'] or row['url'] != expected:
            raise PermissionError('READY_DATA_SEC_SCAN_IDENTITY')
    events = []
    for event in coverage['events']:
        match = next((r for r in scan if r['url'] == event['source_url'] and r['SGOV_confirmed_match']), None)
        if event['ticker'] != 'SGOV' or match is None:
            raise PermissionError('READY_DATA_SEC_EVENT_IDENTITY')
        name = 'quality/' + match['accession'] + '.html.gz'
        raw = gzip.decompress(files[name])
        if len(raw) != match['bytes'] or b'SGOV' not in raw:
            raise PermissionError('READY_DATA_SEC_EVENT_RAW')
        parser = TextHTML(); parser.feed(raw.decode('utf-8'))
        text = ' '.join(parser.text.split())
        if event['type'] == 'adopted_underlying_index_cash_flow_reinvestment_change':
            if not all(s in text for s in ('October 31, 2025', 'ICE US 1-Month Treasury Bill Index', 'did not earn any reinvestment income')):
                raise PermissionError('READY_DATA_SEC_ADOPTED_METHOD')
        elif event['type'] == 'primary_listing_venue_change':
            if not all(s in text for s in ('January 16, 2026', 'February 23, 2026', 'New York Stock Exchange', 'NYSE Arca')):
                raise PermissionError('READY_DATA_SEC_LISTING_NOTICE')
        else:
            raise PermissionError('READY_DATA_SEC_EVENT_TYPE')
        record = records[match['accession']]
        events.append({**deepcopy(event), 'filing_date': record['filingDate'],
            'sec_accepted_at': record['acceptanceDateTime'], 'raw_sha256': sha256(raw).hexdigest(),
            'materiality': None, 'internal_approval_status': None,
            'automatic_buy_prohibition': False})
    return {**coverage, 'events': events, 'filing_index': scan,
        'locally_retained_matched_primary_documents': len(events),
        'review_evidence_basis': 'DELIVERED_RETRIEVAL_INDEX_RECONCILED_TO_SEC_SUBMISSIONS; MATCHED_RAW_DOCUMENTS_REPLAYED',
        'all_forms_reviewed': False, 'unnamed_trust_effects_fully_covered': False,
        'unqualified_no_event_assertion': False, 'new_trade_gate_created': False}


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.text = ''

    def handle_data(self, value):
        self.text += ' ' + value


class SparseYieldHTML(HTMLParser):
    """Read dated fund sections; ignore index sections and nested label tooltips."""
    def __init__(self):
        super().__init__(); self.depth = 0; self.heading = None; self.current = None
        self.cells = None; self.cell = None; self.observations = []

    def handle_starttag(self, tag, attrs):
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.depth += 1
        if tag == 'h2': self.heading = ''
        if tag == 'tr': self.cells = []
        if tag in ('td', 'th') and self.cells is not None:
            self.cell = {'depth': self.depth, 'direct': '', 'all': ''}

    def handle_endtag(self, tag):
        if tag == 'h2' and self.heading is not None:
            heading = ' '.join(self.heading.split()); self.current = None
            metric = ('portfolio_ytm' if heading.startswith('Fund Characteristics') else
                'sec_yield_30day' if heading.startswith('Yields') else None)
            found = re.search(r'as of ([A-Z][a-z]{2} \d{1,2} \d{4})', heading)
            if metric and found: self.current = (metric, iso(found[1], '%b %d %Y'))
            self.heading = None
        if tag in ('td', 'th') and self.cell is not None:
            self.cells.append(self.cell); self.cell = None
        if tag == 'tr' and self.cells is not None:
            if self.current and len(self.cells) == 2:
                label = ' '.join(self.cells[0]['direct'].split())
                value = ' '.join(self.cells[1]['all'].split())
                expected = 'Yield to Maturity' if self.current[0] == 'portfolio_ytm' else '30 Day SEC Yield'
                if label == expected and re.fullmatch(r'\d+(\.\d+)?%', value):
                    self.observations.append((self.current[0], self.current[1], str(number(value[:-1]))))
            self.cells = None
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.depth -= 1

    def handle_data(self, value):
        if self.heading is not None: self.heading += value
        if self.cell is not None:
            self.cell['all'] += value
            if self.depth == self.cell['depth']: self.cell['direct'] += value


def sparse_yields(files, evaluation_at):
    manifest = json.loads(files['spsb_sparse_history/replay_manifest.json'])
    supplied = json.loads(files['spsb_sparse_history/sparse_archived_issuer_yields.json'], parse_float=Decimal)
    actual = []
    for source in manifest:
        key = 'spsb_sparse_history/' + source['path']; raw = files[key]
        if source['status'] != 200 or len(raw) != source['bytes'] or sha256(raw).hexdigest() != source['sha256']:
            raise PermissionError('READY_DATA_SPARSE_RAW_HASH')
        captured = datetime.strptime(source['capture_timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        if captured > time(evaluation_at):
            raise PermissionError('READY_DATA_SPARSE_FUTURE_CAPTURE')
        if (not source['original_url'].startswith('https://www.ssga.com/us/en/')
                or not source['original_url'].split('?')[0].endswith('-spsb')
                or source['replay_url'] != 'https://web.archive.org/web/' + source['capture_timestamp'] + 'id_/' + source['original_url']):
            raise PermissionError('READY_DATA_SPARSE_SOURCE_IDENTITY')
        content = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        parser = SparseYieldHTML(); parser.feed(content.decode('utf-8'))
        for metric, day, value in parser.observations:
            if day > str(captured.date()): raise PermissionError('READY_DATA_SPARSE_ASOF_AFTER_CAPTURE')
            actual.append((metric, day, number(value), source['path']))
    expected = [(r['metric'], r['as_of'], number(r['value_percent']), r['raw_file']) for r in supplied]
    if any(r['ticker'] != 'SPSB' for r in supplied) or Counter(actual) != Counter(expected):
        raise PermissionError('READY_DATA_SPARSE_EXTRACTION_MISMATCH')
    sources = {r['path']: r for r in manifest}; unique = {}
    for row in supplied:
        source = sources[row['raw_file']]
        if (row['original_url'] != source['original_url'] or row['archive_replay_url'] != source['replay_url']
                or row['capture_timestamp'] != source['capture_timestamp']):
            raise PermissionError('READY_DATA_SPARSE_RECEIPT_MISMATCH')
        key = (row['metric'], row['as_of'], str(number(row['value_percent'])))
        item = unique.setdefault(key, {'metric': key[0], 'as_of': key[1], 'value_percent': key[2], 'sources': []})
        item['sources'].append({**deepcopy(source), 'raw_file': 'spsb_sparse_history/' + source['path']})
    verified = sorted(unique.values(), key=lambda r: (r['metric'], r['as_of']))
    return {'ticker': 'SPSB', 'observations': verified, 'raw_source_rows': len(supplied),
        'distinct_observations': len(verified), 'counts_by_metric': dict(Counter(r['metric'] for r in verified)),
        'status': 'SPARSE_ARCHIVED_ISSUER_OBSERVATION_NOT_WEEKLY_SERIES',
        'weekly_history_available': False, 'engine_input_eligible': False,
        'engine_use_entitlement_verified': False, 'capture_date_used_as_asof': False,
        'missing_weeks_filled': False, 'percentile_calculated': False}


def spsb_auxiliary(files, previous_rows):
    supplied = json.loads(files['quality/spsb_12payment_dividends_with_explicit_roc_null.json'])
    old = {r['ex_date']: r for r in previous_rows}
    if supplied['ticker'] != 'SPSB' or supplied['roc_pct'] is not None or supplied['roc_amount_USD_per_share'] is not None:
        raise PermissionError('READY_DATA_SPSB_ROC_NOT_PROVIDED')
    total = Decimal(0)
    for row in supplied['rows']:
        original = old.get(iso(row['EX-DATE'], '%m/%d/%Y'))
        if original is None or row['TICKER'] != 'SPSB' or row['CUSIP'] != '78464A474' or number(row['DIVIDEND ($)']) != number(original['dividend']):
            raise PermissionError('READY_DATA_SPSB_PRIOR_RAW_RECONCILIATION')
        total += number(row['DIVIDEND ($)'])
    dates = {iso(row['EX-DATE'], '%m/%d/%Y') for row in supplied['rows']}
    if len(supplied['rows']) != 12 or len(dates) != 12 or dates != set(old) or total != number(supplied['issuer_reported_dividend_total_USD_per_share']):
        raise PermissionError('READY_DATA_SPSB_DIVIDEND_TOTAL')
    qii = csv_rows(files['quality/spsb_qii_2026.csv'])
    text = files['quality/spsb_qii2026.txt'].decode('utf-8')
    line = next(line for line in text.splitlines() if re.search(r'\bSPSB\s+\d', line))
    values = re.findall(r'(\d+(?:\.\d+)?)%', line)
    if values != [r['qualified_interest_income_percent'] for r in qii]:
        raise PermissionError('READY_DATA_SPSB_QII_TEXT_MISMATCH')
    for row in qii:
        if row['ticker'] != 'SPSB' or row['ROC_percent'] != '':
            raise PermissionError('READY_DATA_QII_IS_NOT_ROC')
        day = datetime.strptime(row['pay_date'], '%Y-%m-%d')
        if f'{day.month}/{day.day}/{day.year}' not in text:
            raise PermissionError('READY_DATA_QII_PAYMENT_DATE')
    return {'dividends': supplied, 'qii': {'rows': qii,
        'tax_basis': 'QUALIFIED_INTEREST_INCOME_FOR_NON_RESIDENT_WITHHOLDING__NOT_ROC',
        'subject_to_change': True, 'roc_inferred': False,
        'source_pdf_sha256': sha256(files['quality/spsb_qii2026.pdf']).hexdigest()},
        'prior_year_final_tax_rows_preserved': True, 'fiscal_year_fund_aggregate_mixed_with_per_share': False}


def extend(pool, source, data, evaluation_at):
    if source is None: return pool
    if not pool.get('formal_parameters') or not pool.get('source_handoff'):
        raise PermissionError('READY_DATA_PRIOR_FORMAL_HANDOFF_REQUIRED')
    files = manifest_files(source, evaluation_at)
    previous = {symbol: issuer['facts'].get('distribution_source_observation')
        for symbol, issuer in pool.get('issuer_observations', {}).items()}
    if not previous.get('SPSB'): raise PermissionError('READY_DATA_PRIOR_SPSB_ROWS_REQUIRED')
    from v75_etf_quality_inputs import assess
    sgov = sgov_distributions(files, time(evaluation_at).date().isoformat())
    events = sec_events(files)
    for evidence in (sgov, events):
        evidence.update(source_manifest_sha256=source['manifest_sha256'], source_available_at=source['ingested_at'])
    sparse = sparse_yields(files, evaluation_at)
    auxiliary = spsb_auxiliary(files, previous['SPSB']['rows'])
    receipt = {'schema_version': 'Family.W8.VerifiedV75ReadyData.v1',
        'manifest_sha256': source['manifest_sha256'], 'source_available_at': source['ingested_at'],
        'source_reference': 'OWNER_ATTACHED_V75_READY_DATA_20261029', 'raw_files_verified': len(files),
        'prior_sources_preserved': True, 'trade_action': 'NO_TRADE'}
    pool['ready_data_handoff'] = {**receipt, 'bounded_event_coverage': events,
        'sparse_yield_evidence': sparse, 'spsb_distribution_and_qii': auxiliary}
    pool['source_proofs']['READY_DATA_HANDOFF'] = {'source_sha256': source['manifest_sha256'],
        'available_at': source['ingested_at'], 'source_reference': receipt['source_reference']}
    pool['available_at'] = max(pool['available_at'], source['ingested_at'], key=time)
    pool.setdefault('distribution_source_observations', {})['SGOV'] = deepcopy(sgov)
    issuer = pool.get('issuer_observations', {}).get('SGOV')
    if issuer:
        issuer['facts']['distribution_source_observation'] = deepcopy(sgov)
        issuer['facts']['bounded_event_coverage'] = deepcopy(events)
        old = pool['etf_quality_assessments']['SGOV']
        assessment = assess(issuer, pool.get('qualified_bond_markets', {}).get('SGOV'),
            data.get('YAHOO_SGOV'), pool['formal_parameters'], evaluation_at,
            authorized_universe=old['normalized_facts']['authorized_universe'])
        pool['etf_quality_assessments']['SGOV'] = assessment
        pool['asset_metrics']['SGOV']['PRED-010'] = assessment['metrics']
        pool['calculations']['SGOV.PRED-010'] = assessment
        pool['asset_unprovided_inputs']['SGOV']['PRED-010'] = assessment['unprovided_inputs']
    pool.setdefault('canonical_yield_observations', {}).setdefault('SPSB', {})['sparse_audit_evidence'] = sparse
    return pool
