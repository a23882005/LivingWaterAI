"""All-asset source inventory beside the existing V82/V75 financial owners.

The V82-only denominator is preserved. Bonds, cash and account completeness
have their own denominators and do not disappear through that equity filter.
"""
from copy import deepcopy
from datetime import datetime
from family_input import digest
from member_market_source import read_market
from w1_portfolio_observations import normalize


def read_broker_views(request, config):
    """Reuse the original owner-authorized read-only normalizer per account."""
    from broker_snapshot_source import read, pinned
    accounts={a['account_key'] for a in request['client_snapshot']['payload']['tables'].get('portfolio_account',[])}
    views=[];seen=set()
    for descriptor in config.get('current_broker_sources',[]):
        manifest=pinned(descriptor);owner=manifest.get('owner') or {}
        if owner.get('client_id')!=request['client_id'] or owner.get('account') not in accounts:
            raise PermissionError('ALL_ASSET_FOREIGN_BROKER_ACCOUNT')
        key=(owner['account'],owner.get('currency'))
        if key in seen:raise ValueError('ALL_ASSET_DUPLICATE_BROKER_ACCOUNT')
        seen.add(key)
        views.append(read({**request,'owner':deepcopy(owner)},descriptor))
    return views


def build(request, config, coverage, repo_root, *, ledger_resource=None):
    snapshot = request['client_snapshot']['payload']
    if snapshot['source_sha256'] != config['source_db_sha256']:
        raise PermissionError('ALL_ASSET_SOURCE_DB_MISMATCH')
    review = normalize(request) if snapshot['tables'].get('portfolio_account') else {
        'accounts':[],'status':'ACCOUNT_SOURCE_NOT_PROVIDED','complete_reconciliation_facts':False}
    broker_views=read_broker_views(request,config)
    from formal_v75_parameters import read as read_parameters
    parameters = read_parameters(config.get('v75_parameter_source'), request['evaluation_at'])
    from bond_engine import V75_PATH
    import sys
    from pathlib import Path
    path = Path(repo_root).resolve()/V75_PATH
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent != path/'v75_runtime':
        raise PermissionError('ALL_ASSET_V75_SOURCE_MISMATCH')
    from v75_runtime.predicates import pred009
    from v75_technical_inputs import produce as produce_technical
    bonds = []; cash_assets = []
    for asset in coverage['excluded']:
        if asset['route'] == 'CASH':
            cash_assets.append(deepcopy(asset));continue
        symbol = asset['symbol']
        row = {'symbol':symbol,'route':'V75','coverage_basis':asset['coverage_basis'],
            'holdings':deepcopy(asset['holdings']),'target_lines':deepcopy(asset['targets']),
            'market':None,'technical_inputs':None,'original_pred009':None,'call_trace':[],
            'missing_inputs':[],'full_financial_complete':False,'trade_action':'NO_TRADE'}
        try:
            market = read_market(config.get('market_sources',{}).get(symbol),symbol=symbol,
                evaluation_at=request['evaluation_at'],repo_root=repo_root,profile=None,
                is_etf=True,observation_route='V75')
        except ValueError as error:
            if not str(error).startswith('MEMBER_MARKET_'):raise
            market = None
            row['missing_inputs'].append({'field':'market.completed_history','reason':str(error),
                'responsibility':'MARKET_SOURCE_ADAPTER'})
        if market:
            row['market'] = {k:deepcopy(v) for k,v in market.items() if k!='completed_rows'}
            row['market']['rows'] = len(market['completed_rows'])
            row['call_trace'] += market['call_trace']
            if 'PROXY' in market.get('calendar_scope',''):
                row['missing_inputs'].append({'field':'calendar.authoritative_venue_schedule',
                    'reason':market['calendar_scope'],'responsibility':'MARKET_SOURCE_ADAPTER',
                    'affects':['formal_deployment_qualification']})
            if parameters:
                technical = produce_technical(market['completed_rows'], parameters)
                result = pred009(technical['metrics'], datetime.fromisoformat(
                    market['completed_session_close_at'].replace('Z','+00:00')),[market['source_reference']])
                row['technical_inputs'] = technical
                row['original_pred009'] = result.model_dump(mode='json')
                row['call_trace'] += ['W8.v75_technical_inputs.produce','V75.predicates.pred009']
            else:
                row['missing_inputs'].append({'field':'formal_v75_parameter_source',
                    'reason':'ORIGINAL_PARAMETER_PROVENANCE_UNBOUND','responsibility':'CODEX_SOURCE_ADAPTER'})
            if market['observed_date'] != market['latest_expected_completed_session']:
                row['missing_inputs'].append({'field':'market.latest_completed_session',
                    'reason':'STALE_COMPLETED_SESSION','responsibility':'MARKET_PROVIDER'})
        elif not row['missing_inputs']:
            row['missing_inputs'].append({'field':'market.completed_history',
                'reason':'EXACT_LISTING_HISTORY_NOT_BOUND','responsibility':'CODEX_SOURCE_ADAPTER'})
        row['missing_inputs'].append({'field':'original_v75_financial_handoff',
            'reason':'ORIGINAL_WORK3_BUDGET_ROLES_REMAINING_PREDICATES_AND_POLICY_REQUIRED',
            'responsibility':'EXISTING_V75_SOURCE_CHAIN','affects':['canonical amount','shared funding','Work9']})
        if symbol == 'SGOV':
            row['sgov_roles'] = {key:deepcopy(snapshot['tables'].get(key,[])) for key in
                ('sgov_role_proposal','sgov_role_confirmation')}
            row['physical_quantity_is_role_amount'] = False
        row['result_digest'] = digest(row);bonds.append(row)
    securities = coverage['assets']+coverage['excluded']
    security_rows = [a for a in securities if a['route']!='CASH']
    expected = {a['symbol'] for a in security_rows}
    equity = {a['symbol'] for a in coverage['assets']}
    observed = equity | {a['symbol'] for a in bonds}
    broker_unmapped=[]
    for view in broker_views:
        for position in view['positions']:
            if position['symbol'] not in expected:
                broker_unmapped.append({'symbol':position['symbol'],'route':'IDENTITY_MAPPING_REQUIRED',
                    'owner':deepcopy(view['owner']),'source_position':deepcopy(position),
                    'captured_at':view['captured_at'],'missing_inputs':['official_instrument_listing_and_engine_route'],
                    'trade_action':'NO_TRADE'})
                expected.add(position['symbol']);observed.add(position['symbol'])
    cash = []
    for account in review['accounts']:
        cash.append({'account_key':account['account_key'],'owner_candidate':account['owner_candidate'],
            'binding_qualification':account['binding_qualification'],
            'missing_binding_fields':account['missing_binding_fields'],
            'cash_observations':deepcopy(account['cash_observations']),
            'available_cash':None,'settlement_inferred':False,
            'missing_inputs':['verified_settlement_and_incremental_funding_authorization'],
            'cash_assets_assigned_by_inference':False})
    ledger = ledger_resource or {}
    result = {'schema_version':'Family.W8.AllAssetCoverage.v1',
        'client_id':request['client_id'],'source_db_sha256':snapshot['source_sha256'],
        'target_version':request['confirmed_target']['target_version'],
        'evaluation_at':request['evaluation_at'],
        'all_member_accounts_in_scope':bool(review['accounts']),
        'expected':sorted(expected),'observed':sorted(observed),'missing':sorted(expected-observed),
        'excluded':[],'account_keys':sorted(a['account_key'] for a in review['accounts']),
        'denominators':{'securities':len(expected),'equity':len(equity),'bonds':len(bonds),
            'cash_accounts':len(cash),'cash_target_lines':sum(len(a['targets']) for a in cash_assets),
            'orders_and_commitments':'COMPLETENESS_UNKNOWN__NOT_ASSUMED_EMPTY'},
        'equity_symbols':sorted(equity),'bonds':bonds,'cash_accounts':cash,
        'unmapped_cash_assets':cash_assets,
        'current_broker_views':broker_views,'broker_assets_needing_identity_mapping':broker_unmapped,
        'holding_and_target_rows':[{'symbol':a['symbol'],'route':a['route'],
            'coverage_basis':a['coverage_basis'],'account_keys':sorted({str(h.get('account_key')) for h in a['holdings']}),
            'source_facts':deepcopy(a['holdings']),'target_lines':deepcopy(a['targets']),
            'current_broker_observations':[{'owner':deepcopy(v['owner']),'captured_at':v['captured_at'],
                'position':deepcopy(p)} for v in broker_views for p in v['positions'] if p['symbol']==a['symbol']]}
            for a in security_rows],
        'planning_ledger':{k:deepcopy(ledger[k]) for k in ('status','cycle_count') if k in ledger},
        'account_reconciliation':review,'coverage_complete':expected==observed,
        'financial_completeness_asserted':False,'database_written':False,'trade_action':'NO_TRADE'}
    result['coverage_digest'] = digest(result)
    return result
