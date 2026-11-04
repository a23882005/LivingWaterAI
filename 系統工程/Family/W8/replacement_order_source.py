"""Source-owner confirmed replacements -> existing C7 snapshot order book.

REPLACED alone proves neither a successor nor cash release. A pinned same-run
confirmation can retire its predecessor; the successor still passes every
original C7 order/fill/cash guard. This producer never alters cash or ledgers.
"""
from copy import deepcopy
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
import json
from family_input import digest
from member_market_source import time


def amount(value):
    if value is None or isinstance(value,bool):raise ValueError('C7_REPLACEMENT_EXACT_QUANTITY_REQUIRED')
    result=Decimal(str(value))
    if not result.is_finite() or result<0:raise ValueError('C7_REPLACEMENT_NONNEGATIVE_QUANTITY_REQUIRED')
    return result


def terminal_acknowledgment(order,owner,facts,chain=None):
    """A zero remaining counter alone never confirms an unfilled termination."""
    ack=order.get('terminal_acknowledgment') or {}
    if (ack.get('evidence_state')!='VERIFIED' or not ack.get('source_reference')
        or not isinstance(order.get('broker_order_id'),str) or not order['broker_order_id']
        or ack.get('broker_order_id')!=order['broker_order_id']
        or ack.get('broker_revision_id')!=order.get('broker_revision_id')
        or ack.get('final_state')!=order['state'] or ack.get('currency')!=owner['currency']
        or ack.get('owner')!=owner or ack.get('asset_id')!=order['asset_id']
        or not ack.get('confirmed_at') or not ack.get('available_at')):
        raise PermissionError('C7_TERMINAL_ORDER_SOURCE_ACKNOWLEDGMENT_REQUIRED')
    if not (time(ack['confirmed_at'])<=time(facts['as_of'])
        and time(ack['confirmed_at'])<=time(ack['available_at'])<=time(facts['available_at'])):
        raise PermissionError('C7_TERMINAL_ORDER_ACKNOWLEDGMENT_AFTER_CUTOFF')
    if any(amount(ack.get(k))!=amount(order[k]) for k in ('order_quantity','filled_quantity','remaining_quantity')):
        raise ValueError('C7_TERMINAL_ORDER_ACKNOWLEDGMENT_COUNTER_CONFLICT')
    if amount(order['filled_quantity'])>0:
        events=chain or [order['event_id']];fills={}
        for fill in facts.get('fills',[]):
            if fill.get('order_event_id') not in events:continue
            fid=fill.get('fill_id')
            if (not fid or (fid in fills and fills[fid]!=fill) or fill.get('account')!=owner['account']
                or fill.get('asset_id')!=order['asset_id']):
                raise PermissionError('C7_TERMINAL_ORDER_FILL_IDENTITY_CONFLICT')
            fills[fid]=fill
        with localcontext() as numeric:
            numeric.prec=50
            if sum((amount(f['quantity']) for f in fills.values()),Decimal(0))!=amount(order['filled_quantity']):
                raise ValueError('C7_TERMINAL_ORDER_EXECUTIONS_NOT_RECONCILED')
    return deepcopy(ack)


