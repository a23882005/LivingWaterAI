"""Consume the PM-approved C7 capacity through the original V82 MIN/allocator.

The portfolio ceiling and source cash remain distinct. This seam never edits
Work3's V70 payload, Target, cash, daily G0/B0, or a broker order.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from c7_engine import load_original_configuration_module


class CeilingBindingError(ValueError):
    pass


def fail(code):raise CeilingBindingError('FAMILY_CEILING_'+code)


def bind(repo_path,computation,request,evidence):
    if computation is None or computation['result'].get('contract_version')!='C-W7-FAMILY-LT-v1.0.0':return None
    module=load_original_configuration_module(repo_path,'work7.family_long_term')
    result=computation['result'];proof=module.validate_result(result)
    if digest(computation['original_source'])!=computation['source_digest']:fail('SOURCE_DIGEST_MISMATCH')
    if result['status']!='READY_FOR_PM_GATE':fail('FRAMEWORK_NOT_READY')
    w3=request['work3_handoff'];scope=proof['input_scope'];owner=scope['family_owner']
    if (result['identity']['run_id']!=w3['run_id']
        or result['identity']['client_id']!=w3['client_state_context']['payload']['client_id']
        or owner['currency']!=w3['currency']
        or any(owner[k]!=w3['owner'][k] for k in ('broker','account'))
        or proof['canonical_input']['v70_asset_framework']['upstream_v70_snapshot_id']!=w3['v70_runtime_context']['upstream_v70_snapshot_id']):
        fail('ACCOUNT_RUN_OR_V70_SOURCE_MISMATCH')
    capacity=proof['occupancy_and_capacity'];currency=capacity['currency']
    rate=module.conversion(scope,proof['canonical_input'],result['created_at'],owner)
    gross=Decimal(str(scope['total_stock_ceiling']['amount']))
    if abs(Decimal(str(w3['v70_runtime_context']['payload']['stock_tactical_amount']))*rate-gross)>max(gross,Decimal(1))*Decimal('1e-12'):
        fail('ORIGINAL_GROSS_V70_AMOUNT_MISMATCH')
    context=evidence.get('approved_v10_context') or {}
    if context.get('identity',{}).get('owner')!=owner:fail('APPROVED_OWNER_SOURCE_MISMATCH')
    own_cash=[b for b in scope['funding_buckets'] if b['owner']==owner]
    if len(own_cash)!=1:fail('SELECTED_ACCOUNT_FUNDING_SOURCE_REQUIRED')
    bucket=own_cash[0];cash=w3['funding_context']['settlement']['cash_state']
    if bucket['value_state']=='KNOWN':
        expected=(Decimal(str(cash['available'])) if bucket['cash_basis']=='NET_AVAILABLE'
            else Decimal(str(cash['total']))-Decimal(str(cash['unsettled'])))
        allowed=Decimal(str(w3['funding_context']['executable_budget']['equity']['amount']))
        if (Decimal(str(bucket['cash_amount']))!=expected or Decimal(str(bucket['reserved_amount']))!=Decimal(str(cash['reserved']))
            or Decimal(str(bucket['authorized_incremental_amount']))>allowed):
            fail('WORK3_SETTLED_CASH_OR_AUTHORIZATION_SOURCE_MISMATCH')
    amount=capacity['incremental_capacity']
    if amount is None:fail('INCREMENTAL_CAPACITY_UNKNOWN')
    planning=planning_exposures(scope,capacity)
    return {'profile':module.PROFILE,'input_scope_digest':proof['input_scope_digest'],
        'scope':deepcopy(scope),'canonical_input':deepcopy(proof['canonical_input']),
        'evaluation_at':result['created_at'],'amount':Decimal(amount)/rate,'currency':w3['currency'],
        'budget_amount':Decimal(amount),'budget_currency':currency,'selected_account_fx_to_budget':str(rate),
        'c7_snapshot_id':result['work7_snapshot_id'],'capacity':deepcopy(capacity),
        'source_gross_v70_amount':str(scope['total_stock_ceiling']['amount']),
        'account_owners':deepcopy(scope['account_owners']),
        'planning_exposure_sources':planning,
        'pm_gate_released':False}


def planning_exposures(scope,capacity):
    """Carry the original capacity producer's release deduplication to SQLite."""
    events={r['event_id']:r for r in scope['exposures']};released={}
    ignored_releases={r['event_id'] for r in capacity['ignored_duplicate_or_release_events']
        if r['reason']!='IDENTICAL_EVENT_ALREADY_COUNTED'}
    for row in events.values():
        if (row['kind']=='RELEASE' and row.get('release_confirmed') is True
            and row['event_id'] not in ignored_releases
            and row['event_id'] not in scope['exposure_coverage']['confirmed_effects_already_applied']):
            target=row['releases_event_id'];released[target]=released.get(target,Decimal(0))+Decimal(str(row['amount']))
    planning=[]
    for row in events.values():
        if row['kind']=='ACTIVE_BUY_RESERVATION':
            planning.append({**deepcopy(row),'amount':str(Decimal(str(row['amount']))-released.get(row['event_id'],Decimal(0)))})
    return planning


