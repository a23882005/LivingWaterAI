"""Historical data convention guards; never adjust prices or invent evidence."""
from decimal import Decimal, InvalidOperation
from replay import ReplayError, instant


def _positive(value):
    if isinstance(value,bool):raise ReplayError('INVALID_POSITIVE_NUMBER')
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError):raise ReplayError('INVALID_POSITIVE_NUMBER')
    if not n.is_finite() or n<=0:raise ReplayError('INVALID_POSITIVE_NUMBER')
    return n


def validate_basis(contract, *, cutoff):
    """The source registry must substantiate referenced evidence separately."""
    limit=instant(cutoff)
    if contract.get('price_basis') not in ('RAW','SPLIT_ADJUSTED','TOTAL_RETURN'):
        raise ReplayError('PRICE_BASIS_UNKNOWN')
    if contract.get('split_basis_verified') is not True:
        raise ReplayError('SPLIT_BASIS_UNVERIFIED')
    if not contract.get('evidence_ref') or not contract.get('available_at'):
        raise ReplayError('AVAILABILITY_EVIDENCE_REQUIRED')
    if instant(contract['available_at'])>limit:raise ReplayError('FUTURE_SOURCE')
    if contract.get('dividend_mode') not in ('CASH_SEPARATE','INCLUDED_IN_TOTAL_RETURN'):
        raise ReplayError('DIVIDEND_MODE_REQUIRED')
    if (contract['price_basis']=='TOTAL_RETURN') != (contract['dividend_mode']=='INCLUDED_IN_TOTAL_RETURN'):
        raise ReplayError('DIVIDEND_DOUBLE_COUNT_OR_OMISSION')
    for action in contract.get('splits',[]):
        _positive(action['new_shares_per_old_share'])
        if not action.get('evidence_ref'):raise ReplayError('SPLIT_EVIDENCE_REQUIRED')
        if instant(action['available_at'])>limit or instant(action['effective_at'])>limit:
            raise ReplayError('FUTURE_SPLIT')
        if contract['price_basis']!='RAW' and action.get('apply_price_adjustment') is not False:
            raise ReplayError('SPLIT_DOUBLE_ADJUSTMENT')
    currency,base=contract.get('quote_currency'),contract.get('base_currency')
    if not currency or not base:raise ReplayError('CURRENCY_REQUIRED')
    if currency!=base:
        fx=contract.get('fx')
        if not fx or fx.get('from_currency')!=currency or fx.get('to_currency')!=base or fx.get('unit')!='TO_PER_FROM':
            raise ReplayError('FX_DIRECTION_REQUIRED')
        _positive(fx['rate'])
        if not fx.get('evidence_ref'):raise ReplayError('FX_EVIDENCE_REQUIRED')
        observed,available=instant(fx['observed_at']),instant(fx['available_at'])
        if observed>available or available>limit:raise ReplayError('FUTURE_FX')
        age=contract.get('max_fx_age_seconds')
        if not isinstance(age,int) or isinstance(age,bool) or age<0:
            raise ReplayError('FX_AGE_POLICY_REQUIRED')
        if (limit-observed).total_seconds()>age:raise ReplayError('STALE_FX')
    return {'status':'PASS','price_basis':contract['price_basis'],
        'dividend_mode':contract['dividend_mode'],'adjustments_applied':0}
