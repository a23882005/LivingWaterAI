"""Member-scoped cached observations through original numeric/V75 routines.

Observed provider prices remain distinct from canonical deployment evidence.
No instrument aliases, exchange identity, session close, PIT, strategy thresholds,
settlement, NAV or capital amounts are inferred by this intake.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv
import io
import json
import math
import re
import sys


def _time(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('OBSERVATION_TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)


def _hash(raw):
    return sha256(raw).hexdigest()


def _macro_metrics(macro, evaluated_at):
    """Unit conversion only; retain observation dates and full original rows."""
    from family_input import digest
    raw = macro['payload']
    if (macro.get('digest') != digest(raw) or
            raw.get('schema') != 'V70.3/family-macro-feed-v3'):
        raise ValueError('OBSERVATION_MACRO_DIGEST_OR_SCHEMA')
    if _time(raw['asOf']) > _time(evaluated_at):
        raise ValueError('OBSERVATION_FUTURE_MACRO')
    metrics, sources = {}, {}
    if raw.get('verification', {}).get('ready') is not True:
        return metrics, sources
    for key, pid, field, unit, factor in [
        ('m02', 'PRED-004', 'hy_oas_bps', '%', Decimal(100)),
        ('m12', 'PRED-005', 'move', '', Decimal(1)),
    ]:
        row = raw.get('indicators', {}).get(key, {})
        if row.get('status') != 'OK' or row.get('value') is None:
            continue
        if row.get('unit') != unit or not row.get('source'):
            raise ValueError('OBSERVATION_MACRO_UNIT_OR_SOURCE:' + key)
        if date.fromisoformat(row['dataDate']) > _time(raw['asOf']).date():
            raise ValueError('OBSERVATION_FUTURE_MACRO_ROW')
        if row.get('lastVerifiedAt') and _time(row['lastVerifiedAt']) > _time(evaluated_at):
            raise ValueError('OBSERVATION_FUTURE_VERIFICATION')
        if isinstance(row['value'], bool):
            raise ValueError('OBSERVATION_MACRO_VALUE')
        value = Decimal(str(row['value']))
        if not value.is_finite() or value < 0:
            raise ValueError('OBSERVATION_MACRO_VALUE')
        metrics.setdefault(pid, {})[field] = format(value * factor, 'f')
        sources[pid + '.' + field] = {'source_row': deepcopy(row),
            'source_path': '/indicators/' + key, 'source_feed_sha256': macro['source_sha256'],
            'conversion': 'percent_x100_to_bps' if factor == 100 else 'index_points_unchanged'}
    return metrics, sources


def evaluate_observed_history(rows, *, repo_root, evaluation_at, macro, asset_id):
    """Run original routines on validated rows; return no deployment decisions."""
    import pandas as pd
    from technical_source_bridge import _originals, _aggregate, NAMES
    from verify_dependencies import verify
    verify(repo_root)
    legacy, numeric = _originals()
    frame = pd.DataFrame(rows)
    values = numeric.technical(frame)
    td9 = asdict(legacy['calculate_td9'](frame['Close'].tolist()))
    # All canonical votes stay UNKNOWN until approved metadata and named rules
    # are supplied. Numeric MA/MACD/TD9 facts cannot silently become votes.
    vectors = {k: [{'truth': 'UNKNOWN'} for _ in names] for k, names in NAMES.items()}
    v82 = _aggregate(repo_root, vectors)
    runtime = Path(repo_root).resolve() / '系統工程/債券V75/正式Runtime/V75_Work6_RuntimeReady_2026-09-25/runtime'
    if str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent != runtime / 'v75_runtime':
        raise ValueError('OBSERVATION_V75_SOURCE_MISMATCH')
    from v75_runtime.predicates import EVALUATORS
    from v75_runtime.work3 import US_LISTED_ASSETS, TW_LISTED_ASSETS
    metrics, sources = _macro_metrics(macro, evaluation_at)
    # Only numeric comparisons are mapped. KD formula compatibility and the
    # named right/trim event producers are still separate required sources.
    mapping = {'low_td_count': 'low_td9_setup', 'high_td_count': 'high_td9_setup',
               'rsi14': 'rsi14', 'ma20': 'ma20', 'ma50': 'ma50', 'atr14': 'atr14'}
    technical = {key: values[name] for key, name in mapping.items() if values.get(name) is not None}
    technical['close'] = rows[-1]['Close']
    if len(rows) >= 20:
        technical['rolling_20d_low'] = min(row['Low'] for row in rows[-20:])
    metrics['PRED-009'] = technical
    predicates = {}
    is_bond = asset_id in US_LISTED_ASSETS | TW_LISTED_ASSETS
    for pid, evaluator in (EVALUATORS.items() if is_bond else []):
        result = evaluator(metrics.get(pid, {}), _time(evaluation_at),
            ['OBSERVED_CACHE_ONLY', 'ORIGINAL_NUMERIC_FORMULAS', 'FULL_SOURCE_COVERAGE_PENDING'])
        predicates[pid] = {'metrics': metrics.get(pid, {}),
            'original_result': result.model_dump(mode='json'),
            'input_coverage': 'PARTIAL' if metrics.get(pid) else 'MISSING',
            'original_result_as_of_basis': 'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE',
            'input_freshness_verified': False,
            'original_default_freshness_is_not_attestation': True,
            'deployment_input_eligible': False}
    return {'numeric': values, 'td9': td9, 'v82_original_aggregation': v82,
        'v75_original_predicates': predicates, 'macro_metric_sources': sources,
        'v75_scope': 'OBSERVED_BOND_INPUTS' if is_bond else 'NOT_A_V75_SUPPORTED_BOND',
        'call_trace': ['ORIGINAL.calculate_td9', 'ORIGINAL.analytics.technical',
                       'V82.evaluate_technical'] + (['V75.PRED-001..010'] if is_bond else []),
        'formal_deployment_eligible': False, 'trade_authorization': 'NONE'}


def build_member_market_observations(snapshot, targets, macro, *, repo_root, evaluation_at):
    """Read only exact-symbol caches referenced by this verified member snapshot.

