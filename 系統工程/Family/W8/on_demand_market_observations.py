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


def evaluate_observed_history(rows, *, repo_root, evaluation_at, macro, asset_id,formal_rule_source=None,
                              approved_rule_profile=None,is_etf=None):
    """Run original routines on validated rows; return no deployment decisions."""
    import pandas as pd
    from technical_source_bridge import _originals, _aggregate, NAMES, mapped_numeric_signals
    from verify_dependencies import verify
    verify(repo_root)
    legacy, numeric = _originals()
    frame = pd.DataFrame(rows)
    values = numeric.technical(frame)
    previous = numeric.technical(frame.iloc[:-1]) if len(rows) >= 2 else {}
    # Reuse W5's existing base-fact comparisons, independently of canonical
    # event voting. A state above MA20 is not silently a reclaim event.
    base_facts = {}
    if values.get('ma20') is not None:
        base_facts['above_ma20'] = rows[-1]['Close'] > values['ma20']
        if len(rows) >= 2 and previous.get('ma20') is not None:
            base_facts['reclaim_ma20'] = (rows[-2]['Close'] <= previous['ma20']
                                        and rows[-1]['Close'] > values['ma20'])
    td9 = asdict(legacy['calculate_td9'](frame['Close'].tolist()))
    # Reuse only the comparisons already mapped in the original source bridge.
    # This observed view remains ineligible for deployment without its receipts.
    vectors = {k: [{'name': name, 'truth': 'UNKNOWN',
        'reason': 'NAMED_RULE_OR_SOURCE_REQUIRED'} for name in names] for k, names in NAMES.items()}
    if len(rows) >= 2:
        for group, name, truth, dependencies in mapped_numeric_signals(values, previous):
            next(r for r in vectors[group] if r['name'] == name).update(
                truth='TRUE' if truth else 'FALSE', reason='EXISTING_BRIDGE_NUMERIC_RULE',
                dependencies=dependencies)
    lows = legacy['confirmed_swing_lows'](frame['Low'].tolist())
    highs = legacy['confirmed_swing_highs'](frame['High'].tolist())
    if len(lows) >= 2:
        next(r for r in vectors['right_signals'] if r['name'] == 'higher_low').update(
            truth='TRUE' if lows[-1].value > lows[-2].value else 'FALSE',
            reason='EXISTING_BRIDGE_NUMERIC_RULE', dependencies=['confirmed_lows[-2:]'])
    swings={key:[dict(asdict(p),pivot_session=rows[p.index]['Date'],
        confirmation_session=rows[p.index+2]['Date']) for p in points]
        for key,points in [('lows',lows),('highs',highs)]}
    formal_signals={}
    if formal_rule_source is not None:
        from formal_analysis_signals import map_formal_observations
        formal_signals=map_formal_observations(rows,values,previous,base_facts,swings,vectors,formal_rule_source)
    approved={}
    if approved_rule_profile is not None:
        from approved_v04_technical import produce
        approved=produce(rows,profile=approved_rule_profile,is_etf=is_etf)
        vectors=approved['signals']
    v82 = _aggregate(repo_root, vectors,approved.get('ma20_ok','UNKNOWN'))
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
    return {'numeric': values, 'previous_numeric': previous, 'base_facts': base_facts,
        'swings':swings,'formal_analysis_signals':formal_signals,'approved_technical':approved,
        'td9': td9, 'observed_named_signals': vectors,
        'v82_original_aggregation': v82,
        'v75_original_predicates': predicates, 'macro_metric_sources': sources,
        'v75_scope': 'OBSERVED_BOND_INPUTS' if is_bond else 'NOT_A_V75_SUPPORTED_BOND',
        'call_trace': ['ORIGINAL.calculate_td9', 'ORIGINAL.analytics.technical',
                       'ORIGINAL.confirmed_swing_lows/highs']+
                       (['W8.formal_analysis_signals.map_formal_observations'] if formal_signals else [])+[
                       'V82.evaluate_technical'] + approved.get('call_trace',[]) + (['V75.PRED-001..010'] if is_bond else []),
        'formal_deployment_eligible': False, 'trade_authorization': 'NONE'}


