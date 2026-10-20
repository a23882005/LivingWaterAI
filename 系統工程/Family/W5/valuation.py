"""Exact unit conversion only: quantity × price × explicit FX; no price producer."""
from copy import deepcopy
from decimal import Decimal,localcontext
from family_boundary import require,timestamp
from funding_guard import amount


def value_position(*,quantity,price,fx,target_currency,evaluation_at):
    at=timestamp(evaluation_at,'evaluation_at')
    sources={'quantity':deepcopy(quantity),'price':deepcopy(price),'fx':deepcopy(fx)}
    unknown=lambda code:{'state':'UNKNOWN','value':None,'currency':target_currency,'issue_codes':[code],'sources':sources}
    if quantity.get('state') not in ('KNOWN','ESTIMATED'):return unknown('QUANTITY_UNKNOWN')
    if price.get('state')!='KNOWN':return unknown('PRICE_UNKNOWN')
    for name,src in [('quantity',quantity),('price',price)]:
        require(bool(src.get('source_reference')),'VALUATION_SOURCE_REQUIRED',name)
        require(timestamp(src.get('as_of'),name+'.as_of')<=at,'FUTURE_VALUATION',name)
    require(quantity.get('instrument_key')==price.get('instrument_key') and bool(quantity.get('instrument_key')),'VALUATION_INSTRUMENT_MISMATCH','price.instrument_key')
    q=amount(quantity.get('value'));p=amount(price.get('value'));rate=Decimal(1)
    require(bool(target_currency) and bool(price.get('currency')),'VALUATION_CURRENCY_REQUIRED','currency')
    if price['currency']!=target_currency:
        if not fx or fx.get('state')!='KNOWN':return unknown('FX_UNKNOWN')
        require(fx.get('from_currency')==price['currency'] and fx.get('to_currency')==target_currency,'FX_CURRENCY_MISMATCH','fx')
        require(bool(fx.get('source_reference')) and timestamp(fx.get('as_of'),'fx.as_of')<=at,'FX_SOURCE_OR_TIME_INVALID','fx')
        rate=amount(fx.get('value'));require(rate>0,'FX_RATE_INVALID','fx.value')
    with localcontext() as ctx:
        ctx.prec=sum(len(x.as_tuple().digits) for x in (q,p,rate))+3
        result=q*p*rate
    return {'state':'ESTIMATED' if quantity['state']=='ESTIMATED' else 'KNOWN','value':str(result),'currency':target_currency,'issue_codes':[],'sources':sources}
