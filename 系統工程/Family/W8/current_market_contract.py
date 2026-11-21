"""Pinned PM current-market facts and bounded downstream interface decisions.

Current reported values do not manufacture historical/PIT qualification,
canonical valuation prices, trade authority or a new portfolio confirmation.
"""
from copy import deepcopy
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from family_input import digest
from member_market_source import time


def read(source,request):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('CURRENT_MARKET_CONTRACT_BYTES_CHANGED')
    data=json.loads(raw);snapshot=request['client_snapshot']['payload'];member=source.get('member')
    original=(data.get('member_revaluations') or {}).get(member)
    if (data.get('schema')!='Family.PM.CurrentPriceSupplement.v1' or not isinstance(original,dict)
        or request.get('trade_authorization')!='NONE' or data.get('trade')!='NONE'
        or snapshot.get('client_id')!=request['client_id']
        or snapshot.get('payload_digest')!=digest(snapshot.get('tables'))
        or str(snapshot.get('identity',{}).get('family_alias','')).casefold()!=str(member).casefold()
        or original.get('source_db_sha256')!=snapshot['source_sha256']
        or source.get('target_version')!=request['confirmed_target']['target_version']
        or not source.get('source_reference') or not source.get('available_at')):
        raise PermissionError('CURRENT_MARKET_CONTRACT_MEMBER_DB_TARGET_OR_TRADE_MISMATCH')
    if time(source['available_at'])>time(request['evaluation_at']):return None
    observations=data['sources'];hashes={}
    for symbol,item in observations.items():
        content=item['raw_original_utf8'].encode()
        if (sha256(content).hexdigest()!=item['raw_sha256'] or len(content)!=item['bytes']
            or item['asset']!=symbol or item.get('validation_issues')
            or time(item['retrieved_at'])>time(request['evaluation_at'])):
            raise PermissionError('CURRENT_MARKET_ORIGINAL_BYTES_SCOPE_OR_TIME')
        hashes[symbol]=item['raw_sha256']
    bank=data['official_BOT_FX_original_reader'];html=data['official_BOT_FX_original_utf8'].encode()
    materialized=source.get('official_bank_source')
    if materialized is not None:
        html=Path(materialized['local_path']).read_bytes()
        if (sha256(html).hexdigest()!=materialized['sha256']
            or html.decode('utf-8-sig').replace('\r\n','\n')!=data['official_BOT_FX_original_utf8']):
            raise PermissionError('CURRENT_MARKET_BANK_EMBEDDED_TEXT_REPLAY_MISMATCH')
    if (sha256(html).hexdigest()!=bank['source']['sha256']
        or time(bank['source']['retrieved_at'])>time(request['evaluation_at'])):
        raise PermissionError('CURRENT_MARKET_BANK_ORIGINAL_BYTES_OR_TIME')
    decision=deepcopy((data.get('PM_integration_decisions') or {}).get(member) or {})
    out={'schema_version':'Family.W8.CurrentMarketContract.v1',
        **{k:request[k] for k in ('client_id','run_id','evaluation_at')},'member':member,
        'source_db_sha256':snapshot['source_sha256'],'target_version':source['target_version'],
        'source_descriptor':deepcopy(source),'source_reference':source['source_reference'],
        'available_at':source['available_at'],'original_quote_hashes':hashes,
        'expected_current_quotes':{k:deepcopy(v['selected_observation']) for k,v in observations.items()},
        'official_bank_original_result':deepcopy(bank['original_reader_result']),
        'decision':decision,'formal_NAV_or_buy_permission_created':False,'trade_authorization':'NONE'}
    current_bank = source.get('updated_bank_source')
    if current_bank:
        from member_position_valuation import read_fx
        updated = read_fx(current_bank, request['evaluation_at'])
        if time(updated['as_of_time']) < time(out['official_bank_original_result']['as_of_time']):
            raise PermissionError('CURRENT_MARKET_BANK_PRECEDES_PINNED_QUOTE')
        out['official_bank_original_result'] = updated
    close_source = source.get('pm_bond_close_source')
    if close_source is not None:
        out['pm_bond_closes'] = _pm_bond_closes(close_source, request, out)
    declared=declared_position_scope(source.get('declared_position_scope'),request)
    if declared:
        out['declared_position_scope']=declared
    closing_batch=source.get('portfolio_close_batch')
    if closing_batch:
        from member_market_source import read_json
        batch=read_json(closing_batch)
        if (batch['client_id']!=request['client_id'] or batch['source_db_sha256']!=snapshot['source_sha256']
                or batch.get('scope')!='PORTFOLIO_VALUATION_ONLY' or batch.get('target_version')!=out['target_version']
                or not closing_batch.get('source_reference') or time(batch['available_at'])>time(request['evaluation_at'])):
            raise PermissionError('CURRENT_POSITION_REGISTERED_CLOSE_BATCH_SCOPE')
        if time(batch['available_at']).astimezone(ZoneInfo('Asia/Taipei')).date()==time(request['evaluation_at']).astimezone(ZoneInfo('Asia/Taipei')).date():
            for symbol,registered in batch['closes'].items():
                if (symbol not in observations or registered['session_date']!=batch['session_date']
                        or registered['currency']!=observations[symbol]['currency']
                        or Decimal(registered['price'])<=0):
                    raise PermissionError('CURRENT_POSITION_REGISTERED_CLOSE_BATCH_ASSET')
                # Only the valuation projection reads these registrations. It checks the
                # original reader's hash, currency, latest completed date and exact price.
                out['original_quote_hashes'][symbol]=registered['source_sha256']
                out['expected_current_quotes'][symbol]=deepcopy(registered)
    from current_nav_source import read as read_nav
    nav=read_nav(source.get('nav_qualification_source'),request,out)
    if nav is not None:out['nav_source_qualification']=nav
    out['digest']=digest(out);return out


