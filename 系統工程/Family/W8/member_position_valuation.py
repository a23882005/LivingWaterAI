"""Dated quantity-times-price observations, independent of deployment money."""
from datetime import datetime
from decimal import Decimal,localcontext
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import re
import json

from family_input import digest
from member_market_source import time


def _number(value):
    if value is None or isinstance(value,bool):raise ValueError('POSITION_VALUATION_EXACT_NUMBER')
    number=Decimal(str(value))
    if not number.is_finite() or number<0:raise ValueError('POSITION_VALUATION_NONNEGATIVE_NUMBER')
    return number


class _BankTable(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag=='td':self.cell=[dict(attrs).get('data-table'),[]]
    def handle_data(self,data):
        if self.cell is not None:self.cell[1].append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            if self.row is not None:self.row.append((self.cell[0],''.join(self.cell[1]).strip()))
            self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None


def read_fx(source,evaluation_at):
    if source is None:return None
    url=urlparse(source['source_reference']);raw=Path(source['local_path']).read_bytes()
    if (url.scheme!='https' or url.hostname!='rate.bot.com.tw' or url.path!='/xrt'
        or sha256(raw).hexdigest()!=source['sha256'] or time(source['retrieved_at'])>time(evaluation_at)):
        raise PermissionError('POSITION_FX_SOURCE_IDENTITY_HASH_OR_TIME')
    text=raw.decode('utf-8-sig');matches=re.findall(r'牌價最新掛牌時間：\s*<span class="time">([^<]+)</span>',text)
    if len(matches)!=1:raise ValueError('POSITION_FX_ORIGINAL_QUOTE_TIME_REQUIRED')
    at=datetime.strptime(matches[0].strip(),'%Y/%m/%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Taipei'))
    if at>min(time(source['retrieved_at']),time(evaluation_at)):raise PermissionError('POSITION_FX_QUOTE_FUTURE')
    table=_BankTable();table.feed(text)
    rows=[r for r in table.rows if any('美金 (USD)' in value for _,value in r)]
    if len(rows)!=1:raise ValueError('POSITION_FX_USD_ROW_REQUIRED')
    quotes=[value for key,value in rows[0] if key=='本行即期買入']
    values={_number(value) for value in quotes}
    # The bank repeats the same labeled quote in screen and print cells.
    # They must agree; neither repetition is another rate or another balance.
    if len(values)!=1 or min(values)<=0:raise ValueError('POSITION_FX_EXPLICIT_SPOT_BUY_REQUIRED')
    return dict(base_currency='USD',quote_currency='TWD',quote_per_base=str(_number(quotes[0])),
        source_url=source['source_reference'],source_sha256=source['sha256'],
        as_of=at.date().isoformat(),as_of_time=at.isoformat(),retrieved_at=source['retrieved_at'],
        basis='PUBLISHED_BANK_USD_SPOT_BUY_REFERENCE__NOT_EXECUTABLE_CASH_OR_FX_ORDER')


def _reported_source_category_keys(facts):
    """Distinct rows in one accepted book can be valued without real account IDs."""
    if not facts or any(f.get('quantity') is None or f.get('source_kind')!='SEALED_W6' or not f.get('source_run_id')
        or not f.get('broker_label') or (f.get('source_row') or {}).get('field_key')!='accepted_W6_broker_holdings_json'
        for f in facts):return None
    if len({f['source_run_id'] for f in facts})!=1:return None
    texts={f['source_row'].get('value_text') for f in facts}
    if len(texts)!=1 or None in texts:return None
    original=json.loads(next(iter(texts)))
    keys=[]
    for fact in facts:
        matches=[r for r in original if r.get('symbol')==fact['symbol'] and r.get('broker_label')==fact['broker_label']]
        if len(matches)!=1 or _number(matches[0].get('quantity'))!=_number(fact.get('quantity')):return None
        keys.append((fact['source_run_id'],fact['broker_label'],fact['symbol']))
    return keys if len(set(keys))==len(keys) else None


