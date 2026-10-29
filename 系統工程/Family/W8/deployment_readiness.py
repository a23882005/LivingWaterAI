"""Original C7 bucket preflight and specific, separately classified blockers.

A preflight projection is never a confirmed Work6 result or a C7 source. It
cannot satisfy assemble_native_input or authorize a replacement allocation.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from c7_engine import load_original_configuration_module


def c7_bucket_preflight(root,request,analysis,context):
    original=load_original_configuration_module(root,'work7.asset_framework')
    from native_asset_source import classification,FORMAL_CLASSES
    typed={r['symbol']:r['native_product_identity'] for r in analysis['analysis_result']['positions']}
    rows=[];mapping=[]
    for source in request['confirmed_target']['payload']['draft']['target_lines']:
        row=deepcopy(source);kind=row.get('asset_type');symbol=row['ticker'];basis='ORIGINAL_APPROVED_TARGET'
        if original._bucket(row)=='UNKNOWN':
            product=typed.get(symbol,{})
            route=product.get('engine_route','')
            if route.startswith('V82_'):
                kind='equity exposure';basis='SOURCE_BOUND_NATIVE_EQUITY_IDENTITY'
            elif route=='V75_PREDICATES':
                kind='bond exposure';basis='SOURCE_BOUND_V75_PRODUCT_IDENTITY'
            elif context.get('sgov_role_classification_source'):
                formal=classification(symbol,context['sgov_role_classification_source'],
                    context.get('sgov_role_product_sources',{}).get(symbol))
                if formal['primary_class'] in FORMAL_CLASSES:
                    # An explicit equity class identifies the C7 asset bucket;
                    # it establishes neither a fund wrapper nor a native grade.
                    kind='equity exposure';basis='FORMAL_V82_EXPLICIT_EQUITY_CLASS__NOT_WRAPPER_OR_GRADE'
        row['asset_type']=kind;weight=row['weight']
        if weight.get('value_state')!='KNOWN' or isinstance(weight.get('value'),bool):
            raise ValueError('C7_PREFLIGHT_APPROVED_WEIGHT_REQUIRED')
        number=Decimal(str(weight['value']))
        if not number.is_finite() or not 0<=number<=1:raise ValueError('C7_PREFLIGHT_WEIGHT_DOMAIN')
        row['weight']={'value_state':'KNOWN','value':float(number)}
        row['source_reference_ids']=['APPROVED_TARGET:'+digest(request['confirmed_target'])]
        rows.append(row);mapping.append({'instrument_id':row['instrument_id'],'symbol':symbol,
            'original_asset_type':source.get('asset_type'),'bucket':original._bucket(row),'basis':basis})
    tactical=next((r['current_analysis'].get('v70_tactical_budget')
        for r in analysis['analysis_result']['positions'] if r['current_analysis'].get('v70_tactical_budget')),None)
    if tactical is None:raise ValueError('C7_PREFLIGHT_SAME_RUN_V70_REQUIRED')
    allocation=tactical['allocation']
    weights={bucket:float(Decimal(str(allocation[key]))/100) for bucket,key in
        [('STOCK','sTot'),('BOND','bTot'),('V70_ORIGINAL_DRY_POWDER','cTot')]}
    # Only the bucket invariant is exercised. No protection/confirmation
    # statement is implied by this minimal, non-dispatchable projection.
    probe={'final_target':{'snapshot':{'positions':rows}},'preference_locks':[]}
    residual,framework,issues,reroute=original._build_residual_allocation(probe,weights)
    return {'schema_version':'Family.W8.C7BucketPreflight.v1',
        'status':'ORIGINAL_BUCKET_MISMATCH' if reroute else
            'ORIGINAL_BUCKET_INPUT_INCOMPLETE' if any(i['blocking'] for i in issues) else 'BUCKET_INVARIANT_PASSED',
        'client_id':request['client_id'],'run_id':request['run_id'],
        'scope':'BUCKET_INVARIANT_ONLY__NO_WORK6_CONFIRMATION_OR_PROTECTED_HOLDING_CLAIM',
        'source_target_digest':digest(request['confirmed_target']),
        'v70_component_digest':digest(tactical),'mapping':mapping,
        'bucket_comparison':deepcopy(residual['buckets']),'native_issues':issues,
        'native_integrated_framework_state':framework['value_state'],
        'full_c7_source_produced':False,'approval_unchanged':True,
        'long_term_approval_and_tactical_recommendation_kept_separate':True,
        'call_trace':['C.Work7._build_residual_allocation:bucket_invariant_preflight'],
        'trade_action':'NO_TRADE'}


def completion_gaps(analysis,missing):
    bond=analysis.get('native_bond_source') or {};observed=bond.get('predicate_observations') or {}
    spec=[];data=[]
    amended=any(v.get('PRED-007',{}).get('rule_identity',{}).get('amendment_id')=='V75-PRED007-20261029-01' for v in observed.values())
    if not amended and any(v.get('PRED-007',{}).get('original_result',{}).get('assessment_status')!='VALID' for v in observed.values()):
        spec=[{'field':field,'reason':'Formal v1.0.3 has bps thresholds but no complete comparison definition'}
            for field in ('SOFR_OIS.sofr_leg_definition','SOFR_OIS.ois_leg_definition',
                'SOFR_OIS.comparison_tenor','FRA_OIS.forward_start_period','FRA_OIS.contract_tenor',
                'FRA_OIS.reference_rate_and_index_tenor','FRA_OIS.matched_ois_tenor')]
        if any('treasury_market_depth_percentile_3y' not in v.get('PRED-007',{}).get('metrics',{}) for v in observed.values()):
            data.append({'field':'PRED-007.treasury_market_depth_percentile_3y',
                'reason':'BrokerTec three-year raw market depth and usage entitlement not acquired; yields are not depth'})
    if amended and any(any(x['candidate']=='D' for x in v.get('PRED-007',{}).get('amendment_assessment',{}).get('missing_candidates',[])) for v in observed.values()):
        data.append({'field':'PRED-007.treasury_market_depth_percentile_3y',
            'reason':'Not acquired; authorized 3/4 VALID aggregation may proceed with PARTIAL_COVERAGE; not a standalone blocker'})
    if 'SPSB' in observed and observed['SPSB'].get('PRED-008',{}).get('original_result',{}).get('assessment_status')!='VALID':
        data.append({'field':'SPSB.PRED-008.five_year_weekly_YTM_or_SEC_yield',
            'reason':'Same-basis weekly history not acquired; current yield/NAV/distribution yield cannot substitute'})
    for symbol,quality in (analysis.get('v75_macro_inputs') or {}).get('etf_quality_assessments',{}).items():
        for field in quality.get('unprovided_inputs',[]):
            data.append({'field':symbol+'.PRED-010.'+field,
                'reason':('20 trading-day NBBO history not acquired; 30 calendar-day issuer median is a separate observation'
                    if field=='median_20d_bid_ask_spread_pct' else
                    'Complete issuer breakdown not supplied; missing ROC is not zero; tax finality is separate'
                    if 'roc' in field else 'Required source coverage/observation not established')})
    engineering=[{'field':field,'owner_input_required':False,
        'reason':'Full same-run Work6 engine lineage, Current Allocation/Drift/protection and C7 framework have not been produced; existing approval is retained'}
        for field in missing]
    return {'specification_undefined':spec,'data_not_acquired':data,'engineering_not_connected':engineering,
        'quality_missing_values_not_normalized_to_zero':True,'trade_action':'NO_TRADE'}