def _pm_bond_closes(source, request, contract):
    """Read dated, member-bound PM close attestations for position valuation only."""
    import re
    from datetime import datetime
    from urllib.parse import urlsplit
    from member_market_source import read_json
    facts = read_json(source)
    if (source.get('client_id') != request['client_id'] or source.get('source_db_sha256') != contract['source_db_sha256']
            or source.get('target_version') != contract['target_version'] or source.get('scope') != 'BOND_POSITION_VALUATION_ONLY'
            or source.get('session_date') != facts['date'] or not source.get('source_reference') or time(facts['retrieved_at']) > time(request['evaluation_at'])):
        raise PermissionError('BOND_CLOSE_MEMBER_DB_SCOPE_OR_TIME')
    session = datetime.strptime(facts['date'], '%Y-%m-%d')
    available = time(facts['retrieved_at'])
    if time(request['evaluation_at']).astimezone(ZoneInfo('Asia/Taipei')).date() != available.astimezone(ZoneInfo('Asia/Taipei')).date():
        return {}
    tpex = urlsplit(facts['tpex_url'])
    roc = f'{session.year-1911:03d}/{session.month:02d}/{session.day:02d}'
    if (facts['tpex_report_date'] != roc or (tpex.scheme,tpex.hostname) != ('https','www.tpex.org.tw')
            or not tpex.path.endswith('/stk_wn1430_result.php') or not facts['tpex_close_twd']):
        raise PermissionError('BOND_CLOSE_TPEX_REPORT_OR_SESSION')
    quotes = {}
    def register(symbol, value, currency, zone, close_hour, close_minute, sources):
        price = Decimal(str(value))
        close = session.replace(hour=close_hour, minute=close_minute, tzinfo=ZoneInfo(zone))
        if close > available or not price.is_finite() or price <= 0:
            raise PermissionError('BOND_CLOSE_PRICE_OR_AVAILABILITY')
        quotes[symbol] = dict(symbol=symbol, price=str(price), currency=currency, session_date=facts['date'],
            source_sha256=source['sha256'], source_reference=source['source_reference'],
            provider_references=sources, available_at=facts['retrieved_at'], purpose='PM_VERIFIED_CLOSE_FOR_POSITION_VALUE_ONLY')
    for symbol, value in facts['tpex_close_twd'].items():
        if not re.fullmatch(r'[0-9]{5}B',symbol):
            raise ValueError('BOND_CLOSE_TPEX_BOND_ETF_REQUIRED')
        register(symbol,value,'TWD','Asia/Taipei',14,30,[facts['tpex_url']])
    refs = [urlsplit(url) for url in facts['sgov_sources']]
    if (any(r.scheme != 'https' for r in refs) or
            not any(r.hostname=='stockanalysis.com' and r.path=='/etf/sgov/history/' for r in refs) or
            not any(r.hostname=='markets.ft.markitdigital.com' and 'SGOV' in r.query for r in refs)):
        raise PermissionError('BOND_CLOSE_SGOV_LISTING_SOURCES')
    register('SGOV',facts['sgov_close_usd'],'USD','America/New_York',16,0,facts['sgov_sources'])
    return quotes


