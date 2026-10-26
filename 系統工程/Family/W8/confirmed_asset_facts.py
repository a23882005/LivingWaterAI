"""Append owner-confirmed asset facts to an existing single-family schema.

Local transaction only. Does not persist to Drive or authorize a trade. Existing
sealed history is never rewritten. Cash owner confirmation is deliberately not
promoted to a broker-settled ledger balance without the ledger evidence.
"""
import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _snapshot_hash(rows):
    # Preserve W7 first_allocation canonical seven-field tuple convention.
    # INTEGER_MINOR values are stringified like the original item() helper;
    # absent values use str(None), while value_state remains in the SQLite row.
    items = [(r['domain_code'],r['entity_key'],r['field_key'],
              str(r['value_integer_minor'] if r['value_type']=='INTEGER_MINOR' else r['value_text']),
              r['unit'],r['currency_code'],r['source_kind']) for r in rows]
    return hashlib.sha256(_canonical(items).encode()).hexdigest()


def _decimal(value, nonnegative=False):
    d = Decimal(str(value))
    if not d.is_finite() or (d < 0 if nonnegative else d <= 0):
        raise ValueError('INVALID_AMOUNT')
    return d


def _stamp(value):
    if not isinstance(value, str) or len(value) != 20 or datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H:%M:%SZ') != value:
        raise ValueError('INVALID_TIMESTAMP')
    return value


def _rows(db, sql, args=()):
    cur = db.execute(sql, args)
    return [dict(zip([x[0] for x in cur.description], r)) for r in cur.fetchall()]


def _insert(db, table, row):
    # Table and column names are exclusively from fixed application/schema data.
    db.execute('INSERT INTO "'+table+'" ('+','.join('"'+k+'"' for k in row)+') VALUES ('+','.join('?' for _ in row)+')', tuple(row.values()))


