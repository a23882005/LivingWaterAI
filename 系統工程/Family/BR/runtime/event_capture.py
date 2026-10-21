"""Capture W5 analysis events without converting proposals into executions.

The caller must first validate/execute the original W5 runner. This captures
the exact input/output with a verified content graph, not a new auth layer.
"""
from copy import deepcopy
from replay import ReplayError, digest, instant, verify_lineage, differences


def _node(payload, parents=()):
    body={'payload':deepcopy(payload),'parents':list(parents)}
    return {**body,'sha256':digest(body)}


def capture(request, context, result, *, source_lock_sha256):
    client=request['client_id']
    if not client or context.get('client_id') != client or request['owner'].get('client_id') != client:
        raise ReplayError('CAPTURE_CLIENT_MISMATCH')
    if request.get('trade_authorization') != 'NONE' or request.get('analysis_permission') != 'ANALYZE_ONLY':
        raise ReplayError('CAPTURE_ANALYSIS_ONLY')
    if context.get('analysis_permission') != 'ANALYZE_ONLY':
        raise ReplayError('CAPTURE_PERMISSION_MISMATCH')
    if context.get('expected_versions') != request['expected_versions']:
        raise ReplayError('CAPTURE_VERSION_MISMATCH')
    if not isinstance(source_lock_sha256,str) or len(source_lock_sha256)!=64 or any(c not in '0123456789abcdef' for c in source_lock_sha256):
        raise ReplayError('CAPTURE_SOURCE_LOCK_REQUIRED')
    instant(request['evaluation_at'])
    for key in ('run_id','request_id'):
        if result.get(key) != request[key]:
            raise ReplayError('CAPTURE_RESULT_BINDING')
    if result.get('client_id',client) != client:
        raise ReplayError('CAPTURE_RESULT_CLIENT')
    if result.get('status')=='OK':
        if result.get('client_id') != client or result.get('owner') != request['owner'] or result.get('trade_action')!='NO_TRADE':
            raise ReplayError('CAPTURE_RESULT_OWNER_OR_TRADE')
    elif result.get('status') not in ('BLOCKED','DATA_UNAVAILABLE','ERROR'):
        raise ReplayError('CAPTURE_RESULT_STATUS')
    if result.get('trade_action','NO_TRADE')!='NO_TRADE':
        raise ReplayError('CAPTURE_RESULT_OWNER_OR_TRADE')
    snapshot=request['client_snapshot']['payload']
    if snapshot.get('client_id') != client:
        raise ReplayError('CAPTURE_SNAPSHOT_CLIENT')
    tables=snapshot['tables']
    for rows in tables.values():
        if not isinstance(rows,list):raise ReplayError('CAPTURE_TABLE_SHAPE')
        for row in rows:
            if 'client_id' in row and row['client_id']!=client:
                raise ReplayError('CAPTURE_TABLE_CLIENT')
    accounts=[r['account_key'] for r in tables['portfolio_account']]
    if len(accounts)!=len(set(accounts)):
        raise ReplayError('CAPTURE_DUPLICATE_ACCOUNT')
    for row in tables['portfolio_position']:
        if row.get('account_key') not in accounts:
            raise ReplayError('CAPTURE_POSITION_ACCOUNT')
    # Preserve every account, original decimal string, zero and unknown field.
    # Analysis-only means actual portfolio stays the same even if advice says BUY.
    portfolio={k:deepcopy(v) for k,v in tables.items()}
    body={'schema_version':'Family.BR.CapturedEvent.v1','client_id':client,
        'event_id':digest({'client_id':client,'request_id':request['request_id'],
                         'request':request,'context':context}),
        'request_id':request['request_id'],'run_id':request['run_id'],
        'event_time':request['evaluation_at'],'owner':deepcopy(request['owner']),
        'expected_versions':deepcopy(request['expected_versions']),
        'source_lock_sha256':source_lock_sha256,'request_sha256':digest(request),
        'context_sha256':digest(context),'result_sha256':digest(result),
        'portfolio_before':portfolio,'portfolio_after':deepcopy(portfolio),
        'portfolio_transition':'UNCHANGED_ANALYSIS_ONLY','executed_trades':[],
        'result_status':result['status'],'issue_codes':deepcopy(result.get('issue_codes',[])),
        'data_provenance':context.get('native_binding',{}).get('data_provenance','UNKNOWN'),
        'historical_pit_verified':False,'trade_authorization':'NONE'}
    nodes={}
    for prefix,data in (('request',request),('context',context)):
        parents=[]
        for i,key in enumerate(sorted(data)):
            name=f'{prefix}.field.{i}'
            nodes[name]=_node({'field':key,'value':data[key]})
            parents.append(name)
        nodes[prefix]=_node(data,parents)
    nodes['result']=_node(result,['request','context'])
    nodes['event']=_node(body,['result'])
    verify_lineage(nodes,'event')
    return {**body,'lineage':nodes,'lineage_root':'event'}


def verify_capture(event, request, context, result, *, source_lock_sha256):
    verify_lineage(event['lineage'],event['lineage_root'])
    expected=capture(request,context,result,source_lock_sha256=source_lock_sha256)
    diff=differences(expected,event)
    if diff:raise ReplayError('CAPTURE_BINDING_MISMATCH:'+diff[0]['path'])
    return {'status':'PASS','lineage_nodes':len(event['lineage']),
        'accounts':len(event['portfolio_before']['portfolio_account']),
        'positions':len(event['portfolio_before']['portfolio_position']),
        'event_sha256':digest(event),'portfolio_unchanged':True}