def declared_position_scope(descriptor,request):
    if descriptor is None:
        return None
    from member_market_source import read_json
    from owner_current_business import read as read_owner
    rule=read_json(descriptor)
    project=descriptor['project']
    owner=read_owner(descriptor['owner'],request)
    auth=read_json(descriptor['authorization'])
    raw=Path(project['source_path']).read_bytes()
    if (rule['scope']!='CURRENT_DECLARED_BROKER_HOLDINGS_ONLY' or rule['trade']!='NONE'
            or rule['client_id']!=request['client_id'] or rule['source_db_sha256']!=request['client_snapshot']['payload']['source_sha256']
            or rule['target_version']!=request['confirmed_target']['target_version']
            or project['client_id']!=rule['client_id'] or project['target_version']!=rule['target_version']
            or owner is None or not owner['unreported_positions_absent'] or owner['member']!=rule['member']
            or owner['source_sha256']!=rule['owner_current_sha256'] or not project.get('source_reference')
            or project['sha256']!=rule['project_document_sha256'] or sha256(raw).hexdigest()!=project['sha256']
            or descriptor['authorization']['sha256']!=rule['broker_owner_authorization_sha256']
            or auth['scope']!='READ_ONLY_RECONCILIATION_AND_ADVICE' or auth['trade_authorization']!='NONE'
            or auth['owner']['client_id']!=rule['client_id'] or auth['owner']['account']!=rule['account']):
        raise PermissionError('CURRENT_DECLARED_ACCOUNT_SCOPE_AUTHORITIES')
    from w1_portfolio_observations import normalize
    matching_accounts = [entry['account_key'] for entry in normalize(request)['accounts']
        if entry['owner_candidate']['broker']==auth['owner']['broker']]
    if matching_accounts != [rule['account']]:
        return None
    if time(rule['available_at'])>time(request['evaluation_at']):
        return None
    lines=raw.decode('utf-8-sig').splitlines()
    cited=rule['source_project_lines']
    if any(not (0<int(n)<=len(lines)) or lines[int(n)-1]!=line for n,line in cited.items()):
        raise PermissionError('CURRENT_DECLARED_ACCOUNT_SCOPE_SOURCE_LINES')
    named=cited[str(rule['named_broker_list_line'])]
    import re
    if (any(not re.search(r'(?<![A-Z0-9])'+re.escape(k)+r'(?![A-Z0-9])',named) for k in rule['current_contracts'])
            or auth['owner']['broker'] not in named):
        raise PermissionError('CURRENT_DECLARED_ACCOUNT_LISTING_NOT_IN_PROJECT')
    return rule


def comparable_declared_position(rule,symbol,facts,position,request):
    if not rule or len(facts)!=1 or not position:
        return False
    original=facts[0]
    account=position['owner']['account']
    return (position['owner']['client_id']==request['client_id'] and rule['account']==account
            and position['contract_id']==rule['current_contracts'].get(symbol)
            and original.get('source_kind')=='SEALED_W6' and original.get('symbol')==symbol
            and original.get('broker_label')==rule['owner_label'] and original.get('account_key') in (None,account)
            and original.get('received_at') and time(original['received_at'])<=time(position['retrieved_at'])
            and time(position['retrieved_at']).astimezone(ZoneInfo('Asia/Taipei')).date()==time(request['evaluation_at']).astimezone(ZoneInfo('Asia/Taipei')).date()
            and original.get('quantity') is not None)


