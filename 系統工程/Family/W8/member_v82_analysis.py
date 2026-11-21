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
import calendar
import re

from family_input import digest
from official_holdings_source import project_official_holdings
from official_target_input import read_confirmed_weights
from member_market_source import read_market, time

SCHEMA = 'Family.W8.MemberV82Analysis.v1'
V70_SAFETY_SIGNAL_NAMES = frozenset((
    'fed_policy', 'fed_policy_bias', 'treasury_2y', 'treasury_10y', 'treasury_30y',
    'real_yield', 'cpi', 'core_cpi', 'pce', 'core_pce', 'gdp',
    'employment_unemployment_rate', 'employment_nonfarm_payrolls_3m_avg',
    'hy_oas', 'ig_oas', 'bbb_oas', 'a_oas', 'sofr', 'repo', 'rrp', 'srf',
    'fra_ois', 'sofr_ois', 'move', 'vix', 'treasury_market_liquidity',
    'liquidity_regime', 'material_macro_events'))


def build_v70_safety_snapshot_source(local_path, *, source_reference, standing_authority_binding):
    """Bind a newly captured original Drive file to independent trusted config.

    The caller supplies authenticated Drive-capture bytes and the PM-verified
    authority, never authority copied from the daily JSON. Rebuild this
    descriptor for each capture; a bound runner still rejects changed bytes.
    """
    if not source_reference:
        raise ValueError('V70_SAFETY_SNAPSHOT_LINEAGE_REQUIRED')
    path = Path(local_path)
    return {'local_path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest(),
        'source_reference': source_reference,
        'standing_maintenance_authorization': deepcopy(standing_authority_binding)}


def missing(field, producer, reason, affects, *, kind='EXTERNAL_SOURCE_OR_APPROVAL_REQUIRED'):
    return {'field': field, 'producer': producer, 'reason': reason,
            'affects': affects, 'kind': kind}


def target_source(snapshot, config, evaluation_at):
    from owner_target_decision_source import project
    historical=_historical_target_source(snapshot,config,evaluation_at)
    selected=project(snapshot,config,evaluation_at,historical)
    from owner_etf_constraints_source import project as project_etf_constraints
    return project_etf_constraints(snapshot,config,evaluation_at,selected)


def _historical_target_source(snapshot, config, evaluation_at):
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
    if args.get('dated_pool_source') is not None:args['evaluation_at']=evaluation_at
    pack = build_approved_target_view(**args);view=pack['target']
    if args.get('dated_pool_source') is not None:
        from dated_document_target_source import replay
        return replay(view,pack['trusted_approved_target_source'],evaluation_at=evaluation_at,snapshot=snapshot)[0]
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
        pending=(target.get('complete_allocation') is False
            and line.get('selection_state')=='CONFIRMED_INSTRUMENT_WEIGHT_PENDING'
            and line.get('ticker') in (target.get('owner_selection_decision') or {}).get('included_weight_pending',[]))
        if line['weight']['value_state'] != 'KNOWN' and not pending:
            raise ValueError('MEMBER_APPROVED_WEIGHT_UNRESOLVED')
        if not pending and Decimal(str(line['weight']['value'])) == 0 and line.get('ticker') not in by_symbol:
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
    registry={}
    for row in registered:registry.setdefault(row['ticker'],[]).append(row)
    assets = []; excluded = []
    for key, entry in sorted(by_symbol.items()):
        symbol = entry['symbol']; candidates=registry.get(symbol,[])
        instrument=candidates[0] if len(candidates)==1 else None
        if len(candidates)>1:
            keys={p.get('instrument_key') for p in entry['holdings'] if p.get('source_kind')=='OWNER_CONFIRMED_QUANTITY'}
            anchored=[r for r in candidates if r['instrument_key'] in keys]
            if len(anchored)!=1:raise ValueError('MEMBER_INSTRUMENT_LISTING_AMBIGUOUS')
            instrument=anchored[0]
            if any(any(r.get(k) is not None and instrument.get(k) is not None and r[k]!=instrument[k]
                    for k in ('instrument_type','quote_currency','exchange_code','isin')) for r in candidates):
                raise ValueError('MEMBER_INSTRUMENT_LISTING_AMBIGUOUS')
            entry.update(instrument_identity_candidates=deepcopy(candidates),
                analysis_instrument_binding='EXPLICIT_OWNER_POSITION_KEY__TARGET_ALIAS_NOT_ATTESTED')
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


