"""W1 physical quantities and new-buy permission; logical SGOV money stays separate."""
from copy import deepcopy
from family_boundary import require,one,timestamp
from funding_guard import amount
from permission_bridge import project_permissions


def bind_bond_sources(request,prepared,binding):
    snapshot=request['client_snapshot']['payload'];tables=snapshot['tables']
    account=request['owner']['account'];bundle=request['native_bundle']
    mappings=binding.get('bond_instruments')
    require(isinstance(mappings,dict) and set(mappings)==set(bundle['bond_evidence']),
            'BOND_INSTRUMENT_MAPPING_REQUIRED','native_binding.bond_instruments',status='DATA_UNAVAILABLE')
    policies=project_permissions(snapshot,account=account,evaluation_at=request['evaluation_at'],
        positions=prepared.payload['positions'])
    native_owner=binding['native_owner']
    native_context=bundle['bond_request']['v75_source_context']
    for name,value_field in [('existing_bond_holdings','amount'),('target_bond_holdings','target_amount')]:
        for row in native_context[name]:
            require(row['broker_account_id']==native_owner['account']
                    and row[value_field]['currency']==request['owner']['currency'],
                    'BOND_HOLDING_OWNER_MISMATCH','v75_source_context.'+name)
    result={};used=set()
    for asset,facts in bundle['bond_evidence'].items():
        mapping=mappings[asset];key=mapping.get('instrument_key')
        require(facts.get('broker_account_id')==native_owner['account'],
                'BOND_EVIDENCE_OWNER_MISMATCH','bond_evidence.'+asset)
        require(key not in used,'DUPLICATE_BOND_INSTRUMENT','bond_instruments');used.add(key)
        positions=[p for p in prepared.payload['positions'] if p['instrument_key']==key]
        registered=[r for r in tables['portfolio_instrument'] if r['instrument_key']==key]
        target_only=not positions and not registered
        if target_only:
            target=mapping.get('approved_target_source')
            require(isinstance(target,dict) and target in request['confirmed_target']['payload']['draft']['target_lines']
                and target.get('ticker')==asset and key=='APPROVED_TARGET:'+target['instrument_id'],
                'BOND_TARGET_INSTRUMENT_SOURCE_REQUIRED','bond_instruments.'+asset)
            instrument={'ticker':asset,'exchange_code':None,
                'quote_currency':facts['currency'],'instrument_key':key}
        else:
            instrument=(one(positions,'bond.positions')['source_instrument'] if positions else one(registered,'bond.instrument'))
        require(mapping.get('source_reference') and mapping.get('account_key')==account
                and mapping.get('native_owner')==binding['native_owner'],
                'BOND_SOURCE_OWNER_MISMATCH','bond_instruments.'+asset)
        reference=mapping.get('market_reference')
        exchange_matches=instrument.get('exchange_code')==mapping.get('exchange')
        if reference is not None:
            require(reference.get('scope')=='ANALYSIS_MARKET_REFERENCE__NOT_HELD_OR_EXECUTION_VENUE'
                and reference.get('asset_id')==asset and reference.get('exchange')==mapping.get('exchange')
                and reference.get('currency')==facts['currency']
                and reference.get('source_digest')==facts.get('market_identity_digest')
                and bool(reference.get('source_reference')),
                'BOND_MARKET_REFERENCE_MISMATCH','bond_instruments.'+asset)
            exchange_matches=True
        require(instrument.get('ticker')==asset==facts.get('asset_id')
                and exchange_matches
                and bool(mapping.get('exchange'))
                and instrument.get('quote_currency')==facts['currency']==request['owner']['currency'],
                'BOND_INSTRUMENT_MISMATCH','bond_instruments.'+asset)
        source=None;quantity=amount('0')
        if positions:
            p=one(positions,'bond.positions')
            require(p['quantity_state']=='KNOWN','BOND_QUANTITY_UNKNOWN','bond.positions','W1','DATA_UNAVAILABLE')
            source=deepcopy(p['source_position']);quantity=amount(p['quantity'])
            if source.get('source_kind')=='BROKER_READONLY_SNAPSHOT':
                view=prepared.payload.get('broker_snapshot_source')
                require(view is not None and view['owner']==request['owner']
                    and view['source_descriptor_digest']==request.get('broker_snapshot_source_digest')
                    and any(r['contract_id']==instrument.get('broker_contract_id')
                        and amount(r['quantity'])==quantity for r in view['positions']),
                    'BOND_BROKER_SOURCE_MISMATCH','bond.position.source_row')
            elif source.get('source_kind') in ('SEALED_W6','OWNER_SCREENSHOT_SOURCE'):
                require(source['source_row'] in tables['portfolio_snapshot_item'],
                        'BOND_SEALED_SOURCE_MISMATCH','bond.position.source_row')
            else:
                when=timestamp(source['as_of_utc'],'bond.position.as_of')
                one([r for r in tables['portfolio_position'] if r['account_key']==account and r['instrument_key']==key
                     and timestamp(r['as_of_utc'],'bond.position.as_of')==when],'bond.latest_position')
        logical=quantity
        if asset=='SGOV' and facts.get('sgov_role_binding') is not None:
            roles=facts['sgov_role_binding'];boundary=bundle['stock_request']['work3_handoff']['funding_context']['sgov_boundary']
            physical=bundle['physical_sgov']
            require(all(roles.get(k)==boundary.get(k) for k in
                ('sgov_bond_bucket_amount','sgov_dry_powder_bucket_amount'))
                and amount(roles['physical_quantity'])==quantity
                and amount(roles['physical_value'])==amount(physical['physical_market_value'])
                and amount(roles['physical_value'])==sum(amount(roles[k]['amount']) for k in
                    ('sgov_bond_bucket_amount','sgov_dry_powder_bucket_amount')),
                'BOND_SGOV_ROLE_SOURCE_MISMATCH','bond_evidence.SGOV.sgov_role_binding')
            bond_amount=amount(roles['sgov_bond_bucket_amount']['amount'])
            require(bond_amount in (0,amount(roles['physical_value'])),
                'BOND_MIXED_ROLE_QUANTITY_SOURCE_REQUIRED','bond_evidence.SGOV.sgov_role_binding',status='DATA_UNAVAILABLE')
            logical=quantity if bond_amount>0 else amount('0')
        require(logical==amount(facts['existing_policy']['current_position_quantity']),
                'BOND_POSITION_QUANTITY_MISMATCH','bond_evidence.'+asset+'.existing_policy.current_position_quantity')
        policy=({'new_buy_candidate':False,'reason_codes':['W1_PERMISSION_NOT_REGISTERED'],
            'holding_policy':'UNCONFIRMED','existing_holding':False} if target_only else
            one([p for p in policies if p['instrument_key']==key],'bond.policy'))
        result[asset]={'asset_id':asset,'instrument_key':key,'confirmed_quantity':str(quantity),
            'logical_bond_quantity':str(logical),'market_reference':deepcopy(reference),
            'held_exchange':instrument.get('exchange_code'),'approved_target_only':target_only,
            'source_instrument':deepcopy(instrument),
            'source_position':source,'policy':policy,'additional_new_buy_cap':None if policy['new_buy_candidate'] else '0',
            'scope':'PHYSICAL_QUANTITY_AND_NEW_BUY_ONLY; valuation/logical SGOV/protected actions validated separately'}
    return result
