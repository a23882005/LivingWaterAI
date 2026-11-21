"""Read explicit Owner buy-order and accepted net-cash facts, without DB writes.

This source covers the named member only. Buy-side absence is not a complete
order/fill/commitment book; accepted net cash is never deducted a second time.
"""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
from family_input import digest
from member_market_source import time


def amount(value):
    if value is None or isinstance(value,bool):raise ValueError('OWNER_CASH_EXACT_NUMBER_REQUIRED')
    n=Decimal(str(value))
    if not n.is_finite() or n<0:raise ValueError('OWNER_CASH_NONNEGATIVE_NUMBER_REQUIRED')
    return n


def read(source,request):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('OWNER_FINANCIAL_SOURCE_BYTES_CHANGED')
    data=json.loads(raw);snapshot=request['client_snapshot']['payload']
    member=source.get('member');scope=data.get('scope') or {};row=(data.get('members') or {}).get(member)
    if (data.get('schema_version')!='Family.PM.OwnerUnfilledBuyConfirmation.v1'
        or data.get('source_type')!='DIRECT_OWNER_CONFIRMATION' or not data.get('confirmed_by')
        or not source.get('source_reference') or not member or not isinstance(row,dict)
        or str(snapshot.get('identity',{}).get('family_alias','')).casefold()!=member.casefold()
        or snapshot['client_id']!=request['client_id']
        or snapshot['payload_digest']!=digest(snapshot['tables'])
        or row.get('official_db_sha256')!=snapshot['source_sha256']
        or member not in scope.get('members',[]) or scope.get('fact')!='CURRENT_UNFILLED_BUY_ORDERS'
        or scope.get('confirmation_applies_from_current_turn') is not True
        or any(scope.get(k) is not False for k in ('sell_orders_covered','other_commitments_covered',
            'historical_fills_covered','historical_order_states_rewritten'))
        or request.get('trade_authorization')!='NONE'):
        raise PermissionError('OWNER_FINANCIAL_MEMBER_DB_OR_SCOPE_MISMATCH')
    # recorded_at is a conservative availability boundary, not a reconstructed
    # message-server timestamp. Earlier replays retain their original unknowns.
    if time(data['recorded_at'])>time(request['evaluation_at']):return None
    if (row.get('evidence_state')!='OWNER_CONFIRMED' or type(row.get('unfilled_buy_order_count')) is not int
        or row['unfilled_buy_order_count']!=0 or row.get('unfilled_buy_orders')!=[]
        or not row.get('unfilled_buy_notional_by_currency')
        or any(amount(v)!=0 for v in row['unfilled_buy_notional_by_currency'].values())
        or amount(row.get('additional_deduction_from_approved_cash'))!=0):
        raise PermissionError('OWNER_NO_UNFILLED_BUY_FACT_MISMATCH')
    original=data['prior_cash_source'];cash_raw=original['original_source_utf8'].encode()
    if sha256(cash_raw).hexdigest()!=original['sha256']:
        raise PermissionError('OWNER_PRIOR_ACCEPTED_CASH_BYTES_CHANGED')
    cash=json.loads(cash_raw);settlement=cash['owner_settlement_confirmation']
    if (cash.get('schema')!='Family.PM.OwnerAvailableCashConfirmation.v1'
        or settlement.get('status')!='OWNER_CONFIRMED_SETTLED'
        or time(settlement['confirmed_at'])>time(data['recorded_at'])):
        raise PermissionError('OWNER_PRIOR_SETTLEMENT_CONFIRMATION_REQUIRED')
    records=[];totals={};seen=set()
    for i,account in enumerate(cash['accounts']):
        if account.get('member')!=member:continue
        value=amount(account['owner_confirmed_available_cash']);currency=account.get('currency')
        key=account.get('cash_record_reference') or 'ACCEPTED_ACCOUNT:'+str(i)
        if key in seen:raise PermissionError('OWNER_ACCEPTED_CASH_DUPLICATE_RECORD')
        seen.add(key)
        records.append({'record_id':key,'member':member,'broker':account.get('broker'),
            'market':account.get('market'),'currency':currency,'amount':str(value),
            'account_key_candidates':deepcopy(account.get('account_keys_in_previous_review',[])),
            'account_binding_inferred':False,'source_kind':'OWNER_CONFIRMED_NET_AVAILABLE',
            'as_of':cash['recorded_at'],'source_json_pointer':'/accounts/'+str(i)})
        if currency:totals[currency]=totals.get(currency,Decimal(0))+value
        elif value!=0:raise PermissionError('OWNER_NONZERO_CASH_CURRENCY_REQUIRED')
    if not records:raise PermissionError('OWNER_MEMBER_ACCEPTED_CASH_REQUIRED')
    extra=(cash.get('separately_approved_additional_cash_TWD') or {}).get(member)
    if extra is not None:
        value=amount(extra);totals['TWD']=totals.get('TWD',Decimal(0))+value
        records.append({'record_id':'ACCEPTED_ADDITIONAL:'+member,'member':member,
            'currency':'TWD','amount':str(value),'source_kind':'SEPARATELY_APPROVED_ADDITIONAL_CASH',
            'as_of':cash['recorded_at'],'source_json_pointer':'/separately_approved_additional_cash_TWD/'+member,
            'account_binding_inferred':False})
    for bank in cash.get('owner_reported_bank_cash',[]):
        if bank.get('member')!=member:continue
        linked=[r for r in records if r['record_id']==bank['cash_record_id']]
        if (len(linked)!=1 or amount(linked[0]['amount'])!=amount(bank['amount'])
            or bank.get('planning_count')!=1 or bank.get('settlement_link_confirmed') is not True):
            raise PermissionError('OWNER_BANK_AND_BROKER_SAME_CASH_RECORD_REQUIRED')
        linked[0]['location_reference_count']=2
        linked[0]['amount_counted']=1
    if amount(row['cash_carried_forward']['TWD'])!=totals.get('TWD',Decimal(0)):
        raise PermissionError('OWNER_CARRIED_FORWARD_CASH_CONFLICT')
    overseas=sum((amount(r['amount']) for r in records if r.get('currency')!='TWD'),Decimal(0))
    if overseas!=amount(row['cash_carried_forward']['overseas_original_currency_record']):
        raise PermissionError('OWNER_CARRIED_FORWARD_OVERSEAS_CASH_CONFLICT')
    bound={k:request[k] for k in ('client_id','run_id','evaluation_at')}
    proof={'source_descriptor':deepcopy(source),'source_sha256':source['sha256'],
        'source_reference':source['source_reference'],'available_at':data['recorded_at'],
        'prior_cash_source_sha256':original['sha256'],'prior_cash_source_drive_id':original['drive_id']}
    buy=dict(schema_version='Family.W8.OwnerNoUnfilledBuys.v1',**bound,
        member=member,source_db_sha256=snapshot['source_sha256'],no_unfilled_buy_orders=True,
        active_buy_notional_by_currency=deepcopy(row['unfilled_buy_notional_by_currency']),
        sell_orders_covered=False,other_commitments_covered=False,historical_fills_covered=False,**proof)
    out=dict(schema_version='Family.W8.AcceptedOwnerFinancialFacts.v1',**bound,member=member,
        source_db_sha256=snapshot['source_sha256'],target_version=request['confirmed_target']['target_version'],
        source=proof,buy_order_confirmation=buy,cash_records=records,
        accepted_net_available_by_currency={k:str(v) for k,v in sorted(totals.items())},
        settlement_status=settlement['status'],cash_acceptance='OWNER_CONFIRMED_ACCEPTED_NET_CASH',
        bank_location_added_as_cash=False,additional_cash_counted_once=True,
        pending_buy_deduction_from_accepted_net_cash='0',
        other_commitments=None,sell_orders=None,historical_fills=None,
        complete_account_binding_asserted=False,complete_NAV_asserted=False,
        full_order_or_commitment_coverage_asserted=False,broker_freshness_asserted=False,
        trade_authorization='NONE')
    out['digest']=digest(out)
    return out


