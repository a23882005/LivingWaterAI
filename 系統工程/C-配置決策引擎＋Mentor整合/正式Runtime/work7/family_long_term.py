"""Approved Family C7 profile: a long-term target and a separate stock ceiling.

Only the integration/accounting contract changes. V70 supplies its amount;
V82 owns Gap, daily slices, allocation order, fees, MIN and shares. Every
occupancy component retains its economic identity and source receipt.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,InvalidOperation
from hashlib import sha256
from pathlib import Path
import json

PROFILE='FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'
VERSION='C-W7-FAMILY-LT-v1.0.0'
WORK6_VERSION='C-W6-FAMILY-LT-v1.0.0'
APPROVAL_SHA256='112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0'
APPROVAL_PATH='系統工程/Family/W8/契約/V82_C7_長期目標與當輪額度分離_中PM裁定_v1.0_20261030.md'
BASE=Path(__file__).resolve().parents[1]


class FamilyScopeError(ValueError):
    def __init__(self,code,path):
        self.code=code;self.path=path
        self.issues=[{'code':code,'field_path':path,'severity':'BLOCKING','blocking':True}]
        super().__init__(code+':'+path)


def fail(code,path):raise FamilyScopeError(code,path)


def number(value,path):
    try:
        if value is None or isinstance(value,bool):raise ValueError()
        n=Decimal(str(value))
        if not n.is_finite() or n<0:raise ValueError()
        return n
    except (ValueError,InvalidOperation):fail('C_W7_LT_NONNEGATIVE_NUMBER_REQUIRED',path)


def time(value,path):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.utcoffset() is None:raise ValueError()
        return d
    except (AttributeError,ValueError,TypeError):fail('C_W7_LT_TIME_REQUIRED',path)


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def verify_profile():
    root=BASE.parents[2]
    if sha256((root/APPROVAL_PATH).read_bytes()).hexdigest()!=APPROVAL_SHA256:
        fail('C_W7_LT_APPROVAL_SOURCE_LOCK_MISMATCH','profile.approval')
    manifest=json.loads((BASE/'contracts_c7/Family_LongTerm_V70Ceiling_v1.manifest.json').read_text())
    if manifest.get('profile')!=PROFILE or manifest.get('approval_sha256')!=APPROVAL_SHA256:
        fail('C_W7_LT_PROFILE_LOCK_MISMATCH','profile')
    for row in manifest['files']:
        if sha256((BASE/row['path']).read_bytes()).hexdigest()!=row['sha256']:
            fail('C_W7_LT_PROFILE_FILE_CHANGED',row['path'])
    return manifest


def receipt(proof,canonical,evaluated_at,path):
    refs={s['source_id']:s for s in canonical['source_references']}
    original=refs.get(proof.get('source_reference_id'))
    if original is None or proof.get('source_sha256')!=original.get('source_fingerprint'):
        fail('C_W7_LT_SOURCE_REFERENCE_OR_HASH_MISMATCH',path)
    at=time(evaluated_at,'evaluated_at')
    if not time(proof.get('as_of'),path+'.as_of')<=time(proof.get('available_at'),path+'.available_at')<=at:
        fail('C_W7_LT_SOURCE_NOT_AVAILABLE_AT_CUTOFF',path)
    if proof.get('qualification')!='VERIFIED_AT_CUTOFF':
        fail('C_W7_LT_SOURCE_QUALIFICATION_REQUIRED',path)


def validate_scope(source,canonical,evaluated_at):
    from jsonschema import Draft202012Validator
    verify_profile()
    schema=json.loads((BASE/'contracts_c7/83_Family_LongTerm_V70Ceiling_Input.schema.json').read_text())
    errors=sorted(Draft202012Validator(schema).iter_errors(source),key=lambda e:str(list(e.path)))
    if errors:fail('C_W7_LT_SCOPE_SCHEMA_INVALID','family_scope.'+'.'.join(map(str,errors[0].path)))
    if source['identity']!=canonical['identity']:
        fail('C_W7_LT_SCOPE_IDENTITY_MISMATCH','family_scope.identity')
    owner=source['family_owner']
    if owner['client_id']!=canonical['identity']['client_id']:
        fail('C_W7_LT_SCOPE_OWNER_MISMATCH','family_scope.family_owner')
    if owner not in source['account_owners'] or len({digest(o) for o in source['account_owners']})!=len(source['account_owners']):
        fail('C_W7_LT_ACCOUNT_SCOPE_MISMATCH','family_scope.account_owners')
    if any(o['client_id']!=owner['client_id'] for o in source['account_owners']):
        fail('C_W7_LT_FOREIGN_ACCOUNT_OWNER','family_scope.account_owners')
    approved=source['approved_long_term_target']
    if digest(approved)!=source['approved_target_digest']:
        fail('C_W7_LT_APPROVED_TARGET_DIGEST_MISMATCH','family_scope.approved_long_term_target')
    if (approved.get('confirmation_status')!='CONFIRMED' or not approved.get('confirmed_by')
        or time(approved.get('confirmed_at'),'approved.confirmed_at')>time(evaluated_at,'evaluated_at')):
        fail('C_W7_LT_EXISTING_APPROVAL_REQUIRED','family_scope.approved_long_term_target')
    receipt(source['approval_receipt'],canonical,evaluated_at,'family_scope.approval_receipt')
    receipt(source['exposure_coverage'],canonical,evaluated_at,'family_scope.exposure_coverage')
    if source['exposure_coverage']['complete'] is not True:
        fail('C_W7_LT_COMPLETE_EXPOSURE_SOURCE_REQUIRED','family_scope.exposure_coverage')
    if not any(r['kind']!='RELEASE' for r in source['exposures']) and source['exposure_coverage'].get('empty_portfolio_asserted') is not True:
        fail('C_W7_LT_EMPTY_EXPOSURE_ASSERTION_REQUIRED','family_scope.exposures')
    current=canonical['allocations']['current_allocation'].get('snapshot')
    if not isinstance(current,dict):
        fail('C_W7_LT_CURRENT_ALLOCATION_REQUIRED','allocations.current_allocation')
    if source['current_nav']!=current.get('denominator'):
        fail('C_W7_LT_CURRENT_NAV_BINDING_MISMATCH','family_scope.current_nav')
    if (source['current_nav'].get('value_state')!='KNOWN'
        or number(source['current_nav'].get('amount'),'current_nav.amount')<=0
        or source['current_nav'].get('currency')!=source['budget_currency']):
        fail('C_W7_LT_CURRENT_NAV_OR_FX_REQUIRED','family_scope.current_nav')
    if approved['denominator']['value_state']!='KNOWN' or number(approved['denominator']['amount'],'approved.denominator')<=0:
        fail('C_W7_LT_APPROVED_INVESTMENT_POOL_REQUIRED','family_scope.approved_long_term_target.denominator')
    if approved['denominator']['currency']!=source['budget_currency']:
        fail('C_W7_LT_APPROVED_POOL_WORK64_FX_REQUIRED','family_scope.approved_long_term_target.denominator.currency')
    pool=number(approved['denominator']['amount'],'approved.denominator.amount')
    ids=set();total=Decimal(0)
    for row in approved['positions']:
        if row['instrument_id'] in ids:fail('C_W7_LT_APPROVED_INSTRUMENT_DUPLICATED','approved.positions')
        ids.add(row['instrument_id']);w=row['weight'];a=row['portfolio_amount']
        if (w['value_state']!='KNOWN' or a['value_state']!='KNOWN' or a['currency']!=source['budget_currency']
            or w.get('unit')!='portfolio_weight'):
            fail('C_W7_LT_APPROVED_MONEY_SOURCE_UNKNOWN','approved.positions.'+row['instrument_id'])
        rate=number(w['value'],'approved.weight');total+=rate
        if rate>1 or abs(number(a['amount'],'approved.amount')-pool*rate)>max(pool,Decimal(1))*Decimal('1e-12'):
            fail('C_W7_LT_APPROVED_POOL_AMOUNT_WEIGHT_MISMATCH','approved.positions.'+row['instrument_id'])
    if abs(total-1)>Decimal('0.0000005'):fail('C_W7_LT_APPROVED_TARGET_NOT_100_PERCENT','approved.positions')
    return deepcopy(source)


def conversion(scope,canonical,evaluated_at,owner):
    """Work64 reporting normalization; never an execution FX instruction."""
    if owner['currency']==scope['budget_currency']:return Decimal(1)
    rows=[r for r in scope.get('budget_normalizations',[]) if r['owner']==owner]
    if len(rows)!=1:fail('C_W7_LT_WORK64_FX_RECEIPT_REQUIRED','budget_normalizations')
    fx=rows[0];receipt(fx['receipt'],canonical,evaluated_at,'budget_normalizations.receipt')
    if (fx['from_currency']!=owner['currency'] or fx['to_currency']!=scope['budget_currency']
        or fx['purpose']!='REPORTING_BUDGET_NORMALIZATION_NOT_EXECUTION'
        or fx['accounting_base_id']!=scope['total_stock_ceiling']['accounting_base']['base_id']):
        fail('C_W7_LT_WORK64_FX_SCOPE_MISMATCH','budget_normalizations')
    rate=number(fx['quote_per_base'],'budget_normalizations.quote_per_base')
    if rate==0:fail('C_W7_LT_WORK64_FX_POSITIVE_RATE_REQUIRED','budget_normalizations')
    return rate


def capacity(source,canonical,evaluated_at):
    """Engineering 63-B only; no asset selection or redistribution occurs here."""
    data=validate_scope(source,canonical,evaluated_at)
    currency=data['budget_currency'];owners={digest(o) for o in data['account_owners']}
    total=data['total_stock_ceiling'];receipt(total['receipt'],canonical,evaluated_at,'total_stock_ceiling.receipt')
    if total['currency']!=currency or total['cap_scope']!='TOTAL_PORTFOLIO_STOCK':
        fail('C_W7_LT_CEILING_SCOPE_OR_CURRENCY_MISMATCH','total_stock_ceiling')
    base=total['accounting_base']
    if base['currency']!=currency or number(base['amount'],'ceiling.accounting_base')<=0:
        fail('C_W7_LT_CEILING_ACCOUNTING_BASE_REQUIRED','total_stock_ceiling.accounting_base')
    raw=canonical['v70_asset_framework'].get('stock_tactical_amount') or {}
    if (raw.get('value_state')!='KNOWN' or raw.get('currency')!=currency
        or number(raw.get('amount'),'v70.stock_tactical_amount')!=number(total['amount'],'ceiling.amount')):
        fail('C_W7_LT_CEILING_ORIGINAL_V70_AMOUNT_MISMATCH','total_stock_ceiling.amount')
    ceiling=number(total['amount'],'ceiling.amount');cap_audit=[];unknown_caps=[]
    for i,cap in enumerate(data['portfolio_caps']):
        path='portfolio_caps.'+str(i)
        if cap['applicability']=='NOT_APPLICABLE':
            cap_audit.append({'cap_id':cap['cap_id'],'state':'NOT_APPLICABLE'});continue
        if cap['value_state']!='KNOWN':unknown_caps.append(cap['cap_id']);continue
        receipt(cap['receipt'],canonical,evaluated_at,path+'.receipt')
        if cap['currency']!=currency or cap['accounting_base']!=base:
            fail('C_W7_LT_CAP_ACCOUNTING_BASE_MISMATCH',path)
        ceiling=min(ceiling,number(cap['amount'],path+'.amount'))
        cap_audit.append({'cap_id':cap['cap_id'],'state':'APPLIED','amount':str(number(cap['amount'],path+'.amount'))})
    components={};releases=[];ignored=[];covered={};by_account={}
    for i,item in enumerate(data['exposures']):
        path='exposures.'+str(i);receipt(item['receipt'],canonical,evaluated_at,path+'.receipt')
        if digest(item['owner']) not in owners or item['currency']!=item['owner']['currency']:
            fail('C_W7_LT_EXPOSURE_OWNER_OR_CURRENCY_MISMATCH',path)
        rate=conversion(data,canonical,evaluated_at,item['owner'])
        event=item['event_id']
        if event in components:
            if components[event]!=item:fail('C_W7_LT_CONFLICTING_ECONOMIC_EVENT',path)
            ignored.append({'event_id':event,'reason':'IDENTICAL_EVENT_ALREADY_COUNTED'});continue
        components[event]=item
        if item['kind']=='RELEASE':releases.append(item);continue
        if item['kind']=='ACTIVE_BUY_RESERVATION':
            if (item.get('side')!='BUY' or item.get('amount_basis')!='REMAINING_UNFILLED_NOTIONAL'
                or item.get('lifecycle_state') not in ('PLANNED','SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING')):
                fail('C_W7_LT_BUY_REMAINING_EXPOSURE_REQUIRED',path)
        for effect in item['economic_effect_ids']:
            if effect in covered:fail('C_W7_LT_ECONOMIC_EXPOSURE_DOUBLE_COUNT',path+'.economic_effect_ids')
            covered[effect]=event
        value=number(item['amount'],path+'.amount')*rate;key=digest(item['owner'])
        by_account[key]=by_account.get(key,Decimal(0))+value
    positive=sum((number(r['amount'],'exposure.amount')*conversion(data,canonical,evaluated_at,r['owner']) for r in components.values() if r['kind']!='RELEASE'),Decimal(0))
    released=Decimal(0);release_by_target={}
    for item in releases:
        event=item['event_id'];target=components.get(item.get('releases_event_id'))
        if item.get('release_confirmed') is not True:
            ignored.append({'event_id':event,'reason':'RELEASE_NOT_CONFIRMED__COMMITMENT_RETAINED'});continue
        if event in data['exposure_coverage']['confirmed_effects_already_applied']:
            ignored.append({'event_id':event,'reason':'ALREADY_REFLECTED_IN_CONFIRMED_EXPOSURE'});continue
        if (target is None or target['kind']=='RELEASE' or item['owner']!=target['owner']
            or item.get('intent_id')!=target.get('intent_id') or item.get('asset_id')!=target.get('asset_id')
            or item.get('release_state') not in ('CANCELLED','EXPIRED','REJECTED','LOCAL_RELEASED','CONFIRMED_POSITION_REDUCTION')):
            fail('C_W7_LT_CONFIRMED_RELEASE_BINDING_REQUIRED','exposures.'+event)
        value=number(item['amount'],'release.amount');target_id=target['event_id']
        release_by_target[target_id]=release_by_target.get(target_id,Decimal(0))+value
        if release_by_target[target_id]>number(target['amount'],'released_exposure.amount'):
            fail('C_W7_LT_RELEASE_EXCEEDS_RECORDED_EXPOSURE','exposures.'+event)
        normalized=value*conversion(data,canonical,evaluated_at,item['owner'])
        released+=normalized;by_account[digest(item['owner'])]-=normalized
    occupied=positive-released
    if unknown_caps:
        # Even an unknown additional MIN cap cannot increase the qualified
        # V70 upper bound. Exhaustion is therefore a provable zero without
        # inventing the missing cap or cash value.
        room=Decimal(0) if occupied>=ceiling else None;overage=None
    else:
        room=max(ceiling-occupied,Decimal(0));overage=max(occupied-ceiling,Decimal(0))
    funding=Decimal(0);funding_unknown=[];cash_audit=[];funding_accounts=set()
    for i,bucket in enumerate(data['funding_buckets']):
        key=digest(bucket['owner']);path='funding_buckets.'+str(i)
        if key not in owners or key in funding_accounts or bucket['currency']!=bucket['owner']['currency']:
            fail('C_W7_LT_FUNDING_ACCOUNT_SCOPE_OR_DUPLICATION',path)
        funding_accounts.add(key)
        if bucket['value_state']!='KNOWN' or bucket['settled'] is not True:
            funding_unknown.append(bucket['bucket_id']);cash_audit.append({'bucket_id':bucket['bucket_id'],'state':'UNKNOWN'});continue
        receipt(bucket['receipt'],canonical,evaluated_at,path+'.receipt')
        rate=conversion(data,canonical,evaluated_at,bucket['owner'])
        cash=number(bucket['cash_amount'],path+'.cash_amount');reserved=number(bucket['reserved_amount'],path+'.reserved_amount')
        if bucket['cash_basis']=='GROSS_SETTLED_CASH':
            if reserved>cash:fail('C_W7_LT_RESERVATIONS_EXCEED_GROSS_CASH',path)
            cash-=reserved
        # A read-only local PLANNED commitment has not become a broker cash
        # reservation. Broker net cash therefore still needs this deduction.
        planned=Decimal(0)
        for event,item in components.items():
            if (item['kind']=='ACTIVE_BUY_RESERVATION' and item.get('lifecycle_state')=='PLANNED'
                and item['owner']==bucket['owner']):
                planned+=number(item['amount'],'planned.amount')-release_by_target.get(event,Decimal(0))
        cash=max(cash-planned,Decimal(0))
        authorization=number(bucket['authorized_incremental_amount'],path+'.authorized_incremental_amount')
        available=min(cash,authorization);funding+=available*rate
        cash_audit.append({'bucket_id':bucket['bucket_id'],'state':'KNOWN','cash_basis':bucket['cash_basis'],
            'net_available':str(cash*rate),'authorized':str(authorization*rate),'available_authorized':str(available*rate),
            'native_net_available':str(cash),'native_authorized':str(authorization),'native_available_authorized':str(available),
            'currency':bucket['currency'],'budget_currency':currency,'fx_to_budget':str(rate),
            'local_planning_deducted_here':str(planned),
            'reserved_deducted_here':bucket['cash_basis']=='GROSS_SETTLED_CASH'})
    funding_unknown+=['ACCOUNT:'+key for key in sorted(owners-funding_accounts)]
    known_funding=None if funding_unknown else funding
    amount=Decimal(0) if room==0 else None if room is None or known_funding is None else min(room,known_funding)
    gross_result={'ceiling':None if unknown_caps else str(ceiling),'ceiling_upper_bound':str(ceiling),
        'ceiling_value_state':'UNKNOWN' if unknown_caps else 'KNOWN',
        'occupied':str(occupied),'confirmed_release_deducted':str(released),
        'overage_lower_bound':str(max(occupied-ceiling,Decimal(0))),
        'overage':str(overage) if overage is not None else None,'incremental_room':str(room) if room is not None else None,
        'available_authorized_incremental_funding':str(known_funding) if known_funding is not None else None,
        'incremental_capacity':str(amount) if amount is not None else None,'currency':currency,
        'value_state':'KNOWN' if amount is not None else 'UNKNOWN','unknown_required_caps':unknown_caps,
        'unknown_funding_buckets':funding_unknown,'cash_audit':cash_audit,'cap_audit':cap_audit,
        'ignored_duplicate_or_release_events':ignored,'account_occupancy':{k:str(v) for k,v in by_account.items()},
        'accounting_base':deepcopy(base),'total_ceiling_is_not_incremental_budget':True,
        'new_sell_or_forced_reallocation_authorized':False}
    net=data.get('upstream_net_capacity')
    if net is not None:
        receipt(net['receipt'],canonical,evaluated_at,'upstream_net_capacity.receipt')
        if (net.get('producer_contract')!=PROFILE or net.get('gross_input_digest')!=digest({k:v for k,v in data.items() if k!='upstream_net_capacity'})
            or amount is None or number(net['amount'],'net_capacity.amount')!=amount):
            fail('C_W7_LT_NET_CAPACITY_RECEIPT_REPLAY_MISMATCH','upstream_net_capacity')
        gross_result['upstream_net_capacity_replayed']=True
    return gross_result


def validate_confirmed_book(scope,canonical,evaluated_at):
    """A complete occupancy book must reconcile to the same Current view."""
    from work7.asset_framework import _bucket
    current=canonical['allocations']['current_allocation']['snapshot'];expected={}
    for row in current['positions']:
        kind=_bucket(row)
        if kind=='UNKNOWN':fail('C_W7_LT_CURRENT_ASSET_CLASS_UNKNOWN','current.positions.'+row['instrument_id'])
        if kind!='STOCK':continue
        money=row['portfolio_amount']
        if money['value_state']!='KNOWN' or money['currency']!=scope['budget_currency']:
            fail('C_W7_LT_CURRENT_STOCK_VALUE_UNKNOWN','current.positions.'+row['instrument_id'])
        expected[row['instrument_id']]=expected.get(row['instrument_id'],Decimal(0))+number(money['amount'],'current.stock.amount')
    actual={};events={}
    for row in scope['exposures']:
        if (row['kind']=='RELEASE' and row.get('release_confirmed') is True
            and row.get('release_state')=='CONFIRMED_POSITION_REDUCTION'
            and row['event_id'] not in scope['exposure_coverage']['confirmed_effects_already_applied']):
            fail('C_W7_LT_POSITION_REDUCTION_CURRENT_REFRESH_REQUIRED','exposures.'+row['event_id'])
        if row['kind']!='CONFIRMED_POSITION':continue
        if row['event_id'] in events:
            if events[row['event_id']]!=row:fail('C_W7_LT_CONFLICTING_ECONOMIC_EVENT','exposures')
            continue
        events[row['event_id']]=row
        value=number(row['amount'],'exposures.amount')*conversion(scope,canonical,evaluated_at,row['owner'])
        actual[row['asset_id']]=actual.get(row['asset_id'],Decimal(0))+value
    # Confirmed reductions reflected in Current must be reflected in this book;
    # a release of a still recorded reservation is a separate accounting event.
    for iid in set(expected)|set(actual):
        a=actual.get(iid,Decimal(0));b=expected.get(iid,Decimal(0))
        if abs(a-b)>max(a,b,Decimal(1))*Decimal('1e-12'):
            fail('C_W7_LT_CONFIRMED_POSITION_CURRENT_RECONCILIATION_REQUIRED','exposures.'+iid)


def integrate(work6_result,scope,weights):
    """Preserve Work6's effective view; never fit it into V70 bucket weights."""
    from work7 import asset_framework as original
    final=work6_result['final_target']['snapshot']
    approved={r['instrument_id']:r for r in scope['approved_long_term_target']['positions']}
    active=original._active_locks(work6_result)
    totals={k:Decimal(0) for k,_ in original.V70_BUCKET_FIELDS};items=[]
    for row in final['positions']:
        iid=row['instrument_id'];bucket=original._bucket(row)
        if bucket not in totals:fail('C_W7_LT_ASSET_CLASS_REQUIRED','final_target.positions.'+iid)
        w=number(original._weight(row),'final_target.weight.'+iid);totals[bucket]+=w
        items.append({'instrument_id':iid,'ticker':row.get('ticker'),'asset_type':row.get('asset_type'),'bucket':bucket,
            'work6_final_target_weight':float(w),'integrated_weight':float(w),
            'protected':iid in active,'allocation_rule':'PRESERVE_EXISTING_LONG_TERM_EFFECTIVE_VIEW',
            'source_reference_ids':deepcopy(row['source_reference_ids'])})
    if abs(sum(totals.values())-1)>Decimal('0.0000005'):
        fail('C_W7_LT_EFFECTIVE_TOTAL_REQUIRES_GOVERNANCE','integrated_asset_framework.total_weight')
    integrated={'value_state':'KNOWN','stock_weight':float(totals['STOCK']),
        'bond_weight':float(totals['BOND']),'v70_original_dry_powder_weight':float(totals['V70_ORIGINAL_DRY_POWDER']),
        'total_weight':float(sum(totals.values())),'instrument_targets':items,
        'work6_final_target_preserved':True,'reason':None}
    residual={'method':'PRESERVE_LONG_TERM_NO_V70_RESIDUAL_SCALING','buckets':[
        {'bucket':b,'effective_target_weight':str(totals[b]),'v70_total_ceiling_weight':str(weights[b]),
         'residual_scaling_performed':False} for b in totals]}
    return residual,integrated,[],False


