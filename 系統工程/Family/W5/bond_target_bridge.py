"""Bind explicit W2 per-instrument targets; preserve C7 client facts separately.

No allocation splitting, FX, or client-action priority is invented here.
"""
from copy import deepcopy
from family_boundary import require, one
from family_input import digest
from target_source_bridge import number


def bind_bond_targets(request, prepared, binding):
    bundle=request['native_bundle']; framework=bundle['asset_framework']
    lines=request['confirmed_target']['payload']['draft']['target_lines']
    source=bundle['bond_request']['v75_source_context']
    native=source['target_bond_holdings']; mappings=binding['bond_instruments']
    require(len(native)==len(mappings) and {r['asset_id'] for r in native}==set(mappings),
            'BOND_TARGET_COVERAGE_MISMATCH','v75_source_context.target_bond_holdings')
    results={};used=set()
    for asset,mapping in mappings.items():
        key=mapping.get('target_instrument_id')
        require(isinstance(key,str) and key.strip() and key not in used,
                'BOND_TARGET_ID_MAPPING_REQUIRED','native_binding.bond_instruments.'+asset,
                status='DATA_UNAVAILABLE');used.add(key)
        line=one([r for r in lines if r['instrument_id']==key],'bond.target_lines.'+asset)
        require(line.get('ticker')==asset,'BOND_TARGET_TICKER_MISMATCH','target_lines.'+key)
        money=line.get('target_amount',{})
        require(money.get('value_state')=='KNOWN','BOND_TARGET_AMOUNT_UNAVAILABLE',
                'target_lines.'+key,'W2','DATA_UNAVAILABLE')
        require(money.get('currency')==request['owner']['currency'],
                'BOND_TARGET_FX_SOURCE_REQUIRED','target_lines.'+key,status='DATA_UNAVAILABLE')
        row=one([r for r in native if r['asset_id']==asset],'bond.native_target.'+asset)
        require(row['broker_account_id']==binding['native_owner']['account'] and
                row['target_amount']['currency']==money['currency'],
                'BOND_TARGET_OWNER_MISMATCH','bond.native_target.'+asset)
        require(number(money.get('amount'),'W2.target_amount')==number(row['target_amount']['amount'],'V75.target_amount'),
                'BOND_TARGET_AMOUNT_MISMATCH','bond.native_target.'+asset)
        policy=prepared.payload['family_sources']['bond'][asset]['policy']
        require(policy['holding_policy'] in ('HOLD_AS_IS','ADJUSTABLE'),
                'BOND_HOLDING_POLICY_UNAVAILABLE','bond.policy.'+asset,'W1','DATA_UNAVAILABLE')
        target=one([r for r in framework['integrated_asset_framework']['instrument_targets']
                    if r['instrument_id']==key],'bond.C7.target.'+asset)
        drift=one([r for r in framework['drift_snapshot']['items'] if r['instrument_id']==key],
                  'bond.C7.drift.'+asset)
        protected=policy['holding_policy']=='HOLD_AS_IS'
        require(target['protected'] is protected and drift['protected'] is protected,
                'BOND_PROTECTED_FLAG_MISMATCH','bond.C7.'+asset)
        require(isinstance(drift.get('client_facing_action'),str) and bool(drift['client_facing_action'].strip()),
                'BOND_C7_CLIENT_ACTION_REQUIRED','bond.C7.drift.'+asset,status='DATA_UNAVAILABLE')
        results[asset]={'asset_id':asset,'target_instrument_id':key,'target_line':deepcopy(line),
            'native_target':deepcopy(row),'policy':deepcopy(policy),'c7_drift':deepcopy(drift),
            'new_buy_candidate':policy['new_buy_candidate'],
            'client_action_resolution':'SOURCE_FACTS_ONLY_PENDING_CROSS_ENGINE_PRIORITY'}
    result={'schema_version':'Family.W5.BondTargetSource.v1','client_id':request['client_id'],
        'run_id':request['run_id'],'owner':deepcopy(binding['native_owner']),
        'currency':request['owner']['currency'],'target_digest':digest(request['confirmed_target']),
        'framework_digest':digest(framework),'items':results}
    return result
