"""Approved CMR9.2 proportional slice caps and SGOV funding-layer audit.

These caps feed the existing deployment MIN. They neither create cash nor
change a V70 ceiling, client target, broker reservation, or SGOV holding.
"""
from decimal import Decimal,localcontext,ROUND_FLOOR
from .approved_profiles import number


def funding_layers(*, available_cash, settled_cash, sgov_sources):
    cash=number(available_cash,'0');settled=number(settled_cash,'0');mobilizable=Decimal(0);missing=[];seen=set();audit=[]
    for source in sgov_sources:
        sid=source.get('source_id')
        if not sid or sid in seen:raise ValueError('DUPLICATE_OR_MISSING_SGOV_FUNDING_SOURCE')
        seen.add(sid)
        if source.get('sale_authorized') is False:
            audit.append({'source_id':sid,'mobilizable':'0','reason':'SALE_NOT_AUTHORIZED'});continue
        amounts=[number(source.get(k),'0') for k in ('physical_value','defensive_bond_role','dry_powder_role','retained_dry_floor','other_dry_commitments')]
        if None in amounts or source.get('sale_authorized') is not True or not source.get('role_source_reference'):
            missing.append(sid);audit.append({'source_id':sid,'mobilizable':None,'reason':'CURRENT_ROLE_OR_AUTHORIZATION_SOURCE_UNKNOWN'});continue
        physical,bond,dry,floor,committed=amounts
        if bond+dry>physical:raise ValueError('SGOV_ROLES_EXCEED_PHYSICAL_VALUE')
        value=max(dry-floor-committed,Decimal(0));mobilizable+=value
        audit.append({'source_id':sid,'mobilizable':str(value),'defensive_role_excluded':str(bond)})
    planning=cash+mobilizable if cash is not None and not missing else None
    return {'planning_pool':str(planning) if planning is not None else None,
        'available_cash':str(cash) if cash is not None else None,
        'authorized_mobilizable_sgov':str(mobilizable) if not missing else None,
        'settled_execution_cash':str(settled) if settled is not None else None,
        'sgov_sources':audit,'missing_sgov_sources':missing,
        'sgov_sale_performed':False,'sgov_included_in_settled_cash':False,
        'reporting_fx_is_execution_fx':False,'trade_action':'NO_TRADE'}


def allocate(*, owner, pool_id, slices, buckets, remaining_tactical_room):
    if not pool_id or not owner:raise ValueError('SHARED_SLICE_POOL_IDENTITY_REQUIRED')
    ids=[r['asset_id'] for r in slices]
    if len(ids)!=len(set(ids)):raise ValueError('DUPLICATE_ASSET_SLICE')
    if not slices:raise ValueError('AUTHORIZED_SLICE_UNIVERSE_REQUIRED')
    bucket_map={r['bucket_id']:r for r in buckets}
    if len(bucket_map)!=len(buckets):raise ValueError('DUPLICATE_FUNDING_BUCKET')
    sources=set()
    for b in buckets:
        if b.get('owner')!=owner or not b.get('currency'):raise ValueError('SLICE_BUCKET_OWNER_OR_CURRENCY_MISMATCH')
        own=set(b.get('funding_source_ids',[]))
        if not own or sources&own:raise ValueError('DUPLICATE_OR_MISSING_BUCKET_FUNDING_SOURCE')
        sources|=own
    tactical=number(remaining_tactical_room,'0');pre={};audit={}
    with localcontext() as ctx:
        ctx.prec=40;ctx.rounding=ROUND_FLOOR
        for bid,bucket in bucket_map.items():
            group=[r for r in slices if r.get('bucket_id')==bid]
            cash=number(bucket.get('available_authorized_notional_cash'),'0')
            amounts=[];invalid=[]
            for row in group:
                if row.get('owner')!=owner:raise ValueError('SLICE_ASSET_OWNER_MISMATCH')
                amount=number(row.get('slice'),'0');fx=number(row.get('fx_to_bucket'),'0')
                if fx==0:fx=None
                if not row.get('currency') or (row['currency']==bucket['currency'] and fx!=1):fx=None
                if row.get('currency')!=bucket['currency'] and not row.get('fx_source_reference'):fx=None
                if amount is None or fx is None:invalid.append(row['asset_id'])
                amounts.append(amount*fx if None not in (amount,fx) else None)
            zero=cash==0 or tactical==0
            factor=None;total=None
            if zero:factor=Decimal(0)
            elif cash is not None and not invalid:
                total=sum(amounts,Decimal(0));factor=min(Decimal(1),cash/total) if total else Decimal(1)
            for row,amount in zip(group,amounts):
                pre[row['asset_id']]=(Decimal(0) if zero else amount*min(cash,total)/total if total and factor is not None
                    else Decimal(0) if total==0 and factor is not None else None)
            audit[bid]={'shared_cash_counted_once':True,'slice_sum_in_bucket_currency':str(total) if total is not None else None,
                'bucket_factor':str(factor) if factor is not None else None,'unknown_assets':invalid}
        for row in slices:
            if row.get('bucket_id') not in bucket_map:pre[row['asset_id']]=None
        budget_values={}
        for row in slices:
            value=pre[row['asset_id']];fx=number(row.get('fx_bucket_to_budget'),'0')
            if fx==0:fx=None
            budget_values[row['asset_id']]=Decimal(0) if value==0 else value*fx if value is not None and fx is not None else None
        unknowns=[aid for aid,v in budget_values.items() if v is None]
        total=sum(budget_values.values(),Decimal(0)) if not unknowns else None
        factor=(Decimal(0) if tactical==0 else min(Decimal(1),tactical/total) if tactical is not None and total not in (None,0)
            else Decimal(1) if tactical is not None and total==0 else None)
        result={}
        for row in slices:
            aid=row['asset_id'];fx=number(row.get('fx_to_bucket'),'0');value=pre.get(aid)
            amount=(Decimal(0) if tactical==0 or value==0 and factor is not None else
                value*min(tactical,total)/total/fx if value is not None and factor is not None and total and fx not in (None,0) else None)
            result[aid]=str(amount) if amount is not None else None
    return {'schema_version':'V82.SharedSliceAllocation.v1','owner':owner,'pool_id':pool_id,
        'allocations':result,'buckets':audit,'total_pre_tactical_budget_currency':str(total) if total is not None else None,
        'remaining_tactical_room':str(tactical) if tactical is not None else None,
        'tactical_factor':str(factor) if factor is not None else None,'unknown_competing_assets':unknowns,
        'unused_rounding_reallocated':False,'v70_ceiling_changed':False,'trade_action':'NO_TRADE'}
