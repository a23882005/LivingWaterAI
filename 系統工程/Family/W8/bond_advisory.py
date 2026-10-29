"""Compare V75's long-term map with the unchanged owner-approved baseline.

This proposal has its own native structural assessment. It never replaces a
confirmed target, establishes a current SGOV role balance, or authorizes buys.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import sys

from family_input import digest
from bond_engine import V75_PATH


def policy(request,context):
    value=context.get('bond_advisory_policy')
    if value is None:return None
    from bond_policy_audit import _read,_time
    if (value.get('schema_version')!='Family.W8.BondAdvisoryPolicy.v1'
        or value.get('client_id')!=request['client_id']
        or value.get('scope')!='BOND_RECOMMENDATIONS_ONLY'
        or value.get('allow_other_bond_recommendations') is not True
        or value.get('trade_authorization')!='NONE'):
        raise PermissionError('BOND_ADVISORY_POLICY_BINDING_MISMATCH')
    _read(value,_time(request['evaluation_at']))
    return {k:deepcopy(value[k]) for k in ('client_id','scope',
        'allow_other_bond_recommendations','source_reference','source_sha256',
        'source_available_at','trade_authorization')}


def candidates(root):
    runtime=Path(root).resolve()/V75_PATH
    if str(runtime) not in sys.path:sys.path.insert(0,str(runtime))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent!=runtime/'v75_runtime':
        raise PermissionError('BOND_ADVISORY_RUNTIME_MISMATCH')
    from v75_runtime.work3 import US_LISTED_ASSETS
    return sorted(US_LISTED_ASSETS)


def build(root,request,bond_source):
    audit=bond_source.get('policy_audit') or {}
    permission=audit.get('bond_advisory_policy')
    if permission is None:return None
    symbols=candidates(root)
    from v75_runtime.work3 import US_GENERIC_CORE_WEIGHTS,build_work3_state
    from v75_runtime.validation import validate_v75_run_input
    targets=bond_source['targets'];currency=request['owner']['currency']
    approved={aid:Decimal(row['money']['amount']) for aid,row in targets.items()}
    core={k:v for k,v in approved.items() if k in US_GENERIC_CORE_WEIGHTS}
    # Preserve non-core approvals; the generic template only redistributes its
    # own existing total. New non-core candidates receive no invented weight.
    with localcontext() as ctx:
        ctx.prec=80
        total=sum(core.values(),Decimal(0))
        proposed={**approved,**{aid:total*weight/100 for aid,weight in US_GENERIC_CORE_WEIGHTS.items()}}
    approved_rows=[targets[aid]['source_line']['target_amount'] for aid in core]
    source_currency={r.get('currency') for r in approved_rows}
    display_currency=next(iter(source_currency)) if len(source_currency)==1 else currency
    display_total=(sum((Decimal(r['amount']) for r in approved_rows),Decimal(0))
        if len(source_currency)==1 else total)
    denominator=request['confirmed_target']['payload']['draft'].get('denominator',{})
    base=(Decimal(denominator['amount']) if denominator.get('value_state')=='KNOWN'
        and denominator.get('currency')==display_currency else None)
    lines=[]
    for aid,weight in US_GENERIC_CORE_WEIGHTS.items():
        old=targets.get(aid,{}).get('source_line',{}).get('target_amount',{})
        prior=(Decimal(old['amount']) if old.get('value_state')=='KNOWN'
            and old.get('currency')==display_currency else Decimal(0) if aid not in targets else None)
        amount=display_total*weight/100
        lines.append({'asset_id':aid,'currency':display_currency,
            'approved_target_amount':str(prior) if prior is not None else None,
            'approved_target_present':aid in targets,
            'proposed_long_term_amount':str(amount),
            'difference_amount':str(amount-prior) if prior is not None else None,
            'proposed_portfolio_weight':str(amount/base) if base else None,
            'native_generic_bucket_weight_percent':str(weight),
            'reason_code':'SHORT_TREASURY_DEFENSIVE_CORE' if aid=='SGOV' else 'SHORT_INVESTMENT_GRADE_CREDIT_INCOME',
            'today_buy_amount':None,'today_buy_status':'REQUIRES_NATIVE_DEPLOYMENT_EVIDENCE'})
    out={'schema_version':'Family.W8.BondAdvisoryComparison.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],
        'scope':'UNAPPROVED_LONG_TERM_COMPARISON__NOT_TODAY_BUY_INSTRUCTIONS',
        'source_target_digest':digest(request['confirmed_target']),
        'rule_basis':deepcopy(audit.get('generic_bond_rule_basis')),
        'policy_source':deepcopy(permission),'candidate_universe':symbols,
        'approved_baseline_changed':False,'owner_decision_required_to_continue_analysis':False,
        'inferred_owner_prohibitions':[],'invented_exception_reason':None,
        'generic_bucket_total':{'amount':str(display_total),'currency':display_currency},
        'lines':lines,'call_trace':[],
        'today_deployment_status':'SOURCE_INCOMPLETE','trade_action':'NO_TRADE'}
    raw=bond_source.get('adapter_result',{}).get('v75_runtime_input')
    if raw is None:return out
    variant=deepcopy(raw)
    variant['target_bond_holdings']=[{'asset_id':aid,
        'target_amount':{'amount':format(amount,'f'),'currency':currency},
        'broker_account_id':request['owner']['account']} for aid,amount in sorted(proposed.items())]
    variant['authorized_universe']=sorted(set(raw['authorized_universe'])|set(symbols))
    out['native_input_delta']={k:deepcopy(variant[k]) for k in ('target_bond_holdings','authorized_universe')}
    out['native_input_digest']=digest(variant)
    out['native_authorization_scope']='ADVISORY_CANDIDATE_ASSESSMENT_ONLY__NOT_W1_NEW_BUY_PERMISSION'
    out['call_trace'].append('V75.validate_v75_run_input:ADVISORY_COMPARISON')
    checked=validate_v75_run_input(variant)
    out['native_validation']={'accepted':checked.accepted,
        'disposition':checked.disposition.value,'issues':[vars(i) for i in checked.issues]}
    if checked.model is not None:
        out['call_trace'].append('V75.build_work3_state:ADVISORY_COMPARISON')
        state=build_work3_state(checked.model)
        out['native_structural_state']=state.model_dump(mode='json')
        assessments={r['asset_id']:r for r in out['native_structural_state']['eligibility_assessments']}
        evidence=bond_source['predicate_observations']
        out['candidate_assessments']=[]
        markets={row['symbol']:row for row in bond_source['shared_inputs']['work3_input']
            ['shared_decision_context']['payload']['bond_market_observations'].values()}
        for symbol in symbols:
            observed=evidence.get(symbol,{})
            missing=[pid for pid in ('PRED-%03d'%n for n in range(1,11))
                if observed.get(pid,{}).get('original_result',{}).get('assessment_status')!='VALID'
                    or not observed.get(pid,{}).get('deployment_input_eligible')]
            out['candidate_assessments'].append({'asset_id':symbol,
                'native_eligibility':deepcopy(assessments[symbol]),
                'market_source_status':'OBSERVED' if observed else 'NOT_AVAILABLE',
                'market_date':markets.get(symbol,{}).get('observed_date'),
                'missing_predicates':missing,'today_buy_amount':None,
                'today_buy_status':('NOT_ELIGIBLE_FOR_NEW_ALLOCATION'
                    if assessments[symbol]['new_long_term_target_allowed'] is False
                    else 'DEPLOYMENT_EVIDENCE_REQUIRED'),
                'new_long_term_weight':next((r['proposed_portfolio_weight'] for r in lines if r['asset_id']==symbol),None),
                'source_scope':'ADVISORY_ONLY__NO_APPROVED_HOLDING_OR_TARGET_INFERRED'})
    out['runtime_work3_sha256']=sha256((Path(root)/V75_PATH/'v75_runtime/work3.py').read_bytes()).hexdigest()
    return out