def evaluate_close_history(rows, *, repo_root,formal_rule_source=None,approved_rule_profile=None,is_etf=None):
    """Execute only original Close-dependent routines when H/L/O is invalid.

    Unknown High/Low/Volume inputs are explicit NaN, never repaired prices.
    Their dependent outputs are discarded and returned as unavailable.
    """
    import pandas as pd
    from technical_source_bridge import _originals,_aggregate,NAMES,mapped_numeric_signals
    legacy,numeric=_originals()
    frame=pd.DataFrame({'Close':[r['Close'] for r in rows],
        'High':[float('nan')]*len(rows),'Low':[float('nan')]*len(rows),
        'Volume':[float('nan')]*len(rows)})
    current=numeric.technical(frame);previous=numeric.technical(frame.iloc[:-1])
    independent={'high_td9_setup','low_td9_setup','macd_12_26','macd_signal_9','macd_histogram',
        'rsi14','ma5','ma10','ma20','ma50','ma60','ma200'}
    current={k:v if k in independent else None for k,v in current.items()}
    previous={k:v if k in independent else None for k,v in previous.items()}
    vectors={g:[{'name':name,'truth':'UNKNOWN','reason':'INDEPENDENT_CLOSE_ANALYSIS_ONLY'}
        for name in names] for g,names in NAMES.items()}
    for group,name,value,deps in mapped_numeric_signals(current,previous):
        next(x for x in vectors[group] if x['name']==name).update(
            truth='TRUE' if value else 'FALSE',reason='EXISTING_BRIDGE_NUMERIC_RULE',dependencies=deps)
    facts={}
    if current.get('ma20') is not None:
        facts['above_ma20']=rows[-1]['Close']>current['ma20']
        if previous.get('ma20') is not None:
            facts['reclaim_ma20']=rows[-2]['Close']<=previous['ma20'] and rows[-1]['Close']>current['ma20']
    formal_signals={}
    if formal_rule_source is not None:
        from formal_analysis_signals import map_formal_observations
        formal_signals=map_formal_observations(rows,current,previous,facts,{},vectors,formal_rule_source)
    approved={}
    if approved_rule_profile is not None:
        from approved_v04_technical import produce
        approved=produce(rows,profile=approved_rule_profile,is_etf=is_etf,close_only=True)
        vectors=approved['signals']
    return {'numeric':current,'previous_numeric':previous,'td9':asdict(legacy['calculate_td9'](frame['Close'].tolist())),
        'approved_technical':approved,
        'formal_analysis_signals':formal_signals,
        'base_facts':facts,'swings':{'lows':[],'highs':[]},'observed_named_signals':vectors,
        'v82_original_aggregation':_aggregate(repo_root,vectors,approved.get('ma20_ok','UNKNOWN')),'v75_original_predicates':{},
        'component_gaps':{k:'INVALID_OHLCV__CLOSE_ONLY_COMPONENT_DOES_NOT_CONSUME_HIGH_LOW_VOLUME'
            for k in current if k not in independent},
        'call_trace':['ORIGINAL.calculate_td9','ORIGINAL.analytics.technical:Close_dependencies_only','V82.evaluate_technical'],
        'formal_deployment_eligible':False,'trade_authorization':'NONE'}


def resolve_analysis_market(instrument, repo_root, evaluation_at):
    """Use only explicit source-reviewed aliases, never suffix guessing.

    A reference listing does not manufacture the held trading venue. Missing
    held venue and independent provider attestation remain separate gaps.
    """
    symbol=instrument.get('ticker')
    path=Path(repo_root)/'系統工程/Family/W8/market_identity_aliases.json'
    if not path.is_file():return symbol,None
    raw=path.read_bytes();catalog=json.loads(raw)
    if catalog.get('schema_version')!='Family.W8.AnalysisMarketAliases.v1':
        raise ValueError('ANALYSIS_MARKET_ALIAS_SCHEMA')
    row=catalog['aliases'].get(symbol)
    if row is None:return symbol,None
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,31}',row['provider_symbol'])
        or not row.get('source_url') or not row.get('isin')
        or instrument.get('quote_currency')!=row['quote_currency']
        or instrument.get('isin') not in (None,row['isin'])):
        raise ValueError('ANALYSIS_MARKET_ALIAS_IDENTITY_MISMATCH')
    exchange=instrument.get('exchange_code')
    if exchange not in (None,'',row['reference_exchange'],'LSE'):
        raise ValueError('ANALYSIS_MARKET_ALIAS_EXCHANGE_MISMATCH')
    if row['verified_on']>_time(evaluation_at).date().isoformat():
        raise ValueError('ANALYSIS_MARKET_ALIAS_VERIFICATION_IN_FUTURE')
    return row['provider_symbol'],{**deepcopy(row),'catalog_sha256':_hash(raw),
        'held_exchange':exchange,'held_exchange_inferred':False,
        'provider_independent_attestation':False}