def reconcile(facts,request):
    originals=facts.get('orders',[]);confirmations=facts.get('replacement_confirmations',[])
    retired={r['event_id'] for r in originals if r.get('side')=='BUY' and r.get('state')=='REPLACED'}
    if not retired and not confirmations:return deepcopy(originals),None
    if (not isinstance(originals,list) or not isinstance(confirmations,list)
        or facts.get('coverage',{}).get('orders_complete') is not True
        or facts.get('coverage',{}).get('fills_reconciled') is not True):
        raise ValueError('C7_REPLACEMENT_COMPLETE_ORDER_AND_FILL_SCOPE_REQUIRED')
    orders={};duplicates=[]
    broker_keys={}
    for row in originals:
        event=row.get('event_id')
        if not isinstance(event,str) or not event:raise ValueError('C7_REPLACEMENT_EVENT_ID_REQUIRED')
        if event in orders:
            if orders[event]!=row:raise ValueError('C7_REPLACEMENT_CONFLICTING_ORDER_EVENT')
            duplicates.append(event)
        else:
            orders[event]=deepcopy(row)
            if row.get('broker_order_id') is not None:
                key=(row.get('account'),row['broker_order_id'],row.get('broker_revision_id'))
                if key in broker_keys:raise ValueError('C7_REPLACEMENT_BROKER_ORDER_VERSION_DUPLICATED')
                broker_keys[key]=event
    owners={r['owner']['account']:r['owner'] for r in facts['accounts']}
    edges={};incoming={};sources=[];seen={}
    for descriptor in confirmations:
        raw=Path(descriptor['local_path']).read_bytes()
        if sha256(raw).hexdigest()!=descriptor['sha256']:raise PermissionError('C7_REPLACEMENT_CONFIRMATION_BYTES_CHANGED')
        proof=json.loads(raw);pid=proof.get('confirmation_id')
        if not isinstance(pid,str) or not pid:raise ValueError('C7_REPLACEMENT_CONFIRMATION_ID_REQUIRED')
        if not (time(proof['confirmed_at'])<=time(facts['as_of'])
            and time(proof['confirmed_at'])<=time(proof['available_at'])<=time(descriptor['retrieved_at'])
            <=time(facts['available_at'])<=time(request['evaluation_at'])):
            raise PermissionError('C7_REPLACEMENT_CONFIRMATION_NOT_KNOWN_AT_CUTOFF')
        if pid in seen:
            if seen[pid]!=proof:raise ValueError('C7_REPLACEMENT_CONFLICTING_CONFIRMATION')
            continue
        seen[pid]=deepcopy(proof)
        old_id,new_id=proof.get('predecessor_event_id'),proof.get('successor_event_id')
        old,new=orders.get(old_id),orders.get(new_id)
        if old is None or new is None or old_id==new_id:raise ValueError('C7_REPLACEMENT_SUCCESSOR_OR_PREDECESSOR_REQUIRED')
        owner=owners.get(old.get('account'))
        if (proof.get('schema_version')!='Family.W8.OrderReplacementConfirmation.v1'
            or any(proof.get(k)!=request[k] for k in ('client_id','run_id','evaluation_at'))
            or proof.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
            or proof.get('owner')!=owner or owner is None or proof.get('evidence_state')!='VERIFIED'
            or proof.get('unfilled_commitment_transferred') is not True or not proof.get('source_reference')):
            raise PermissionError('C7_REPLACEMENT_OWNER_RUN_DB_OR_CONFIRMATION_UNVERIFIED')
        if (old_id not in retired or any(old.get(k)!=new.get(k) for k in ('account','asset_id','intent_id','side'))
            or old.get('side')!='BUY' or not old.get('intent_id')
            or proof.get('asset_id')!=old['asset_id'] or proof.get('intent_id')!=old['intent_id']
            or any(r.get('currency')!=owner['currency'] for r in (old,new,proof))):
            raise PermissionError('C7_REPLACEMENT_ACCOUNT_ASSET_OR_INTENT_CONFLICT')
        for name,row in (('predecessor',old),('successor',new)):
            key={'broker_order_id':row.get('broker_order_id'),'broker_revision_id':row.get('broker_revision_id')}
            if (not isinstance(key['broker_order_id'],str) or not key['broker_order_id'] or proof.get(name+'_order_key')!=key
                or row.get('filled_quantity_basis')!='CHAIN_CUMULATIVE'):
                raise PermissionError('C7_REPLACEMENT_BROKER_ID_REVISION_OR_FILL_BASIS_REQUIRED')
        if old['broker_order_id']==new['broker_order_id'] and (not old.get('broker_revision_id')
            or not new.get('broker_revision_id') or old['broker_revision_id']==new['broker_revision_id']):
            raise ValueError('C7_REPLACEMENT_SAME_ORDER_ID_DISTINCT_REVISIONS_REQUIRED')
        if old_id in edges or new_id in incoming:raise ValueError('C7_REPLACEMENT_FORK_OR_MERGE_NOT_ALLOWED')
        ack=old.get('last_acknowledged_commitment') or {}
        if (not ack.get('source_reference') or not ack.get('as_of') or time(ack['as_of'])>time(proof['confirmed_at'])
            or amount(ack.get('order_quantity'))!=amount(old.get('order_quantity'))
            or amount(ack.get('commitment_price'))!=amount(old.get('commitment_price'))
            or amount(old.get('commitment_price'))<=0
            or old.get('price_basis') not in ('ORIGINAL_LIMIT_PRICE','BROKER_COMMITMENT_PRICE')):
            raise ValueError('C7_REPLACEMENT_LAST_ACKNOWLEDGED_COMMITMENT_REQUIRED')
        if amount(old.get('filled_quantity'))>amount(old.get('order_quantity')) or amount(old.get('filled_quantity'))>amount(new.get('filled_quantity')):
            raise ValueError('C7_REPLACEMENT_CUMULATIVE_FILL_REGRESSION')
        if amount(old.get('remaining_quantity')) not in (Decimal(0),amount(old['order_quantity'])-amount(old['filled_quantity'])):
            raise ValueError('C7_REPLACEMENT_PREDECESSOR_REMAINING_CONFLICT')
        edges[old_id]=(new_id,proof);incoming[new_id]=old_id
        sources.append({'descriptor':deepcopy(descriptor),'confirmation':deepcopy(proof)})
    if set(edges)!=retired:raise ValueError('C7_REPLACED_SUCCESSOR_OR_ACKNOWLEDGMENT_REQUIRED')
    visited=set();chains=[]
    with localcontext() as numeric:
        numeric.prec=50
        for root in sorted(set(edges)-set(incoming)):
            chain=[root];current=root;last_at=None
            while current in edges:
                if current in visited:raise ValueError('C7_REPLACEMENT_CYCLIC_LINEAGE')
                visited.add(current);successor,proof=edges[current];at=time(proof['confirmed_at'])
                if last_at is not None and at<last_at:raise ValueError('C7_REPLACEMENT_ACKNOWLEDGMENT_ORDER_CONFLICT')
                last_at=at;chain.append(successor);current=successor
            leaf=orders[current]
            if leaf.get('state') not in ('SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING','FILLED','CANCELLED','REJECTED','EXPIRED'):
                raise ValueError('C7_REPLACEMENT_ACKNOWLEDGED_SUCCESSOR_STATE_REQUIRED')
            fills={}
            for fill in facts.get('fills',[]):
                if fill.get('order_event_id') not in chain:continue
                fid=fill.get('fill_id')
                if not fid or (fid in fills and fills[fid]!=fill):raise ValueError('C7_REPLACEMENT_FILL_IDENTITY_CONFLICT')
                if fill.get('account')!=leaf['account'] or fill.get('asset_id')!=leaf['asset_id']:
                    raise PermissionError('C7_REPLACEMENT_FILL_OWNER_OR_ASSET_CONFLICT')
                fills[fid]=fill
            if sum((amount(f['quantity']) for f in fills.values()),Decimal(0))!=amount(leaf.get('filled_quantity')):
                raise ValueError('C7_REPLACEMENT_CUMULATIVE_FILLS_NOT_RECONCILED')
            chains.append({'events':chain,'active_or_terminal_successor_event_id':current,
                'cumulative_filled_quantity':str(amount(leaf['filled_quantity'])),'unique_fill_ids':sorted(fills)})
    if visited!=retired:raise ValueError('C7_REPLACEMENT_CYCLIC_LINEAGE')
    if any(r.get('releases_event_id') in retired for r in facts.get('confirmed_releases',[])):
        raise ValueError('C7_REPLACEMENT_RETIRED_COMMITMENT_CANNOT_BE_RELEASED_AGAIN')
    result=[row for event,row in orders.items() if event not in retired]
    receipt=dict(schema_version='Family.W8.OrderReplacementReplay.v1',client_id=request['client_id'],run_id=request['run_id'],
        evaluation_at=request['evaluation_at'],retired_predecessors=[orders[e] for e in sorted(retired)],chains=chains,
        confirmation_sources=sources,identical_order_rows_deduplicated=duplicates,successor_orders_use_original_C7_guards=True,
        cash_or_authorization_recomputed=False,confirmed_cash_release_created=False,ledger_written=False,trade_action='NO_TRADE')
    receipt['digest']=digest(receipt)
    return result,receipt
