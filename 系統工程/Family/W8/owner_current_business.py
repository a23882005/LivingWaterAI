"""Current Owner business facts, separated from market and historical evidence."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
from family_input import digest
from member_market_source import time


def read(source,request):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('OWNER_CURRENT_SOURCE_BYTES_CHANGED')
    data=json.loads(raw);snapshot=request['client_snapshot']['payload'];member=source.get('member')
    selected=(data.get('members') or {}).get(member)
    if (data.get('schema_version')!='Family.PM.OwnerCurrentBusinessFacts.v1'
        or not data.get('confirmed_by') or not source.get('source_reference')
        or not isinstance(selected,dict) or data.get('trade_authorization')!='NONE'
        or request.get('trade_authorization')!='NONE'
        or str(snapshot.get('identity',{}).get('family_alias','')).casefold()!=str(member).casefold()
        or snapshot.get('client_id')!=request['client_id']
        or selected.get('client_id')!=request['client_id']
        or selected.get('source_db_sha256')!=snapshot['source_sha256']
        or snapshot.get('payload_digest')!=digest(snapshot['tables'])
        or any(selected.get(k) is not True for k in ('no_open_buy_orders','no_open_sell_orders',
            'other_unreported_commitments_absent','unreported_pending_receivables_or_payables_absent'))
        or data.get('existing_holding_preferences_preserved') is not True
        or data.get('existing_amounts_and_targets_preserved') is not True
        or any(data.get(k)!=[] for k in ('current_unreported_sell_orders','current_unreported_other_commitments',
            'current_unreported_pending_receivables_or_payables'))):
        raise PermissionError('OWNER_CURRENT_MEMBER_DB_OR_SCOPE_MISMATCH')
    if time(data['recorded_at'])>time(request['evaluation_at']):return None
    absences=deepcopy((data.get('unreported_position_quantity') or {}).get(member,{}))
    if any(isinstance(v,bool) or Decimal(str(v))!=0 for v in absences.values()):
        raise PermissionError('OWNER_CURRENT_ABSENCE_CANNOT_REPLACE_POSITIVE_HOLDING')
    out={'schema_version':'Family.W8.OwnerCurrentBusiness.v1',
        **{k:request[k] for k in ('client_id','run_id','evaluation_at')},'member':member,
        'source_db_sha256':snapshot['source_sha256'],'source_descriptor':deepcopy(source),
        'source_reference':source['source_reference'],'source_sha256':source['sha256'],
        'available_at':data['recorded_at'],'explicit_position_absences':absences,
        'unreported_positions_absent':True,'no_open_buy_orders':True,'no_open_sell_orders':True,
        'unreported_other_commitments':[],'unreported_pending_receivables_or_payables':[],
        'unreported_additional_constraints':[],
        'reported_preferences_and_constraints_preserved':True,
        'market_or_valuation_qualification_created':False,'historical_snapshots_rewritten':False,
        'trade_authorization':'NONE'}
    out['digest']=digest(out);return out


def order_confirmation(current,request):
    if current is None:return None
    return {'schema_version':'Family.W8.OwnerNoOpenOrders.v1','client_id':request['client_id'],
        'owner':deepcopy(request['owner']),'no_open_orders':True,
        'source_reference':current['source_reference'],'source_sha256':current['source_sha256'],
        'available_at':current['available_at'],'recorded_at':current['available_at'],
        'run_id':request['run_id'],'source_db_sha256':current['source_db_sha256'],
        'current_owner_business_fact':True,'historical_order_states_rewritten':False}


def holding_view(holding,symbol,current):
    result=deepcopy(holding)
    if current is None:return result
    if symbol in current['explicit_position_absences']:
        quantities=[result.get('quantity')]+[f.get('quantity') for f in result.get('source_facts',[])]
        if any(q is not None and Decimal(str(q))!=0 for q in quantities):
            raise PermissionError('OWNER_CURRENT_POSITIVE_HOLDING_CONFLICT:'+symbol)
        absent=True
    else:absent=result.get('quantity') is None and not result.get('source_facts')
    if absent:
        result.update(quantity='0',quantity_state='KNOWN',observed_at=current['available_at'],
            absence_is_not_zero=False,confirmed_absence_source={
                'source_reference':current['source_reference'],'sha256':current['source_sha256'],
                'available_at':current['available_at']})
    return result


def logical_portfolio(request,accepted,current):
    """Bind existing source categories; this never provisions a real account."""
    tables=request['client_snapshot']['payload']['tables'];accounts=tables.get('portfolio_account',[])
    books=[];used=set();cash_records=accepted['cash_records'];client=request['client_id']
    for record in cash_records:
        if record.get('source_kind')=='SEPARATELY_APPROVED_ADDITIONAL_CASH':continue
        market=record.get('market');currency=record.get('currency');overseas=market=='overseas'
        candidates=[]
        for account in accounts:
            if account['account_key'] not in record.get('account_key_candidates',[]):continue
            label=(account['account_key']+' '+str(account.get('account_label',''))).casefold()
            unit=account.get('account_currency')
            if currency and unit and unit!=currency:continue
            matching=any(x in label for x in (('美股','海外','-ib-','ib-us','interactive brokers','_us_') if overseas
                else ('台股','-tw-','_tw','twd')))
            score=(4 if currency and unit==currency else 0)+(3 if matching else 0)-(2 if 'cash' in label else 0)
            candidates.append((score,account))
        candidates.sort(key=lambda p:(-p[0],p[1]['account_key']))
        chosen=candidates[0][1] if candidates and (not overseas or candidates[0][0]>0) else None
        if currency is None and chosen is not None:currency=chosen.get('account_currency')
        # A zero foreign-currency record is bound only through the existing
        # account's stated currency, never by guessing a conversion.
        if currency is None:
            if Decimal(record['amount'])!=0:raise PermissionError('OWNER_CURRENT_ACCOUNT_CURRENCY_REQUIRED')
            continue
        aid=chosen['account_key'] if chosen is not None else (
            record['account_key_candidates'][0]+'/'+str(market).upper())
        if aid in used:aid=aid+'/'+currency
        used.add(aid)
        label=record.get('broker') or 'OWNER_REPORTED_CASH'
        broker=('IBKR' if label=='Interactive Brokers' else 'CATHAY' if label.startswith('Cathay Securities') else label)
        owner={'client_id':client,'account':aid,'broker':broker,'currency':currency,'funding_domain':'INVESTMENT'}
        books.append({'owner':owner,'cash_amount':record['amount'],'cash_record_ids':[record['record_id']],
            'source_account_keys':deepcopy(record.get('account_key_candidates',[])),
            'classification':'OWNER_ACCEPTED_EXISTING_LOGICAL_CATEGORY',
            'real_account_number_created':False,'broker_connection_verified':False})
    for record in cash_records:
        if record.get('source_kind')!='SEPARATELY_APPROVED_ADDITIONAL_CASH':continue
        selected=[b for b in books if b['owner']['currency']==record['currency']]
        if len(selected)!=1:raise PermissionError('OWNER_CURRENT_ADDITIONAL_CASH_CATEGORY_AMBIGUOUS')
        selected[0]['cash_amount']=str(Decimal(selected[0]['cash_amount'])+Decimal(record['amount']))
        selected[0]['cash_record_ids'].append(record['record_id'])
    # Old cash/source aliases remain addressable but are not extra balances.
    for account in accounts:
        if account['account_key'] in used:continue
        currency=account.get('account_currency')
        reference=next((b for b in books if b['owner']['currency']==currency),None)
        if reference is None:continue
        owner={**reference['owner'],'account':account['account_key']}
        books.append({'owner':owner,'cash_amount':'0','cash_record_ids':[],
            'source_representation_alias_of':reference['owner']['account'],
            'classification':'EXISTING_SOURCE_ALIAS__NOT_ADDITIONAL_CASH',
            'real_account_number_created':False,'broker_connection_verified':False})
    totals={}
    for book in books:
        c=book['owner']['currency'];totals[c]=totals.get(c,Decimal(0))+Decimal(book['cash_amount'])
    for currency,value in accepted['accepted_net_available_by_currency'].items():
        if totals.get(currency,Decimal(0))!=Decimal(value):raise PermissionError('OWNER_CURRENT_CASH_COUNTING_CONFLICT')
    return {'logical_accounts':books,'accepted_net_available_by_currency':{k:str(v) for k,v in totals.items()},
        'current_open_orders':[],'current_unreported_commitments':[],
        'current_unreported_receivables_or_payables':[],
        'reported_preference_records':{k:deepcopy(v) for k,v in tables.items()
            if 'holding_policy' in k or 'preference' in k},
        'reported_cap_records':{k:deepcopy(v) for k,v in tables.items() if 'constraint' in k or k.startswith('portfolio_cap')},
        'market_prices_or_NAV_qualification_asserted':False,'source':deepcopy(current)}