def allocate(repo_path,binding,group,*,asset_id,daily_cap):
    """Use the unchanged CMR-ALLOC-01 arithmetic with a source-bound global pool.

    Multi-account inputs name real owners and unique owner/asset units. Only
    calculation keys are mapped to those unit ids; no broker identity is made
    up and each account keeps its own authorized cash bucket.
    """
    from livingwater_v82_runtime.slice_allocation import allocate as original_allocate
    from livingwater_v82_runtime.approved_profiles import number
    if group is None:fail('SHARED_ALLOCATION_SOURCE_REQUIRED')
    source=deepcopy(group);scope=binding['scope'];owner=scope['family_owner']
    budget_currency=binding.get('budget_currency',binding['currency'])
    budget_amount=binding.get('budget_amount',binding['amount'])
    if source.get('schema_version')!='V82.FamilyPortfolioSliceAllocation.v1':
        if len(scope['account_owners'])!=1:fail('PORTFOLIO_ALLOCATION_SOURCE_REQUIRED')
        if source.get('owner')!=owner:fail('SHARED_ACCOUNT_MISMATCH')
        own=[r for r in source.get('slices',[]) if r['asset_id']==asset_id]
        if len(own)!=1 or number(own[0].get('slice'),'0')!=number(daily_cap,'0'):fail('DAILY_SLICE_SOURCE_MISMATCH')
        if number(source.get('remaining_tactical_room'),'0')!=binding['amount']:fail('SHARED_INCREMENTAL_ROOM_MISMATCH')
        # Source cash cannot exceed the same C7 account's settled authorization.
        if len(source.get('buckets',[]))!=1:fail('ACCOUNT_CASH_BUCKET_SOURCE_REQUIRED')
        bucket=source['buckets'][0];audit=binding['capacity']['cash_audit'][0]
        if (bucket.get('bucket_id')!=audit['bucket_id'] or bucket.get('owner')!=owner
            or bucket.get('currency')!=binding['currency']
            or number(bucket.get('available_authorized_notional_cash'),'0')!=number(audit.get('native_available_authorized'),'0')):
            fail('SHARED_CASH_SOURCE_MISMATCH')
        out=original_allocate(**source)
        return {**out,'selected_allocation':out['allocations'].get(asset_id),
            'family_scope_digest':binding['input_scope_digest'],'family_ceiling_applied':True}
    module=load_original_configuration_module(repo_path,'work7.family_long_term')
    if (source.get('profile')!=module.PROFILE or source.get('input_scope_digest')!=binding['input_scope_digest']
        or source.get('identity')!=scope['identity'] or source.get('budget_currency')!=budget_currency
        or source.get('complete_universe') is not True):fail('PORTFOLIO_ALLOCATION_SOURCE_MISMATCH')
    module.receipt(source['receipt'],binding['canonical_input'],binding['evaluation_at'],'portfolio_allocation.receipt')
    rows=source['slices'];buckets=source['buckets'];units=[r['unit_id'] for r in rows]
    if len(units)!=len(set(units)) or not units:fail('PORTFOLIO_UNIT_AMBIGUOUS')
    selected=[r for r in rows if r['owner']==owner and r['asset_id']==asset_id]
    if len(selected)!=1 or number(selected[0].get('slice'),'0')!=number(daily_cap,'0'):fail('DAILY_SLICE_SOURCE_MISMATCH')
    permitted={digest(v) for v in scope['account_owners']};cash={r['bucket_id']:r for r in scope['funding_buckets']}
    # This actual portfolio identity is an arithmetic grouping key, not an
    # invented account. Actual per-account source owners are retained below.
    portfolio_owner={k:scope['identity'][k] for k in ('client_id','portfolio_id')}
    mapped_buckets=[]
    for bucket in buckets:
        original=cash.get(bucket['bucket_id']);audit=next((r for r in binding['capacity']['cash_audit'] if r['bucket_id']==bucket['bucket_id']),None)
        if (original is None or audit is None or bucket['owner']!=original['owner']
            or bucket['currency']!=original['currency'] or digest(bucket['owner']) not in permitted
            or number(bucket.get('available_authorized_notional_cash'),'0')!=number(audit.get('native_available_authorized'),'0')):
            fail('PORTFOLIO_ACCOUNT_CASH_SOURCE_MISMATCH')
        mapped_buckets.append({**bucket,'owner':portfolio_owner})
    mapped=[];seen=set()
    for row in rows:
        key=(digest(row['owner']),row['asset_id']);bucket=next((b for b in buckets if b['bucket_id']==row['bucket_id']),None)
        if (key in seen or key[0] not in permitted or bucket is None or row['owner']!=bucket['owner']
            or row['currency']!=bucket['currency'] or number(row.get('fx_to_bucket'),'0')!=1
            or number(row.get('fx_bucket_to_budget'),'0')!=module.conversion(scope,binding['canonical_input'],binding['evaluation_at'],row['owner'])):fail('PORTFOLIO_OWNER_OR_WORK64_FX_SOURCE_REQUIRED')
        seen.add(key);mapped.append({**row,'owner':portfolio_owner,'asset_id':row['unit_id']})
    out=original_allocate(owner=portfolio_owner,pool_id=source['pool_id'],slices=mapped,
        buckets=mapped_buckets,remaining_tactical_room=str(budget_amount))
    return {**out,'schema_version':'V82.FamilyPortfolioSliceAllocationResult.v1',
        'account_unit_sources':deepcopy(rows),'selected_unit_id':selected[0]['unit_id'],
        'selected_allocation':out['allocations'][selected[0]['unit_id']],
        'family_scope_digest':binding['input_scope_digest'],'family_ceiling_applied':True}


