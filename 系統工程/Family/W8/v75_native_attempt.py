"""Run original V75 from qualified component inputs, preserving native holds."""
from copy import deepcopy
from family_input import digest
from bond_engine import run_bond_engine


def normalized_evidence(request,source):
    """Emit qualified leaves even if the approved target fails Work3's template.

    The physical SGOV source establishes quantity; only its explicit accounting
    role establishes the bond quantity. Unobserved risk facts remain None.
    """
    adapter=source['adapter_request'];evidence={};excluded={}
    if source['native_validation']['accepted']:
        shared=source['shared_inputs']['work3_input']['shared_decision_context']
        observed=adapter['v75_source_context']['market_snapshot']['data_timestamp']
        pool=shared['payload'].get('v75_macro_inputs') or {}
        symbols={r['asset_id'] for r in adapter['v75_source_context']['target_bond_holdings']}
        symbols.update(r['asset_id'] for r in adapter['v75_source_context']['existing_bond_holdings'])
        for symbol in sorted(symbols):
            predicates=source['predicate_observations'].get(symbol,{})
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
            facts=evidence[symbol];issuer=pool.get('issuer_observations',{}).get(symbol,{})
            duration=issuer.get('facts',{}).get('effective_duration')
            if duration:
                from v75_etf_quality_inputs import daily_freshness
                if duration['unit']=='YEARS' and daily_freshness(duration['observed_date'],request['evaluation_at'])['state']=='FRESH':
                    facts['effective_duration_years']=duration['value']
                    facts['duration_source']={'source_reference':issuer['source_reference'],
                        'source_sha256':issuer['source_sha256'],**deepcopy(duration)}
            # Product mandate classification, never an inferred credit rating.
            from v75_issuer_facts import URLS
            classes={'SGOV':'TREASURY','SPSB':'CORPORATE'}
            if symbol in classes and issuer.get('source_reference')==URLS[symbol] and issuer.get('source_sha256'):
                facts['asset_credit_class']=classes[symbol]
                facts['credit_class_source']={'basis':'IDENTITY_CHECKED_OFFICIAL_PRODUCT_MANDATE__NOT_CREDIT_RATING',
                    'source_reference':issuer['source_reference'],'source_sha256':issuer['source_sha256']}
            physical=source.get('physical_holdings',{}).get(symbol)
            quantity=physical['quantity'] if physical else '0'
            if symbol=='SGOV':
                roles=source.get('sgov_role_source') or {}
                if roles.get('status')=='SOURCE_DERIVED_ACCOUNTING' and physical:
                    from decimal import Decimal
                    bond=Decimal(roles['roles']['sgov_bond_bucket_amount']['amount'])
                    value=Decimal(physical['valuation']['amount'])
                    if bond not in (0,value):
                        facts['policy_missing_fields']=['mixed_sgov_role_share_quantities'];continue
                    facts['sgov_role_binding']={**deepcopy(roles['roles']),
                        'physical_quantity':quantity,'physical_value':physical['valuation']['amount'],
                        'source_digest':roles['digest']}
                    quantity=quantity if bond>0 else '0'
                else:
                    facts['policy_missing_fields']=['sgov_role_source'];continue
            facts['existing_policy']={'current_position_quantity':quantity,
                'capital_gain_harvest_eligible':None,'rebound_reduction_eligible':None,
                'investment_logic_invalidated':None}
            facts['policy_source_scope']='SOURCE_LOGICAL_POSITION; RISK_FLAGS_UNOBSERVED_NOT_FALSE'
    return evidence,excluded


def build(root,request,source):
    adapter=source['adapter_request']
    evidence,excluded=normalized_evidence(request,source)
    state=source.get('structural_state') or {}
    if state.get('work3_complete'):
        required=[]
        for symbol,facts in evidence.items():
            predicates=source['predicate_observations'].get(symbol,{})
            if not excluded[symbol] and all(predicates.get(pid,{}).get('original_result',{}).get('assessment_status')=='VALID' for pid in facts['metrics']):
                required += [symbol+'.'+field for field in ('effective_duration_years','asset_credit_class','existing_policy') if field not in facts]
        if required:
            return {'status':'TERMINAL_POLICY_SOURCE_REQUIRED','canonical':None,
                'required_inputs':required,'normalized_evidence':evidence,
                'call_trace':[],'trade_action':'NO_TRADE'}
    try:
        result=run_bond_engine(root,adapter,evidence)
    except (ValueError,KeyError,TypeError) as error:
        return {'status':'NATIVE_INPUT_REJECTED','canonical':None,
            'code':getattr(error,'code',type(error).__name__),'message':str(error),
            'call_trace':['W5.run_bond_engine:original_input_rejected'],'trade_action':'NO_TRADE'}
    return {**result,'normalized_evidence':evidence,'source_binding':{'client_id':request['client_id'],'run_id':request['run_id'],
        'owner':deepcopy(request['owner']),'source_db_sha256':source['source_db_sha256'],
        'source_input_digest':digest(adapter),'normalized_evidence_digest':digest(evidence)},
        'unqualified_predicates_not_substituted':excluded,
        'complete_predicate_inputs_asserted':False,'trade_action':'NO_TRADE'}
