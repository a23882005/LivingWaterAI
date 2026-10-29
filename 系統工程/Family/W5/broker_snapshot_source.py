"""Owner-bound read-only broker observations layered over an immutable DB.

The connector's account identity must be established separately. Margin funds
are retained as observations and never mapped to available brokerage cash.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json,re
from family_input import digest


def time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('BROKER_SOURCE_TIMEZONE_REQUIRED')
    return at


def number(value):
    if isinstance(value,bool) or value is None:raise ValueError('BROKER_SOURCE_NUMBER_REQUIRED')
    n=Decimal(str(value))
    if not n.is_finite():raise ValueError('BROKER_SOURCE_NONFINITE')
    return str(n)


def pinned(item):
    raw=Path(item['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=item['sha256']:raise PermissionError('BROKER_SOURCE_BYTES_CHANGED')
    return json.loads(raw)


def response(item,method):
    if item.get('tool_name')!=method:raise PermissionError('BROKER_SOURCE_METHOD_MISMATCH')
    result=pinned(item)
    if result.get('status')!='fulfilled':raise ValueError('BROKER_SOURCE_CALL_FAILED')
    value=result['value']
    if value.get('isError') or not isinstance(value.get('structuredContent'),dict):
        raise ValueError('BROKER_SOURCE_RESULT_UNAVAILABLE')
    return value['structuredContent']


def read(request,source):
    if source is None:return None
    manifest=pinned(source);owner=request['owner'];at=time(request['evaluation_at'])
    if (manifest.get('schema_version')!='Family.W5.ReadonlyBrokerSnapshot.v1'
        or manifest.get('client_id')!=request['client_id'] or manifest.get('owner')!=owner
        or manifest.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']):
        raise PermissionError('BROKER_SOURCE_OWNER_OR_DB_MISMATCH')
    authorization=pinned(manifest['owner_authorization'])
    if (authorization.get('schema_version')!='Family.W8.BrokerConnectionOwner.v1'
        or authorization.get('client_id')!=request['client_id'] or authorization.get('owner')!=owner
        or authorization.get('scope')!='READ_ONLY_RECONCILIATION_AND_ADVICE'
        or authorization.get('trade_authorization')!='NONE' or not authorization.get('source_reference')):
        raise PermissionError('BROKER_CONNECTION_OWNER_CONFIRMATION_REQUIRED')
    captured=time(manifest['captured_at'])
    if time(authorization['recorded_at'])>captured or captured>at:
        raise PermissionError('BROKER_SOURCE_FUTURE_CAPTURE')
    positions=response(manifest['positions'],'get_account_positions').get('positions')
    if not isinstance(positions,list):raise ValueError('BROKER_COMPLETE_POSITIONS_REQUIRED')
    rows=[];ids=set();symbols=set()
    for raw in positions:
        symbol=raw['contract_description'].split()[0];cid=raw['contract_id']
        qty=number(raw['position'])
        if (raw.get('asset_class')!='STK' or raw.get('currency')!=owner['currency']
            or not isinstance(cid,int) or isinstance(cid,bool) or cid<=0
            or not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*',symbol)
            or cid in ids or symbol in symbols or Decimal(qty)<0):
            raise ValueError('BROKER_POSITION_IDENTITY_OR_SCOPE_INVALID')
        ids.add(cid);symbols.add(symbol)
        rows.append({'symbol':symbol,'contract_id':cid,'quantity':qty,
            'currency':raw['currency'],'market_price':number(raw['market_price']),
            'average_price':number(raw['average_price']),'raw_broker_position':deepcopy(raw)})
    balances=response(manifest['balances'],'get_account_balances').get('balances',[])
    selected=[b for b in balances if b.get('currency')==owner['currency']]
    if len(selected)!=1:raise ValueError('BROKER_CASH_CURRENCY_AMBIGUOUS')
    cash={'total':number(selected[0]['cash_balance']),
        'settled_cash_observation':number(selected[0]['settled_cash']),
        'available':None,'unsettled':None,'reserved':None,
        'available_cash_formula_inferred':False,'margin_funds_used_as_cash':False}
    if Decimal(cash['total'])<0:raise ValueError('BROKER_NEGATIVE_CASH_REQUIRES_MARGIN_CONTRACT')
    if manifest.get('summary'):
        cash['account_summary_observations']=response(manifest['summary'],'get_account_summary')
    order_source={'schema_version':'Family.W5.BrokerOrderExposure.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(owner),
        'source_descriptor_digest':digest(source),'source_db_sha256':manifest['source_db_sha256'],
        'captured_at':manifest['captured_at'],'status':'UNKNOWN','active_orders':None,
        'complete_for_open_order_exposure':False,'lifecycle_fully_resolved':False,
        'source_reference':'IBKR.get_account_orders:working_only','issues':[]}
    if manifest.get('orders'):
        item=manifest['orders']
        if item.get('arguments')!={'show_completed':False}:
            raise PermissionError('BROKER_WORKING_ORDER_SCOPE_REQUIRED')
        try:
            raw_orders=response(item,'get_account_orders').get('orders')
            if not isinstance(raw_orders,list):raise ValueError('BROKER_ORDER_LIST_REQUIRED')
            parsed=[];seen=set();caveat=False
            for raw in raw_orders:
                oid=str(raw['order_id']);label=raw['primary_description'].split()
                symbol=label[-1];side=raw['side'];total=number(raw['total_shares_qty'])
                filled=number(raw['cum_shares_qty']);remaining=number(raw['remaining_shares_qty'])
                if (oid in seen or side not in ('BUY','SELL') or symbol not in symbols
                    or time(raw['order_time'])>captured or Decimal(total)<0 or Decimal(filled)<0
                    or Decimal(remaining)<0 or Decimal(total)-Decimal(filled)!=Decimal(remaining)):
                    raise ValueError('BROKER_ORDER_EXPOSURE_CONFLICT')
                seen.add(oid);status=raw['order_status']
                mapping={'SUBMITTED':'SUBMITTED','PRESUBMITTED':'SUBMITTED','OPEN':'OPEN',
                    'WORKING':'OPEN','PARTIALLY_FILLED':'PARTIAL_FILL','FILLED':'FILLED',
                    'CANCELLED':'CANCELLED','CANCELED':'CANCELLED','REJECTED':'REJECTED','EXPIRED':'EXPIRED'}
                if status=='REPLACED' and Decimal(remaining)>0:
                    # The provider returned this row in its working-only list.
                    # Retain remaining exposure conservatively until the
                    # replacement lifecycle is reconciled; do not drop it as
                    # the native terminal state with the same display label.
                    state='REPLACE_PENDING';caveat=True
                else:state=mapping.get(status)
                if state is None:raise ValueError('BROKER_ORDER_LIFECYCLE_MAPPING_REQUIRED')
                parsed.append({'asset_id':symbol,'order_intent_id':'IBKR:'+oid,'side':side,
                    'state':state,'order_qty':total,'confirmed_filled_qty':filled,
                    'remaining_qty':remaining,'provider_status':status,'order_time':raw['order_time'],
                    'limit_price':number(raw['limit_price'])})
            order_source.update(status='BROKER_WORKING_EXPOSURE_VERIFIED',active_orders=parsed,
                complete_for_open_order_exposure=True,lifecycle_fully_resolved=not caveat,
                exposure_scope='CONSERVATIVE_REPLACEMENT_EXPOSURE' if caveat else 'BROKER_WORKING_ORDER_SNAPSHOT')
        except (ValueError,KeyError) as error:
            order_source['issues'].append(str(error))
    return {'schema_version':'Family.W5.ReadonlyBrokerView.v1','client_id':request['client_id'],
        'run_id':request['run_id'],'owner':deepcopy(owner),'source_db_sha256':manifest['source_db_sha256'],
        'source_descriptor_digest':digest(source),'captured_at':manifest['captured_at'],
        'positions':rows,'cash':cash,'order_source':order_source,
        'owner_authorization':authorization,'database_written':False,'trade_action':'NO_TRADE'}


def project_positions(original,view):
    if view is None:return deepcopy(original)
    by={p['source_instrument']['ticker']:p for p in original}
    if len(by)!=len(original):raise ValueError('BROKER_REGISTRY_SYMBOL_AMBIGUOUS')
    output=[]
    for row in view['positions']:
        if row['symbol'] not in by:raise ValueError('BROKER_NEW_ASSET_MAPPING_REQUIRED:'+row['symbol'])
        old=by[row['symbol']];p=deepcopy(old);instrument=p['source_instrument']
        if instrument.get('quote_currency') not in (None,row['currency']):
            raise ValueError('BROKER_REGISTRY_CURRENCY_CONFLICT')
        p['original_db_position']=deepcopy(old)
        instrument.update(quote_currency=row['currency'],broker_contract_id=row['contract_id'],
            identity_overlay_scope='OWNER_BOUND_BROKER_CONTRACT_AND_CURRENCY__EXCHANGE_UNCHANGED')
        source_row={'source_reference':'IBKR:CONID:'+str(row['contract_id']),
            'account_key':view['owner']['account'],'broker_position':deepcopy(row['raw_broker_position'])}
        p.update(quantity=row['quantity'],quantity_state='KNOWN',source_position={
            'client_id':view['client_id'],'account_key':view['owner']['account'],
            'instrument_key':p['instrument_key'],'quantity_decimal':row['quantity'],
            'as_of_utc':view['captured_at'],'received_at_utc':view['captured_at'],
            'source_kind':'BROKER_READONLY_SNAPSHOT','source_row':source_row,
            'source_db_sha256':view['source_db_sha256'],
            'broker_source_descriptor_digest':view['source_descriptor_digest']})
        p['source_fields']={name:[{'value_state':'KNOWN','currency_code':row['currency'],
            'unit':row['currency']+'_PER_SHARE','value':row[field],
            'source_reference':source_row['source_reference']}] for name,field in
            [('last_price_displayed','market_price'),('average_price_displayed','average_price')]}
        output.append(p)
    return output


def project_holdings(holdings,positions,view):
    if view is None:return deepcopy(holdings)
    out=deepcopy(holdings)
    old={digest(p['original_db_position']['source_position']['source_row']) for p in positions}
    out['analysis_security_positions']=[r for r in out['analysis_security_positions'] if digest(r['source_row']) not in old]
    for p in positions:
        source=p['source_position']
        out['analysis_security_positions'].append({'symbol':p['source_instrument']['ticker'],
            'instrument':deepcopy(p['source_instrument']),'quantity':p['quantity'],'quantity_state':'KNOWN',
            'currency':view['owner']['currency'],'broker_label':'IB','source_kind':'BROKER_READONLY_SNAPSHOT',
            'source_row':deepcopy(source['source_row']),'source_run_id':view['run_id'],
            'observed_at':view['captured_at'],'received_at':view['captured_at'],
            'source_fields':deepcopy(p['source_fields'])})
    out['broker_snapshot_source_digest']=view['source_descriptor_digest']
    return out