def append_confirmed_asset_facts(db, client_id, facts):
    """Caller owns commit/rollback; requires foreign_keys=ON and no active writer.

    facts: confirmed, request_id, source_reference, as_of_utc, account_key,
    instrument_key, quantity, cost_per_unit, currency, investable_cash,
    long_term_stock_weight, long_term_bond_weight, optional quote dictionary.
    quote contains price, currency, retrieved_at_utc, kind, url and either
    observed_at_utc or observed_date with observation_precision=TRADING_DATE_ONLY.
    """
    if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise ValueError('FOREIGN_KEYS_REQUIRED')
    identities = db.execute('SELECT client_id FROM family_member_identity').fetchall()
    if len(identities) != 1 or identities[0][0] != client_id:
        raise ValueError('FAMILY_IDENTITY_MISMATCH')
    if facts.get('confirmed') is not True:
        raise ValueError('OWNER_CONFIRMATION_REQUIRED')
    for key in ('request_id', 'source_reference', 'account_key', 'instrument_key', 'currency'):
        if not isinstance(facts.get(key), str) or not facts[key].strip():
            raise ValueError('MISSING_'+key.upper())
    stamp = _stamp(facts['as_of_utc'])
    quantity = _decimal(facts['quantity'])
    cost = _decimal(facts['cost_per_unit'])
    cash = _decimal(facts['investable_cash'], True)
    stock = _decimal(facts['long_term_stock_weight'], True)
    bond = _decimal(facts['long_term_bond_weight'], True)
    if stock + bond != 1:
        raise ValueError('LONG_TERM_WEIGHTS_MUST_SUM_TO_ONE')
    account, instrument, currency = facts['account_key'], facts['instrument_key'], facts['currency']
    for table, key, val in [('portfolio_account','account_key',account), ('portfolio_instrument','instrument_key',instrument)]:
        if not db.execute('SELECT 1 FROM '+table+' WHERE client_id=? AND '+key+'=?', (client_id,val)).fetchone():
            raise ValueError('UNKNOWN_'+key.upper())
    instrument_currency = db.execute('SELECT quote_currency FROM portfolio_instrument WHERE client_id=? AND instrument_key=?',(client_id,instrument)).fetchone()[0]
    if instrument_currency != currency or not db.execute('SELECT 1 FROM cash_account_scope WHERE client_id=? AND account_key=? AND currency_code=?',(client_id,account,currency)).fetchone():
        raise ValueError('ASSET_CURRENCY_SCOPE_MISMATCH')
    unit = db.execute('SELECT minor_digits FROM currency_registry WHERE currency_code=?', (currency,)).fetchone()
    if unit is None:
        raise ValueError('CURRENCY_NOT_REGISTERED')
    cash_minor = cash * Decimal(10) ** unit[0]
    if cash_minor != cash_minor.to_integral_value() or cash_minor > 9223372036854775807:
        raise ValueError('INVALID_MINOR_PRECISION')
    input_hash = hashlib.sha256(_canonical(facts).encode()).hexdigest()
    run_id = 'CONFIRM-'+hashlib.sha256((client_id+':'+facts['request_id']).encode()).hexdigest()[:32]
    run_ref = facts['source_reference']+'; payload_sha256='+input_hash
    old = db.execute('SELECT source_reference,run_state FROM portfolio_snapshot_run WHERE client_id=? AND run_id=?', (client_id,run_id)).fetchone()
    if old:
        if tuple(old) != (run_ref,'SEALED'):
            raise ValueError('IDEMPOTENCY_CONFLICT')
        return {'status':'LOCAL_ALREADY_PREPARED', 'run_id':run_id, 'persisted':False, 'trade_authorization':'NONE'}
    previous = _rows(db, "SELECT * FROM portfolio_snapshot_run WHERE client_id=? AND run_state='SEALED' AND source_kind<>'USER_HYPOTHETICAL' ORDER BY as_of_utc DESC, version_no DESC LIMIT 1", (client_id,))
    if not previous:
        raise ValueError('NO_ACTUAL_BASE_SNAPSHOT')
    if stamp <= previous[0]['as_of_utc']:
        raise ValueError('CONFIRMATION_NOT_AFTER_BASE')
    base_id = previous[0]['run_id']
    items = _rows(db,'SELECT * FROM portfolio_snapshot_item WHERE client_id=? AND run_id=? ORDER BY item_no',(client_id,base_id))
    keys = [(r['domain_code'],r['entity_key'],r['field_key']) for r in items]
    if len(keys) != len(set(keys)):
        raise ValueError('AMBIGUOUS_BASE_FIELDS')
    lineages = {r['item_no']: r for r in _rows(db,'SELECT * FROM portfolio_snapshot_lineage WHERE client_id=? AND run_id=?',(client_id,base_id))}
    position = _rows(db, 'SELECT * FROM portfolio_position WHERE client_id=? AND account_key=? AND instrument_key=? ORDER BY as_of_utc DESC LIMIT 1',(client_id,account,instrument))
    if not position or stamp <= position[0]['as_of_utc']:
        raise ValueError('NO_OLDER_POSITION')
    quote = facts.get('quote')
    if quote:
        if quote.get('currency') != currency or quote.get('kind') not in ('CLOSE','DELAYED','LIVE') or not str(quote.get('url','')).startswith('https://'):
            raise ValueError('INVALID_QUOTE_PROVENANCE')
        _stamp(quote['retrieved_at_utc'])
        if quote.get('observation_precision') == 'TRADING_DATE_ONLY':
            observation_day = quote.get('observed_date')
            if not isinstance(observation_day,str) or len(observation_day)!=10 or datetime.strptime(observation_day,'%Y-%m-%d').strftime('%Y-%m-%d')!=observation_day:
                raise ValueError('INVALID_QUOTE_DATE')
            observation_utc = None  # Do not invent an exact closing-event timestamp.
            valid_order = observation_day <= quote['retrieved_at_utc'][:10]
        else:
            observation_utc = _stamp(quote['observed_at_utc'])
            observation_day = observation_utc[:10]
            valid_order = observation_utc <= quote['retrieved_at_utc']
        if not valid_order or quote['retrieved_at_utc'] > stamp:
            raise ValueError('INVALID_QUOTE_TIME')
        price = _decimal(quote['price'])
    replacements = {}
    def put(domain,entity,field,value,kind='DECIMAL_TEXT',cur=None,unit=None,source=None,observed=None):
        replacements[(domain,entity,field)] = dict(value_state='UNKNOWN' if value is None else 'KNOWN',value_type=kind,
            value_text=None if value is None or kind=='INTEGER_MINOR' else str(value),
            value_integer_minor=int(value) if value is not None and kind=='INTEGER_MINOR' else None,
            currency_code=cur,unit=unit,source_kind='DOCUMENT' if source else 'OWNER_VERIFIED',
            source_reference=source or facts['source_reference'],source_observed_at_utc=(observed if source else stamp),recorded_at_utc=stamp)
    put('PROFILE','LONG_TERM','stock_weight',format(stock,'f'))
    put('PROFILE','LONG_TERM','bond_weight',format(bond,'f'))
    put('HOLDING',instrument,'confirmed_quantity',format(quantity,'f'),unit='SHARE')
    put('HOLDING',instrument,'cost_basis',format(quantity*cost,'f'),cur=currency,unit=currency)
    put('HOLDING',instrument,'cost_per_unit',format(cost,'f'),cur=currency,unit=currency)
    put('CASH',account,'reported_amount_minor',int(cash_minor),'INTEGER_MINOR',currency,'MINOR')
    put('CASH',account,'owner_confirmed_investable_minor',int(cash_minor),'INTEGER_MINOR',currency,'MINOR')
    put('CASH',account,'investable_confirmation_basis','OWNER_CONFIRMED_NOT_BROKER_RECONCILIATION','TEXT')
    # The legacy field is explicitly TWD; refuse to reuse it for another currency.
    if currency == 'TWD':
        put('HOLDING',instrument,'reference_market_value_twd',format(quantity*price,'f') if quote else None,cur=currency,unit=currency,source=quote['url'] if quote else None,observed=observation_utc if quote else None)
    else:
        put('HOLDING',instrument,'market_value',format(quantity*price,'f') if quote else None,cur=currency,unit=currency,source=quote['url'] if quote else None,observed=observation_utc if quote else None)
    put('HOLDING',instrument,'reference_value_only','false' if quote else 'true','BOOLEAN')
    put('HOLDING',instrument,'reference_valuation_date',observation_day if quote else None,'TEXT',source=quote['url'] if quote else None,observed=observation_utc if quote else None)
    for key,value in [('quote_price',format(price,'f') if quote else None),('quote_kind',quote['kind'] if quote else None),('quote_retrieved_at_utc',quote['retrieved_at_utc'] if quote else None),('quote_observation_precision',quote.get('observation_precision','TIMESTAMP') if quote else None)]:
        put('HOLDING',instrument,key,value,'DECIMAL_TEXT' if key=='quote_price' else 'TEXT',cur=currency if key=='quote_price' else None,source=quote['url'] if quote else None,observed=observation_utc if quote else None)
    # Validate all data before beginning inserts. SAVEPOINT also makes failures atomic.
    db.execute('SAVEPOINT confirmed_asset_facts')
    try:
        version=db.execute('SELECT COALESCE(MAX(version_no),0)+1 FROM portfolio_snapshot_run WHERE client_id=? AND as_of_utc=?',(client_id,stamp)).fetchone()[0]
        _insert(db,'portfolio_snapshot_run',dict(client_id=client_id,run_id=run_id,as_of_utc=stamp,version_no=version,run_state='DRAFT',data_state='PARTIAL',source_kind='OWNER_VERIFIED',source_reference=run_ref,created_at_utc=stamp,sealed_at_utc=None,content_hash=None))
        pos=dict(position[0]);pos.update(as_of_utc=stamp,quantity_decimal=format(quantity,'f'),cost_state='KNOWN',cost_basis_total_decimal=format(quantity*cost,'f'),cost_per_unit_decimal=format(cost,'f'),cost_currency=currency,cost_source_kind='OWNER_VERIFIED',cost_source_reference=facts['source_reference'],position_source_kind='OWNER_VERIFIED',position_source_reference=facts['source_reference'],recorded_at_utc=stamp)
        _insert(db,'portfolio_position',pos)
        # Do not rewrite the sealed cash ledger or fabricate settlement evidence.
        for item in items:
            original_no=item['item_no']; key=(item['domain_code'],item['entity_key'],item['field_key'])
            item.update(run_id=run_id)
            replacement=replacements.pop(key,None)
            if replacement:item.update(replacement)
            _insert(db,'portfolio_snapshot_item',item)
            lineage=dict(lineages.get(original_no,{}))
            if not lineage or replacement:
                lineage=dict(client_id=client_id,run_id=run_id,item_no=original_no,origin_domain='CONFIRMED_ASSET_FACT',origin_record_key=item['entity_key'],origin_effective_at_utc=item['source_observed_at_utc'],origin_received_at_utc=stamp,origin_record_version='1',origin_source_reference=item['source_reference'],origin_evidence_state='VERIFIED' if item['value_state']=='KNOWN' else 'UNKNOWN')
            else:lineage['run_id']=run_id
            _insert(db,'portfolio_snapshot_lineage',lineage)
        number=max([x['item_no'] for x in items],default=0)
        for (domain,entity,field),values in replacements.items():
            number+=1
            row=dict(client_id=client_id,run_id=run_id,item_no=number,domain_code=domain,entity_key=entity,field_key=field,source_row_key=None,**values)
            _insert(db,'portfolio_snapshot_item',row)
            _insert(db,'portfolio_snapshot_lineage',dict(client_id=client_id,run_id=run_id,item_no=number,origin_domain='CONFIRMED_ASSET_FACT',origin_record_key=entity,origin_effective_at_utc=row['source_observed_at_utc'],origin_received_at_utc=stamp,origin_record_version='1',origin_source_reference=row['source_reference'],origin_evidence_state='VERIFIED' if row['value_state']=='KNOWN' else 'UNKNOWN'))
        content=_rows(db,'SELECT * FROM portfolio_snapshot_item WHERE client_id=? AND run_id=? ORDER BY item_no',(client_id,run_id))
        digest=_snapshot_hash(content)
        db.execute("UPDATE portfolio_snapshot_run SET run_state='SEALED',sealed_at_utc=?,content_hash=? WHERE client_id=? AND run_id=?",(stamp,digest,client_id,run_id))
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('SQLITE_VALIDATION_FAILED')
        db.execute('RELEASE SAVEPOINT confirmed_asset_facts')
    except Exception:
        db.execute('ROLLBACK TO SAVEPOINT confirmed_asset_facts');db.execute('RELEASE SAVEPOINT confirmed_asset_facts');raise
    return {'status':'LOCAL_PREPARED','run_id':run_id,'base_run_id':base_id,'position_cost_total':format(quantity*cost,'f'),'market_value':format(quantity*price,'f') if quote else None,'cash_owner_confirmed_minor':int(cash_minor),'cash_ledger_state':'UNCHANGED','snapshot_items':number,'persisted':False,'trade_authorization':'NONE'}


