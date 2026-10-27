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
        instrument=(one(positions,'bond.positions')['source_instrument'] if positions else
            one([r for r in tables['portfolio_instrument'] if r['instrument_key']==key],'bond.instrument'))
        require(mapping.get('source_reference') and mapping.get('account_key')==account
                and mapping.get('native_owner')==binding['native_owner'],
                'BOND_SOURCE_OWNER_MISMATCH','bond_instruments.'+asset)
        require(instrument.get('ticker')==asset==facts.get('asset_id')
                and instrument.get('exchange_code')==mapping.get('exchange')
                and bool(mapping.get('exchange'))
                and instrument.get('quote_currency')==facts['currency']==request['owner']['currency'],
                'BOND_INSTRUMENT_MISMATCH','bond_instruments.'+asset)
        source=None;quantity=amount('0')
        if positions:
            p=one(positions,'bond.positions')
            require(p['quantity_state']=='KNOWN','BOND_QUANTITY_UNKNOWN','bond.positions','W1','DATA_UNAVAILABLE')
            source=deepcopy(p['source_position']);quantity=amount(p['quantity'])
            if source.get('source_kind') in ('SEALED_W6','OWNER_SCREENSHOT_SOURCE'):
                require(source['source_row'] in tables['portfolio_snapshot_item'],
                        'BOND_SEALED_SOURCE_MISMATCH','bond.position.source_row')
            else:
                when=timestamp(source['as_of_utc'],'bond.position.as_of')
                one([r for r in tables['portfolio_position'] if r['account_key']==account and r['instrument_key']==key
                     and timestamp(r['as_of_utc'],'bond.position.as_of')==when],'bond.latest_position')
        require(quantity==amount(facts['existing_policy']['current_position_quantity']),
                'BOND_POSITION_QUANTITY_MISMATCH','bond_evidence.'+asset+'.existing_policy.current_position_quantity')
        policy=one([p for p in policies if p['instrument_key']==key],'bond.policy')
        result[asset]={'asset_id':asset,'instrument_key':key,'confirmed_quantity':str(quantity),
            'source_position':source,'policy':policy,'additional_new_buy_cap':None if policy['new_buy_candidate'] else '0',
            'scope':'PHYSICAL_QUANTITY_AND_NEW_BUY_ONLY; valuation/logical SGOV/protected actions validated separately'}
    return result
