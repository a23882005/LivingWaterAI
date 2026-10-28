"""Convert from an explicit dated public quote; never infer a market rate."""
from decimal import Decimal

def convert(amount,source_currency,target_currency,observation):
    if source_currency==target_currency:return Decimal(str(amount))
    if not observation:return None
    if (observation.get('base_currency')!='USD' or observation.get('quote_currency')!='TWD'
        or not observation.get('as_of') or not observation.get('source_url')):raise ValueError('FX_SOURCE_REQUIRED')
    rate=Decimal(str(observation['quote_per_base']))
    if not rate.is_finite() or rate<=0:raise ValueError('FX_RATE_INVALID')
    value=Decimal(str(amount))
    if (source_currency,target_currency)==('TWD','USD'):return value/rate
    if (source_currency,target_currency)==('USD','TWD'):return value*rate
    return None
