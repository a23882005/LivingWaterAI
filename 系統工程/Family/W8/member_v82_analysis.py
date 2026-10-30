"""All-account holding/target coverage for the original Menu04 V82 chain.

This source adapter calls the existing observation/Core/approved-decision and
slice producers. It does not synthesize Work3/C7/funding, broker orders, a cycle
ledger, or a canonical Family result. Dependent missing inputs stay explicit.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import uuid

from family_input import digest
from official_holdings_source import project_official_holdings
from official_target_input import read_confirmed_weights
from member_market_source import read_market, time

SCHEMA = 'Family.W8.MemberV82Analysis.v1'


def missing(field, producer, reason, affects, *, kind='EXTERNAL_SOURCE_OR_APPROVAL_REQUIRED'):
    return {'field': field, 'producer': producer, 'reason': reason,
            'affects': affects, 'kind': kind}


def target_source(snapshot, config, evaluation_at):
    approved = read_confirmed_weights(snapshot, evaluation_at=evaluation_at)
    if approved is not None:
        if config.get('official_target_base_source') is not None:
            from official_target_input import build
            return build(snapshot, evaluation_at=evaluation_at,
                         base_source=config['official_target_base_source'])[0] | {'weight_denominator': '1'}
        lines = []
        for row, instrument in zip(approved['allocations'], approved['instruments']):
            lines.append({'instrument_id': row['instrument_key'], 'ticker': instrument.get('ticker'),
                'asset_type': instrument['instrument_type'],
                'weight': {'value_state': 'KNOWN', 'value': str(Decimal(row['weight_units']) / 1000000)},
                'target_amount': {'value_state': 'UNKNOWN', 'amount': None, 'currency': None,
                    'reason': 'APPROVED_INVESTMENT_POOL_MONEY_BASE_NOT_BOUND'},
                'source_allocation_row': row, 'source_instrument_row': instrument})
        version = approved['version']
        return {'source_kind': 'OFFICIAL_W1_CONFIRMED_ALLOCATION',
            'target_version': version['version_no'], 'original_confirmation': version,
            'payload': {'draft': {'target_lines': lines}}, 'approval_created': False,
            'weight_denominator': '1', 'source_db_sha256': snapshot['source_sha256']}
    source = config.get('document_target')
    if source is None:
        return {'source_kind': 'UNAVAILABLE', 'target_version': None,
                'payload': {'draft': {'target_lines': []}}, 'weight_denominator': None}
    from approved_target_input import build_approved_target_view
    args = deepcopy(source)
    if args.get('client_id') != snapshot['client_id']:
        raise PermissionError('MEMBER_TARGET_DOCUMENT_CLIENT_MISMATCH')
    if time(args['source_available_at']) > time(evaluation_at):
        raise PermissionError('MEMBER_TARGET_DOCUMENT_NOT_AVAILABLE')
    raw = Path(args['source_path']).read_bytes()
    expected = args.pop('sha256')
    if sha256(raw).hexdigest() != expected:
        raise PermissionError('MEMBER_TARGET_DOCUMENT_HASH_MISMATCH')
    view = build_approved_target_view(**args)['target']
    # Preserve dated table amounts as source facts, without reusing a superseded
    # investment-pool assumption as today's target denominator.
    for line in view['payload']['draft']['target_lines']:
        line['original_document_target_amount'] = line['target_amount']
        line['target_amount'] = {'value_state': 'UNKNOWN', 'amount': None, 'currency': None,
            'reason': 'CURRENT_APPROVED_INVESTMENT_POOL_MONEY_BASE_NOT_BOUND'}
    view['weight_denominator'] = '1'
    return view


def universe(snapshot, target, evaluation_at, repo_root):
    """Select current source facts without adding history or representations."""
    projection = project_official_holdings(snapshot, evaluation_at=evaluation_at)
    ledger = {}
    for row in projection['ledger_only_positions']:
        key = (row['account_key'], row['instrument_key'])
        previous = ledger.get(key)
        if previous is None or time(row['observed_at']) > time(previous['observed_at']):
            ledger[key] = row
        elif row['observed_at'] == previous['observed_at'] and row != previous:
            raise ValueError('MEMBER_LATEST_POSITION_AMBIGUOUS')
    by_symbol = {}
    for fact in projection['analysis_security_positions'] + list(ledger.values()):
        if fact['quantity'] is not None and Decimal(fact['quantity']) == 0:
            continue
        if not fact.get('symbol'):
            raise ValueError('MEMBER_HOLDING_INSTRUMENT_UNRESOLVED')
        entry = by_symbol.setdefault(fact['symbol'], {'symbol': fact['symbol'], 'holdings': [], 'targets': []})
        entry['holdings'].append(deepcopy(fact))
    for line in target['payload']['draft']['target_lines']:
        if line['weight']['value_state'] != 'KNOWN':
            raise ValueError('MEMBER_APPROVED_WEIGHT_UNRESOLVED')
        if Decimal(str(line['weight']['value'])) == 0 and line.get('ticker') not in by_symbol:
            continue
        key = line.get('ticker') or line['instrument_id']
        entry = by_symbol.setdefault(key, {'symbol': line.get('ticker'), 'holdings': [], 'targets': []})
        entry['targets'].append(deepcopy(line))
    # Reuse the original V75 applicability set solely to separate its assets.
    from formal_mode_analysis import native
    native(repo_root)
    path = Path(repo_root)/'系統工程/債券V75/正式Runtime/V75_Work6_RuntimeReady_2026-09-25/runtime'
    import sys
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent != path/'v75_runtime':
        raise PermissionError('MEMBER_BOND_APPLICABILITY_SOURCE_MISMATCH')
    from v75_runtime.work3 import US_LISTED_ASSETS, TW_LISTED_ASSETS
    registered = [r for r in snapshot['tables']['portfolio_instrument'] if r.get('ticker')]
    if len({r['ticker'] for r in registered}) != len(registered):
        raise ValueError('MEMBER_INSTRUMENT_LISTING_AMBIGUOUS')
    registry = {r['ticker']: r for r in registered}
    assets = []; excluded = []
    for key, entry in sorted(by_symbol.items()):
        symbol = entry['symbol']; instrument = registry.get(symbol)
        if instrument is None:
            instrument = next((t.get('source_instrument_row') for t in entry['targets']
                               if t.get('source_instrument_row')), None)
        types = {t['asset_type'].upper() for t in entry['targets']}
        cash = (instrument or {}).get('instrument_type') == 'CASH' or bool(types) and types <= {'CASH', '現金'}
        bond = symbol in US_LISTED_ASSETS | TW_LISTED_ASSETS
        entry.update(instrument=deepcopy(instrument),
            coverage_basis='HOLDING_AND_TARGET' if entry['holdings'] and entry['targets'] else
                           'HOLDING_ONLY' if entry['holdings'] else 'TARGET_ONLY',
            source_layer_conflict=symbol in projection['source_layer_conflicts'])
        if cash or bond:
            entry['route'] = 'V75_SEPARATE' if bond else 'CASH'
            excluded.append(entry)
        else:
            entry['route'] = 'V82'
            assets.append(entry)
    result = {'schema_version': 'Family.W8.MemberV82Universe.v1', 'client_id': snapshot['client_id'],
        'source_db_sha256': snapshot['source_sha256'], 'expected_count': len(assets),
        'assets': assets, 'excluded': excluded, 'holdings_projection_digest': digest(projection),
        'all_member_accounts_in_scope': True, 'missing_quantity_defaulted_to_zero': False,
        'approval_weight_denominator': target.get('weight_denominator'),
        'target_version': target.get('target_version')}
    result['universe_digest'] = digest(result)
    return result


def build_report(request, config, repo_root):
    from formal_mode_analysis import native
    native(repo_root)
    from native_asset_source import classification, native_core_observation
    from approved_v04_technical import load_profile
    from holdings_analysis import scenario_class, read_issuer_facts
    from core_analysis_inputs import issuer_inputs
    from formal_mode_analysis import build_formal_conclusion
    from livingwater_v82_runtime.approved_decision import slice_cap
    snapshot = request['client_snapshot']['payload']; client = request['client_id']
    if (snapshot['client_id'] != client or config['client_id'] != client
            or snapshot['source_sha256'] != config['source_db_sha256']
            or snapshot['payload_digest'] != digest(snapshot['tables'])
            or request['trade_authorization'] != 'NONE'):
        raise PermissionError('MEMBER_V82_SNAPSHOT_OR_OWNER_MISMATCH')
    if any(r.get('client_id', client) != client for rows in snapshot['tables'].values() for r in rows):
        raise PermissionError('MEMBER_V82_FOREIGN_CLIENT_ROW')
    target = target_source(snapshot, config, request['evaluation_at'])
    if request.get('confirmed_target') != target:
        raise PermissionError('MEMBER_V82_TARGET_SOURCE_REPLAY_MISMATCH')
    coverage = universe(snapshot, target, request['evaluation_at'], repo_root)
    profile = load_profile(Path(__file__).with_name('owner_approved_v10.json'))
    rows = []
    for asset in coverage['assets']:
        symbol = asset['symbol']; instrument = asset['instrument'] or {}
        cls = classification(symbol, config['classification_source'], config.get('product_sources', {}).get(symbol))
        # Preserve each explicit primary class's formal §32.6 metric order;
        # a global ETF's fallback order is not a QQQ/VOO/0050 waterfall.
        etf_waterfalls = {
            '美國大型核心ETF': ['FORWARD_PE','CAPE','TRAILING_PE','FCF_YIELD','PB'],
            '科技／AI／高成長ETF': ['FORWARD_PE','EV_EBITDA','EV_SALES','FCF_YIELD'],
            '台灣大型權值ETF': ['FORWARD_PE','PB','FCF_YIELD']}
        if cls['asset_type']!='INDIVIDUAL_STOCK' and 'valuation_waterfall' not in cls and cls['primary_class'] in etf_waterfalls:
            cls['valuation_waterfall'] = etf_waterfalls[cls['primary_class']]
        if cls['primary_class']=='UNKNOWN' and 'valuation_waterfall' not in cls:
            cls['valuation_waterfall'] = []
        market_error = None
        try:
            market = read_market(config.get('market_sources', {}).get(symbol), symbol=symbol,
                evaluation_at=request['evaluation_at'], repo_root=repo_root, profile=profile,
                is_etf=False if instrument.get('instrument_type') == 'STOCK' or cls['asset_type']=='INDIVIDUAL_STOCK' else
                       True if instrument.get('instrument_type') == 'ETF' or cls['asset_type'] in
                       ('BROAD_ETF','INDUSTRY_ETF','THEME_ETF') else None)
        except ValueError as error:
            if not str(error).startswith('MEMBER_MARKET_'):
                raise
            market = None; market_error = str(error)
        # Registry STOCK plus the exact provider EQUITY listing establishes the
        # stock route, not a company quality grade or a valuation framework.
        if (cls['asset_type'] is None and instrument.get('instrument_type') == 'STOCK'
                and market and market['market_identity']['provider_type'] == 'EQUITY'):
            cls.update(asset_type='INDIVIDUAL_STOCK', valuation_waterfall=[],
                identity_basis='OFFICIAL_MEMBER_REGISTRY_AND_EXACT_PROVIDER_EQUITY_LISTING')
        facts = asset['holdings']
        quantity = facts[0]['quantity'] if len(facts) == 1 and not asset['source_layer_conflict'] else None
        holding = {'quantity': quantity, 'quantity_state': 'KNOWN' if quantity is not None else 'UNKNOWN',
            'source_facts': deepcopy(facts), 'observed_at': facts[0].get('observed_at') if len(facts) == 1 else None,
            'absence_is_not_zero': True, 'account_aggregation_performed': False}
        row = {'instrument_id': instrument.get('instrument_key', 'SOURCE:'+symbol), 'symbol': symbol,
            'coverage_basis': asset['coverage_basis'], 'owner': deepcopy(request['owner']),
            'holding': holding, 'target_lines': deepcopy(asset['targets']), 'market': market,
            'native_product_identity': {**deepcopy(cls), 'registry_identity': deepcopy(instrument)},
            'primary_framework': cls['primary_framework'], 'scenario_class': scenario_class(repo_root, cls),
            'core_observation': None, 'formal_conclusion': None, 'position_valuation_allowed': False,
            'valuation_observations': [], 'issuer_facts': read_issuer_facts(
                config.get('issuer_facts_sources', {}).get(symbol), symbol, request['evaluation_at']),
            'call_trace': [], 'missing_inputs': [], 'execution_status': 'SOURCE_BLOCKED'}
        if market:
            metrics, fundamentals = issuer_inputs(row['issuer_facts'],
                allowed_metrics=cls.get('valuation_waterfall'))
            row['valuation_observations'] = metrics
            kwargs = {'valuation_waterfall': cls['valuation_waterfall']} if 'valuation_waterfall' in cls else {}
            row['core_observation'] = native_core_observation(repo_root, market,
                valuation_metrics=metrics, fundamental_fields=fundamentals,
                broad_etf=cls['asset_type'] != 'INDIVIDUAL_STOCK', **kwargs)
            if market.get('independent_close_observation'):
                close = {**market, **market['independent_close_observation']}
                row['independent_close_core_observation'] = native_core_observation(repo_root, close,
                    valuation_metrics=metrics, fundamental_fields=fundamentals,
                    broad_etf=cls['asset_type'] != 'INDIVIDUAL_STOCK', **kwargs)
            row['formal_conclusion'] = build_formal_conclusion(repo_root, row, request,
                approved_source_descriptor=config.get('approved_sources', {}).get(symbol))
            conclusion = row['formal_conclusion']; analysis = conclusion['approved_v10_analysis']
            row['daily_slice'] = slice_cap(analysis, conclusion['approved_v10_context'],
                permission=conclusion['buy_permission']['value'], positive_gap=None)
            row['execution_status'] = 'NATIVE_COMPONENTS_COMPUTED'
            row['call_trace'] = (market['call_trace'] + ['V82.evaluate_core_rule_state']
                                 + analysis['call_trace'] + ['V82.approved_decision.slice_cap'])
            for item in row['core_observation']['input_gaps']:
                row['missing_inputs'].append(missing(item['field_path'], 'W8.core_analysis_inputs',
                    item['reason'], ['dependent Core safety/permission'],
                    kind='PRODUCER_NOT_CONNECTED' if item['kind']=='DEFINITION_OR_PRODUCER_UNRESOLVED'
                    else 'EXTERNAL_SOURCE_OR_APPROVAL_REQUIRED'))
            for key in ('qV', 'qP'):
                if analysis[key]['status'] != 'COMPLETE':
                    row['missing_inputs'].append(missing(key, 'V82.own_history',
                        ';'.join(analysis[key]['reason_codes']), ['dependent Stage/price-depth branches']))
            for field in conclusion['deployment_gap']['missing_fields']:
                row['missing_inputs'].append(missing(field, 'W8.formal_mode_analysis',
                    'ORIGINAL_GAP_REQUIRED_INPUT_NOT_SOURCE_QUALIFIED', ['Projected/Gap']))
            if market['observed_date'] != market['latest_expected_completed_session']:
                row['missing_inputs'].append(missing('market.latest_completed_session', 'market provider',
                    market['observed_date']+' < '+market['latest_expected_completed_session'], ['current-as-of conclusion']))
            if market['history_quality']['invalid_source_rows'] or market['history_quality']['discarded_before_last_gap']:
                row['missing_inputs'].append(missing('market.contiguous_full_ohlcv_history', 'exact listing market provider/calendar',
                    'INVALID_OR_MISSING_EXPECTED_BARS__ORIGINAL_VALUES_RETAINED',
                    ['long-window OHLC predicates; independent Close components are reported separately']))
        else:
            row['missing_inputs'].append(missing('market.history', 'exact listing market provider',
                market_error or 'EXACT_SYMBOL_COMPLETED_HISTORY_UNAVAILABLE', ['technical/Core/Mode/Stage/M']))
        row['missing_inputs'] += [
            missing('cycle_snapshot', 'persistent V82 cycle ledger source',
                'NO_MEMBER_ASSET_EXCHANGE_BOUND_CYCLE_SNAPSHOT_SUPPLIED', ['remaining daily room']),
            missing('work3/C7/funding/execution_constraints', 'original Work3/C7/Work4 producers',
                'FULL_SAME_RUN_FINANCIAL_BUNDLE_NOT_BOUND', ['final amount/caps/MIN/lot/shared cash'],
                kind='UPSTREAM_INTEGRATION_NOT_COMPLETED'),
        ]
        for field in ('asset_type','asset_grade','primary_framework'):
            if cls[field] in (None,'UNKNOWN'):
                row['missing_inputs'].append(missing('native_product_identity.'+field,
                    'W8.native_asset_source.classification / independent product/company evidence',
                    'UNRESOLVED_VALUE='+str(cls[field]), ['dependent formal framework/Stage/grade limits'],
                    kind='SOURCE_OR_FRAMEWORK_MAPPING_UNRESOLVED'))
        row.update(proposed_amount=None, trade_action='NO_TRADE', trade_authorization='NONE',
            full_native_pipeline_complete=False, data_complete=not row['missing_inputs'])
        row['result_digest'] = digest(row)
        rows.append(row)
    report = {'schema_version': SCHEMA, 'status': 'ANALYSIS_PARTIAL',
        'scope': 'ALL_MEMBER_V82_HOLDINGS_AND_APPROVED_TARGETS__ORIGINAL_COMPONENT_CHAIN',
        'client_id': client, 'run_id': request['run_id'], 'evaluation_at': request['evaluation_at'],
        'request_digest': digest(request), 'source_db_sha256': snapshot['source_sha256'],
        'config_digest': digest(config), 'universe': coverage, 'positions': rows,
        'summary': {'expected': coverage['expected_count'], 'tested': len(rows),
            'native_components_computed': sum(r['execution_status']=='NATIVE_COMPONENTS_COMPUTED' for r in rows),
            'source_blocked': sum(r['execution_status']=='SOURCE_BLOCKED' for r in rows),
            'data_complete': sum(r['data_complete'] for r in rows)},
        'canonical_result': None, 'full_native_pipeline_complete': False,
        'full_native_mentor_reached': False, 'mentor': None, 'cash_overlay_applied': False,
        'database_written': False, 'trade_authorization': 'NONE', 'trade_action': 'NO_TRADE',
        'call_trace': ['Family.Menu04', 'W8.OnDemandAnalysisProvider',
            'W5.project_official_holdings', 'W8.official_target_input.read_confirmed_weights',
            'W8.member_v82_analysis.universe', 'ORIGINAL_V82_COMPONENT_CHAIN']}
    report['report_digest'] = digest(report)
    return report


class MemberV82SourceProducer:
    def __init__(self, *, repo_root, **config):
        self.root = Path(repo_root); self.config = deepcopy(config)

    def __call__(self, snapshot, payload):
        # Establish imports/approved native path before the pure report replay.
        from formal_mode_analysis import native
        native(self.root)
        at = datetime.now(timezone.utc).isoformat(); run = 'member-v82-'+uuid.uuid4().hex
        request = {'schema_version': 'Family.W8.MemberV82Request.v1', 'client_id': snapshot['client_id'],
            'run_id': run, 'evaluation_at': at, 'question': payload['question'],
            'owner': {'client_id': snapshot['client_id'], 'scope': 'ALL_MEMBER_ACCOUNTS',
                'account': None, 'broker': None, 'currency': None, 'funding_domain': None},
            'client_snapshot': {'payload': deepcopy(snapshot)}, 'trade_authorization': 'NONE'}
        request['confirmed_target'] = target_source(snapshot, self.config, at)
        report = build_report(request, self.config, self.root)
        return {'request': request, 'trusted_context': {'client_id': snapshot['client_id'],
            'trade_authorization': 'NONE', 'member_v82_config': deepcopy(self.config)},
            'member_v82_report': report, 'source_metadata': {'client_id': snapshot['client_id'],
                'source_db_sha256': snapshot['source_sha256'], 'run_id': run}}


class MemberV82Runner:
    def __init__(self, *, repo_root, context, report):
        self.root = Path(repo_root); self.context = deepcopy(context); self.report = deepcopy(report)

    def context_provider(self):
        return deepcopy(self.context)

    def analyze(self, request):
        expected = build_report(request, self.context['member_v82_config'], self.root)
        if expected != self.report:
            raise PermissionError('MEMBER_V82_NATIVE_SOURCE_REPLAY_MISMATCH')
        return deepcopy(expected)