def validate_result(result):
    """Version-aware serialized consumer; replay the exact scope arithmetic."""
    from jsonschema import Draft202012Validator
    verify_profile()
    schema=json.loads((BASE/'contracts_c7/85_Family_LongTerm_Work7_Result.schema.json').read_text())
    errors=list(Draft202012Validator(schema).iter_errors(result))
    if errors:fail('C_W7_LT_RESULT_SCHEMA_INVALID','result.'+'.'.join(map(str,errors[0].path)))
    evidence=result['family_scope_evidence'];scope=evidence['input_scope'];ci=evidence['canonical_input']
    if (result['identity']!=ci['identity'] or digest(scope)!=evidence['input_scope_digest']
        or scope['family_owner']!=evidence['family_owner']
        or scope['source_db_sha256']!=evidence['source_db_sha256']
        or scope['target_version']!=evidence['target_version']
        or scope['approved_long_term_target']!=evidence['approved_long_term_target']
        or scope['approved_target_digest']!=evidence['approved_target_digest']
        or scope['approved_long_term_target']['denominator']!=evidence['project_target_money_base']
        or scope['current_nav']!=evidence['current_weight_and_drift_base']
        or scope['total_stock_ceiling']!=evidence['same_run_v70_total_ceiling']):
        fail('C_W7_LT_SERIALIZED_SOURCE_BINDING_MISMATCH','result.family_scope_evidence')
    if capacity(scope,ci,result['created_at'])!=evidence['occupancy_and_capacity']:
        fail('C_W7_LT_SERIALIZED_CAPACITY_REPLAY_MISMATCH','result.occupancy_and_capacity')
    validate_confirmed_book(scope,ci,result['created_at'])
    if result['work7_snapshot_id']!='C-W7-'+digest({k:v for k,v in result.items() if k!='work7_snapshot_id'})[:32]:
        fail('C_W7_LT_RESULT_SNAPSHOT_DIGEST_MISMATCH','result.work7_snapshot_id')
    gate=result['pm_gate']
    if (gate['required'] is not True or gate['status']!='PENDING_ABC_PM_CONTRACT_SCHEMA_GATE'
        or gate['a78_a79_released'] is not False or gate['work8_released'] is not False):
        fail('C_W7_LT_PM_GATE_NOT_RELEASED','result.pm_gate')
    return deepcopy(evidence)