def produce(request,coverage,equity_rows,inputs,*,current_market_contract=None):
    snapshot=request['client_snapshot']['payload'];client=request['client_id']
    if (snapshot['client_id']!=client or snapshot['payload_digest']!=digest(snapshot['tables'])
        or coverage.get('client_id')!=client or coverage.get('source_db_sha256')!=snapshot['source_sha256']
        or coverage.get('evaluation_at')!=request['evaluation_at']
        or coverage.get('coverage_digest')!=digest({k:v for k,v in coverage.items() if k!='coverage_digest'})):
        raise PermissionError('POSITION_VALUATION_MEMBER_SNAPSHOT_COVERAGE_BINDING')
    fx=read_fx(inputs.get('fx_source'),request['evaluation_at']);markets={r['symbol']:r.get('market') for r in equity_rows}
    markets.update({r['symbol']:r.get('market') for r in coverage['bonds']})
    markets={k:(v.get('position_valuation_observation') or v.get('independent_broker_observation',v) if v else v) for k,v in markets.items()}
    discrepancies = {r['symbol']: r['holding']['quantity_discrepancy'] for r in equity_rows
                     if (r.get('holding') or {}).get('quantity_discrepancy')}
    account_values = {}
    for r in equity_rows:
        holding = r.get('holding') or {}
        position = holding.get('current_broker_position')
        if not position:
            continue
        result = deepcopy_fact(position)
        market = markets.get(r['symbol']) or {}
        if (market.get('observed_date') and market['observed_date'] == market.get('latest_expected_completed_session')
                and market['market_identity']['currency'] == position['currency']):
            result.update(valuation_price=str(market['observed_close']),
                          valuation_source_sha256=market['source_sha256'], observed_date=market['observed_date'],
                          account_position_amount=str(_number(position['quantity']) * _number(market['observed_close'])))
        account_values[r['symbol']] = result
        if holding.get('household_quantity_status') == 'OTHER_ACCOUNT_SCOPE_UNCONFIRMED':
            discrepancies[r['symbol']] = {'reason': 'OTHER_ACCOUNT_SCOPE_UNCONFIRMED',
                'prior_reported_quantity':holding.get('prior_reported_quantity'), 'current_broker_position':result}
    from current_market_contract import comparable_declared_position, current_account_observation
    bond_quotes = (current_market_contract or {}).get('pm_bond_closes', {})
    for asset in coverage['holding_and_target_rows']:
        symbol = asset['symbol']
        quote = bond_quotes.get(symbol)
        if not quote or asset['route'] != 'V75_SEPARATE':
            continue
        markets[symbol] = dict(market_identity={'currency':quote['currency']}, observed_date=quote['session_date'],
            observed_close=quote['price'], source_sha256=quote['source_sha256'],
            history_quality={'price_basis':quote['purpose']}, pm_bond_close=quote)
        # Preserve the account-specific result even if the old workbook disagrees.
        # A bond holding or its reserved role must never be counted again as available cash.
        positions = asset.get('current_broker_observations') or []
        if len(positions) == 1:
            observation = positions[0]
            position = observation['position']
            observed_at = observation.get('positions_retrieved_at') or observation['captured_at']
            if (position['symbol'] == symbol and position['currency'] == quote['currency']
                    and observation['owner']['client_id'] == client):
                result = dict(symbol=symbol, contract_id=position['contract_id'], currency=quote['currency'],
                    owner=deepcopy_fact(observation['owner']), quantity=position['quantity'], scope='AUTHORIZED_BROKER_ACCOUNT_ONLY',
                    retrieved_at=observation['captured_at'], valuation_price=quote['price'], observed_date=quote['session_date'],
                    valuation_source_sha256=quote['source_sha256'],
                    account_position_amount=str(_number(position['quantity'])*_number(quote['price'])))
                current = current_account_observation(observed_at, request['evaluation_at'])
                if current:
                    account_values[symbol] = result
                old = asset['source_facts']
                if len(old)==1 and old[0].get('quantity') is not None and _number(old[0]['quantity'])!=_number(position['quantity']):
                    if current:
                        discrepancies[symbol] = dict(reason='OTHER_ACCOUNT_SCOPE_UNCONFIRMED',
                            prior_reported_quantity=old[0]['quantity'], current_broker_position=result)
                    else:
                        discrepancies[symbol] = dict(reason='CURRENT_ACCOUNT_POSITION_REFRESH_REQUIRED',
                            prior_reported_quantity=old[0]['quantity'],
                            dated_broker_position={**result, 'positions_retrieved_at':observed_at})
    rule=(current_market_contract or {}).get('declared_position_scope')
    replaced={}
    if rule:
        for asset in coverage['holding_and_target_rows']:
            symbol=asset['symbol']
            broker=account_values.get(symbol)
            if comparable_declared_position(rule,symbol,asset['source_facts'],broker,request):
                replaced[symbol]=broker
                discrepancies.pop(symbol,None)
    rows=[];totals={}
    if current_market_contract is not None and (any(current_market_contract.get(k)!=request[k] for k in ('client_id','run_id','evaluation_at'))
        or current_market_contract.get('source_db_sha256')!=snapshot['source_sha256']):
        raise PermissionError('CURRENT_POSITION_VALUATION_CONTRACT_SCOPE_MISMATCH')
    with localcontext() as context:
        context.prec=50
        for asset in coverage['holding_and_target_rows']:
            facts=asset['source_facts'];market=markets.get(asset['symbol'])
            reference_quote=(market or {}).get('current_reference_quote') if current_market_contract is not None else None
            if reference_quote is not None:
                market={**market,**{k:reference_quote[k] for k in ('observed_date','observed_close','source_sha256','source_path','source_reference')}}
            if not facts and asset.get('owner_confirmed_position_absence'):
                proof=asset['owner_confirmed_position_absence']
                rows.append({'symbol':asset['symbol'],'account_key':None,'quantity':'0',
                    'quantity_source':{'quantity':'0','source_kind':'OWNER_CURRENT_CONFIRMED_ABSENCE',
                        'observed_at':proof['available_at'],'received_at':proof['available_at'],**proof},
                    'amount':'0','currency':(market or {}).get('market_identity',{}).get('currency'),
                    'reporting_amount_TWD':'0','observed_market_date':(market or {}).get('observed_date'),
                    'issue':None,'zero_value_does_not_assert_market_qualification':True})
                continue
            keys=[(f.get('account_key'),f.get('instrument_key')) for f in facts]
            logical_keys=(_reported_source_category_keys(facts) if current_market_contract is not None
                and coverage.get('current_owner_business_facts') is not None else None)
            if logical_keys is not None:keys=logical_keys
            for fact,key in zip(facts,keys):
                row=dict(symbol=asset['symbol'],account_key=fact.get('account_key'),
                    quantity=fact.get('quantity'),quantity_source=deepcopy_fact(fact),
                    observed_market_date=(market or {}).get('observed_date'),
                    amount=None,currency=None,reporting_amount_TWD=None,issue=None)
                if (market or {}).get('pm_bond_close'):
                    row['pm_bond_close']=deepcopy_fact(market['pm_bond_close'])
                if market and market.get('latest_expected_completed_session') is not None:
                    row['latest_expected_completed_session'] = market['latest_expected_completed_session']
                if reference_quote is not None:
                    row['current_reference_quote']=deepcopy_fact(reference_quote)
                if logical_keys is not None:
                    row.update(logical_holding_source_key=list(key),logical_category_is_real_account=False,
                        original_account_binding_unchanged=True)
                currency=fact.get('currency') or (fact.get('instrument') or {}).get('quote_currency')
                if currency is None:
                    from official_holdings_source import holding_quote_currency
                    proof=holding_quote_currency(fact);currency=proof['currency'] if proof else None
                replacement=replaced.get(asset['symbol'])
                if replacement:
                    row.update(quantity=replacement['quantity'],prior_reported_quantity=fact['quantity'],
                            quantity_source={'source_kind':'AUTHORIZED_BROKER_CURRENT_DECLARED_ACCOUNT','original':deepcopy_fact(fact),
                                'position':deepcopy_fact(replacement),'source_scope':current_market_contract['source_descriptor']['declared_position_scope']['sha256']})
                if asset['symbol'] in discrepancies:
                    row.update(quantity=None, issue=discrepancies[asset['symbol']].get('reason','UNRECONCILED_MEMBER_BROKER_QUANTITY'),
                               quantity_discrepancy=discrepancies[asset['symbol']])
                elif keys.count(key)>1 or len(facts)>1 and None in key:
                    row['issue']='UNRESOLVED_ACCOUNT_OR_DUPLICATE_HOLDING_REPRESENTATION'
                elif fact.get('quantity') is None:row['issue']='ORIGINAL_QUANTITY_NOT_PROVIDED'
                elif not market:row['issue']='DATED_MARKET_OBSERVATION_NOT_PROVIDED'
                elif not currency or currency!=market['market_identity']['currency']:
                    row['issue']='ORIGINAL_PRICE_CURRENCY_NOT_BOUND'
                else:
                    value=_number(row['quantity'])*_number(market['observed_close'])
                    row.update(amount=str(value),currency=currency,observed_close=str(market['observed_close']),
                        market_source_sha256=market['source_sha256'],price_basis=market['history_quality']['price_basis'])
                    if currency=='TWD':row['reporting_amount_TWD']=str(value)
                    elif currency=='USD' and fx:row['reporting_amount_TWD']=str(value*_number(fx['quote_per_base']))
                    from current_nav_source import apply_official_quote
                    apply_official_quote(row,current_market_contract)
                    totals[currency]=totals.get(currency,Decimal(0))+Decimal(row['amount'])
                rows.append(row)
    # Read the latest explicit owner report by currency. Account/source keys in
    # cash_balance_snapshot are retained separately and never added together.
    tables=request['client_snapshot']['payload']['tables'];runs={r['run_id']:r for r in tables['portfolio_snapshot_run']
        if r.get('run_state')=='SEALED' and r.get('source_kind')!='USER_HYPOTHETICAL'
        and time(r['as_of_utc'])<=time(request['evaluation_at'])}
    cash={}
    for fact in tables['portfolio_snapshot_item']:
        run=runs.get(fact['run_id'])
        if (run is None or fact.get('domain_code')!='CASH' or fact['field_key']!='owner_reported_amount'
            or fact.get('value_state')!='KNOWN'):continue
        for field in ('recorded_at_utc','source_observed_at_utc'):
            if fact.get(field) and time(fact[field])>time(request['evaluation_at']):
                raise PermissionError('POSITION_CASH_OWNER_REPORT_FUTURE')
        currency=fact.get('currency_code');order=(time(run['as_of_utc']),run.get('version_no',0))
        if currency is None:continue
        item=dict(currency=currency,amount=str(_number(fact['value_text'])),source_row=deepcopy_fact(fact),
            source_run=deepcopy_fact(run),settlement_qualified=False)
        if currency not in cash or order>cash[currency][0]:cash[currency]=(order,item)
        elif order==cash[currency][0] and cash[currency][1]!=item:raise ValueError('POSITION_CASH_REPORT_AMBIGUOUS')
    out=dict(schema_version='Family.W8.DatedPositionValueObservations.v1',client_id=request['client_id'],
        run_id=request['run_id'],source_db_sha256=request['client_snapshot']['payload']['source_sha256'],
        evaluation_at=request['evaluation_at'],positions=rows,
        observed_security_subtotals_by_currency={k:str(v) for k,v in sorted(totals.items())},
        fx_observation=fx,latest_owner_cash_reports=[cash[k][1] for k in sorted(cash)],
        cash_account_sources=deepcopy_fact(coverage['cash_accounts']),cash_sources_assumed_independent=False,
        qualified_portfolio_NAV=None,deployable_cash=None,new_buy_amount=None,
        scope='DATED_PARTIAL_POSITION_OBSERVATIONS__NOT_COMPLETE_NAV_OR_DEPLOYMENT_INPUT',trade_action='NO_TRADE')
    if account_values:
        out['current_broker_account_positions'] = account_values
    out['digest']=digest(out);return out


def deepcopy_fact(value):
    from copy import deepcopy
    return deepcopy(value)
