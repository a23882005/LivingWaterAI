"""Project W1 confirmed policy facts; preserve native C8C9 risk/action separation."""
from copy import deepcopy
from family_boundary import require,timestamp
from runtime_loader import load_c_module


def effective(rows,confirmations,keys,at):
    eligible=[r for r in rows if timestamp(r['effective_at_utc'],'effective_at_utc')<=at]
    if not eligible:return None
    latest=max(eligible,key=lambda r:r['version_no'])
    confirmed=[c for c in confirmations if all(c.get(k)==latest.get(k) for k in keys) and c.get('version_no')==latest['version_no'] and timestamp(c['confirmed_at_utc'],'confirmed_at_utc')<=at]
    if latest.get('evidence_state')!='VERIFIED' or len(confirmed)!=1:return None
    return latest


def project_permissions(snapshot,*,account,evaluation_at):
    t=snapshot['tables'];at=timestamp(evaluation_at,'evaluation_at');client=snapshot['client_id']
    held={r['instrument_key'] for r in t['portfolio_position'] if r['account_key']==account and timestamp(r['as_of_utc'],'position.as_of')<=at}
    all_ids=held|{r['instrument_key'] for r in t['universe_membership']}
    output=[]
    for asset in sorted(all_ids):
        memberships={}
        for universe in ('PERSONAL','RESEARCH','EXCLUSION'):
            row=effective([r for r in t['universe_membership'] if r['instrument_key']==asset and r['universe_code']==universe],t['universe_confirmation'],('client_id','universe_code','instrument_key'),at)
            memberships[universe]=row['membership_code'] if row else 'UNKNOWN'
        rows=[r for r in t['permission_policy'] if r.get('account_key') in (None,account) and r.get('instrument_key') in (None,asset) and r['action_code']=='NEW_BUY']
        decisions=[]
        for key in sorted({r['policy_key'] for r in rows}):
            row=effective([r for r in rows if r['policy_key']==key],t['permission_confirmation'],('client_id','policy_key'),at)
            decisions.append(row['decision_code'] if row else 'UNKNOWN')
        permitted=bool(decisions) and all(d=='ALLOW' for d in decisions)
        holding=effective([r for r in t['holding_policy_proposal'] if r['account_key']==account and r['instrument_key']==asset],t['holding_policy_confirmation'],('client_id','account_key','instrument_key'),at)
        output.append({'client_id':client,'account_key':account,'instrument_key':asset,'existing_holding':asset in held,
            'membership':memberships,'permission_decisions':decisions,
            'new_buy_candidate':memberships['PERSONAL']=='IN' and memberships['EXCLUSION']=='OUT' and permitted,
            'holding_policy':holding['policy_code'] if holding else 'UNKNOWN',
            'retain_in_holdings_and_drift':asset in held})
    return output


def protect_existing(repo_path,*,native_request,projection,instrument_binding):
    require(instrument_binding.get('instrument_key')==projection['instrument_key'] and bool(instrument_binding.get('source_reference')),'INSTRUMENT_BINDING_REQUIRED','instrument_binding')
    w4=native_request['work4_v82_integration_result'];c7=native_request['c_work7_asset_framework_result']
    require(w4['asset_id']==instrument_binding.get('asset_id'),'INSTRUMENT_BINDING_MISMATCH','work4.asset_id')
    require(c7['identity'].get('client_id')==projection['client_id'],'PROTECTED_CLIENT_MISMATCH','c_work7.identity')
    require(instrument_binding.get('account_key')==projection['account_key'] and instrument_binding.get('native_owner')==w4['owner'],'PROTECTED_OWNER_MISMATCH','instrument_binding.native_owner')
    result=load_c_module(repo_path,8).protect_client_action(deepcopy(native_request))
    if projection['holding_policy']=='HOLD_AS_IS':
        require(result['protected_holding']['protection_applied'],'PROTECTED_MAPPING_MISMATCH','protected_holding')
    return {'native_work8':result,'permissions':deepcopy(projection),
        'risk_action':result['v82_signal_visibility']['raw_execution_action'],
        'client_action':result['client_action_protection']['client_facing_action'],'trade_action':'NO_TRADE'}