def gap_price(contract, market, instrument, symbol, request):
    """Qualify one latest completed quote for same-run exposure math only."""
    if not contract or not market:
        return None
    market = market.get('independent_broker_observation', market)
    registration = (contract['source_descriptor'].get('gap_price_registrations') or {}).get(symbol)
    if not registration:
        return None
    identity = market['market_identity']
    fx = contract['official_bank_original_result']
    day = time(request['evaluation_at']).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()
    if day != registration['evaluation_day'] or fx['as_of'] != day:
        return None
    if (instrument.get('client_id') != request['client_id'] or instrument.get('ticker') != symbol
            or instrument.get('identity_state') != 'KNOWN' or instrument.get('instrument_type') != 'ETF'
            or instrument.get('instrument_key') != registration['instrument_key']
            or identity['provider_symbol'] != symbol or identity['provider_type'] != 'ETF'
            or instrument.get('quote_currency') != identity['currency']
            or identity['currency'] != registration['currency'] or identity['exchange'] != registration['exchange']
            or market['source_sha256'] != registration['source_sha256']):
        raise PermissionError('CURRENT_GAP_PRICE_INSTRUMENT_OR_ORIGINAL_MISMATCH')
    if (market.get('observed_date') != market.get('latest_expected_completed_session')
            or not market.get('completed_session_close_at') or not market.get('provider_verified_at')
            or not time(market['completed_session_close_at']) <= time(market['provider_verified_at']) <= time(request['evaluation_at'])
            or Decimal(str(market['observed_close'])) <= 0):
        return None
    return {'client_id': request['client_id'], 'run_id': request['run_id'], 'evaluation_at': request['evaluation_at'],
            'symbol': symbol, 'source_sha256': market['source_sha256'], 'observed_close': market['observed_close'],
            'session': market['observed_date'], 'currency': identity['currency'], 'exchange': identity['exchange'],
            'scope': 'CURRENT_POSITION_EXPOSURE_ONLY', 'fx_observation': deepcopy(fx)}


def new_buy_scope(contract,symbol):
    if contract is None:return None
    decision=contract['decision']
    if (decision.get('status')!='NO_ADDITIONAL_BUY_TARGET_AUTHORIZED__PRESERVE_EXISTING_HOLDINGS'
        or symbol not in decision.get('symbols',[])):return None
    return {'status':'NOT_APPLICABLE_NO_ADDITIONAL_BUY_AUTHORIZATION','additional_buy_authorized':False,
        'client_id':contract['client_id'],'run_id':contract['run_id'],'symbol':symbol,
        'source':deepcopy(contract['source_descriptor']),'existing_holding_and_risk_analysis_preserved':True,
        'zero_target_invented':False,'sell_instruction_created':False,'other_assets_restricted':False}