def read_latest_confirmed_asset_facts(db, client_id):
    """Select the latest sealed actual facts, never combine different runs.

    This explicit reader supplements W5's history-preserving raw reader; it does
    not change W5 calculations or make an unverified cash ledger spendable.
    """
    identities=db.execute('SELECT client_id FROM family_member_identity').fetchall()
    if len(identities)!=1 or identities[0][0]!=client_id:
        raise ValueError('FAMILY_IDENTITY_MISMATCH')
    runs=_rows(db,"SELECT * FROM portfolio_snapshot_run WHERE client_id=? AND run_state='SEALED' AND source_kind<>'USER_HYPOTHETICAL' ORDER BY as_of_utc DESC,version_no DESC",(client_id,))
    if not runs:return {'status':'NO_ACTUAL_SNAPSHOT','fields':[],'trade_authorization':'NONE'}
    run=runs[0]
    if len(runs)>1 and (runs[1]['as_of_utc'],runs[1]['version_no'])==(run['as_of_utc'],run['version_no']):
        raise ValueError('AMBIGUOUS_LATEST_SNAPSHOT')
    items=_rows(db,'SELECT * FROM portfolio_snapshot_item WHERE client_id=? AND run_id=? ORDER BY item_no',(client_id,run['run_id']))
    if run['run_id'].startswith('CONFIRM-') and _snapshot_hash(items)!=run['content_hash']:
        raise ValueError('CONFIRMED_SNAPSHOT_HASH_MISMATCH')
    return {'status':'LATEST_ACTUAL_FACTS','run_id':run['run_id'],'as_of_utc':run['as_of_utc'],
        'data_state':run['data_state'],'fields':items,'cash_ledger_verified':False,'trade_authorization':'NONE'}
