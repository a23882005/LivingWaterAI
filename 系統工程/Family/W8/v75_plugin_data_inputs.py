"""Replay plugin market/dividend evidence as independent cross-checks.

Issuer composition and primary qualified daily data retain their authority.
Weekly bars, cash dividends and distribution yields do not supply YTM, SEC
yield, total-return wealth or historical NBBO inputs.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from hashlib import sha256
from zoneinfo import ZoneInfo
import csv
import io
import json

from v75_handoff_inputs import csv_rows, iso
from v75_ready_data_inputs import manifest_files
from v75_remaining_inputs import number, time


def tool_response(raw):
    envelope = json.loads(raw, parse_float=Decimal)
    result = envelope.get('result', envelope)
    if result.get('isError') is not False or not isinstance(result.get('structuredContent'), dict):
        raise PermissionError('PLUGIN_DATA_TOOL_RESULT_UNAVAILABLE')
    structured = result['structuredContent']
    texts = [r['text'] for r in result.get('content', []) if r.get('type') == 'text']
    if len(texts) != 1:
        raise PermissionError('PLUGIN_DATA_RAW_TEXT_REQUIRED')
    if 'result' in structured and isinstance(structured['result'], str):
        if texts[0] != structured['result']:
            raise PermissionError('PLUGIN_DATA_RAW_STRUCTURED_MISMATCH')
    elif json.loads(texts[0], parse_float=Decimal) != structured:
        raise PermissionError('PLUGIN_DATA_RAW_STRUCTURED_MISMATCH')
    return envelope.get('args'), structured


def ohlcv(values):
    o, h, l, c, v = map(number, values)
    if min(o, h, l, c) <= 0 or h < max(o, l, c) or l > min(o, h, c) or v < 0:
        raise ValueError('PLUGIN_DATA_INVALID_OHLCV')
    return [str(x) for x in (o, h, l, c, v)]


def ibkr_history(files, symbol, evaluation_at):
    import exchange_calendars as xc
    prefix = 'ibkr/' + symbol
    args, raw = tool_response(files[prefix + '_5y_weekly_raw.json'])
    _, contracts = tool_response(files[prefix + '_contracts.json'])
    matches = [r for r in contracts['results'] if r.get('symbol') == symbol and r.get('country_code') == 'US'
        and any(s.get('security_type') == 'STK' for s in r.get('sections', []))]
    if (len(matches) != 1 or args != {'contract_id': matches[0]['underlying_contract_id'],
            'security_type': 'STK', 'outside_rth': False, 'period': 'FIVE_YEARS',
            'step': 'ONE_WEEK', 'include_corporate_actions': True}
            or raw['chart_step'] != 604800 or raw['source'] != 'Last'):
        raise PermissionError('PLUGIN_DATA_IBKR_IDENTITY_OR_REQUEST')
    extracted = csv_rows(files[prefix + '_5y_weekly.csv'])
    if any(len(raw[k]) != len(raw['time']) for k in ('open', 'high', 'low', 'close', 'volume')) or len(extracted) != len(raw['time']):
        raise PermissionError('PLUGIN_DATA_IBKR_ARRAY_COVERAGE')
    if raw['time'] != sorted(set(raw['time'])):
        raise ValueError('PLUGIN_DATA_IBKR_TIMESTAMP_ORDER')
    days = [time(t).date() for t in raw['time']]
    if not days or max(days) > time(evaluation_at).date():
        raise PermissionError('PLUGIN_DATA_IBKR_FUTURE_BAR')
    cal = xc.get_calendar('XNYS', start=min(days)-timedelta(days=7), end=max(days)+timedelta(days=7))
    grouped = defaultdict(list); rows = []
    for i, stamp in enumerate(raw['time']):
        values = [str(number(raw[k][i])) for k in ('open', 'high', 'low', 'close', 'volume')]
        try:
            ohlcv(values); valid = True
        except ValueError:
            valid = False
        row = extracted[i]
        if row['time'] != stamp or list(map(number, values)) != [number(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')]:
            raise PermissionError('PLUGIN_DATA_IBKR_CSV_MISMATCH')
        item = {'provider_timestamp': stamp, 'provider_label_date': str(days[i]),
            **dict(zip(('open', 'high', 'low', 'close', 'volume'), values)), 'ohlcv_valid': valid}
        grouped[days[i].isocalendar()[:2]].append(item); rows.append(item)
    latest_week = max(days).isocalendar()[:2]
    qa = json.loads(files['ibkr/qa.json'])[symbol + '_5y_weekly.csv']
    if (qa['rows'] != len(rows) or qa['first'] != raw['time'][0] or qa['last'] != raw['time'][-1]
            or qa.get('latest_week_incomplete') is not True):
        raise PermissionError('PLUGIN_DATA_IBKR_QA_MISMATCH')
    ambiguous = []; excluded = []; completed = []
    for week, items in sorted(grouped.items()):
        monday = date.fromisocalendar(week[0], week[1], 1)
        sessions = cal.sessions_in_range(str(monday), str(monday+timedelta(days=4)))
        ended = bool(len(sessions)) and cal.session_close(sessions[-1]).to_pydatetime() <= time(evaluation_at)
        reason = 'LATEST_SOURCE_WEEK_INCOMPLETE' if week == latest_week else 'WEEK_NOT_COMPLETE_AT_EVALUATION' if not ended else None
        if len(items) > 1:
            ambiguous.append({'iso_week': list(week), 'provider_timestamps': [r['provider_timestamp'] for r in items],
                'latest_week': week == latest_week, 'merged_or_silently_deduplicated': False})
            reason = reason or 'MULTIPLE_PROVIDER_BARS_IN_HISTORICAL_WEEK'
        for item in items:
            exclusion = reason or ('INVALID_OHLCV' if not item['ohlcv_valid'] else None)
            item['completed_unique_week_eligible'] = exclusion is None
            if exclusion: excluded.append({'provider_timestamp': item['provider_timestamp'], 'reason': exclusion})
            else: completed.append(item)
    dividends = []
    for event in raw['corp_actions']:
        if event['type'] != 'CashDividends' or event['currency'] != 'USD' or number(event['value']) <= 0:
            raise ValueError('PLUGIN_DATA_IBKR_DIVIDEND_KIND')
        dividends.append({'ex_date': iso(event['date'], '%Y%m%d'), 'pay_date': iso(event['payment_date'], '%Y%m%d')
            if event.get('payment_date') else None, 'amount': str(number(event['value'])), 'roc': None})
    return {'symbol': symbol, 'contract_id': matches[0]['underlying_contract_id'], 'exchange': matches[0]['exchange'],
        'raw_bar_count': len(rows), 'bars': rows, 'usable_unique_completed_weeks': len(completed),
        'excluded_bars': excluded, 'multiple_bars_per_iso_week': ambiguous,
        'invalid_ohlcv_bars': [deepcopy(r) for r in rows if not r['ohlcv_valid']],
        'last_observed_provider_timestamp': raw['time'][-1], 'provider_chart_end': raw['chart_end'],
        'chart_end_used_as_observed_date': False, 'provider_midnight_labels_shifted_to_previous_ET_date': False,
        'dividend_events': dividends, 'dividend_count': len(dividends),
        'daily_MA_or_YTM_derived_from_weekly_prices': False, 'canonical_market_source_replaced': False,
        'source_raw_sha256': sha256(files[prefix + '_5y_weekly_raw.json']).hexdigest()}


def daily_history(files, symbol, primary_raw, evaluation_at):
    import exchange_calendars as xc
    _, raw = tool_response(files['massive/' + symbol + '_daily_raw.json'])
    original = list(csv.DictReader(io.StringIO(raw['result'])))
    extracted = csv_rows(files['massive/' + symbol + '_daily.csv'])
    if len(original) != len(extracted) or not original:
        raise PermissionError('PLUGIN_DATA_DAILY_COVERAGE')
    zone = ZoneInfo('America/New_York'); primary = json.loads(primary_raw, parse_float=Decimal)['chart']['result'][0]
    prior = {datetime.fromtimestamp(stamp, zone).date().isoformat(): primary['indicators']['quote'][0]['close'][i]
        for i, stamp in enumerate(primary['timestamp'])}
    days = [datetime.fromtimestamp(int(row['t'])/1000, zone).date() for row in original]
    if days != sorted(set(days)) or max(days) > time(evaluation_at).date():
        raise PermissionError('PLUGIN_DATA_DAILY_DATE_ORDER_OR_FUTURE')
    cal = xc.get_calendar('XNYS', start=min(days), end=max(days)+timedelta(days=7))
    comparisons = []; rows = []; excluded = []
    for source, row, day in zip(original, extracted, days):
        if set(row) != set(source)|{'date_et'} or row['date_et'] != str(day) or any(number(row[k]) != number(v) for k,v in source.items()):
            raise PermissionError('PLUGIN_DATA_DAILY_CSV_MISMATCH')
        ohlcv(source[k] for k in ('o', 'h', 'l', 'c', 'v'))
        if not cal.is_session(str(day)):
            raise ValueError('PLUGIN_DATA_DAILY_NONSESSION')
        if cal.session_close(str(day)).to_pydatetime() > time(evaluation_at):
            excluded.append(str(day)); continue
        rows.append({**source, 'date_et': str(day)})
        if str(day) in prior:
            official = number(prior[str(day)]); other = number(source['c'])
            comparisons.append({'date': str(day), 'primary_close': str(official), 'massive_close': str(other),
                'difference': str(other-official),
                'same_at_four_decimal_places': other.quantize(Decimal('.0001'), rounding=ROUND_HALF_EVEN) ==
                    official.quantize(Decimal('.0001'), rounding=ROUND_HALF_EVEN)})
    qa = json.loads(files['massive/qa.json'])[symbol]
    if (qa['count'] != len(original) or qa['first'] != str(days[0]) or qa['last'] != str(days[-1])
            or qa['request_adjusted'] is not True or qa['source'] !=
            'Massive /v2/aggs/ticker/' + symbol + '/range/1/day/' + str(days[0]) + '/' + str(days[-1])):
        raise PermissionError('PLUGIN_DATA_DAILY_QA_MISMATCH')
    return {'symbol': symbol, 'raw_bar_count': len(original), 'completed_daily_bars': rows,
        'forming_sessions_excluded': excluded, 'overlap_count': len(comparisons), 'close_comparisons': comparisons,
        'exact_close_matches': sum(number(r['difference']) == 0 for r in comparisons),
        'four_decimal_close_matches': sum(r['same_at_four_decimal_places'] for r in comparisons),
        'max_abs_close_difference': str(max((abs(number(r['difference'])) for r in comparisons), default=Decimal(0))),
        'comparison_basis': 'DECIMAL_HALF_EVEN_4DP_DIAGNOSTIC_ONLY__NO_ACCEPTANCE_THRESHOLD',
        'request_adjusted': True, 'total_return_attested': False,
        'volume_basis_qualified_for_canonical_liquidity': False,
        'instrument_identity_basis': 'DELIVERED_REQUEST_QA_CONTEXT__NO_SYMBOL_ECHO_IN_RAW_CSV',
        'canonical_market_source_replaced': False, 'used_as_NBBO': False,
        'source_raw_sha256': sha256(files['massive/' + symbol + '_daily_raw.json']).hexdigest()}


def alpha_dividends(files, symbol, evaluation_at):
    _, raw = tool_response(files['alpha/' + symbol + '_dividends_raw.json'])
    if raw['symbol'] != symbol:
        raise PermissionError('PLUGIN_DATA_ALPHA_SYMBOL')
    extracted = csv_rows(files['alpha/' + symbol + '_dividends.csv'])
    if len(extracted) != len(raw['data']):
        raise PermissionError('PLUGIN_DATA_ALPHA_COVERAGE')
    rows = []
    for source, row in zip(raw['data'], extracted):
        pay = source.get('payment_date'); pay = None if pay in (None, '', 'None') else date.fromisoformat(pay).isoformat()
        ex = date.fromisoformat(source['ex_dividend_date']).isoformat(); amount = number(source['amount'])
        csv_pay = None if row['pay_date'] in ('', 'null', 'None') else date.fromisoformat(row['pay_date']).isoformat()
        if (amount <= 0 or row['symbol'] != symbol or row['ex_date'] != ex or csv_pay != pay
                or number(row['amount']) != amount or row['ROC'] != 'null'):
            raise PermissionError('PLUGIN_DATA_ALPHA_CSV_MISMATCH')
        rows.append({'ex_date': ex, 'pay_date': pay, 'amount': str(amount), 'roc': None,
            'event_status': 'DECLARED_FUTURE' if ex > time(evaluation_at).date().isoformat() else 'EX_DATE_OCCURRED'})
    if [r['ex_date'] for r in rows] != sorted({r['ex_date'] for r in rows}, reverse=True):
        raise ValueError('PLUGIN_DATA_ALPHA_DATE_ORDER')
    qa = json.loads(files['alpha/provenance_qa.json'])['symbols'][symbol]
    if (qa['rows'] != len(rows) or qa['payment_dates_missing'] != sum(r['pay_date'] is None for r in rows)
            or qa['ROC_nonnull'] != 0):
        raise PermissionError('PLUGIN_DATA_ALPHA_QA_MISMATCH')
    return {'symbol': symbol, 'rows': rows, 'row_count': len(rows), 'missing_payment_dates': qa['payment_dates_missing'],
        'ROC_provided': False, 'issuer_composition_overwritten': False,
        'source_raw_sha256': sha256(files['alpha/' + symbol + '_dividends_raw.json']).hexdigest()}


def compare_dividends(events, issuer_rows, *, allow_ambiguous=False):
    grouped = defaultdict(list)
    for row in events: grouped[row['ex_date']].append(row)
    ambiguous = {key: rows for key, rows in grouped.items() if len(rows) > 1}
    indexed = {key: rows[0] for key, rows in grouped.items() if len(rows) == 1}; differences = []
    if ambiguous and not allow_ambiguous:
        raise PermissionError('PLUGIN_DATA_DUPLICATE_DIVIDEND_EX_DATE')
    total = Decimal(0); other_total = Decimal(0); compared = 0
    for official in issuer_rows:
        expected = number(official['amount']); total += expected
        row = indexed.get(official['ex_date'])
        if row is None:
            differences.append({'ex_date': official['ex_date'], 'field':
                'ambiguous_provider_events' if official['ex_date'] in ambiguous else 'missing_provider_event'}); continue
        compared += 1; other_total += number(row['amount'])
        if number(row['amount']) != expected:
            differences.append({'ex_date': row['ex_date'], 'field': 'amount', 'provider': row['amount'],
                'issuer': official['amount'], 'difference': str(number(row['amount'])-expected)})
        if row['pay_date'] != official['pay_date']:
            differences.append({'ex_date': row['ex_date'], 'field': 'payment_date',
                'provider': row['pay_date'], 'issuer': official['pay_date']})
    return {'issuer_payment_count': len(issuer_rows), 'records_compared': compared,
        'issuer_total_per_share': str(total), 'provider_total_for_same_ex_dates': str(other_total) if compared == len(issuer_rows) else None,
        'matched_provider_amount_sum': str(other_total), 'ambiguous_provider_events': deepcopy(ambiguous),
        'differences': differences, 'issuer_primary_preserved': True,
        'missing_payment_date_or_ROC_filled_from_other_provider': False}


def extend(pool, source, data, evaluation_at):
    if source is None: return pool
    if not pool.get('additional_delta_handoff'):
        raise PermissionError('PLUGIN_DATA_PRIOR_ISSUER_EVIDENCE_REQUIRED')
    files = manifest_files(source, evaluation_at, schema='Family.W8.V75PluginDataSource.v1',
        manifest_name='manifest.json', size_field='bytes')
    ready = pool['ready_data_handoff']; comparisons = {}; ibkr = {}; massive = {}; alpha = {}
    for symbol in ('SGOV', 'SPSB'):
        ibkr[symbol] = ibkr_history(files, symbol, evaluation_at)
        massive[symbol] = daily_history(files, symbol, data['YAHOO_' + symbol], evaluation_at)
        alpha[symbol] = alpha_dividends(files, symbol, evaluation_at)
        original = (ready['spsb_distribution_and_qii']['dividends']['rows'] if symbol == 'SPSB' else None)
        if original:
            issuer = [{'ex_date': iso(r['EX-DATE'], '%m/%d/%Y'), 'pay_date': iso(r['PAYABLE DATE'], '%m/%d/%Y'),
                'amount': str(number(r['DIVIDEND ($)']))} for r in original]
        else:
            issuer = [{'ex_date': r['ex_date'], 'pay_date': r['pay_date'], 'amount': r['total']}
                for r in pool['issuer_observations'][symbol]['facts']['distribution_source_observation']['rows']]
        comparisons[symbol] = {'alpha': compare_dividends(alpha[symbol]['rows'], issuer),
            'ibkr': compare_dividends(ibkr[symbol]['dividend_events'], issuer, allow_ambiguous=True)}
    _, profile = tool_response(files['alpha/SPSB_profile_raw.json'])
    receipt = {'schema_version': 'Family.W8.VerifiedV75PluginData.v1', 'source_reference': source['source_reference'],
        'manifest_sha256': source['manifest_sha256'], 'source_available_at': source['ingested_at'],
        'raw_files_verified': len(files), 'ibkr_weekly': ibkr, 'massive_daily': massive,
        'alpha_dividends': alpha, 'issuer_dividend_comparisons': comparisons,
        'SPSB_profile_auxiliary': {'dividend_yield': profile.get('dividend_yield'),
            'last_updated': profile.get('last_updated'), 'yield_kind': 'DISTRIBUTION_YIELD_RATIO__NOT_PORTFOLIO_YTM_OR_SEC_YIELD'},
        'primary_financial_inputs_changed': False, 'canonical_market_source_replaced': False,
        'qualified_weekly_YTM_or_SEC_history_supplied': False, 'NBBO_quotes_acquired': False,
        'NBBO_handoff_reported_status': 'NOT_ENTITLED', 'NBBO_raw_denial_response_in_package': False,
        'redistribution_rights_attested': False, 'trade_action': 'NO_TRADE'}
    pool['plugin_data_cross_checks'] = receipt
    pool['auxiliary_evidence_available_at'] = source['ingested_at']
    pool.setdefault('auxiliary_source_proofs', {})['PLUGIN_DATA_HANDOFF'] = {
        'source_reference': source['source_reference'], 'source_sha256': source['manifest_sha256'], 'available_at': source['ingested_at']}
    return pool


def summary(evidence, symbol):
    weekly = evidence['ibkr_weekly'][symbol]; daily = evidence['massive_daily'][symbol]
    return {'source_available_at': evidence['source_available_at'],
        'manifest_sha256': evidence['manifest_sha256'],
        'IBKR_raw_weekly_bars': weekly['raw_bar_count'],
        'IBKR_usable_unique_completed_weeks': weekly['usable_unique_completed_weeks'],
        'IBKR_ambiguous_weeks': deepcopy(weekly['multiple_bars_per_iso_week']),
        'IBKR_invalid_ohlcv_count': len(weekly['invalid_ohlcv_bars']),
        'IBKR_dividend_events': weekly['dividend_count'],
        'Massive_daily_bars': daily['raw_bar_count'], 'daily_price_overlap': daily['overlap_count'],
        'daily_four_decimal_close_matches': daily['four_decimal_close_matches'],
        'daily_max_abs_close_difference': daily['max_abs_close_difference'],
        'Alpha_dividend_events': evidence['alpha_dividends'][symbol]['row_count'],
        'issuer_dividend_comparisons': deepcopy(evidence['issuer_dividend_comparisons'][symbol]),
        'primary_financial_inputs_changed': False, 'NBBO_quotes_acquired': False,
        'qualified_weekly_YTM_or_SEC_history_supplied': False}