def portfolio_reference(request,coverage,values,accepted,current_owner,contract):
    if contract is None:return None
    if accepted is None or current_owner is None:raise PermissionError('CURRENT_PORTFOLIO_ACCEPTED_OWNER_FACTS_REQUIRED')
    for source in (accepted,current_owner,contract,values):
        if (any(source.get(k)!=request[k] for k in ('client_id','run_id','evaluation_at'))
            or source.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']):
            raise PermissionError('CURRENT_PORTFOLIO_MEMBER_RUN_OR_DB_MISMATCH')
    fx=values.get('fx_observation')
    if fx!=contract['official_bank_original_result']:
        raise PermissionError('CURRENT_PORTFOLIO_OFFICIAL_BANK_READER_REPLAY_MISMATCH')
    assets={r['symbol']:r for r in coverage['holding_and_target_rows']};positions=[];issues=[]
    cash=deepcopy(accepted['accepted_net_available_by_currency']);totals={};stock=Decimal(0)
    def to_twd(amount,currency):
        if currency=='TWD':return amount
        if currency=='USD':return amount*Decimal(fx['quote_per_base'])
        return None
    with localcontext() as numeric:
        numeric.prec=50
        for row in values['positions']:
            symbol=row['symbol'];item=deepcopy(row);problem=row.get('issue')
            if row.get('quantity')=='0':value=Decimal(0)
            elif row.get('amount') is None:problem=problem or 'CURRENT_POSITION_AMOUNT_UNAVAILABLE';value=None
            elif row.get('pm_bond_close'):
                quote=(contract.get('pm_bond_closes') or {}).get(symbol)
                if (quote!=row['pm_bond_close'] or assets[symbol]['route']!='V75_SEPARATE'
                        or row.get('market_source_sha256')!=quote['source_sha256']
                        or row.get('currency')!=quote['currency'] or row.get('observed_market_date')!=quote['session_date']
                        or Decimal(str(row['observed_close']))!=Decimal(quote['price'])):
                    raise PermissionError('CURRENT_POSITION_PM_BOND_CLOSE_BINDING')
                value=Decimal(row['amount'])
            elif row.get('market_source_sha256')!=((contract.get('nav_source_qualification') or {}).get('official_quotes',{}).get(symbol) or {}).get('source_sha256',contract['original_quote_hashes'].get(symbol)):
                problem='CURRENT_POSITION_QUOTE_NOT_FROM_PINNED_BATCH';value=None
            elif (contract['expected_current_quotes'][symbol].get('currency',row.get('currency'))!=row.get('currency')
                or row.get('observed_market_date')!=contract['expected_current_quotes'][symbol].get('session_date')
                or Decimal(str(row.get('observed_close')))!=Decimal(((contract.get('nav_source_qualification') or {}).get('official_quotes',{}).get(symbol) or contract['expected_current_quotes'][symbol])['price'])):
                problem='CURRENT_POSITION_PRICE_OR_SESSION_REPLAY_MISMATCH';value=None
            else:value=Decimal(row['amount'])
            reporting=to_twd(value,row.get('currency')) if value is not None else None
            if value==0 and reporting is None:reporting=Decimal(0)
            if reporting is None:problem=problem or 'CURRENT_POSITION_REPORTING_FX_UNAVAILABLE'
            if problem:issues.append({'symbol':symbol,'reason':problem})
            elif value is not None:
                currency=row.get('currency')
                if currency:totals[currency]=totals.get(currency,Decimal(0))+value
                if assets[symbol]['route']=='V82':stock+=reporting
            item.update(reference_amount_TWD=str(reporting) if reporting is not None else None,
                route=assets[symbol]['route'],new_buy_scope=new_buy_scope(contract,symbol))
            positions.append(item)
        cash_twd=Decimal(0)
        for currency,amount in cash.items():
            amount_twd=to_twd(Decimal(amount),currency)
            if amount_twd is None:issues.append({'currency':currency,'reason':'CURRENT_CASH_REPORTING_FX_UNAVAILABLE'})
            else:cash_twd+=amount_twd
        nav=None if issues else sum((Decimal(p['reference_amount_TWD']) for p in positions),Decimal(0))+cash_twd
        for p in positions:p['current_reference_weight']=str(Decimal(p['reference_amount_TWD'])/nav) if nav and p['reference_amount_TWD'] is not None else None
        gaps=[]
        for symbol,asset in assets.items():
            selected=[p for p in positions if p['symbol']==symbol];scope=new_buy_scope(contract,symbol)
            total=sum((Decimal(p['reference_amount_TWD']) for p in selected if p['reference_amount_TWD'] is not None),Decimal(0))
            targets=asset['target_lines'];target_twd=Decimal(0);ready=bool(targets)
            for line in targets:
                money=line['target_amount']
                if money.get('value_state')!='KNOWN':ready=False;continue
                converted=to_twd(Decimal(money['amount']),money.get('currency'))
                if converted is None:ready=False
                else:target_twd+=converted
            if any(p['reference_amount_TWD'] is None or p.get('issue') for p in selected):ready=False
            status=scope['status'] if scope else 'REFERENCE_COMPUTED' if ready else 'REFERENCE_SOURCE_INCOMPLETE'
            gaps.append({'symbol':symbol,'status':status,'current_value_TWD':str(total),
                'approved_target_amount_TWD':str(target_twd) if ready and scope is None else None,
                'reference_gap_TWD':str(target_twd-total) if ready and scope is None else None,
                'original_target_lines':deepcopy(targets),'canonical_stage_or_order_amount_created':False})
    out={'schema_version':'Family.W8.CurrentPortfolioReference.v1',
        **{k:request[k] for k in ('client_id','run_id','evaluation_at')},
        'source_db_sha256':contract['source_db_sha256'],'contract':deepcopy(contract),
        'positions':positions,'security_subtotals_by_currency':{k:str(v) for k,v in totals.items()},
        'accepted_net_cash_by_currency':cash,'cash_TWD':str(cash_twd),
        'positions_plus_accepted_cash_TWD':str(nav) if nav is not None else None,
        'current_stock_exposure_TWD':str(stock) if not issues else None,
        'stock_weight':str(stock/nav) if nav else None,'allocation_reference_gaps':gaps,
        'reporting_FX':deepcopy(fx),'issues':issues,'cash_counted_once':True,
        'formal_source_qualification_dependencies':[{'symbol':p['symbol'],
            'reason':'ORIGINAL_CURRENT_SESSION_FINAL_CLOSE_NOT_VERIFIED',
            'source_evidence':deepcopy(p['current_reference_quote']['final_close_qualification_issues'])}
            for p in positions if p.get('current_reference_quote',{}).get('original_final_close_verified') is False
            and not p.get('qualified_current_NAV_quote')],
        'SGOV_physical_value_counted_once':True,'SGOV_roles_added_to_cash':False,
        'approved_pool_and_target_amounts_rebased':False,'additional_cash_target_reserve_deducted':'0',
        'formal_NAV_or_buy_permission_created':False,'trade_action':'NO_TRADE'}
    from current_nav_source import qualify
    qualify(out,accepted,current_owner)
    out['digest']=digest(out);return out


def broker_cash_check(source, accepted, request):
    """Compare settled cash to the existing owner's accepted same-currency amount."""
    if not source:
        return None
    if (accepted is None or source['client_id'] != request['client_id']
            or source['source_db_sha256'] != request['client_snapshot']['payload']['source_sha256']
            or accepted['member'] != source['member'] or request['trade_authorization'] != 'NONE'):
        raise PermissionError('CURRENT_CASH_CORROBORATION_OWNER')
    from member_market_source import read_json
    authorization = read_json(source['owner_authorization'])
    if (authorization['client_id'] != request['client_id'] or authorization['owner']['broker'] != 'IBKR'
            or authorization['scope'] != 'READ_ONLY_RECONCILIATION_AND_ADVICE'
            or authorization['trade_authorization'] != 'NONE'):
        raise PermissionError('CURRENT_CASH_CORROBORATION_BROKER')
    originals = {}
    for key in ('balances', 'orders'):
        evidence = read_json(source[key])
        if (evidence['isError'] or evidence['args'] or evidence['method'] != 'get_account_' + key
                or not time(authorization['recorded_at']) <= time(evidence['started_at']) <= time(evidence['retrieved_at']) <= time(request['evaluation_at'])):
            raise PermissionError('CURRENT_CASH_CORROBORATION_RESPONSE')
        originals[key] = evidence['original']
    currency = authorization['owner']['currency']
    records = [v for v in originals['balances']['balances'] if v['currency'] == currency]
    matches = (len(records) == 1 and Decimal(str(records[0]['cash_balance']))
               == Decimal(str(records[0]['settled_cash'])) == Decimal(accepted['accepted_net_available_by_currency'][currency]))
    return {'source': deepcopy(source), 'currency': currency, 'matches_accepted_cash': matches,
            'working_orders_empty': originals['orders'].get('orders') == [],
            'previously_accepted_net_cash': accepted['accepted_net_available_by_currency'][currency],
            'margin_or_buying_power_added': False}


def compare_broker_quantity(source, holding, symbol, request):
    """Keep both original books when a sealed quantity disagrees with the broker."""
    if not source or symbol not in source.get('contract_ids', {}):
        return holding
    from member_market_source import read_json
    authorization = read_json(source['owner_authorization'])
    if (authorization['client_id'] != request['client_id'] or source['client_id'] != request['client_id']
            or source['source_db_sha256'] != request['client_snapshot']['payload']['source_sha256']
            or authorization['scope'] != 'READ_ONLY_RECONCILIATION_AND_ADVICE'
            or authorization['trade_authorization'] != 'NONE' or authorization['owner']['broker'] != 'IBKR'):
        raise PermissionError('CURRENT_BROKER_QUANTITY_OWNER')
    current = source.get('current_positions')
    if current:
        record = read_json(current)
        captured = time(record['retrieval_recorded_at'])
        evaluated = time(request['evaluation_at'])
        if (record['tool'] != 'interactive_brokers_ibkr_get_account_positions' or record['arguments'] != {}
                or current.get('owner_authorization_sha256') != source['owner_authorization']['sha256']
                or time(authorization['recorded_at']) > captured):
            raise PermissionError('CURRENT_BROKER_CONNECTED_OWNER_OR_ORIGINAL')
        if captured <= evaluated and captured.astimezone(ZoneInfo('Asia/Taipei')).date() == evaluated.astimezone(ZoneInfo('Asia/Taipei')).date():
            positions = record['response']['positions']
            matches = [row for row in positions if row.get('contract_id') == source['contract_ids'][symbol]]
            if len(matches) != 1:
                raise PermissionError('CURRENT_BROKER_CONTRACT_NOT_UNIQUE')
            pos = matches[0]
            qty = Decimal(str(pos['position']))
            if (pos['contract_description'].split()[0] != symbol or pos['currency'] != authorization['owner']['currency']
                    or pos['asset_class'] != 'STK' or not qty.is_finite() or qty < 0):
                raise PermissionError('CURRENT_BROKER_LISTING_MISMATCH')
            scoped = {'owner': deepcopy(authorization['owner']), 'symbol': symbol, 'contract_id': pos['contract_id'],
                      'quantity': str(qty), 'currency': pos['currency'], 'source_sha256': current['sha256'],
                      'retrieved_at': record['retrieval_recorded_at'], 'scope': 'AUTHORIZED_BROKER_ACCOUNT_ONLY'}
            updated = {**holding, 'current_broker_position': scoped}
            if holding.get('quantity') is None or Decimal(str(holding['quantity'])) != qty:
                updated.update(quantity=None, quantity_state='UNKNOWN', prior_reported_quantity=holding.get('quantity'),
                               household_quantity_status='OTHER_ACCOUNT_SCOPE_UNCONFIRMED')
                rule=declared_position_scope(source.get('declared_position_scope'),request)
                if comparable_declared_position(rule,symbol,holding.get('source_facts',[]),scoped,request):
                    updated.update(quantity=str(qty),quantity_state='KNOWN',observed_at=scoped['retrieved_at'],
                        household_quantity_status='CURRENT_DECLARED_ACCOUNT_CONFIRMED',
                        quantity_basis='NEWER_AUTHORIZED_BROKER_POSITION_FOR_DECLARED_ACCOUNT',
                        declared_scope_source_sha256=source['declared_position_scope']['sha256'])
            return updated
    evidence = read_json(source['historical_positions'])
    if (evidence['method'] != 'get_account_positions' or evidence['status'] != 'fulfilled'
            or evidence['value'].get('isError') or evidence['arguments'] != {}):
        raise PermissionError('CURRENT_BROKER_POSITION_ORIGINAL')
    if time(evidence['retrieved_at']) > time(request['evaluation_at']):
        return holding
    rows = [row for row in evidence['value']['structuredContent']['positions']
            if row['contract_id'] == source['contract_ids'][symbol]
            and row['contract_description'].split()[0] == symbol and row['currency'] == authorization['owner']['currency']]
    if len(rows) != 1 or holding.get('quantity') is None:
        return holding
    broker_qty = Decimal(str(rows[0]['position']))
    if broker_qty == Decimal(str(holding['quantity'])):
        return holding
    facts = holding.get('source_facts') or []
    proof = {'broker_source': deepcopy(source['historical_positions']), 'broker_account': authorization['owner']['account'],
             'broker_quantity': str(broker_qty), 'broker_retrieved_at': evidence['retrieved_at'],
             'registered_quantity': holding['quantity'], 'registered_observed_at': holding.get('observed_at'),
             'registered_source_rows': [{k: row.get(k) for k in ('source_kind','received_at','account_key','broker_label')} for row in facts],
             'same_account_verified': bool(facts) and all(row.get('account_key') == authorization['owner']['account'] for row in facts),
             'reason': 'UNRECONCILED_MEMBER_BROKER_QUANTITY'}
    return {**holding, 'quantity': None, 'quantity_state': 'UNKNOWN', 'quantity_discrepancy': proof}
