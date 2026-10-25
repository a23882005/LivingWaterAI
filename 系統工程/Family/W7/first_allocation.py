"""Family menu 01: record confirmed current holdings, cash and Mentor interview.

This operation is a snapshot / account opening, NOT a Loop 1 target confirmation
or a Loop 2 deployment. Only the trusted account gateway supplies identity,
resource, account_key and Coordinator. No orders, no target rebalancing.

The W7 Coordinator owns the same-ID Drive transaction, backup, lock, idempotency
and read-back. Register 'first_allocation_snapshot' on the trusted writer.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import sqlite3
import tempfile
from pathlib import Path


OPERATION = 'first_allocation_snapshot'
STATUS = 'FIRST_ALLOCATION_SAVED'
REQUIRED_TABLES = ('family_member_identity', 'portfolio_account',
                   'portfolio_instrument', 'portfolio_position',
                   'cash_balance_snapshot', 'portfolio_snapshot_run',
                   'portfolio_snapshot_item')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('MONEY_REQUIRED')
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError('MONEY_INVALID') from None
    if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
        raise ValueError('MONEY_INVALID')
    return number


def _text(value, field, maxlen=240):
    if not isinstance(value, str) or not value.strip() or len(value) > maxlen:
        raise ValueError('INVALID_' + field)
    return value.strip()


def normalize_request(data):
    """Only user-confirmed facts; market value is NOT a share quantity/cost."""
    if not isinstance(data, dict) or data.get('interview_confirmed') is not True:
        raise ValueError('CONFIRMED_INTERVIEW_REQUIRED')
    when = _text(data.get('as_of_utc'), 'AS_OF')
    stamp = datetime.fromisoformat(when.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('AS_OF_TIMEZONE_REQUIRED')
    when = stamp.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    ref = _text(data.get('confirmation_reference'), 'CONFIRMATION_REFERENCE', 500)
    answers = data.get('mentor_answers')
    if not isinstance(answers, dict) or not answers:
        raise ValueError('MENTOR_ANSWERS_REQUIRED')
    if len(canonical(answers).encode('utf-8')) > 20000:
        raise ValueError('MENTOR_ANSWERS_TOO_LARGE')
    # A preferred ratio is optional for onboarding. Record one when the
    # owner supplies it; never invent a 60/40 target for another family.
    style = data.get('long_term_style')
    normalized_style = None
    if style is not None:
        if not isinstance(style, dict) or set(style) != {'stock_weight', 'bond_weight'}:
            raise ValueError('LONG_TERM_STYLE_INVALID')
        try:
            sw, bw = (Decimal(str(style[k])) for k in ('stock_weight', 'bond_weight'))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError('LONG_TERM_STYLE_INVALID') from None
        if not sw.is_finite() or not bw.is_finite() or sw < 0 or bw < 0:
            raise ValueError('LONG_TERM_STYLE_INVALID')
        if sw > 1 or bw > 1 or sw + bw != 1:
            raise ValueError('LONG_TERM_STYLE_INVALID')
        normalized_style = {'stock_weight':str(sw), 'bond_weight':str(bw)}
    holdings = data.get('holdings')
    cash = data.get('cash')
    if not isinstance(holdings, list) or not isinstance(cash, list) or not holdings and not cash:
        raise ValueError('ASSETS_REQUIRED')
    seen = set()
    recorded_holdings = []
    for row in holdings:
        if not isinstance(row, dict):
            raise ValueError('HOLDING_INVALID')
        ticker = _text(row.get('ticker'), 'TICKER', 32).upper()
        currency = _text(row.get('currency'), 'CURRENCY', 8).upper()
        exchange = _text(row.get('exchange', 'UNKNOWN'), 'EXCHANGE', 30).upper()
        if not re.fullmatch(r'[A-Z0-9.^_-]+', ticker) or not re.fullmatch(r'[A-Z]{3}', currency):
            raise ValueError('HOLDING_IDENTITY_INVALID')
        key = (ticker, exchange, currency)
        if key in seen:
            raise ValueError('DUPLICATE_HOLDING')
        seen.add(key)
        value = _amount(row.get('reported_market_value'))
        qty = row.get('confirmed_quantity')
        if qty is not None:
            try:
                quantity = Decimal(str(qty))
            except (ValueError, InvalidOperation):
                raise ValueError('QUANTITY_INVALID') from None
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError('QUANTITY_INVALID')
            qty = str(quantity)
        recorded_holdings.append({
            'ticker':ticker, 'exchange':exchange, 'currency':currency,
            'display_name':_text(row.get('display_name'), 'DISPLAY_NAME', 160),
            'reported_market_value':str(value),
            'value_is_estimate':row.get('value_is_estimate') is True,
            'confirmed_quantity':qty,
        })
    money_seen = set()
    recorded_cash = []
    for row in cash:
        if not isinstance(row, dict):
            raise ValueError('CASH_INVALID')
        currency = _text(row.get('currency'), 'CURRENCY', 8).upper()
        if not re.fullmatch(r'[A-Z]{3}', currency) or currency in money_seen:
            raise ValueError('CASH_CURRENCY_INVALID_OR_DUPLICATE')
        money_seen.add(currency)
        recorded_cash.append({'currency':currency, 'reported_amount':str(_amount(row.get('reported_amount'))),
                              'settled_verified':row.get('settled_verified') is True})
    return {'interview_confirmed':True,
            'as_of_utc':when, 'confirmation_reference':ref,
            'mentor_answers':answers,
            'long_term_style':normalized_style,
            'holdings':recorded_holdings, 'cash':recorded_cash}


def _identity(db, client_id):
    clients = [row[0] for row in db.execute('select client_id from family_member_identity')]
    if clients != [client_id]:
        raise PermissionError('CLIENT_MISMATCH')


def _existing_account(db, client_id, account_key, ref, as_of):
    row = db.execute('select client_id from portfolio_account where account_key=?', (account_key,)).fetchone()
    if row and row[0] != client_id:
        raise PermissionError('ACCOUNT_CROSS_CLIENT')
    if row is None:
        db.execute('''insert into portfolio_account
            (client_id,account_key,account_label,account_currency,account_state,
             source_kind,source_reference,as_of_utc,created_at_utc)
            values(?,?,?,?,?,?,?,?,?)''',
            (client_id,account_key,'本人申報資產','TWD','REPORTED',
             'USER_CONFIRMED',ref,as_of,as_of))


def _run_id(client_id, request_id):
    return 'FIRST01-' + sha256((client_id + ':' + request_id).encode()).hexdigest()[:30]


def make_writer(client_id, account_key):
    """Trusted Coordinator.handlers[OPERATION] writer, run inside B06 transaction."""
    client_id = _text(client_id, 'CLIENT_ID')
    account_key = _text(account_key, 'ACCOUNT_KEY')

    def writer(db, payload):
        if not isinstance(payload, dict) or payload.get('client_id') != client_id:
            raise PermissionError('CLIENT_MISMATCH')
        request_id = _text(payload.get('request_id'), 'REQUEST_ID', 128)
        normalized = normalize_request(payload.get('confirmed_record'))
        _identity(db, client_id)
        for table in REQUIRED_TABLES:
            if not db.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone():
                raise RuntimeError('W1_SCHEMA_MISSING:' + table)
        ref, when = normalized['confirmation_reference'], normalized['as_of_utc']
        run_id = _run_id(client_id, request_id)
        if db.execute('select 1 from portfolio_snapshot_run where client_id=? and run_id=?',
                      (client_id,run_id)).fetchone():
            raise ValueError('INITIAL_SNAPSHOT_REQUEST_COLLISION')
        _existing_account(db, client_id, account_key, ref, when)
        items = []
        def item(domain, entity, field, value, *, unit=None, currency=None, source='USER_CONFIRMED'):
            items.append((domain,entity,field,str(value),unit,currency,source))
        item('PROFILE','MENTOR','interview_answers_json',canonical(normalized['mentor_answers']))
        if normalized['long_term_style'] is not None:
            item('PROFILE','LONG_TERM','stock_weight',normalized['long_term_style']['stock_weight'])
            item('PROFILE','LONG_TERM','bond_weight',normalized['long_term_style']['bond_weight'])
        for row in normalized['holdings']:
            ticker, exchange, currency = row['ticker'], row['exchange'], row['currency']
            found = db.execute('''select instrument_key from portfolio_instrument
                where client_id=? and ticker=? and exchange_code=? and quote_currency=?''',
                (client_id,ticker,exchange,currency)).fetchall()
            if len(found)>1:
                raise ValueError('DUPLICATE_INSTRUMENT_IDENTITY')
            key = found[0][0] if found else 'USER01-' + sha256(canonical([client_id,ticker,exchange,currency]).encode()).hexdigest()[:25]
            if not found:
                db.execute('''insert into portfolio_instrument
                    (client_id,instrument_key,instrument_type,ticker,exchange_code,
                     instrument_label,quote_currency,identity_state,source_kind,
                     source_reference,as_of_utc,created_at_utc)
                    values(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (client_id,key,'EQUITY',ticker,exchange,row['display_name'],
                     currency,'USER_REPORTED','USER_CONFIRMED',ref,when,when))
            # Quantity is unknown unless supplied by the owner. An estimated
            # market value must never be mistaken for cost basis or shares.
            db.execute('''insert into portfolio_position
                (client_id,account_key,instrument_key,as_of_utc,quantity_decimal,
                 cost_state,position_source_kind,position_source_reference,recorded_at_utc)
                values(?,?,?,?,?,?,?,?,?)''',
                (client_id,account_key,key,when,row['confirmed_quantity'],
                 'UNKNOWN','USER_CONFIRMED',ref,when))
            item('HOLDING',key,'ticker',ticker)
            item('HOLDING',key,'reported_market_value',row['reported_market_value'],
                 unit='CURRENCY',currency=currency,
                 source='USER_ESTIMATE' if row['value_is_estimate'] else 'USER_CONFIRMED')
            item('HOLDING',key,'value_is_estimate',str(row['value_is_estimate']).lower())
        for row in normalized['cash']:
            currency = row['currency']
            minor = int(_amount(row['reported_amount'])*100)
            snapshot_id = run_id + '-CASH-' + currency
            db.execute('''insert into cash_balance_snapshot
                (cash_snapshot_id,client_id,account_key,currency_code,as_of_utc,version,
                 source_snapshot_id,reported_cash_minor,reported_cash_basis,
                 data_state,source_kind,source_reference,reconciled_at_utc)
                values(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (snapshot_id,client_id,account_key,currency,when,1,run_id,minor,
                 'USER_REPORTED','REPORTED','USER_CONFIRMED',ref,None))
            item('CASH',account_key,'reported_amount_minor',minor,unit='MINOR',currency=currency)
            item('CASH',account_key,'settled_verified',str(row['settled_verified']).lower(),
                 source='USER_CONFIRMED')
        h = sha256(canonical(items).encode()).hexdigest()
        db.execute('''insert into portfolio_snapshot_run
            (client_id,run_id,as_of_utc,version_no,run_state,data_state,
             source_kind,source_reference,created_at_utc,sealed_at_utc,content_hash)
            values(?,?,?,?,?,?,?,?,?,?,?)''',
            (client_id,run_id,when,1,'RECORDED','USER_CONFIRMED',
             'USER_CONFIRMED',ref,when,when,h))
        for idx,(domain,entity,field,value,unit,currency,source) in enumerate(items,1):
            db.execute('''insert into portfolio_snapshot_item
                (client_id,run_id,item_no,domain_code,entity_key,field_key,
                 value_state,value_type,value_text,unit,currency_code,
                 source_kind,source_reference,source_observed_at_utc,recorded_at_utc)
                values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (client_id,run_id,idx,domain,entity,field,'KNOWN','TEXT',
                 value,unit,currency,source,ref,when,when))
        return {'status':'STORED','run_id':run_id,'client_id':client_id,
                'items':len(items),'holdings':len(normalized['holdings']),
                'cash_currencies':len(normalized['cash']),'content_hash':h,
                'long_term_style_only':True,'loop2_executed':False,
                'trade_authorization':'NONE'}
    return writer


def first_allocation_handler(coordinator, *, principal, resource, client_id, account_key):
    """Bind to FamilyMenu.handlers['first_allocation'] via trusted W7 gateway.

    Registration is separate: Coordinator must have make_writer(client_id,
    account_key) under OPERATION. DB name/ID/identity never come from user text.
    """
    def handle(payload):
        if not isinstance(payload, dict):
            raise ValueError('INVALID_MENU_PAYLOAD')
        request_id = _text(payload.get('request_id'), 'REQUEST_ID', 128)
        record = normalize_request(payload.get('confirmed_record'))
        before = coordinator.snapshot(resource, principal)
        with tempfile.TemporaryDirectory() as tmp:
            db_path=Path(tmp)/'before.db'
            db_path.write_bytes(before['data'])
            with sqlite3.connect(db_path) as check_db:
                _identity(check_db, client_id)
        data = {'client_id':client_id,'request_id':request_id,'confirmed_record':record}
        committed = coordinator.update(resource, principal, request_id, before['epoch'],OPERATION,data)
        result=committed['result']
        if result.get('status') != 'STORED' or result.get('client_id') != client_id:
            raise RuntimeError('INITIAL_SNAPSHOT_WRITE_FAILED')
        after=coordinator.snapshot(resource,principal)
        with tempfile.TemporaryDirectory() as tmp:
            db_path=Path(tmp)/'after.db'
            db_path.write_bytes(after['data'])
            with sqlite3.connect(db_path) as read_db:
                _identity(read_db,client_id)
                run = read_db.execute('''select content_hash from portfolio_snapshot_run
                    where client_id=? and run_id=?''', (client_id,result['run_id'])).fetchone()
                count=read_db.execute('''select count(*) from portfolio_snapshot_item
                    where client_id=? and run_id=?''',(client_id,result['run_id'])).fetchone()[0]
        if not run or run[0] != result['content_hash'] or count != result['items']:
            raise RuntimeError('FIRST_ALLOCATION_READBACK_FAILED')
        return {'status':STATUS,'client_id':client_id,'run_id':result['run_id'],
                'holdings_recorded':result['holdings'],'cash_currencies_recorded':result['cash_currencies'],
                'long_term_style_only':True,'loop2_executed':False,
                'trade_authorization':'NONE','save_receipt':{
                    'resource':resource,'run_id':result['run_id'],
                    'content_hash':result['content_hash'],'items_readback':count,
                    'readback_sha256':after['sha256'],
                    'epoch':after['epoch'],'verified':True}}
    return handle


def completion_check(result):
    """Menu 01 may close after verified snapshot, without Loop 1 or Loop 2."""
    if not isinstance(result,dict) or result.get('status') != STATUS:
        return False
    receipt=result.get('save_receipt')
    return (isinstance(receipt,dict) and receipt.get('verified') is True
            and result.get('loop2_executed') is False
            and result.get('trade_authorization') == 'NONE'
            and receipt.get('run_id') == result.get('run_id')
            and type(receipt.get('items_readback')) is int and receipt['items_readback'] > 0)
