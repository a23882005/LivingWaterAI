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
    from current_nav_source import read as read_nav
    nav=read_nav(source.get('nav_qualification_source'),request,out)
    if nav is not None:out['nav_source_qualification']=nav
    out['digest']=digest(out);return out


def gap_price(contract, market, instrument, symbol, request):
    """Qualify one latest completed quote for same-run exposure math only."""
    if not contract or not market:
        return None
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
            elif row.get('market_source_sha256')!=((contract.get('nav_source_qualification') or {}).get('official_quotes',{}).get(symbol) or {}).get('source_sha256',contract['original_quote_hashes'].get(symbol)):
                problem='CURRENT_POSITION_QUOTE_NOT_FROM_PINNED_BATCH';value=None
            elif (row.get('observed_market_date')!=contract['expected_current_quotes'][symbol].get('session_date')
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