def bind_buy_orders(original,confirmation,request):
    if confirmation is None:return original
    if (confirmation.get('schema_version')!='Family.W8.OwnerNoUnfilledBuys.v1'
        or any(confirmation.get(k)!=request[k] for k in ('client_id','run_id','evaluation_at'))
        or confirmation.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
        or confirmation.get('no_unfilled_buy_orders') is not True
        or time(confirmation['available_at'])>time(request['evaluation_at'])):
        raise PermissionError('OWNER_BUY_CONFIRMATION_RUN_OR_MEMBER_MISMATCH')
    result=deepcopy(original)
    if original.get('complete_for_open_order_exposure'):
        asof=original.get('as_of') or original.get('snapshot_as_of')
        conflicts=[r for r in original.get('active_orders',[]) if r.get('side')=='BUY'
            and amount(r.get('order_qty'))>amount(r.get('confirmed_filled_qty'))]
        if conflicts and asof and time(asof)>=time(confirmation['available_at']):
            raise PermissionError('OWNER_BUY_CONFIRMATION_CONFLICT:broker_order_source.active_orders')
        if not asof or time(asof)<time(confirmation['available_at']):
            result.update(prior_order_source=deepcopy(original),active_orders=None,
                status='OWNER_CONFIRMED_BUY_SIDE_ONLY',complete_for_open_order_exposure=False)
    result['owner_buy_confirmation']=deepcopy(confirmation)
    result['active_buy_notional_by_currency']=deepcopy(confirmation['active_buy_notional_by_currency'])
    result['buy_orders_confirmed_empty']=True
    result['historical_order_or_fill_completeness_asserted']=False
    if not result.get('complete_for_open_order_exposure') and result.get('status')!='VERIFIED':
        result.update(status='OWNER_CONFIRMED_BUY_SIDE_ONLY',active_sell_orders=None,
            remaining_required_fields=['active_sell_orders_and_fill_reconciliation'],
            complete_for_open_order_exposure=False)
    return result
