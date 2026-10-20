"""Bind W1 stock identity/quantity and NEW_BUY policy before native dispatch.

This is a partial source mapping: it does not certify target units, C7 cash,
bond policy, macro derivation or protected-holding semantics.
"""
from copy import deepcopy
from family_boundary import require, one, timestamp
from family_input import digest
from funding_guard import amount
from permission_bridge import project_permissions


def bind_stock_source(request, prepared, binding):
    snapshot=request['client_snapshot']['payload']
    tables=snapshot['tables'];account=request['owner']['account']
    mapping=binding.get('stock_instrument')
    require(isinstance(mapping,dict) and bool(mapping.get('source_reference')),
            'STOCK_INSTRUMENT_MAPPING_REQUIRED','native_binding.stock_instrument',status='DATA_UNAVAILABLE')
    instrument=one([r for r in tables['portfolio_instrument']
                    if r['instrument_key']==mapping.get('instrument_key')],'stock.portfolio_instrument')
    native=request['native_bundle']['stock_request']['asset_context']
    facts=request['native_bundle']['stock_evidence']
    require(mapping.get('account_key')==account and mapping.get('native_owner')==binding['native_owner'],
            'STOCK_SOURCE_OWNER_MISMATCH','native_binding.stock_instrument')
    require(mapping.get('asset_id')==native['asset']['asset_id']==facts['asset_id']==instrument.get('ticker')
            and facts['exchange']==instrument.get('exchange_code')
            and facts['currency']==instrument.get('quote_currency')==request['owner']['currency'],
            'STOCK_INSTRUMENT_MISMATCH','stock.asset_identity')
    positions=[p for p in prepared.payload['positions'] if p['instrument_key']==instrument['instrument_key']]
    if positions:
        position=one(positions,'stock.positions')
        require(position['quantity_state']=='KNOWN','STOCK_QUANTITY_UNKNOWN','stock.position','W1','DATA_UNAVAILABLE')
        when=timestamp(position['source_position']['as_of_utc'],'stock.position.as_of')
        one([r for r in tables['portfolio_position'] if r['account_key']==account
             and r['instrument_key']==instrument['instrument_key']
             and timestamp(r['as_of_utc'],'stock.position.as_of')==when],'stock.latest_position')
        quantity=amount(position['quantity'])
        source=deepcopy(position['source_position'])
    else:
        # prepare_input has already required trusted account completeness evidence.
        quantity=amount('0');source=None
    require(amount(native['confirmed_position_snapshot']['quantity'])==quantity,
            'STOCK_POSITION_QUANTITY_MISMATCH','stock.confirmed_position_snapshot.quantity')
    policies=project_permissions(snapshot,account=account,evaluation_at=request['evaluation_at'])
    policy=one([p for p in policies if p['instrument_key']==instrument['instrument_key']],'stock.policy')
    return {'schema_version':'Family.W5.StockSource.v1','client_id':request['client_id'],
            'account_key':account,'asset_id':native['asset']['asset_id'],
            'instrument_key':instrument['instrument_key'],'snapshot_digest':digest(snapshot),
            'source_position':source,'confirmed_quantity':str(quantity),'policy':policy,
            'additional_new_buy_cap':None if policy['new_buy_candidate'] else '0',
            'scope':'STOCK_IDENTITY_QUANTITY_NEW_BUY_ONLY'}


def apply_stock_policy(bundle, source):
    """Add a cap to the existing V82 cap path; preserve original risk inputs."""
    data=deepcopy(bundle)
    if source is not None:
        require(source['asset_id']==data['stock_request']['asset_context']['asset']['asset_id'],
                'STOCK_POLICY_ASSET_MISMATCH','stock_source.asset_id')
        if source['additional_new_buy_cap']=='0':
            data['stock_evidence']['required_known_caps'].append('0')
    return data
