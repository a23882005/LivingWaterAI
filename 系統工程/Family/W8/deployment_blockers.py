"""Locate original contract/source blockers without changing their decisions."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path


V70_FIELDS={'STOCK':'stock_tactical_weight','BOND':'bond_tactical_weight',
            'V70_ORIGINAL_DRY_POWDER':'v70_original_dry_powder_weight'}


def _v75_contract(analysis,root):
    bond=analysis.get('native_bond_source') or {}
    state=bond.get('structural_state') or {}
    attempt=bond.get('native_runtime_attempt') or {}
    rows=[]
    for symbol,predicates in bond.get('predicate_observations',{}).items():
        for pid,slot in predicates.items():
            original=slot.get('original_result') or {}
            if slot.get('input_freshness_verified') is True and original.get('assessment_status')=='VALID':continue
            rows.append({'asset_id':symbol,'predicate_id':pid,
                'source_field':'native_bond_source.predicate_observations.'+symbol+'.'+pid,
                'input_freshness_verified':slot.get('input_freshness_verified'),
                'original_assessment_status':original.get('assessment_status'),
                'original_aggregate_state':original.get('aggregate_state'),
                'metrics':deepcopy(slot.get('metrics',{})),
                'native_reason_codes':deepcopy(original.get('reason_codes',[])),
                'missing_or_unqualified_input_is_wait':False})
    result={'rule_basis':deepcopy((bond.get('policy_audit') or {}).get('generic_bond_rule_basis')),
        'target_compatibility':deepcopy(bond.get('target_compatibility')),
        'structural_evaluation_state':state.get('evaluation_state'),
        'structural_issues':deepcopy(state.get('issues',[])),
        'native_attempt_status':attempt.get('status'),
        'predicate_input_limitations':rows,
        'native_wait_requires_valid_predicates':True,
        'missing_predicates_may_be_rewritten_as_wait':False,
        'full_cutover_required_for_read_only_formal_hard_wait_review':False,
        'original_cutover_gate_preserved':True,
        'undeployed_contribution_is_sgov_buy_authorization':False,
        'defensive_sgov_is_stock_cash':False,'approved_target_overwritten':False}
    if root is not None:
        from bond_advisory import candidates
        candidates(root)  # Verify the original module's origin before import.
        from bond_engine import V75_PATH
        from v75_runtime.constants import RULE_SOT_VERSION,PREDICATE_VERSION
        from v75_runtime.work3 import US_GENERIC_CORE_WEIGHTS
        result.update(runtime_rule_version=RULE_SOT_VERSION,predicate_version=PREDICATE_VERSION,
            native_us_long_term_weights_percent={k:str(v) for k,v in US_GENERIC_CORE_WEIGHTS.items()})
        references=[]
        for filename,function,clause in (
            ('work3.py','build_work3_state','US_GENERIC_CORE_TARGET_RATIO_MISMATCH'),
            ('work4.py','_predicate_map','Step10 must fail-closed before invocation'),
            ('work6.py','evaluate_runtime_ready','Work5FinalClassification.HARD_WAIT')):
            path=V75_PATH/'v75_runtime'/filename;raw=(Path(root)/path).read_bytes()
            lines=raw.decode('utf-8').splitlines()
            references.append({'path':str(path),'sha256':sha256(raw).hexdigest(),'function':function,
                'line':next((i for i,s in enumerate(lines,1) if clause in s),None),'clause':clause})
        result['original_contract_locations']=references
    return result


def build(analysis,work6,c7,root=None):
    contract=[]
    for index,row in enumerate(c7.get('residual_allocation',{}).get('buckets',[])):
        bucket=row['bucket']
        related=[r for r in c7.get('issues',[]) if r.get('field_path')=='asset_framework.'+bucket]
        if not related:continue
        contract.append({'category':'ORIGINAL_CONTRACT_RECONFIRMATION','bucket':bucket,
            'native_issues':deepcopy(related),
            'confirmed_weight':row.get('work6_final_target_bucket_weight'),
            'same_run_v70_weight':row.get('target_weight'),
            'confirmed_source_field':'work6_result.final_target.snapshot.positions[*].weight.value',
            'v70_source_field':'canonical_input.v70_asset_framework.'+V70_FIELDS[bucket]+'.value',
            'native_comparison_field':'c7_result.residual_allocation.buckets['+str(index)+']',
            'next_step':'Return the same-run V70 framework to Work6 proposal/reconfirmation; retain the long-term approval separately.',
            'external_NBBO_yield_ROC_dependency':False,'automatic_reapproval_allowed':False})
    engine=[];seen=set()
    for stage in ('proposal_engine_result','final_target_engine_result'):
        result=work6.get(stage) or {}
        for i,issue in enumerate(result.get('issues',[])):
            if not issue.get('blocking'):continue
            key=(issue.get('code'),issue.get('field_path'),issue.get('message'))
            if key in seen:continue
            seen.add(key)
            path=issue.get('field_path') or ''
            category=('BENCHMARK_UNIVERSE_COVERAGE' if path.endswith('.ticker') else
                'REFERENCE_CURRENCY_BINDING' if path.endswith('.base_currency') else
                'PORTFOLIO_DENOMINATOR_QUALIFICATION' if path.startswith('allocation.denominator') else
                'ORIGINAL_CONFIGURATION_ENGINE_GATE')
            engine.append({'category':category,'native_issue':deepcopy(issue),
                'source_field':'work6_result.'+stage+'.issues['+str(i)+']',
                'dependent_on_three_requested_market_datasets':False})
    native=[]
    positions={r['instrument_id']:r for r in analysis.get('analysis_result',{}).get('positions',[])}
    for iid,item in (analysis.get('native_funding_advice') or {}).get('items',{}).items():
        if item.get('status')=='CASH_TRIAL_ADVICE_COMPUTED':continue
        row=positions.get(iid,{})
        codes={r.get('code') for r in item.get('issues',[])}
        conclusion=row.get('formal_conclusion') or {}
        native.append({'instrument_id':iid,'symbol':item.get('symbol'),'native_status':item.get('status'),
            'category':'ENGINEERING_PRODUCER_NOT_CONNECTED' if any(c and ('PRODUCER' in c) for c in codes)
                else 'BOND_CANONICAL_DEPENDENCIES' if item.get('status')=='BOND_DELEGATED_TO_V75'
                else 'ORIGINAL_NATIVE_INPUT_UNRESOLVED',
            'source_field':'native_funding_advice.items.'+iid,
            'issues':deepcopy(item.get('issues',[])),
            'mode_source_field':'analysis_result.positions['+str(list(positions).index(iid))+'].formal_conclusion',
            'native_selector_connected':bool(conclusion.get('call_trace')),
            'selected_mode':conclusion.get('selected_mode'),
            'formal_stage':conclusion.get('formal_stage'),
            'canonical_target_rate':conclusion.get('canonical_target_rate'),
            'required_unknown_fields':deepcopy(conclusion.get('stage_required_unknown_fields',[])),
            'market_predicates':deepcopy(conclusion.get('market_predicates',{})),
            'unresolved_mode_dependencies':{k:deepcopy(v.get('unresolved_dependencies',[]))
                for k,v in row.get('current_analysis',{}).get('four_modes',{}).items()
                if v.get('unresolved_dependencies')},
            'available_calculations_retained':bool(row.get('current_analysis'))})
    gaps=[{'id':'SIP_NBBO_20_COMPLETE_SESSIONS','affected_fields':[
        'SGOV.PRED-010.median_20d_bid_ask_spread_pct','SPSB.PRED-010.median_20d_bid_ask_spread_pct'],
        'unaffected':['stock valuation','stock technical observations','C7 bucket comparison'],
        'status':'MISSING_LEGITIMATE_HISTORY_OR_EXPORT'},
        {'id':'SPSB_FIVE_YEAR_WEEKLY_YIELDS','affected_fields':['SPSB.PRED-008'],
        'unaffected':['SGOV independent sources','stock observations','C7 target identity'],
        'status':'SPARSE_80_OBSERVATIONS_NOT_COMPLETE_WEEKLY_SERIES'},
        {'id':'SPSB_NINE_PAYMENT_COMPONENTS','affected_fields':['SPSB.PRED-010.distribution_quality_state'],
        'unaffected':['SGOV issuer decomposition','known SPSB distribution amounts','QII classification'],
        'status':'COMPONENTS_UNKNOWN__WHOLE_TTM_ROC_UNKNOWN'}]
    return {'schema_version':'Family.W8.DeploymentBlockers.v1',
        'contract_reconfirmation':contract,'configuration_engine_inputs':engine,
        'v75_original_contract':_v75_contract(analysis,root),
        'native_decision_inputs':native,'separate_market_data_gaps':gaps,
        'support_inquiries':deepcopy((analysis.get('v75_macro_inputs') or {}).get('official_reply_status')),
        'available_analysis_not_globally_blocked_by_data_gaps':True,
        'new_target_or_approval_created':False,'trade_action':'NO_TRADE'}
