"""Versioned same-analysis envelope around an immutable upstream V70 result.

V70 owns the amounts and risk states. W5 only binds runs and preserves lineage.
The W3 macro feed alone does not provide these tactical amounts.
"""
from copy import deepcopy
from family_boundary import require, nonempty, timestamp
from family_input import digest
from tactical_budget import tactical_cap, TacticalBudgetError


def project_v70_context(original, analysis_run_id):
    require(isinstance(original,dict) and isinstance(original.get('payload'),dict),
            'V70_SOURCE_CONTEXT_REQUIRED','v70_source.context',status='DATA_UNAVAILABLE')
    source_run=original.get('run_id')
    require(nonempty(source_run) and original['payload'].get('run_id')==source_run,
            'V70_SOURCE_RUN_MISMATCH','v70_source.context.run_id')
    require(nonempty(analysis_run_id),'V70_ANALYSIS_RUN_REQUIRED','run_id')
    result=deepcopy(original)
    result['run_id']=analysis_run_id
    result['payload']['run_id']=analysis_run_id
    return result


def bind_v70_source(request,context):
    source=context.get('v70_source')
    require(isinstance(source,dict),'V70_TACTICAL_SOURCE_REQUIRED','trusted_context.v70_source',
            'V70','DATA_UNAVAILABLE')
    require(source.get('schema_version')=='Family.W5.V70Source.v1' and
            all(nonempty(source.get(k)) for k in ('producer','version','source_reference')),
            'V70_SOURCE_PROVENANCE_REQUIRED','trusted_context.v70_source')
    require(request.get('v70_source_digest')==digest(source),
            'V70_SOURCE_DIGEST_MISMATCH','request.v70_source_digest')
    require(source.get('client_id')==request['client_id'] and source.get('family_owner')==request['owner'],
            'V70_SOURCE_OWNER_MISMATCH','v70_source.family_owner')
    raw=source.get('context')
    projected=project_v70_context(raw,request['run_id'])
    require(raw.get('source_namespace')=='V70.RUNTIME_CONTEXT' and
            nonempty(raw.get('upstream_v70_snapshot_id')) and bool(raw.get('source_reference_ids')),
            'V70_SOURCE_LINEAGE_REQUIRED','v70_source.context')
    require(timestamp(raw.get('snapshot_as_of'),'v70_source.snapshot_as_of')<=
            timestamp(request['evaluation_at'],'evaluation_at'),
            'V70_FUTURE_SOURCE','v70_source.snapshot_as_of')
    bundle=request['native_bundle'];caps={}
    for branch in ('stock_request','bond_request'):
        handoff=bundle[branch]['work3_handoff']
        require(handoff['v70_runtime_context']==projected,
                'V70_NATIVE_PROJECTION_MISMATCH',branch+'.v70_runtime_context')
        for leg in ('equity','bond'):
            try:cap=tactical_cap(handoff,leg)
            except TacticalBudgetError as error:
                require(False,str(error),branch+'.v70_runtime_context','V70','DATA_UNAVAILABLE')
            caps[leg]={**cap,'amount':str(cap['amount']),'source_amount':str(cap['source_amount'])}
    bond=bundle['bond_request']['v75_source_context']['v70_snapshot']
    require(bond.get('payload')==projected['payload'] and
            bond.get('data_timestamp')==projected['snapshot_as_of'] and
            bond.get('source_lineage')==projected['source_reference_ids'],
            'V70_BOND_SNAPSHOT_MISMATCH','v75_source_context.v70_snapshot')
    return {'schema_version':'Family.W5.V70RunBinding.v1','source_run_id':raw['run_id'],
        'analysis_run_id':request['run_id'],'source_digest':digest(source),
        'original_context_digest':digest(raw),'projected_context_digest':digest(projected),
        'original_source':deepcopy(source),'projected_context':projected,'tactical_caps':caps,
        'scope':'EXPLICIT_TACTICAL_RESULT_RUN_BINDING','trade_action':'NO_TRADE'}
