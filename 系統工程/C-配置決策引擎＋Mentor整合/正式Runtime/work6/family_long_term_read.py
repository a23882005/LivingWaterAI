"""Read an existing approved long-term target; never create tactical CONFIRM.

Work5 still supplies C calculations. Work6's effective view uses Current NAV
for protection/weight drift; the immutable approved money base is separately
carried to Project Target consumers. No residual scaling is authorized here.
"""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json
from jsonschema import Draft202012Validator
from work6 import adjustment_loop as original
from work5.core_engine import run_configuration_engine
from work7.family_long_term import (PROFILE,WORK6_VERSION,APPROVAL_SHA256,
    validate_scope,digest,number,time,fail)


def run_existing_long_term(canonical_input,*,family_scope,adjustment_request,
        benchmark_path,binding_path,input_schema_path,output_schema_path,
        work6_request_schema_path,work6_output_schema_path,evaluated_at):
    scope=validate_scope(family_scope,canonical_input,evaluated_at)
    from work7.family_long_term import validate_confirmed_book
    validate_confirmed_book(scope,canonical_input,evaluated_at)
    request=deepcopy(adjustment_request);ci=deepcopy(canonical_input)
    errors=original._schema_issues(request,original._load_json(work6_request_schema_path),'adjustment_request')
    if errors:raise original.AdjustmentLoopValidationError(errors)
    if (request['confirmation']['action']!='KEEP_PENDING'
        or request['requested_change_types']!=['REVIEW_ONLY']
        or request['weight_overrides'] or request['preference_decisions']):
        fail('C_W6_LT_READ_EXISTING_IS_NOT_TACTICAL_CONFIRM','adjustment_request')
    if scope['protection_coverage']['complete'] is not True:
        fail('C_W6_LT_PROTECTION_SOURCE_INCOMPLETE','family_scope.protection_coverage')
    from work7.family_long_term import receipt
    receipt(scope['protection_coverage'],ci,evaluated_at,'family_scope.protection_coverage')
    current=deepcopy(ci['allocations']['current_allocation']['snapshot'])
    approved=deepcopy(scope['approved_long_term_target'])
    if approved['stage']!='FINAL_TARGET':
        fail('C_W6_LT_APPROVED_TARGET_STAGE_REQUIRED','approved_long_term_target.stage')
    states={r['instrument_id']:deepcopy(r) for r in scope['preference_locks']}
    if len(states)!=len(scope['preference_locks']):
        fail('C_W6_LT_PREFERENCE_LOCK_DUPLICATED','family_scope.preference_locks')
    source_ids={r['source_id'] for r in ci['source_references']}
    for state in states.values():
        refs=state['preference_source_ids']+state['unlock_source_ids']
        if set(refs)-source_ids:
            fail('C_W6_LT_PREFERENCE_SOURCE_MISSING','family_scope.preference_locks')
        if state['client_preference_locked']:
            if not state['preference_confirmed_at'] or not state['preference_source_ids']:
                fail('C_W6_LT_PREFERENCE_CONFIRMATION_REQUIRED','family_scope.preference_locks')
            if time(state['preference_confirmed_at'],'preference.confirmed_at')>time(evaluated_at,'evaluated_at'):
                fail('C_W6_LT_PREFERENCE_NOT_AVAILABLE','family_scope.preference_locks')
    active=original._active_locks(states);cur=original._index_positions(current)
    effective=deepcopy(approved)
    # This derived C analysis view is explicitly not the Project Target money
    # view. The approval id/time/signer remain the original read-only identity.
    effective['denominator']=deepcopy(current['denominator'])
    effective['as_of']=evaluated_at
    nav=number(current['denominator']['amount'],'current_nav.amount')
    issues=[];rows={r['instrument_id']:r for r in effective['positions']}
    for iid,lock in active.items():
        observed=cur.get(iid)
        if observed is None or not original._is_individual_company_stock(observed):
            fail('C_W6_LT_PROTECTED_CURRENT_INDIVIDUAL_REQUIRED','preference_locks.'+iid)
        cw=original._weight(observed)
        if cw is None or abs(Decimal(str(cw))-Decimal(str(lock['current_weight'])))>Decimal('0.0000005'):
            fail('C_W6_LT_LOCK_CURRENT_WEIGHT_MISMATCH','preference_locks.'+iid)
        if iid not in rows:
            rows[iid]=deepcopy(observed);effective['positions'].append(rows[iid])
        rows[iid]['weight']=deepcopy(observed['weight'])
    for row in effective['positions']:
        weight=original._weight(row)
        if weight is None:fail('C_W6_LT_EFFECTIVE_WEIGHT_UNKNOWN','final_target.'+row['instrument_id'])
        row['portfolio_amount']=original._money_from_template(current['denominator'],
            float(nav*Decimal(str(weight))),current['denominator']['currency'],evaluated_at,
            original._uniq(row['source_reference_ids']+current['source_reference_ids']))
    total=sum((Decimal(str(original._weight(r))) for r in effective['positions']),Decimal(0))
    effective['declared_total_weight']=original._metric_from_template(approved['declared_total_weight'],float(total),evaluated_at,
        original._uniq(approved['source_reference_ids']+current['source_reference_ids']))
    if abs(total-1)>Decimal('0.0000005'):
        issues.append(original._issue('C_W6_LT_PROTECTED_TARGET_GOVERNANCE_REQUIRED','BLOCKING',
            'final_target.declared_total_weight','Protected Current differs from approved target; no residual redistribution or new confirmation is authorized.',blocking=True))
    ci['allocations']['final_target']=original._slot(effective)
    ci['decision_phase']='FINAL_TARGET_CONFIRMED'
    # Work5 remains the only producer of C's financial/radar context. Calling
    # it does not call _confirm_final or sign/approve this derived view.
    common=dict(benchmark_path=benchmark_path,binding_path=binding_path,input_schema_path=input_schema_path,
        output_schema_path=output_schema_path,evaluated_at=evaluated_at)
    current_engine=run_configuration_engine(ci,allocation_slot='current_allocation',**common)
    final_engine=None if issues else run_configuration_engine(ci,allocation_slot='final_target',**common)
    if final_engine is not None and final_engine.get('formal_output_eligibility',{}).get('eligible') is not True:
        issues.append(original._issue('C_W6_LT_ORIGINAL_C_ENGINE_INELIGIBLE','BLOCKING','final_target_engine_result',
            'Original C Work5 did not qualify the existing-target view.',blocking=True))
    drift=original._drift_snapshot(current,effective,states,evaluated_at)
    radar=original._radar_snapshot(request,evaluated_at)
    radar_errors=original.validate_radar_display_contract(radar)
    if radar_errors:fail('C_W6_LT_RADAR_CONTRACT_FAIL','radar_snapshot')
    blocked=any(r['blocking'] for r in issues)
    status='BLOCKED' if blocked else 'EXISTING_LONG_TERM_TARGET_READ'
    empty=original._none_slot('READ_EXISTING_APPROVAL creates no tactical proposal or confirmation.')
    evidence={'profile':PROFILE,'approval_contract_sha256':APPROVAL_SHA256,
        'input_scope_digest':digest(scope),'approved_long_term_target':approved,'approved_target_digest':digest(approved),
        'current_allocation':current,'current_engine_result':current_engine,
        'project_target_money_base':deepcopy(approved['denominator']),
        'current_weight_and_drift_base':deepcopy(current['denominator']),
        'effective_view_role':'CURRENT_NAV_PROJECTION_FOR_PROTECTION_AND_WEIGHT_DRIFT_ONLY',
        'effective_view_digest':digest(effective),'new_confirmation_created':False,
        'tactical_target_approved':False,'project_target_money_rebased_to_NAV':False}
    out={'contract_name':'LivingWaterAI.C.Work6.MentorAdjustmentResult','contract_version':WORK6_VERSION,
        'identity':deepcopy(ci['identity']),'work6_snapshot_id':'C-W6-'+digest({'version':WORK6_VERSION,'canonical':canonical_input,'scope':scope,'at':evaluated_at})[:32],
        'parent_work6_snapshot_id':None,'loop_status':status,'route':{'decision':'BLOCKED' if blocked else 'C_ONLY','reason_codes':[r['code'] for r in issues]},
        'draft_allocation':deepcopy(empty),'previous_proposal':deepcopy(empty),'current_proposal':deepcopy(empty),
        'final_target':original._slot(effective),'confirmation_status':'CONFIRMED',
        'preference_locks':[states[k] for k in sorted(states)],'drift_snapshot':drift,'radar_snapshot':radar,
        'adjustment_history':[],'proposal_engine_result':None,'final_target_engine_result':final_engine,
        'mentor_result_contract':{'display_status':status,'next_route':'BLOCKED' if blocked else 'C_ONLY',
            'human_readable_summary':'讀取既有長期核准；本輪總額度另行限制新增。未建立新的戰術確認。',
            'report_engine_must_not_recompute_final_target':True,'risk_warning_is_not_sell_instruction':True,
            'protected_holding_actions':[{'instrument_id':iid,'action':'HOLD_PROTECTED','risk_disclosure_separate_from_sell_action':True,
                'note':'Existing verified Preference Lock retained.'} for iid in sorted(active)],'route_reason_codes':[r['code'] for r in issues]},
        'family_scope_evidence':evidence,'issues':issues,'created_at':evaluated_at}
    schema=json.loads(Path(work6_output_schema_path).read_text())
    original._validate_output_or_raise(out,schema)
    return out
