"""Dated quantity-times-price observations, independent of deployment money."""
from datetime import datetime
from decimal import Decimal,localcontext
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import re

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


def produce(request,coverage,equity_rows,inputs):
    snapshot=request['client_snapshot']['payload'];client=request['client_id']
    if (snapshot['client_id']!=client or snapshot['payload_digest']!=digest(snapshot['tables'])
        or coverage.get('client_id')!=client or coverage.get('source_db_sha256')!=snapshot['source_sha256']
        or coverage.get('evaluation_at')!=request['evaluation_at']
        or coverage.get('coverage_digest')!=digest({k:v for k,v in coverage.items() if k!='coverage_digest'})):
        raise PermissionError('POSITION_VALUATION_MEMBER_SNAPSHOT_COVERAGE_BINDING')
    fx=read_fx(inputs.get('fx_source'),request['evaluation_at']);markets={r['symbol']:r.get('market') for r in equity_rows}
    markets.update({r['symbol']:r.get('market') for r in coverage['bonds']})
    rows=[];totals={}
    with localcontext() as context:
        context.prec=50
        for asset in coverage['holding_and_target_rows']:
            facts=asset['source_facts'];market=markets.get(asset['symbol'])
            keys=[(f.get('account_key'),f.get('instrument_key')) for f in facts]
            for fact,key in zip(facts,keys):
                row=dict(symbol=asset['symbol'],account_key=fact.get('account_key'),
                    quantity=fact.get('quantity'),quantity_source=deepcopy_fact(fact),
                    observed_market_date=(market or {}).get('observed_date'),
                    amount=None,currency=None,reporting_amount_TWD=None,issue=None)
                currency=fact.get('currency') or (fact.get('instrument') or {}).get('quote_currency')
                if currency is None:
                    from official_holdings_source import holding_quote_currency
                    proof=holding_quote_currency(fact);currency=proof['currency'] if proof else None
                if keys.count(key)>1 or len(facts)>1 and None in key:
                    row['issue']='UNRESOLVED_ACCOUNT_OR_DUPLICATE_HOLDING_REPRESENTATION'
                elif fact.get('quantity') is None:row['issue']='ORIGINAL_QUANTITY_NOT_PROVIDED'
                elif not market:row['issue']='DATED_MARKET_OBSERVATION_NOT_PROVIDED'
                elif not currency or currency!=market['market_identity']['currency']:
                    row['issue']='ORIGINAL_PRICE_CURRENCY_NOT_BOUND'
                else:
                    value=_number(fact['quantity'])*_number(market['observed_close'])
                    row.update(amount=str(value),currency=currency,observed_close=str(market['observed_close']),
                        market_source_sha256=market['source_sha256'],price_basis=market['history_quality']['price_basis'])
                    totals[currency]=totals.get(currency,Decimal(0))+value
                    if currency=='TWD':row['reporting_amount_TWD']=str(value)
                    elif currency=='USD' and fx:row['reporting_amount_TWD']=str(value*_number(fx['quote_per_base']))
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
    out['digest']=digest(out);return out


def deepcopy_fact(value):
    from copy import deepcopy
    return deepcopy(value)
