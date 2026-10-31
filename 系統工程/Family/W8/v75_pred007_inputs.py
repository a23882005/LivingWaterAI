"""Bind the new USD policy to verified legacy S/D and official R/C sources."""
from copy import deepcopy
from datetime import datetime
from family_input import digest
from v75_pred007_source import evaluate,identity,time,EFFECTIVE_AT


def extend(pool,source,evaluation_at):
    if source is None:return pool
    if pool.get('formal_parameters',{}).get('parameter_version')!=identity()['base_predicate_version']:
        raise PermissionError('PRED007_BASE_FORMAL_PARAMETER_SOURCE_REQUIRED')
    from v75_etf_quality_inputs import daily_freshness
    old=pool['shared_metrics'].get('PRED-007',{});proof=pool['calculations'].get('PRED-007',{})
    srf=pool['source_proofs'].get('NYFED_REPO',{});day=proof.get('observed_date')
    s={'value':old.get('srf_usage_usd'),'units':'USD','observation_date':day,
        'retrieved_at':srf.get('available_at'),'source_ids':[srf['source_reference']] if srf else [],
        'freshness_verified':bool(day) and daily_freshness(day,evaluation_at)['state']=='FRESH',
        'legacy_definition':deepcopy(proof)}
    # A located supplier is not acquired market depth. Preserve absent D.
    d={'value':None,'units':'percentile_0_100','observation_date':None,'retrieved_at':None,
        'source_ids':[],'freshness_verified':False,'reason':'TREASURY_3Y_DEPTH_NOT_ACQUIRED'}
    metrics={'amendment_source':deepcopy(source),'legacy_candidates':{'S':s,'D':d}}
    model,assessment=evaluate(metrics,evaluation_at)
    pool['usd_pred007_amendment']={'rule_identity':identity(),'metrics':metrics,
        'assessment':assessment,'native_version_mapping':{
            'outer_version':identity()['effective_predicate_version'],
            'frozen_transport_version':identity()['base_predicate_version'],
            'mandatory_amendment_lineage':model.source_lineage[0],
            'base_transport_version_is_not_complete_rule_identity':True},
        'source_digest':digest({'source':source,'legacy_candidates':metrics['legacy_candidates']})}
    pool['formal_parameters']['usd_pred007_active_rule']=identity()
    pool['formal_parameters']['retired_usd_fields']={
        'SOFR_OIS_bps':'RETIRED_UNDEFINED_NOT_AN_ALIAS','FRA_OIS_bps':'RETIRED_UNDEFINED_NOT_AN_ALIAS'}
    clocks=[pool['available_at'],source['ruleset']['ingested_at']]
    for signal in assessment['signals'].values():
        retrieved=signal.get('retrieved_at')
        clocks.extend(retrieved.values() if isinstance(retrieved,dict) else [retrieved] if retrieved else [])
    if assessment.get('calendar'):clocks.append(assessment['calendar']['retrieved_at'])
    pool['available_at']=max(clocks,key=lambda x:datetime.fromisoformat(x.replace('Z','+00:00')))
    return pool


def slot(pool,asset,evaluation_at,previous):
    amendment=pool.get('usd_pred007_amendment')
    currency=(pool.get('qualified_bond_markets',{}).get(asset,{}) or
        pool.get('issuer_observations',{}).get(asset,{})).get('currency')
    if currency!='USD':return None
    if amendment is None:
        if time(evaluation_at)<time(EFFECTIVE_AT):return None
        from v75_runtime.models import PredicateResult
        result=PredicateResult(predicate_id='PRED-007',predicate_version=identity()['base_predicate_version'],
            aggregate_state=None,sub_states=[],assessment_status='REVIEW_REQUIRED',as_of=time(evaluation_at),
            source_lineage=['AMENDMENT_SOURCE_REQUIRED:'+identity()['effective_predicate_version']],
            input_freshness_state='UNKNOWN',reason_codes=['PRED007_AMENDMENT_SOURCE_REQUIRED'],
            required_input_missing=['pred007_amendment_source'])
        return {'metrics':{},'original_result':result.model_dump(mode='json'),
            'rule_identity':{**identity(),'source_binding_status':'MISSING_AMENDMENT_SOURCE'},
            'input_coverage':'AMENDMENT_NOT_LOADED','unprovided_inputs':['pred007_amendment_source'],
            'source_pool_digest':digest(pool),'source_available_at':pool['available_at'],
            'input_freshness_verified':False,'deployment_input_eligible':False,
            'previous_observation':deepcopy(previous)}
    model,assessment=evaluate(amendment['metrics'],evaluation_at)
    return {'metrics':deepcopy(amendment['metrics']),'original_result':model.model_dump(mode='json'),
        'rule_identity':deepcopy(amendment['rule_identity']),'amendment_assessment':assessment,
        'native_version_mapping':deepcopy(amendment['native_version_mapping']),
        'input_coverage':'PARTIAL_RAW_METRICS' if assessment['missing_candidates'] else 'COMPLETE_RAW_METRICS',
        'unprovided_inputs':[r['candidate']+':'+str(r['reason']) for r in assessment['missing_candidates']],
        'source_pool_digest':digest(pool),'source_available_at':pool['available_at'],
        'input_freshness_verified':True,'deployment_input_eligible':model.assessment_status.value=='VALID',
        'freshness_scope':'AVAILABLE_CANDIDATES_UNDER_AUTHORIZED_COMPOSITE_POLICY',
        'original_default_freshness_is_not_attestation':True,
        'original_result_as_of_basis':'LATEST_OBSERVATION_COMPOSITE__PER_SIGNAL_DATES_PRESERVED',
        'previous_observation':deepcopy(previous)}