The caller has validated snapshot bytes/client against the fixed member DB.
No suffix/alias is guessed: NATO is never mapped to NATO.CN, for example.
These cache manifests attest row counts/dates, not exchange or price basis.
"""
    w5 = Path(repo_root).resolve() / '系統工程/Family/W5'
    if str(w5) not in sys.path:
        sys.path.insert(0, str(w5))
    tables = snapshot['tables']
    keys = {r['instrument_key'] for r in tables.get('portfolio_position', [])}
    keys.update(r['instrument_key'] for target in targets for r in target['allocations'])
    instruments = [r for r in tables.get('portfolio_instrument', []) if r['instrument_key'] in keys]
    assets, missing = [], []
    base = Path(repo_root).resolve() / 'data/market_history/global'
    manifest_path = base / 'manifest.json'
    if not instruments:
        return {'assets': [], 'missing': [], 'formal_deployment_eligible': False}
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    for instrument in instruments:
        key, symbol = instrument['instrument_key'], instrument.get('ticker')
        if (instrument.get('identity_state') != 'KNOWN' or not isinstance(symbol, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,31}', symbol)):
            missing.append({'instrument_key': key, 'code': 'KNOWN_EXACT_SYMBOL_REQUIRED'})
            continue
        entry = manifest['items'].get(symbol, {})
        cache = base / (symbol + '.csv')
        if entry.get('status') != 'OK' or not cache.is_file():
            missing.append({'instrument_key': key, 'symbol': symbol, 'code': 'EXACT_SYMBOL_CACHE_UNAVAILABLE'})
            continue
        try:
            if _time(entry['last_verified_utc']) > _time(evaluation_at):
                raise ValueError('CACHE_VERIFICATION_IN_FUTURE')
            raw = cache.read_bytes()
            source_rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            if len(source_rows) != entry['rows'] or not source_rows or source_rows[-1]['Date'] != entry['latest_observation']:
                raise ValueError('CACHE_MANIFEST_MISMATCH')
            dates = [r['Date'] for r in source_rows]
            if dates != sorted(set(dates)):
                raise ValueError('CACHE_DATE_ORDER')
            rows = []
            for row in source_rows:
                day = date.fromisoformat(row['Date'])
                if day >= _time(evaluation_at).date():
                    raise ValueError('CACHE_FORMING_OR_FUTURE_BAR')
                vals = {k: float(row[k]) for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
                if (not all(math.isfinite(v) for v in vals.values()) or vals['Low'] <= 0
                        or vals['Volume'] < 0 or not vals['Low'] <= min(vals['Open'], vals['Close'])
                        <= max(vals['Open'], vals['Close']) <= vals['High']):
                    raise ValueError('CACHE_OHLCV_INVALID')
                rows.append({'Date': row['Date'], **vals})
            if len(rows) < 13:
                raise ValueError('CACHE_SAMPLE_INSUFFICIENT')
            result = evaluate_observed_history(rows, repo_root=repo_root, evaluation_at=evaluation_at, macro=macro, asset_id=symbol)
            if cache.read_bytes() != raw:
                raise ValueError('CACHE_CHANGED_DURING_CALCULATION')
            assets.append({'instrument_key': key, 'symbol': symbol, 'observed_date': dates[-1],
                'observed_close': rows[-1]['Close'], 'rows': len(rows),
                'source_path': str(cache.relative_to(Path(repo_root).resolve())),
                'source_sha256': _hash(raw), 'manifest_sha256': _hash(manifest_raw),
                'provider_symbol_match_only': True, 'formal_identity_verified': False,
                'source_gaps': ['EXCHANGE_CURRENCY_PROVIDER_ATTESTATION', 'PRICE_BASIS_AND_SPLITS',
                                'OFFICIAL_SESSION_CLOSE_AND_AVAILABILITY', 'CANONICAL_NAMED_PREDICATES'],
                **result})
        except (KeyError, ValueError) as exc:
            missing.append({'instrument_key': key, 'symbol': symbol, 'code': str(exc)})
    if manifest_path.read_bytes() != manifest_raw:
        raise ValueError('MANIFEST_CHANGED_DURING_CALCULATION')
    return {'schema_version': 'Family.W8.MemberMarketObservations.v1',
        'client_id': snapshot['client_id'], 'source_db_sha256': snapshot['source_sha256'],
        'evaluation_at': evaluation_at, 'assets': assets, 'missing': missing,
        'scope': 'OBSERVED_PROVIDER_PRICE_NUMERICS__NOT_CANONICAL_DEPLOYMENT',
        'data_provenance': 'SOURCE_BACKED', 'formal_deployment_eligible': False,
        'trade_authorization': 'NONE'}
