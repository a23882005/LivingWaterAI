"""Append raw-replayed IB audits, derived weeks and sparse issuer observations.

Connector response anomalies are not a diagnosis of the broker's backend.
Derived/independent-source prices never repair or overwrite the original bars.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

from v75_additional_delta_inputs import observation_key
from v75_handoff_inputs import csv_rows
from v75_plugin_data_inputs import daily_bars, ibkr_history, ohlcv, tool_response
from v75_ready_data_inputs import SparseYieldHTML, manifest_files
from v75_remaining_inputs import number, time

FIELDS = ('time', 'open', 'high', 'low', 'close', 'volume')


def week(row):
    return time(row['time']).date().isocalendar()[:2]


def series(raw_file, contract_id, step, evaluation_at):
    args, raw = tool_response(raw_file)
    if (args != {'contract_id': contract_id, 'security_type': 'STK', 'outside_rth': False,
            'period': 'FIVE_YEARS', 'step': step, 'include_corporate_actions': True}
            or raw['chart_step'] != (86400 if step == 'ONE_DAY' else 604800) or raw['source'] != 'Last'):
        raise PermissionError('IB_QA_REQUEST_OR_IDENTITY')
    if not raw['time'] or any(len(raw[k]) != len(raw['time']) for k in FIELDS):
        raise PermissionError('IB_QA_ARRAY_LENGTH')
    if raw['time'] != sorted(set(raw['time'])) or any(time(t) > time(evaluation_at) for t in raw['time']):
        raise PermissionError('IB_QA_TIMESTAMP_ORDER_OR_FUTURE')
    rows = [dict(zip(FIELDS, values)) for values in zip(*(raw[f] for f in FIELDS))]
    if any(number(r[f]) < 0 for r in rows for f in FIELDS[1:]):
        raise ValueError('IB_QA_NEGATIVE_VALUE')
    return rows


def valid(row):
    try:
        ohlcv(row[f] for f in FIELDS[1:]); return True
    except ValueError:
        return False


def audit(rows, *, weekly=False):
    out = {'counts': {f: len(rows) for f in FIELDS}, 'first': rows[0]['time'], 'last': rows[-1]['time'],
        'invalid_ohlc': [r for r in rows if not valid(r)], 'nonfinite_or_negative_values': [],
        'duplicate_timestamps': [], 'nonincreasing_timestamps': []}
    if weekly:
        groups = defaultdict(list)
        for row in rows: groups[str(tuple(week(row)))].append(row)
        out['duplicate_iso_weeks'] = {k: v for k, v in groups.items() if len(v) > 1}
    return out


def aggregate(rows):
    if not rows: raise PermissionError('IB_QA_EMPTY_AGGREGATE')
    return {'open': rows[0]['open'], 'high': max(r['high'] for r in rows),
        'low': min(r['low'] for r in rows), 'close': rows[-1]['close'],
        'volume': sum((number(r['volume']) for r in rows), Decimal(0))}


def text_numbers(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, list): return [text_numbers(v) for v in value]
    if isinstance(value, dict): return {k: text_numbers(v) for k, v in value.items()}
    return value


def ibkr_audit(files, previous, evaluation_at):
    """Independently recompute the supplied audit from every retained raw row."""
    original = {'ibkr/' + k.removeprefix('original_ibkr/'): v for k, v in files.items()
        if k.startswith('original_ibkr/')}
    report = {}; result = {}; daily_rows = {}
    for symbol in ('SGOV', 'SPSB'):
        prior = previous['ibkr_weekly'][symbol]
        if sha256(original['ibkr/' + symbol + '_5y_weekly_raw.json']).hexdigest() != prior['source_raw_sha256']:
            raise PermissionError('IB_QA_ORIGINAL_SOURCE_MISMATCH')
        replay = ibkr_history(original, symbol, evaluation_at)
        if replay != prior: raise PermissionError('IB_QA_PRIOR_REPLAY_MISMATCH')
        contract = prior['contract_id']
        old = series(original['ibkr/' + symbol + '_5y_weekly_raw.json'], contract, 'ONE_WEEK', evaluation_at)
        new = series(files['ibkr/' + symbol + '_ONE_WEEK_refetch.json'], contract, 'ONE_WEEK', evaluation_at)
        daily = series(files['ibkr/' + symbol + '_ONE_DAY_refetch.json'], contract, 'ONE_DAY', evaluation_at)
        if [r['time'] for r in old] != [r['time'] for r in new]:
            raise PermissionError('IB_QA_REFETCH_TIMESTAMP_COVERAGE')
        differences = [{'index': i, 'old': a, 'new': b} for i, (a, b) in enumerate(zip(old, new)) if a != b]
        affected = {week(r) for r in old if not valid(r)}
        if symbol == 'SPSB':
            affected.update(tuple(r['iso_week']) for r in prior['multiple_bars_per_iso_week'] if not r['latest_week'])
        windows = [r for r in daily if week(r) in affected]
        extracted = csv_rows(files['ibkr/' + symbol + '_affected_daily_windows.csv'])
        if len(extracted) != len(windows) or any(a['time'] != b['time'] or any(
                number(a[f]) != number(b[f]) for f in FIELDS[1:]) for a, b in zip(extracted, windows)):
            raise PermissionError('IB_QA_AFFECTED_WINDOW_CSV')
        evidence = [{'iso_week': list(w), 'provider_weekly': [r for r in new if week(r) == w],
            'daily_bars': [r for r in windows if week(r) == w],
            'daily_derived_ohlcv': aggregate([r for r in windows if week(r) == w])} for w in sorted(affected)]
        report[symbol] = {'raw_text_matches_structured': True, 'csv_matches_raw': True,
            'original_weekly_validation': audit(old, weekly=True), 'refetch_weekly_validation': audit(new, weekly=True),
            'refetch_weekly_row_differences': differences, 'daily_validation': audit(daily),
            'affected_week_daily_evidence': evidence}
        invalid = [r for r in old if not valid(r)]
        invalid_reproduced = [r for r in invalid if r in new]
        daily_rows[symbol] = daily
        result[symbol] = text_numbers({'daily_raw_bar_count': len(daily),
            'daily_first': daily[0]['time'], 'daily_last': daily[-1]['time'],
            'invalid_daily_bars': [r for r in daily if not valid(r)],
            'invalid_weekly_bars_reproduced': invalid_reproduced, 'refetch_weekly_row_differences': differences,
            'affected_week_daily_evidence': evidence, 'original_source_preserved': True,
            'root_cause_scope': 'ANOMALY_PRESENT_IN_CONNECTOR_RAW_RESPONSE__BACKEND_CAUSE_UNESTABLISHED',
            'chart_end_used_as_observation_date': False, 'latest_source_week_complete': False,
            'latest_daily_bar_completion_attested': False,
            'raw_daily_sha256': sha256(files['ibkr/' + symbol + '_ONE_DAY_refetch.json']).hexdigest(),
            'raw_weekly_sha256': sha256(files['ibkr/' + symbol + '_ONE_WEEK_refetch.json']).hexdigest()})
    if report != json.loads(files['ibkr/validation_report.json'], parse_float=Decimal):
        raise PermissionError('IB_QA_VALIDATION_REPORT_MISMATCH')
    return result, daily_rows


def derived_week(files, daily):
    import exchange_calendars as xc
    supplied = json.loads(files['SPSB_20230320_reconstructed.json'], parse_float=Decimal)
    start = date.fromisoformat(supplied['week_start']); end = date.fromisoformat(supplied['week_end'])
    if (supplied['symbol'] != 'SPSB' or supplied['status'] != 'DERIVED_RECONSTRUCTION'
            or start.weekday() != 0 or end != start+timedelta(days=4)):
        raise PermissionError('IB_QA_DERIVED_WEEK_IDENTITY')
    rows = [r for r in daily if start <= time(r['time']).date() <= end]
    cal = xc.get_calendar('XNYS', start=start, end=end)
    expected = [str(s.date()) for s in cal.sessions_in_range(str(start), str(end))]
    if [str(time(r['time']).date()) for r in rows] != expected or not all(valid(r) for r in rows):
        raise PermissionError('IB_QA_DERIVED_WEEK_INCOMPLETE_OR_INVALID')
    values = aggregate(rows)
    if any(number(supplied[f]) != number(v) for f, v in values.items()):
        raise PermissionError('IB_QA_DERIVED_VALUES_MISMATCH')
    _, weekly = tool_response(files['ibkr/SPSB_ONE_WEEK_refetch.json'])
    split = [dict(zip(FIELDS, r)) for r in zip(*(weekly[f] for f in FIELDS))
        if start <= time(r[0]).date() <= end]
    if len(split) != 2:
        raise PermissionError('IB_QA_DERIVED_SPLIT_COVERAGE')
    for i, row in enumerate(split):
        lower = time(row['time']).date()
        upper = time(split[i+1]['time']).date()-timedelta(days=1) if i+1 < len(split) else end
        segment = aggregate([r for r in rows if lower <= time(r['time']).date() <= upper])
        if any(number(row[f]) != number(v) for f,v in segment.items()):
            raise PermissionError('IB_QA_DERIVED_SPLIT_DAILY_MISMATCH')
    return text_numbers({'symbol': 'SPSB', 'week_start': str(start), 'week_end': str(end), **values,
        'status': 'DERIVED_RECONSTRUCTION', 'input_daily_bars': rows, 'all_expected_sessions_present': True,
        'split_provider_rows': split, 'split_rows_reconciled_to_daily_segments': True,
        'input_raw_sha256': sha256(files['ibkr/SPSB_ONE_DAY_refetch.json']).hexdigest(),
        'provider_corrected_weekly': False, 'original_weekly_bars_replaced': False,
        'canonical_market_source_replaced': False})


def massive_extension(files, previous, data, evaluation_at):
    out = {}; coverage = json.loads(files['massive/coverage_qa.json'])
    for symbol in ('SGOV', 'SPSB'):
        current = daily_bars(files['massive/' + symbol + '_5y_daily_raw.json'],
            files['massive/' + symbol + '_actual_daily.csv'], data['YAHOO_' + symbol], evaluation_at)
        qa = coverage[symbol]
        if (qa['rows'] != current['raw_bar_count'] or qa['actual_first'] != current['first_session_date']
                or qa['actual_last'] != current['last_session_date'] or qa['bad_ohlc'] != 0
                or date.fromisoformat(qa['requested_start']) >= date.fromisoformat(qa['actual_first'])):
            raise PermissionError('IB_QA_MASSIVE_COVERAGE')
        prior = previous['massive_daily'][symbol]['completed_daily_bars']
        index = {r['t']: r for r in current['completed_daily_bars']}
        if any(index.get(r['t']) != r for r in prior):
            raise PermissionError('IB_QA_MASSIVE_PRIOR_OVERLAP_MISMATCH')
        out[symbol] = {**current, 'symbol': symbol, 'requested_start': qa['requested_start'],
            'actual_is_full_requested_five_years': False, 'previous_daily_bars_reconciled': len(prior),
            'additional_daily_bars': len(current['completed_daily_bars'])-len(prior),
            'instrument_identity_basis': 'DELIVERED_FILENAME_AND_REQUEST_CONTEXT__NO_SYMBOL_ECHO_IN_RAW_CSV',
            'adjusted_request_reported_by_handoff': True, 'adjustment_basis': 'REPORTED_SPLIT_ONLY__NOT_DIVIDEND_REINVESTMENT',
            'per_call_request_args_retained': False, 'canonical_liquidity_qualified': False}
    checks = []
    for supplied in json.loads(files['massive/SGOV_two_week_crosscheck.json'], parse_float=Decimal):
        rows = [r for r in out['SGOV']['completed_daily_bars'] if supplied['week_start'] <= r['date_et'] <= supplied['week_end']]
        mapped = [{'time': r['date_et']+'T00:00:00Z', **{f: number(r[k]) for f, k in zip(FIELDS[1:], ('o','h','l','c','v'))}} for r in rows]
        values = aggregate(mapped)
        if ([r['date_et'] for r in rows] != supplied['dates'] or any(number(supplied[f]) != number(v) for f,v in values.items())):
            raise PermissionError('IB_QA_MASSIVE_WEEK_CROSSCHECK')
        checks.append({'week_start': supplied['week_start'], 'week_end': supplied['week_end'],
            **text_numbers(values), 'input_session_dates': supplied['dates'],
            'status': 'INDEPENDENT_SOURCE_DERIVED_CROSSCHECK', 'IBKR_correction': False,
            'session_trade_condition_volume_comparability_attested': False})
    out['SGOV']['derived_week_cross_checks'] = checks
    return out


def arquivo_yields(files, previous, source, evaluation_at):
    manifest = json.loads(files['yield/arquivo_replay_manifest.json'])
    supplied = json.loads(files['yield/arquivo_extracted_source_rows.json'], parse_float=Decimal)
    delta = json.loads(files['yield/DELTA_MANIFEST.json'])
    for r in delta['files']:
        raw = files['yield/' + r['path']]
        if len(raw) != r['bytes'] or sha256(raw).hexdigest() != r['sha256']:
            raise PermissionError('IB_QA_YIELD_DELTA_HASH')
    actual = []; sources = {}
    for proof in manifest:
        path = proof['path']; raw = files['yield/' + path]
        captured = datetime.strptime(proof['capture_timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        allowed = ['https://ssga.com/us/en/' + audience + '/etfs/funds/spdr-portfolio-short-term-corporate-bond-etf-spsb'
            for audience in ('individual', 'intermediary')]
        if (path in sources or proof['status'] != 200 or sha256(raw).hexdigest() != proof['sha256']
                or proof['original_url'] not in allowed or proof['url'] !=
                'https://arquivo.pt/noFrame/replay/' + proof['capture_timestamp'] + 'id_/' + proof['original_url']
                or captured > time(evaluation_at)):
            raise PermissionError('IB_QA_ARQUIVO_SOURCE')
        parser = SparseYieldHTML(); parser.feed(raw.decode('utf-8'))
        for metric, day, value in parser.observations:
            if day > str(captured.date()): raise PermissionError('IB_QA_YIELD_ASOF_AFTER_CAPTURE')
            actual.append((metric, day, number(value), path))
        sources[path] = proof
    if Counter(actual) != Counter((r['metric'], r['as_of'], number(r['value_percent']), r['raw_file']) for r in supplied):
        raise PermissionError('IB_QA_YIELD_EXTRACTION_MISMATCH')
    merged = {(r['metric'], r['as_of']): deepcopy(r) for r in previous['observations']}; unique = {}
    def source_key(r):
        return r['capture_timestamp'], r['original_url'], r.get('archive_replay_url', r.get('url')), r['raw_file'].split('/')[-1]
    for row in supplied:
        proof = sources[row['raw_file']]
        if row['ticker'] != 'SPSB' or source_key(row) != source_key({**proof, 'raw_file': proof['path']}):
            raise PermissionError('IB_QA_YIELD_RECEIPT_MISMATCH')
        key = (row['metric'], row['as_of'])
        target = unique.setdefault(key, {k: deepcopy(row[k]) for k in ('metric', 'as_of', 'value_percent')})
        if number(target['value_percent']) != number(row['value_percent']):
            raise PermissionError('IB_QA_YIELD_SAME_DATE_VALUE_CONFLICT')
        target.setdefault('sources', []).append({**proof, 'archive_replay_url': proof['url'],
            'raw_file': 'yield/' + proof['path'], 'origin_source_root': source['root'],
            'origin_handoff_manifest_sha256': source['manifest_sha256']})
    delivered = json.loads(files['yield/NEW_ARQUIVO_OBSERVATIONS.json'], parse_float=Decimal)
    if len(delivered) != len(unique) or {observation_key(r) for r in delivered} != {observation_key(r) for r in unique.values()}:
        raise PermissionError('IB_QA_YIELD_UNIQUE_SET')
    for row in delivered:
        if row['ticker'] != 'SPSB' or Counter(map(source_key, row['sources'])) != Counter(map(source_key, unique[(row['metric'],row['as_of'])]['sources'])):
            raise PermissionError('IB_QA_YIELD_UNIQUE_PROOFS')
    new_count = 0; added_source_rows = 0
    for key, row in unique.items():
        if key in merged and number(merged[key]['value_percent']) != number(row['value_percent']):
            raise PermissionError('IB_QA_YIELD_SAME_DATE_VALUE_CONFLICT')
        if key not in merged: merged[key] = {k: deepcopy(v) for k,v in row.items() if k != 'sources'}; new_count += 1
        target = merged[key]; target['value_percent'] = str(number(target['value_percent']))
        target.setdefault('sources', [])
        seen = {source_key(r) for r in target['sources']}
        for proof in row['sources']:
            if source_key(proof) not in seen:
                target['sources'].append(deepcopy(proof)); seen.add(source_key(proof)); added_source_rows += 1
    if delta['new_unique_metric_observations'] != len(unique) or delta['qualified_weekly_series'] is not False:
        raise PermissionError('IB_QA_YIELD_DELTA_DECLARATION')
    observations = sorted(merged.values(), key=lambda r: (r['metric'],r['as_of']))
    summary = {'baseline_unique_metric_observations': previous['distinct_observations'],
        'new_unique_metric_observations': new_count, 'replayed_source_rows': len(supplied),
        'cumulative_unique_metric_observations': len(observations), 'deduplication_key': ['ticker','metric','as_of'],
        'same_date_value_conflicts': [], 'not_a_qualified_weekly_series': True, 'per_metric': {}}
    for metric in ('portfolio_ytm','sec_yield_30day'):
        days = sorted(date.fromisoformat(r['as_of']) for r in observations if r['metric'] == metric)
        summary['per_metric'][metric] = {'cumulative_unique_observations': len(days),
            'first_as_of': str(days[0]), 'last_as_of': str(days[-1]),
            'unique_ISO_weeks': len({d.isocalendar()[:2] for d in days}),
            'largest_gap_days': max(((b-a).days for a,b in zip(days,days[1:])), default=0)}
    return text_numbers({**deepcopy(previous), 'observations': observations, 'distinct_observations': len(observations),
        'counts_by_metric': dict(Counter(r['metric'] for r in observations)), 'delta_summary': summary,
        'raw_source_rows': previous['raw_source_rows'] + added_source_rows,
        'weekly_history_available': False, 'engine_input_eligible': False, 'capture_date_used_as_asof': False})


def extend(pool, source, data, evaluation_at):
    if source is None: return pool
    prior = pool.get('plugin_data_cross_checks'); delta = pool.get('additional_delta_handoff')
    if not prior or not delta: raise PermissionError('IB_QA_PRIOR_EVIDENCE_REQUIRED')
    files = manifest_files(source, evaluation_at, schema='Family.W8.V75IBQAAdditionalSource.v1',
        manifest_name='manifest.json', size_field='bytes')
    audits, daily = ibkr_audit(files, prior, evaluation_at)
    receipt = {'schema_version': 'Family.W8.VerifiedV75IBQAAdditional.v1',
        'manifest_sha256': source['manifest_sha256'], 'source_reference': source['source_reference'],
        'source_available_at': source['ingested_at'], 'raw_files_verified': len(files), 'ibkr_audit': audits,
        'SPSB_derived_week': derived_week(files, daily['SPSB']),
        'massive_daily': massive_extension(files, prior, data, evaluation_at),
        'sparse_yield_evidence': arquivo_yields(files, delta['sparse_yield_evidence'], source, evaluation_at),
        'primary_financial_inputs_changed': False, 'issuer_composition_overwritten': False,
        'NBBO_quotes_acquired': False, 'qualified_weekly_YTM_or_SEC_history_supplied': False, 'trade_action': 'NO_TRADE'}
    pool['ib_qa_handoff'] = receipt
    pool['canonical_yield_observations']['SPSB']['sparse_audit_evidence'] = deepcopy(receipt['sparse_yield_evidence'])
    pool['auxiliary_evidence_available_at'] = source['ingested_at']
    pool.setdefault('auxiliary_source_proofs', {})['IB_QA_ADDITIONAL_HANDOFF'] = {
        'source_reference': source['source_reference'], 'source_sha256': source['manifest_sha256'], 'available_at': source['ingested_at']}
    return pool


def summary(evidence, symbol):
    audit = evidence['ibkr_audit'][symbol]; daily = evidence['massive_daily'][symbol]
    out = {'manifest_sha256': evidence['manifest_sha256'], 'source_available_at': evidence['source_available_at'],
        'IBKR_invalid_weekly_reproduced': len(audit['invalid_weekly_bars_reproduced']),
        'IBKR_daily_raw_bars': audit['daily_raw_bar_count'], 'IBKR_invalid_daily_bars': len(audit['invalid_daily_bars']),
        'Massive_daily_bars': daily['raw_bar_count'], 'Massive_actual_first': daily['first_session_date'],
        'Massive_actual_last': daily['last_session_date'], 'Massive_full_five_years': False,
        'Massive_prior_bars_reconciled': daily['previous_daily_bars_reconciled'],
        'Massive_missing_sessions': daily['missing_session_dates_within_actual_range'],
        'daily_price_overlap': daily['overlap_count'], 'daily_four_decimal_close_matches': daily['four_decimal_close_matches'],
        'primary_financial_inputs_changed': False, 'NBBO_quotes_acquired': False}
    if symbol == 'SPSB': out['derived_week'] = deepcopy(evidence['SPSB_derived_week'])
    else: out['independent_derived_week_cross_checks'] = deepcopy(daily['derived_week_cross_checks'])
    return out
