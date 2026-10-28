"""Project a complete existing approval through the original C Work6 lookup.

This resolves the existing allocation baseline, not a new optimized proposal.
It never changes the W2 approval, source document, DB or trade authorization.
"""
from copy import deepcopy
from decimal import Decimal
import re
from family_input import digest


def produce(root,request,context,policy,symbols):
    symbols=sorted(set(symbols))
    out={'schema_version':'Family.W8.Loop2TargetProjection.v1','status':'NOT_RUN',
        'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'policy':deepcopy(policy),'requested_symbols':symbols,'targets':{},'issues':[],
        'call_trace':[],'scope':'EXISTING_APPROVED_FULL_ALLOCATION__NOT_NEW_OPTIMIZATION',
        'full_loop2_complete':False,'trade_action':'NO_TRADE'}
    if policy is None:return out
    if request.get('confirmed_target',{}).get('source_kind')=='OFFICIAL_W1_CONFIRMED_ALLOCATION':
        out['status']='SUPERSEDED_BY_CURRENT_OFFICIAL_W1_TARGET'
        return out
    if (policy.get('schema_version')!='Family.W8.CompleteTargetProjectionPolicy.v1'
        or policy.get('client_id')!=request['client_id']
        or policy.get('scope')!='EXISTING_CONFIRMED_FULL_ALLOCATION_ONLY'
        or not policy.get('source_reference')):
        raise PermissionError('LOOP2_TARGET_PROJECTION_POLICY_SCOPE_MISMATCH')
    target=request.get('confirmed_target',{});payload=target.get('payload',{});draft=payload.get('draft',{})
    proof=context.get('approved_document_target_source') or {}
    if (target.get('source_kind')!='EXISTING_APPROVED_DOCUMENT'
        or payload.get('status')!='APPROVED_DOCUMENT_VIEW'
        or draft.get('identity',{}).get('client_id')!=request['client_id']
        or proof.get('client_id')!=request['client_id'] or proof.get('target_view_digest')!=digest(target)):
        raise PermissionError('LOOP2_TARGET_APPROVAL_SOURCE_MISMATCH')
    lines=draft.get('target_lines',[]);weight_view={'positions':[]}
    for row in lines:
        weight=row.get('weight') or {};ticker=row.get('ticker')
        if not ticker or weight.get('value_state')!='KNOWN' or isinstance(weight.get('value'),bool):
            out['status']='INCOMPLETE_SOURCE';out['issues']=[{'field_path':'confirmed_target.target_lines.weight_or_ticker'}];return out
        value=Decimal(str(weight.get('value')))
        if not value.is_finite() or value<0 or value>1:
            out['status']='INCOMPLETE_SOURCE';out['issues']=[{'field_path':'confirmed_target.target_lines.weight'}];return out
        weight_view['positions'].append({'instrument_id':row['instrument_id'],'ticker':ticker,
            'weight':deepcopy(weight)})
    from c7_engine import load_original_configuration_module
    c6=load_original_configuration_module(root,'work6.adjustment_loop')
    out['call_trace'].append('C.Work6._validate_snapshot_weights')
    issues=c6._validate_snapshot_weights(weight_view,'confirmed_target.target_lines')
    if not lines or issues:
        out['status']='INCOMPLETE_SOURCE';out['issues']=issues or [{'field_path':'confirmed_target.target_lines'}];return out
    denom=draft.get('denominator') or {}
    out['source_target_digest']=digest(target);out['native_weight_input']=weight_view
    for symbol in symbols:
        same=[r for r in lines if r.get('ticker')==symbol]
        if same:continue # Existing explicit targets and multiple-role boundaries retain their own mapper.
        # A symbol mentioned in a grouped source row is unresolved, not absent.
        pattern=r'(?<![A-Z0-9])'+re.escape(symbol)+r'(?![A-Z0-9])'
        if any(re.search(pattern,r.get('original_document_row','')) for r in lines):
            out['issues'].append({'field_path':'target.'+symbol,'code':'GROUPED_TARGET_MAPPING_REQUIRED'});continue
        # Use a guaranteed-absent ID only after proving absence by ticker in
        # this same complete approval. Do not mistake an opaque source ID for
        # a different security's ticker.
        iid='FAMILY-C6-ABSENT-TICKER:'+symbol
        if any(r['instrument_id']==iid for r in lines):raise ValueError('TARGET_PROJECTION_ID_COLLISION')
        weight=c6.final_target_weight(weight_view,iid)
        if weight!=0:raise ValueError('ORIGINAL_C6_ABSENT_TARGET_NOT_ZERO')
        amount=(str(Decimal(str(weight))*Decimal(str(denom['amount'])))
            if denom.get('value_state')=='KNOWN' and denom.get('currency') else None)
        out['targets'][symbol]={'weight':{'value_state':'KNOWN','value':str(weight)},
            'target_amount':{'value_state':'KNOWN' if amount is not None else 'UNKNOWN',
                'amount':amount,'currency':denom.get('currency'),
                'basis':'ORIGINAL_C6_COMPLETE_APPROVED_TARGET_LOOKUP',
                'source_target_digest':out['source_target_digest'],
                'source_reference':policy['source_reference']},
            'original_instrument_id':iid,'basis':'ORIGINAL_C6_COMPLETE_APPROVED_TARGET_LOOKUP',
            'not_an_immediate_sell_instruction':True}
        out['call_trace'].append('C.Work6.final_target_weight:'+symbol)
    out['status']='SOURCE_BASELINE_PROJECTED';out['output_digest']=digest(out['targets'])
    return out


def validate(root,request,context,report):
    recorded=report.get('loop2_target_projection')
    if recorded is None:return
    expected=produce(root,request,context,recorded.get('policy'),recorded['requested_symbols'])
    if expected!=recorded:raise PermissionError('LOOP2_TARGET_PROJECTION_REPLAY_MISMATCH')
