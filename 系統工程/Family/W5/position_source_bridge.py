"""W1 quantities × explicit quote/FX, then native value/protection reconciliation."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation,localcontext
from family_boundary import require,one,timestamp
from funding_guard import amount
from valuation import value_position
from family_input import digest


def native_number(value,field):
    try:
        require(not isinstance(value,bool) and value is not None,'NATIVE_NUMBER_INVALID',field)
        n=Decimal(str(value))
        require(n.is_finite() and n>=0,'NATIVE_NUMBER_INVALID',field)
        return n
    except InvalidOperation:
        require(False,'NATIVE_NUMBER_INVALID',field)


def quantity_time(request,position,context):
    """Separate original observation time from the accepted-snapshot boundary.

    Owner acceptance is already authenticated before native dispatch. It can
    establish a current analysis baseline without dating an undated screenshot
    or sealed row. It is not historical point-in-time observation evidence.
    """
    proof=context.get('holdings_completeness',{})
    if position is None:return proof['as_of'],'ACCOUNT_COMPLETENESS_BOUNDARY'
    if position.get('as_of_utc') is not None:return position['as_of_utc'],'SOURCE_OBSERVATION'
    snapshot=request['client_snapshot']['payload']
    require(position.get('source_kind') in ('SEALED_W6','OWNER_SCREENSHOT_SOURCE')
        and proof.get('schema_version')=='Family.W8.OfficialHoldingsAcceptance.v1'
        and proof.get('state')=='COMPLETE'
        and proof.get('client_id')==request['client_id']
        and proof.get('account_key')==request['owner']['account']
        and proof.get('source_db_sha256')==snapshot['source_sha256']
        and proof.get('snapshot_digest')==snapshot['payload_digest']
        and proof.get('owner_decision',{}).get('action')=='ACCEPT_EXISTING_OFFICIAL_HOLDINGS',
        'POSITION_OBSERVATION_TIME_REQUIRED','valuation.quantity.as_of','W1','DATA_UNAVAILABLE')
    require(timestamp(proof.get('as_of'),'holdings.accepted_at')<=timestamp(request['evaluation_at'],'evaluation_at'),
        'FUTURE_HOLDINGS_ACCEPTANCE','holdings.accepted_at')
    return proof['as_of'],'OWNER_ACCEPTANCE_BOUNDARY__NOT_ORIGINAL_OBSERVATION'


def bind_position_values(request,prepared,context):
    source=context.get('valuation_source')
    require(isinstance(source,dict),'VALUATION_INPUT_REQUIRED','trusted_context.valuation_source',status='DATA_UNAVAILABLE')
    require(request.get('valuation_digest')==digest(source),'VALUATION_VERSION_CONFLICT','valuation_digest')
    stock=prepared.payload['stock_source'];bonds=prepared.payload['family_sources']['bond']
    sources={stock['asset_id']:stock,**bonds}
    require(len(sources)==len(bonds)+1,'VALUATION_ASSET_COLLISION','valuation_source')
    require(set(source.get('prices',{}))==set(sources),'VALUATION_PRICE_COVERAGE','valuation_source.prices',status='DATA_UNAVAILABLE')
    bundle=request['native_bundle'];native_at=bundle['stock_request']['work3_handoff']['temporal']['as_of']
    result={}
    for asset,row in sources.items():
        price=source['prices'][asset]
        require(price.get('unit')=='CURRENCY_PER_SHARE','VALUATION_PRICE_UNIT_REQUIRED','prices.'+asset+'.unit')
        positions=[p for p in prepared.payload['positions'] if p['instrument_key']==row['instrument_key']]
        if row.get('approved_target_only'):
            instrument=row['source_instrument']  # Already authenticated by bind_bond_sources.
        else:
            instrument=(one(positions,'valuation.positions')['source_instrument'] if positions else
                one([r for r in request['client_snapshot']['payload']['tables']['portfolio_instrument']
                     if r['instrument_key']==row['instrument_key']],'valuation.instrument'))
        require(price.get('currency')==instrument['quote_currency'],'VALUATION_QUOTE_CURRENCY_MISMATCH','prices.'+asset)
        position=row['source_position']
        quantity_at,quantity_basis=quantity_time(request,position,context)
        qty={'state':'KNOWN','value':row['confirmed_quantity'],'instrument_key':row['instrument_key'],
            'as_of':quantity_at,'as_of_basis':quantity_basis,
            'original_observation_at':position.get('as_of_utc') if position else None,
            'source_reference':request['client_snapshot']['digest']+':'+row['instrument_key']}
        # Quantity must exist by the quote's valuation instant; preserve old quote dates.
        require(timestamp(qty['as_of'],'quantity.as_of')<=timestamp(price['as_of'],'price.as_of')
                <=timestamp(native_at,'native.as_of')<=timestamp(request['evaluation_at'],'evaluation_at'),
                'VALUATION_TIME_MISMATCH','prices.'+asset)
        valued=value_position(quantity=qty,price=price,fx=source.get('fx',{}).get(asset),
            target_currency=request['owner']['currency'],evaluation_at=price['as_of'])
        require(valued['state']=='KNOWN','POSITION_VALUATION_UNAVAILABLE','valuation.'+asset,status='DATA_UNAVAILABLE')
        result[asset]=valued
    quote=source['prices'][stock['asset_id']];facts=bundle['stock_evidence']
    observation_at=quote.get('price_observation_as_of',quote['as_of'])
    if observation_at!=quote['as_of']:
        require(quote.get('valuation_basis')=='CURRENT_QUANTITY_AT_KNOWN_REFERENCE_PRICE'
            and timestamp(observation_at,'price.observation')<=timestamp(quote['as_of'],'price.valuation')
            and bool(quote.get('price_source_digest')),
            'STOCK_VALUATION_REFERENCE_CLOCK_REQUIRED','stock_evidence.valuation_price')
    require(amount(quote['value'])==amount(facts['valuation_price']) and observation_at==facts['as_of'],
            'STOCK_VALUATION_SOURCE_MISMATCH','stock_evidence.valuation_price')
    holdings=bundle['bond_request']['v75_source_context']['existing_bond_holdings']
    for asset in bonds:
        if asset=='SGOV':continue  # Existing bond bucket is logical money, not all physical SGOV.
        found=[r for r in holdings if r['asset_id']==asset]
        if not found and amount(bonds[asset]['confirmed_quantity'])==0 and amount(result[asset]['value'])==0:
            continue  # Complete W1 source proves an approved target is not held.
        holding=one(found,'bond.valuation')
        require(native_number(holding['amount']['amount'],'bond.amount')==amount(result[asset]['value']),
                'BOND_VALUATION_MISMATCH','existing_bond_holdings.'+asset)
    require('SGOV' in bonds,'SGOV_PHYSICAL_SOURCE_REQUIRED','bond_instruments',status='DATA_UNAVAILABLE')
    physical=bundle['physical_sgov'];sgov=result['SGOV']
    require(physical.get('client_id')==request['client_id'] and physical.get('owner')==context['native_binding']['native_owner']
            and physical.get('currency')==request['owner']['currency'] and physical.get('run_id')==request['run_id'],
            'SGOV_PHYSICAL_OWNER_MISMATCH','physical_sgov')
    require(physical.get('as_of')==source['prices']['SGOV']['as_of']==physical.get('role_valuation_as_of')
            and native_number(physical.get('physical_market_value'),'physical_sgov.value')==amount(sgov['value']),
            'SGOV_PHYSICAL_VALUATION_MISMATCH','physical_sgov')
    return {'positions':result,'stock_asset_id':stock['asset_id'],'source_reference':request['client_snapshot']['digest'],
            'sgov_semantics':'PHYSICAL_VALUE_SEPARATE_FROM_LOGICAL_BOND_DRY_POWDER_AND_UNFILLED_CONTRIBUTION'}


def bind_stock_protection(request,prepared,context,values):
    projection=prepared.payload['stock_source']['policy'];asset=prepared.payload['stock_source']['asset_id']
    policy=projection['holding_policy']
    require(policy in ('HOLD_AS_IS','ADJUSTABLE'),'HOLDING_POLICY_UNAVAILABLE','stock.holding_policy',status='DATA_UNAVAILABLE')
    framework=request['native_bundle']['asset_framework']
    target=one([r for r in framework['integrated_asset_framework']['instrument_targets'] if r['instrument_id']==asset],'protected.target')
    drift=one([r for r in framework['drift_snapshot']['items'] if r['instrument_id']==asset],'protected.drift')
    locked=[r for r in framework['protected_locked_weights'] if r['instrument_id']==asset]
    protected=policy=='HOLD_AS_IS'
    require(target.get('protected') is protected and drift.get('protected') is protected
            and len(locked)==int(protected),'HOLDING_POLICY_FRAMEWORK_MISMATCH','asset_framework.protected')
    nav=context.get('valuation_source',{}).get('portfolio_nav',{})
    require(nav.get('state')=='KNOWN' and bool(nav.get('source_reference')),
            'PORTFOLIO_NAV_REQUIRED','valuation_source.portfolio_nav',status='DATA_UNAVAILABLE')
    denominator=framework['drift_snapshot']['denominator']
    require(nav.get('currency')==request['owner']['currency']==denominator['currency']
            and denominator['value_state']=='KNOWN' and amount(nav['value'])>0
            and native_number(denominator['amount'],'drift.denominator')==amount(nav['value'])
            and nav['as_of']==denominator['as_of']==framework['drift_snapshot']['as_of']
            ==values['positions'][asset]['sources']['price']['as_of'],
            'DRIFT_NAV_SOURCE_MISMATCH','drift_snapshot.denominator')
    with localcontext() as ctx:
        ctx.prec=50
        weight=amount(values['positions'][asset]['value'])/amount(nav['value'])
        current=drift['current_weight']
        require(current['value_state']=='KNOWN' and abs(native_number(current['value'],'drift.current')-weight)<=Decimal('1e-12'),
                'CURRENT_WEIGHT_VALUATION_MISMATCH','drift.current_weight')
        if protected:
            require(abs(native_number(locked[0]['current_weight'],'locked.current')-weight)<=Decimal('1e-12'),
                    'LOCKED_WEIGHT_VALUATION_MISMATCH','protected_locked_weights')
    return {'projection':deepcopy(projection),'instrument_binding':deepcopy(context['native_binding']['stock_instrument']),
            'current_weight':str(weight),'nav_source':deepcopy(nav),'scope':'STOCK_W1_POLICY_AND_CURRENT_WEIGHT; Work8 validates target/drift/client action'}