def read_v70_safety_snapshot(source, evaluation_at):
    """Read approved shared evidence; the original V82 Core decides safety."""
    raw = Path(source['local_path']).read_bytes()
    fingerprint = sha256(raw).hexdigest()
    if fingerprint != source['sha256']:
        raise PermissionError('V70_SAFETY_SNAPSHOT_HASH_MISMATCH')
    snapshot = json.loads(raw)
    if snapshot.get('schema_version') != 'V70.3/family-macro-safety-v2':
        raise ValueError('V70_SAFETY_SNAPSHOT_SCHEMA_MISMATCH')
    approval = snapshot.get('approval', {})
    if not isinstance(approval, dict) or approval.get('status') != 'APPROVED' or not approval.get('record_url'):
        raise PermissionError('V70_SAFETY_SNAPSHOT_APPROVAL_REQUIRED')
    extension = snapshot.get('extension_approval')
    standing = (isinstance(extension, dict)
                and extension.get('approval_type') == 'STANDING_MAINTENANCE_AUTHORIZATION')
    if standing:
        # The PM-bound descriptor carries the accepted maintenance authority.
        # Daily producer output cannot grant itself a wider source scope.
        authority = source.get('standing_maintenance_authorization') or {}
        if (not isinstance(authority, dict)
                or authority.get('status') != 'PASS_PM_ACTIVATION_ACCEPTED'
                or not authority.get('record_url')
                or extension.get('status') != 'APPROVED'
                or extension.get('record_url') != authority['record_url']
                or approval.get('record_url') != authority['record_url']
                or approval.get('approval_type') != extension['approval_type']
                or extension.get('approved_at') != authority.get('approved_at')
                or not extension.get('approved_by') or not extension.get('scope')):
            raise PermissionError('V70_STANDING_AUTHORIZATION_REQUIRED')
        numeric = authority.get('approved_numeric_signal_keys')
        reserved = authority.get('unknown_signal_keys')
        if (not isinstance(numeric, list) or not isinstance(reserved, list)
                or len(numeric) != len(set(numeric)) or len(reserved) != len(set(reserved))
                or set(numeric) & set(reserved)
                or set(numeric) | set(reserved) != V70_SAFETY_SIGNAL_NAMES
                or not isinstance(extension.get('approved_numeric_signal_keys'), list)
                or not isinstance(extension.get('unknown_signal_keys'), list)
                or len(extension['approved_numeric_signal_keys']) != len(numeric)
                or len(extension['unknown_signal_keys']) != len(reserved)
                or set(extension['approved_numeric_signal_keys']) != set(numeric)
                or set(extension['unknown_signal_keys']) != set(reserved)
                or any(snapshot['signals'].get(k, {}).get('value') is not None for k in reserved)):
            raise PermissionError('V70_STANDING_AUTHORIZED_SCOPE_MISMATCH')
        context = snapshot.get('automatic_context_validation') or {}
        publication = snapshot.get('upstream_publication') or {}
        if (context.get('status') != 'FORMAL_LIVE_FEED_AND_DAILY_CAPTURE_MATCH'
                or context.get('human_per_run_approval_claimed') is not False
                or approval.get('human_review_of_current_snapshot') is not False
                or extension.get('human_review_of_current_snapshot') is not False
                or publication.get('mode') != 'FORMAL'
                or publication.get('scoringAllowed') is not True
                or not re.fullmatch(r'[0-9a-f]{64}', snapshot.get('publication_identity', ''))):
            raise PermissionError('V70_STANDING_FORMAL_PUBLICATION_REQUIRED')
        ordered = (time(approval['approved_at']) <= time(authority['approved_at'])
                   <= time(snapshot['data_cutoff']) <= time(snapshot['snapshot_timestamp'])
                   <= time(snapshot['run_timestamp_utc']) <= time(evaluation_at)
                   and time(authority['approved_at']) <= time(authority['activation_acceptance_at'])
                   <= time(evaluation_at))
    elif extension is not None:
        if (not isinstance(extension, dict) or extension.get('status') != 'APPROVED'
                or not extension.get('record_url') or not extension.get('approved_by')
                or not extension.get('scope')
                or not isinstance(extension.get('candidate_sha256'), str)
                or len(extension['candidate_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in extension['candidate_sha256'])):
            raise PermissionError('V70_SAFETY_SNAPSHOT_EXTENSION_APPROVAL_REQUIRED')
        ordered = (time(snapshot['data_cutoff']) <= time(approval['approved_at'])
                   <= time(snapshot['snapshot_timestamp']) <= time(extension['approved_at'])
                   <= time(evaluation_at))
    else:
        ordered = (time(snapshot['data_cutoff']) <= time(snapshot['snapshot_timestamp'])
                   <= time(approval['approved_at']) <= time(evaluation_at))
    if not ordered:
        raise PermissionError('V70_SAFETY_SNAPSHOT_AFTER_EVALUATION')
    if not source.get('source_reference') or not snapshot.get('upstream_snapshot_reference'):
        raise ValueError('V70_SAFETY_SNAPSHOT_LINEAGE_REQUIRED')
    signals = snapshot['signals']
    if not isinstance(signals, dict) or set(signals) != V70_SAFETY_SIGNAL_NAMES:
        raise ValueError('V70_SAFETY_SNAPSHOT_SIGNAL_SET_MISMATCH')
    if (not isinstance(snapshot.get('v70_indicators'), dict)
            or not isinstance(snapshot.get('v70_judgments'), dict)
            or not isinstance(snapshot.get('consumer'), dict)):
        raise ValueError('V70_SAFETY_SNAPSHOT_ORIGINAL_EVIDENCE_REQUIRED')
    unknowns = []
    for name, signal in signals.items():
        if not isinstance(signal, dict) or name != signal.get('signal_name') or 'value' not in signal:
            raise ValueError('V70_SAFETY_SNAPSHOT_SIGNAL_MISMATCH:' + name)
        if signal['value'] is None:
            if signal.get('data_quality') != 'UNKNOWN' or not signal.get('issue_detail'):
                raise ValueError('V70_SAFETY_SNAPSHOT_UNKNOWN_REASON_REQUIRED:' + name)
            unknowns.append(name)
        elif (not signal.get('data_quality') or signal.get('data_quality') == 'UNKNOWN' or not signal.get('source')
              or not signal.get('as_of')):
            raise ValueError('V70_SAFETY_SNAPSHOT_SIGNAL_PROVENANCE_REQUIRED:' + name)
        for field in ('as_of', 'published_at'):
            value = signal.get(field)
            if value is not None:
                quarter = re.fullmatch(r'(\d{4})-Q([1-4])', value) if field == 'as_of' else None
                if quarter:
                    year, month = int(quarter[1]), int(quarter[2]) * 3
                    observed = datetime(year, month, calendar.monthrange(year, month)[1])
                    if observed.date() > time(snapshot['data_cutoff']).date():
                        raise PermissionError('V70_SAFETY_SNAPSHOT_FUTURE_SIGNAL:' + name)
                    continue
                observed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                future = (time(value) > time(snapshot['data_cutoff']) if len(value) > 10
                          else observed.date() > time(snapshot['data_cutoff']).date())
                if future:
                    raise PermissionError('V70_SAFETY_SNAPSHOT_FUTURE_SIGNAL:' + name)
    # Keep the whole approved upstream object, including original indicator
    # IDs, judgments, caveats and dates. Nothing here becomes a Core safety
    # assertion or a permission; the independent v3 feed remains unchanged.
    return {**deepcopy(snapshot),
        'source_reference': source['source_reference'], 'sha256': fingerprint,
        'safety_assessment_status': snapshot['consumer']['safety_assessment_status'],
        'unknown_signals': sorted(unknowns),
        **({'standing_maintenance_authorization': deepcopy(authority)} if standing else {}),
    }


def normal_buy_pause(row):
    quote = row.get('same_run_gap_price')
    core = row.get('core_observation') or {}
    market = row.get('market') or {}
    comparison = market.get('independent_history_comparison') or {}
    technical_hash = comparison.get('technical_source_sha256') if quote and comparison.get('position_valuation_source_sha256') == quote['source_sha256'] else (quote or {}).get('source_sha256')
    if (not quote or not row.get('holding', {}).get('current_broker_position')
            or core.get('source_sha256') != technical_hash
            or core.get('result', {}).get('technical', {}).get('runaway_down') != 'TRUE'):
        return None
    approved = (market.get('approved_technical') or {}).get('signals', {})
    votes = {group: [v['name'] for v in approved.get(group, ()) if v['truth'] == 'TRUE'
                     and v.get('reason') == 'APPROVED_V10_COMPUTED'] for group in ('down_break','down_accel')}
    if len(set(votes['down_break'])) < 1 or len(set(votes['down_accel'])) < 2:
        return None
    return {'status': 'NORMAL_NEW_BUYS_PAUSED', 'rule': 'V82 CMR7 / 44-A / 44-E',
            'run_id': quote['run_id'], 'evaluation_at': quote['evaluation_at'], 'symbol': row['symbol'],
            'source_sha256': technical_hash, 'position_valuation_source_sha256':quote['source_sha256'],
            'session': quote['session'], 'votes': votes,
            'amount': {'amount':'0','currency':quote['currency']}, 'quantity':'0',
            'sell_intent_created': False, 'target_and_gap_preserved': True}


def assessed_holding(asset, symbol, current_owner, config, request):
    from owner_current_business import holding_view
    facts = asset['holdings']
    quantity = facts[0]['quantity'] if len(facts) == 1 and not asset['source_layer_conflict'] else None
    holding = {'quantity': quantity, 'quantity_state': 'KNOWN' if quantity is not None else 'UNKNOWN',
        'source_facts': deepcopy(facts), 'observed_at': facts[0].get('observed_at') if len(facts) == 1 else None,
        'absence_is_not_zero': True, 'account_aggregation_performed': False}
    holding=holding_view(holding,symbol,current_owner)
    from current_market_contract import compare_broker_quantity
    holding = compare_broker_quantity(config.get('current_cash_corroboration'), holding, symbol, request)
    return holding


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
    safety_source = config.get('v70_safety_snapshot_source')
    safety_snapshot = (read_v70_safety_snapshot(safety_source, request['evaluation_at'])
                       if safety_source is not None else None)
    from v70_safety_decisions import read_source_window,produce as produce_safety_decisions
    safety_window = read_source_window(config.get('v70_safety_window_source'), safety_snapshot, request)
    safety_decisions = produce_safety_decisions(safety_snapshot,request['evaluation_at'],safety_window) if safety_snapshot else None
    from owner_financial_confirmation import read as read_owner_financial_confirmation
    owner_facts = read_owner_financial_confirmation(config.get('owner_financial_confirmation_source'),request)
    from owner_current_business import read as read_current_owner,holding_view,order_confirmation
    current_owner=read_current_owner(config.get('owner_current_business_source'),request)
    from current_market_contract import read as read_current_market,new_buy_scope,portfolio_reference,gap_price
    market_contract=read_current_market(config.get('current_market_contract_source'),request)
    coverage = universe(snapshot, target, request['evaluation_at'], repo_root)
    ledger_resource={'status':'MEMBER_LEDGER_NOT_REGISTERED','cycle_count':None,
        'resource_initialized':False,'financial_cycle_initialized':False}
    if config.get('member_db_path'):
        from on_demand_drive_io import Binding,inspect
        from v82_ledger_drive import resolve_resource
        binding=Binding(**config['member_drive_binding'])
        if binding.client_id!=client or inspect(config['member_db_path'],binding)['sha256']!=snapshot['source_sha256']:
            raise PermissionError('MEMBER_LEDGER_SNAPSHOT_BINDING_MISMATCH')
        ledger_resource=resolve_resource(config['member_db_path'],binding,
            config.get('ledger_source'),evaluation_at=request['evaluation_at'])
    profile = load_profile(Path(__file__).with_name('owner_approved_v10.json'))
    rows = []
    for asset in coverage['assets']:
        symbol = asset['symbol']; instrument = asset['instrument'] or {}
        cls = classification(symbol, config['classification_source'], config.get('product_sources', {}).get(symbol),
            evaluation_at=request['evaluation_at'])
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
                       ('BROAD_ETF','SECTOR_ETF','INDUSTRY_ETF','THEME_ETF') else None)
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
        holding = assessed_holding(asset, symbol, current_owner, config, request)
        row = {'instrument_id': instrument.get('instrument_key', 'SOURCE:'+symbol), 'symbol': symbol,
            'coverage_basis': asset['coverage_basis'], 'owner': deepcopy(request['owner']),
            'holding': holding, 'target_lines': deepcopy(asset['targets']), 'market': market,
            'native_product_identity': {**deepcopy(cls), 'registry_identity': deepcopy(instrument)},
            'primary_framework': cls['primary_framework'], 'scenario_class': scenario_class(repo_root, cls),
            'core_observation': None, 'formal_conclusion': None, 'position_valuation_allowed': False,
            'valuation_observations': [], 'issuer_facts': read_issuer_facts(
                config.get('issuer_facts_sources', {}).get(symbol), symbol, request['evaluation_at']),
            'call_trace': [], 'missing_inputs': [], 'execution_status': 'SOURCE_BLOCKED'}
        price = gap_price(market_contract, market, instrument, symbol, request)
        if price:
            row['position_valuation_allowed'] = True
            row['same_run_gap_price'] = price
        registered_structure = config.get('registered_issuer_structures', {}).get(symbol)
        if (registered_structure and time(registered_structure['retrieved_at']) <= time(request['evaluation_at'])
                and registered_structure['as_of'] <= time(request['evaluation_at']).date().isoformat()):
            row['registered_issuer_structure'] = deepcopy(registered_structure)
        history_sources=config.get('public_history_sources',{}).get(symbol)
        buy_scope=new_buy_scope(market_contract,symbol)
        if buy_scope is not None:row['new_buy_scope']=buy_scope
        if owner_facts is not None:
            row['owner_buy_confirmation']=deepcopy(owner_facts['buy_order_confirmation'])
        if current_owner is not None:
            row['owner_order_confirmation']=order_confirmation(current_owner,request)
        if history_sources is not None:
            from historical_source_qualification import bind
            row['history_source_qualification']=bind(history_sources,request,symbol)
        if asset.get('analysis_instrument_binding'):
            row['missing_inputs'].append(missing('target.listing_identity',
                'original holding instrument and target registry rows',
                asset['analysis_instrument_binding'],['formal target-to-holding financial join'],
                kind='SOURCE_IDENTITY_QUALIFICATION_REQUIRED'))
        if safety_snapshot is not None:
            row['macro_observations']=deepcopy(safety_decisions)
        if market:
            from v82_core_source import read as read_core_source
            core_source=read_core_source(config.get('core_sources',{}).get(symbol),request,symbol)
            metrics, fundamentals = issuer_inputs(row['issuer_facts'],
                allowed_metrics=cls.get('valuation_waterfall'))
            row['valuation_observations'] = metrics
            if request.get('macro_snapshot') is not None:
                from v10_source_observations import macro_observations,forward_observations
                v3_observations=macro_observations(request['macro_snapshot'],request['evaluation_at'])
                if safety_snapshot is None:
                    row['macro_observations']=v3_observations
                else:
                    row['v3_macro_observations']=v3_observations
                forward=forward_observations(request['macro_snapshot'],symbol,request['evaluation_at'])
                metrics,fundamentals=issuer_inputs(row['issuer_facts'],forward,allowed_metrics=cls.get('valuation_waterfall'))
                row['valuation_observations']=metrics
            kwargs = {'valuation_waterfall': cls['valuation_waterfall']} if 'valuation_waterfall' in cls else {}
            if safety_snapshot is not None:
                kwargs['macro_observations']=row['macro_observations']
            if cls.get('valuation_profile') is not None:
                kwargs['valuation_profile']=deepcopy(cls['valuation_profile'])
            row['core_observation'] = native_core_observation(repo_root, market,
                valuation_metrics=metrics, fundamental_fields=fundamentals,
                broad_etf=cls['asset_type'] != 'INDIVIDUAL_STOCK', qualified_core_source=core_source, **kwargs)
            row['valuation_observations']=deepcopy(row['core_observation']['actual_inputs']['valuation_metrics'])
            close_source = market.get('independent_broker_observation', market)
            if close_source.get('independent_close_observation'):
                close = {**close_source, **close_source['independent_close_observation']}
                row['independent_close_core_observation'] = native_core_observation(repo_root, close,
                    valuation_metrics=metrics, fundamental_fields=fundamentals,
                    broad_etf=cls['asset_type'] != 'INDIVIDUAL_STOCK', qualified_core_source=core_source, **kwargs)
            row['formal_conclusion'] = build_formal_conclusion(repo_root, row, request,
                approved_source_descriptor=config.get('approved_sources', {}).get(symbol))
            conclusion = row['formal_conclusion']; analysis = conclusion['approved_v10_analysis']
            row['daily_slice'] = slice_cap(analysis, conclusion['approved_v10_context'],
                permission=conclusion['buy_permission']['value'], positive_gap=None)
            row['execution_status'] = 'NATIVE_COMPONENTS_COMPUTED'
            row['call_trace'] = (market['call_trace'] +
                                 (row['macro_observations']['call_trace'] if safety_snapshot is not None else [])+
                                 ['V82.evaluate_core_rule_state']
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
        row['planning_ledger_resource']={k:v for k,v in ledger_resource.items()
            if k in ('status','cycle_count','resource_initialized','financial_cycle_initialized',
                'sha256','reference','requires_serialized_writer','distributed_remote_cas_provided')}
        row['missing_inputs'] += [
            missing('cycle_snapshot', 'persistent V82 cycle ledger source',
                'QUALIFIED_GAP_AND_OWNER_SESSION_REQUIRED_FOR_CYCLE_INITIALIZATION'
                if ledger_resource['status']=='VERIFIED_REGISTERED_DRIVE_RESOURCE' else ledger_resource['status'],
                ['remaining daily room'],kind='UPSTREAM_QUALIFICATION_REQUIRED'
                if ledger_resource['status']=='VERIFIED_REGISTERED_DRIVE_RESOURCE' else 'LEDGER_TRANSPORT_INPUT_REQUIRED'),
            missing('work3/C7/funding/execution_constraints', 'original Work3/C7/Work4 producers',
                'FULL_SAME_RUN_FINANCIAL_BUNDLE_NOT_BOUND', ['final amount/caps/MIN/lot/shared cash'],
                kind='UPSTREAM_INTEGRATION_NOT_COMPLETED'),
        ]
        if buy_scope is not None:
            inactive={'cycle_snapshot','work3/C7/funding/execution_constraints'}
            row['inactive_new_buy_dependencies']=[deepcopy(m) for m in row['missing_inputs'] if m['field'] in inactive]
            row['missing_inputs']=[m for m in row['missing_inputs'] if m['field'] not in inactive]
            row['cycle_initialization_status']='NOT_APPLICABLE_NO_ADDITIONAL_BUY_AUTHORIZATION'
        for field in ('asset_type','asset_grade','primary_framework'):
            if cls[field] in (None,'UNKNOWN'):
                row['missing_inputs'].append(missing('native_product_identity.'+field,
                    'W8.native_asset_source.classification / independent product/company evidence',
                    'UNRESOLVED_VALUE='+str(cls[field]), ['dependent formal framework/Stage/grade limits'],
                    kind='SOURCE_OR_FRAMEWORK_MAPPING_UNRESOLVED'))
        row.update(proposed_amount=None, trade_action='NO_TRADE', trade_authorization='NONE',
            full_native_pipeline_complete=False, data_complete=not row['missing_inputs'])
        pause = normal_buy_pause(row)
        if pause:
            row.update(normal_buy_pause=pause, proposed_amount=deepcopy(pause['amount']), proposed_quantity=pause['quantity'])
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
        'planning_ledger_resource':{k:v for k,v in ledger_resource.items() if k!='cycles'},
        'full_native_mentor_reached': False, 'mentor': None, 'cash_overlay_applied': False,
        'database_written': False, 'trade_authorization': 'NONE', 'trade_action': 'NO_TRADE',
        'call_trace': ['Family.Menu04', 'W8.OnDemandAnalysisProvider',
            'W5.project_official_holdings', 'W8.official_target_input.read_confirmed_weights',
            'W8.member_v82_analysis.universe', 'ORIGINAL_V82_COMPONENT_CHAIN']}
    from all_asset_coverage import build as build_all_asset_coverage
    report['all_asset_coverage'] = build_all_asset_coverage(request,config,coverage,repo_root,
        ledger_resource=ledger_resource)
    if config.get('position_valuation_inputs') is not None:
        from member_position_valuation import produce
        report['source_position_valuations']=produce(request,report['all_asset_coverage'],rows,
            config['position_valuation_inputs'],current_market_contract=market_contract)
    if config.get('current_cash_corroboration'):
        from current_market_contract import broker_cash_check
        report['broker_cash_corroboration'] = broker_cash_check(config['current_cash_corroboration'], owner_facts, request)
    if safety_snapshot is not None:
        report['v70_safety_snapshot'] = safety_snapshot
    if owner_facts is not None:
        report['accepted_owner_financial_facts']=deepcopy(owner_facts)
    if current_owner is not None:
        report['current_owner_business_facts']=deepcopy(current_owner)
    if market_contract is not None:
        report['current_market_contract']=market_contract
        report['current_portfolio_reference']=portfolio_reference(request,report['all_asset_coverage'],
            report['source_position_valuations'],owner_facts,current_owner,market_contract)
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
        if self.config.get('run_binding') is not None:
            binding=self.config['run_binding']
            if (binding.get('client_id')!=snapshot['client_id'] or not binding.get('run_id')
                or time(binding['evaluation_at'])>time(at)):
                raise PermissionError('MEMBER_FINANCIAL_RUN_BINDING_MISMATCH')
            at=binding['evaluation_at'];run=binding['run_id']
        request = {'schema_version': 'Family.W8.MemberV82Request.v1', 'client_id': snapshot['client_id'],
            'run_id': run, 'evaluation_at': at, 'question': payload['question'],
            'owner': {'client_id': snapshot['client_id'], 'scope': 'ALL_MEMBER_ACCOUNTS',
                'account': None, 'broker': None, 'currency': None, 'funding_domain': None},
            'client_snapshot': {'payload': deepcopy(snapshot)}, 'trade_authorization': 'NONE'}
        request['confirmed_target'] = target_source(snapshot, self.config, at)
        if self.config.get('macro_snapshot') is not None:
            from market_bridge import read_macro_snapshot
            saved=deepcopy(self.config['macro_snapshot'])
            source_path=Path(saved['source_path'])
            if not source_path.is_absolute():source_path=self.root/source_path
            if sha256(source_path.read_bytes()).hexdigest()!=saved['source_sha256']:
                raise PermissionError('MEMBER_MACRO_SOURCE_BYTES_CHANGED')
            from v10_source_observations import checked_payload
            checked_payload(saved,at)
            if time(saved['capture_receipt']['captured_at'])>time(at):
                raise PermissionError('MEMBER_MACRO_CAPTURE_AFTER_EVALUATION')
            request['macro_snapshot']=saved
        elif self.config.get('macro_source_enabled') is True:
            from market_bridge import read_macro_snapshot
            options={'source':self.config['macro_source']} if self.config.get('macro_source') else {}
            request['macro_snapshot']=read_macro_snapshot(self.root,source_commit=self.config.get('source_commit'),
                capture_bound=True,**options)
            captured=datetime.now(timezone.utc).isoformat()
            if self.config.get('run_binding') is not None and time(captured)>time(at):
                raise PermissionError('MEMBER_PINNED_RUN_REQUIRES_PRECAPTURED_MACRO')
            request['evaluation_at']=captured
            request['confirmed_target']=target_source(snapshot,self.config,captured)
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
        from member_financial_chain import complete_report
        return complete_report(expected,request,self.context['member_v82_config'],self.root)
