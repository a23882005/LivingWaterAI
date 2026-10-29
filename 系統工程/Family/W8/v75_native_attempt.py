"""Run original V75 from qualified component inputs, preserving native holds."""
from copy import deepcopy
from family_input import digest
from bond_engine import run_bond_engine


def build(root,request,source):
    adapter=source['adapter_request'];checked=source['native_validation']
    state=source.get('structural_state') or {};evidence={};excluded={}
    if checked['accepted'] and state.get('work3_complete'):
        shared=source['shared_inputs']['work3_input']['shared_decision_context']
        observed=adapter['v75_source_context']['market_snapshot']['data_timestamp']
        for item in state['per_asset_inputs']:
            symbol=item['asset_id'];predicates=source['predicate_observations'].get(symbol,{})
            metrics={};unqualified=[]
            for n in range(1,11):
                pid='PRED-%03d'%n;slot=predicates.get(pid,{})
                if slot.get('input_freshness_verified') is True:
                    metrics[pid]=deepcopy(slot.get('metrics',{}))
                else:
                    metrics[pid]={};unqualified.append(pid)
            excluded[symbol]=unqualified
            evidence[symbol]={'asset_id':symbol,'run_id':request['run_id'],
                'broker_account_id':request['owner']['account'],'currency':request['owner']['currency'],
                'producer':'Family.W8.QualifiedV75ComponentInputs','version':'1.0',
                'source_reference':'SHARED-BOND-CONTEXT:'+digest(shared),
                'as_of':observed,'available_at':observed,'metrics':metrics}
            # Terminal decision inputs have no fallback. They are required
            # only after every original predicate is valid and qualified.
            if not unqualified and all(predicates[pid]['original_result']['assessment_status']=='VALID' for pid in metrics):
                return {'status':'TERMINAL_POLICY_SOURCE_REQUIRED','canonical':None,
                    'required_inputs':['effective_duration_years','asset_credit_class',
                        'existing_policy.current_position_quantity_and_risk_facts'],
                    'call_trace':[],'trade_action':'NO_TRADE'}
    try:
        result=run_bond_engine(root,adapter,evidence)
    except (ValueError,KeyError,TypeError) as error:
        return {'status':'NATIVE_INPUT_REJECTED','canonical':None,
            'code':getattr(error,'code',type(error).__name__),'message':str(error),
            'call_trace':['W5.run_bond_engine:original_input_rejected'],'trade_action':'NO_TRADE'}
    return {**result,'source_binding':{'client_id':request['client_id'],'run_id':request['run_id'],
        'owner':deepcopy(request['owner']),'source_db_sha256':source['source_db_sha256'],
        'source_input_digest':digest(adapter),'normalized_evidence_digest':digest(evidence)},
        'unqualified_predicates_not_substituted':excluded,
        'complete_predicate_inputs_asserted':False,'trade_action':'NO_TRADE'}