def validate_ledger_commit(source,binding,others,pending,previous,*,new_amount):
    """Inside the original SQLite transaction, reject stale global plan books.

    C7 already counted baseline reservations. Only this new delta consumes its
    remaining capacity. All accounts use the same member-owned ledger resource.
    """
    baseline=source.get('portfolio_cycle_baseline') or {}
    saved=baseline.get('cycles')
    if (baseline.get('complete') is not True or not isinstance(saved,list)
        or baseline.get('input_scope_digest')!=binding['input_scope_digest']
        or baseline.get('cycles_digest')!=digest(sorted(saved,key=lambda r:r['slice_cycle_id']))):
        fail('PORTFOLIO_LEDGER_BASELINE_SOURCE_REQUIRED')
    observed=[*others,*([previous] if previous is not None else [])]
    if sorted(observed,key=lambda r:r['slice_cycle_id'])!=sorted(saved,key=lambda r:r['slice_cycle_id']):
        fail('PORTFOLIO_LEDGER_CHANGED_REBUILD_REQUIRED')
    owners={digest(o) for o in binding['account_owners']};seen=set();exposures={}
    for row in binding['planning_exposure_sources']:
        if row['event_id'] in seen:continue
        seen.add(row['event_id']);key=(digest(row['owner']),row['asset_id'],row.get('intent_id'))
        exposures[key]=exposures.get(key,Decimal(0))+Decimal(str(row['amount']))
    for cycle in saved:
        owner=digest(cycle['owner'])
        if owner not in owners:fail('FOREIGN_ACCOUNT_IN_PORTFOLIO_LEDGER')
        for intent_id,item in cycle['intents'].items():
            if item['state'] not in ('PLANNED','SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'):continue
            amount=Decimal(item['remaining_amount']);key=(owner,cycle['asset_id'],intent_id)
            if amount>0 and exposures.get(key)!=amount:fail('PORTFOLIO_LEDGER_EXPOSURE_RECONCILIATION_REQUIRED')
    native=Decimal(str(new_amount));budget=native*Decimal(binding.get('selected_account_fx_to_budget','1'))
    if budget>Decimal(str(binding.get('budget_amount',binding['amount']))):fail('NEW_PLAN_EXCEEDS_SHARED_INCREMENTAL_CAPACITY')
    audit=next((r for r in binding['capacity']['cash_audit'] if r['bucket_id']==next(
        row['bucket_id'] for row in source['shared_allocation_request']['slices']
        if row['owner']==source['identity']['owner'] and row['asset_id']==source['identity']['asset_id'])),None)
    if audit is None or native>Decimal(audit['native_available_authorized']):fail('NEW_PLAN_EXCEEDS_ACCOUNT_CASH')


def mentor_evidence(repo_path,computation):
    if computation is None or computation['result'].get('contract_version')!='C-W7-FAMILY-LT-v1.0.0':return None
    module=load_original_configuration_module(repo_path,'work7.family_long_term')
    result=computation['result'];e=module.validate_result(result)
    return {'schema_version':'Family.W5.C7LongTermCapacityMentor.v1','profile':module.PROFILE,
        'c7_snapshot_id':result['work7_snapshot_id'],'source_db_sha256':e['source_db_sha256'],
        'target_version':e['target_version'],'approved_long_term_target':deepcopy(e['approved_long_term_target']),
        'project_target_money_base':deepcopy(e['project_target_money_base']),
        'current_weight_and_drift_base':deepcopy(e['current_weight_and_drift_base']),
        'capacity':deepcopy(e['occupancy_and_capacity']),'pm_gate':deepcopy(result['pm_gate']),
        'long_term_target_rewritten':False,'automatic_sell_or_sgov_purchase':False,
        'explanation':'長期核准目標保持；本輪新增另受已占用股票額度、各帳戶已結算授權現金、日切片、費用與股數限制。C7仍待中PM獨立Gate；僅供分析建議。',
        'trade_action':'NO_TRADE'}
