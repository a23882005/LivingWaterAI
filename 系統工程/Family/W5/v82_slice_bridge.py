"""Family-owned source validation and CAS persistence for native daily cycles.

The operator supplies an existing planning ledger. No missing ledger is
created during analysis and no broker reservation/order is issued here.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys
from family_input import digest
from family_boundary import require,timestamp


def bind(repo_path,request,context):
    from stock_engine import V82_PATH
    path=Path(repo_path).resolve()/V82_PATH
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    import livingwater_v82_runtime as runtime
    require(Path(runtime.__file__).resolve().parent==path/'livingwater_v82_runtime',
        'V82_APPROVED_RUNTIME_ORIGIN_MISMATCH','approved_v10_context')
    from livingwater_v82_runtime.approved_profiles import SPEC_SHA256,VERSION
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore,validate_cycle
    source=request['native_bundle']['stock_evidence'].get('approved_v10_context')
    if source is None:
        require(context['native_binding']['data_provenance']=='SYNTHETIC'
            or timestamp(request['evaluation_at'],'evaluation_at')<timestamp('2026-10-28T04:27:00+08:00','effective_at'),
            'V82_APPROVED_CONTEXT_REQUIRED','native_bundle.stock_evidence.approved_v10_context',status='DATA_UNAVAILABLE')
        return None  # Explicit historical construction compatibility.
    identity=source.get('identity') or {}
    require(source.get('spec_sha256')==SPEC_SHA256 and
        all(identity.get(k)==request.get(k) for k in ('client_id','run_id','owner','evaluation_at')) and
        identity.get('asset_id')==request['native_bundle']['stock_request']['asset_context']['asset']['asset_id'] and
        identity.get('snapshot_id')==request['client_snapshot']['payload']['source_sha256'],
        'V82_APPROVED_CONTEXT_IDENTITY_MISMATCH','approved_v10_context.identity')
    require(source.get('native_owner')==context['native_binding']['native_owner'],
        'V82_APPROVED_NATIVE_OWNER_BINDING_MISMATCH','approved_v10_context.native_owner')
    descriptor=source.get('supplemental_source_descriptor')
    if descriptor is not None:
        expected=(context.get('v82_approved_sources') or {}).get(identity['asset_id'])
        require(expected==descriptor,'V82_APPROVED_OPERATOR_SOURCE_MISMATCH','approved_v10_context.source')
        raw=Path(descriptor['local_path']).read_bytes()
        require(sha256(raw).hexdigest()==descriptor['sha256'],'V82_APPROVED_SOURCE_HASH_MISMATCH','approved_v10_context.source')
        facts=json.loads(raw.decode('utf-8-sig'))
        require(facts.get('owner')==request['owner'] and facts.get('asset_id')==identity['asset_id']
            and facts.get('source_db_sha256')==identity['snapshot_id']
            and timestamp(facts['available_at'],'available_at')<=timestamp(request['evaluation_at'],'evaluation_at'),
            'V82_APPROVED_SOURCE_SCOPE_OR_TIME_MISMATCH','approved_v10_context.source')
    snapshot=source.get('cycle_snapshot') or {};cycle=snapshot.get('cycle')
    if cycle is not None:
        validate_cycle(cycle)
        require(cycle['profile_version']==VERSION and cycle['owner']==request['owner'] and cycle['asset_id']==identity['asset_id'],
            'V82_CYCLE_OWNER_PROFILE_MISMATCH','approved_v10_context.cycle_snapshot')
        if context['native_binding']['data_provenance']!='SYNTHETIC':
            session=source.get('session') or {}
            require(all(session.get(k) for k in ('calendar_id','calendar_version','planning_start_at','planning_end_at')),
                'V82_CYCLE_SESSION_CALENDAR_REQUIRED','approved_v10_context.session',status='DATA_UNAVAILABLE')
            open_now=(timestamp(session['planning_start_at'],'planning_start_at')<=timestamp(request['evaluation_at'],'evaluation_at')
                <timestamp(session['planning_end_at'],'planning_end_at'))
            require(session.get('open_for_planning') is open_now,
                'V82_CYCLE_SESSION_STATE_MISMATCH','approved_v10_context.session')
        path=snapshot.get('ledger_path')
        if path is None:
            require(context['native_binding']['data_provenance']=='SYNTHETIC',
                'V82_DURABLE_CYCLE_SOURCE_REQUIRED','approved_v10_context.cycle_snapshot',status='DATA_UNAVAILABLE')
        else:
            current=CycleLedgerStore(path).get(cycle['slice_cycle_id'])
            proposed=(snapshot.get('status')=='PROPOSED' and current is None and cycle['revision']==0
                and cycle['intents']=={} and cycle['events']=={} and
                (source.get('planning_ledger_source') or {}).get('planning_write_authorized') is True)
            require(current==cycle or proposed or _own_commit_replay(cycle,current,digest(request),
                request['native_bundle']['stock_evidence'].get('order_intent_id')),
                'V82_CYCLE_LEDGER_CHANGED_REBUILD_REQUIRED','approved_v10_context.cycle_snapshot',status='DATA_UNAVAILABLE')
    return deepcopy(source)


def _own_commit_replay(before,current,request_digest,intent_id):
    if before is None or current is None or not intent_id:return False
    eid='LOCAL_PLAN:'+request_digest;item=current.get('intents',{}).get(intent_id)
    if not item or item['state']!='PLANNED' or item['filled_amount']!='0':return False
    receipt=item.get('receipt') or {}
    if (receipt.get('source_reference')!='FAMILY_READONLY_RECOMMENDATION:'+request_digest
        or receipt.get('source_hash')!=digest({'request_digest':request_digest,'amount':item['remaining_amount'],'intent_id':intent_id})):
        return False
    expected=deepcopy(before);expected['intents'][intent_id]=deepcopy(item)
    expected['events'][eid]=current.get('events',{}).get(eid);expected['revision']+=1
    return expected==current


def ensure_cycle(source, analysis, *, gap, permission, exposure_reconciled, execution_inputs_qualified):
    """Read fixed G0/B0 or propose the first cycle for atomic final commitment.

    Called only by the operator source producer, after qualification. Session
    and authority come from its verified supplementary source, not menu payload.
    """
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore,cycle_id,open_cycle
    out=deepcopy(source);authority=out.get('planning_ledger_source') or {};session=out.get('session') or {};identity=out['identity']
    if not authority or authority.get('planning_write_authorized') is not True:return out
    if authority.get('owner')!=identity['owner'] or not authority.get('source_reference'):
        raise PermissionError('V82_PLANNING_LEDGER_AUTHORITY_MISMATCH')
    if not session.get('session_id') or not session.get('exchange') or type(session.get('open_for_planning')) is not bool:
        out['cycle_snapshot']={'status':'QUALIFIED_SESSION_CALENDAR_REQUIRED','cycle':None,
            'ledger_path':authority['local_path'],'source_reference':authority['source_reference']}
        return out
    store=CycleLedgerStore(authority['local_path'])
    key=cycle_id(owner=identity['owner'],session_id=session['session_id'],exchange=session['exchange'],asset_id=identity['asset_id'])
    cycle=store.get(key)
    proposed=False
    if cycle is None and execution_inputs_qualified is True:
        cycle=open_cycle(owner=identity['owner'],session_id=session['session_id'],exchange=session['exchange'],
            asset_id=identity['asset_id'],opened_at=identity['evaluation_at'],gap=gap,
            speed_result=analysis['speed'],permission=permission,trend_allowed=analysis['trend_timing']['truth'],
            exposure_reconciled=exposure_reconciled,session_open=session.get('open_for_planning'))
        if cycle is not None:
            proposed=True
    out['cycle_snapshot']={'status':'PROPOSED' if proposed else 'VERIFIED','cycle':cycle,'ledger_path':str(store.path),
        'source_reference':authority['source_reference'],'cycle_digest':digest(cycle)}
    return out


def commit_local_plan(source,calculation,*,request_digest):
    """Explicit local planning commitment after all Family safeguards pass.

    A broker CASH reservation is never created. The source producer must renew
    the next request's ledger snapshot; an old snapshot cannot reset its budget.
    """
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore,update_intent
    snapshot=source.get('cycle_snapshot') or {};authority=source.get('planning_ledger_source') or {}
    plan=calculation.get('execution');cycle=snapshot.get('cycle')
    if plan is None or plan.execution_amount is None or plan.execution_amount<=0:return None
    if authority.get('planning_write_authorized') is not True or not snapshot.get('ledger_path') or cycle is None:
        raise PermissionError('V82_LOCAL_PLAN_LEDGER_AUTHORITY_REQUIRED')
    if authority.get('owner')!=source['identity']['owner']:raise PermissionError('V82_LOCAL_PLAN_OWNER_MISMATCH')
    store=CycleLedgerStore(snapshot['ledger_path']);current=store.get(cycle['slice_cycle_id'])
    iid=calculation['evidence']['order_intent_id'];at=source['identity']['evaluation_at']
    if _own_commit_replay(cycle,current,request_digest,iid):
        return {'slice_cycle_id':cycle['slice_cycle_id'],'before_digest':digest(cycle),'after_digest':digest(current),
            'intent_id':iid,'planning_commitment':str(plan.execution_amount),'already_committed':True,
            'new_commitment':'0','broker_cash_reserved':False,'trade_action':'NO_TRADE'}
    proposed=snapshot.get('status')=='PROPOSED' and current is None and cycle['revision']==0 and not cycle['intents']
    if current!=cycle and not proposed:raise PermissionError('V82_CYCLE_LEDGER_CHANGED_REBUILD_REQUIRED')
    receipt={'owner':source['identity']['owner'],'asset_id':source['identity']['asset_id'],
        'source_reference':'FAMILY_READONLY_RECOMMENDATION:'+request_digest,
        'source_hash':digest({'request_digest':request_digest,'amount':str(plan.execution_amount),'intent_id':iid}),
        'as_of':at,'available_at':at,'broker_submission_performed':False,
        'planning_pool_id':source['shared_allocation_request']['pool_id'],
        'funding_bucket_id':next(r['bucket_id'] for r in source['shared_allocation_request']['slices'] if r['asset_id']==source['identity']['asset_id'])}
    updated=update_intent(cycle,event_id='LOCAL_PLAN:'+request_digest,intent_id=iid,state='PLANNED',
        filled_amount='0',remaining_amount=str(plan.execution_amount),receipt=receipt,evaluation_at=at,
        speed_result=calculation['approved_v10_analysis']['speed'],permission=True,
        trend_allowed=calculation['approved_v10_analysis']['trend_timing']['truth'],
        session_id=source['session']['session_id'],session_open=source['session']['open_for_planning'])
    def validate_shared(others,pending):
        from funding_guard import check_aggregate
        from decimal import Decimal
        group=source['shared_allocation_request'];pool=group['pool_id'];owner=source['identity']['owner'];by_bucket={}
        for item in [*others,pending]:
            if item['owner']!=owner:continue
            for intent in item['intents'].values():
                proof=intent.get('receipt') or {}
                if proof.get('planning_pool_id')!=pool or intent['state'] not in ('PLANNED','SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'):continue
                # Only a bound broker cash source can attest that its net cash
                # has already deducted this reservation. Unknown is not release.
                if intent['state']!='PLANNED':
                    if proof.get('reservation_cash_source_digest')==source.get('cash_source_digest'):continue
                    raise PermissionError('V82_BROKER_RESERVATION_CASH_BINDING_REQUIRED')
                bid=proof.get('funding_bucket_id');asset=item['asset_id']
                amounts=by_bucket.setdefault(bid,{})
                amounts[asset]=amounts.get(asset,Decimal(0))+Decimal(intent['remaining_amount'])
        total=Decimal(0)
        for bucket in group['buckets']:
            values=by_bucket.pop(bucket['bucket_id'],{});cash=bucket['available_authorized_notional_cash']
            normalized={};bucket_owner={**owner,'currency':bucket['currency']}
            for asset,value in values.items():
                row=next((r for r in group['slices'] if r['asset_id']==asset),None)
                if row is None:raise PermissionError('V82_EXISTING_PLAN_OUTSIDE_SHARED_ALLOCATION_UNIVERSE')
                normalized[asset]=value*Decimal(row['fx_to_bucket'])
                total+=value*Decimal(row['fx_to_bucket'])*Decimal(row['fx_bucket_to_budget'])
            check_aggregate(owner=bucket_owner,run_id=source['identity']['run_id'],available=cash,equity_budget=cash,bond_budget='0',
                claims=[{'claim_id':'PLANNING:'+a,'owner':bucket_owner,'run_id':source['identity']['run_id'],'asset_class':'EQUITY','amount':str(v)} for a,v in normalized.items()])
        if by_bucket:raise PermissionError('V82_EXISTING_PLAN_FUNDING_BUCKET_UNRESOLVED')
        check_aggregate(owner=owner,run_id=source['identity']['run_id'],available=group['remaining_tactical_room'],
            equity_budget=group['remaining_tactical_room'],bond_budget='0',claims=[{
                'claim_id':'ALL_LOCAL_PLANS','owner':owner,'run_id':source['identity']['run_id'],'asset_class':'EQUITY','amount':str(total)}])
    store.save(updated,expected_revision=None if proposed else cycle['revision'],validate_shared=validate_shared)
    return {'slice_cycle_id':cycle['slice_cycle_id'],'before_digest':digest(cycle),'after_digest':digest(updated),
        'intent_id':iid,'planning_commitment':str(plan.execution_amount),'broker_cash_reserved':False,
        'already_committed':False,'new_commitment':str(plan.execution_amount),'trade_action':'NO_TRADE'}


def finalize(request,result):
    """Commit only after the original full Family/Work9/funding result passed."""
    from decimal import Decimal
    from types import SimpleNamespace
    source=request['native_bundle']['stock_evidence'].get('approved_v10_context')
    native=result.get('native_result') or {};local=native.get('stock_local_plan')
    if source is None or not local:return None
    amount=local.get('execution_amount')
    if amount is None or Decimal(amount)<=0:return None
    if result.get('status')!='OK' or not native.get('unified_result') or native.get('trade_action')!='NO_TRADE':
        raise PermissionError('V82_LOCAL_PLAN_FULL_FAMILY_VALIDATION_REQUIRED')
    actual=native['stock_result']['canonical_v82_output']['canonical_analysis']['execution_amount']['value']
    if not isinstance(actual,dict) or Decimal(str(actual['amount']))!=Decimal(amount):
        raise PermissionError('V82_LOCAL_PLAN_CANONICAL_AMOUNT_MISMATCH')
    return commit_local_plan(source,{'execution':SimpleNamespace(execution_amount=Decimal(amount)),
        'evidence':request['native_bundle']['stock_evidence'],
        'approved_v10_analysis':local['approved_v10_analysis']},request_digest=digest(request))