def build_member_market_observations(snapshot, targets, macro, *, repo_root, evaluation_at,
                                     official_holdings=None,alternative_source_dir=None,formal_rule_source=None,
                                     approved_rule_profile=None,verified_asset_types=None):
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
    instruments = [deepcopy(r) for r in tables.get('portfolio_instrument', []) if r['instrument_key'] in keys]
    if official_holdings is not None:
        if (official_holdings.get('client_id') != snapshot['client_id'] or
                official_holdings.get('source_db_sha256') != snapshot['source_sha256'] or
                official_holdings.get('snapshot_digest') != snapshot.get('payload_digest')):
            raise PermissionError('OBSERVATION_HOLDINGS_SNAPSHOT_MISMATCH')
        seen = {r.get('ticker') for r in instruments}
        for row in official_holdings['analysis_security_positions']:
            symbol = row['symbol']
            if symbol in seen:
                continue
            instrument = deepcopy(row.get('instrument')) or {
                'instrument_key': None, 'ticker': symbol, 'identity_state': 'SOURCE_SYMBOL_ONLY'}
            instrument['holding_source_reference'] = row['source_row'].get('source_reference')
            instruments.append(instrument);seen.add(symbol)
    assets, missing = [], []
    base = Path(repo_root).resolve() / 'data/market_history/global'
    manifest_path = base / 'manifest.json'
    if not instruments:
        return {'assets': [], 'missing': [], 'formal_deployment_eligible': False}
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    alternate={};alternate_raw=None;alternate_base=None
    if alternative_source_dir is not None:
        alternate_base=Path(alternative_source_dir).resolve(strict=True)
        alternate_raw=(alternate_base/'manifest.json').read_bytes();alternate=json.loads(alternate_raw)
        if alternate.get('schema_version')!='Family.W8.AlternativeMarketHistory.v1':
            raise ValueError('ALTERNATIVE_MARKET_MANIFEST_SCHEMA')
    for instrument in instruments:
        key, symbol = instrument['instrument_key'], instrument.get('ticker')
        is_etf=(True if (verified_asset_types or {}).get(symbol)=='BROAD_ETF' else
            instrument.get('instrument_type')=='ETF' if instrument.get('instrument_type') in ('ETF','STOCK') else None)
        # First production route is restricted to independently proven broad
        # stock ETFs. V75 bonds and unverified/derivative products retain their
        # existing components; approval does not manufacture product identity.
        routed_profile=(approved_rule_profile if (verified_asset_types or {}).get(symbol)=='BROAD_ETF' else None)
        if (instrument.get('identity_state') not in ('KNOWN', 'SOURCE_SYMBOL_ONLY') or not isinstance(symbol, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,31}', symbol)):
            missing.append({'instrument_key': key, 'code': 'KNOWN_EXACT_SYMBOL_REQUIRED'})
            continue
        try:
            provider_symbol,identity_mapping=resolve_analysis_market(instrument,repo_root,evaluation_at)
        except ValueError as error:
            missing.append({'instrument_key':key,'symbol':symbol,'code':str(error)})
            continue
        entry = manifest['items'].get(provider_symbol, {})
        cache = base / (provider_symbol + '.csv')
        alternate_entry=None
        if (entry.get('status')!='OK' or not cache.is_file()) and symbol in alternate.get('items',{}):
            candidate=alternate['items'][symbol]
            if (candidate['file_name']!=symbol+'.csv' or candidate['currency']!='USD'
                or instrument.get('quote_currency') not in (None,candidate['currency'])
                or instrument.get('exchange_code') not in (None,'',candidate['exchange'],'LSE')):
                missing.append({'instrument_key':key,'symbol':symbol,'code':'ALTERNATIVE_MARKET_IDENTITY_MISMATCH'})
                continue
            entry=candidate;alternate_entry=candidate;provider_symbol=symbol
            cache=alternate_base/candidate['file_name']
            identity_mapping={'reference_exchange':candidate['exchange'],'reference_timezone':candidate['timezone'],
                'quote_currency':candidate['currency'],'source_url':candidate['source_url'],
                'scope':'VERIFIED_DISPLAYED_REFERENCE_MARKET__NOT_HELD_VENUE_OR_DEPLOYMENT_ATTESTATION',
                'catalog_sha256':_hash(alternate_raw),'held_exchange':instrument.get('exchange_code'),
                'held_exchange_inferred':False}
        if entry.get('status') != 'OK' or not cache.is_file():
            missing.append({'instrument_key': key, 'symbol': symbol,'provider_symbol':provider_symbol,
                'source_path':str(cache.relative_to(Path(repo_root))),
                'code': 'EXACT_SYMBOL_CACHE_UNAVAILABLE'})
            continue
        try:
            if _time(entry['last_verified_utc']) > _time(evaluation_at):
                raise ValueError('CACHE_VERIFICATION_IN_FUTURE')
            raw = cache.read_bytes()
            if alternate_entry and _hash(raw)!=alternate_entry['sha256']:
                raise ValueError('ALTERNATIVE_MARKET_HISTORY_SHA_MISMATCH')
            source_rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            if len(source_rows) != entry['rows'] or not source_rows or source_rows[-1]['Date'] != entry['latest_observation']:
                raise ValueError('CACHE_MANIFEST_MISMATCH')
            dates = [r['Date'] for r in source_rows]
            if dates != sorted(set(dates)):
                raise ValueError('CACHE_DATE_ORDER')
            rows = [];invalid_rows=[];last_invalid=-1;close_only=False;excluded_sessions=[]
            for source_index,row in enumerate(source_rows):
                day = date.fromisoformat(row['Date'])
                if day > _time(evaluation_at).date():
                    raise ValueError('CACHE_FORMING_OR_FUTURE_BAR')
                if day == _time(evaluation_at).date():
                    # Without a bound market-calendar/final-close receipt,
                    # preserve this bar as unverified. It must not erase the
                    # independent prior-session history or become a final bar.
                    excluded_sessions.append({'date':row['Date'],'source_row':source_index+2,
                        'reason':'SAME_UTC_DATE_FINAL_SESSION_RECEIPT_NOT_VERIFIED'})
                    continue
                try:
                    vals = {k: float(row[k]) for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
                    valid=(all(math.isfinite(v) for v in vals.values()) and vals['Low'] > 0
                        and vals['Volume'] >= 0 and vals['Low'] <= min(vals['Open'], vals['Close'])
                        <= max(vals['Open'], vals['Close']) <= vals['High'])
                except (KeyError,ValueError):valid=False;vals={}
                if not valid:
                    invalid_rows.append({'date':row['Date'],'source_row':source_index+2,'code':'CACHE_OHLCV_INVALID'})
                    last_invalid=source_index
                    suffix_policy=identity_mapping and identity_mapping.get('history_policy')=='CONTIGUOUS_VALID_SUFFIX_FOR_ANALYSIS_ONLY'
                    if not suffix_policy:
                        if alternate_entry and alternate_entry.get('allow_close_only_analysis'):
                            close_only=True
                        else:raise ValueError('CACHE_OHLCV_INVALID')
                rows.append({'Date': row['Date'], **vals,'_source_decimal':{
                    key:row.get(key) for key in ('Open','High','Low','Close','Volume')}})
            if invalid_rows and not close_only:
                # No middle rows are deleted, repaired or made up. Start a new
                # analysis window strictly after the most recent bad source bar.
                rows=rows[last_invalid+1:]
            if len(rows) < 13:
                raise ValueError('CACHE_SAMPLE_INSUFFICIENT_AFTER_SOURCE_ERRORS' if invalid_rows else 'CACHE_SAMPLE_INSUFFICIENT')
            history_quality={'source_rows':len(source_rows),'used_rows':len(rows),
                'analysis_start':rows[0]['Date'],'analysis_end':rows[-1]['Date'],
                'excluded_prefix_rows':0 if close_only else last_invalid+1,'invalid_source_rows':invalid_rows,
                'source_values_modified':False,'middle_rows_removed':False,
                'full_source_history_valid':not invalid_rows,
                'excluded_unverified_session_rows':excluded_sessions,
                'source_latest_observation':source_rows[-1]['Date'],
                'scope':'CLOSE_ONLY__INVALID_OHLC_NOT_CONSUMED' if close_only else 'CONTIGUOUS_VALID_WINDOW__ANALYSIS_ONLY' if invalid_rows else 'SOURCE_HISTORY'}
            if close_only:
                if any(not math.isfinite(r.get('Close',float('nan'))) or r['Close']<=0 for r in rows):
                    raise ValueError('CLOSE_ONLY_SOURCE_CLOSE_INVALID')
                result=evaluate_close_history(rows,repo_root=repo_root,formal_rule_source=formal_rule_source,
                    approved_rule_profile=routed_profile,is_etf=is_etf)
            else:result = evaluate_observed_history(rows, repo_root=repo_root, evaluation_at=evaluation_at,
                macro=macro, asset_id=symbol,formal_rule_source=formal_rule_source,
                approved_rule_profile=routed_profile,is_etf=is_etf)
            if cache.read_bytes() != raw:
                raise ValueError('CACHE_CHANGED_DURING_CALCULATION')
            if result.get('approved_technical'):
                binding={'symbol':symbol,'provider_symbol':provider_symbol,'source_sha256':_hash(raw),
                    'manifest_sha256':_hash(alternate_raw if alternate_entry else manifest_raw),
                    'source_db_sha256':snapshot['source_sha256'],'observed_session':rows[-1]['Date'],
                    'evaluated_at':evaluation_at,'provider_verified_at':entry['last_verified_utc']}
                result['approved_technical']['source_binding']=binding
                for slots in result['observed_named_signals'].values():
                    for slot in slots:
                        slot['source_ids_and_digests']=deepcopy(binding)
                        slot['numeric_context_reference']='approved_technical.numeric_decimal'
            assets.append({'instrument_key': key, 'symbol': symbol, 'observed_date': rows[-1]['Date'],
                'provider_symbol':provider_symbol,'analysis_identity_mapping':identity_mapping,
                'observed_close': rows[-1]['Close'], 'rows': len(rows),'history_quality':history_quality,
                'source_path': str(cache.relative_to(Path(repo_root).resolve())) if cache.is_relative_to(Path(repo_root).resolve()) else str(cache),
                'source_sha256': _hash(raw), 'manifest_sha256': _hash(alternate_raw if alternate_entry else manifest_raw),
                'alternative_source_receipt':alternate_entry,
                'provider_symbol_match_only': True, 'formal_identity_verified': False,
                'provider': alternate_entry['provider'] if alternate_entry else manifest.get('data_source'),
                'provider_verified_at': entry['last_verified_utc'],
                'cache_validation': 'MANIFEST_DATE_ORDER_SHA256_CLOSE_VERIFIED__OHLC_INVALID' if close_only else 'MANIFEST_DATE_ORDER_SHA256_VERIFIED__VALID_SUFFIX_OHLCV_ONLY' if invalid_rows else 'ROW_COUNT_DATE_ORDER_OHLCV_SHA256_VERIFIED',
                'instrument_registry_state': instrument.get('identity_state'),
                'holding_source_reference': instrument.get('holding_source_reference'),
                'source_gaps': ['EXCHANGE_CURRENCY_PROVIDER_ATTESTATION', 'PRICE_BASIS_AND_SPLITS',
                                'OFFICIAL_SESSION_CLOSE_AND_AVAILABILITY', 'CANONICAL_NAMED_PREDICATES'],
                **result})
        except (KeyError, ValueError) as exc:
            missing.append({'instrument_key': key, 'symbol': symbol, 'code': str(exc)})
    if manifest_path.read_bytes() != manifest_raw:
        raise ValueError('MANIFEST_CHANGED_DURING_CALCULATION')
    if alternate_raw is not None and (alternate_base/'manifest.json').read_bytes()!=alternate_raw:
        raise ValueError('ALTERNATIVE_MANIFEST_CHANGED_DURING_CALCULATION')
    return {'schema_version': 'Family.W8.MemberMarketObservations.v1',
        'client_id': snapshot['client_id'], 'source_db_sha256': snapshot['source_sha256'],
        'evaluation_at': evaluation_at, 'assets': assets, 'missing': missing,
        'scope': 'OBSERVED_PROVIDER_PRICE_NUMERICS__NOT_CANONICAL_DEPLOYMENT',
        'data_provenance': 'SOURCE_BACKED', 'formal_deployment_eligible': False,
        'trade_authorization': 'NONE'}
